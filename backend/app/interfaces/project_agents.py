"""Project guide analysis agent contracts."""

from __future__ import annotations

import json
import math
import re
from enum import StrEnum
from typing import Annotated, Literal, Protocol
from uuid import UUID

from app.modules.checkers.api.artifact_paths import (
    is_canonical_relative_path, is_canonical_relative_pattern,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from app.modules.projects.api.task_examples import ProjectGuideTaskExamples
from app.modules.checkers.api import PostSubmitCatalogue, PostSubmitDefinition
from app.modules.checkers.api.pre_submit_catalogue import (
    PreSubmissionCapabilityDefinition,
    PreSubmissionCapabilityProjection,
)
from app.interfaces.external_services import (
    ExternalServiceAdapter,
    ExternalServiceAdapterError,
    ExternalServiceConfigurationError,
)
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.modules.projects.api.guide_documents import GuideRuntimeCleanupCustody, GuideDocumentManifest, GuideRuntimeCapabilities


MAXIMUM_PROJECT_GUIDE_COMPILATION_PROMPT_BYTES = 1_000_000
MAXIMUM_COMPILATION_FINDINGS = 100
MAXIMUM_COMPILATION_REQUIREMENTS = 200
MAXIMUM_COMPILATION_BINDINGS = MAXIMUM_COMPILATION_REQUIREMENTS
MAXIMUM_COMPILATION_SUGGESTIONS = MAXIMUM_COMPILATION_REQUIREMENTS
MAXIMUM_COMPILATION_RESULT_STORAGE_BYTES = 4_194_304
MAXIMUM_COMPILATION_NOTES = 20
MAXIMUM_EVIDENCE_REFS = 20
PROJECT_GUIDE_COMPILATION_AGENT_IDENTITY = "project-guide-compilation-agent-v1"
PROJECT_GUIDE_COMPILATION_AGENT_NAME = "ProjectGuideCompilationAgent"
PROJECT_GUIDE_COMPILATION_AGENT_VERSION = "v1"
PROJECT_GUIDE_COMPILATION_INSTRUCTION_VERSION = "v1"
PROJECT_GUIDE_COMPILATION_SCHEMA_VERSION = "project_guide_compilation_result.v1"

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
        "Describe shell instructions and module loading without literal command tokens."
    ),
}
ModelProse = Annotated[str, Field(json_schema_extra=_MODEL_PROSE_SCHEMA)]


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


class RequirementDisposition(StrEnum):
    """Closed trusted classifications for one atomic guide requirement."""

    PLATFORM_COVERED = "platform_covered"
    SUPPORTED_PRE_SUBMIT = "supported_pre_submit"
    PRE_SUBMIT_CAPABILITY_GAP = "pre_submit_capability_gap"
    SUPPORTED_POST_SUBMIT = "supported_post_submit"
    POST_SUBMIT_CAPABILITY_GAP = "post_submit_capability_gap"
    HUMAN_REVIEW = "human_review"
    PROJECT_LIFECYCLE_POLICY = "project_lifecycle_policy"
    GUIDE_BLOCKER = "guide_blocker"
    INFORMATIONAL = "informational"


class GuideEvidenceRef(BaseModel):
    """Untrusted page/section attribution bound to an exact original document version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_item_id: UUID
    document_version_id: UUID
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    start_page: StrictInt | None = Field(default=None, ge=1, le=100_000)
    end_page: StrictInt | None = Field(default=None, ge=1, le=100_000)
    section: str | None = Field(default=None, max_length=200, description=(
        "Optional plain-prose section label. Paraphrase headings; do not copy URLs, "
        "paths, slash-separated phrases, credentials or executable command tokens."
    ))

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


CapabilityScalar = Annotated[
    StrictStr | StrictInt | StrictFloat | StrictBool,
    Field(union_mode="left_to_right"),
]


class CapabilityParameter(BaseModel):
    """Closed flat capability configuration supplied for trusted validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern})
    value: CapabilityScalar | Annotated[tuple[CapabilityScalar, ...], Field(min_length=1, max_length=50)]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require a canonical catalogue-owned parameter name."""
        return _validated_identifier(value)

    @field_validator("value")
    @classmethod
    def validate_value(
        cls, value: CapabilityScalar | tuple[CapabilityScalar, ...]
    ) -> CapabilityScalar | tuple[CapabilityScalar, ...]:
        """Reject nested, non-finite, executable, or unbounded parameter values."""
        values = value if isinstance(value, tuple) else (value,)
        if not values or len(values) > 50:
            raise ValueError("capability parameter value is invalid")
        for item in values:
            if type(item) not in {str, int, float, bool}:
                raise ValueError("capability parameter scalar is invalid")
            if isinstance(item, str):
                _validated_safe_model_text(item)
            elif isinstance(item, (int, float)):
                if not math.isfinite(item) or abs(item) > 10**12:
                    raise ValueError("capability parameter number is out of range")
        return value


class _CapabilityBindingIdentity(BaseModel):
    """One stage-bound proposal against canonical capability truth."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_id: str = Field(json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern})
    capability_id: str = Field(json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern})
    capability_version: str = Field(json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern})
    stage: CompilationStage

    @field_validator("requirement_id", "capability_id", "capability_version")
    @classmethod
    def validate_identifiers(cls, value: str) -> str:
        """Require canonical requirement and capability identity fields."""
        return _validated_identifier(value)

