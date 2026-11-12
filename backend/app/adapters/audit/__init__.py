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
from app.modules.tasks.api.revision_expiry import (
    TaskRevisionExpiryAuthorityFacts, TaskRevisionExpiryAuditPort,
    TaskRevisionExpiryEvidence, TaskRevisionExpiryReceiptSnapshot, TaskRevisionExpiryUnavailable,
    revision_expiry_resource_digest,
)
from app.modules.tasks.api import TaskAuthorityOperation, TaskTransitionAuditPort, TaskTransitionFacts
from app.modules.tasks.api.transition_audit import TaskRevisionRepairAuditFacts


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


    async def record_revision_repair(self, facts: TaskRevisionRepairAuditFacts) -> None:
        await self._participant.add_event(LifecycleAuditEventInput(
            event_id=facts.event_id, entity_type=LifecycleAuditEntityType.TASK,
            entity_id=facts.task_id, event_type=LifecycleAuditEventType.TASK_REVISION_CONTEXT_REPAIRED,
            actor_id=facts.actor_profile_id, reason=LifecycleAuditReason.FACT_RECORDED,
            task_reason=facts.reason,
            authorization_resource_digest=facts.authorization_resource_digest,
            references={
                LifecycleAuditReferenceKind.PROJECT: facts.project_id,
                LifecycleAuditReferenceKind.TASK: facts.task_id,
                LifecycleAuditReferenceKind.ASSIGNMENT: facts.assignment_id,
                LifecycleAuditReferenceKind.SUBMISSION: facts.submission_id,
                LifecycleAuditReferenceKind.ROUTING_MANIFEST: facts.routing_manifest_id,
                LifecycleAuditReferenceKind.REVISION_PREPARATION: facts.preparation_id,
                LifecycleAuditReferenceKind.AUTHORIZATION_DECISION: facts.authorization_decision_id,
                **({LifecycleAuditReferenceKind.OUTBOX_EVENT: facts.outbox_event_id}
                   if facts.outbox_event_id is not None else {}),
            },
        ))



def task_transition_audit(session: AsyncSession) -> TaskTransitionAuditPort:
    """Use the existing participant in the same caller-owned transaction."""
    return _TaskTransitionAudit(session)


class _CheckerRetryAudit:
    """Use the shared AUDIT lifecycle participant for a retry initiation fact."""

    def __init__(self, session: AsyncSession) -> None:
        self._participant = LifecycleAuditParticipant(session)

    async def record(self, preparation, successor, authority) -> None:
        source = preparation.source
        await self._participant.add_event(LifecycleAuditEventInput(
            event_id=successor.audit_event_id,
            entity_type=LifecycleAuditEntityType.CHECKER_RUN,
            entity_id=successor.run_id,
            event_type=LifecycleAuditEventType.CHECKER_RETRY_REQUESTED,
            actor_id=preparation.actor_profile_id,
            reason=LifecycleAuditReason.FACT_RECORDED,
            operator_reason=preparation.reason,
            authorization_resource_digest=authority.resource_digest,
            references={
                LifecycleAuditReferenceKind.PROJECT: source.project_id,
                LifecycleAuditReferenceKind.TASK: source.task_id,
                LifecycleAuditReferenceKind.ASSIGNMENT: source.assignment_id,
                LifecycleAuditReferenceKind.SUBMISSION: source.submission_id,
                LifecycleAuditReferenceKind.CHECKER_RUN: successor.run_id,
                LifecycleAuditReferenceKind.SOURCE_CHECKER_RUN: source.source_run_id,
                LifecycleAuditReferenceKind.AUTHORIZATION_DECISION: authority.decision_id,
                LifecycleAuditReferenceKind.OUTBOX_EVENT: successor.event_id,
            },
        ))


def checker_retry_audit(session: AsyncSession):
    """Compose the existing transaction-bound AUDIT participant."""
    return _CheckerRetryAudit(session)


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


