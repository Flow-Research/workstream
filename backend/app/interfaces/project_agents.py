"""Project guide analysis agent contracts."""

from __future__ import annotations

import json
import math
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
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from app.core.hashing import canonical_json_hash
from app.modules.projects.api.task_examples import ProjectGuideTaskExamples
from app.modules.checkers.api.external import (
    EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS,
    ExternalCheckerCapabilityDefinition,
    ExternalCheckerCapabilityProjection,
)
from app.modules.checkers.api.external_policy import (
    MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS,
    MAXIMUM_SELECTED_PRE_EXECUTION_BUDGET_MS,
    SELECTED_POST_MATERIALIZATION_BUDGET_MS,
    WORKSTREAM_DEFAULT_EXECUTION_BUDGET_MS,
)
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


GENERATED_REQUIREMENT_DISPOSITIONS = frozenset({
    RequirementDisposition.PLATFORM_COVERED,
    RequirementDisposition.SUPPORTED_PRE_SUBMIT,
    RequirementDisposition.PRE_SUBMIT_CAPABILITY_GAP,
    RequirementDisposition.SUPPORTED_POST_SUBMIT,
    RequirementDisposition.POST_SUBMIT_CAPABILITY_GAP,
    RequirementDisposition.GUIDE_BLOCKER,
})


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


CapabilityScalar = Annotated[
    StrictStr | StrictInt | StrictFloat | StrictBool,
    Field(union_mode="left_to_right"),
]


