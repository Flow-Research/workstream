"""Explicit one-hour real-clock proof: pytest -q tests/artifacts/revision_deadline_drill.py.

Kept outside default test_ collection because policy windows cannot be shorter
than one hour. Use the isolated runner with --timeout-seconds 4500. Scripted
source/PRE transport; real acceptance, PostgreSQL clock, authority and OUTBOX T5.
"""
import asyncio
from unittest.mock import patch

from sqlalchemy import text

from app.db import session as db_session
from app.modules.checkers.api.execution import REQUEST_EVENT
from app.modules.artifacts.intake.finalization import AcceptedSubmissionFinalization
from tests.submission_fixtures import seed_retained_submission, route_retained_checker_remediation
from tests.retained_material_fixtures import finalize_retained_intake
from tests.test_tasks import (
    task_client, task_database_env,  # noqa: F401 -- pytest fixtures
    create_active_project, create_started_task, complete_submission_payload, set_dev_actor,
)


async def test_accepted_revision_finishes_after_original_deadline(task_client, monkeypatch):  # noqa: F811
    project = await create_active_project(task_client, revision_deadline_hours=1)
    task = await create_started_task(task_client, project["id"], monkeypatch)
    first = await seed_retained_submission(task["id"], complete_submission_payload())
    await route_retained_checker_remediation(first)
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    observed = []

    async def delayed(factory, intake):
        async with factory() as session:
            row = (await session.execute(text("""
                SELECT o.accepted_at,p.deadline_at,o.acceptance_receipt,o.state
                FROM submission_intake_operations o JOIN task_revision_preparations p
                  ON p.id=(o.command_metadata->>'revision_preparation_id')::uuid WHERE o.id=:id
            """), {"id": intake.operation_id})).one()
        assert row.state == "finalization_pending" and row.accepted_at < row.deadline_at
        while True:
            async with factory() as session:
                remaining = await session.scalar(text(
                    "SELECT extract(epoch FROM (CAST(:deadline AS timestamptz)-clock_timestamp()))"
                ), {"deadline": row.deadline_at})
            if remaining <= 0:
                break
            await asyncio.sleep(min(30, float(remaining) + 0.01))
        run = AcceptedSubmissionFinalization.run
        replays = []

        async def run_and_replay(finalizer, operation_id):
            first_result = await run(finalizer, operation_id)
            replay = await run(finalizer, operation_id)
            assert replay == first_result
            replays.append(operation_id)
            return first_result

        with patch.object(AcceptedSubmissionFinalization, "run", run_and_replay):
            result = await finalize_retained_intake(factory, intake)
        assert replays == [intake.operation_id]
        async with factory() as session:
            final = (await session.execute(text("""
                SELECT o.state,o.acceptance_receipt,o.finalized_at,o.finalized_submission_id,
                       a.status,a.consumed_by_submission_id,t.active_submission_operation_id
                FROM submission_intake_operations o JOIN submission_bundle_admissions a
                  ON a.id=o.finalized_admission_id JOIN workstream_tasks t ON t.id=o.task_id
                WHERE o.id=:id
            """), {"id": intake.operation_id})).one()
        assert final.state == "finalized" and final.acceptance_receipt == row.acceptance_receipt
        assert final.finalized_at >= row.deadline_at
        assert str(final.finalized_submission_id) == result == str(final.consumed_by_submission_id)
        assert final.status == "consumed" and final.active_submission_operation_id is None
        observed.append(result)
        return result

    with patch("tests.submission_fixtures.finalize_retained_intake", delayed):
        second = await seed_retained_submission(task["id"], complete_submission_payload(), predecessor_id=first)
    assert observed == [second]
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(text("SELECT count(*) FROM submissions WHERE task_id=:id"), {"id": task["id"]}) == 2
        assert await session.scalar(text("SELECT count(*) FROM submission_dispatches WHERE submission_id=:id"), {"id": second}) == 1
        assert await session.scalar(text("""
            SELECT count(*) FROM outbox_events WHERE event_type=:event_type
              AND payload->>'submission_id'=:id
        """), {"id": second, "event_type": REQUEST_EVENT}) == 1
