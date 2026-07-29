"""Closed product capabilities owned by artifact orchestration."""

from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from app.modules.artifacts.sources import ArtifactCommitment, PreparedArtifact
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.authorization.runtime import AuthorizationContext

__all__ = (
    "ArtifactAuditResourceType",
    "ArtifactBindingResourceType",
    "ArtifactBindingPort",
    "ArtifactMaterializationPort",
    "ArtifactOperatorReadPort",
    "ArtifactOperatorRecoveryPort",
    "ArtifactRecoveryRequest",
    "BindingMaterializationRequest",
    "CheckerArtifactOutputPort",
    "CheckerOutputBindingRequest",
    "CheckerOutputArtifactRequest",
    "GuideArtifactIngestPort",
    "GuideArtifactIngestCommand",
    "GuideArtifactIngestRequest",
    "GuideArtifactIngestResult",
    "GuideSourceBindingRequest",
    "GuideSourceBindingResult",
    "PreparedBundleMaterializationRequest",
    "SubmissionBundlePreparationPort",
    "SubmissionBundlePreparationRequest",
    "SubmissionBindingRequest",
)

ArtifactBindingResourceType = Literal[
    "project",
    "project_guide",
    "guide_source_snapshot",
    "guide_source_snapshot_item",
    "task",
    "submission",
    "checker_run",
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
    """Prepared guide-source authority and canonical product ownership."""

    prepared_authorization: PreparedAuthorizationHandle
    project_id: UUID
    guide_id: UUID
    guide_source_snapshot_id: UUID
    source_item_id: UUID
    operation_identity: str
    request_digest: str
    logical_role: str
    media_type: str
    byte_source: AsyncIterable[bytes]


@dataclass(frozen=True, slots=True)
class GuideArtifactIngestResult:
    """Durable identity returned without exposing provider coordinates."""

    put_attempt_id: UUID
    operation_identity: str
    sha256: str
    byte_count: int
    status: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class GuideSourceBindingRequest:
    """Verified guide content and its exact setup-generation owner."""

    prepared_authorization: PreparedAuthorizationHandle
    project_id: UUID
    guide_id: UUID
    guide_source_snapshot_id: UUID
    source_item_id: UUID
    project_setup_run_id: UUID
    setup_generation: int
    logical_role: str
    verified_content_id: UUID


@dataclass(frozen=True, slots=True)
class GuideSourceBindingResult:
    """One immutable authoritative guide-source binding."""

    binding_id: UUID
    content_id: UUID
    setup_generation: int
    replayed: bool


@dataclass(frozen=True, slots=True)
class SubmissionBindingRequest:
    """Verified contributor content and its exact Submission owner."""

    prepared_authorization: PreparedAuthorizationHandle
    project_id: UUID
    task_id: UUID
    submission_id: UUID
    logical_role: str
    verified_content_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class CheckerOutputBindingRequest:
    """Verified checker output and its exact CheckerRun owner."""

    prepared_authorization: PreparedAuthorizationHandle
    project_id: UUID
    task_id: UUID
    submission_id: UUID
    checker_run_id: UUID
    logical_role: str
    verified_content_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class SubmissionBundlePreparationRequest:
    """One prepared contributor authority and continuous outer ZIP source."""

    prepared_authorization: PreparedAuthorizationHandle
    task_id: UUID
    assignment_id: UUID
    byte_source: AsyncIterable[bytes]
    client_commitment: ArtifactCommitment | None = None


@dataclass(frozen=True, slots=True)
class PreparedBundleMaterializationRequest:
    """Process-local prepared bytes and exact policy selectors."""

    prepared_authorization: PreparedAuthorizationHandle
    task_id: UUID
    assignment_id: UUID
    submission_artifact_policy_id: UUID
    checker_policy_id: UUID
    prepared_artifact: PreparedArtifact


@dataclass(frozen=True, slots=True)
class BindingMaterializationRequest:
    """Immutable bindings selected by exact execution context."""

    prepared_authorization: PreparedAuthorizationHandle
    task_id: UUID
    submission_id: UUID | None
    checker_run_id: UUID
    binding_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class CheckerOutputArtifactRequest:
    """Generated checker bytes bound to one fixed service execution."""

    prepared_authorization: PreparedAuthorizationHandle
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
    task_id: UUID | None
    submission_id: UUID | None
    source_verification_job_id: UUID
    reason: str
    client_idempotency_key: str
    expected_source_job_cas_version: int


class GuideArtifactIngestPort(Protocol):
    """Ingest authorized guide bytes without exposing provider operations."""

    async def ingest(self, request: GuideArtifactIngestRequest) -> GuideArtifactIngestResult:
        """Ingest one canonical guide source item."""


class GuideArtifactIngestCommand(Protocol):
    """Route-facing preflight that owns one request-local PREP lifecycle."""

    async def ingest(
        self,
        *,
        authorization_context: AuthorizationContext,
        project_id: UUID,
        guide_id: UUID,
        guide_source_snapshot_id: UUID,
        source_item_id: UUID,
        idempotency_key: UUID,
        byte_source: AsyncIterable[bytes],
    ) -> GuideArtifactIngestResult:
        """Prepare authority before delegating to durable byte ingestion."""


class SubmissionBundlePreparationPort(Protocol):
    """Prepare one continuous contributor bundle without upload sessions."""

    async def prepare(self, request: SubmissionBundlePreparationRequest) -> object:
        """Prepare one authorized outer ZIP in bounded private scratch."""


class ArtifactBindingPort(Protocol):
    """Create exact action-bound bindings from verified content."""

    async def bind_guide_source(self, request: GuideSourceBindingRequest) -> GuideSourceBindingResult:
        """Bind verified guide content under the guide binding action."""

    async def bind_submission(self, request: SubmissionBindingRequest) -> object:
        """Bind verified submission content under the submission binding action."""

    async def bind_checker_output(self, request: CheckerOutputBindingRequest) -> object:
        """Bind verified checker output under the checker binding action."""


class ArtifactMaterializationPort(Protocol):
    """Materialize only the two canonical immutable source forms."""

    async def materialize_prepared_bundle(
        self,
        request: PreparedBundleMaterializationRequest,
    ) -> object:
        """Materialize one process-local prepared bundle generation."""

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
