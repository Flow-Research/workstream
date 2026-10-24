"""Closed internal contracts for durable artifact admission."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, TypeAlias, final
from uuid import UUID

from app.modules.artifacts.sources import CommittedArtifactSource
from app.modules.checkers.api.output_custody import (
    GeneratedOutputReservation,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.actors.api import ServiceIdentity


@final
@dataclass(frozen=True, slots=True)
class TaskImportSourceAdmissionRequest:
    """One canonical JSON upload selected by its immutable ART declaration."""

    source_id: UUID
    source: CommittedArtifactSource


class TaskImportSourceAdmissionAuthority(Protocol):
    async def consume(self, request: TaskImportSourceAdmissionRequest) -> UUID: ...


@final
@dataclass(frozen=True, slots=True)
class GuideArtifactAdmissionRequest:
    """One prepared guide source item admitted under its canonical project."""

    guide_source_item_id: UUID
    source: CommittedArtifactSource
    operation_identity: str
    request_digest: str
    project_id: UUID | None = None
    guide_id: UUID | None = None
    guide_source_snapshot_id: UUID | None = None


@final
@dataclass(frozen=True, slots=True)
class CheckerOutputArtifactAdmissionRequest:
    """One prepared model or trial output admitted under its exact durable owner."""

    reservation: GeneratedOutputReservation
    slot_key: str
    source: CommittedArtifactSource


@final
@dataclass(frozen=True, slots=True)
class SubmissionBundleArtifactAdmissionRequest:
    """One passing prepared bundle selected for durable provider intent."""

    pre_submit_evidence_set_id: UUID | None
    custody: object
    replay_durable_intent_id: UUID | None
    selected_pre_submit_run_id: UUID | None = None
    selected_terminal_digest: str | None = None

    def __post_init__(self) -> None:
        if (
            self.pre_submit_evidence_set_id is not None
            or self.selected_pre_submit_run_id is None
            or self.selected_terminal_digest is None
            or (
                self.selected_terminal_digest is not None
                and (
                    len(self.selected_terminal_digest) != 71
                    or not self.selected_terminal_digest.startswith("sha256:")
                )
            )
        ):
            raise ValueError("submission bundle admission lineage is invalid")

    @property
    def source(self) -> CommittedArtifactSource:
        """Expose only the source sealed into process-local prepared custody."""
        from app.modules.artifacts.submission_custody import SubmissionBundlePreparedCustody

        if type(self.custody) is not SubmissionBundlePreparedCustody:
            raise TypeError("submission bundle prepared custody is unavailable")
        return self.custody.source


ArtifactAdmissionRequest: TypeAlias = (
    GuideArtifactAdmissionRequest
    | TaskImportSourceAdmissionRequest
    | CheckerOutputArtifactAdmissionRequest
    | SubmissionBundleArtifactAdmissionRequest
)


@final
@dataclass(frozen=True, slots=True)
class ArtifactAdmissionResult:
    """Committed pre-I/O attempt and its complete admission-charge set."""

    attempt_id: UUID
    status: str
    operation_identity: str
    request_digest: str
    charge_ids: tuple[UUID, ...]
    replayed: bool


class ArtifactAuthorityDeniedError(RuntimeError):
    """Raised while internal artifact actions remain unavailable."""


@final
@dataclass(frozen=True, slots=True)
class GuideArtifactIngestAuthorityFacts:
    """Canonical guide lineage bound to the exact ingest action."""

    project_id: UUID
    guide_id: UUID
    guide_source_snapshot_id: UUID
    guide_source_item_id: UUID
    operation_identity: str
    request_digest: str
    sha256: str
    byte_count: int
    media_type: str


@final
@dataclass(frozen=True, slots=True)
class GuideSourceReadAuthorityFacts:
    """Exact committed original and already-fenced setup attempt for one file read."""

    project_id: UUID
    guide_id: UUID
    guide_source_snapshot_id: UUID
    guide_source_item_id: UUID
    project_setup_run_id: UUID
    setup_generation: int
    compilation_attempt_id: UUID
    manifest_sha256: str
    document_version_id: UUID
    put_attempt_id: UUID
    content_id: UUID
    replica_id: UUID
    storage_namespace_id: str
    namespace_fingerprint: str
    sha256: str
    byte_count: int
    media_type: str


@final
@dataclass(frozen=True, slots=True)
class SubmissionBundleDurableIntentAuthorityFacts:
    """Final locked contributor and custody facts bound before durable intent."""

    actor_profile_id: UUID
    identity_link_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    predecessor_submission_id: UUID | None
    predecessor_submission_version: int | None
    checker_remediation_manifest_id: UUID | None = field(default=None, kw_only=True)
    pre_submit_evidence_set_id: UUID | None
    prepared_generation_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_sha256: str
    effective_policy_id: UUID
    effective_policy_sha256: str
    pre_submit_policy_id: UUID
    pre_submit_policy_sha256: str
    effective_plan_sha256: str
    semantic_manifest_id: UUID
    semantic_manifest_sha256: str
    semantic_manifest_body: dict[str, object]
    packet_sha256: str
    archive_sha256: str
    archive_byte_count: int
    media_type: str
    storage_scheme: str
    operation_identity: str
    replay_durable_intent_id: UUID | None
    selected_pre_submit_run_id: UUID | None = None
    selected_terminal_digest: str | None = None

    def __post_init__(self) -> None:
        if (
            self.pre_submit_evidence_set_id is not None
            or self.selected_pre_submit_run_id is None
            or self.selected_terminal_digest is None
        ):
            raise ValueError("submission bundle authority lineage is invalid")


class ArtifactInternalResourceType(StrEnum):
    """Closed artifact-owned resource types for internal actions."""

    PUT_ATTEMPT = "artifact_put_attempt"
    VERIFICATION_JOB = "artifact_verification_job"
    PENDING_WORK = "artifact_pending_work"


@final
@dataclass(frozen=True, slots=True)
class ArtifactPutAttemptAuthorityFacts:
    resource_type: ArtifactInternalResourceType
    resource_id: UUID
    operation_identity: str
    namespace_fingerprint: str
    sha256: str
    byte_count: int
    executor_id: UUID
    execution_generation: int


@final
@dataclass(frozen=True, slots=True)
class ArtifactVerificationAuthorityFacts:
    resource_type: ArtifactInternalResourceType
    resource_id: UUID
    replica_id: UUID
    namespace_fingerprint: str
    provider_object_ref: str
    sha256: str
    byte_count: int
    executor_id: UUID
    execution_generation: int


@final
@dataclass(frozen=True, slots=True)
class ArtifactPendingWorkAuthorityFacts:
    resource_type: ArtifactInternalResourceType
    resource_id: str
    scanner_kind: str
    database_cutoff_iso: str
    page_size: int
    put_attempt_ids: tuple[UUID, ...] = ()
    verification_job_ids: tuple[UUID, ...] = ()


ArtifactInternalAuthorityFacts: TypeAlias = (
    ArtifactPutAttemptAuthorityFacts
    | ArtifactVerificationAuthorityFacts
    | ArtifactPendingWorkAuthorityFacts
)


class ArtifactInternalAuthority(Protocol):
    """Transaction-bound authority seam implemented by the ART adapter."""

    async def prepare(
        self,
        *,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        facts: ArtifactInternalAuthorityFacts,
        phase: str,
        idempotency_key: UUID,
    ) -> None: ...

    async def consume(
        self,
        *,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        facts: ArtifactInternalAuthorityFacts,
    ) -> None: ...

    def discard(self) -> None: ...


class DenyArtifactInternalAuthority:
    """Production-safe seam until AUTH activates exact artifact actions."""

    async def prepare(
        self,
        *,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        facts: ArtifactInternalAuthorityFacts,
        phase: str,
        idempotency_key: UUID,
    ) -> None:
        del service_identity, action_id, facts, phase, idempotency_key
        raise ArtifactAuthorityDeniedError("artifact internal action is unavailable")

    async def consume(
        self,
        *,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        facts: ArtifactInternalAuthorityFacts,
    ) -> None:
        del service_identity, action_id, facts
        raise ArtifactAuthorityDeniedError("artifact internal action is unavailable")

    def discard(self) -> None:
        return None


@dataclass(frozen=True, slots=True)
class ArtifactRecoveryResult:
    """Stable identifiers returned by an exact recovery request or replay."""

    recovery_attempt_id: UUID
    source_verification_job_id: UUID
    retry_verification_job_id: UUID
    replayed: bool


class ArtifactRecoveryError(Exception):
    """Base failure for an internal recovery request."""


class ArtifactRecoveryConflictError(ArtifactRecoveryError):
    """Raised when idempotency or lifetime source ownership conflicts."""


class ArtifactRecoveryIneligibleError(ArtifactRecoveryError):
    """Raised when the source job is not exhausted provider-unavailable work."""


class ArtifactRecoveryNotFoundError(ArtifactRecoveryError):
    """Conceal a missing recovery lineage before an exact authority decision."""


# Only these current producers use post-put full-object verification.
VERIFICATION_PRODUCERS = (
    "checker_output",
    "setup_model_output",
    "submission_bundle",
    "task_import_source",
)
