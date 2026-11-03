"""Project guide analysis agent contracts."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Annotated, Literal, Protocol
from uuid import UUID

from app.modules.checkers.api.artifact_paths import (
    is_canonical_relative_path,
    is_canonical_relative_pattern,
)

from pydantic import (
    BaseModel,
    ValidationError,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from app.core.hashing import canonical_json_hash
from app.modules.projects.api.task_examples import ProjectGuideTaskExamples
from app.interfaces.external_services import (
    ExternalServiceAdapter,
    ExternalServiceAdapterError,
    ExternalServiceConfigurationError,
)
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.modules.projects.api.guide_documents import (
    GuideDocumentManifest,
    GuideRuntimeCapabilities,
)


MAXIMUM_PROJECT_GUIDE_COMPILATION_PROMPT_BYTES = 1_000_000
MAXIMUM_COMPILATION_FINDINGS = 100
MAXIMUM_COMPILATION_REQUIREMENTS = 200
MAXIMUM_COMPILATION_RESULT_STORAGE_BYTES = 4_194_304
MAXIMUM_COMPILATION_NOTES = 20
MAXIMUM_EVIDENCE_REFS = 20
PROJECT_GUIDE_COMPILATION_AGENT_IDENTITY = "project-guide-compilation-agent-v1"
PROJECT_GUIDE_COMPILATION_AGENT_NAME = "ProjectGuideCompilationAgent"
PROJECT_GUIDE_COMPILATION_AGENT_VERSION = "v1"
PROJECT_GUIDE_COMPILATION_INSTRUCTION_VERSION = "v1"
PROJECT_GUIDE_COMPILATION_SCHEMA_VERSION = "project_guide_check_specification.v1"

_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")
_UNSAFE_MODEL_TEXT = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f]|(?:https?|file|data|ssh)://|"
    r"(?:^|\s)(?:/|\\\\|\.\.?/|[a-z]:\\|[\w.-]+/[\w./-]+)|"
    r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b|"
    r"\b(?:bearer\s+\S+|(?:password|secret|credential|api[_ -]?key|token)"
    r"\b\s*(?:[:=]\s*\S+|\s+(?=\S*(?:\d|[-_=+/]))\S+))|"
    r"\brequire\s*\(|\b(?:import|pip install|npm install|"
    r"curl|wget|powershell|bash|sh)\b",
    re.IGNORECASE,
)


_MODEL_PROSE_SCHEMA = {
    "minLength": 1,
    "maxLength": 1000,
    "description": (
        "Plain prose only. No URLs, email addresses, credentials, filesystem paths, "
        "slash-separated words, code, or executable command names. Spell alternatives "
        "with words (for example, 'training and evaluation', not a slash expression). "
        "Describe shell instructions and module loading without literal command tokens. "
        "Source-defined field identifiers, types, numeric constraints and constants "
        "may be described explicitly; put file and directory paths in typed relative_path inputs."
    ),
}
ModelProse = Annotated[str, Field(json_schema_extra=_MODEL_PROSE_SCHEMA)]
PolicyIdentifier = Annotated[
    str,
    Field(
        json_schema_extra={
            "pattern": _SAFE_IDENTIFIER.pattern,
            "minLength": 1,
            "maxLength": 100,
            "description": "Canonical machine identifier, not prose or a file path: start with a lowercase letter, then lowercase letters, digits, underscores, dots or hyphens. Example: results or rights_confirmed.",
        }
    ),
]


def _validated_safe_model_text(value: str) -> str:
    """Reject unsafe or unbounded model-produced operator text."""
    if not value or len(value) > 1000 or _UNSAFE_MODEL_TEXT.search(value):
        raise ValueError("model-produced text is unsafe")
    return value


def _validated_identifier(value: str) -> str:
    """Require one bounded canonical identifier."""
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError("identifier is invalid")
    return value


class CompilationStage(StrEnum):
    """Closed checker stages available to unified compilation."""

    PRE_SUBMIT = "pre_submit"
    POST_SUBMIT = "post_submit"


class GuideEvidenceRef(BaseModel):
    """Untrusted page/section attribution bound to an exact original document version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_item_id: UUID
    document_version_id: UUID
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    start_page: StrictInt | None = Field(default=None, ge=1, le=100_000)
    end_page: StrictInt | None = Field(default=None, ge=1, le=100_000)
    section: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Optional plain-prose section label. Paraphrase headings; do not copy URLs, "
            "paths, slash-separated phrases, credentials or executable command tokens."
        ),
    )

    @field_validator("section")
    @classmethod
    def validate_section(cls, value: str | None) -> str | None:
        """Keep section labels bounded and safe; they are not independently verified."""
        return _validated_safe_model_text(value) if value is not None else None

    @model_validator(mode="after")
    def validate_pages(self) -> GuideEvidenceRef:
        """Require both ends of a coherent optional page range."""
        if (self.start_page is None) != (self.end_page is None):
            raise ValueError("evidence page range is incomplete")
        if self.start_page is not None and self.end_page < self.start_page:
            raise ValueError("evidence page range is invalid")
        return self


