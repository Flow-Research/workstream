"""Stored selected completion fixtures with no routing or acceptance shortcut."""

import json
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import select, text

from app.modules.checkers.api.execution import EvaluationCompletion
from app.modules.checkers.models import CheckerRun
from app.modules.outbox.models import OutboxEvent
from tests.checkers.external.support import post_registry_spec
from tests.post_submit_materialization_helpers import material_fixture
from .support import ControlledSelectedExecution, live_executor, reserve


@asynccontextmanager
async def completed_evidence(
    tmp_path, database_url, recommendation="needs_revision", *, findings=None, **options,
):
    """Use real selected material, AUTH, finalization and event publication.

    ``findings`` replaces the default single error finding; the verdict follows
    the contract (failed exactly when an error finding exists).
    """
    if recommendation not in {"allow_review", "needs_revision"}:
        raise ValueError("selected completion recommendation is unsupported")
    failed = recommendation == "needs_revision"
    verdict = (
        ("failed" if failed else "passed") if findings is None
        else "failed" if any(item["level"] == "error" for item in findings) else "passed"
    )
    async with material_fixture(
        tmp_path,
        database_url,
        post_submit_registry_spec=post_registry_spec(),
        **options,
    ) as h:
        await reserve(h)
        h.result = await live_executor(
            h,
            selected_execution=ControlledSelectedExecution(verdict=verdict, findings=findings),
        ).evaluate_post_submission(h.request)
        async with h.factory() as session:
            h.run = await session.get(CheckerRun, str(h.result.attempt_id))
            assert h.run.routing_recommendation == recommendation, (
                h.run.status, h.run.outcome_source, h.run.routing_recommendation,
            )
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
