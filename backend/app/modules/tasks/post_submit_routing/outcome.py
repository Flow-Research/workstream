"""One flush-only governed outcome; callers own commit and delivery acknowledgement."""

import json
from contextlib import AsyncExitStack
from uuid import UUID

from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import COMPLETION_EVENT, EvaluationCompletion
from app.modules.outbox.api import OutboxAppendInput, OutboxEventEnvelope
from app.modules.tasks.api.accepted_effects import TaskAcceptedEffectsRequest
from app.modules.tasks.models import WorkstreamTask
from app.modules.tasks.post_submit_routing.models import TaskPostSubmitRoutingManifest
from app.modules.tasks.api.routing_outcome import RoutingAuthorityFacts
from app.modules.tasks.post_submit_routing.requests import (
    TaskRoutingRequestUnavailable,
    require_routing_transaction,
)
from app.modules.tasks.post_submit_routing.source import TaskRoutingSourcePreparer

OUTCOME_EVENT = "TaskPostSubmitRouted"


class TaskPostSubmitOutcome:
    """Bind current completion, fresh AUTH and all consequences in one root transaction."""

    def __init__(
        self,
        session,
        *,
        projects,
        evaluations,
        authorization,
        acceptance,
        observer,
        invocation_fence,
        audit,
        outbox,
    ):
        """Inject existing owner ports into one caller-owned transaction."""
        self._session, self._projects = session, projects
        self._source = TaskRoutingSourcePreparer(
            session, projects=projects, evaluations=evaluations
        )
        self._authorization, self._acceptance = authorization, acceptance
        self._observer, self._invocation_fence = observer, invocation_fence
        self._audit, self._outbox = audit, outbox

    async def apply(self, envelope: OutboxEventEnvelope, *, current_generation: int | None):
        """Return durable identities only after staging complete new or exact replay facts."""
        await require_routing_transaction(self._session)
        envelope = OutboxEventEnvelope.model_validate(envelope)
        completion = EvaluationCompletion.model_validate_json(envelope.payload_json)
        if (
            envelope.event_type != COMPLETION_EVENT
            or envelope.event_version != 1
            or envelope.aggregate_type != "checker_run"
            or envelope.aggregate_id != completion.reference.attempt_id
            or envelope.claim.project_id != completion.project_id
            or completion.routing_recommendation != "allow_review"
            or await self._observer.observe_invocation(envelope) is None
        ):
            raise TaskRoutingRequestUnavailable("routing invocation unavailable")
        # This observation grants nothing. It selects lock order, and the complete
        # source is revalidated after acquiring that order's mutation custody.
        with self._session.no_autoflush:
            policy_id = await self._session.scalar(
                select(WorkstreamTask.locked_review_policy_id).where(
                    WorkstreamTask.id == str(completion.task_id),
                    WorkstreamTask.project_id == str(completion.project_id),
                )
            )
            human = (
                await self._projects.observe_review_mode(completion.project_id, UUID(policy_id))
                if policy_id is not None
                else None
            )
        if type(human) is not bool or ((current_generation is None) != human):
            raise TaskRoutingRequestUnavailable("routing branch unavailable")
        async with AsyncExitStack() as stack:
            acceptance = None
            if not human:
                acceptance = await stack.enter_async_context(
                    self._acceptance.prepare(current_generation)
                )
            source = await self._source.prepare(envelope.claim.event_id, completion)
            if source.source.human_review_required is not human:
                raise TaskRoutingRequestUnavailable("routing branch changed")
            stored = await self._session.get(
                TaskPostSubmitRoutingManifest, source.source.id, populate_existing=True
            )
            replay = stored is not None
            if acceptance is not None and not replay:
                await acceptance.require_new()
            authorized_generation = (
                stored.authorized_lifecycle_generation if replay else current_generation
            )
            acceptance_id = (
                stored.final_acceptance_id if replay else (None if human else new_record_id())
            )
            effects = (
                None
                if human
                else TaskAcceptedEffectsRequest(
                    **source.source.model_dump(
                        include={
                            "project_id",
                            "task_id",
                            "assignment_id",
                            "submission_id",
                            "submission_version",
                            "contributor_id",
                            "contribution_policy_version_id",
                            "content_id",
                            "content_sha256",
                        }
                    ),
                    final_acceptance_id=acceptance_id,
                    expected_task_status="evaluation_pending",
                )
            )
            if human != (acceptance_id is None) or human != (authorized_generation is None):
                raise TaskRoutingRequestUnavailable("routing retained consequence unavailable")
            authority = await stack.enter_async_context(self._authorization.prepare(source.request))
            if await self._invocation_fence.fence_invocation(envelope) is None:
                raise TaskRoutingRequestUnavailable("routing invocation changed")
            if replay:
                receipt = RoutingAuthorityFacts(
                    decision_id=UUID(stored.authorization_decision_id),
                    actor_id=UUID(stored.router_actor_id),
                    identity_link_id=UUID(stored.router_identity_link_id),
                    context_json=json.dumps(stored.authority_context),
                )
                await authority.validate_replay(source, receipt, effects, authorized_generation)
            else:
                receipt = await authority.consume(
                    source, envelope.claim, effects, authorized_generation
                )
            audit_id = UUID(stored.audit_event_id) if replay else new_record_id()
            if replay:
                await self._outbox.require_existing(
                    stored.outcome_event_id, _notice(source, receipt, acceptance_id)
                )
            else:
                event = await self._append_notice(source, receipt, acceptance_id)
                stored = _manifest(source, receipt, acceptance_id, authorized_generation, audit_id)
                stored.outcome_event_id = event.event_id
                self._session.add(stored)
                await self._session.flush()
            economic = None
            if human:
                task = await self._session.get(WorkstreamTask, str(source.source.task_id))
                if not replay:
                    task.status = "review_pending"
            else:
                economic = await acceptance.participate(
                    source, effects, receipt, authorized_generation
                )
            await self._audit.record(
                audit_event_id=audit_id,
                source=source,
                authority=receipt,
                economic=economic,
                replay=replay,
            )
            await self._session.flush()
            return {
                "routing_manifest_id": stored.id,
                "authorization_decision_id": receipt.decision_id,
                "outcome_event_id": stored.outcome_event_id,
                "final_acceptance_id": acceptance_id,
                "economic": economic,
                "replayed": replay,
            }

    async def _append_notice(self, source, receipt, acceptance_id):
        """Stage the outcome notice without autoflushing an incomplete manifest."""
        # Outbox's explicit append avoids ORM autoflush before its ID is known.
        with self._session.no_autoflush:
            return await self._outbox.append(_notice(source, receipt, acceptance_id))


