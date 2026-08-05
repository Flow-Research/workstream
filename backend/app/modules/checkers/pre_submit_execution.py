"""Hidden plan-bound execution of Workstream-default pre-submission checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from pathlib import PurePosixPath
import threading
from typing import BinaryIO
from fnmatch import fnmatchcase
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.sources import ArtifactCommitment
from app.modules.artifacts.submission_archive import (
    SealedSubmissionTree,
    SubmissionArchiveInspectionResult,
    SubmissionArchiveInspector,
)
from app.modules.artifacts.submission_manifest import (
    SubmissionChangeGateResult,
    SubmissionManifest,
    build_submission_manifest,
)
from app.modules.checkers.catalogue import (
    PRE_SUBMISSION_RESULT_SCHEMA_VERSION,
    PreSubmissionCheckerCatalogue,
    PreSubmissionCheckerPhase,
    PreSubmissionCheckerState,
    PreSubmissionPlatformCapability,
    PreSubmissionPolicyPrimitive,
)
from app.modules.checkers.effective_plan import (
    EffectivePreSubmissionExecutionPlan,
    EffectivePreSubmissionPlanEntry,
)
from app.modules.checkers.pre_submit_defaults import (
    attestation_validation_facts,
    matched_low_quality_patterns,
)


_EXECUTED_PHASES = frozenset(
    {
        PreSubmissionCheckerPhase.CUSTODY.value,
        PreSubmissionCheckerPhase.IDENTITY.value,
        PreSubmissionCheckerPhase.MATERIALIZATION.value,
        PreSubmissionCheckerPhase.DEFAULT_POLICY.value,
    }
)
_FORBIDDEN_EXACT_NAMES = frozenset({".env", "id_rsa", "id_ed25519"})
_FORBIDDEN_DIRECTORY_NAMES = frozenset({".git"})
_FORBIDDEN_SUFFIXES = (".pem", ".key")
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
_RESULT_METADATA_KEYS = frozenset({"entry_count", "finding_count", "matched_category_count"})


class DefaultPreSubmissionExecutionError(RuntimeError):
    """Fail hidden execution without creating a durable checker effect."""


class PreSubmissionInfrastructureUnavailable(DefaultPreSubmissionExecutionError):
    """Fail closed for an impossible or disabled mandatory execution state."""


class PreSubmissionResultStatus(StrEnum):
    """Closed non-review status vocabulary for every pre-submit result."""

    PASSED = "passed"
    WARNING = "warning"
    ADVISORY_DISABLED = "advisory_disabled"
    DEPENDENCY_NOT_RUN = "dependency_not_run"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SubmissionPacketView:
    """Bounded contributor-authored text accompanying server-owned ZIP facts."""

    summary: str
    contributor_attestation: str

    def __post_init__(self) -> None:
        """Reject unbounded or malformed contributor packet text."""
        for value in (self.summary, self.contributor_attestation):
            if type(value) is not str or len(value.encode("utf-8")) > 64 * 1024:
                raise ValueError("submission packet text is invalid")


@dataclass(frozen=True, slots=True)
class PreSubmissionResultDefinition:
    """Authority-neutral identity for one catalogue-owned definition."""

    dispatch_authority: str
    definition_id: str
    definition_version: str
    public_name: str
    source: str


@dataclass(frozen=True, slots=True)
class PreSubmissionResultPolicyTrace:
    """Exact locked policy trace for one result."""

    effective_plan_sha256: str
    rule_instance_id: str | None
    locked_policy_sha256: str


@dataclass(frozen=True, slots=True)
class PreSubmissionEntryResult:
    """One canonical bounded and path-redacted pre-submit result."""

    schema_version: str
    definition: PreSubmissionResultDefinition
    policy_trace: PreSubmissionResultPolicyTrace
    phase: str
    order: int
    classification: str
    severity: str
    status: PreSubmissionResultStatus
    failure_code: str | None
    message_code: str
    metadata: tuple[tuple[str, int | bool | str], ...] = ()


@dataclass(frozen=True, slots=True)
class PreSubmissionExecutionCustody:
    """Exact server-owned artifact facts observed by the sealed-tree execution."""

    prepared_generation_id: UUID
    archive_sha256: str
    archive_byte_count: int
    semantic_manifest_sha256: str
    storage_scheme: str


@dataclass(frozen=True, slots=True)
class PreSubmissionExecutionResult:
    """Complete canonical platform-plus-project result after scratch cleanup."""

    plan_sha256: str
    custody: PreSubmissionExecutionCustody
    eligible: bool
    entries: tuple[PreSubmissionEntryResult, ...]


@dataclass(frozen=True, slots=True)
class DefaultPreSubmissionExecutionInput:
    """Exact 04A/04B1 facts required by the default executor."""

    plan: EffectivePreSubmissionExecutionPlan
    commitment: ArtifactCommitment
    inspection: SubmissionArchiveInspectionResult
    manifest: SubmissionManifest
    change_gate: SubmissionChangeGateResult
    packet: SubmissionPacketView
    prepared_generation_id: UUID
    storage_scheme: str


class EffectivePreSubmissionProcessor:
    """Prepared-artifact processor owning the sole effective-plan dispatch."""

    def __init__(
        self,
        *,
        archive_inspector: SubmissionArchiveInspector,
        catalogue: PreSubmissionCheckerCatalogue,
        execution_input: DefaultPreSubmissionExecutionInput,
    ) -> None:
        """Bind one exact inspector, catalogue, and immutable execution input."""
        self._archive_inspector = archive_inspector
        self._catalogue = catalogue
        self._input = execution_input
        self._aborted = threading.Event()

    def abort(self) -> None:
        """Prevent checker callback access after caller cancellation or timeout."""
        self._aborted.set()

    def process_blocking(self, reader: BinaryIO, workspace: Path) -> PreSubmissionExecutionResult:
        """Project and execute inside preparation's bounded blocking adapter."""
        self._validate_input()
        return self._archive_inspector.project_and_run(
            reader,
            workspace,
            expected=self._input.inspection,
            callback=self._execute_unless_aborted,
        )

    def _execute_unless_aborted(
        self,
        tree: SealedSubmissionTree,
    ) -> PreSubmissionExecutionResult:
        """Deny checker access after caller cancellation or deadline expiry."""
        if self._aborted.is_set():
            raise DefaultPreSubmissionExecutionError("pre_submission_execution_aborted")
        return self._execute(tree)

    def _validate_input(self) -> None:
        """Fail closed unless every plan, archive, and manifest fact agrees."""
        plan = self._input.plan
        if canonical_json_hash(plan.as_dict()) != plan.plan_sha256:
            raise PreSubmissionInfrastructureUnavailable("pre_submission_plan_identity_invalid")
        if plan.catalogue_manifest_sha256 != self._catalogue.manifest_sha256:
            raise PreSubmissionInfrastructureUnavailable("pre_submission_catalogue_stale")
        if build_submission_manifest(self._input.inspection) != self._input.manifest:
            raise PreSubmissionInfrastructureUnavailable("submission_manifest_identity_unavailable")
        if (
            self._input.change_gate.archive_sha256 != self._input.commitment.sha256
            or self._input.change_gate.archive_byte_count != self._input.commitment.byte_count
            or self._input.change_gate.manifest != self._input.manifest
        ):
            raise PreSubmissionInfrastructureUnavailable("submission_change_identity_invalid")

    def _execute(self, tree: SealedSubmissionTree) -> PreSubmissionExecutionResult:
        """Run the complete ordered platform-plus-project plan exactly once."""
        results: list[PreSubmissionEntryResult] = []
        statuses: dict[str, PreSubmissionResultStatus] = {}
        blocked = False
        executed_ids = {
            entry.definition_id
            for entry in self._input.plan.entries
            if entry.phase in _EXECUTED_PHASES | {PreSubmissionCheckerPhase.PROJECT_POLICY.value}
        }
        for entry in self._input.plan.entries:
            definition = self._catalogue.definition(entry.definition_id)
            if entry.definition_id in statuses:
                raise PreSubmissionInfrastructureUnavailable("pre_submission_duplicate_result")
            if (
                entry.state == PreSubmissionCheckerState.DISABLED.value
                and definition.classification.mandatory
            ):
                raise PreSubmissionInfrastructureUnavailable(
                    "pre_submission_infrastructure_unavailable"
                )
            if (
                entry.definition_version != definition.version
                or entry.dispatch_capability != definition.dispatch_capability
                or entry.classification != definition.classification.value
                or entry.state != definition.state.value
            ):
                raise PreSubmissionInfrastructureUnavailable("pre_submission_plan_entry_stale")
            if any(dependency not in executed_ids for dependency in entry.dependencies):
                raise PreSubmissionInfrastructureUnavailable("pre_submission_dependency_invalid")
            unmet = any(
                statuses.get(dependency)
                not in {
                    PreSubmissionResultStatus.PASSED,
                    PreSubmissionResultStatus.WARNING,
                    PreSubmissionResultStatus.ADVISORY_DISABLED,
                }
                for dependency in entry.dependencies
            )
            if blocked or unmet:
                result = self._result(
                    entry,
                    PreSubmissionResultStatus.DEPENDENCY_NOT_RUN,
                    message_code="dependency_not_run",
                )
            elif entry.state == PreSubmissionCheckerState.DISABLED.value:
                result = self._result(
                    entry,
                    PreSubmissionResultStatus.ADVISORY_DISABLED,
                    message_code="advisory_disabled",
                )
            else:
                result = self._dispatch(entry, tree)
                if result.status is PreSubmissionResultStatus.FAILED:
                    blocked = True
            statuses[entry.definition_id] = result.status
            results.append(result)
        if set(statuses) != executed_ids:
            raise PreSubmissionInfrastructureUnavailable("pre_submission_result_incomplete")
        execution = PreSubmissionExecutionResult(
            plan_sha256=self._input.plan.plan_sha256,
            custody=PreSubmissionExecutionCustody(
                prepared_generation_id=self._input.prepared_generation_id,
                archive_sha256=self._input.commitment.sha256,
                archive_byte_count=self._input.commitment.byte_count,
                semantic_manifest_sha256=self._input.manifest.sha256,
                storage_scheme=self._input.storage_scheme,
            ),
            eligible=not blocked,
            entries=tuple(results),
        )
        validate_pre_submission_execution_result(self._input.plan, execution)
        return execution

    def _dispatch(
        self,
        entry: EffectivePreSubmissionPlanEntry,
        tree: SealedSubmissionTree,
    ) -> PreSubmissionEntryResult:
        """Dispatch one catalogue-validated platform capability or policy primitive."""
        if entry.dispatch_kind == "policy_primitive":
            return self._dispatch_policy(entry, tree)
        if entry.dispatch_kind != "platform_capability":
            raise PreSubmissionInfrastructureUnavailable("pre_submission_dispatch_kind_invalid")
        try:
            capability = PreSubmissionPlatformCapability(entry.dispatch_capability)
        except ValueError as exc:
            raise PreSubmissionInfrastructureUnavailable(
                "pre_submission_dispatch_capability_unknown"
            ) from exc
        if entry.phase in {
            PreSubmissionCheckerPhase.CUSTODY.value,
            PreSubmissionCheckerPhase.IDENTITY.value,
        }:
            return self._result(entry, PreSubmissionResultStatus.PASSED)
        if entry.phase == PreSubmissionCheckerPhase.MATERIALIZATION.value:
            if tree.entries != self._input.manifest.entries:
                raise PreSubmissionInfrastructureUnavailable(
                    "pre_submission_materialization_unavailable"
                )
            return self._result(
                entry,
                PreSubmissionResultStatus.PASSED,
                metadata=(("entry_count", len(tree.entries)),),
            )
        if capability is PreSubmissionPlatformCapability.SUBMISSION_PACKET:
            missing = int(not self._input.packet.summary.strip()) + int(
                not self._input.packet.contributor_attestation.strip()
            )
            return self._blocking_or_pass(entry, missing, "submission_packet_invalid")
        if capability is PreSubmissionPlatformCapability.ATTESTATION:
            facts = attestation_validation_facts(self._input.packet.contributor_attestation)
            missing = sum(
                not getattr(facts, key)
                for key in (
                    "has_required_length",
                    "has_non_generic_text",
                    "has_confidentiality_term",
                    "has_credential_term",
                    "has_source_or_platform_term",
                )
            )
            return self._blocking_or_pass(entry, missing, "attestation_missing")
        if capability is PreSubmissionPlatformCapability.SENSITIVE_PATH:
            matches = sum(
                _is_high_confidence_sensitive(item.normalized_path) for item in tree.entries
            )
            return self._blocking_or_pass(entry, matches, "sensitive_path_forbidden")
        if capability is not PreSubmissionPlatformCapability.QUALITY_WARNING:
            raise PreSubmissionInfrastructureUnavailable(
                "pre_submission_dispatch_capability_unknown"
            )
        matches = matched_low_quality_patterns(
            (
                self._input.packet.summary,
                self._input.packet.contributor_attestation,
                *(item.normalized_path for item in tree.entries),
            )
        )
        if matches:
            return self._result(
                entry,
                PreSubmissionResultStatus.WARNING,
                message_code="quality_signal_warning",
                metadata=(("matched_category_count", len(matches)),),
            )
        return self._result(entry, PreSubmissionResultStatus.PASSED)

    def _dispatch_policy(
        self, entry: EffectivePreSubmissionPlanEntry, tree: SealedSubmissionTree
    ) -> PreSubmissionEntryResult:
        """Evaluate one closed project-policy primitive using server-owned facts only."""
        try:
            primitive = PreSubmissionPolicyPrimitive(entry.dispatch_capability)
        except ValueError as exc:
            raise PreSubmissionInfrastructureUnavailable(
                "pre_submission_policy_primitive_unknown"
            ) from exc
        config = entry.configuration.as_dict()
        file_entries = tuple(item for item in tree.entries if item.sha256 is not None)
        paths = {item.normalized_path for item in file_entries}
        failure_count = 0
        message_code = "passed"
        if primitive is PreSubmissionPolicyPrimitive.REQUIRE_FILE:
            required = self._canonical_policy_paths(config.get("artifact_paths"))
            failure_count = sum(path not in paths for path in required)
            message_code = "required_file_missing"
        elif primitive is PreSubmissionPolicyPrimitive.REQUIRE_MINIMUM_EVIDENCE:
            required = self._canonical_policy_paths(config.get("evidence_paths"))
            failure_count = sum(path not in paths for path in required)
            message_code = "required_evidence_missing"
        elif primitive is PreSubmissionPolicyPrimitive.FORBID_ARTIFACT:
            patterns = self._string_list(config.get("patterns"))
            failure_count = sum(
                any(fnmatchcase(path, pattern) for pattern in patterns) for path in paths
            )
            message_code = "forbidden_artifact_present"
        elif primitive is PreSubmissionPolicyPrimitive.LIMIT_FILE_SIZE:
            maximum = self._positive_limit(config, "maximum_file_size_bytes")
            failure_count = sum(item.byte_count > maximum for item in file_entries)
            message_code = "file_size_limit_exceeded"
        elif primitive is PreSubmissionPolicyPrimitive.LIMIT_PACKAGE_SIZE:
            maximum = self._positive_limit(config, "maximum_package_size_bytes")
            failure_count = int(self._input.manifest.total_expanded_bytes > maximum)
            message_code = "package_size_limit_exceeded"
        elif primitive is PreSubmissionPolicyPrimitive.REQUIRE_ATTESTATION:
            terms = self._string_list(config.get("terms"))
            attestation = self._input.packet.contributor_attestation.casefold()
            failure_count = sum(term.casefold() not in attestation for term in terms)
            message_code = "policy_attestation_missing"
        elif primitive is PreSubmissionPolicyPrimitive.VALIDATE_SUBMISSION_PACKET:
            fields = set(self._string_list(config.get("fields")))
            known = {"summary", "worker_attestation", "contributor_attestation"}
            if not fields.issubset(known):
                raise PreSubmissionInfrastructureUnavailable(
                    "pre_submission_policy_field_unmappable"
                )
            failure_count = int("summary" in fields and not self._input.packet.summary.strip())
            failure_count += int(
                bool(fields & {"worker_attestation", "contributor_attestation"})
                and not self._input.packet.contributor_attestation.strip()
            )
            message_code = "submission_packet_invalid"
        elif primitive is PreSubmissionPolicyPrimitive.REQUIRE_MANIFEST_FIELD:
            failure_count = 0
        elif primitive is PreSubmissionPolicyPrimitive.VERIFY_HASH:
            if config.get("algorithm") != "sha256":
                raise PreSubmissionInfrastructureUnavailable(
                    "pre_submission_policy_hash_algorithm_invalid"
                )
        elif primitive is PreSubmissionPolicyPrimitive.REQUIRE_PACKAGING:
            allowed = config.get("allowed_package_formats", [])
            if not isinstance(allowed, list) or any(not isinstance(item, str) for item in allowed):
                raise PreSubmissionInfrastructureUnavailable(
                    "pre_submission_policy_configuration_invalid"
                )
            failure_count = int(bool(allowed) and "zip" not in allowed)
            message_code = "packaging_requirement_failed"
        elif primitive is PreSubmissionPolicyPrimitive.ENFORCE_STORAGE_SCHEME:
            schemes = self._string_list(config.get("schemes"))
            failure_count = int(self._input.storage_scheme not in schemes)
            message_code = "storage_scheme_not_allowed"
        elif primitive is PreSubmissionPolicyPrimitive.WARN_LOW_QUALITY_GENERATED_ARTIFACT:
            matches = matched_low_quality_patterns(
                (self._input.packet.summary, self._input.packet.contributor_attestation, *paths)
            )
            return self._result(
                entry,
                PreSubmissionResultStatus.WARNING if matches else PreSubmissionResultStatus.PASSED,
                message_code="quality_signal_warning" if matches else "passed",
                metadata=(("matched_category_count", len(matches)),) if matches else (),
            )
        return self._blocking_or_pass(entry, failure_count, message_code)

    @staticmethod
    def _string_list(value: object) -> tuple[str, ...]:
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item for item in value
        ):
            raise PreSubmissionInfrastructureUnavailable(
                "pre_submission_policy_configuration_invalid"
            )
        return tuple(value)

    @classmethod
    def _canonical_policy_paths(cls, value: object) -> tuple[str, ...]:
        paths = cls._string_list(value)
        if len(paths) != len(set(paths)) or any(
            path in {".", ".."}
            or "\\" in path
            or PurePosixPath(path).is_absolute()
            or path != PurePosixPath(path).as_posix()
            or ".." in PurePosixPath(path).parts
            for path in paths
        ):
            raise PreSubmissionInfrastructureUnavailable("pre_submission_policy_path_unmappable")
        return paths

    @staticmethod
    def _positive_limit(config: dict[str, object], key: str) -> int:
        value = config.get(key)
        if type(value) is not int or value < 0:
            raise PreSubmissionInfrastructureUnavailable(
                "pre_submission_policy_configuration_invalid"
            )
        return value

    def _blocking_or_pass(
        self,
        entry: EffectivePreSubmissionPlanEntry,
        finding_count: int,
        message_code: str,
    ) -> PreSubmissionEntryResult:
        """Build one blocking failure or successful bounded result."""
        return self._result(
            entry,
            (
                PreSubmissionResultStatus.FAILED
                if finding_count
                else PreSubmissionResultStatus.PASSED
            ),
            failure_code=entry.failure_code if finding_count else None,
            message_code=message_code if finding_count else "passed",
            metadata=(("finding_count", finding_count),) if finding_count else (),
        )

    def _result(
        self,
        entry: EffectivePreSubmissionPlanEntry,
        status: PreSubmissionResultStatus,
        *,
        failure_code: str | None = None,
        message_code: str = "passed",
        metadata: tuple[tuple[str, int | bool | str], ...] = (),
    ) -> PreSubmissionEntryResult:
        """Build one result bound to the exact plan and definition version."""
        return PreSubmissionEntryResult(
            schema_version=PRE_SUBMISSION_RESULT_SCHEMA_VERSION,
            definition=PreSubmissionResultDefinition(
                dispatch_authority="workstream.pre_submission_checker_catalogue",
                definition_id=entry.definition_id,
                definition_version=entry.definition_version,
                public_name=entry.public_name,
                source=entry.policy_trace_source,
            ),
            policy_trace=PreSubmissionResultPolicyTrace(
                effective_plan_sha256=self._input.plan.plan_sha256,
                rule_instance_id=entry.rule_instance_id,
                locked_policy_sha256=self._input.plan.lineage.effective_policy_hash,
            ),
            phase=entry.phase,
            order=entry.order,
            classification=entry.classification,
            severity="warning" if entry.classification == "advisory" else "blocking",
            status=status,
            failure_code=failure_code,
            message_code=message_code,
            metadata=metadata,
        )


