"""Reconcile retained last-attempt failures through the canonical terminal writer."""

import json
from uuid import UUID

from sqlalchemy import func, select

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.outbox.api import OutboxAppendDisposition
from app.modules.projects.api import ProjectLockedPolicyContextRequest, ProjectLockedPolicyContextUnavailable
from app.modules.projects.api.policy_lineage import RevisionPolicySemantics
from app.modules.tasks.api.revision_exhaustion import TaskRevisionExhaustionAuditFacts
from app.modules.tasks.api.revision_recovery import TaskRevisionRecoveryFacts
from app.modules.tasks.models import Submission
from app.modules.tasks.submission_attempts import COVERAGE_RETURN_REASON
from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequestUnavailable
from app.modules.tasks.revision.exhaustion import commit_exhaustion
from app.modules.tasks.revision.exhaustion_event import revision_exhausted_event
from app.modules.tasks.revision.models import TaskRevisionExhaustion
from app.modules.tasks.service import LOCKED_CONTEXT_HASH_FIELDS


async def recover_exhausted_assignment(session, *, projects, authorization, audit, outbox,
                                     manifest, task, assignment, source, root, head):
    """Return false below the cap or without locked context; otherwise exhaust the source."""
    try:
        context = await projects.lock_locked_policy_context(ProjectLockedPolicyContextRequest(
            project_id=UUID(manifest.project_id), guide_version=source.locked_guide_version,
            source_snapshot_id=UUID(source.locked_guide_source_snapshot_id),
            source_snapshot_hash=source.locked_guide_source_snapshot_hash,
            effective_policy_id=UUID(source.locked_effective_project_submission_artifact_policy_id),
            effective_policy_hash=source.locked_effective_project_submission_artifact_policy_hash,
            pre_submit_policy_id=UUID(source.locked_pre_submit_checker_policy_id),
            pre_submit_policy_bundle_hash=source.locked_pre_submit_checker_bundle_hash,
        ))
    except ProjectLockedPolicyContextUnavailable:
        return False
    policy = RevisionPolicySemantics.model_validate_json(context.revision_policy.value)
    count = await session.scalar(select(func.count()).select_from(Submission).where(
        Submission.task_assignment_id == assignment.id, Submission.version <= source.version,
        Submission.status_reason.is_distinct_from(COVERAGE_RETURN_REASON),
    ))
    revision_round = count - 1
    if revision_round < policy.max_revision_rounds:
        return False
    if revision_round != policy.max_revision_rounds:
        raise TaskRoutingRequestUnavailable("retained revision count differs")
    receipt_id = new_record_id()
    request_digest = canonical_json_hash({
        "routing_manifest_id": str(manifest.id),
        "preparation_id": str(root.id) if root else None,
        "preparation_sha256": root.preparation_sha256 if root else None,
        "head_preparation_id": str(head.id) if head else None,
        "head_preparation_sha256": head.preparation_sha256 if head else None,
        "exhaustion_receipt_id": str(receipt_id),
        "revision_round": revision_round, "max_revision_rounds": policy.max_revision_rounds,
    })
    context_hash = canonical_json_hash({
        field: str(getattr(task, field)) if isinstance(getattr(task, field), UUID)
        else getattr(task, field) for field in LOCKED_CONTEXT_HASH_FIELDS
    })
    actor_id, decision = await authorization.authorize(TaskRevisionRecoveryFacts(
        project_id=UUID(task.project_id), task_id=UUID(task.id),
        assignment_id=UUID(assignment.id), contributor_id=UUID(assignment.contributor_id),
        routing_manifest_id=manifest.id, locked_context_hash=context_hash,
        request_digest=request_digest, preparation_id=UUID(str(root.id)) if root else None,
        preparation_sha256=root.preparation_sha256 if root else None,
    ))
    receipt = TaskRevisionExhaustion(
        id=receipt_id, project_id=task.project_id, task_id=task.id,
        assignment_id=assignment.id, contributor_id=assignment.contributor_id,
        source_submission_id=source.id, routing_manifest_id=manifest.id,
        revision_round=revision_round, max_revision_rounds=policy.max_revision_rounds,
        revision_policy_id=source.locked_revision_policy_id,
        revision_policy_generation=source.locked_revision_policy_generation,
        revision_policy_hash=source.locked_revision_policy_hash,
        exhausted_at=await session.scalar(select(func.clock_timestamp())),
        authorization_decision_id=str(decision.decision_id), audit_event_id=str(new_record_id()),
        recovery_authority_context=json.loads(decision.resource_context_json),
    )
    event = await outbox.append(revision_exhausted_event(receipt, manifest))
    if event.disposition is not OutboxAppendDisposition.CREATED:
        raise TaskRoutingRequestUnavailable("retained exhaustion outcome differs")
    receipt.outcome_event_id = event.event_id
    await commit_exhaustion(session, receipt=receipt, task=task, assignment=assignment)
    await audit.record_revision_exhaustion(TaskRevisionExhaustionAuditFacts(
        event_id=UUID(receipt.audit_event_id), project_id=UUID(task.project_id),
        task_id=UUID(task.id), assignment_id=UUID(assignment.id), submission_id=UUID(source.id),
        routing_manifest_id=manifest.id, exhaustion_receipt_id=receipt.id,
        actor_profile_id=actor_id, outbox_event_id=event.event_id, authority=decision,
    ))
    await session.flush()
    return True
