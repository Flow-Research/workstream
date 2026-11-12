"""TASK-owned, caller-transaction expiration of one routed revision window."""

import json
from uuid import UUID

from sqlalchemy import func, select

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.outbox.api import HandlerOutcome, OutboxAppendDisposition, OutboxEventEnvelope
from app.modules.tasks.submission_attempts import record_attempt_outcome
from app.modules.tasks.api.revision_expiry import (
    REVISION_EXPIRY_EVENT, TaskRevisionExpiryAuthorityFacts, TaskRevisionExpiryEvidence,
    TaskRevisionExpiryTarget, TaskRevisionExpiryUnavailable,
    revision_expiry_resource_digest,
)
from app.modules.tasks.models import Submission
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.revision.expiry_event import (
    expiry_receipt_snapshot, revision_expired_event, revision_expiry_event,
)
from app.modules.tasks.revision.models import TaskRevisionExpiration, TaskRevisionPreparation


class TaskRevisionExpiryOperation:
    """Release the exact overdue assignment without changing its Submission."""

    def __init__(self, session, *, observer, fence, authorization, audit, outbox):
        """Use owner ports and the caller session for one atomic expiry effect."""
        self._session, self._repo = session, TaskRepository(session)
        self._observer, self._fence = observer, fence
        self._authorization, self._audit = authorization, audit
        self._outbox = outbox

    async def expire(self, envelope: OutboxEventEnvelope) -> HandlerOutcome:
        """Revalidate TASK-first custody, then expire or replay the exact window."""
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise TaskRevisionExpiryUnavailable("revision expiry requires a root transaction")
        try:
            envelope = OutboxEventEnvelope.model_validate(envelope)
            target = TaskRevisionExpiryTarget.model_validate_json(envelope.payload_json)
        except (TypeError, ValueError, AttributeError):
            return HandlerOutcome.REJECT
        if (envelope.event_type != REVISION_EXPIRY_EVENT or envelope.event_version != 1
                or envelope.aggregate_type != "task" or envelope.aggregate_id != target.task_id
                or envelope.claim.project_id != target.project_id
                or await self._observer.observe_invocation(envelope) is None):
            return HandlerOutcome.REJECT
        task = await self._repo.lock_project_task(target.project_id, target.task_id)
        if task is None:
            return HandlerOutcome.REJECT
        assignment = await self._repo.lock_accepted_assignment(
            project_id=target.project_id, task_id=target.task_id,
            assignment_id=target.assignment_id,
        )
        if assignment is None or assignment.contributor_id != str(target.contributor_id):
            return HandlerOutcome.REJECT
        latest = await self._session.scalar(select(Submission).where(
            Submission.task_id == str(target.task_id),
        ).order_by(Submission.version.desc()).limit(1))
        manifest = await self._repo.read_routing_manifest(
            manifest_id=target.routing_manifest_id, project_id=target.project_id,
            task_id=target.task_id, submission_id=target.source_submission_id,
        )
        root = await self._session.get(TaskRevisionPreparation, target.root_preparation_id)
        if (manifest is None or manifest.routing_recommendation != "needs_revision"
                or root is None or root.sequence != 1 or root.predecessor_id is not None
                or root.preparation_sha256 != target.root_preparation_sha256
                or root.routing_manifest_id != target.routing_manifest_id
                or root.assignment_id != str(target.assignment_id)
                or root.submission_id != str(target.source_submission_id)):
            return HandlerOutcome.REJECT
        scheduled = await self._scheduled_preparation(envelope, manifest, root, target)
        if scheduled is None:
            return HandlerOutcome.REJECT
        expected = revision_expiry_event(manifest, root, scheduled)
        if (envelope.idempotency_key != expected.idempotency_key
                or envelope.correlation_id != expected.correlation_id
                or envelope.causation_event_id != expected.causation_event_id
                or json.loads(envelope.payload_json) != expected.payload):
            return HandlerOutcome.REJECT
        head = await self._session.scalar(select(TaskRevisionPreparation).where(
            TaskRevisionPreparation.routing_manifest_id == target.routing_manifest_id,
        ).order_by(TaskRevisionPreparation.sequence.desc()).limit(1))
        if head is None:
            return HandlerOutcome.REJECT
        if head.deadline_at is None or head.deadline_at != target.deadline_at:
            # A paused or superseded timer cannot expire the current head.
            return HandlerOutcome.ACKNOWLEDGE
        now = await self._session.scalar(select(func.clock_timestamp()))
        if now < target.deadline_at:
            return HandlerOutcome.RETRY
        prior = await self._session.scalar(select(TaskRevisionExpiration).where(
            TaskRevisionExpiration.routing_manifest_id == target.routing_manifest_id,
        ))
        if prior is not None:
            evidence = await self._audit.read_expiry(expiry_receipt_snapshot(prior))
            if (prior.source_submission_id != str(target.source_submission_id)
                    or prior.root_preparation_id != target.root_preparation_id
                    or prior.root_preparation_sha256 != target.root_preparation_sha256
                    or assignment.status != "revision_expired"
                    or assignment.released_at != prior.expired_at
                    or evidence is None or evidence.receipt_id != prior.id):
                raise TaskRevisionExpiryUnavailable("revision expiry replay differs")
            return HandlerOutcome.ACKNOWLEDGE
        facts = TaskRevisionExpiryAuthorityFacts(
            target=target, head_preparation_id=UUID(str(head.id)),
            head_preparation_sha256=head.preparation_sha256,
            delivery_event_id=envelope.claim.event_id,
            delivery_generation=envelope.claim.claim_generation,
            invocation_digest=canonical_json_hash(envelope.model_dump(mode="json")),
            task_status=task.status, assignment_status=assignment.status,
        )
        async with self._authorization.prepare_revision_expiry(facts) as prepared:
            authority = await prepared.consume(facts)
            if authority.resource_context_digest != revision_expiry_resource_digest(facts):
                raise TaskRevisionExpiryUnavailable("revision expiry authority differs")
            custody = await self._fence.fence_invocation(envelope)
            if custody is None or custody.claim != envelope.claim:
                raise TaskRevisionExpiryUnavailable("revision expiry custody unavailable")
            source_current = await self._session.scalar(select(
                func.revision_routing_source_current(target.routing_manifest_id)))
            if (latest is None or latest.id != str(target.source_submission_id)
                    or not source_current or task.status != "needs_revision"
                    or task.assigned_to != str(target.contributor_id)
                    or assignment.status != "active" or assignment.released_at is not None):
                return HandlerOutcome.ACKNOWLEDGE
            return await self._record_expiration(
                target=target, envelope=envelope, head=head, authority=authority,
                facts=facts, task=task, assignment=assignment,
            )

    async def _scheduled_preparation(self, envelope, manifest, root, target):
        """Resolve the exact immutable clock head that originally scheduled this timer."""
        scheduled = root
        prefix = "task.revision.expire:" + str(manifest.id)
        if envelope.idempotency_key != prefix:
            try:
                scheduled_id = UUID(envelope.idempotency_key.removeprefix(prefix + ":"))
            except (ValueError, AttributeError):
                return None
            scheduled = await self._session.get(TaskRevisionPreparation, scheduled_id)
            if (scheduled is None or scheduled.id == root.id
                    or scheduled.routing_manifest_id != manifest.id):
                return None
        if scheduled.deadline_at is None or scheduled.deadline_at != target.deadline_at:
            return None
        return scheduled

    async def _record_expiration(self, *, target, envelope, head, authority, facts, task, assignment):
        """Atomically persist the rejection, its notice, custody release, and audit."""
        expired_at = await self._session.scalar(select(func.clock_timestamp()))
        if expired_at < target.deadline_at:
            return HandlerOutcome.RETRY
        audit_event_id = new_record_id()
        receipt = TaskRevisionExpiration(
            id=new_record_id(), project_id=str(target.project_id), task_id=str(target.task_id),
            assignment_id=str(target.assignment_id), contributor_id=str(target.contributor_id),
            source_submission_id=str(target.source_submission_id),
            routing_manifest_id=target.routing_manifest_id,
            root_preparation_id=target.root_preparation_id,
            root_preparation_sha256=target.root_preparation_sha256,
            head_preparation_id=head.id, head_preparation_sha256=head.preparation_sha256,
            deadline_at=target.deadline_at, expired_at=expired_at,
            delivery_event_id=envelope.claim.event_id,
            authorization_decision_id=str(authority.decision_id),
            authority_context=facts.model_dump(mode="json"),
            audit_event_id=str(audit_event_id),
        )
        outcome = await self._outbox.append(revision_expired_event(receipt))
        if outcome.disposition is not OutboxAppendDisposition.CREATED:
            raise TaskRevisionExpiryUnavailable("revision expiry outcome differs")
        receipt.outcome_event_id = outcome.event_id
        self._session.add(receipt)
        await self._session.flush()
        assignment.status, assignment.released_at = "revision_expired", expired_at
        task.status, task.assigned_to = "ready", None
        await self._session.flush()
        await record_attempt_outcome(
            self._session, submission_id=target.source_submission_id,
            task_id=target.task_id, outcome="rejected",
        )
        recorded = await self._audit.record_expiry(
            TaskRevisionExpiryEvidence(facts, authority, receipt.id, audit_event_id, expired_at))
        if recorded != audit_event_id:
            raise TaskRevisionExpiryUnavailable("revision expiry audit differs")
        await self._session.flush()
        return HandlerOutcome.ACKNOWLEDGE
