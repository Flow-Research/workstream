"""TASK-owned immediate rejection and release after the last permitted attempt."""

from sqlalchemy import func, select

from app.modules.tasks.api.post_submit_routing import TaskRevisionExhaustionFacts
from app.modules.tasks.models import TaskAssignment, WorkstreamTask
from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequestUnavailable
from app.modules.tasks.revision.models import TaskRevisionExhaustion
from app.modules.tasks.submission_attempts import record_attempt_outcome


def exhaustion_facts(receipt) -> TaskRevisionExhaustionFacts:
    """Recover exactly the consequence authorized for the original routing effect."""
    return TaskRevisionExhaustionFacts(
        exhaustion_receipt_id=receipt.id,
        revision_round=receipt.revision_round,
        max_revision_rounds=receipt.max_revision_rounds,
    )


async def exhaust_assignment(session, *, manifest, source, replay):
    """Stage immutable terminal evidence and release under existing TASK custody."""
    facts = source.exhaustion
    if facts is None:
        raise TaskRoutingRequestUnavailable("revision exhaustion unavailable")
    assignment = await session.get(TaskAssignment, str(source.source.assignment_id))
    if replay:
        receipt = await session.get(TaskRevisionExhaustion, facts.exhaustion_receipt_id)
        if receipt is None or assignment is None or not (
            receipt.routing_manifest_id == manifest.id
            and receipt.assignment_id == str(source.source.assignment_id)
            and receipt.source_submission_id == str(source.source.submission_id)
            and (
                receipt.authorization_decision_id == manifest.authorization_decision_id
                and receipt.audit_event_id == manifest.audit_event_id
                and receipt.outcome_event_id == manifest.outcome_event_id
            )
            and exhaustion_facts(receipt) == facts
            and assignment.status == "revision_exhausted"
            and assignment.released_at == receipt.exhausted_at
        ):
            raise TaskRoutingRequestUnavailable("revision exhaustion replay differs")
        return receipt
    task = await session.get(WorkstreamTask, str(source.source.task_id))
    if task is None or assignment is None or not (
        task.status == "evaluation_pending"
        and task.assigned_to == assignment.contributor_id == str(source.source.contributor_id)
        and assignment.status == "active" and assignment.released_at is None
    ):
        raise TaskRoutingRequestUnavailable("revision exhaustion source changed")
    exhausted_at = await session.scalar(select(func.clock_timestamp()))
    policy = source.source.locked_policy
    receipt = TaskRevisionExhaustion(
        id=facts.exhaustion_receipt_id,
        project_id=str(source.source.project_id), task_id=str(source.source.task_id),
        assignment_id=assignment.id, contributor_id=assignment.contributor_id,
        source_submission_id=str(source.source.submission_id), routing_manifest_id=manifest.id,
        revision_round=facts.revision_round, max_revision_rounds=facts.max_revision_rounds,
        revision_policy_id=str(policy.locked_revision_policy_id),
        revision_policy_generation=policy.locked_revision_policy_generation,
        revision_policy_hash=policy.locked_revision_policy_hash,
        exhausted_at=exhausted_at,
        authorization_decision_id=manifest.authorization_decision_id,
        audit_event_id=manifest.audit_event_id, outcome_event_id=manifest.outcome_event_id,
    )
    await commit_exhaustion(session, receipt=receipt, task=task, assignment=assignment)
    return receipt


async def commit_exhaustion(session, *, receipt, task, assignment):
    """Stage the terminal consequence under the original routing authority."""
    if not (
        task.status == "evaluation_pending" and task.id == receipt.task_id
        and task.assigned_to == assignment.contributor_id == receipt.contributor_id
        and assignment.id == receipt.assignment_id and assignment.status == "active"
        and assignment.released_at is None
    ):
        raise TaskRoutingRequestUnavailable("revision exhaustion source changed")
    session.add(receipt)
    await session.flush()
    assignment.status, assignment.released_at = "revision_exhausted", receipt.exhausted_at
    task.status, task.assigned_to = "ready", None
    await session.flush()
    await record_attempt_outcome(
        session, submission_id=receipt.source_submission_id, task_id=receipt.task_id,
        outcome="rejected",
    )
