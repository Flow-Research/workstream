"""Shared audit owner composition for typed product transition ports."""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.schemas import (
    LifecycleAuditEntityType, LifecycleAuditEventInput, LifecycleAuditEventType,
    LifecycleAuditReason, LifecycleAuditReferenceKind,
)
from app.modules.audit.service import LifecycleAuditParticipant
from app.modules.tasks.api import TaskAuthorityOperation, TaskTransitionAuditPort, TaskTransitionFacts


class _TaskTransitionAudit:
    def __init__(self, session: AsyncSession) -> None:
        self._participant = LifecycleAuditParticipant(session)

    async def record(self, facts: TaskTransitionFacts) -> None:
        event_type = {
            TaskAuthorityOperation.CLAIM: LifecycleAuditEventType.TASK_CLAIMED,
            TaskAuthorityOperation.START: LifecycleAuditEventType.TASK_STARTED,
            TaskAuthorityOperation.START_OVERRIDE: LifecycleAuditEventType.TASK_START_OVERRIDDEN,
        }[facts.operation]
        await self._participant.add_event(LifecycleAuditEventInput(
            event_id=uuid4(), entity_type=LifecycleAuditEntityType.TASK, entity_id=facts.task_id,
            event_type=event_type, from_status=facts.from_status, to_status=facts.to_status,
            actor_id=facts.actor_profile_id, reason=LifecycleAuditReason.STATE_CHANGED,
            task_reason=facts.reason if facts.reason and facts.reason.strip() else None,
            references={
                LifecycleAuditReferenceKind.PROJECT: facts.project_id,
                LifecycleAuditReferenceKind.TASK: facts.task_id,
                LifecycleAuditReferenceKind.ASSIGNMENT: facts.assignment_id,
                LifecycleAuditReferenceKind.AUTHORIZATION_DECISION: facts.authorization_decision_id,
            },
        ))


def task_transition_audit(session: AsyncSession) -> TaskTransitionAuditPort:
    """Use the existing participant in the same caller-owned transaction."""
    return _TaskTransitionAudit(session)
