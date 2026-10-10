"""Hidden completion delivery; shared OUTBOX alone owns retry and finalization."""

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.checkers.api.execution import COMPLETION_EVENT, EvaluationCompletion
from app.modules.outbox.api import CommittedInvocationPort, HandlerOutcome, OutboxEventEnvelope
from app.modules.tasks.api.routing_outcome import TaskRoutingOutcome
from app.modules.tasks.post_submit_routing.outcome import TaskPostSubmitOutcome
from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequestUnavailable


class EvaluationCompletionHandler:
    """Commit one existing authorized outcome before acknowledging delivery."""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], *,
        observer: CommittedInvocationPort,
        outcomes: Callable[[AsyncSession], TaskPostSubmitOutcome],
    ):
        self._sessions, self._observer, self._outcomes = sessions, observer, outcomes

    async def __call__(self, envelope: OutboxEventEnvelope) -> HandlerOutcome:
        """Reject intrinsic invalidity; uncertain owner effects propagate to UNKNOWN."""
        try:
            envelope = OutboxEventEnvelope.model_validate(envelope.model_dump())
            completion = EvaluationCompletion.model_validate_json(envelope.payload_json)
        except (AttributeError, TypeError, ValueError):
            return HandlerOutcome.REJECT
        if (
            envelope.event_type != COMPLETION_EVENT
            or envelope.event_version != 1
            or envelope.aggregate_type != "checker_run"
            or envelope.aggregate_id != completion.reference.attempt_id
            or envelope.claim.project_id != completion.project_id
            or completion.routing_recommendation != "allow_review"
        ):
            return HandlerOutcome.REJECT
        observed = await self._observer.observe_invocation(envelope)
        if observed is None or observed.claim != envelope.claim:
            return HandlerOutcome.REJECT
        async with self._sessions() as session, session.begin():
            operation = self._outcomes(session)
            generation = await operation.observe_delivery_generation(envelope)
            staged = await operation.apply(envelope, current_generation=generation)
            result = TaskRoutingOutcome.model_validate(staged.model_dump())
            if (
                result.project_id, result.task_id, result.submission_id, result.completion_event_id
            ) != (
                completion.project_id, completion.task_id, completion.submission_id,
                envelope.claim.event_id,
            ) or ((result.final_acceptance_id is None) != (generation is None)):
                raise TaskRoutingRequestUnavailable("routing outcome identity differs")
        # Context exit includes deferred constraints and the actual root commit.
        return HandlerOutcome.ACKNOWLEDGE