class CompilationFinding(BaseModel):
    """One bounded operator-visible finding from unified compilation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Literal["blocking_gap", "warning", "info"]
    code: str = Field(json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern})
    message: ModelProse
    evidence_refs: tuple[GuideEvidenceRef, ...] = Field(
        default=(), max_length=MAXIMUM_EVIDENCE_REFS
    )

    _code = field_validator("code")(_validated_identifier)
    _message = field_validator("message")(_validated_safe_model_text)


class CheckInput(BaseModel):
    """One exact material or context input needed by a proposed check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_id: PolicyIdentifier
    kind: PolicyIdentifier
    relative_path: (
        Annotated[
            str,
            Field(
                min_length=1,
                max_length=500,
                description="Canonical relative POSIX path inside the submitted package.",
            ),
        ]
        | None
    ) = Field(default=None, exclude_if=lambda value: value is None)
    purpose: ModelProse

    _input_id = field_validator("input_id")(_validated_identifier)
    _kind = field_validator("kind")(_validated_identifier)
    _purpose = field_validator("purpose")(_validated_safe_model_text)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str | None) -> str | None:
        """Only canonical paths within a submitted package may be proposed."""
        if value is not None and not is_canonical_relative_path(value):
            raise ValueError("check input relative path is invalid")
        return value


class CheckFailureFinding(BaseModel):
    """One stable work finding an implementation must return when observed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: PolicyIdentifier
    level: Literal["warning", "error"]
    condition: ModelProse
    message: ModelProse

    _code = field_validator("code")(_validated_identifier)
    _condition = field_validator("condition")(_validated_safe_model_text)
    _message = field_validator("message")(_validated_safe_model_text)


class CheckNegativeTest(BaseModel):
    """One representative non-happy path and its exact observable outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: PolicyIdentifier
    scenario: ModelProse
    expected_verdict: Literal["passed", "failed"]
    expected_finding_codes: tuple[PolicyIdentifier, ...] = Field(min_length=1, max_length=10)

    _name = field_validator("name")(_validated_identifier)
    _scenario = field_validator("scenario")(_validated_safe_model_text)

    @field_validator("expected_finding_codes")
    @classmethod
    def validate_expected_finding_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Keep the expected finding set stable, bounded and unambiguous."""
        if len(values) != len(set(values)):
            raise ValueError("negative test finding codes must be unique")
        return tuple(_validated_identifier(value) for value in values)


class CheckInabilityToEvaluate(BaseModel):
    """A proposed condition where no work verdict can be established."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: PolicyIdentifier
    condition: ModelProse

    _code = field_validator("code")(_validated_identifier)
    _condition = field_validator("condition")(_validated_safe_model_text)


