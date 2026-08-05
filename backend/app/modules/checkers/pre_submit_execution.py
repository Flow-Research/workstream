"""Hidden plan-bound execution of Workstream-default pre-submission checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from pathlib import PurePosixPath
import threading
from typing import BinaryIO

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


class DefaultPreSubmissionExecutionError(RuntimeError):
    """Fail hidden execution without creating a durable checker effect."""


class PreSubmissionInfrastructureUnavailable(DefaultPreSubmissionExecutionError):
    """Fail closed for an impossible or disabled mandatory execution state."""


class DefaultPreSubmissionResultStatus(StrEnum):
    """Closed non-review status vocabulary for one default checker result."""

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
class DefaultPreSubmissionEntryResult:
    """One bounded path-redacted result bound to its exact plan entry."""

    schema_version: str
    plan_sha256: str
    entry_id: str
    entry_version: str
    status: DefaultPreSubmissionResultStatus
    failure_code: str | None
    message_code: str
    metadata: tuple[tuple[str, int | bool | str], ...] = ()


@dataclass(frozen=True, slots=True)
class DefaultPreSubmissionExecutionResult:
    """Complete non-durable 04B2 phase result returned after scratch cleanup."""

    plan_sha256: str
    eligible: bool
    entries: tuple[DefaultPreSubmissionEntryResult, ...]


@dataclass(frozen=True, slots=True)
class DefaultPreSubmissionExecutionInput:
    """Exact 04A/04B1 facts required by the default executor."""

    plan: EffectivePreSubmissionExecutionPlan
    commitment: ArtifactCommitment
    inspection: SubmissionArchiveInspectionResult
    manifest: SubmissionManifest
    change_gate: SubmissionChangeGateResult
    packet: SubmissionPacketView


class DefaultPreSubmissionProcessor:
    """Prepared-artifact processor that owns projection and default dispatch."""

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

    def process_blocking(
        self, reader: BinaryIO, workspace: Path
    ) -> DefaultPreSubmissionExecutionResult:
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
    ) -> DefaultPreSubmissionExecutionResult:
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

    def _execute(self, tree: SealedSubmissionTree) -> DefaultPreSubmissionExecutionResult:
        """Run the ordered platform/default phase slice exactly once."""
        results: list[DefaultPreSubmissionEntryResult] = []
        statuses: dict[str, DefaultPreSubmissionResultStatus] = {}
        blocked = False
        executed_ids = {
            entry.definition_id
            for entry in self._input.plan.entries
            if entry.phase in _EXECUTED_PHASES
        }
        for entry in self._input.plan.entries:
            if entry.phase not in _EXECUTED_PHASES:
                continue
            if entry.dispatch_kind != "platform_capability":
                raise PreSubmissionInfrastructureUnavailable("pre_submission_dispatch_kind_invalid")
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
                    DefaultPreSubmissionResultStatus.PASSED,
                    DefaultPreSubmissionResultStatus.WARNING,
                    DefaultPreSubmissionResultStatus.ADVISORY_DISABLED,
                }
                for dependency in entry.dependencies
            )
            if blocked or unmet:
                result = self._result(
                    entry,
                    DefaultPreSubmissionResultStatus.DEPENDENCY_NOT_RUN,
                    message_code="dependency_not_run",
                )
            elif entry.state == PreSubmissionCheckerState.DISABLED.value:
                result = self._result(
                    entry,
                    DefaultPreSubmissionResultStatus.ADVISORY_DISABLED,
                    message_code="advisory_disabled",
                )
            else:
                result = self._dispatch(entry, tree)
                if result.status is DefaultPreSubmissionResultStatus.FAILED:
                    blocked = True
            statuses[entry.definition_id] = result.status
            results.append(result)
        if set(statuses) != executed_ids:
            raise PreSubmissionInfrastructureUnavailable("pre_submission_result_incomplete")
        return DefaultPreSubmissionExecutionResult(
            plan_sha256=self._input.plan.plan_sha256,
            eligible=not blocked,
            entries=tuple(results),
        )

    def _dispatch(
        self,
        entry: EffectivePreSubmissionPlanEntry,
        tree: SealedSubmissionTree,
    ) -> DefaultPreSubmissionEntryResult:
        """Dispatch one catalogue-validated platform capability."""
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
            return self._result(entry, DefaultPreSubmissionResultStatus.PASSED)
        if entry.phase == PreSubmissionCheckerPhase.MATERIALIZATION.value:
            if tree.entries != self._input.manifest.entries:
                raise PreSubmissionInfrastructureUnavailable(
                    "pre_submission_materialization_unavailable"
                )
            return self._result(
                entry,
                DefaultPreSubmissionResultStatus.PASSED,
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
                DefaultPreSubmissionResultStatus.WARNING,
                message_code="quality_signal_warning",
                metadata=(("matched_category_count", len(matches)),),
            )
        return self._result(entry, DefaultPreSubmissionResultStatus.PASSED)

    def _blocking_or_pass(
        self,
        entry: EffectivePreSubmissionPlanEntry,
        finding_count: int,
        message_code: str,
    ) -> DefaultPreSubmissionEntryResult:
        """Build one blocking failure or successful bounded result."""
        return self._result(
            entry,
            (
                DefaultPreSubmissionResultStatus.FAILED
                if finding_count
                else DefaultPreSubmissionResultStatus.PASSED
            ),
            failure_code=entry.failure_code if finding_count else None,
            message_code=message_code if finding_count else "passed",
            metadata=(("finding_count", finding_count),) if finding_count else (),
        )

    def _result(
        self,
        entry: EffectivePreSubmissionPlanEntry,
        status: DefaultPreSubmissionResultStatus,
        *,
        failure_code: str | None = None,
        message_code: str = "passed",
        metadata: tuple[tuple[str, int | bool | str], ...] = (),
    ) -> DefaultPreSubmissionEntryResult:
        """Build one result bound to the exact plan and definition version."""
        return DefaultPreSubmissionEntryResult(
            schema_version=PRE_SUBMISSION_RESULT_SCHEMA_VERSION,
            plan_sha256=self._input.plan.plan_sha256,
            entry_id=entry.definition_id,
            entry_version=entry.definition_version,
            status=status,
            failure_code=failure_code,
            message_code=message_code,
            metadata=metadata,
        )


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
