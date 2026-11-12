"""Read committed exhaustion for exact replay after task release or later claims."""

import json
from uuid import UUID

from sqlalchemy import func, select

from app.modules.tasks.api.post_submit_routing import (
    TaskPostSubmitSourceProposal, TaskRoutingRequestFacts, TaskRoutingSourcePreparation,
)
from app.modules.tasks.post_submit_routing.models import TaskRoutingRequest
from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequestUnavailable
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.revision.exhaustion import exhaustion_facts
from app.modules.tasks.revision.models import TaskRevisionExhaustion


async def exhausted_source(session, manifest, completion):
    """Return retained facts only; the caller must validate fresh AUTH and delivery custody."""
    receipt = await session.scalar(select(TaskRevisionExhaustion).where(
        TaskRevisionExhaustion.routing_manifest_id == manifest.id,
    ))
    if receipt is None:
        return None
    repo = TaskRepository(session)
    assignment = await repo.lock_accepted_assignment(
        project_id=completion.project_id, task_id=completion.task_id,
        assignment_id=UUID(receipt.assignment_id),
    )
    submission = await repo.lock_exact_submission_for_task(
        project_id=completion.project_id, task_id=completion.task_id,
        submission_id=completion.submission_id,
    )
    if assignment is None or submission is None or not (
        assignment.status == "revision_exhausted"
        and assignment.released_at == receipt.exhausted_at
        and assignment.id == receipt.assignment_id == submission.task_assignment_id
        and submission.id == receipt.source_submission_id == manifest.submission_id
        and receipt.project_id == manifest.project_id
        and receipt.task_id == manifest.task_id
        and receipt.contributor_id == assignment.contributor_id == submission.contributor_id
        and (
            receipt.authorization_decision_id == manifest.authorization_decision_id
            and receipt.audit_event_id == manifest.audit_event_id
            and receipt.outcome_event_id == manifest.outcome_event_id
        )
    ):
        raise TaskRoutingRequestUnavailable("routing terminal source differs")
    if not await session.scalar(select(func.task_revision_exhaustion_complete(receipt.id))):
        raise TaskRoutingRequestUnavailable("routing terminal evidence differs")
    source = TaskPostSubmitSourceProposal.model_validate_json(
        json.dumps(manifest.authority_context["source"])
    )
    request = await session.scalar(select(TaskRoutingRequest).where(
        TaskRoutingRequest.routing_manifest_id == manifest.id,
    ))
    if request is None:
        raise TaskRoutingRequestUnavailable("routing terminal request unavailable")
    fields = {}
    for key in TaskRoutingRequestFacts.model_fields:
        value = getattr(request, key)
        fields[key] = UUID(value) if key in {"project_id", "task_id", "submission_id", "checker_run_id"} else value
    facts = TaskRoutingRequestFacts(**fields)
    ref = completion.reference
    if not (
        facts.project_id == completion.project_id and facts.task_id == completion.task_id
        and facts.submission_id == completion.submission_id
        and facts.checker_run_id == ref.attempt_id
        and facts.evaluation_request_id == ref.request_id
        and facts.evaluation_request_digest == ref.request_digest
        and facts.evaluation_generation == ref.evaluation_generation
        and facts.result_id == ref.result_id and facts.result_digest == ref.result_digest
        and source.execute_evidence_id == completion.execute_evidence_id
        and source.finalize_evidence_id == completion.finalize_evidence_id
        and facts.routing_recommendation == completion.routing_recommendation == "needs_revision"
    ):
        raise TaskRoutingRequestUnavailable("routing terminal completion differs")
    return TaskRoutingSourcePreparation(
        request=facts, source=source, exhaustion=exhaustion_facts(receipt),
    )