class CheckSpecification(BaseModel):
    """Source-derived check handoff with no claim about available implementations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evaluation_method: ModelProse = Field(
        description="Proposed way to observe the outcome, not a supported runtime selector."
    )
    inputs: tuple[CheckInput, ...] = Field(min_length=1, max_length=20)
    check_steps: tuple[ModelProse, ...] = Field(min_length=1, max_length=20)
    pass_conditions: tuple[ModelProse, ...] = Field(min_length=1, max_length=20)
    failure_findings: tuple[CheckFailureFinding, ...] = Field(min_length=1, max_length=20)
    positive_tests: tuple[ModelProse, ...] = Field(min_length=1, max_length=10)
    negative_tests: tuple[CheckNegativeTest, ...] = Field(min_length=1, max_length=10)
    implementation_needs: tuple[ModelProse, ...] = Field(min_length=1, max_length=10)
    inability_to_evaluate: tuple[CheckInabilityToEvaluate, ...] = Field(
        min_length=1, max_length=10,
        description="Conditions where an implementation cannot establish a work verdict.",
    )

    _evaluation_method = field_validator("evaluation_method")(_validated_safe_model_text)

    @field_validator("check_steps", "pass_conditions", "positive_tests", "implementation_needs")
    @classmethod
    def validate_prose_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_validated_safe_model_text(value) for value in values)

    @model_validator(mode="after")
    def validate_linkage(self) -> CheckSpecification:
        """Keep work findings and inability to evaluate separate and unambiguous."""
        for values, message in (
            ([item.input_id for item in self.inputs], "check inputs must be unique"),
            ([item.code for item in self.failure_findings], "check failure findings must be unique"),
            ([item.name for item in self.negative_tests], "check negative tests must be unique"),
            ([item.code for item in self.inability_to_evaluate], "evaluation inability codes must be unique"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(message)
        findings = {item.code: item for item in self.failure_findings}
        if set(findings).intersection(item.code for item in self.inability_to_evaluate):
            raise ValueError("work and evaluation inability codes must be distinct")
        for test in self.negative_tests:
            referenced = [findings.get(code) for code in test.expected_finding_codes]
            if any(item is None for item in referenced):
                raise ValueError("negative test references an unknown work finding")
            has_error = any(item.level == "error" for item in referenced if item is not None)
            if (test.expected_verdict == "failed") != has_error:
                raise ValueError("negative test verdict disagrees with its findings")
        return self


class AtomicGuideRequirement(BaseModel):
    """One source-linked project check specification, independent of implementations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    suggestion_id: str = Field(json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern})
    statement: ModelProse
    stage: CompilationStage
    classification_rationale: ModelProse
    check_specification: CheckSpecification
    evidence_refs: tuple[GuideEvidenceRef, ...] = Field(
        min_length=1, max_length=MAXIMUM_EVIDENCE_REFS
    )

    _suggestion_id = field_validator("suggestion_id")(_validated_identifier)
    _statement = field_validator("statement")(_validated_safe_model_text)
    _classification_rationale = field_validator("classification_rationale")(
        _validated_safe_model_text
    )