class PreSubmissionBindingProposal(_CapabilityBindingIdentity):
    """Reference intake capability; its settings live only in the artifact policy."""


class PostSubmissionBindingProposal(_CapabilityBindingIdentity):
    """Reference work evaluation capability with its own typed configuration."""

    parameters: tuple[CapabilityParameter, ...] = Field(default=(), max_length=50)

    @model_validator(mode="after")
    def validate_parameter_names(self) -> PostSubmissionBindingProposal:
        """Reject duplicate parameter names within one binding."""
        names = [parameter.name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("capability parameters must be unique")
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


class PlatformCoverageRef(BaseModel):
    """Exact non-selectable phase-owner capability covering a requirement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: str = Field(json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern})
    capability_version: str = Field(json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern})
    stage: CompilationStage

    _capability_identity = field_validator("capability_id", "capability_version")(
        _validated_identifier
    )


class AtomicGuideRequirement(BaseModel):
    """One evidence-linked guide requirement with one disposition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_id: str = Field(json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern})
    statement: ModelProse
    disposition: RequirementDisposition = Field(description=(
        "Use human_review for work assigned to an authorized human reviewer. "
        "Use a capability gap only for required unsupported automated evaluation. "
        "Any guide_blocker, pre_submit_capability_gap or post_submit_capability_gap "
        "requires guide_blocked and no artifact policy. Exact supported binding "
        "proposals may remain as catalogue-match evidence without being projected."
    ))
    platform_coverage: PlatformCoverageRef | None = None
    evidence_refs: tuple[GuideEvidenceRef, ...] = Field(
        default=(), max_length=MAXIMUM_EVIDENCE_REFS
    )

    _requirement_id = field_validator("requirement_id")(_validated_identifier)
    _statement = field_validator("statement")(_validated_safe_model_text)


