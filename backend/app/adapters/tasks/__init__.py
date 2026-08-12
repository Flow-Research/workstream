"""TASK-owned composition adapters."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.api import SubmissionAdmissionConsumptionPort
from app.modules.tasks.api import (
    SubmissionArtifactAdmissionRequest,
    SubmissionArtifactAdmissionResult,
    SubmissionCreationAuthorizationPort,
    SubmissionCreationRequest,
    SubmissionCreationResult,
    TaskSubmissionContextPort,
)
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.submission_composition import TaskSubmissionCreationService
from app.adapters.tasks.submission_composition import (
    DenySubmissionCreationAuthorization,
)

__all__ = (
    "DenySubmissionCreationAuthorization",
    "TransactionalSubmissionCreationCommand",
    "task_submission_context_port",
)


def task_submission_context_port(session: AsyncSession) -> TaskSubmissionContextPort:
    """Bind the public TASK submission-context port to its repository."""
    return TaskRepository(session)


class TransactionalSubmissionCreationCommand:
    """Open the sole root transaction and delegate lifecycle sequencing to TASK."""

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
        """Commit once only after TASK and ART participants succeed."""
        if self._session.in_transaction():
            raise RuntimeError("submission composition requires a transaction-free session")
        async with self._session.begin():
            class ArtifactAdmissionAdapter:
                async def consume(
                    _self, request: SubmissionArtifactAdmissionRequest
                ) -> SubmissionArtifactAdmissionResult:
                    from app.modules.artifacts.api import SubmissionAdmissionConsumptionRequest

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

            return await TaskSubmissionCreationService(
                self._session,
                authorization=self._authorization,
                admissions=ArtifactAdmissionAdapter(),
            ).create(request)
