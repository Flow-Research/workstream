"""Hidden, caller-transaction release of one exact pre-submit assignment."""

import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.audit.api import AuthorityInvalidationPort
from app.modules.outbox.api import (
    CommittedInvocationPort,
    HandlerOutcome,
    InvocationFencePort,
    OutboxEventEnvelope,
)
from app.modules.tasks.api.assignment_invalidation import (
    ASSIGNMENT_INVALIDATION_EVENT,
    AssignmentInvalidationAuditPort,
    AssignmentInvalidationAuthority,
    AssignmentInvalidationAuthorityFacts,
    AssignmentInvalidationAuthorizationPort,
    AssignmentInvalidationEvidence,
    AssignmentInvalidationTarget,
    AssignmentInvalidationUnavailable,
)
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.service import LOCKED_CONTEXT_HASH_FIELDS


def _target(envelope):
    try:
        envelope = OutboxEventEnvelope.model_validate(envelope.model_dump())
        target = AssignmentInvalidationTarget.model_validate_json(envelope.payload_json)
        if (
            envelope.event_type != ASSIGNMENT_INVALIDATION_EVENT
            or envelope.event_version != 1
            or envelope.aggregate_type != "task_assignment"
            or envelope.aggregate_id != target.assignment_id
            or envelope.claim.project_id != target.project_id
            or envelope.causation_event_id != target.authority_invalidation_event_id
        ):
            return None
        return target
    except (AttributeError, TypeError, ValueError):
        return None


class AssignmentInvalidationOperation:
    """TASK owns the effect; ports own committed causes, custody and authority."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        observer: CommittedInvocationPort,
        fence: InvocationFencePort,
        causes: AuthorityInvalidationPort,
        authorization: AssignmentInvalidationAuthorizationPort,
        audit: AssignmentInvalidationAuditPort,
    ):
        self._session, self._repo = session, TaskRepository(session)
        self._observer, self._fence, self._causes = observer, fence, causes
        self._authorization, self._audit = authorization, audit

    async def reconcile(self, envelope: OutboxEventEnvelope) -> HandlerOutcome:
        """Never commit; the handler acknowledges only after its root commit."""
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise AssignmentInvalidationUnavailable(
                "assignment reconciliation requires a root transaction"
            )
        target = _target(envelope)
        if target is None or await self._observer.observe_invocation(envelope) is None:
            return HandlerOutcome.REJECT
        cause = await self._causes.read_invalidation(target.authority_invalidation_event_id)
        if (
            cause is None
            or cause.invalidation_event_id != target.authority_invalidation_event_id
            or cause.contributor_id != target.contributor_id
            or (cause.project_id is not None and cause.project_id != target.project_id)
        ):
            return HandlerOutcome.REJECT
        task = await self._repo.lock_project_task(target.project_id, target.task_id)
        if task is None:
            return HandlerOutcome.REJECT
        assignment = await self._repo.lock_invalidation_assignment(target)
        if assignment is None:
            return HandlerOutcome.REJECT
        if assignment.assigned_at > cause.recorded_at:
            return HandlerOutcome.REJECT
        prior = await self._audit.read_release(target)
        if prior is not None:
            if (
                prior.facts.target != target
                or assignment.status != "authority_revoked"
                or assignment.released_at is None
            ):
                raise AssignmentInvalidationUnavailable(
                    "assignment reconciliation receipt differs from state"
                )
            return HandlerOutcome.ACKNOWLEDGE
        if task.status != "in_progress" or await self._repo.has_submission(
            target.task_id
        ):
            return HandlerOutcome.ACKNOWLEDGE
        if (
            assignment.status != "active"
            or assignment.released_at is not None
            or task.assigned_to != str(target.contributor_id)
            or task.locked_contribution_policy_version_id
            != assignment.submitter_contribution_policy_version_id
        ):
            return HandlerOutcome.REJECT
        facts = AssignmentInvalidationAuthorityFacts(
            target=target,
            cause_event_id=cause.cause_event_id,
            delivery_event_id=envelope.claim.event_id,
            delivery_generation=envelope.claim.claim_generation,
            cause_digest=canonical_json_hash(cause.model_dump(mode="json")),
            invocation_digest=canonical_json_hash(envelope.model_dump(mode="json")),
            task_status=task.status,
            locked_context_hash=canonical_json_hash(
                {
                    field: str(value) if isinstance(value, UUID) else value
                    for field in LOCKED_CONTEXT_HASH_FIELDS
                    for value in (getattr(task, field),)
                }
            ),
        )
        async with self._authorization.prepare_assignment_invalidation(facts) as prepared:
            authority = await prepared.consume(facts)
            if (
                type(authority) is not AssignmentInvalidationAuthority
                or type(authority.actor_profile_id) is not UUID
                or type(authority.decision_id) is not UUID
                or type(authority.resource_context_digest) is not str
                or re.fullmatch(r"sha256:[0-9a-f]{64}", authority.resource_context_digest) is None
            ):
                raise AssignmentInvalidationUnavailable(
                    "assignment reconciliation authority unavailable"
                )
            custody = await self._fence.fence_invocation(envelope)
            if custody is None or custody.claim != envelope.claim:
                raise AssignmentInvalidationUnavailable(
                    "assignment reconciliation custody unavailable"
                )
            assignment.status, assignment.released_at = "authority_revoked", custody.observed_at
            task.status, task.assigned_to = "ready", None
            await self._audit.record_release(
                AssignmentInvalidationEvidence(facts, authority)
            )
            await self._session.flush()
        return HandlerOutcome.ACKNOWLEDGE
