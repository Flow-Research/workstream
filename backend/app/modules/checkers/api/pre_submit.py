"""Dependency-safe CHECKER contracts for pre-submission planning and results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from uuid import UUID


EFFECTIVE_PRE_SUBMISSION_PLAN_SCHEMA_VERSION = "effective_pre_submission_plan.v1"
EFFECTIVE_PRE_SUBMISSION_PLAN_HASH_DOMAIN = "workstream.effective_pre_submission_plan.v1"
ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES = frozenset({"local", "s3"})
_RESULT_MESSAGE_CODES = frozenset(
    {
        "advisory_disabled",
        "attestation_missing",
        "dependency_not_run",
        "file_size_limit_exceeded",
        "forbidden_artifact_present",
        "package_size_limit_exceeded",
        "packaging_requirement_failed",
        "passed",
        "policy_attestation_missing",
        "quality_signal_warning",
        "required_evidence_missing",
        "required_file_missing",
        "sensitive_path_forbidden",
        "storage_scheme_not_allowed",
        "submission_packet_invalid",
    }
)
PRE_SUBMISSION_RESULT_METADATA_KEYS = frozenset(
    {"entry_count", "finding_count", "matched_category_count"}
)
_EXECUTION_STATUSES = frozenset(
    {"passed", "warning", "advisory_disabled", "dependency_not_run", "failed"}
)


class EffectivePreSubmissionPlanError(ValueError):
    """Reject a stale, ambiguous, or unavailable effective plan."""


class PreSubmissionInfrastructureUnavailableError(EffectivePreSubmissionPlanError):
    """Fail preparation closed when mandatory deployment capability is disabled."""


@dataclass(frozen=True, slots=True)
class EffectivePreSubmissionPlanLineage:
    """Exact server-locked lineage used to compile one checker plan."""

    project_id: UUID
    guide_id: UUID
    guide_version: int
    source_snapshot_id: UUID
    source_snapshot_hash: str
    effective_policy_id: UUID
    effective_policy_hash: str
    pre_submit_policy_id: UUID
    pre_submit_policy_bundle_hash: str

    def __post_init__(self) -> None:
        if any(
            type(value) is not UUID
            for value in (
                self.project_id,
                self.guide_id,
                self.source_snapshot_id,
                self.effective_policy_id,
                self.pre_submit_policy_id,
            )
        ):
            raise EffectivePreSubmissionPlanError("effective plan lineage id is invalid")
        if type(self.guide_version) is not int or self.guide_version <= 0:
            raise EffectivePreSubmissionPlanError("effective plan guide version is invalid")
        for value in (
            self.source_snapshot_hash,
            self.effective_policy_hash,
            self.pre_submit_policy_bundle_hash,
        ):
            _validate_sha256(value)

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": str(self.project_id),
            "guide_id": str(self.guide_id),
            "guide_version": self.guide_version,
            "source_snapshot_id": str(self.source_snapshot_id),
            "source_snapshot_hash": self.source_snapshot_hash,
            "effective_policy_id": str(self.effective_policy_id),
            "effective_policy_hash": self.effective_policy_hash,
            "pre_submit_policy_id": str(self.pre_submit_policy_id),
            "pre_submit_policy_bundle_hash": self.pre_submit_policy_bundle_hash,
        }


@dataclass(frozen=True, slots=True)
class FrozenJsonObject:
    """Hashable deeply immutable projection of one canonical JSON object."""

    items: tuple[tuple[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {key: thaw_json(value) for key, value in self.items}


@dataclass(frozen=True, slots=True)
class EffectivePreSubmissionPlanEntry:
    """One ordered checker definition or locked-policy rule instance."""

    definition_id: str
    definition_version: str
    public_name: str
    phase: str
    order: int
    dependencies: tuple[str, ...]
    classification: str
    checker_definition_state: str
    disabled_behavior: str
    dispatch_kind: str
    dispatch_capability: str
    typed_inputs: tuple[str, ...]
    result_schema: str
    failure_code: str
    resource_budget: tuple[tuple[str, int], ...]
    policy_trace_source: str
    rule_instance_id: str | None
    configuration: FrozenJsonObject
    configuration_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "definition_id": self.definition_id,
            "definition_version": self.definition_version,
            "public_name": self.public_name,
            "phase": self.phase,
            "order": self.order,
            "dependencies": list(self.dependencies),
            "classification": self.classification,
            "checker_definition_state": self.checker_definition_state,
            "disabled_behavior": self.disabled_behavior,
            "dispatch_kind": self.dispatch_kind,
            "dispatch_capability": self.dispatch_capability,
            "typed_inputs": list(self.typed_inputs),
            "result_schema": self.result_schema,
            "failure_code": self.failure_code,
            "resource_budget": dict(self.resource_budget),
            "policy_trace_source": self.policy_trace_source,
            "rule_instance_id": self.rule_instance_id,
            "configuration": self.configuration.as_dict(),
            "configuration_sha256": self.configuration_sha256,
        }


@dataclass(frozen=True, slots=True)
class EffectivePreSubmissionExecutionPlan:
    """Canonical side-effect-free plan returned by the CHECKER capability."""

    lineage: EffectivePreSubmissionPlanLineage
    catalogue_id: str
    catalogue_version: str
    catalogue_schema_version: str
    catalogue_manifest_sha256: str
    entries: tuple[EffectivePreSubmissionPlanEntry, ...]
    plan_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return effective_plan_body(
            self.lineage,
            self.catalogue_id,
            self.catalogue_version,
            self.catalogue_schema_version,
            self.catalogue_manifest_sha256,
            self.entries,
        )


class EffectivePreSubmissionPlanningPort(Protocol):
    """CHECKER-owned deterministic planning capability."""

    def compile_effective_plan(
        self,
        *,
        lineage: EffectivePreSubmissionPlanLineage,
        effective_policy: Mapping[str, object],
        compiled_bundle: Mapping[str, object],
    ) -> EffectivePreSubmissionExecutionPlan:
        """Compile one plan from exact immutable locked-policy facts."""


@dataclass(frozen=True, slots=True)
class SubmissionPacketView:
    """Bounded contributor-authored text accompanying server-owned ZIP facts."""

    summary: str
    contributor_attestation: str

    def __post_init__(self) -> None:
        for value in (self.summary, self.contributor_attestation):
            if type(value) is not str or len(value.encode("utf-8")) > 64 * 1024:
                raise ValueError("submission packet text is invalid")


@dataclass(frozen=True, slots=True)
class PreSubmissionExecutionEntryFacts:
    """One bounded checker outcome without ART custody or persistence facts."""

    dispatch_authority: str
    definition_id: str
    definition_version: str
    public_name: str
    policy_source: str
    effective_plan_sha256: str
    rule_instance_id: str | None
    locked_policy_sha256: str
    phase: str
    order: int
    classification: str
    severity: str
    checker_execution_status: str
    failure_code: str | None
    message_code: str
    metadata: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class PreSubmissionExecutionFacts:
    """Bounded immutable CHECKER result safe for cross-module use."""

    plan_sha256: str
    eligible: bool
    entries: tuple[PreSubmissionExecutionEntryFacts, ...]


def validate_pre_submission_execution_facts(
    plan: EffectivePreSubmissionExecutionPlan,
    execution: PreSubmissionExecutionFacts,
) -> None:
    """Validate one bounded CHECKER result against its exact immutable plan."""
    if (
        type(execution.eligible) is not bool
        or execution.plan_sha256 != plan.plan_sha256
        or len(execution.entries) != len(plan.entries)
    ):
        raise PreSubmissionInfrastructureUnavailableError(
            "pre_submission_result_context_invalid"
        )
    disqualified = False
    for plan_entry, result in zip(plan.entries, execution.entries, strict=True):
        expected_severity = (
            "warning" if plan_entry.classification == "advisory" else "blocking"
        )
        status = result.checker_execution_status
        if (
            result.dispatch_authority != "workstream.pre_submission_checker_catalogue"
            or result.definition_id != plan_entry.definition_id
            or result.definition_version != plan_entry.definition_version
            or result.public_name != plan_entry.public_name
            or result.policy_source != plan_entry.policy_trace_source
            or result.effective_plan_sha256 != plan.plan_sha256
            or result.rule_instance_id != plan_entry.rule_instance_id
            or result.locked_policy_sha256 != plan.lineage.effective_policy_hash
            or result.phase != plan_entry.phase
            or result.order != plan_entry.order
            or result.classification != plan_entry.classification
            or result.severity != expected_severity
            or status not in _EXECUTION_STATUSES
            or result.message_code not in _RESULT_MESSAGE_CODES
            or result.failure_code
            != (plan_entry.failure_code if status == "failed" else None)
            or len(result.metadata) != len({key for key, _ in result.metadata})
            or any(
                key not in PRE_SUBMISSION_RESULT_METADATA_KEYS
                or type(value) is not int
                or value < 0
                for key, value in result.metadata
            )
        ):
            raise PreSubmissionInfrastructureUnavailableError(
                "pre_submission_result_context_invalid"
            )
        disqualified = disqualified or status in {"failed", "dependency_not_run"}
    if execution.eligible == disqualified:
        raise PreSubmissionInfrastructureUnavailableError(
            "pre_submission_result_context_invalid"
        )


def effective_plan_body(
    lineage: EffectivePreSubmissionPlanLineage,
    catalogue_id: str,
    catalogue_version: str,
    catalogue_schema_version: str,
    catalogue_manifest_sha256: str,
    entries: tuple[EffectivePreSubmissionPlanEntry, ...],
) -> dict[str, Any]:
    """Return the canonical hash body for one public plan."""
    return {
        "domain": EFFECTIVE_PRE_SUBMISSION_PLAN_HASH_DOMAIN,
        "schema_version": EFFECTIVE_PRE_SUBMISSION_PLAN_SCHEMA_VERSION,
        "lineage": lineage.as_dict(),
        "catalogue": {
            "id": catalogue_id,
            "version": catalogue_version,
            "schema_version": catalogue_schema_version,
            "manifest_sha256": catalogue_manifest_sha256,
        },
        "entries": [entry.as_dict() for entry in entries],
    }


def freeze_json(value: Any) -> Any:
    """Convert canonical JSON containers into immutable public values."""
    if isinstance(value, dict):
        return FrozenJsonObject(
            tuple((key, freeze_json(item)) for key, item in sorted(value.items()))
        )
    if isinstance(value, list):
        return tuple(freeze_json(item) for item in value)
    return value


def thaw_json(value: Any) -> Any:
    """Return a detached JSON-compatible projection."""
    if isinstance(value, FrozenJsonObject):
        return value.as_dict()
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


def _validate_sha256(value: str) -> None:
    if (
        type(value) is not str
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise EffectivePreSubmissionPlanError("effective plan lineage hash is invalid")
