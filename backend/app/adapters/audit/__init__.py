"""Shared audit owner composition for typed product transition ports."""

import json
from uuid import UUID
from app.core.identifiers import new_record_id

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.schemas import (
    LifecycleAuditEntityType, LifecycleAuditEventInput, LifecycleAuditEventType,
    LifecycleAuditReason, LifecycleAuditReferenceKind,
)
from app.modules.audit.service import LifecycleAuditParticipant
from app.modules.audit.invalidation import CommittedAuthorityInvalidationReader
from app.modules.audit.api import AuthorityInvalidationPort
from app.modules.audit.repository import AuditRepository, LIFECYCLE_AUTH_SOURCE
from app.modules.tasks.api.assignment_invalidation import (
    AssignmentInvalidationAuditPort, AssignmentInvalidationEvidence,
    AssignmentInvalidationAuthority, AssignmentInvalidationUnavailable,
    AssignmentInvalidationAuthorityFacts,
    assignment_invalidation_resource_digest,
)
from app.modules.tasks.api import TaskAuthorityOperation, TaskTransitionAuditPort, TaskTransitionFacts


class _TaskTransitionAudit:
    def __init__(self, session: AsyncSession) -> None:
        self._participant = LifecycleAuditParticipant(session)

    async def record(self, facts: TaskTransitionFacts) -> None:
        authority_facts = json.loads(facts.authority.resource_context_json) if facts.authority else None
        if facts.authority and (
            facts.authority.decision_id != facts.authorization_decision_id
            or authority_facts.get("identity_link_id") != str(facts.authority.identity_link_id)
        ):
            raise ValueError("task authority evidence mismatch")
        event_type = {
            TaskAuthorityOperation.CREATE: LifecycleAuditEventType.TASK_CREATED,
            TaskAuthorityOperation.SCREEN: LifecycleAuditEventType.TASK_SCREENED,
            TaskAuthorityOperation.RELEASE: LifecycleAuditEventType.TASK_RELEASED,
            TaskAuthorityOperation.CLAIM: LifecycleAuditEventType.TASK_CLAIMED,
            TaskAuthorityOperation.START: LifecycleAuditEventType.TASK_STARTED,
            TaskAuthorityOperation.START_OVERRIDE: LifecycleAuditEventType.TASK_START_OVERRIDDEN,
        }[facts.operation]
        await self._participant.add_event(LifecycleAuditEventInput(
            event_id=new_record_id(), entity_type=LifecycleAuditEntityType.TASK, entity_id=facts.task_id,
            event_type=event_type, from_status=facts.from_status, to_status=facts.to_status,
            actor_id=facts.actor_profile_id, reason=LifecycleAuditReason.STATE_CHANGED,
            task_reason=facts.reason if facts.reason and facts.reason.strip() else None,
            source_type=facts.source_type,
            manager_authority_facts=authority_facts,
            authorization_resource_digest=facts.authority.resource_context_digest if facts.authority else None,
            locked_lineage=facts.locked_lineage.model_dump(mode="json") if facts.locked_lineage else None,
            references={
                LifecycleAuditReferenceKind.PROJECT: facts.project_id,
                LifecycleAuditReferenceKind.TASK: facts.task_id,
                **({LifecycleAuditReferenceKind.ASSIGNMENT: facts.assignment_id} if facts.assignment_id else {}),
                LifecycleAuditReferenceKind.AUTHORIZATION_DECISION: facts.authorization_decision_id,
            },
        ))


def task_transition_audit(session: AsyncSession) -> TaskTransitionAuditPort:
    """Use the existing participant in the same caller-owned transaction."""
    return _TaskTransitionAudit(session)


def committed_authority_invalidation(session_factory) -> AuthorityInvalidationPort:
    """Keep cause validation and independent committed reads in AUDIT."""
    return CommittedAuthorityInvalidationReader(session_factory)