def validate_pre_submission_execution_result(
    plan: EffectivePreSubmissionExecutionPlan,
    execution: PreSubmissionExecutionResult,
) -> None:
    """Reject any result envelope not produced by the exact immutable plan."""
    custody = execution.custody
    try:
        ArtifactCommitment.validate_sha256(custody.archive_sha256)
        ArtifactCommitment.validate_sha256(custody.semantic_manifest_sha256)
    except ValueError as exc:
        raise PreSubmissionInfrastructureUnavailable(
            "pre_submission_result_context_invalid"
        ) from exc
    if (
        type(custody.prepared_generation_id) is not UUID
        or type(custody.archive_byte_count) is not int
        or type(execution.eligible) is not bool
        or custody.archive_byte_count < 0
        or custody.storage_scheme not in {"local", "s3"}
        or execution.plan_sha256 != plan.plan_sha256
        or len(execution.entries) != len(plan.entries)
    ):
        raise PreSubmissionInfrastructureUnavailable("pre_submission_result_context_invalid")
    disqualified = False
    for plan_entry, result in zip(plan.entries, execution.entries, strict=True):
        expected_severity = "warning" if plan_entry.classification == "advisory" else "blocking"
        if (
            type(result.status) is not PreSubmissionResultStatus
            or result.schema_version != plan_entry.result_schema
            or result.definition.dispatch_authority != "workstream.pre_submission_checker_catalogue"
            or result.definition.definition_id != plan_entry.definition_id
            or result.definition.definition_version != plan_entry.definition_version
            or result.definition.public_name != plan_entry.public_name
            or result.definition.source != plan_entry.policy_trace_source
            or result.policy_trace.effective_plan_sha256 != plan.plan_sha256
            or result.policy_trace.rule_instance_id != plan_entry.rule_instance_id
            or result.policy_trace.locked_policy_sha256 != plan.lineage.effective_policy_hash
            or result.phase != plan_entry.phase
            or result.order != plan_entry.order
            or result.classification != plan_entry.classification
            or result.severity != expected_severity
            or result.message_code not in _RESULT_MESSAGE_CODES
            or (
                result.failure_code
                != (
                    plan_entry.failure_code
                    if result.status is PreSubmissionResultStatus.FAILED
                    else None
                )
            )
            or len(result.metadata) != len({key for key, _ in result.metadata})
            or any(
                key not in _RESULT_METADATA_KEYS or type(value) is not int or value < 0
                for key, value in result.metadata
            )
        ):
            raise PreSubmissionInfrastructureUnavailable("pre_submission_result_context_invalid")
        disqualified = disqualified or result.status in {
            PreSubmissionResultStatus.FAILED,
            PreSubmissionResultStatus.DEPENDENCY_NOT_RUN,
        }
    if execution.eligible == disqualified:
        raise PreSubmissionInfrastructureUnavailable("pre_submission_result_context_invalid")


def _is_high_confidence_sensitive(normalized_path: str) -> bool:
    """Match only the narrow Workstream-default sensitive-path set."""
    parts = tuple(part.casefold() for part in PurePosixPath(normalized_path).parts)
    if not parts:
        return False
    return (
        parts[-1] in _FORBIDDEN_EXACT_NAMES
        or parts[-1].endswith(_FORBIDDEN_SUFFIXES)
        or any(part in _FORBIDDEN_DIRECTORY_NAMES for part in parts)
    )