class SubmissionArtifactPolicyProposal(BaseModel):
    """Closed submission artifact policy proposed by compilation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    packaging: Literal["zip"] = "zip"
    maximum_file_size_bytes: StrictInt | None = Field(
        default=None,
        gt=0,
        le=10 * 1024 * 1024 * 1024,
        description="Project-specific maximum expanded bytes per submitted file. Null adds no project limit; platform safety limits always apply.",
    )
    maximum_package_size_bytes: StrictInt | None = Field(
        default=None,
        gt=0,
        le=10 * 1024 * 1024 * 1024,
        description="Project-specific maximum total expanded bytes in the submitted ZIP, verified from actual contents; not compressed upload bytes. Null adds no project limit; platform safety limits always apply.",
    )
    maximum_archive_size_bytes: StrictInt | None = Field(
        default=None,
        gt=0,
        description="Maximum verified byte count of the entire submitted compressed ZIP, including archive metadata; not expanded contents or summed compressed member sizes. Null adds no project limit; platform safety limits always apply.",
    )
    maximum_archive_entries: StrictInt | None = Field(
        default=None,
        gt=0,
        description="Maximum normalized outer ZIP entries, counting files and directory entries including implied parent directories. Omitting a directory record cannot evade the limit. Nested archives count as files, not recursively expanded members. Null adds no project limit; platform safety limits always apply.",
    )
    allowed_storage_schemes: tuple[Literal["artifact"], ...] = ("artifact",)
    required_artifacts: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...] = Field(
        default=(),
        max_length=100,
        description="Exact canonical relative POSIX regular-file paths inside the submitted ZIP. Required directories belong in checker specifications, never this hash-required file list. A bare path such as task.toml requires that file at the ZIP root; wrapper/task.toml does not satisfy it. Nested paths such as outputs/answer.md require that exact location. No trailing separators, duplicate paths, traversal, storage references or secret files.",
    )
    forbidden_artifacts: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...] = Field(
        default=(),
        max_length=100,
        description="Relative artifact prohibition patterns, such as secret* or outputs/*.tmp; these are machine fields, not prose.",
    )
    required_evidence: tuple[PolicyIdentifier, ...] = Field(default=(), max_length=100)
    attestation_terms: tuple[PolicyIdentifier, ...] = Field(default=(), max_length=50)

    @field_validator("required_artifacts")
    @classmethod
    def validate_required_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Artifact paths are machine fields, not display prose."""
        if len(values) != len(set(values)) or not all(
            is_canonical_relative_path(value) for value in values
        ):
            raise ValueError("artifact policy paths must be unique canonical relative paths")
        return values

    @field_validator("forbidden_artifacts")
    @classmethod
    def validate_forbidden_patterns(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Express prohibition patterns without treating their secret names as requests."""
        if len(values) != len(set(values)) or not all(
            is_canonical_relative_pattern(value) for value in values
        ):
            raise ValueError("artifact policy patterns must be unique canonical relative patterns")
        return values

    @field_validator("required_evidence", "attestation_terms")
    @classmethod
    def validate_policy_identifiers(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Evidence and attestations use bounded machine identifiers."""
        if len(values) != len(set(values)):
            raise ValueError("artifact policy values must be unique")
        return tuple(_validated_identifier(value) for value in values)

    @model_validator(mode="after")
    def validate_package_limit(self) -> SubmissionArtifactPolicyProposal:
        """Require coherent file/package limits and artifact sets."""
        if (
            self.maximum_file_size_bytes is not None
            and self.maximum_package_size_bytes is not None
            and self.maximum_file_size_bytes > self.maximum_package_size_bytes
        ):
            raise ValueError("file limit exceeds package limit")
        if set(self.required_artifacts).intersection(self.forbidden_artifacts):
            raise ValueError("artifact policy requirements conflict")
        return self


class ProjectGuideCompilationResult(BaseModel):
    """Strict untrusted proposal; trusted code must validate it with context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["guide_blocked", "draft_ready", "draft_ready_with_warnings"]
    findings: tuple[CompilationFinding, ...] = Field(
        default=(), max_length=MAXIMUM_COMPILATION_FINDINGS
    )
    submission_artifact_policy: SubmissionArtifactPolicyProposal | None = None
    requirements: tuple[AtomicGuideRequirement, ...] = Field(
        default=(), max_length=MAXIMUM_COMPILATION_REQUIREMENTS
    )
    setup_notes: tuple[ModelProse, ...] = Field(default=(), max_length=MAXIMUM_COMPILATION_NOTES)
    agent_name: Literal["ProjectGuideCompilationAgent"] = "ProjectGuideCompilationAgent"
    agent_version: str = Field(
        max_length=100, json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern}
    )
    schema_version: Literal["project_guide_check_specification.v1"] = (
        "project_guide_check_specification.v1"
    )

    @field_validator("setup_notes")
    @classmethod
    def validate_notes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject unsafe setup notes before trusted validation."""
        return tuple(_validated_safe_model_text(value) for value in values)

    _agent_version = field_validator("agent_version")(_validated_identifier)


class ProjectGuideCorrectionFeedback(BaseModel):
    """Bounded manager input tied to the exact result being reconsidered."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    predecessor_compilation_id: UUID
    predecessor_result_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    target_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=4000)


class ProjectGuideCompilationContext(BaseModel):
    """Exact bounded input for one future unified compilation attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    material: GuideDocumentManifest
    setup_run_id: UUID
    setup_generation: StrictInt = Field(ge=1)
    instruction_version: str = Field(max_length=100)
    agent_identity: str = Field(max_length=100)
    agent_version: str = Field(
        max_length=100, json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern}
    )
    runtime_configuration: ProjectGuideRuntimeConfiguration
    task_examples: ProjectGuideTaskExamples
    correction_feedback: ProjectGuideCorrectionFeedback | None = None
    correction_predecessor: ProjectGuideCompilationResult | None = None

    @model_validator(mode="after")
    def validate_instruction_configuration(self) -> ProjectGuideCompilationContext:
        """Bind the semantic instruction version to its exact execution snapshot."""
        self.require_correction_predecessor()
        configuration = self.runtime_configuration
        if (
            self.material.setup_run_id != self.setup_run_id
            or self.material.setup_generation != self.setup_generation
            or len(self.material.documents) > configuration.maximum_documents
            or any(
                item.byte_count > configuration.maximum_document_bytes
                for item in self.material.documents
            )
            or sum(item.byte_count for item in self.material.documents)
            > configuration.maximum_total_document_bytes
        ):
            raise ValueError("compilation document manifest exceeds its execution boundary")
        if self.instruction_version != self.runtime_configuration.instruction_version:
            raise ValueError("compilation instruction configuration mismatch")
        return self

    def require_correction_predecessor(self) -> None:
        """Authenticate derived correction material against its existing commitment."""
        feedback = self.correction_feedback
        predecessor = self.correction_predecessor
        if (feedback is None) != (predecessor is None):
            raise ValueError("correction feedback and predecessor must be paired")
        if (
            feedback is not None
            and canonical_json_hash(predecessor.model_dump(mode="json"))
            != feedback.predecessor_result_hash
        ):
            raise ValueError("correction predecessor hash mismatch")


