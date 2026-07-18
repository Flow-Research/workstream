"""Closed product capabilities owned by artifact orchestration."""

from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from app.modules.artifacts.sources import ArtifactCommitment
from app.modules.authorization.runtime import AuthorizationContext

__all__ = (
    "ArtifactAuditResourceType",
    "ArtifactBindingResourceType",
    "ArtifactBindingCreateRequest",
    "ArtifactBindingPort",
    "ArtifactMaterializationPort",
    "ArtifactOperatorReadPort",
    "ArtifactOperatorRecoveryPort",
    "ArtifactRecoveryRequest",
    "BindingMaterializationRequest",
    "CheckerArtifactOutputPort",
    "CheckerOutputArtifactRequest",
    "ContributorArtifactUploadPort",
    "GuideArtifactIngestPort",
    "GuideArtifactIngestRequest",
    "ReadyUploadSetRequest",
)

ArtifactBindingResourceType = Literal[
    "project",
    "project_guide",
    "guide_source_snapshot",
    "guide_source_snapshot_item",
    "task",
    "submission",
    "checker_run",
    "review",
]
ArtifactAuditResourceType = Literal[
    "artifact_binding",
    "artifact_content",
    "artifact_replica",
    "artifact_receipt",
    "artifact_verification_job",
    "artifact_recovery_attempt",
]


@dataclass(frozen=True, slots=True)
class GuideArtifactIngestRequest:
    """Authorized guide-source bytes and their canonical product ownership."""

    authorization_context: AuthorizationContext
    project_id: UUID
    guide_source_snapshot_id: UUID
    source_item_id: UUID
    logical_role: str
    byte_source: AsyncIterable[bytes]
    client_commitment: ArtifactCommitment | None = None


@dataclass(frozen=True, slots=True)
class ArtifactBindingCreateRequest:
    """Verified content and exact product facts for immutable binding."""

    authorization_context: AuthorizationContext
    project_id: UUID
    task_id: UUID
    submission_id: UUID | None
    checker_run_id: UUID | None
    logical_role: str
    verified_content_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ReadyUploadSetRequest:
    """One sealed upload set and its locked task policy context."""

    authorization_context: AuthorizationContext
    task_id: UUID
    sealed_upload_session_id: UUID
    submission_artifact_policy_id: UUID
    checker_policy_id: UUID


@dataclass(frozen=True, slots=True)
class BindingMaterializationRequest:
    """Immutable bindings selected by exact execution context."""

    authorization_context: AuthorizationContext
    task_id: UUID
    submission_id: UUID | None
    checker_run_id: UUID
    binding_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class CheckerOutputArtifactRequest:
    """Generated checker bytes bound to one fixed service execution."""

    service_actor_context: AuthorizationContext
    task_id: UUID
    submission_id: UUID
    checker_run_id: UUID
    logical_role: str
    byte_source: AsyncIterable[bytes]


@dataclass(frozen=True, slots=True)
class ArtifactRecoveryRequest:
    """Reason-bound Operator retry of one exact verification job."""

    authorization_context: AuthorizationContext
    project_id: UUID
    task_id: UUID
    submission_id: UUID | None
    source_verification_job_id: UUID
    reason: str
    client_idempotency_key: str
    expected_source_job_cas_version: int


class GuideArtifactIngestPort(Protocol):
    """Ingest authorized guide bytes without exposing provider operations."""

    async def ingest(self, request: GuideArtifactIngestRequest) -> object:
        """Ingest one canonical guide source item."""


class ContributorArtifactUploadPort(Protocol):
    """Own the closed contributor upload-session lifecycle."""

    async def create(
        self,
        *,
        authorization_context: AuthorizationContext,
        task_id: UUID,
    ) -> object:
        """Create one authorized task upload session."""

    async def read(
        self,
        *,
        authorization_context: AuthorizationContext,
        task_id: UUID,
        upload_session_id: UUID,
    ) -> object:
        """Read one authorized upload session."""

    async def write(
        self,
        *,
        authorization_context: AuthorizationContext,
        task_id: UUID,
        upload_session_id: UUID,
        logical_role: str,
        byte_source: AsyncIterable[bytes],
        client_commitment: ArtifactCommitment | None = None,
    ) -> object:
        """Write one bounded item through artifact orchestration."""

    async def seal(
        self,
        *,
        authorization_context: AuthorizationContext,
        task_id: UUID,
        upload_session_id: UUID,
    ) -> object:
        """Seal one exact upload set."""

    async def cancel(
        self,
        *,
        authorization_context: AuthorizationContext,
        task_id: UUID,
        upload_session_id: UUID,
    ) -> None:
        """Cancel one unsealed upload session."""


class ArtifactBindingPort(Protocol):
    """Create bindings only from orchestrator-verified content."""

    async def bind_verified(self, request: ArtifactBindingCreateRequest) -> object:
        """Bind exact verified content to canonical product facts."""


class ArtifactMaterializationPort(Protocol):
    """Materialize only the two canonical immutable source forms."""

    async def materialize_ready_upload_set(
        self,
        request: ReadyUploadSetRequest,
    ) -> object:
        """Materialize one sealed upload set whose items are ready."""

    async def materialize_bindings(
        self,
        request: BindingMaterializationRequest,
    ) -> object:
        """Materialize exact immutable binding IDs."""


class CheckerArtifactOutputPort(Protocol):
    """Store generated output for one fixed checker execution."""

    async def store(self, request: CheckerOutputArtifactRequest) -> object:
        """Store one generated checker artifact."""


class ArtifactOperatorReadPort(Protocol):
    """Expose bounded Operator reads without provider references."""

    async def list_bindings(
        self,
        *,
        authorization_context: AuthorizationContext,
        resource_type: ArtifactBindingResourceType,
        resource_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> object:
        """List bindings for one exact canonical product resource."""

    async def list_replicas(
        self,
        *,
        authorization_context: AuthorizationContext,
        content_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> object:
        """List replicas for one exact Workstream content identity."""

    async def list_receipts(
        self,
        *,
        authorization_context: AuthorizationContext,
        replica_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> object:
        """List receipts for one exact Workstream replica identity."""

    async def get_verification_job(
        self,
        *,
        authorization_context: AuthorizationContext,
        verification_job_id: UUID,
    ) -> object:
        """Read one exact verification job."""

    async def get_recovery_attempt(
        self,
        *,
        authorization_context: AuthorizationContext,
        recovery_attempt_id: UUID,
    ) -> object:
        """Read one exact recovery attempt."""

    async def list_audit_events(
        self,
        *,
        authorization_context: AuthorizationContext,
        resource_type: ArtifactAuditResourceType,
        resource_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> object:
        """List bounded artifact audit events for one exact resource."""

    async def admission_usage(
        self,
        *,
        authorization_context: AuthorizationContext,
        project_id: UUID | None,
        task_id: UUID | None,
        cursor: str | None,
        limit: int,
    ) -> object:
        """Read bounded reserved/completed byte usage and configured limits."""


class ArtifactOperatorRecoveryPort(Protocol):
    """Expose only reason-bound verification retry to Operators."""

    async def retry_verification(self, request: ArtifactRecoveryRequest) -> object:
        """Retry one exact source verification job under CAS fencing."""
