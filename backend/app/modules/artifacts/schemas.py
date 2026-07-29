"""Closed internal contracts for durable artifact admission."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeAlias, final
from uuid import UUID

from app.modules.artifacts.sources import CommittedArtifactSource
from app.modules.authorization.runtime import AuthorizationContext
from app.modules.authorization.catalogue import ActionId
from app.modules.actors.service_identities import ServiceIdentity


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
class ContributorArtifactAdmissionRequest:
    """One prepared contributor item admitted under its upload session."""

    authorization_context: AuthorizationContext
    upload_item_id: UUID
    source: CommittedArtifactSource


@final
@dataclass(frozen=True, slots=True)
class CheckerOutputArtifactAdmissionRequest:
    """One prepared checker output admitted under its exact checker run."""

    authorization_context: AuthorizationContext
    checker_run_id: UUID
    logical_role: str
    source: CommittedArtifactSource


ArtifactAdmissionRequest: TypeAlias = (
    GuideArtifactAdmissionRequest
    | ContributorArtifactAdmissionRequest
    | CheckerOutputArtifactAdmissionRequest
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
class GuideSourceBindingAuthorityFacts:
    """Canonical verified guide lineage bound to one setup generation."""

    project_id: UUID
    guide_id: UUID
    guide_source_snapshot_id: UUID
    guide_source_item_id: UUID
    project_setup_run_id: UUID
    setup_generation: int
    content_id: UUID
    verified_replica_id: UUID
    sha256: str
    byte_count: int
    logical_role: str


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


@final
@dataclass(frozen=True, slots=True)
class ArtifactRecoveryAuthorityFacts:
    """Canonical facts bound to one exact Operator retry decision."""

    project_id: UUID
    task_id: UUID | None
    submission_id: UUID | None
    source_verification_job_id: UUID
    expected_source_job_cas_version: int


@final
@dataclass(frozen=True, slots=True)
class ArtifactRecoveryAuthorizationEvidence:
    """Privacy-bounded evidence returned by the AUTH-owned recovery seam."""

    action_id: ActionId
    permission_id: str
    decision_id: UUID


class ArtifactRecoveryAuthority(Protocol):
    """Fresh exact Operator authority seam owned by the later activation chunk."""

    async def authorize(
        self,
        *,
        authorization_context: AuthorizationContext,
        facts: ArtifactRecoveryAuthorityFacts,
    ) -> ArtifactRecoveryAuthorizationEvidence: ...


class DenyArtifactRecoveryAuthority:
    """Production-safe recovery authority until AUTH activates the Operator action."""

    async def authorize(
        self,
        *,
        authorization_context: AuthorizationContext,
        facts: ArtifactRecoveryAuthorityFacts,
    ) -> ArtifactRecoveryAuthorizationEvidence:
        del authorization_context, facts
        raise ArtifactAuthorityDeniedError("artifact recovery action is unavailable")


class ArtifactOperatorResourceType(StrEnum):
    """Closed resource vocabulary exposed to the AUTH activation adapter."""

    BINDING_SCOPE = "artifact_binding_scope"
    CONTENT = "artifact_content"
    REPLICA = "artifact_replica"
    VERIFICATION_JOB = "artifact_verification_job"
    RECOVERY_ATTEMPT = "artifact_recovery_attempt"
    AUDIT_RESOURCE = "artifact_audit_resource"
    ADMISSION_SCOPE = "artifact_admission_scope"


@final
@dataclass(frozen=True, slots=True)
class ArtifactOperatorAuthorityFacts:
    """Canonical, provider-neutral facts for one exact Operator decision."""

    resource_type: ArtifactOperatorResourceType
    resource_id: str
    project_ids: tuple[UUID, ...]
    action_id: ActionId


@final
@dataclass(frozen=True, slots=True)
class ArtifactOperatorAuthorizationEvidence:
    """Bounded evidence returned by the later AUTH activation adapter."""

    action_id: ActionId
    permission_id: str
    decision_id: UUID


class ArtifactOperatorAuthority(Protocol):
    """Exact Operator read authority seam; it never evaluates roles or grants."""

    async def authorize(
        self,
        *,
        authorization_context: AuthorizationContext,
        facts: ArtifactOperatorAuthorityFacts,
    ) -> ArtifactOperatorAuthorizationEvidence: ...


class DenyArtifactOperatorAuthority:
    """Production-safe authority while the Operator actions remain planned."""

    async def authorize(
        self,
        *,
        authorization_context: AuthorizationContext,
        facts: ArtifactOperatorAuthorityFacts,
    ) -> ArtifactOperatorAuthorizationEvidence:
        del authorization_context, facts
        raise ArtifactAuthorityDeniedError("artifact Operator action is unavailable")