class _AssignmentInvalidationAudit:
    def __init__(self, session):
        self._repo = AuditRepository(session)
        self._participant = LifecycleAuditParticipant(session)

    @staticmethod
    def _references(target, decision_id):
        return {
            LifecycleAuditReferenceKind.PROJECT: target.project_id,
            LifecycleAuditReferenceKind.TASK: target.task_id,
            LifecycleAuditReferenceKind.ASSIGNMENT: target.assignment_id,
            LifecycleAuditReferenceKind.AUTHORITY_INVALIDATION: target.authority_invalidation_event_id,
            LifecycleAuditReferenceKind.AUTHORIZATION_DECISION: decision_id,
        }

    async def read_release(self, target):
        row = await self._repo.assignment_release_event(
            target.assignment_id, target.authority_invalidation_event_id,
        )
        if row is None:
            return None
        try:
            refs = row.event_payload["references"]
            decision = UUID(refs["authorization_decision_id"])
            expected = {key.value: str(value) for key, value in self._references(target, decision).items()}
            digest = row.event_payload["authorization_resource_digest"]
            facts = AssignmentInvalidationAuthorityFacts.model_validate_json(
                json.dumps(row.event_payload["assignment_invalidation_facts"])
            )
            authorization = await self._repo.get_authority_event(str(decision))
            if (
                row.event_domain != "legacy_lifecycle" or row.auth_source != LIFECYCLE_AUTH_SOURCE
                or row.entity_type != "task" or row.entity_id != str(target.task_id)
                or row.event_type != LifecycleAuditEventType.TASK_ASSIGNMENT_AUTHORITY_REVOKED.value
                or row.from_status not in {"claimed", "in_progress"} or row.to_status != "ready"
                or row.event_payload != {"references": expected, "authorization_resource_digest": digest,
                                         "assignment_invalidation_facts": facts.model_dump(mode="json")}
                or facts.target != target or facts.task_status != row.from_status
                or assignment_invalidation_resource_digest(facts) != digest
                or authorization is None
                or authorization.event_type != "SensitiveAuthorizationAllowed"
                or authorization.action_id != "task.assignment.authority_reconcile"
                or authorization.permission_id != "task.assignment.authority_reconcile"
                or authorization.actor_id != row.actor_id
                or authorization.resource_type != "task"
                or authorization.resource_id != str(target.task_id)
                or authorization.project_id != str(target.project_id)
                or authorization.request_id != str(facts.delivery_event_id)
                or authorization.correlation_id != str(target.authority_invalidation_event_id)
                or authorization.after_facts != {"allowed": True, "resource_context_digest": digest}
                or row.reason != LifecycleAuditReason.STATE_CHANGED.value or row.is_dev_auth
            ):
                raise ValueError("invalid release receipt")
            return AssignmentInvalidationEvidence(facts, AssignmentInvalidationAuthority(
                actor_profile_id=UUID(row.actor_id), decision_id=decision, resource_context_digest=digest,
            ))
        except (AttributeError, KeyError, TypeError, ValueError):
            raise AssignmentInvalidationUnavailable("assignment reconciliation unavailable") from None

    async def record_release(self, evidence):
        facts = AssignmentInvalidationAuthorityFacts.model_validate(evidence.facts.model_dump())
        if assignment_invalidation_resource_digest(facts) != evidence.authority.resource_context_digest:
            raise AssignmentInvalidationUnavailable("assignment reconciliation authority differs")
        target = facts.target
        await self._participant.add_event(LifecycleAuditEventInput(
            event_id=new_record_id(),
            entity_type=LifecycleAuditEntityType.TASK, entity_id=target.task_id,
            event_type=LifecycleAuditEventType.TASK_ASSIGNMENT_AUTHORITY_REVOKED,
            actor_id=evidence.authority.actor_profile_id,
            reason=LifecycleAuditReason.STATE_CHANGED,
            from_status=evidence.facts.task_status, to_status="ready",
            references=self._references(target, evidence.authority.decision_id),
            authorization_resource_digest=evidence.authority.resource_context_digest,
            assignment_invalidation_facts=facts.model_dump(mode="json"),
        ))


def assignment_invalidation_audit(session: AsyncSession) -> AssignmentInvalidationAuditPort:
    """The existing typed lifecycle participant is the atomic release receipt."""
    return _AssignmentInvalidationAudit(session)


