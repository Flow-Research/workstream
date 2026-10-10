"""Stored completion fixtures; controlled handlers prove classification, not input quality."""

import json
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import select, text

from app.modules.checkers.api.execution import EvaluationCompletion
from app.modules.checkers.api.post_submit import PostSubmitCounter, PostSubmitMemberResult
from app.modules.checkers.models import CheckerRun
from app.modules.checkers.post_submit_contracts import make_post_submit_result
from app.modules.checkers.runner import CheckerOutcome, CheckerRegistry, FunctionChecker, default_checker_registry
from app.modules.outbox.models import OutboxEvent
from tests.post_submit_materialization_helpers import material_fixture
from .support import live_executor, reserve
from .test_concurrency import final_facts


FAILURE_CHECKERS = {
    "needs_revision": "check_submission_packet",
    "task_setup_blocked": "check_policy_context_present",
}


def controlled_registry(recommendation):
    """Keep canonical definitions; change only one selected handler's declared outcome."""
    canonical = default_checker_registry()
    if recommendation == "allow_review":
        return canonical
    definition = canonical.resolve(FAILURE_CHECKERS[recommendation]).definition

    async def declared_failure(context):
        return CheckerOutcome(
            checker_name=definition.capability_id, status=definition.failure_status,
            severity=definition.failure_severity, message="Controlled declared failure.",
        )

    registry = CheckerRegistry()
    for item in canonical.definitions():
        checker = (
            FunctionChecker(item.capability_id, declared_failure)
            if item.capability_id == definition.capability_id
            else canonical.resolve(item.capability_id).checker
        )
        registry.register(checker, definition=item)
    return registry


@asynccontextmanager
async def completed_evidence(tmp_path, database_url, recommendation="needs_revision", *, counters=False, **options):
    """Use real material, AUTH, finalization and publication; never insert a terminal row."""
    async with material_fixture(tmp_path, database_url, **options) as h:
        await reserve(h)
        executor = live_executor(h, registry=controlled_registry(recommendation))
        if counters:
            lease, replay = await executor._claim(h.request)
            assert replay is None
            facts = await final_facts(h, lease)
            definition = h.request.catalogue.definition(FAILURE_CHECKERS[recommendation], "v0.1")
            member = PostSubmitMemberResult(
                checker_id=definition.capability_id, implementation_version=definition.implementation_version,
                status=definition.failure_status, code=definition.failure_code,
                failure_category=definition.failure_category, severity=definition.failure_severity,
                counters=(PostSubmitCounter(key="missing_count", value=2),),
            )
            fields = facts.result.model_dump(exclude={"result_digest"})
            fields["member_results"] = tuple(
                member if m.checker_id == member.checker_id else m for m in facts.result.member_results
            )
            controlled = make_post_submit_result(**fields)
            h.result = await executor.finalize(facts.model_copy(update={"result": controlled}))
        else:
            h.result = await executor.evaluate_post_submission(h.request)
        async with h.factory() as session:
            h.run = await session.get(CheckerRun, str(h.result.attempt_id))
            assert h.run.routing_recommendation == recommendation
            event = await session.scalar(select(OutboxEvent).where(
                OutboxEvent.event_id == h.run.completion_event_id,
            ))
            assert event is not None
            h.completion = EvaluationCompletion.model_validate_json(json.dumps(event.payload))
            h.source = {"completion_event_id": UUID(str(event.event_id))}
        yield h


async def evidence_snapshot(session):
    """Detect owner writes and unintended routing/economic effects during observation."""
    return (await session.execute(text("""
        SELECT (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.checker_runs r),
          (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.checker_results r),
          (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.submission_id) FROM public.checker_submission_fences r),
          (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.route_operation_id) FROM public.task_post_submit_routing_requests r),
          (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.task_post_submit_routing_manifests r),
          (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.workstream_tasks r),
          (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.final_acceptances r),
          (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.contribution_records r),
          (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.compensation_awards r),
          (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM public.audit_events r),
          (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.event_id) FROM public.outbox_events r)
    """))).one()
