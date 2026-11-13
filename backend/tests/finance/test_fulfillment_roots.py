"""Native earning closure, source identity and immutable fulfillment custody."""

import asyncio
import json
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.adapters.compensation import (
    FulfillmentLifecycleFenceAdapter, compensation_fulfillment_readiness,
)
from app.adapters.outbox import outbox_append
from app.modules.compensation.api import CompensationAwardConflict
from app.modules.compensation.api.fulfillment import OBLIGATION_DELIVERY_EVENT
from app.modules.compensation.fulfillment.service import (
    CompensationFulfillmentParticipant, CompensationFulfillmentReadiness,
)
from app.modules.outbox.api import OutboxAppendDisposition, OutboxAppendResult
from app.modules.outbox.service import OutboxService
from app.modules.reviews.api.lifecycle import JointLifecycleUnavailable
from app.modules.reviews.lifecycle.fence import PostgresJointLifecycleMutationFence
from tests.contributions.records.support import authorized_submitter_source
from tests.contributions.participation.support import complete_award_request_for, request_for
from tests.reviews.lifecycle.transition_support import command_for, snapshot, transition
from tests.reviews.lifecycle.test_fence import observe_advisory_wait
from tests.tasks.post_submit_routing.outcome_support import (
    apply_outcome, authorized_routing_source, outcome_snapshot,
)


async def _snapshot(factory):
    async with factory() as session:
        return await outcome_snapshot(session), await session.scalar(text(
            "SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY r.id),'[]'::jsonb) "
            "FROM public.compensation_fulfillment_roots r"
        ))


async def test_fulfillment_closure_rolls_back_incomplete_earning(
    tmp_path, isolated_database_env, monkeypatch, live_acceptance_lifecycle,
):
    async with authorized_routing_source(tmp_path, isolated_database_env,
                                         contribution_awards=("money",)) as h:
        before = await _snapshot(h.factory)
        original_append = OutboxService.append

        async def no_root(_owner, _request, _awards):
            return None

        for mode in ("missing_root", "missing_event", "wrong_event", "guard_removed", "complete"):
            with monkeypatch.context() as patch:
                if mode in {"missing_root", "guard_removed"}:
                    patch.setattr(CompensationFulfillmentParticipant, "complete", no_root)
                if mode in {"missing_event", "wrong_event"}:
                    async def wrong_append(owner, value):
                        if value.event_type != OBLIGATION_DELIVERY_EVENT:
                            return await original_append(owner, value)
                        return OutboxAppendResult(
                            event_id=(new_record_id() if mode == "missing_event" else h.envelope.claim.event_id),
                            disposition=OutboxAppendDisposition.CREATED,
                            payload_digest=canonical_json_hash(value.payload), occurred_at=h.envelope.occurred_at,
                        )
                    patch.setattr(OutboxService, "append", wrong_append)
                async with h.factory() as session:
                    await session.begin()
                    try:
                        if mode == "missing_event":
                            # Defer only this FK so the independent closure guard is reached.
                            name = await session.scalar(text("""SELECT conname FROM pg_constraint
                                WHERE conrelid='public.compensation_fulfillment_roots'::regclass
                                  AND confrelid='public.outbox_events'::regclass AND contype='f'"""))
                            assert name and name.replace("_", "").isalnum()
                            await session.execute(text(f'ALTER TABLE public.compensation_fulfillment_roots '
                                f'ALTER CONSTRAINT "{name}" DEFERRABLE INITIALLY DEFERRED'))
                        if mode == "guard_removed":
                            await session.execute(text("ALTER TABLE public.compensation_awards "
                                "DISABLE TRIGGER compensation_award_fulfillment_closure"))
                        result = await apply_outcome(session, h, 2)
                        assert result.economic is not None
                        assert await session.scalar(text("SELECT count(*) FROM public.compensation_awards")) == 1
                        target = ("compensation_award_fulfillment_closure" if mode in {"missing_root", "guard_removed"}
                                  else "compensation_root_fulfillment_closure")
                        if mode == "complete":
                            await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                            await session.commit()
                        elif mode == "guard_removed":
                            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                                with pytest.raises(DBAPIError, match="fulfillment custody incomplete"):
                                    await session.execute(text(f"SET CONSTRAINTS {target} IMMEDIATE"))
                        else:
                            with pytest.raises(DBAPIError, match="fulfillment custody incomplete"):
                                await session.execute(text(f"SET CONSTRAINTS {target} IMMEDIATE"))
                    finally:
                        await session.rollback()
            if mode != "complete":
                assert await _snapshot(h.factory) == before
                async with h.factory() as session:
                    assert await session.scalar(text(
                        "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgenabled='D'"
                    )) == 0
        committed = await _snapshot(h.factory)
        async with h.factory() as session, session.begin():
            assert (await apply_outcome(session, h, 2)).replayed
        assert await _snapshot(h.factory) == committed
        async with h.factory() as session:
            root_id = await session.scalar(text("SELECT id FROM public.compensation_fulfillment_roots"))
        for statement in ("UPDATE public.compensation_fulfillment_roots SET ordinal=ordinal+1 WHERE id=:id",
                          "DELETE FROM public.compensation_fulfillment_roots WHERE id=:id"):
            async with h.factory() as session:
                with pytest.raises(DBAPIError, match="immutable"):
                    async with session.begin():
                        await session.execute(text(statement), {"id": root_id})
        assert await _snapshot(h.factory) == committed