class SubmissionArtifactPolicyProposal(BaseModel):
    """Closed submission artifact policy proposed by compilation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    packaging: Literal["zip"] = "zip"
    maximum_file_size_bytes: StrictInt = Field(gt=0, le=10 * 1024 * 1024 * 1024)
    maximum_package_size_bytes: StrictInt = Field(gt=0, le=10 * 1024 * 1024 * 1024)
    allowed_storage_schemes: tuple[Literal["artifact"], ...] = ("artifact",)
    required_artifacts: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...] = Field(
        default=(), max_length=100,
        description="Canonical relative POSIX paths inside the submitted ZIP, such as outputs/answer.md. No traversal, storage references or secret files.",
    )
    forbidden_artifacts: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...] = Field(
        default=(), max_length=100,
        description="Relative artifact prohibition patterns, such as secret* or outputs/*.tmp; these are machine fields, not prose.",
    )
    required_evidence: tuple[ModelProse, ...] = Field(default=(), max_length=100)
    attestation_terms: tuple[ModelProse, ...] = Field(default=(), max_length=50)

    @field_validator("required_artifacts")
    @classmethod
    def validate_required_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Artifact paths are machine fields, not display prose."""
        if len(values) != len(set(values)) or not all(is_canonical_relative_path(value) for value in values):
            raise ValueError("artifact policy paths must be unique canonical relative paths")
        return values

    @field_validator("forbidden_artifacts")
    @classmethod
    def validate_forbidden_patterns(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Express prohibition patterns without treating their secret names as requests."""
        if len(values) != len(set(values)) or not all(is_canonical_relative_pattern(value) for value in values):
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
        if self.maximum_file_size_bytes > self.maximum_package_size_bytes:
            raise ValueError("file limit exceeds package limit")
        if set(self.required_artifacts).intersection(self.forbidden_artifacts):
            raise ValueError("artifact policy requirements conflict")
        return self


class CapabilitySuggestion(BaseModel):
    """Non-executable engineering suggestion for a capability gap."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_id: str = Field(json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern})
    stage: CompilationStage
    title: ModelProse
    rationale: ModelProse
    evidence_refs: tuple[GuideEvidenceRef, ...] = Field(
        min_length=1, max_length=MAXIMUM_EVIDENCE_REFS
    )

    _requirement_id = field_validator("requirement_id")(_validated_identifier)
    _title = field_validator("title")(_validated_safe_model_text)
    _rationale = field_validator("rationale")(_validated_safe_model_text)


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
    agent_version: str = Field(max_length=100, json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern})
    runtime_configuration: ProjectGuideRuntimeConfiguration
    pre_submission_capabilities: PreSubmissionCapabilityProjection
    post_submission_capabilities: PostSubmitCatalogue
    task_examples: ProjectGuideTaskExamples
    correction_feedback: ProjectGuideCorrectionFeedback | None = None

    @model_validator(mode="after")
    def validate_instruction_configuration(self) -> ProjectGuideCompilationContext:
        """Bind the semantic instruction version to its exact execution snapshot."""
        configuration = self.runtime_configuration
        if (self.material.setup_run_id != self.setup_run_id
                or self.material.setup_generation != self.setup_generation
                or len(self.material.documents) > configuration.maximum_documents
                or any(item.byte_count > configuration.maximum_document_bytes for item in self.material.documents)
                or sum(item.byte_count for item in self.material.documents) > configuration.maximum_total_document_bytes):
            raise ValueError("compilation document manifest exceeds its execution boundary")
        if self.instruction_version != self.runtime_configuration.instruction_version:
            raise ValueError("compilation instruction configuration mismatch")
        return self