class _TaskRevisionExpiryAudit:
    def __init__(self, session):
        self._repo = AuditRepository(session)
        self._participant = LifecycleAuditParticipant(session)

    async def read_expiry(self, receipt: TaskRevisionExpiryReceiptSnapshot):
        event = await self._repo.get_lifecycle_event(str(receipt.audit_event_id))
        authority = await self._repo.get_authority_event(str(receipt.authorization_decision_id))
        try:
            facts = TaskRevisionExpiryAuthorityFacts.model_validate_json(
                json.dumps(receipt.authority_context))
            expected = {
                "project_id": str(facts.target.project_id),
                "task_id": str(facts.target.task_id),
                "assignment_id": str(facts.target.assignment_id),
                "submission_id": str(facts.target.source_submission_id),
                "routing_manifest_id": str(facts.target.routing_manifest_id),
                "revision_preparation_id": str(facts.head_preparation_id),
                "authorization_decision_id": str(receipt.authorization_decision_id),
                "outbox_event_id": str(facts.delivery_event_id),
            }
            digest = revision_expiry_resource_digest(facts)
            if (event is None or authority is None
                    or event.event_type != LifecycleAuditEventType.TASK_REVISION_EXPIRED.value
                    or event.entity_type != "task" or event.entity_id != str(facts.target.task_id)
                    or event.from_status != "needs_revision" or event.to_status != "ready"
                    or event.event_payload != {
                        "references": expected, "authorization_resource_digest": digest,
                        "revision_expiry_facts": facts.model_dump(mode="json"),
                    }
                    or authority.event_type != "SensitiveAuthorizationAllowed"
                    or authority.action_id != "task.revision.expire"
                    or authority.permission_id != "task.revision.expire"
                    or authority.actor_id != event.actor_id
                    or authority.resource_type != "task"
                    or authority.resource_id != str(facts.target.task_id)
                    or authority.project_id != str(facts.target.project_id)
                    or authority.request_id != str(facts.delivery_event_id)
                    or authority.correlation_id != str(facts.target.routing_manifest_id)
                    or authority.after_facts != {"allowed": True, "resource_context_digest": digest}
                    or receipt.routing_manifest_id != facts.target.routing_manifest_id
                    or receipt.source_submission_id != facts.target.source_submission_id
                    or receipt.head_preparation_id != facts.head_preparation_id
                    or receipt.expired_at < facts.target.deadline_at):
                raise ValueError("invalid revision expiry evidence")
            from app.modules.tasks.api.revision_expiry import TaskRevisionExpiryAuthority
            return TaskRevisionExpiryEvidence(
                facts, TaskRevisionExpiryAuthority(UUID(event.actor_id), UUID(authority.id), digest),
                receipt.receipt_id, receipt.audit_event_id, receipt.expired_at,
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            raise TaskRevisionExpiryUnavailable("revision expiry evidence unavailable") from None

    async def record_expiry(self, evidence: TaskRevisionExpiryEvidence):
        facts = TaskRevisionExpiryAuthorityFacts.model_validate_json(evidence.facts.model_dump_json())
        if revision_expiry_resource_digest(facts) != evidence.authority.resource_context_digest:
            raise TaskRevisionExpiryUnavailable("revision expiry authority differs")
        target = facts.target
        await self._participant.add_event(LifecycleAuditEventInput(
            event_id=evidence.audit_event_id,
            entity_type=LifecycleAuditEntityType.TASK, entity_id=target.task_id,
            event_type=LifecycleAuditEventType.TASK_REVISION_EXPIRED,
            actor_id=evidence.authority.actor_profile_id,
            reason=LifecycleAuditReason.STATE_CHANGED,
            from_status="needs_revision", to_status="ready",
            references={
                LifecycleAuditReferenceKind.PROJECT: target.project_id,
                LifecycleAuditReferenceKind.TASK: target.task_id,
                LifecycleAuditReferenceKind.ASSIGNMENT: target.assignment_id,
                LifecycleAuditReferenceKind.SUBMISSION: target.source_submission_id,
                LifecycleAuditReferenceKind.ROUTING_MANIFEST: target.routing_manifest_id,
                LifecycleAuditReferenceKind.REVISION_PREPARATION: facts.head_preparation_id,
                LifecycleAuditReferenceKind.AUTHORIZATION_DECISION: evidence.authority.decision_id,
                LifecycleAuditReferenceKind.OUTBOX_EVENT: facts.delivery_event_id,
            },
            authorization_resource_digest=evidence.authority.resource_context_digest,
            revision_expiry_facts=facts.model_dump(mode="json"),
        ))
        return evidence.audit_event_id


def task_revision_expiry_audit(session: AsyncSession) -> TaskRevisionExpiryAuditPort:
    return _TaskRevisionExpiryAudit(session)


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
                to_status=(
                    "ready"
                    if source.exhaustion is not None
                    else "needs_revision"
                    if s.routing_recommendation == "needs_revision"
                    else "review_pending"
                    if s.human_review_required
                    else "accepted"
                ),
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