class _TaskRoutingAudit:
    def __init__(self, session):
        self._session = session
        self._participant = LifecycleAuditParticipant(session)
        self._repository = AuditRepository(session)

    async def record(self, *, audit_event_id, source, authority, economic, replay):
        s = source.source
        await self._record(
            LifecycleAuditEventInput(
                event_id=audit_event_id,
                entity_type=LifecycleAuditEntityType.TASK,
                entity_id=s.task_id,
                event_type=LifecycleAuditEventType.TASK_POST_SUBMIT_ROUTED,
                actor_id=authority.actor_id,
                reason=LifecycleAuditReason.STATE_CHANGED,
                from_status="evaluation_pending",
                to_status="review_pending" if s.human_review_required else "accepted",
                references={
                    LifecycleAuditReferenceKind.PROJECT: s.project_id,
                    LifecycleAuditReferenceKind.TASK: s.task_id,
                    LifecycleAuditReferenceKind.SUBMISSION: s.submission_id,
                    LifecycleAuditReferenceKind.ASSIGNMENT: s.assignment_id,
                    LifecycleAuditReferenceKind.AUTHORIZATION_DECISION: authority.decision_id,
                    LifecycleAuditReferenceKind.ROUTING_MANIFEST: s.id,
                },
            ),
            replay,
        )
        if economic is None:
            return
        await self._fact(
            LifecycleAuditEventType.SUBMITTER_CONTRIBUTION_RECORDED,
            LifecycleAuditEntityType.CONTRIBUTION,
            economic.contribution_record_id,
            authority.actor_id,
            {
                LifecycleAuditReferenceKind.PROJECT: s.project_id,
                LifecycleAuditReferenceKind.TASK: s.task_id,
                LifecycleAuditReferenceKind.SUBMISSION: s.submission_id,
                LifecycleAuditReferenceKind.ASSIGNMENT: s.assignment_id,
                LifecycleAuditReferenceKind.FINAL_ACCEPTANCE: economic.final_acceptance_id,
                LifecycleAuditReferenceKind.CONTRIBUTION_RECORD: economic.contribution_record_id,
            },
            replay,
        )
        for award_id in economic.award_ids:
            await self._fact(
                LifecycleAuditEventType.COMPENSATION_AWARD_CREATED,
                LifecycleAuditEntityType.COMPENSATION_AWARD,
                award_id,
                authority.actor_id,
                {
                    LifecycleAuditReferenceKind.PROJECT: s.project_id,
                    LifecycleAuditReferenceKind.COMPENSATION_AWARD: award_id,
                    LifecycleAuditReferenceKind.CONTRIBUTION_RECORD: economic.contribution_record_id,
                },
                replay,
            )

    async def _fact(self, event_type, entity_type, entity_id, actor_id, references, replay):
        if replay:
            events = await self._repository.list_audit_events(entity_type.value, str(entity_id))
            ids = [
                event.id
                for event in events
                if event.event_type == event_type.value
                and event.auth_source == LIFECYCLE_AUTH_SOURCE
            ]
            if len(ids) != 1:
                raise ValueError("routing audit is incomplete")
            event_id = UUID(ids[0])
        else:
            event_id = new_record_id()
        await self._record(
            LifecycleAuditEventInput(
                event_id=event_id,
                entity_type=entity_type,
                entity_id=entity_id,
                event_type=event_type,
                actor_id=actor_id,
                reason=LifecycleAuditReason.FACT_RECORDED,
                references=references,
            ),
            replay,
        )

    async def _record(self, value, replay):
        if replay:
            events = await self._repository.list_audit_events(
                value.entity_type.value, str(value.entity_id)
            )
            if not any(event.id == str(value.event_id) for event in events):
                raise ValueError("routing audit is incomplete")
        # The shared participant compares every retained field on exact replay.
        await self._participant.add_event(value)


def task_routing_audit(session):
    """Compose routing and economic evidence through the shared audit owner."""
    return _TaskRoutingAudit(session)
