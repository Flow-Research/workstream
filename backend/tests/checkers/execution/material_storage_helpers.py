"""Direct SQL terminal writes, deliberately bypassing the executor's validation."""

from uuid import UUID
import json
from app.adapters.auth import post_submit_execution_authority
from app.modules.checkers.api.execution import FinalizeAuthorityFacts, VerifiedMaterialFacts

from sqlalchemy import func, insert, update

from app.adapters.outbox import outbox_append
from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import COMPLETION_EVENT, EvaluationCompletion
from app.modules.checkers.api.post_submit import PostSubmitCurrentResultReference
from app.modules.checkers.api.post_submit_catalogue import canonical_post_submit_bytes
from app.modules.checkers.execution_results import classify_result
from app.modules.checkers.models import CheckerResult, CheckerRun
from app.modules.outbox.api import OutboxAppendInput


async def write_terminal(session, facts, material, *, authorized_facts=None):
    """Stage all otherwise valid members/event/terminal fields in the caller transaction."""
    request, result = facts.request, facts.result
    run = await session.get(CheckerRun, str(result.attempt_id))
    # An explicit earlier valid receipt can accompany deliberately malformed SQL
    # in database-guard tests; production never accepts the malformed payload.
    authorized = authorized_facts if authorized_facts is not None else facts.model_copy(update={
        "material": VerifiedMaterialFacts.model_validate_json(json.dumps(material)) if material is not None else None,
    })
    authority_facts = FinalizeAuthorityFacts(
        **authorized.model_dump(),
        execute_evidence_id=UUID(run.execute_evidence_id),
    )
    async with post_submit_execution_authority(session).prepare_finalization(request) as prepared:
        evidence_id = (await prepared.consume(authority_facts)).evidence_id
    await stage_terminal(session, facts, material, evidence_id)


async def stage_terminal(session, facts, material, evidence_id):
    """One direct SQL writer, with the caller's explicit receipt and all guards enabled."""
    request, result = facts.request, facts.result
    run = await session.get(CheckerRun, str(result.attempt_id))
    classification = classify_result(request, result)
    for order, member in enumerate(result.member_results):
        await session.execute(insert(CheckerResult).values(
            id=str(new_record_id()), checker_run_id=run.id, task_id=run.task_id,
            submission_id=run.submission_id, member_order=order, checker_name=member.checker_id,
            definition_version=member.definition_version, implementation_version=member.implementation_version,
            status=member.status, severity=member.severity, code=member.code,
            failure_category=member.failure_category,
            counters=[item.model_dump(mode="json") for item in member.counters],
        ))
    event_id = None
    if result.outcome == "completed":
        reference = PostSubmitCurrentResultReference(**result.model_dump(
            include=set(PostSubmitCurrentResultReference.model_fields) - {"schema_version"},
        ))
        event = EvaluationCompletion(
            project_id=request.project_id, task_id=request.task_id, submission_id=request.submission_id,
            reference=reference, routing_recommendation=classification.routing,
            output_binding_ids=(), execute_evidence_id=UUID(run.execute_evidence_id),
            finalize_evidence_id=evidence_id,
        )
        appended = await outbox_append(session).append(OutboxAppendInput(
            event_type=COMPLETION_EVENT, event_version=1, aggregate_type="checker_run",
            aggregate_id=result.attempt_id, project_id=request.project_id,
            correlation_id=str(request.evaluation_request_id), idempotency_key="checker-completed:" + run.id,
            payload=event.model_dump(mode="json"),
        ))
        event_id = appended.event_id
    await session.execute(update(CheckerRun).where(CheckerRun.id == run.id).values(
        status=result.outcome, result_json=canonical_post_submit_bytes(result, exclude={"result_digest"}).decode(),
        result_digest=result.result_digest, material_custody=material, finalize_evidence_id=str(evidence_id),
        completed_at=func.clock_timestamp(), outcome_source="auto_checker",
        routing_recommendation=classification.routing, failure_code=result.infrastructure_failure_code,
        passed_count=classification.passed, warning_count=classification.warning,
        failed_count=classification.failed, blocking_count=classification.blocking,
        completion_event_id=event_id,
    ))
