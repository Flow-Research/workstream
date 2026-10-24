"""Project exact immutable CHECKERS findings without taking a historical fence."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from app.modules.checkers.api.revision_feedback import (
    RevisionFeedback,
    RevisionFeedbackMember,
    RevisionFeedbackRequest,
)
from app.modules.checkers.execution_repository import (
    require_transaction,
    stored_request,
    stored_result,
)
from app.modules.checkers.models import CheckerRun


class RevisionFeedbackReader:
    """Read complete evidence; the caller separately establishes current byte authority."""

    def __init__(self, session: AsyncSession) -> None:
        """Retain the caller-owned short transaction, never commit it."""
        self._session = session

    async def read(self, request: RevisionFeedbackRequest) -> RevisionFeedback:
        """Fail closed on source substitution, malformed retained data or excess size."""
        require_transaction(self._session)
        try:
            request = RevisionFeedbackRequest.model_validate(request)
            return await self._read(request)
        except (ValueError, TypeError, AttributeError, KeyError):
            raise CheckerExecutionUnavailable("revision_feedback_unavailable") from None

    async def _read(self, selector: RevisionFeedbackRequest) -> RevisionFeedback:
        """Bind the historical completion and its selected-policy member order."""
        reference = selector.result
        run = await self._session.scalar(
            select(CheckerRun)
            .where(
                CheckerRun.id == str(reference.attempt_id),
                CheckerRun.project_id == str(selector.project_id),
                CheckerRun.task_id == str(selector.task_id),
                CheckerRun.submission_id == str(selector.submission_id),
                CheckerRun.submission_version == selector.submission_version,
                CheckerRun.evaluation_request_id == str(reference.request_id),
                CheckerRun.request_digest == reference.request_digest,
                CheckerRun.evaluation_generation == reference.evaluation_generation,
                CheckerRun.result_id == str(reference.result_id),
                CheckerRun.result_digest == reference.result_digest,
                CheckerRun.completion_event_id == selector.completion_event_id,
                CheckerRun.status == "completed",
                CheckerRun.routing_recommendation == "needs_revision",
            )
            .execution_options(populate_existing=True)
        )
        if run is None:
            raise CheckerExecutionUnavailable("revision_feedback_unavailable")
        request = stored_request(run)
        result = stored_result(run)
        reference.validate_result(result)
        if (
            request.assignment_id != selector.assignment_id
            or request.project_id != selector.project_id
            or request.task_id != selector.task_id
            or request.submission_id != selector.submission_id
            or request.submission_version != selector.submission_version
            or result.execution is None
        ):
            raise CheckerExecutionUnavailable("revision_feedback_unavailable")
        return RevisionFeedback(
            source=selector,
            policy_sha256=request.policy.policy_sha256,
            members=tuple(
                RevisionFeedbackMember(
                    order=member.order,
                    requirement_id=member.requirement_id,
                    registry_entry_id=member.registry_entry_id,
                    registry_entry_digest=member.registry_entry_digest,
                    configuration_sha256=binding.configuration_sha256,
                    request_digest=member.request_digest,
                    result_digest=member.result.result_digest,
                    verdict=member.result.verdict,
                    findings=member.result.findings,
                )
                for binding, member in zip(
                    request.policy.entries, result.execution.external_members, strict=True
                )
            ),
        )