def canonical_project_guide_compilation_context_bytes(
    context: ProjectGuideCompilationContext,
) -> bytes:
    """Serialize one context without double-encoding canonical guide JSON."""
    body = context.model_dump(mode="json")
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
    """Serialize only source and capability input, excluding trusted runtime settings."""
    body = json.loads(canonical_project_guide_compilation_context_bytes(context))
    del body["runtime_configuration"]
    body["material"] = context.material.agent_projection()
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


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
    pre_submit_bindings: tuple[PreSubmissionBindingProposal, ...] = Field(
        default=(), max_length=MAXIMUM_COMPILATION_BINDINGS
    )
    post_submit_bindings: tuple[PostSubmissionBindingProposal, ...] = Field(
        default=(), max_length=MAXIMUM_COMPILATION_BINDINGS
    )
    capability_suggestions: tuple[CapabilitySuggestion, ...] = Field(
        default=(), max_length=MAXIMUM_COMPILATION_SUGGESTIONS
    )
    setup_notes: tuple[ModelProse, ...] = Field(default=(), max_length=MAXIMUM_COMPILATION_NOTES)
    agent_name: Literal["ProjectGuideCompilationAgent"] = "ProjectGuideCompilationAgent"
    agent_version: str = Field(max_length=100, json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern})
    schema_version: Literal["project_guide_compilation_result.v1"] = (
        "project_guide_compilation_result.v1"
    )

    @field_validator("setup_notes")
    @classmethod
    def validate_notes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject unsafe setup notes before trusted validation."""
        return tuple(_validated_safe_model_text(value) for value in values)

    _agent_version = field_validator("agent_version")(_validated_identifier)


_COMPLETE_COMPILATION_RESULT_FIELDS = frozenset(ProjectGuideCompilationResult.model_fields)


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
    """Fail closed when an untrusted result diverges from canonical capability truth."""
    if project_guide_compilation_result_storage_bytes(result) > MAXIMUM_COMPILATION_RESULT_STORAGE_BYTES:
        raise ValueError("compilation result exceeds storage byte limit")
    if not context.pre_submission_capabilities.available:
        raise ValueError("pre-submit capability projection is unavailable")
    requirements = {item.requirement_id: item for item in result.requirements}
    if len(requirements) != len(result.requirements):
        raise ValueError("compilation requirements must be unique")
    _validate_status_consistency(result)
    _validate_capability_suggestions(result.capability_suggestions, requirements)
    if result.status == "guide_blocked":
        if result.submission_artifact_policy is not None:
            raise ValueError("blocked guide cannot publish policy proposals")
    elif result.submission_artifact_policy is None:
        raise ValueError("draft-ready compilation requires artifact policy")

    pre_definitions = {
        definition.stable_id: definition
        for definition in context.pre_submission_capabilities.definitions
    }
    post_capabilities = context.post_submission_capabilities
    post_capabilities = PostSubmitCatalogue.model_validate(post_capabilities)
    if any(
        item.platform_default and item.state != "enabled" for item in post_capabilities.definitions
    ):
        raise ValueError("post-submit capability projection is unavailable")
    post_definitions = {
        definition.capability_id: definition for definition in post_capabilities.definitions
    }
    _validate_platform_coverage(result.requirements, pre_definitions, post_definitions)
    _validate_evidence_lineage(context, result)
    pre_bound_requirements = _validate_bindings(
        result.pre_submit_bindings,
        requirements,
        pre_definitions,
        "pre_submit",
    )
    post_bound_requirements = _validate_bindings(
        result.post_submit_bindings, requirements, post_definitions, "post_submit"
    )
    expected_pre = {
        item.requirement_id
        for item in result.requirements
        if item.disposition is RequirementDisposition.SUPPORTED_PRE_SUBMIT
    }
    expected_post = {
        item.requirement_id
        for item in result.requirements
        if item.disposition is RequirementDisposition.SUPPORTED_POST_SUBMIT
    }
    if pre_bound_requirements != expected_pre or post_bound_requirements != expected_post:
        raise ValueError("supported compilation requirements must have one binding")


def project_guide_compilation_result_storage_bytes(result: ProjectGuideCompilationResult) -> int:
    """Measure the default SQLAlchemy PostgreSQL JSON representation, not hash encoding."""
    return len(json.dumps(result.model_dump(mode="json"), ensure_ascii=True,
                          allow_nan=False).encode("utf-8"))


def _validate_capability_suggestions(
    suggestions: tuple[CapabilitySuggestion, ...],
    requirements: dict[str, AtomicGuideRequirement],
) -> None:
    """Require one evidence-backed engineering handoff for each exact staged gap."""
    stages = {
        RequirementDisposition.PRE_SUBMIT_CAPABILITY_GAP: CompilationStage.PRE_SUBMIT,
        RequirementDisposition.POST_SUBMIT_CAPABILITY_GAP: CompilationStage.POST_SUBMIT,
    }
    gaps = {key: stages[item.disposition] for key, item in requirements.items()
            if item.disposition in stages}
    seen: set[str] = set()
    for suggestion in suggestions:
        if (suggestion.requirement_id in seen
                or gaps.get(suggestion.requirement_id) != suggestion.stage
                or not suggestion.evidence_refs):
            raise ValueError("compilation capability suggestion is invalid")
        seen.add(suggestion.requirement_id)
    if seen != set(gaps):
        raise ValueError("capability gaps must have exactly one suggestion")


def _validate_status_consistency(result: ProjectGuideCompilationResult) -> None:
    """Require ready and blocked status to match findings and dispositions."""
    has_blocker = any(finding.severity == "blocking_gap" for finding in result.findings) or any(
        requirement.disposition
        in {
            RequirementDisposition.GUIDE_BLOCKER,
            RequirementDisposition.PRE_SUBMIT_CAPABILITY_GAP,
            RequirementDisposition.POST_SUBMIT_CAPABILITY_GAP,
        }
        for requirement in result.requirements
    )
    has_warning = any(finding.severity == "warning" for finding in result.findings)
    if result.status == "guide_blocked" and not has_blocker:
        raise ValueError("blocked compilation requires blocking evidence")
    if result.status != "guide_blocked" and has_blocker:
        raise ValueError("ready compilation cannot contain blocking evidence")
    if result.status == "draft_ready" and has_warning:
        raise ValueError("draft-ready compilation cannot contain warnings")
    if result.status == "draft_ready_with_warnings" and not has_warning:
        raise ValueError("warning-ready compilation requires a warning")


def _validate_platform_coverage(
    requirements: tuple[AtomicGuideRequirement, ...],
    pre_definitions: dict[str, PreSubmissionCapabilityDefinition],
    post_definitions: dict[str, PostSubmitDefinition],
) -> None:
    """Resolve platform coverage only against eligible phase-owner truth."""
    for requirement in requirements:
        coverage = requirement.platform_coverage
        if requirement.disposition is not RequirementDisposition.PLATFORM_COVERED:
            if coverage is not None:
                raise ValueError("non-platform requirement cannot claim platform coverage")
            continue
        if coverage is None:
            raise ValueError("platform-covered requirement requires canonical proof")
        if coverage.stage is CompilationStage.PRE_SUBMIT:
            definition = pre_definitions.get(coverage.capability_id)
            valid = (
                definition is not None
                and definition.version == coverage.capability_version
                and definition.dispatch_kind == "platform_capability"
                and definition.state == "enabled"
                and definition.classification != "advisory"
                and not definition.selectable
            )
        else:
            post_definition = post_definitions.get(coverage.capability_id)
            valid = (
                post_definition is not None
                and post_definition.capability_version == coverage.capability_version
                and post_definition.state == "enabled"
                and post_definition.platform_default
                and not post_definition.selectable
            )
        if not valid:
            raise ValueError("platform coverage does not resolve to canonical truth")


def _validate_evidence_lineage(
    context: ProjectGuideCompilationContext,
    result: ProjectGuideCompilationResult,
) -> None:
    """Resolve every model evidence reference to immutable source lineage."""
    source_lineage = {
        (
            str(item.source_item_id),
            str(item.ingest_id),
            item.sha256,
        )
        for item in context.material.documents
    }
    evidence_refs = (
        *(ref for finding in result.findings for ref in finding.evidence_refs),
        *(ref for requirement in result.requirements for ref in requirement.evidence_refs),
        *(ref for suggestion in result.capability_suggestions for ref in suggestion.evidence_refs),
    )
    for evidence in evidence_refs:
        lineage = (
            str(evidence.source_item_id),
            str(evidence.document_version_id),
            evidence.sha256,
        )
        if lineage not in source_lineage:
            raise ValueError("compilation evidence does not resolve to source lineage")


def _validate_bindings(
    bindings: tuple[PreSubmissionBindingProposal | PostSubmissionBindingProposal, ...],
    requirements: dict[str, AtomicGuideRequirement],
    definitions: dict[str, PreSubmissionCapabilityDefinition | PostSubmitDefinition],
    expected_stage: Literal["pre_submit", "post_submit"],
) -> set[str]:
    """Validate exact stage, version, selectability, and parameter ownership."""
    seen_requirements: set[str] = set()
    expected_disposition = (
        RequirementDisposition.SUPPORTED_PRE_SUBMIT
        if expected_stage == "pre_submit"
        else RequirementDisposition.SUPPORTED_POST_SUBMIT
    )
    for binding in bindings:
        requirement = requirements.get(binding.requirement_id)
        definition = definitions.get(binding.capability_id)
        if (
            requirement is None
            or requirement.disposition is not expected_disposition
            or binding.requirement_id in seen_requirements
            or definition is None
            or not definition.selectable
            or binding.stage.value != expected_stage
        ):
            raise ValueError("compilation capability binding is invalid")
        version = (
            definition.version
            if isinstance(definition, PreSubmissionCapabilityDefinition)
            else definition.capability_version
        )
        if binding.capability_version != version:
            raise ValueError("compilation capability version is stale")
        if isinstance(definition, PostSubmitDefinition):
            if not isinstance(binding, PostSubmissionBindingProposal):
                raise ValueError("compilation capability binding is invalid")
            definition.validate_configuration(
                {item.name: item.value for item in binding.parameters}
            )
        seen_requirements.add(binding.requirement_id)
    return seen_requirements



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

    async def cleanup_resources(self, custody: GuideRuntimeCleanupCustody) -> bool:
        """Reconcile exact owned resources without admitting or executing inference."""
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
