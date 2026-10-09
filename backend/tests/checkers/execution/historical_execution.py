"""Revision-shaped checker history for migration tests only, never current AUTH proof.

All predecessor database guards remain enabled. No current input receipt is
fabricated: that evidence did not exist in these schema revisions.
"""

from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import insert, text

from app.adapters.outbox import outbox_append
from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import (
    EvaluationReservation,
    ExecutionLease,
    EvaluationCompletion,
    VerifiedMaterialFacts,
    COMPLETION_EVENT,
)
from app.modules.checkers.api.post_submit import (
    PostSubmissionEvaluationRequest,
    PostSubmissionEvaluationResult,
    PostSubmitCurrentResultReference,
)
from app.modules.checkers.api.post_submit_catalogue import canonical_post_submit_bytes
from app.modules.checkers.execution_repository import request_text
from app.modules.checkers.execution_results import classify_result
from app.modules.checkers.models import CheckerRun, CheckerResult
from app.modules.checkers.post_submit_contracts import make_post_submit_result
from app.modules.outbox.api import OutboxAppendInput
from app.modules.tasks.models import AuditEvent
from tests.checkers.post_submit.test_result_contract import result as value_result
from tests.historical_submission_fixtures import historical_material_fixture


class HistoricalTerminalFacts(BaseModel):
    request: PostSubmissionEvaluationRequest
    lease: ExecutionLease
    result: PostSubmissionEvaluationResult
    material: VerifiedMaterialFacts | None


async def historical_revision(session):
    revision = await session.scalar(text("SELECT version_num FROM public.alembic_version"))
    assert 8 <= int(revision[:4]) <= 28, "historical fixture used outside its predecessor schemas"
    assert not await session.scalar(
        text("""SELECT EXISTS(SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name='checker_runs'
        AND column_name='input_materialization_evidence_id')""")
    )
    return int(revision[:4])


async def historical_reserve(h):
    r, c = h.request, h.request.expected_context
    async with h.factory() as session, session.begin():
        await historical_revision(session)
        previous = await session.scalar(
            text(
                "SELECT current_run_id FROM public.checker_submission_fences WHERE submission_id=:id"
            ),
            {"id": r.submission_id},
        )
        run_id, result_id = new_record_id(), new_record_id()
        await session.execute(
            insert(CheckerRun.__table__).values(
                id=str(run_id),
                project_id=str(r.project_id),
                task_id=str(r.task_id),
                submission_id=str(r.submission_id),
                submission_version=r.submission_version,
                evaluation_request_id=str(r.evaluation_request_id),
                phase="post_submission",
                evaluation_generation=r.evaluation_generation,
                request_json=request_text(r),
                request_digest=r.request_sha256,
                result_id=str(result_id),
                trigger_source="coordinated_evaluation",
                status="queued",
                outcome_source="none",
                routing_recommendation="not_evaluated",
                worker_lease_generation=0,
                supersedes_checker_run_id=str(previous) if previous else None,
                locked_guide_version=c.guide_version,
                locked_post_submit_checker_policy_id=str(c.post_policy_id),
                locked_post_submit_checker_policy_version=c.post_policy_version,
                locked_post_submit_checker_policy_hash=c.post_policy_hash,
                locked_review_policy_id=str(c.review_policy_id),
                locked_review_policy_generation=c.review_generation,
                locked_review_policy_hash=c.review_hash,
                locked_revision_policy_id=str(c.revision_policy_id),
                locked_revision_policy_generation=c.revision_generation,
                locked_revision_policy_hash=c.revision_hash,
            )
        )
        await session.execute(
            text("""INSERT INTO public.checker_submission_fences(submission_id,current_run_id)
          VALUES (:submission,:run) ON CONFLICT(submission_id) DO UPDATE SET current_run_id=excluded.current_run_id"""),
            {"submission": r.submission_id, "run": run_id},
        )
    return EvaluationReservation(
        request_id=r.evaluation_request_id,
        request_digest=r.request_sha256,
        attempt_id=run_id,
        result_id=result_id,
        evaluation_generation=r.evaluation_generation,
    )