def _notice(source, receipt, acceptance_id):
    """Build the bounded shared outbox consequence from exact source and authority."""
    return OutboxAppendInput(
        event_type=OUTCOME_EVENT,
        event_version=1,
        aggregate_type="task",
        aggregate_id=source.source.task_id,
        project_id=source.source.project_id,
        correlation_id=str(source.request.route_operation_id),
        causation_event_id=source.source.completion_event_id,
        idempotency_key="task-routed:" + str(source.source.id),
        payload={
            "routing_manifest_id": str(source.source.id),
            "task_id": str(source.source.task_id),
            "submission_id": str(source.source.submission_id),
            "authorization_decision_id": str(receipt.decision_id),
            "human_review_required": source.source.human_review_required,
            "final_acceptance_id": str(acceptance_id) if acceptance_id else None,
        },
    )


def _manifest(source, receipt, acceptance_id, generation, audit_id):
    """Bind the source to actual authority and consequence using owner column types."""
    columns = set(TaskPostSubmitRoutingManifest.__table__.columns.keys())
    fields = source.source.model_dump(include=columns)
    # Existing owner columns deliberately store strings at their Python boundary.
    for key, column in TaskPostSubmitRoutingManifest.__table__.columns.items():
        if (
            key in fields
            and isinstance(fields[key], UUID)
            and getattr(column.type, "as_uuid", True) is False
        ):
            fields[key] = str(fields[key])
    return TaskPostSubmitRoutingManifest(
        **fields,
        authorization_decision_id=str(receipt.decision_id),
        router_actor_id=str(receipt.actor_id),
        router_identity_link_id=str(receipt.identity_link_id),
        authority_context=json.loads(receipt.context_json),
        final_acceptance_id=acceptance_id,
        authorized_lifecycle_generation=generation,
        audit_event_id=str(audit_id),
    )