async def test_root_retains_suspended_original_binding_and_source_on_restart(
    tmp_path, isolated_database_env, live_acceptance_lifecycle,
):
    async with authorized_submitter_source(tmp_path, isolated_database_env, paid=True,
                                           retire_before_outcome=True) as h:
        before = await _snapshot(h.factory)
        async with h.factory() as session, session.begin():
            root = (await session.execute(text("""SELECT r.source_instance_id,r.adapter_binding_id,r.route_key,
                r.obligation_body,b.status,b.route_key AS binding_route
                FROM public.compensation_fulfillment_roots r
                JOIN public.project_compensation_adapter_bindings b ON b.id=r.adapter_binding_id"""))).one()
            assert root[1] == h.participation.awards[0].adapter_binding_id
            assert root[2] == root[5] and root[4] == "suspended"
            assert json.loads(json.dumps(root[3]))["adapter_binding_id"] == str(root[1])
            # A new process composition retains the same explicitly configured source.
            assert await CompensationFulfillmentReadiness(session, UUID(str(root[0]))).require_source_ready() == root[0]
            with pytest.raises(CompensationAwardConflict, match="source_unavailable"):
                await CompensationFulfillmentReadiness(session, new_record_id()).require_source_ready()
        assert await _snapshot(h.factory) == before


async def test_live_activation_requires_actual_source_configuration(admin_access, monkeypatch):
    access = admin_access
    await access.signed.grant(access.admin, access.target)
    await transition(await command_for(access.target.id, "shadow"))
    live = await command_for(access.target.id, "live")
    before = await snapshot()
    monkeypatch.delenv("WORKSTREAM_SOURCE_INSTANCE_ID")
    get_settings.cache_clear()
    with pytest.raises(JointLifecycleUnavailable, match="source configuration unavailable"):
        await transition(live)
    assert await snapshot() == before
    monkeypatch.setenv("WORKSTREAM_SOURCE_INSTANCE_ID", "019a78b0-0000-7000-8000-000000000040")
    get_settings.cache_clear()
    assert (await transition(live)).phase == "live"


async def test_compensation_root_requires_current_root_fence(
    tmp_path, isolated_database_env, live_acceptance_lifecycle,
):
    async with authorized_submitter_source(tmp_path, isolated_database_env, paid=True) as h:
        request = complete_award_request_for(h, request_for(h, acceptance_disposition="replay"))
        before = await _snapshot(h.factory)
        for mode in ("closed", "stale", "nested", "raw_savepoint", "valid"):
            async with h.factory() as session:
                await session.begin()
                try:
                    fence = PostgresJointLifecycleMutationFence(session)
                    checked = request
                    if mode == "closed":
                        async with fence.hold(2) as held:
                            pass
                        fence = held
                    elif mode == "stale":
                        checked = request.model_copy(update={"expected_generation": 3})
                    elif mode == "nested":
                        await session.begin_nested()
                    elif mode == "raw_savepoint":
                        await session.execute(text("SAVEPOINT root_custody_probe"))
                        assert not session.in_nested_transaction()
                    owner = CompensationFulfillmentParticipant(
                        session, fence=FulfillmentLifecycleFenceAdapter(fence),
                        outbox=outbox_append(session), source=compensation_fulfillment_readiness(session),
                    )
                    if mode == "valid":
                        assert await owner.complete(checked, h.participation.awards) is None
                    else:
                        with pytest.raises(CompensationAwardConflict, match="fulfillment_unavailable"):
                            await owner.complete(checked, h.participation.awards)
                finally:
                    await session.rollback()
            assert await _snapshot(h.factory) == before


@pytest.mark.parametrize("rollback_first", [False, True], ids=["commit", "rollback"])
async def test_fulfillment_ordinals_serialize_distinct_acceptances(
    tmp_path, isolated_database_env, live_acceptance_lifecycle, rollback_first,
):
    async with authorized_routing_source(tmp_path / "first", isolated_database_env,
                                         contribution_awards=("money",)) as first:
        async with authorized_routing_source(tmp_path / "second", isolated_database_env,
                                             contribution_awards=("money",), storage_settings=first.settings,
                                             provision_services=False) as second:
            pids = asyncio.Queue()

            async def contender():
                async with second.factory() as session, session.begin():
                    await pids.put(await session.scalar(text("SELECT pg_backend_pid()")))
                    return await apply_outcome(session, second, 2)

            pending = None
            async with first.factory() as session:
                await session.begin()
                # Hold actual REV custody before any root can allocate an ordinal.
                await PostgresJointLifecycleMutationFence(session).acquire(2)
                try:
                    pending = asyncio.create_task(contender())
                    pid = await asyncio.wait_for(pids.get(), 10)
                    await observe_advisory_wait(first.factory, pid, pending)
                    await apply_outcome(session, first, 2)
                    if rollback_first:
                        await session.rollback()
                    else:
                        await session.commit()
                    await asyncio.wait_for(pending, 30)
                    if rollback_first:
                        async with session.begin():
                            await apply_outcome(session, first, 2)
                finally:
                    await session.rollback()
                    if pending is not None:
                        if not pending.done():
                            pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)
            async with first.factory() as session:
                rows = (await session.execute(text("""SELECT ordinal,obligation_body->>'task_id',
                    public.compensation_fulfillment_is_complete(award_id)
                    FROM public.compensation_fulfillment_roots ORDER BY ordinal"""))).all()
                expected = [second.request.task_id, first.request.task_id] if rollback_first else [
                    first.request.task_id, second.request.task_id,
                ]
                assert rows == [(ordinal, str(task), True) for ordinal, task in enumerate(expected, 1)]
