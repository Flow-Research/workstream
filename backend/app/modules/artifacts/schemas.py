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

    authorization_context: AuthorizationContext
    guide_source_item_id: UUID
    source: CommittedArtifactSource


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


ArtifactInternalAuthorityFacts: TypeAlias = (
    ArtifactPutAttemptAuthorityFacts
    | ArtifactVerificationAuthorityFacts
    | ArtifactPendingWorkAuthorityFacts
)


class ArtifactInternalAuthority(Protocol):
    """Two-phase authority seam owned by AUTH activation."""

    async def preflight(
        self,
        *,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        facts: ArtifactInternalAuthorityFacts,
    ) -> None: ...

    async def revalidate_terminal(
        self,
        *,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        facts: ArtifactInternalAuthorityFacts,
    ) -> None: ...


class DenyArtifactInternalAuthority:
    """Production-safe seam until AUTH activates exact artifact actions."""

    async def preflight(
        self,
        *,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        facts: ArtifactInternalAuthorityFacts,
    ) -> None:
        del service_identity, action_id, facts
        raise ArtifactAuthorityDeniedError("artifact internal action is unavailable")

    async def revalidate_terminal(
        self,
        *,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        facts: ArtifactInternalAuthorityFacts,
    ) -> None:
        del service_identity, action_id, facts
        raise ArtifactAuthorityDeniedError("artifact internal action is unavailable")


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
