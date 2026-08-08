"""Project guide analysis agent contracts."""

from __future__ import annotations

import hashlib
import json
import math
import re
from enum import StrEnum
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

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

MAXIMUM_VERIFIED_GUIDE_AGENT_MATERIAL_BYTES = 12 * 1024 * 1024
MAXIMUM_COMPILATION_FINDINGS = 100
MAXIMUM_COMPILATION_REQUIREMENTS = 200
MAXIMUM_COMPILATION_BINDINGS = 100
MAXIMUM_COMPILATION_SUGGESTIONS = 50
MAXIMUM_COMPILATION_NOTES = 20
MAXIMUM_EVIDENCE_REFS = 20

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


class ResourceBudget(BaseModel):
    """Frozen canonical ART resource budget."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    maximum_results: StrictInt = Field(ge=1)


class PreSubmissionCapabilityDefinition(BaseModel):
    """Exact read-only projection of one ART catalogue definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stable_id: str
    version: str
    public_name: str
    owner: str
    phase: str
    order: int = Field(ge=0)
    dependencies: tuple[str, ...]
    classification: str
    typed_inputs: tuple[str, ...]
    result_schema: str
    failure_code: str
    resource_budget: ResourceBudget
    state: Literal["enabled", "disabled"]
    disabled_behavior: str
    policy_trace_source: str
    dispatch_kind: Literal["platform_capability", "policy_primitive"]
    dispatch_capability: str
    primitive: str | None = None
    policy_fields: tuple[str, ...] = ()
    selectable: bool


class PreSubmissionCapabilityProjection(BaseModel):
    """Complete immutable ART catalogue plus model-facing selectability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalogue_id: Literal["workstream.pre_submission_checkers"]
    version: Literal["v0.1"]
    schema_version: Literal["pre_submission_checker_catalogue.v1"]
    manifest_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    available: bool
    definitions: tuple[PreSubmissionCapabilityDefinition, ...]


class PostSubmissionCapabilityDefinition(BaseModel):
    """One registered post-submit capability in a frozen source snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: str
    capability_version: str
    stage: Literal["post_submit"] = "post_submit"
    platform_default: bool
    selectable: bool