def canonical_project_guide_compilation_context_bytes(
    context: ProjectGuideCompilationContext,
) -> bytes:
    """Serialize one context without double-encoding canonical guide JSON."""
    context.require_correction_predecessor()
    # The immutable feedback hash already commits this exact derived body.
    body = context.model_dump(mode="json", exclude={"correction_predecessor"})
    if context.correction_feedback is None:
        # Absent optional input contributes no canonical field; a real
        # correction is always included in the exact attempt identity.
        del body["correction_feedback"]
    return json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def project_guide_compilation_prompt_bytes(context: ProjectGuideCompilationContext) -> bytes:
    """Give the model only assigned originals and task examples."""
    context.require_correction_predecessor()
    body = {
        "material": context.material.agent_projection(),
        "task_examples": [item.model_dump(mode="json") for item in context.task_examples],
    }
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


_COMPLETE_COMPILATION_RESULT_FIELDS = frozenset(ProjectGuideCompilationResult.model_fields) - {
    "setup_notes"
}


def require_complete_project_guide_compilation_result(
    result: ProjectGuideCompilationResult,
) -> None:
    """Reject provider output that omitted any member of the strict envelope."""
    if _COMPLETE_COMPILATION_RESULT_FIELDS - result.model_fields_set:
        raise ValueError("compilation result envelope is incomplete")


