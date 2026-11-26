"""Send one private alert for current, committed contributor quality feedback."""

from collections.abc import Awaitable, Callable
from datetime import timedelta
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from workstream_external_services import ExternalServiceAdapterError

from app.interfaces.submission_feedback_email import (
    SubmissionFeedbackEmail, SubmissionFeedbackEmailAdapter, is_single_mailbox,
)
from app.modules.outbox.api import CommittedInvocationPort, HandlerOutcome, OutboxEventEnvelope
from app.modules.tasks.models import Submission, WorkstreamTask
from app.modules.tasks.post_submit_routing.models import TaskPostSubmitRoutingManifest
from app.modules.tasks.post_submit_routing.outcome import (
    FeedbackOutcome, routing_outcome_complete, submission_feedback_email_event,
)
from app.modules.tasks.revision.service import read_task_revision

SUBMISSION_FEEDBACK_EMAIL_LIFETIME = timedelta(hours=12)


class TaskSubmissionFeedbackEmailHandler:
    """Read an independently committed source before allowing any external effect."""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], *, observer: CommittedInvocationPort,
        recipient: Callable[[AsyncSession, UUID, UUID], Awaitable[str | None]],
        adapter: SubmissionFeedbackEmailAdapter,
    ) -> None:
        """Receive scoped recipient lookup and the typed transport from composition."""
        self._sessions, self._observer, self._recipient = sessions, observer, recipient
        self._adapter = adapter

    async def __call__(self, envelope: OutboxEventEnvelope) -> HandlerOutcome:
        """Stop at expiry and prevent foreign or obsolete effects before the HTTP call."""
        try:
            payload = json.loads(envelope.payload_json)
            manifest_id = UUID(payload["routing_manifest_id"])
            outcome = payload["outcome"]
        except (TypeError, ValueError, KeyError):
            return HandlerOutcome.REJECT
        if outcome not in ("needs_revision", "rejected"):
            return HandlerOutcome.REJECT
        observed = await self._observer.observe_invocation(envelope)
        if (observed is None or not envelope.occurred_at <= observed.observed_at
                < envelope.occurred_at + SUBMISSION_FEEDBACK_EMAIL_LIFETIME):
            return HandlerOutcome.REJECT
        async with self._sessions() as session:
            await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            manifest = await session.get(TaskPostSubmitRoutingManifest, manifest_id)
            if manifest is None or not _matches(envelope, payload, manifest, outcome):
                return HandlerOutcome.REJECT
            if not await _current_outcome(session, manifest, outcome):
                return HandlerOutcome.ACKNOWLEDGE
            recipient = await self._recipient(session, UUID(manifest.project_id), UUID(manifest.contributor_id))
            if recipient is None or not is_single_mailbox(recipient):
                return HandlerOutcome.ACKNOWLEDGE
            message = _message(envelope.claim.event_id, manifest, outcome, recipient)
        try:
            await self._adapter.send(message)
        except ExternalServiceAdapterError as error:
            return HandlerOutcome.RETRY if error.retryable else HandlerOutcome.REJECT
        return HandlerOutcome.ACKNOWLEDGE


def _matches(
    envelope: OutboxEventEnvelope, payload: dict, manifest: TaskPostSubmitRoutingManifest,
    outcome: FeedbackOutcome,
) -> bool:
    expected = submission_feedback_email_event(manifest, outcome)
    return (envelope.event_type == expected.event_type
            and envelope.event_version == expected.event_version
            and envelope.aggregate_type == expected.aggregate_type
            and envelope.aggregate_id == expected.aggregate_id
            and envelope.claim.project_id == expected.project_id
            and envelope.correlation_id == expected.correlation_id
            and envelope.causation_event_id == expected.causation_event_id
            and envelope.idempotency_key == expected.idempotency_key
            and payload == expected.payload)


async def _current_outcome(
    session: AsyncSession, manifest: TaskPostSubmitRoutingManifest, outcome: FeedbackOutcome,
) -> bool:
    """Reuse TASK's exact outcome closure and current revision projection."""
    if manifest.routing_recommendation != "needs_revision":
        return False
    latest = (await session.execute(select(
        Submission.id, Submission.attempt_status, Submission.status_reason,
    ).where(
        Submission.task_assignment_id == manifest.assignment_id,
    ).order_by(Submission.version.desc()).limit(1))).one_or_none()
    expected_reason = "revision_limit_reached" if outcome == "rejected" else None
    if (latest is None or latest.id != manifest.submission_id
            or latest.attempt_status != outcome or latest.status_reason != expected_reason):
        return False
    if not await routing_outcome_complete(session, manifest.id):
        return False
    if outcome == "rejected":
        return True
    task = (await session.execute(select(
        WorkstreamTask.status, WorkstreamTask.assigned_to, WorkstreamTask.active_submission_operation_id,
    ).where(WorkstreamTask.id == manifest.task_id))).one_or_none()
    if (task is None or task.assigned_to != manifest.contributor_id
            or task.active_submission_operation_id is not None):
        return False
    revision = await read_task_revision(
        session, task_id=manifest.task_id, status=task.status, assignment_id=manifest.assignment_id,
    )
    return revision is not None and revision.disposition in {"ready", "context_blocked"}


def _message(
    event_id: UUID, manifest: TaskPostSubmitRoutingManifest, outcome: FeedbackOutcome, recipient: str,
) -> SubmissionFeedbackEmail:
    if outcome == "needs_revision":
        subject = "Action required: Workstream submission feedback available"
        status = (f"Workstream assignment {manifest.assignment_id} needs revision. "
                  "Review the feedback, fix your submission and resubmit when the assignment allows it.")
    else:
        subject = "Workstream assignment reached its revision limit"
        status = (f"Workstream assignment {manifest.assignment_id} reached its revision limit. "
                  "Its submission was rejected.")
    hint = f"workstream task status {manifest.assignment_id}"
    return SubmissionFeedbackEmail(event_id, recipient, subject, (
        f"{status}\n\nRead your assignment feedback in Workstream using the API, CLI or MCP.\n\n"
        f"CLI: {hint}\n"
    ))