class PostSubmissionCapabilityProjection(BaseModel):
    """Read-only projection of CHECKER registration and frozen defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalogue_id: Literal["workstream.post_submission_checkers"]
    source_version: str
    schema_version: Literal["post_submission_checker_capability_projection.v1"]
    manifest_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    definitions: tuple[PostSubmissionCapabilityDefinition, ...]


class RepresentativeTaskPolicyContext(BaseModel):
    """Bounded server-redacted task shape; never task or actor content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_kind: str = Field(max_length=100)
    deliverable_kinds: tuple[str, ...] = Field(default=(), max_length=20)
    required_evidence_kinds: tuple[str, ...] = Field(default=(), max_length=20)

    @field_validator("task_kind")
    @classmethod
    def validate_task_kind(cls, value: str) -> str:
        """Require a canonical redacted task-kind identifier."""
        return _validated_identifier(value)

    @field_validator("deliverable_kinds", "required_evidence_kinds")
    @classmethod
    def validate_task_identifiers(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Require unique canonical task policy identifiers."""
        if len(values) != len(set(values)):
            raise ValueError("task policy identifiers must be unique")
        return tuple(_validated_identifier(value) for value in values)


class GuideEvidenceRef(BaseModel):
    """Server-minted reference to immutable extracted guide content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_item_id: UUID
    extraction_usage_id: UUID
    canonical_output_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    start_ordinal: StrictInt = Field(ge=0, le=10_000_000)
    end_ordinal: StrictInt = Field(gt=0, le=10_000_000)

    @model_validator(mode="after")
    def validate_ordinals(self) -> GuideEvidenceRef:
        """Require a non-empty ordered evidence range."""
        if self.end_ordinal <= self.start_ordinal:
            raise ValueError("evidence ordinals are invalid")
        return self


class GuideSourceLineageRef(BaseModel):
    """Immutable source lineage available for evidence resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_item_id: UUID
    extraction_usage_id: UUID
    canonical_output_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class VerifiedGuideMaterialSnapshot(BaseModel):
    """Deeply immutable canonical snapshot of exact ART-verified material."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str
    guide_id: str
    guide_version: str
    source_snapshot_id: str
    source_snapshot_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    canonical_payload: bytes = Field(max_length=MAXIMUM_VERIFIED_GUIDE_AGENT_MATERIAL_BYTES)
    canonical_payload_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_lineage: tuple[GuideSourceLineageRef, ...]

    @model_validator(mode="after")
    def validate_snapshot_integrity(self) -> VerifiedGuideMaterialSnapshot:
        """Bind the immutable payload to its hash and unique lineage."""
        expected_hash = "sha256:" + hashlib.sha256(self.canonical_payload).hexdigest()
        if self.canonical_payload_sha256 != expected_hash:
            raise ValueError("canonical guide material hash is invalid")
        identities = {
            (item.source_item_id, item.extraction_usage_id) for item in self.source_lineage
        }
        if len(identities) != len(self.source_lineage):
            raise ValueError("canonical guide source lineage contains duplicates")
        return self

    @classmethod
    def from_material(cls, material: GuideSourceMaterial) -> VerifiedGuideMaterialSnapshot:
        """Snapshot exact verified material after rejecting legacy open shapes."""
        if not material.verified_artifact_material:
            raise ValueError("compilation requires ART-verified guide material")
        if material.representative_task_material.items:
            raise ValueError("raw representative-task material is forbidden")
        if set(material.guide_material) != {"content_markdown"}:
            raise ValueError("guide material contains non-canonical fields")
        if not isinstance(material.guide_material["content_markdown"], str):
            raise ValueError("canonical guide content must be text")
        payload = canonical_guide_source_material_bytes(material)
        if len(payload) > MAXIMUM_VERIFIED_GUIDE_AGENT_MATERIAL_BYTES:
            raise ValueError("canonical guide material exceeds the bounded input")
        lineage = tuple(
            GuideSourceLineageRef(
                source_item_id=UUID(item.source_item_id),
                extraction_usage_id=UUID(item.extraction_usage_id),
                canonical_output_sha256=item.canonical_output_sha256,
            )
            for item in material.source_items
            if item.source_item_id and item.extraction_usage_id and item.canonical_output_sha256
        )
        if not lineage or len(lineage) != len(material.source_items):
            raise ValueError("compilation material requires complete source lineage")
        return cls(
            project_id=material.project_id,
            guide_id=material.guide_id,
            guide_version=material.guide_version,
            source_snapshot_id=material.source_snapshot_id,
            source_snapshot_hash=material.source_snapshot_hash,
            canonical_payload=payload,
            canonical_payload_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
            source_lineage=lineage,
        )


CapabilityScalar = Annotated[
    StrictStr | StrictInt | StrictFloat | StrictBool,
    Field(union_mode="left_to_right"),
]


class CapabilityParameter(BaseModel):
    """Closed flat capability configuration supplied for trusted validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    value: CapabilityScalar | tuple[CapabilityScalar, ...]

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


class CapabilityBindingProposal(BaseModel):
    """One stage-bound proposal against canonical capability truth."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_id: str
    capability_id: str
    capability_version: str
    stage: CompilationStage
    parameters: tuple[CapabilityParameter, ...] = Field(default=(), max_length=50)

    @field_validator("requirement_id", "capability_id", "capability_version")
    @classmethod
    def validate_identifiers(cls, value: str) -> str:
        """Require canonical requirement and capability identity fields."""
        return _validated_identifier(value)

    @model_validator(mode="after")
    def validate_parameter_names(self) -> CapabilityBindingProposal:
        """Reject duplicate parameter names within one binding."""
        names = [parameter.name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("capability parameters must be unique")
        return self


class CompilationFinding(BaseModel):
    """One bounded operator-visible finding from unified compilation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Literal["blocking_gap", "warning", "info"]
    code: str
    message: str
    evidence_refs: tuple[GuideEvidenceRef, ...] = Field(
        default=(), max_length=MAXIMUM_EVIDENCE_REFS
    )

    _code = field_validator("code")(_validated_identifier)
    _message = field_validator("message")(_validated_safe_model_text)


class PlatformCoverageRef(BaseModel):
    """Exact non-selectable phase-owner capability covering a requirement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: str
    capability_version: str
    stage: CompilationStage

    _capability_identity = field_validator("capability_id", "capability_version")(
        _validated_identifier
    )


class AtomicGuideRequirement(BaseModel):
    """One evidence-linked guide requirement with one disposition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_id: str
    statement: str
    disposition: RequirementDisposition
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
    required_artifacts: tuple[str, ...] = Field(default=(), max_length=100)
    forbidden_artifacts: tuple[str, ...] = Field(default=(), max_length=100)
    required_evidence: tuple[str, ...] = Field(default=(), max_length=100)
    attestation_terms: tuple[str, ...] = Field(default=(), max_length=50)

    @field_validator(
        "required_artifacts", "forbidden_artifacts", "required_evidence", "attestation_terms"
    )
    @classmethod
    def validate_policy_text(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject duplicate or unsafe artifact policy text."""
        if len(values) != len(set(values)):
            raise ValueError("artifact policy values must be unique")
        return tuple(_validated_safe_model_text(value) for value in values)

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

    title: str
    rationale: str
    evidence_refs: tuple[GuideEvidenceRef, ...] = Field(
        default=(), max_length=MAXIMUM_EVIDENCE_REFS
    )

    _title = field_validator("title")(_validated_safe_model_text)
    _rationale = field_validator("rationale")(_validated_safe_model_text)


class ProjectGuideCompilationContext(BaseModel):
    """Exact bounded input for one future unified compilation attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    material: VerifiedGuideMaterialSnapshot
    setup_run_id: UUID
    setup_generation: StrictInt = Field(ge=1)
    instruction_version: str = Field(max_length=100)
    agent_identity: str = Field(max_length=100)
    pre_submission_capabilities: PreSubmissionCapabilityProjection
    post_submission_capabilities: PostSubmissionCapabilityProjection
    representative_task: RepresentativeTaskPolicyContext | None = None


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
    pre_submit_bindings: tuple[CapabilityBindingProposal, ...] = Field(
        default=(), max_length=MAXIMUM_COMPILATION_BINDINGS
    )
    post_submit_bindings: tuple[CapabilityBindingProposal, ...] = Field(
        default=(), max_length=MAXIMUM_COMPILATION_BINDINGS
    )
    capability_suggestions: tuple[CapabilitySuggestion, ...] = Field(
        default=(), max_length=MAXIMUM_COMPILATION_SUGGESTIONS
    )
    setup_notes: tuple[str, ...] = Field(default=(), max_length=MAXIMUM_COMPILATION_NOTES)
    agent_name: Literal["ProjectGuideCompilationAgent"] = "ProjectGuideCompilationAgent"
    agent_version: str = Field(max_length=100)
    schema_version: Literal["project_guide_compilation_result.v1"] = (
        "project_guide_compilation_result.v1"
    )

    @field_validator("setup_notes")
    @classmethod
    def validate_notes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject unsafe setup notes before trusted validation."""
        return tuple(_validated_safe_model_text(value) for value in values)

    _agent_version = field_validator("agent_version")(_validated_identifier)


def validate_project_guide_compilation_result(
    context: ProjectGuideCompilationContext,
    result: ProjectGuideCompilationResult,
) -> None:
    """Fail closed when an untrusted result diverges from canonical capability truth."""
    if not context.pre_submission_capabilities.available:
        raise ValueError("pre-submit capability projection is unavailable")
    requirements = {item.requirement_id: item for item in result.requirements}
    if len(requirements) != len(result.requirements):
        raise ValueError("compilation requirements must be unique")
    _validate_status_consistency(result)
    if result.status == "guide_blocked":
        if (
            result.submission_artifact_policy
            or result.pre_submit_bindings
            or result.post_submit_bindings
        ):
            raise ValueError("blocked guide cannot publish policy proposals")
    elif result.submission_artifact_policy is None:
        raise ValueError("draft-ready compilation requires artifact policy")

    pre_definitions = {
        definition.stable_id: definition
        for definition in context.pre_submission_capabilities.definitions
    }
    post_definitions = {
        definition.capability_id: definition
        for definition in context.post_submission_capabilities.definitions
    }
    _validate_platform_coverage(result.requirements, pre_definitions, post_definitions)
    _validate_evidence_lineage(context, result)
    pre_bound_requirements = _validate_bindings(
        result.pre_submit_bindings, requirements, pre_definitions, "pre_submit"
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
    post_definitions: dict[str, PostSubmissionCapabilityDefinition],
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
            str(item.extraction_usage_id),
            item.canonical_output_sha256,
        )
        for item in context.material.source_lineage
    }
    evidence_refs = (
        *(ref for finding in result.findings for ref in finding.evidence_refs),
        *(ref for requirement in result.requirements for ref in requirement.evidence_refs),
        *(ref for suggestion in result.capability_suggestions for ref in suggestion.evidence_refs),
    )
    for evidence in evidence_refs:
        lineage = (
            str(evidence.source_item_id),
            str(evidence.extraction_usage_id),
            evidence.canonical_output_sha256,
        )
        if lineage not in source_lineage:
            raise ValueError("compilation evidence does not resolve to source lineage")


def _validate_bindings(
    bindings: tuple[CapabilityBindingProposal, ...],
    requirements: dict[str, AtomicGuideRequirement],
    definitions: dict[str, PreSubmissionCapabilityDefinition | PostSubmissionCapabilityDefinition],
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
        if isinstance(definition, PreSubmissionCapabilityDefinition):
            allowed_fields = set(definition.policy_fields)
            if any(parameter.name not in allowed_fields for parameter in binding.parameters):
                raise ValueError("pre-submit capability parameters are invalid")
        elif binding.parameters:
            raise ValueError("post-submit capability parameters are not supported")
        seen_requirements.add(binding.requirement_id)
    return seen_requirements


class ProjectAgentRuntimeError(Exception):
    """Raised when a project-agent runtime cannot complete a trusted operation."""


class ProjectAgentRuntimeConfigurationError(ProjectAgentRuntimeError):
    """Raised when a configured project-agent runtime is unavailable or incomplete."""


class GuideSourceItemMaterial(BaseModel):
    """One immutable source item made available to setup agents."""

    model_config = ConfigDict(extra="forbid")

    source_kind: str
    ingestion_adapter: str
    media_type: str | None = None
    source_item_id: str | None = None
    item_order: int | None = None
    binding_id: str | None = None
    artifact_content_id: str | None = None
    artifact_sha256: str | None = None
    artifact_byte_count: int | None = None
    classification_id: str | None = None
    detected_format: str | None = None
    extraction_attempt_id: str | None = None
    extraction_usage_id: str | None = None
    extracted_content_id: str | None = None
    extractor_name: str | None = None
    extractor_version: str | None = None
    extraction_policy_version: str | None = None
    canonical_output_sha256: str | None = None
    omission_facts: dict[str, Any] | None = None
    canonical_content: str | None = None
    structural_metadata: dict[str, Any] | None = None
    untrusted_data: bool = False
    untrusted_data_label: Literal["UNTRUSTED_GUIDE_SOURCE_DATA"] | None = None


class RepresentativeTaskMaterialContext(BaseModel):
    """Representative task material used for guide sufficiency analysis."""

    model_config = ConfigDict(extra="forbid")

    items: list[GuideSourceItemMaterial] = Field(default_factory=list)


class GuideSourceMaterial(BaseModel):
    """Immutable project and task-context material made available to setup agents."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    guide_id: str
    guide_version: str
    source_snapshot_id: str
    source_snapshot_hash: str
    guide_material: dict[str, Any]
    verified_artifact_material: bool = False
    source_items: list[GuideSourceItemMaterial] = Field(default_factory=list)
    representative_task_material: RepresentativeTaskMaterialContext = Field(
        default_factory=RepresentativeTaskMaterialContext
    )


def canonical_guide_source_material_bytes(material: GuideSourceMaterial) -> bytes:
    """Serialize the exact deterministic UTF-8 payload supplied to the agent."""
    return json.dumps(
        material.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


class AgentFinding(BaseModel):
    """Structured finding emitted by a project setup agent."""

    model_config = ConfigDict(extra="forbid")

    severity: Literal["blocking_gap", "warning", "info"]
    code: str = Field(max_length=100)
    message: str = Field(max_length=1000)
    location: str | None = Field(default=None, max_length=500)


class GuideSufficiencyAgentResult(BaseModel):
    """Structured output from the project guide sufficiency agent."""

    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "guide_sufficient",
        "guide_blocked",
        "guide_sufficient_with_warnings",
    ]
    findings: list[AgentFinding] = Field(default_factory=list)
    summary: str | None = Field(default=None, max_length=2000)
    agent_name: str = Field(default="ProjectGuideSufficiencyAgent", max_length=100)
    agent_version: str = Field(max_length=50)


class SubmissionArtifactPolicyDerivationResult(BaseModel):
    """Structured output from the submission artifact policy derivation agent."""

    model_config = ConfigDict(extra="forbid")

    policy_version: str = Field(max_length=50)
    policy_body: dict[str, Any]
    change_summary: str | None = Field(default=None, max_length=2000)
    agent_name: str = Field(default="SubmissionArtifactPolicyDerivationAgent", max_length=100)
    agent_version: str = Field(max_length=100)


class PostSubmitCheckerCatalogEntry(BaseModel):
    """One registered deterministic checker available for post-submit setup."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=100)
    platform_default: bool = False


class PostSubmitCheckerPolicyEvidenceRef(BaseModel):
    """Bounded source-evidence reference for post-submit derivation reasons."""

    model_config = ConfigDict(extra="forbid")

    ref: str = Field(max_length=200)


class PostSubmitCheckerPolicyReason(BaseModel):
    """Reason tying a requested checker to bounded source evidence."""

    model_config = ConfigDict(extra="forbid")

    checker_name: str = Field(max_length=100)
    rationale: str = Field(max_length=1000)
    evidence_refs: list[PostSubmitCheckerPolicyEvidenceRef] = Field(
        default_factory=list,
        max_length=10,
    )


class UnsupportedPostSubmitCheckerGap(BaseModel):
    """Unsupported required post-submit checker requirement from guide setup."""

    model_config = ConfigDict(extra="forbid")

    requested_checker: str = Field(max_length=500)
    reason: str = Field(max_length=1000)
    evidence_refs: list[PostSubmitCheckerPolicyEvidenceRef] = Field(
        default_factory=list,
        max_length=10,
    )


class PostSubmitCheckerPolicyCorrectionFeedback(BaseModel):
    """Bounded operator feedback for replacing one superseded checker policy."""

    model_config = ConfigDict(extra="forbid")

    superseded_policy_id: str = Field(max_length=36)
    superseded_policy_hash: str = Field(max_length=71)
    required_checkers: list[str] = Field(default_factory=list, max_length=100)
    warning_checkers: list[str] = Field(default_factory=list, max_length=100)
    blocking_severities: list[str] = Field(default_factory=list, max_length=10)
    correction_reason: str = Field(max_length=500)


class PostSubmitCheckerPolicyDerivationContext(BaseModel):
    """Server-owned context supplied to the post-submit policy derivation agent."""

    model_config = ConfigDict(extra="forbid")

    sufficiency_report_summary: dict[str, Any]
    effective_policy_summary: dict[str, Any]
    pre_submit_checker_summary: dict[str, Any]
    registered_checker_catalog: list[PostSubmitCheckerCatalogEntry]
    correction_feedback: PostSubmitCheckerPolicyCorrectionFeedback | None = None


class PostSubmitCheckerPolicyDerivationResult(BaseModel):
    """Structured output from the post-submit checker policy derivation agent."""

    model_config = ConfigDict(extra="forbid")

    required_checkers: list[str] = Field(default_factory=list, max_length=100)
    warning_checkers: list[str] = Field(default_factory=list, max_length=100)
    blocking_severities: list[str] | None = Field(default=None, max_length=10)
    reasons: list[PostSubmitCheckerPolicyReason] = Field(default_factory=list, max_length=100)
    unsupported_required_checks: list[UnsupportedPostSubmitCheckerGap] = Field(
        default_factory=list,
        max_length=100,
    )
    setup_notes: list[str] = Field(default_factory=list, max_length=20)
    agent_name: str = Field(default="PostSubmitCheckerPolicyDerivationAgent", max_length=100)
    agent_version: str = Field(max_length=100)


class ProjectGuideAgentRuntime(Protocol):
    """Port implemented by project guide setup agent runtimes."""

    async def analyze_guide_sufficiency(
        self,
        material: GuideSourceMaterial,
    ) -> GuideSufficiencyAgentResult:
        """Assess whether guide material is sufficient for project setup."""

    async def derive_submission_artifact_policy(
        self,
        material: GuideSourceMaterial,
        sufficiency_report: GuideSufficiencyAgentResult,
    ) -> SubmissionArtifactPolicyDerivationResult:
        """Derive the machine-readable submission artifact policy."""

    async def derive_post_submit_checker_policy(
        self,
        material: GuideSourceMaterial,
        context: PostSubmitCheckerPolicyDerivationContext,
    ) -> PostSubmitCheckerPolicyDerivationResult:
        """Derive the constrained project post-submit checker policy spec."""