def validate_project_guide_compilation_result(
    context: ProjectGuideCompilationContext,
    result: ProjectGuideCompilationResult,
) -> None:
    """Validate source lineage, status, and bounded specification-only output."""
    if project_guide_compilation_result_storage_bytes(result) > MAXIMUM_COMPILATION_RESULT_STORAGE_BYTES:
        raise ValueError("compilation result exceeds storage byte limit")
    identifiers = [item.suggestion_id for item in result.requirements]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("compilation requirements must be unique")
    has_blocker = any(item.severity == "blocking_gap" for item in result.findings)
    has_warning = any(item.severity == "warning" for item in result.findings)
    if result.status == "guide_blocked":
        if not has_blocker:
            raise ValueError("blocked compilation requires blocking evidence")
        if result.submission_artifact_policy is not None or result.requirements:
            raise ValueError("blocked guide cannot publish policy proposals")
    else:
        if has_blocker:
            raise ValueError("ready compilation cannot contain blocking evidence")
        if result.submission_artifact_policy is None:
            raise ValueError("draft-ready compilation requires artifact policy")
        if result.status == "draft_ready" and has_warning:
            raise ValueError("draft-ready compilation cannot contain warnings")
        if result.status == "draft_ready_with_warnings" and not has_warning:
            raise ValueError("warning-ready compilation requires a warning")
    source_lineage = {
        (item.source_item_id, item.ingest_id, item.sha256)
        for item in context.material.documents
    }
    refs = (
        *(ref for finding in result.findings for ref in finding.evidence_refs),
        *(ref for requirement in result.requirements for ref in requirement.evidence_refs),
    )
    if any(
        (ref.source_item_id, ref.document_version_id, ref.sha256) not in source_lineage
        for ref in refs
    ):
        raise ValueError("compilation evidence does not resolve to source lineage")


def require_ready_result_cites_every_document(
    context: ProjectGuideCompilationContext,
    result: ProjectGuideCompilationResult,
) -> None:
    """Require a ready proposal to account for every assigned original."""
    cited = {
        ref.source_item_id
        for item in (*result.findings, *result.requirements)
        for ref in item.evidence_refs
    }
    if result.status != "guide_blocked" and cited != {
        item.source_item_id for item in context.material.documents
    }:
        raise ValueError("ready compilation does not account for every assigned document")


def project_guide_compilation_result_storage_bytes(result: ProjectGuideCompilationResult) -> int:
    """Measure the SQLAlchemy PostgreSQL JSON representation."""
    return len(json.dumps(result.model_dump(mode="json"), ensure_ascii=True, allow_nan=False).encode("utf-8"))


def invalid_compilation_failure_code(
    error: TypeError | ValueError,
) -> Literal["schema_invalid", "unsafe_text"]:
    """Classify only a proven unsafe-text validation without exposing the rejected value."""
    if isinstance(error, ValidationError):
        for item in error.errors(include_url=False, include_input=False):
            context = item.get("ctx") or {}
            cause = context.get("error")
            if isinstance(cause, ValueError) and str(cause) == "model-produced text is unsafe":
                return "unsafe_text"
    if str(error) == "model-produced text is unsafe":
        return "unsafe_text"
    return "schema_invalid"


class ProjectAgentRuntimeError(ExternalServiceAdapterError):
    """Raised when a project-agent runtime cannot complete a trusted operation."""

    def __init__(self, message: str) -> None:
        """Expose only a caller-supplied stable error, never provider exception text."""
        self.identity = None
        Exception.__init__(self, message)


class ProjectAgentRuntimeConfigurationError(
    ProjectAgentRuntimeError, ExternalServiceConfigurationError
):
    """Raised when a configured project-agent runtime is unavailable or incomplete."""


class ProjectGuideCompilationInvalidOutputError(ProjectAgentRuntimeError):
    """A returned compilation output was known to be invalid and safe to terminalize."""

    def __init__(self, failure_code: Literal["schema_invalid", "unsafe_text"]) -> None:
        self.failure_code = failure_code
        super().__init__("Project guide compilation returned invalid structured output")


class ProjectGuideAgentRuntime(ExternalServiceAdapter, Protocol):
    """Port implemented by project guide setup agent runtimes."""

    def admit_execution(self) -> None:
        """Acquire provider availability admission before the durable execution fence."""
        ...

    async def aclose(self) -> None:
        """Release runtime admission even if dispatch loses before execution."""
        ...

    async def compile_project_guide(
        self,
        context: ProjectGuideCompilationContext,
        capabilities: GuideRuntimeCapabilities,
    ) -> ProjectGuideCompilationResult:
        """Compile one complete untrusted project-guide proposal."""
