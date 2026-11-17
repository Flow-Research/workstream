"""Real phase boundaries: committed execution cannot outlive revoked delivery custody."""

import asyncio

import pytest
from sqlalchemy import text

from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from app.modules.outbox.api import DeliveryOptions, FinalizationCause, HandlerOutcome
from tests.post_submit_materialization_helpers import material_fixture
from .support import delivery_fixture, invoked, state, outcome


async def test_expired_invocation_cannot_start_execution(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        d = await delivery_fixture(h, options=DeliveryOptions(lease_seconds=2, handler_timeout_seconds=1))
        envelope = await invoked(h, d)
        before = await state(h)
        async with h.factory() as session:
            await session.execute(text("select pg_sleep(greatest(0, extract(epoch from "
                                       "(:deadline - clock_timestamp()))) + 0.02)"),
                                  {"deadline": envelope.claim.claim_expires_at})
        assert await d.handler(envelope) is HandlerOutcome.REJECT
        assert await state(h) == before and not h.store.opens


async def test_expired_execution_is_not_renewed(tmp_path, isolated_database_env, monkeypatch):
    import app.modules.checkers.execution as execution

    async with material_fixture(tmp_path, isolated_database_env) as h:
        d = await delivery_fixture(h)
        envelope = await invoked(h, d)
        executor = d.handler._executor(envelope, h.request)
        with monkeypatch.context() as patch:
            patch.setattr(executor, "_execution_budget_seconds", lambda _request: 1)
            patch.setattr(execution, "SELECTED_POST_FINALIZATION_MARGIN_MS", 9_000)
            lease, replay = await executor._claim(h.request)
        assert replay is None and lease.lease_generation == 1
        before = await state(h)
        async with h.factory() as session:
            assert await session.scalar(text(
                "SELECT EXTRACT(EPOCH FROM worker_lease_expires_at-started_at) "
                "FROM public.checker_runs WHERE id=:id"
            ), {"id": lease.reservation.attempt_id}) == 10
            await session.execute(text("select pg_sleep(greatest(0, extract(epoch from "
                                       "(:deadline - clock_timestamp()))) + 0.02)"),
                                  {"deadline": lease.expires_at})
            assert await session.scalar(text("SELECT clock_timestamp()>=:expiry"),
                                        {"expiry": lease.expires_at})
        with pytest.raises(CheckerExecutionUnavailable, match="checker_delivery_execution_unavailable"):
            await d.handler(envelope)
        assert await state(h) == before and not h.store.opens and not h.preparation._active
        receipt = await d.delivery.finalize(envelope.claim, FinalizationCause.UNKNOWN)
        assert outcome(receipt)["invocation_unknown"] is True
        assert await d.delivery.deliver(h.created.evaluation_event_id, h.request.project_id, "retry") is None


async def test_delivery_closed_during_io_cannot_publish_terminal(tmp_path, isolated_database_env, monkeypatch):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        d = await delivery_fixture(h)
        envelope = await invoked(h, d)
        entered, release = asyncio.Event(), asyncio.Event()
        original = h.store.open_source

        async def paused(reference, **kwargs):
            source = original(reference, **kwargs)
            try:
                entered.set()
                await release.wait()
                async for chunk in source:
                    yield chunk
            finally:
                await source.aclose()

        monkeypatch.setattr(h.store, "open_source", paused)
        operation = asyncio.create_task(d.handler(envelope))
        try:
            await asyncio.wait_for(entered.wait(), 20)
            running = await state(h)
            assert running["run"]["status"] == "running"
            assert running["run"]["worker_lease_generation"] == 1
            assert running["run"]["execute_evidence_id"] is not None
            assert running["run"]["finalize_evidence_id"] is None
            # Real dispatcher transaction must complete while I/O is paused.
            receipt = await asyncio.wait_for(
                d.delivery.finalize(envelope.claim, FinalizationCause.UNKNOWN), 10,
            )
            assert outcome(receipt)["invocation_unknown"] is True
            release.set()
            with pytest.raises(CheckerExecutionUnavailable, match="checker_delivery_invocation_unavailable"):
                await asyncio.wait_for(operation, 20)
            assert await state(h) == running
            assert running["members"] == running["events"] == 0
            assert not h.preparation._active and not list((h.scratch / "workspaces").iterdir())
            assert len(h.store.opens) == 1
            assert await d.delivery.deliver(h.created.evaluation_event_id, h.request.project_id, "again") is None
            assert len(h.store.opens) == 1
        finally:
            release.set()
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)


async def test_cancellation_after_execute_preserves_unknown(tmp_path, isolated_database_env, monkeypatch):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        d = await delivery_fixture(h)
        envelope = await invoked(h, d)
        entered = asyncio.Event()
        original = h.store.open_source

        async def paused(reference, **kwargs):
            source = original(reference, **kwargs)
            try:
                entered.set()
                await asyncio.Event().wait()
                async for chunk in source:
                    yield chunk
            finally:
                await source.aclose()

        monkeypatch.setattr(h.store, "open_source", paused)
        operation = asyncio.create_task(d.handler(envelope))
        try:
            await asyncio.wait_for(entered.wait(), 20)
            running = await state(h)
            operation.cancel()
            with pytest.raises(asyncio.CancelledError):
                await operation
            receipt = await d.delivery.finalize(envelope.claim, FinalizationCause.UNKNOWN)
            assert outcome(receipt)["invocation_unknown"] is True
            assert await state(h) == running
            assert not h.preparation._active and not list((h.scratch / "workspaces").iterdir())
            assert await d.delivery.deliver(h.created.evaluation_event_id, h.request.project_id, "again") is None
            assert len(h.store.opens) == 1
        finally:
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
