"""Hidden composition for the TASK-owned admission-backed Submission command."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.api import (
    SubmissionAdmissionConsumptionPort,
    SubmissionAdmissionConsumptionRequest,
)
from app.modules.tasks.api import (
    SubmissionArtifactAdmissionRequest,
    SubmissionArtifactAdmissionResult,
    SubmissionCreationAuthorizationPort,
    SubmissionCreationAuthorityFacts,
    SubmissionCreationPreparationFacts,
    SubmissionCreationRequest,
    SubmissionCreationResult,
    SubmissionCreationUnavailable,
)
from app.modules.tasks.submission_composition import TaskSubmissionCreationService


class DenySubmissionCreationAuthorization:
    """Keep the hidden human action unavailable until AUTH activation."""

    async def authorize(self, facts: SubmissionCreationPreparationFacts) -> None:
        del facts
        raise SubmissionCreationUnavailable("submission creation is unavailable")

    async def consume(self, facts: SubmissionCreationAuthorityFacts) -> None:
        del facts
        raise SubmissionCreationUnavailable("submission creation is unavailable")


class _ArtifactAdmissionAdapter:
    def __init__(self, admissions: SubmissionAdmissionConsumptionPort) -> None:
        self._admissions = admissions

    async def consume(
        self, request: SubmissionArtifactAdmissionRequest
    ) -> SubmissionArtifactAdmissionResult:
        result = await self._admissions.consume(
            SubmissionAdmissionConsumptionRequest(
                admission_id=request.admission_id,
                submission_id=request.submission_id,
                submission_version=request.submission_version,
                task_context=request.task_context,
            )
        )
        if result.binding_id is None or result.status != "consumed":
            raise RuntimeError("admission did not produce a binding")
        return SubmissionArtifactAdmissionResult(
            binding_id=result.binding_id,
            content_id=result.content_id,
        )


class TransactionalSubmissionCreationCommand:
    """Open the sole root transaction and delegate sequencing to TASK."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        authorization: SubmissionCreationAuthorizationPort,
        admissions: SubmissionAdmissionConsumptionPort,
    ) -> None:
        self._session = session
        self._authorization = authorization
        self._admissions = admissions

    async def create(self, request: SubmissionCreationRequest) -> SubmissionCreationResult:
        if self._session.in_transaction():
            raise RuntimeError("submission composition requires a transaction-free session")
        async with self._session.begin():
            return await TaskSubmissionCreationService(
                self._session,
                authorization=self._authorization,
                admissions=_ArtifactAdmissionAdapter(self._admissions),
            ).create(request)