class CapabilityParameter(BaseModel):
    """Closed flat capability configuration supplied for trusted validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern})
    value: (
        CapabilityScalar
        | Annotated[tuple[CapabilityScalar, ...], Field(min_length=1, max_length=50)]
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require a canonical registered-checker parameter name."""
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
                if "/" in item or "\\" in item:
                    if not is_canonical_relative_pattern(item):
                        raise ValueError("capability parameter path is invalid")
                    # Machine paths belong to the image configuration. Keep
                    # command/credential checks without treating '/' as prose.
                    _validated_safe_model_text(item.replace("/", " "))
                else:
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
    """Reference an external intake image with approved typed configuration."""

    parameters: tuple[CapabilityParameter, ...] = Field(
        default=(),
        max_length=50,
        exclude_if=lambda value: not value,
    )

    @model_validator(mode="after")
    def validate_parameter_names(self) -> PreSubmissionBindingProposal:
        """Reject duplicate names without changing retained empty bindings."""
        names = [parameter.name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("capability parameters must be unique")
        return self


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


CheckEvaluationMethod = Literal["static_inspection", "isolated_execution", "model_evaluation"]
CheckExecutionMode = Literal["bounded_pre_submit", "background"]
CheckInputKind = Literal[
    "package",
    "manifest",
    "request_metadata",
    "relative_file",
    "relative_directory",
    "task_context",
    "guide_context",
    "prepared_material",
]
CheckerDependencyKind = Literal[
    "checker_tool",
    "isolated_execution",
    "nested_sandbox",
    "task_context",
    "guide_context",
    "model_service",
    "execution_capacity",
    "prepared_material",
]
DependencyProvisioning = Literal[
    "current_runner", "checker_implementation", "model_proxy", "trial_proxy", "runtime_gap"
]
InfrastructureFailureCode = Literal[
    "capacity_exceeded",
    "deadline_exceeded",
    "material_unavailable",
    "implementation_unavailable",
    "invalid_output",
]
_INFRASTRUCTURE_FAILURE_CODES = frozenset(
    {
        "capacity_exceeded",
        "deadline_exceeded",
        "material_unavailable",
        "implementation_unavailable",
        "invalid_output",
    }
)


class CheckInput(BaseModel):
    """One exact material or context input needed by a proposed check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_id: PolicyIdentifier
    kind: CheckInputKind
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
    _purpose = field_validator("purpose")(_validated_safe_model_text)

    @model_validator(mode="after")
    def validate_relative_path(self) -> CheckInput:
        """Require a safe path only for an exact file or directory input."""
        path_required = self.kind in {"relative_file", "relative_directory"}
        if path_required != (self.relative_path is not None):
            raise ValueError("check input relative path does not match its kind")
        if self.relative_path is not None and not is_canonical_relative_path(self.relative_path):
            raise ValueError("check input relative path is invalid")
        return self


class CheckFailureFinding(BaseModel):
    """One stable work finding an implementation must return when observed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: PolicyIdentifier
    level: Literal["warning", "error", "coverage_incomplete"]
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


class CheckRuntimeDependency(BaseModel):
    """One implementation or runner dependency and its availability owner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dependency_id: PolicyIdentifier
    kind: CheckerDependencyKind
    provisioning: DependencyProvisioning
    purpose: ModelProse
    unavailable_code: InfrastructureFailureCode

    _dependency_id = field_validator("dependency_id")(_validated_identifier)
    _purpose = field_validator("purpose")(_validated_safe_model_text)

    @model_validator(mode="after")
    def validate_provisioning(self) -> CheckRuntimeDependency:
        """Describe current runner support without treating desired access as live."""
        expected = {
            "checker_tool": ("checker_implementation", "implementation_unavailable"),
            "isolated_execution": ("current_runner", "implementation_unavailable"),
            "nested_sandbox": ({"trial_proxy", "runtime_gap"}, "implementation_unavailable"),
            "task_context": ("runtime_gap", "material_unavailable"),
            "guide_context": ("runtime_gap", "material_unavailable"),
            "prepared_material": ({"trial_proxy", "runtime_gap"}, "material_unavailable"),
            # runtime_gap remains readable for immutable retained compilations. New
            # generation admission below requires the precise model_proxy owner.
            "model_service": (
                {"model_proxy", "runtime_gap"},
                "implementation_unavailable",
            ),
            "execution_capacity": ("runtime_gap", "capacity_exceeded"),
        }[self.kind]
        expected_provisioning, expected_code = expected
        if (
            self.provisioning
            not in (
                expected_provisioning
                if isinstance(expected_provisioning, set)
                else {expected_provisioning}
            )
            or self.unavailable_code != expected_code
        ):
            raise ValueError("check dependency availability is invalid")
        return self


class CheckInfrastructureFailure(BaseModel):
    """One non-work failure that must never become a failed work verdict."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: InfrastructureFailureCode
    condition: ModelProse

    _condition = field_validator("condition")(_validated_safe_model_text)


class CheckSpecification(BaseModel):
    """Bounded implementation and test handoff for one atomic requirement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evaluation_method: CheckEvaluationMethod = Field(
        description=(
            "isolated_execution requires a runtime dependency of kind isolated_execution; "
            "model_evaluation requires model_service and belongs to POST background work. "
            "Model review assesses content; proving runtime outcomes or built-environment "
            "properties requires isolated_execution with actual trials and observations."
        )
    )
    execution_mode: CheckExecutionMode
    maximum_duration_seconds: StrictInt = Field(
        ge=1,
        le=3600,
        description=(
            "Proposed engineering budget for one check execution, not a measured runtime "
            "promise. PRE checks must be at most 60 seconds; POST checks may use up to "
            "3600 seconds in background execution."
        ),
    )
    stage_rationale: ModelProse
    inputs: tuple[CheckInput, ...] = Field(
        min_length=1,
        max_length=20,
        description=(
            "All materials needed to observe every pass condition and negative case. "
            "Every task_context, guide_context or prepared_material runtime dependency "
            "requires an input of that same kind, and vice versa."
        ),
    )
    check_steps: tuple[ModelProse, ...] = Field(
        min_length=1,
        max_length=20,
        description=(
            "Implementable steps on the declared inputs. Static inspection needs explicit "
            "syntax or deterministic predicates, including source-defined field identifiers, "
            "types, values, ranges and exceptions rather than references to documented rules; "
            "qualitative free-form comparison needs "
            "model evaluation in POST. Never invent a document grammar absent from the guide."
        ),
    )
    pass_conditions: tuple[ModelProse, ...] = Field(
        min_length=1,
        max_length=20,
        description=(
            "Observable outcomes proved by the declared method and inputs. A model's "
            "review of claimed execution is not proof of actual execution; a static "
            "predicate cannot interpret free-form explanations. Require mandatory content "
            "to exist before judging its accuracy; absent required claims cannot pass vacuously."
        ),
    )
    failure_findings: tuple[CheckFailureFinding, ...] = Field(min_length=1, max_length=20)
    positive_tests: tuple[ModelProse, ...] = Field(min_length=1, max_length=10)
    negative_tests: tuple[CheckNegativeTest, ...] = Field(min_length=1, max_length=10)
    runtime_dependencies: tuple[CheckRuntimeDependency, ...] = Field(
        max_length=10,
        description=(
            "Declare the evaluation method's required dependency and any task_context, "
            "guide_context or prepared_material input dependency. Each of those three kinds "
            "must occur in both inputs and runtime_dependencies, never just one. "
            "Each unavailable_code must appear in "
            "infrastructure_failures."
        ),
    )
    infrastructure_failures: tuple[CheckInfrastructureFailure, ...] = Field(
        min_length=1, max_length=5
    )

    _stage_rationale = field_validator("stage_rationale")(_validated_safe_model_text)

    @field_validator("check_steps", "pass_conditions", "positive_tests")
    @classmethod
    def validate_prose_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Apply safe-prose validation to every collection member."""
        return tuple(_validated_safe_model_text(value) for value in values)

    @model_validator(mode="after")
    def validate_linkage(self) -> CheckSpecification:
        """Reject duplicate handoff identities and contradictory expected results."""
        for values, message in (
            ([item.input_id for item in self.inputs], "check inputs must be unique"),
            (
                [item.code for item in self.failure_findings],
                "check failure findings must be unique",
            ),
            (
                [item.name for item in self.negative_tests],
                "check negative tests must be unique",
            ),
            (
                [item.dependency_id for item in self.runtime_dependencies],
                "check runtime dependencies must be unique",
            ),
            (
                [item.code for item in self.infrastructure_failures],
                "check infrastructure failures must be unique",
            ),
        ):
            if len(values) != len(set(values)):
                raise ValueError(message)

        findings = {item.code: item for item in self.failure_findings}
        if set(findings).intersection(_INFRASTRUCTURE_FAILURE_CODES):
            raise ValueError("work and infrastructure finding codes must be distinct")
        for test in self.negative_tests:
            referenced = [findings.get(code) for code in test.expected_finding_codes]
            if any(item is None for item in referenced):
                raise ValueError("negative test references an unknown finding")
            has_error = any(item.level == "error" for item in referenced if item is not None)
            if (test.expected_verdict == "failed") != has_error:
                raise ValueError("negative test verdict disagrees with its findings")

        dependency_kinds = {item.kind for item in self.runtime_dependencies}
        if self.evaluation_method == "model_evaluation" and "model_service" not in dependency_kinds:
            raise ValueError("model evaluation requires a model service dependency")
        if (
            self.evaluation_method == "isolated_execution"
            and "isolated_execution" not in dependency_kinds
        ):
            raise ValueError("isolated evaluation requires an execution dependency")
        for item in self.inputs:
            if (
                item.kind in {"task_context", "guide_context", "prepared_material"}
                and item.kind not in dependency_kinds
            ):
                raise ValueError("check context input requires a runtime dependency")
        material_dependencies = dependency_kinds.intersection(
            {"task_context", "guide_context", "prepared_material"}
        )
        if material_dependencies - {item.kind for item in self.inputs}:
            raise ValueError("check material dependency requires a declared input")
        available_failures = {item.code for item in self.infrastructure_failures}
        if any(
            dependency.unavailable_code not in available_failures
            for dependency in self.runtime_dependencies
        ):
            raise ValueError("check dependency failure is not specified")
        return self


class AtomicGuideRequirement(BaseModel):
    """One evidence-linked guide requirement with one disposition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_id: str = Field(json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern})
    statement: ModelProse
    disposition: RequirementDisposition = Field(
        description=(
            "Infer checkable requirements from observable outcomes even when the guide "
            "does not call them automated. Use supported_pre_submit for static or other "
            "bounded checks that reliably complete within 60 seconds, and "
            "supported_post_submit for longer background evaluation. Use the matching "
            "capability gap when the required implementation is unavailable; a gap keeps "
            "the proposal warning-ready but blocks activation. Use human_review only for "
            "retained historical evidence only. Newly generated requirements are limited to "
            "PRE and POST checks, exact platform coverage and check-definition blockers. "
            "Do not propose human-review or project-management policy. Revision explanation, rerun evidence and objective "
            "preservation remain separately checkable work requirements, not lifecycle. "
            "A guide_blocker requires guide_blocked and no "
            "artifact policy."
        )
    )
    platform_coverage: PlatformCoverageRef | None = None
    classification_rationale: ModelProse | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description=(
            "Explain the selected ownership and, for a staged check, why its work and "
            "runtime fit PRE or POST."
        ),
    )
    check_specification: CheckSpecification | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description=(
            "Typed implementation and test handoff inferred from the required outcome for "
            "every supported or capability-gap PRE or POST requirement."
        ),
    )
    evidence_refs: tuple[GuideEvidenceRef, ...] = Field(
        default=(), max_length=MAXIMUM_EVIDENCE_REFS
    )

    _requirement_id = field_validator("requirement_id")(_validated_identifier)
    _statement = field_validator("statement")(_validated_safe_model_text)
    _classification_rationale = field_validator("classification_rationale")(
        lambda value: _validated_safe_model_text(value) if value is not None else None
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
    agent_version: str = Field(
        max_length=100, json_schema_extra={"pattern": _SAFE_IDENTIFIER.pattern}
    )
    schema_version: Literal["project_guide_compilation_result.v1"] = (
        "project_guide_compilation_result.v1"
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
    checker_capabilities: ExternalCheckerCapabilityProjection
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
        if feedback is not None and canonical_json_hash(
            predecessor.model_dump(mode="json")
        ) != feedback.predecessor_result_hash:
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
    """Serialize only source and capability input, excluding trusted runtime settings."""
    body = json.loads(canonical_project_guide_compilation_context_bytes(context))
    del body["runtime_configuration"]
    body["material"] = context.material.agent_projection()
    if context.correction_predecessor is not None:
        body["correction_predecessor"] = context.correction_predecessor.model_dump(mode="json")
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


_COMPLETE_COMPILATION_RESULT_FIELDS = frozenset(ProjectGuideCompilationResult.model_fields) - {"setup_notes"}


def require_complete_project_guide_compilation_result(
    result: ProjectGuideCompilationResult,
) -> None:
    """Reject provider output that omitted any member of the strict envelope."""
    if _COMPLETE_COMPILATION_RESULT_FIELDS - result.model_fields_set:
        raise ValueError("compilation result envelope is incomplete")


def _require_trial_dependencies(specification: CheckSpecification, stage: CompilationStage) -> None:
    """Keep the nested runtime tool distinct from ordinary checker isolation."""
    dependencies = specification.runtime_dependencies
    nested = any(item.kind == "nested_sandbox" for item in dependencies)
    if any(item.kind == "nested_sandbox" and item.provisioning != "trial_proxy"
           for item in dependencies):
        raise ValueError("nested execution requires trial proxy provisioning")
    if any(item.provisioning == "trial_proxy" for item in dependencies):
        if stage is not CompilationStage.POST_SUBMIT:
            raise ValueError("trial execution requires post-submit background work")
        if not nested:
            raise ValueError("trial material requires an isolated trial dependency")


def require_complete_generated_specifications(
    context: ProjectGuideCompilationContext,
    result: ProjectGuideCompilationResult,
) -> None:
    """Require an actionable typed handoff on newly generated requirements."""
    if (context.runtime_configuration.uses_inference
            and "setup_notes" in result.model_fields_set):
        raise ValueError("generated setup notes are outside checker specification scope")

    specification_stages = {
        RequirementDisposition.SUPPORTED_PRE_SUBMIT: CompilationStage.PRE_SUBMIT,
        RequirementDisposition.PRE_SUBMIT_CAPABILITY_GAP: CompilationStage.PRE_SUBMIT,
        RequirementDisposition.SUPPORTED_POST_SUBMIT: CompilationStage.POST_SUBMIT,
        RequirementDisposition.POST_SUBMIT_CAPABILITY_GAP: CompilationStage.POST_SUBMIT,
    }
    supported = {
        RequirementDisposition.SUPPORTED_PRE_SUBMIT,
        RequirementDisposition.SUPPORTED_POST_SUBMIT,
    }
    for requirement in result.requirements:
        if (context.runtime_configuration.uses_inference
                and requirement.disposition not in GENERATED_REQUIREMENT_DISPOSITIONS):
            raise ValueError("generated requirement is outside PRE and POST checker scope")
        if requirement.classification_rationale is None:
            raise ValueError("generated requirement lacks a classification rationale")
        if not requirement.evidence_refs:
            raise ValueError("generated requirement lacks source evidence")
        expected_stage = specification_stages.get(requirement.disposition)
        specification = requirement.check_specification
        if expected_stage is None:
            if specification is not None:
                raise ValueError("non-check requirement cannot include a check specification")
            continue
        if specification is None:
            raise ValueError("check requirement lacks a check specification")
        if expected_stage is CompilationStage.PRE_SUBMIT:
            if specification.evaluation_method == "model_evaluation" or any(
                dependency.kind == "model_service"
                for dependency in specification.runtime_dependencies
            ):
                raise ValueError("model service requires post-submit background work")
            if (
                specification.execution_mode != "bounded_pre_submit"
                or specification.maximum_duration_seconds > 60
            ):
                raise ValueError("pre-submit check specification is not bounded")
        elif specification.execution_mode != "background":
            raise ValueError("post-submit check specification is not background work")
        if requirement.disposition in supported and any(
            dependency.provisioning == "runtime_gap"
            for dependency in specification.runtime_dependencies
        ):
            raise ValueError("supported check depends on unavailable runtime support")
        if any(
            dependency.kind == "model_service"
            and dependency.provisioning != "model_proxy"
            for dependency in specification.runtime_dependencies
        ):
            raise ValueError("model service requires model proxy provisioning")
        _require_trial_dependencies(specification, expected_stage)

    definitions = {
        (definition.phase, definition.capability_id, definition.capability_version): definition
        for definition in context.checker_capabilities.definitions
    }
    requirements = {item.requirement_id: item for item in result.requirements}
    supported_deadlines: dict[str, int] = {}
    for binding in (*result.pre_submit_bindings, *result.post_submit_bindings):
        definition = definitions.get(
            (binding.stage.value, binding.capability_id, binding.capability_version)
        )
        requirement = requirements.get(binding.requirement_id)
        specification = requirement.check_specification if requirement is not None else None
        if definition is None or definition.registry_entry is None or specification is None:
            continue
        deadline_ms = definition.registry_entry.resources.deadline_ms
        if binding.stage is CompilationStage.PRE_SUBMIT and deadline_ms > 60_000:
            raise ValueError("pre-submit checker deadline exceeds the bounded stage")
        if specification.maximum_duration_seconds * 1000 > deadline_ms:
            raise ValueError("check specification exceeds the checker deadline")
        supported_deadlines[binding.requirement_id] = deadline_ms

    for stage, fixed_budget, maximum_budget in (
        (
            CompilationStage.PRE_SUBMIT,
            WORKSTREAM_DEFAULT_EXECUTION_BUDGET_MS,
            MAXIMUM_SELECTED_PRE_EXECUTION_BUDGET_MS,
        ),
        (
            CompilationStage.POST_SUBMIT,
            SELECTED_POST_MATERIALIZATION_BUDGET_MS,
            MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS,
        ),
    ):
        staged_requirements = [
            item
            for item in result.requirements
            if specification_stages.get(item.disposition) is stage
        ]
        supported_budget = fixed_budget + sum(
            supported_deadlines[item.requirement_id] + EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS
            for item in staged_requirements
            if item.requirement_id in supported_deadlines
        )
        stage_name = stage.value.replace("_", "-")
        if supported_budget > maximum_budget:
            raise ValueError(f"supported {stage_name} checks exceed the aggregate execution budget")
        proposed_budget = fixed_budget + sum(
            max(
                item.check_specification.maximum_duration_seconds * 1000,
                supported_deadlines.get(item.requirement_id, 0),
            )
            + EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS
            for item in staged_requirements
        )
        has_capacity_gap = any(
            dependency.kind == "execution_capacity"
            for item in staged_requirements
            for dependency in item.check_specification.runtime_dependencies
        )
        if proposed_budget > maximum_budget and not has_capacity_gap:
            raise ValueError(f"proposed {stage_name} checks require an execution capacity gap")
        if proposed_budget <= maximum_budget and has_capacity_gap:
            raise ValueError(
                f"proposed {stage_name} checks do not require an execution capacity gap"
            )


def validate_project_guide_compilation_result(
    context: ProjectGuideCompilationContext,
    result: ProjectGuideCompilationResult,
) -> None:
    """Fail closed when an untrusted result diverges from canonical capability truth."""
    if (
        project_guide_compilation_result_storage_bytes(result)
        > MAXIMUM_COMPILATION_RESULT_STORAGE_BYTES
    ):
        raise ValueError("compilation result exceeds storage byte limit")
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

    capabilities = ExternalCheckerCapabilityProjection.model_validate(context.checker_capabilities)
    pre_definitions = {
        (definition.capability_id, definition.capability_version): definition
        for definition in capabilities.definitions
        if definition.phase == "pre_submit"
    }
    post_definitions = {
        (definition.capability_id, definition.capability_version): definition
        for definition in capabilities.definitions
        if definition.phase == "post_submit"
    }
    _validate_platform_coverage(result.requirements, pre_definitions, post_definitions)
    _validate_evidence_lineage(context, result)
    pre_bound_requirements = _validate_bindings(
        result.pre_submit_bindings,
        requirements,
        pre_definitions,
        "pre_submit",
    )
    post_bound_requirements = validate_post_submission_bindings(result, capabilities)
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


def require_ready_result_cites_every_document(
    context: ProjectGuideCompilationContext,
    result: ProjectGuideCompilationResult,
) -> None:
    """Require a ready result to cite every assigned original at least once."""
    cited = {
        ref.source_item_id
        for item in (*result.findings, *result.requirements, *result.capability_suggestions)
        for ref in item.evidence_refs
    }
    if result.status != "guide_blocked" and cited != {
        item.source_item_id for item in context.material.documents
    }:
        raise ValueError("ready compilation does not account for every assigned document")


def validate_post_submission_bindings(
    result: ProjectGuideCompilationResult,
    capabilities: ExternalCheckerCapabilityProjection,
) -> set[str]:
    """Validate POST bindings against the immutable external registry projection."""
    result = ProjectGuideCompilationResult.model_validate_json(result.model_dump_json())
    capabilities = ExternalCheckerCapabilityProjection.model_validate(capabilities)
    requirements = {item.requirement_id: item for item in result.requirements}
    if len(requirements) != len(result.requirements):
        raise ValueError("compilation requirements must be unique")
    _validate_status_consistency(result)
    bound = _validate_bindings(
        result.post_submit_bindings,
        requirements,
        {
            (item.capability_id, item.capability_version): item
            for item in capabilities.definitions
            if item.phase == "post_submit"
        },
        "post_submit",
    )
    if bound != {
        item.requirement_id
        for item in result.requirements
        if item.disposition is RequirementDisposition.SUPPORTED_POST_SUBMIT
    }:
        raise ValueError("supported compilation requirements must have one binding")
    return bound


def project_guide_compilation_result_storage_bytes(result: ProjectGuideCompilationResult) -> int:
    """Measure the default SQLAlchemy PostgreSQL JSON representation, not hash encoding."""
    return len(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=True, allow_nan=False).encode(
            "utf-8"
        )
    )


def _validate_capability_suggestions(
    suggestions: tuple[CapabilitySuggestion, ...],
    requirements: dict[str, AtomicGuideRequirement],
) -> None:
    """Require one evidence-backed engineering handoff for each exact staged gap."""
    stages = {
        RequirementDisposition.PRE_SUBMIT_CAPABILITY_GAP: CompilationStage.PRE_SUBMIT,
        RequirementDisposition.POST_SUBMIT_CAPABILITY_GAP: CompilationStage.POST_SUBMIT,
    }
    gaps = {
        key: stages[item.disposition]
        for key, item in requirements.items()
        if item.disposition in stages
    }
    seen: set[str] = set()
    for suggestion in suggestions:
        if (
            suggestion.requirement_id in seen
            or gaps.get(suggestion.requirement_id) != suggestion.stage
            or not suggestion.evidence_refs
        ):
            raise ValueError("compilation capability suggestion is invalid")
        seen.add(suggestion.requirement_id)
    if seen != set(gaps):
        raise ValueError("capability gaps must have exactly one suggestion")


def _validate_status_consistency(result: ProjectGuideCompilationResult) -> None:
    """Require ready and blocked status to match findings and dispositions."""
    has_blocker = any(finding.severity == "blocking_gap" for finding in result.findings) or any(
        requirement.disposition is RequirementDisposition.GUIDE_BLOCKER
        for requirement in result.requirements
    )
    has_warning = any(finding.severity == "warning" for finding in result.findings) or bool(
        result.capability_suggestions
    )
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
    pre_definitions: dict[tuple[str, str], ExternalCheckerCapabilityDefinition],
    post_definitions: dict[tuple[str, str], ExternalCheckerCapabilityDefinition],
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
            definition = pre_definitions.get((coverage.capability_id, coverage.capability_version))
            valid = (
                definition is not None
                and definition.capability_id == "workstream.default"
                and not definition.selectable
            )
        else:
            # Workstream owns exactly one built-in default checker and it runs
            # before admission. POST capabilities are project-selected images.
            valid = False
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
    definitions: dict[tuple[str, str], ExternalCheckerCapabilityDefinition],
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
        definition = definitions.get((binding.capability_id, binding.capability_version))
        if definition is None and any(
            capability_id == binding.capability_id for capability_id, _ in definitions
        ):
            raise ValueError("compilation capability version is stale")
        if (
            requirement is None
            or requirement.disposition is not expected_disposition
            or binding.requirement_id in seen_requirements
            or definition is None
            or not definition.selectable
            or binding.stage.value != expected_stage
        ):
            raise ValueError("compilation capability binding is invalid")
        if definition.registry_entry is None:
            raise ValueError("compilation capability binding is invalid")
        definition.registry_entry.configuration_schema.validate_instance(
            {item.name: item.model_dump(mode="json")["value"] for item in binding.parameters}
        )
        seen_requirements.add(binding.requirement_id)
    return seen_requirements


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
