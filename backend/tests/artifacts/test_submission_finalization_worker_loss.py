"""Actual process death retains accepted custody before and after T5 commit."""
import asyncio
from datetime import timedelta
import multiprocessing
import os
import signal
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import submission_finalization_handler
from app.adapters.auth import outbox_dispatch_authorization
from app.adapters.checkers import selected_pre_submit_coordinator
from app.adapters.outbox import outbox_append, outbox_delivery
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.intake.models import SubmissionIntakeOperation
from app.modules.outbox.api import DeliveryOptions, HandlerOutcome
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.registry import HandlerRegistry
from tests.artifact_store_helpers import initialize_local_store
from tests.artifacts.intake_acceptance_support import completed_source
from tests.artifacts.test_submission_intake_admission import admission_intake as admission_intake
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env, clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import (
    signed_access as signed_access, admin_access as admin_access,
)
from tests.checkers.execution.support import provision_post_submit_service
from tests.test_artifact_admission import _settings


def _delivery(factory, path, *, kill_at=None, observations=None, forbid_observation=False):
    store = initialize_local_store(root=path / "durable", buffer_bytes=256 * 1024)

    class ObservedStore:
        async def observe_sealed_source(self, source):
            if kill_at == "before_observation":
                os.kill(os.getpid(), signal.SIGKILL)
            assert not forbid_observation, "committed finalization reread source"
            if observations is not None:
                observations.append(source)
            return await store.observe_sealed_source(source)

    handler = submission_finalization_handler(sessions=factory, settings=_settings(path),
        store=ObservedStore(), lease_duration=timedelta(seconds=15))

    async def invoke(envelope):
        result = await handler(envelope)
        assert result == HandlerOutcome.ACKNOWLEDGE
        if kill_at == "after_commit":
            os.kill(os.getpid(), signal.SIGKILL)
        return result

    event = ("SubmissionFinalizationRequested", 1)
    return outbox_delivery(factory, authorization_factory=outbox_dispatch_authorization,
        registry=HandlerRegistry([(*event, invoke)], replay_safe=frozenset({event})),
        options=DeliveryOptions(lease_seconds=15, handler_timeout_seconds=14,
            retry_base_seconds=1, retry_cap_seconds=1)), store


def _crash_worker(database_url, path, event_id, project_id, kill_at):
    """Use fresh SQL resources in a process which cannot run cleanup on SIGKILL."""
    async def run():
        engine = create_async_engine(database_url)
        delivery, store = _delivery(async_sessionmaker(engine, expire_on_commit=False), path, kill_at=kill_at)
        try:
            await delivery.deliver(event_id, project_id, "killed-finalizer")
        finally:
            store.close()
            await engine.dispose()
    asyncio.run(run())


async def _wait_until_database_time(factory, target):
    """The lease uses PostgreSQL wall time, not the test process's sleep clock."""
    async with asyncio.timeout(30):
        while True:
            async with factory() as session:
                now = await session.scalar(select(func.clock_timestamp()))
            if now >= target:
                return
            await asyncio.sleep(min(0.1, (target - now).total_seconds()))


@pytest.mark.parametrize("kill_at", ["before_observation", "after_commit"])
async def test_sigkill_finalizer_recovers_exact_accepted_operation(admission_intake, tmp_path, kill_at):
    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    await f.admission.accept(owner, request, terminal.terminal_digest,
        checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    for identity in (ServiceIdentity.ARTIFACT_BINDING, ServiceIdentity.OUTBOX_DISPATCHER):
        await provision_post_submit_service(f.factory, identity)
    async with f.factory() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        event_id = UUID(row.finalization_event_id)
    process = multiprocessing.get_context("fork").Process(target=_crash_worker, args=(
        f.factory.kw["bind"].url, tmp_path, event_id, f.project, kill_at))
    observations = []
    delivery, store = _delivery(f.factory, tmp_path, observations=observations,
        forbid_observation=kill_at == "after_commit")
    process.start()
    try:
        await asyncio.to_thread(process.join, 45)
        assert not process.is_alive(), "finalizer did not reach crash boundary"
        assert process.exitcode == -signal.SIGKILL
        async with f.factory() as session:
            row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
            event = await session.get(OutboxEvent, event_id)
            assert event.delivery_state == "claimed" and event.attempt_count == 1
            assert row.state == ("finalized" if kill_at == "after_commit" else "finalization_pending")
            original_submission = row.finalized_submission_id
            ready_at = max(event.claim_expires_at, row.continuation_expires_at)
        await _wait_until_database_time(f.factory, ready_at)
        assert await delivery.recover(event_id, f.project) is not None
        async with f.factory() as session:
            event = await session.get(OutboxEvent, event_id)
            assert event.delivery_state == "retryable"
            ready_at = event.next_attempt_at
        await _wait_until_database_time(f.factory, ready_at)
        assert await delivery.deliver(event_id, f.project, "replacement-finalizer") is not None
        async with f.factory() as session:
            row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
            event = await session.get(OutboxEvent, event_id)
            assert row.state == "finalized" and event.delivery_state == "acknowledged"
            assert event.attempt_count == 2
            assert row.continuation_generation == (1 if kill_at == "after_commit" else 2)
            if original_submission is not None:
                assert row.finalized_submission_id == original_submission
            for table in ("submissions", "submission_dispatches", "checker_runs"):
                assert await session.scalar(text(f"SELECT count(*) FROM {table} WHERE task_id=:id"), {"id": f.task}) == 1
            assert await session.scalar(text("SELECT count(*) FROM artifact_bindings WHERE resource_id=:id"),
                {"id": row.finalized_submission_id}) == 1
            assert await session.scalar(text("SELECT count(*) FROM outbox_events WHERE project_id=:id "
                "AND event_type='PostSubmissionEvaluationRequested'"), {"id": f.project}) == 1
        assert observations == ([] if kill_at == "after_commit" else [request.source])
    finally:
        if process.is_alive():
            process.kill()
        await asyncio.to_thread(process.join, 5)
        assert not process.is_alive(), "crash worker cleanup failed"
        process.close()
        store.close()
