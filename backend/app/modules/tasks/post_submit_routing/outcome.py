"""One flush-only governed outcome; callers own commit and delivery acknowledgement."""

import json
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from uuid import UUID

from sqlalchemy import select, text

from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import COMPLETION_EVENT, EvaluationCompletion
from app.modules.outbox.api import OutboxAppendInput, OutboxClaim, OutboxEventEnvelope
from app.modules.tasks.api.accepted_effects import TaskAcceptedEffectsRequest
from app.modules.tasks.models import Submission, WorkstreamTask
from app.modules.tasks.submission_attempts import record_attempt_outcome
from app.modules.tasks.revision.service import prepare_revision
from app.modules.tasks.revision.expiry_event import revision_preparation_event
from app.modules.tasks.revision.models import TaskRevisionPreparation
from app.modules.tasks.revision.exhaustion import exhaust_assignment
from app.modules.tasks.post_submit_routing.models import TaskPostSubmitRoutingManifest
from app.modules.tasks.api.routing_outcome import RoutingAuthorityFacts, TaskRoutingOutcome
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
        rewards,
        evaluations,
        authorization,
        acceptance,
        observer,
        invocation_fence,
        audit,
        outbox,
        reconciliation_claim: Callable[[], Awaitable[OutboxClaim]] | None = None,
    ):
        """Inject existing owner ports into one caller-owned transaction."""
        self._session, self._projects = session, projects
        self._source = TaskRoutingSourcePreparer(
            session, projects=projects, rewards=rewards, evaluations=evaluations
        )
        self._authorization, self._acceptance = authorization, acceptance
        self._observer, self._invocation_fence = observer, invocation_fence
        self._audit, self._outbox = audit, outbox
        self._reconciliation_claim = reconciliation_claim

    async def apply(self, envelope: OutboxEventEnvelope, *, current_generation: int | None) -> TaskRoutingOutcome:
        """Return durable identities only after staging complete new or exact replay facts."""
        await require_routing_transaction(self._session)
        envelope, completion = self._completion(envelope)
        if await self._observer.observe_invocation(envelope) is None:
            raise TaskRoutingRequestUnavailable("routing invocation unavailable")
        human = await self._observe_review_mode(completion)
        accepts = completion.routing_recommendation == "allow_review" and not human
        if accepts != (current_generation is not None):
            raise TaskRoutingRequestUnavailable("routing branch unavailable")
        async with AsyncExitStack() as stack:
            acceptance = None
            if accepts:
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
            acceptance_id = stored.final_acceptance_id if replay else (
                new_record_id() if accepts else None
            )
            effects = (
                TaskAcceptedEffectsRequest(
                    **source.source.model_dump(
                        include={
                            "project_id",
                            "task_id",
                            "assignment_id",
                            "submission_id",
                            "submission_version",
                            "contributor_id",
                            "contribution_policy_version_id", "task_size", "contribution_award_definition_id",
                            "content_id",
                            "content_sha256",
                        }
                    ),
                    final_acceptance_id=acceptance_id,
                    expected_task_status="evaluation_pending",
                )
                if accepts
                else None
            )
            if accepts != (acceptance_id is not None) or accepts != (
                authorized_generation is not None
            ):
                raise TaskRoutingRequestUnavailable("routing retained consequence unavailable")
            authority = await stack.enter_async_context(self._authorization.prepare(source.request))
            effect_claim = envelope.claim
            if self._reconciliation_claim is not None:
                effect_claim = OutboxClaim.model_validate(
                    await self._reconciliation_claim()
                )
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
                    source,
                    envelope.claim,
                    effects,
                    authorized_generation,
                    reconciliation_claim=(
                        effect_claim if effect_claim != envelope.claim else None
                    ),
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
            if source.source.routing_recommendation == "needs_revision":
                task = await self._session.get(WorkstreamTask, str(source.source.task_id))
                if source.exhaustion is not None:
                    await exhaust_assignment(self._session, manifest=stored, source=source, replay=replay)
                elif not replay:
                    task.status = "needs_revision"
                    await self._session.flush()
                    await record_attempt_outcome(
                        self._session, submission_id=source.source.submission_id,
                        task_id=source.source.task_id, outcome="needs_revision",
                    )
                    if source.revision_candidate is None:
                        raise TaskRoutingRequestUnavailable("revision context unavailable")
                    root = await prepare_revision(
                        self._session, manifest=stored, candidate=source.revision_candidate,
                        audit_event_id=audit_id,
                    )
                    await self._outbox.append(revision_preparation_event(stored, root))
                else:
                    root = await self._session.scalar(select(TaskRevisionPreparation).where(
                        TaskRevisionPreparation.routing_manifest_id == stored.id,
                        TaskRevisionPreparation.sequence == 1,
                    ))
                    if root is not None:
                        await self._outbox.require_existing(None, revision_preparation_event(stored, root))
            elif human:
                task = await self._session.get(WorkstreamTask, str(source.source.task_id))
                if not replay:
                    task.status = "review_pending"
                    await self._session.flush()
                    await record_attempt_outcome(
                        self._session, submission_id=source.source.submission_id,
                        task_id=source.source.task_id, outcome="review_pending",
                    )
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
            return TaskRoutingOutcome(
                project_id=source.source.project_id,
                task_id=source.source.task_id,
                submission_id=source.source.submission_id,
                completion_event_id=source.source.completion_event_id,
                routing_manifest_id=stored.id,
                authorization_decision_id=receipt.decision_id,
                outcome_event_id=stored.outcome_event_id,
                routing_recommendation=source.source.routing_recommendation,
                final_acceptance_id=acceptance_id,
                economic=economic,
                replayed=replay,
            )

    async def classify_uncertain_delivery(
        self, envelope: OutboxEventEnvelope, *, current_generation: int | None,
    ) -> str:
        """Classify exact completion facts without staging a request or any effect."""
        await require_routing_transaction(self._session)
        envelope, completion = self._completion(envelope)
        human = await self._observe_review_mode(completion)
        accepts = completion.routing_recommendation == "allow_review" and not human
        if accepts != (current_generation is not None):
            return "unresolved"
        async with AsyncExitStack() as stack:
            if accepts:
                await stack.enter_async_context(
                    self._acceptance.prepare(current_generation)
                )
            retained = await self._retained(envelope, completion)
            try:
                if retained is None:
                    observed = await self._source.observe_unstaged(
                        envelope.claim.event_id, completion
                    )
                    if observed.human_review_required is not human:
                        return "unresolved"
                    return "retry_safe"
                source = await self._source.prepare(
                    envelope.claim.event_id, completion
                )
                if source.source.human_review_required is not human:
                    return "unresolved"
                return (
                    "committed"
                    if await self._routing_complete(retained.id)
                    else "unresolved"
                )
            except TaskRoutingRequestUnavailable:
                return "unresolved"

    async def verify_retained_delivery(
        self, envelope: OutboxEventEnvelope, *, current_generation: int | None,
    ) -> None:
        """Verify exact committed routing facts without calling any effect writer."""
        await require_routing_transaction(self._session)
        envelope, completion = self._completion(envelope)
        human = await self._observe_review_mode(completion)
        accepts = completion.routing_recommendation == "allow_review" and not human
        if accepts != (current_generation is not None):
            raise TaskRoutingRequestUnavailable("routing branch unavailable")
        async with AsyncExitStack() as stack:
            if accepts:
                await stack.enter_async_context(
                    self._acceptance.prepare(current_generation)
                )
            source = await self._source.prepare(envelope.claim.event_id, completion)
            if source.source.human_review_required is not human:
                raise TaskRoutingRequestUnavailable("routing branch changed")
            stored = await self._retained(envelope, completion)
            if stored is None or not await self._routing_complete(stored.id):
                raise TaskRoutingRequestUnavailable("routing retained outcome unavailable")
            authorized_generation = stored.authorized_lifecycle_generation
            acceptance_id = stored.final_acceptance_id
            if accepts != (acceptance_id is not None) or accepts != (
                authorized_generation is not None
            ):
                raise TaskRoutingRequestUnavailable(
                    "routing retained consequence unavailable"
                )
            effects = (
                TaskAcceptedEffectsRequest(
                    **source.source.model_dump(
                        include={
                            "project_id", "task_id", "assignment_id", "submission_id",
                            "submission_version", "contributor_id",
                            "contribution_policy_version_id", "task_size", "contribution_award_definition_id", "content_id", "content_sha256",
                        }
                    ),
                    final_acceptance_id=acceptance_id,
                    expected_task_status="evaluation_pending",
                )
                if accepts
                else None
            )
            receipt = RoutingAuthorityFacts(
                decision_id=UUID(stored.authorization_decision_id),
                actor_id=UUID(stored.router_actor_id),
                identity_link_id=UUID(stored.router_identity_link_id),
                context_json=json.dumps(stored.authority_context),
            )
            async with self._authorization.prepare(source.request) as authority:
                await authority.validate_replay(
                    source, receipt, effects, authorized_generation
                )
            if self._reconciliation_claim is not None:
                await self._reconciliation_claim()
            if await self._invocation_fence.fence_invocation(envelope) is None:
                raise TaskRoutingRequestUnavailable("routing invocation changed")
            await self._outbox.require_existing(
                stored.outcome_event_id,
                _notice(source, receipt, acceptance_id),
            )
            if not await self._routing_complete(stored.id):
                raise TaskRoutingRequestUnavailable(
                    "routing retained outcome unavailable"
                )

    async def observe_delivery_generation(self, envelope: OutboxEventEnvelope) -> int | None:
        """Select server-owned generation without authority or mutation locks."""
        completion = EvaluationCompletion.model_validate_json(envelope.payload_json)
        if completion.routing_recommendation == "needs_revision":
            return None
        human = await self._observe_review_mode(completion)
        if human:
            return None
        return await self._acceptance.observe_generation()

    @staticmethod
    def _completion(
        envelope: OutboxEventEnvelope,
    ) -> tuple[OutboxEventEnvelope, EvaluationCompletion]:
        """Validate the original completion envelope without granting invocation custody."""
        try:
            envelope = OutboxEventEnvelope.model_validate(envelope)
            completion = EvaluationCompletion.model_validate_json(envelope.payload_json)
        except (TypeError, ValueError) as exc:
            raise TaskRoutingRequestUnavailable("routing invocation unavailable") from exc
        if (
            envelope.event_type != COMPLETION_EVENT
            or envelope.event_version != 1
            or envelope.aggregate_type != "checker_run"
            or envelope.aggregate_id != completion.reference.attempt_id
            or envelope.claim.project_id != completion.project_id
            or completion.routing_recommendation
            not in {"allow_review", "needs_revision"}
        ):
            raise TaskRoutingRequestUnavailable("routing invocation unavailable")
        return envelope, completion

    async def _retained(self, envelope, completion):
        """Read the exact manifest selected by the original completion event."""
        return await self._session.scalar(
            select(TaskPostSubmitRoutingManifest).where(
                TaskPostSubmitRoutingManifest.project_id == str(completion.project_id),
                TaskPostSubmitRoutingManifest.task_id == str(completion.task_id),
                TaskPostSubmitRoutingManifest.submission_id == str(completion.submission_id),
                TaskPostSubmitRoutingManifest.completion_event_id == envelope.claim.event_id,
            ).execution_options(populate_existing=True)
        )

    async def _routing_complete(self, manifest_id: UUID) -> bool:
        """Delegate complete retained effect closure to TASK's database owner."""
        return (
            await self._session.scalar(
                text(
                    "SELECT public.task_routing_outcome_complete(m) "
                    "FROM public.task_post_submit_routing_manifests m WHERE m.id=:manifest_id"
                ),
                {"manifest_id": manifest_id},
            )
        ) is True

    async def _observe_review_mode(self, completion: EvaluationCompletion) -> bool:
        """Observe exact task policy; authoritative source preparation rechecks it."""
        # This observation grants nothing. It selects lock order, and the complete
        # source is revalidated after acquiring that order's mutation custody.
        with self._session.no_autoflush:
            policy_id = await self._session.scalar(
                select(Submission.locked_review_policy_id).join(
                    WorkstreamTask, WorkstreamTask.id == Submission.task_id,
                ).where(
                    Submission.id == str(completion.submission_id),
                    Submission.task_id == str(completion.task_id),
                    WorkstreamTask.project_id == str(completion.project_id),
                )
            )
            human = (
                await self._projects.observe_review_mode(completion.project_id, UUID(policy_id))
                if policy_id is not None
                else None
            )
        if type(human) is not bool:
            raise TaskRoutingRequestUnavailable("routing branch unavailable")
        return human

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
            **({
                "exhaustion_receipt_id": str(source.exhaustion.exhaustion_receipt_id),
                "assignment_status": "revision_exhausted",
                "status_reason": "revision_limit_reached",
            } if source.exhaustion is not None else {}),
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