async def _historical_receipt(session, run_id, phase, receipt_id):
    """Persist the predecessor's exact SQL-validated event shape, not a live permission."""
    row = (
        (
            await session.execute(
                text("""SELECT r.project_id,r.evaluation_request_id,
        public.checker_post_submit_authority_digest(r,:phase) AS digest,
        (SELECT id FROM public.actor_profiles WHERE service_identity='workstream.checker.post_submit') AS actor
      FROM public.checker_runs r WHERE r.id=:id"""),
                {"id": run_id, "phase": phase},
            )
        )
        .mappings()
        .one()
    )
    assert row["actor"] is not None
    now = await session.scalar(text("SELECT clock_timestamp()"))
    await session.execute(
        insert(AuditEvent.__table__).values(
            id=str(receipt_id),
            entity_type="authorization_decision",
            entity_id=str(receipt_id),
            event_type="SensitiveAuthorizationAllowed",
            actor_id=str(row["actor"]),
            actor_roles=[],
            claim_snapshot={},
            auth_source="local_authority",
            is_dev_auth=False,
            event_payload={},
            event_domain="authority",
            event_version=1,
            occurred_at=now,
            reason="authorization_evaluation",
            actor_ref_kind="actor_profile",
            request_id=str(row["evaluation_request_id"]),
            correlation_id=str(row["evaluation_request_id"]),
            action_id="checker.post_submit." + phase,
            permission_id="checker.post_submit." + phase,
            project_id=str(row["project_id"]),
            resource_type="checker_run",
            resource_id=str(run_id),
            target_ref_kind="project",
            target_ref_id=str(row["project_id"]),
            after_facts={"allowed": True, "resource_context_digest": row["digest"]},
        )
    )


async def historical_lease(h):
    async with h.factory() as session, session.begin():
        revision = await historical_revision(session)
        r = (
            (
                await session.execute(
                    text("""SELECT r.* FROM public.checker_runs r
          JOIN public.checker_submission_fences f ON f.current_run_id=r.id WHERE f.submission_id=:id"""),
                    {"id": h.request.submission_id},
                )
            )
            .mappings()
            .one()
        )
        now = await session.scalar(text("SELECT clock_timestamp()"))
        lease = ExecutionLease(
            reservation=EvaluationReservation(
                request_id=UUID(str(r["evaluation_request_id"])),
                request_digest=r["request_digest"],
                attempt_id=UUID(str(r["id"])),
                result_id=UUID(str(r["result_id"])),
                evaluation_generation=r["evaluation_generation"],
            ),
            lease_id=new_record_id(),
            lease_generation=1,
            expires_at=now + timedelta(seconds=300),
        )
        receipt_id = new_record_id()
        await session.execute(
            text("""UPDATE public.checker_runs SET status='running',started_at=:now,
          worker_lease_id=:lease,worker_lease_generation=1,worker_lease_expires_at=:expires,
          execute_evidence_id=:receipt WHERE id=:id"""),
            {
                "id": r["id"],
                "now": now,
                "lease": lease.lease_id,
                "expires": lease.expires_at,
                "receipt": receipt_id,
            },
        )
        if revision >= 10:
            await _historical_receipt(session, r["id"], "execute", receipt_id)
        return lease


def historical_terminal_facts(h, lease, outcome="completed"):
    result = value_result(
        h.request, attempt_id=lease.reservation.attempt_id, result_id=lease.reservation.result_id
    )
    if outcome == "infrastructure_failed":
        result = make_post_submit_result(
            **(
                result.model_dump(exclude={"result_digest"})
                | {
                    "outcome": outcome,
                    "member_results": (),
                    "infrastructure_failure_code": "implementation_unavailable",
                }
            )
        )
    return HistoricalTerminalFacts(
        request=h.request,
        lease=lease,
        result=result,
        material=VerifiedMaterialFacts(
            submission_id=h.request.submission_id,
            submission_version=h.request.submission_version,
            admission_id=h.created.admission_id,
            binding_id=h.request.binding_id,
            content_id=h.request.content_id,
            replica_id=h.replica_id,
            content_sha256=h.request.content_sha256,
            byte_count=h.request.byte_count,
            semantic_manifest_sha256=h.manifest.sha256,
        ),
    )


