"""Hidden evidence-bound durable put handoff for one checked submission ZIP."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.pre_submit_evidence import PreSubmitPassCapability
from app.modules.artifacts.schemas import (
    ArtifactAdmissionResult,
    SubmissionBundleArtifactAdmissionRequest,
)
from app.modules.artifacts.submission_authorization import (
    SubmissionBundlePreparedAuthorization,
)
from app.modules.artifacts.service import (
    ArtifactAdmissionService,
    ArtifactStorageOrchestrator,
)
from app.modules.artifacts.sources import PreparedArtifact
from app.modules.artifacts.submission_custody import SubmissionBundlePreparedCustody
from app.modules.authorization.prepared import PreparedAuthorizationHandle


@dataclass(frozen=True, slots=True)
class SubmissionBundleDurablePutRequest:
    """Exact live custody and opaque authority for one final durable handoff."""

    prepared_authorization: PreparedAuthorizationHandle
    prepared_artifact: PreparedArtifact
    pass_capability: PreSubmitPassCapability
    replay_durable_intent_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SubmissionBundleDurablePutResult:
    """Bounded durable operation result without provider coordinates."""

    put_attempt_id: UUID
    pre_submit_evidence_set_id: UUID
    operation_identity: str
    status: str
    replayed: bool


class SubmissionBundleDurablePutService:
    """Commit final authority and intent before invoking the generic provider path."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        admission: ArtifactAdmissionService,
        storage: ArtifactStorageOrchestrator,
        authorization: SubmissionBundlePreparedAuthorization,
    ) -> None:
        self._session = session
        self._admission = admission
        self._storage = storage
        self._authorization = authorization

    async def admit_in_transaction(
        self,
        request: SubmissionBundleDurablePutRequest,
    ) -> tuple[PreparedArtifact, UUID, ArtifactAdmissionResult]:
        """Consume live custody and persist the complete intent in the caller transaction."""
        if type(request) is not SubmissionBundleDurablePutRequest:
            raise TypeError("invalid submission bundle durable put request")
        transaction = self._session.sync_session.get_transaction()
        prepared = request.prepared_artifact
        if (
            transaction is None
            or not transaction.is_active
            or self._session.in_nested_transaction()
            or type(request.prepared_authorization) is not PreparedAuthorizationHandle
            or type(prepared) is not PreparedArtifact
            or type(request.pass_capability) is not PreSubmitPassCapability
        ):
            if type(prepared) is PreparedArtifact:
                await prepared.close()
            raise RuntimeError("submission bundle durable transaction is unavailable")
        try:
            evidence_set_id = request.pass_capability.evidence_set_id
            custody = SubmissionBundlePreparedCustody._from_live_preparation(
                prepared=prepared,
                capability=request.pass_capability,
            )
            admission = await self._admission.admit(
                SubmissionBundleArtifactAdmissionRequest(
                    pre_submit_evidence_set_id=evidence_set_id,
                    custody=custody,
                    replay_durable_intent_id=request.replay_durable_intent_id,
                ),
                submission_prepared_authorization=self._authorization,
                prepared_authorization=request.prepared_authorization,
                existing_transaction=True,
            )
            return prepared, evidence_set_id, admission
        except BaseException:
            await prepared.close()
            raise

    async def publish_after_commit(
        self,
        prepared: PreparedArtifact,
        evidence_set_id: UUID,
        admission: ArtifactAdmissionResult,
    ) -> SubmissionBundleDurablePutResult:
        """Hand the exact ZIP to storage only after the durable transaction ended."""
        if self._session.in_transaction():
            await prepared.close()
            raise RuntimeError("submission bundle durable transaction is still active")
        try:
            if admission.replayed:
                status = await self._storage.resume_committed_put(
                    attempt_id=admission.attempt_id,
                    source=prepared.committed_source,
                )
            else:
                status = await self._storage.execute_committed_put(
                    attempt_id=admission.attempt_id,
                    source=prepared.committed_source,
                )
            return SubmissionBundleDurablePutResult(
                put_attempt_id=admission.attempt_id,
                pre_submit_evidence_set_id=evidence_set_id,
                operation_identity=admission.operation_identity,
                status=status,
                replayed=admission.replayed,
            )
        finally:
            await prepared.close()