async def historical_write_terminal(session, facts, material):
    revision = await historical_revision(session)
    request, result = facts.request, facts.result
    run_id = result.attempt_id
    execute_id = await session.scalar(
        text("SELECT execute_evidence_id FROM public.checker_runs WHERE id=:id"), {"id": run_id}
    )
    final_id = new_record_id()
    classification = classify_result(request, result)
    for order, member in enumerate(result.member_results):
        await session.execute(
            insert(CheckerResult.__table__).values(
                id=str(new_record_id()),
                checker_run_id=str(run_id),
                task_id=str(request.task_id),
                submission_id=str(request.submission_id),
                member_order=order,
                checker_name=member.checker_id,
                definition_version=member.definition_version,
                implementation_version=member.implementation_version,
                status=member.status,
                severity=member.severity,
                code=member.code,
                failure_category=member.failure_category,
                counters=[v.model_dump(mode="json") for v in member.counters],
            )
        )
    event_id = None
    if result.outcome == "completed":
        reference = PostSubmitCurrentResultReference(
            **result.model_dump(
                include=set(PostSubmitCurrentResultReference.model_fields) - {"schema_version"}
            )
        )
        event = EvaluationCompletion(
            project_id=request.project_id,
            task_id=request.task_id,
            submission_id=request.submission_id,
            reference=reference,
            routing_recommendation=classification.routing,
            output_binding_ids=(),
            execute_evidence_id=UUID(str(execute_id)),
            finalize_evidence_id=final_id,
        )
        appended = await outbox_append(session).append(
            OutboxAppendInput(
                event_type=COMPLETION_EVENT,
                event_version=1,
                aggregate_type="checker_run",
                aggregate_id=run_id,
                project_id=request.project_id,
                correlation_id=str(request.evaluation_request_id),
                idempotency_key="checker-completed:" + str(run_id),
                payload=event.model_dump(mode="json"),
            )
        )
        event_id = appended.event_id
    import json

    await session.execute(
        text("""UPDATE public.checker_runs SET status=:status,
      result_json=:body,result_digest=:digest,material_custody=CAST(:material AS json),
      finalize_evidence_id=:final,completed_at=clock_timestamp(),outcome_source='auto_checker',
      routing_recommendation=:routing,failure_code=:failure,passed_count=:passed,
      warning_count=:warning,failed_count=:failed,blocking_count=:blocking,completion_event_id=:event WHERE id=:id"""),
        dict(
            id=run_id,
            status=result.outcome,
            body=canonical_post_submit_bytes(result, exclude={"result_digest"}).decode(),
            digest=result.result_digest,
            material=json.dumps(material) if material is not None else None,
            final=final_id,
            routing=classification.routing,
            failure=result.infrastructure_failure_code,
            passed=classification.passed,
            warning=classification.warning,
            failed=classification.failed,
            blocking=classification.blocking,
            event=event_id,
        ),
    )
    if revision >= 10:
        await _historical_receipt(session, run_id, "finalize", final_id)


@asynccontextmanager
async def historical_completed_source(tmp_path, database_url, **options):
    async with historical_material_fixture(tmp_path, database_url, **options) as h:
        await historical_reserve(h)
        lease = await historical_lease(h)
        facts = historical_terminal_facts(h, lease)
        async with h.factory() as session, session.begin():
            await historical_write_terminal(session, facts, facts.material.model_dump(mode="json"))
        h.result, h.material = facts.result, facts.material.model_dump(mode="json")
        async with h.factory() as session:
            r = (
                (
                    await session.execute(
                        text("""SELECT r.*,s.task_assignment_id,s.contributor_id,
              s.contribution_policy_version_id,p.human_review_required FROM public.checker_runs r
              JOIN public.submissions s ON s.id=r.submission_id
              JOIN public.review_policies p ON p.id=s.locked_review_policy_id WHERE r.id=:id"""),
                        {"id": facts.result.attempt_id},
                    )
                )
                .mappings()
                .one()
            )
        names = (
            "project_id",
            "task_id",
            "submission_id",
            "submission_version",
            "contributor_id",
            "contribution_policy_version_id",
            "evaluation_request_id",
            "request_digest",
            "evaluation_generation",
            "result_id",
            "result_digest",
            "completion_event_id",
            "execute_evidence_id",
            "finalize_evidence_id",
            "human_review_required",
        )
        h.source = {name: r[name] for name in names} | {
            "id": new_record_id(),
            "checker_run_id": r["id"],
            "assignment_id": r["task_assignment_id"],
            **{
                name: h.material[name]
                for name in (
                    "replica_id",
                    "content_sha256",
                    "byte_count",
                    "semantic_manifest_sha256",
                )
            },
        }
        for name, value in h.source.items():
            if name.endswith("_id") or name == "id":
                h.source[name] = UUID(str(value))
        yield h
