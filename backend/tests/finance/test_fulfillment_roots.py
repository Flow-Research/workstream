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
from app.modules.compensation.api.fulfillment import OBLIGATION_DELIVERY_EVENT, fulfillment_obligation
from app.modules.compensation.api.fulfillment_contracts import SOURCE_AWARD_KEYS
from app.modules.compensation.fulfillment.service import (
    CompensationFulfillmentParticipant, CompensationFulfillmentReadiness,
)
from app.modules.outbox.api import OutboxAppendDisposition, OutboxAppendInput, OutboxAppendResult
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


async def _append_native_root_event(session, award, values):
    """Persist the exact selector through the real OUTBOX owner, not a fake."""
    event = await outbox_append(session).append(OutboxAppendInput(
        event_type=OBLIGATION_DELIVERY_EVENT, event_version=1,
        aggregate_type="compensation_fulfillment", aggregate_id=values["id"],
        project_id=award.project_id, correlation_id=str(award.correlation_id),
        idempotency_key=f"compensation.fulfillment:{values['id']}",
        payload={
            "fulfillment_root_id": str(values["id"]), "award_id": str(award.id),
            "adapter_binding_id": str(award.adapter_binding_id),
            "admission_generation": values["admission_generation"],
            "source_award_digest": values["source_award_digest"],
            "obligation_digest": values["obligation_digest"],
        },
    ))
    assert event.disposition is OutboxAppendDisposition.CREATED
    return event.event_id


async def _insert_native_root(session, values):
    """Insert raw values without running the root ORM or participant validation."""
    statement = text("""INSERT INTO public.compensation_fulfillment_roots
        (id,award_id,project_id,ordinal,admission_generation,source_instance_id,
         adapter_binding_id,route_key,source_final_acceptance_id,
         source_authorization_decision_id,source_routing_manifest_id,
         source_award_digest,obligation_digest,obligation_body,initial_outbox_event_id)
        VALUES (:id,:award_id,:project_id,:ordinal,:admission_generation,
         :source_instance_id,:adapter_binding_id,:route_key,:source_final_acceptance_id,
         :source_authorization_decision_id,:source_routing_manifest_id,
         :source_award_digest,:obligation_digest,CAST(:obligation_body AS jsonb),
         :initial_outbox_event_id)""")
    await session.execute(statement, values)


async def test_native_root_insert_rejects_independent_source_substitutions(
    tmp_path, isolated_database_env, monkeypatch, live_acceptance_lifecycle,
):
    """Bypass the root ORM against genuine earning custody and real foreign facts."""
    async with authorized_routing_source(
        tmp_path / "anchor", isolated_database_env, contribution_awards=("money",),
    ) as anchor:
        async with anchor.factory() as session, session.begin():
            await apply_outcome(session, anchor, 2)
        async with authorized_routing_source(
            tmp_path / "candidate", isolated_database_env, contribution_awards=("money",),
            storage_settings=anchor.settings, provision_services=False,
        ) as h:
            async with h.factory() as session:
                foreign = (await session.execute(text(
                    "SELECT * FROM public.compensation_fulfillment_roots"
                ))).mappings().one()
            before = await _snapshot(h.factory)
            captured = []

            async def capture_root_input(_owner, request, awards):
                captured.append((request, awards))

            monkeypatch.setattr(CompensationFulfillmentParticipant, "complete", capture_root_input)
            cases = (
                "source", "ordinal", "generation", "project", "binding", "authorization",
                "manifest", "acceptance", "body", "source_digest", "digest",
                "source_guard_removed", "valid",
            )
            for case in cases:
                async with h.factory() as session:
                    await session.begin()
                    try:
                        captured.clear()
                        await apply_outcome(session, h, 2)
                        assert len(captured) == 1
                        request, (award,) = captured[0]
                        route = await session.scalar(text(
                            "SELECT route_key FROM public.project_compensation_adapter_bindings WHERE id=:id"
                        ), {"id": award.adapter_binding_id})
                        root_id = new_record_id()
                        body = fulfillment_obligation(
                            request, award, source_instance_id=get_settings().source_instance_id,
                            root_id=root_id, route_key=route,
                        )
                        values = dict(
                            id=root_id, award_id=award.id, project_id=award.project_id, ordinal=2,
                            admission_generation=2, source_instance_id=get_settings().source_instance_id,
                            adapter_binding_id=award.adapter_binding_id, route_key=route,
                            source_final_acceptance_id=request.contribution.final_acceptance_id,
                            source_authorization_decision_id=request.source_authorization_decision_id,
                            source_routing_manifest_id=request.source_routing_manifest_id,
                        )
                        if case in {"source", "source_guard_removed"}:
                            values["source_instance_id"] = new_record_id()
                            body["source_instance_id"] = str(values["source_instance_id"])
                        elif case == "ordinal":
                            values["ordinal"] = 3
                        elif case == "generation":
                            values["admission_generation"] = 3
                        elif case in {"project", "binding", "authorization", "manifest", "acceptance"}:
                            column = {
                                "project": "project_id", "binding": "adapter_binding_id",
                                "authorization": "source_authorization_decision_id",
                                "manifest": "source_routing_manifest_id",
                                "acceptance": "source_final_acceptance_id",
                            }[case]
                            original_value = values[column]
                            values[column] = foreign[column]
                            assert str(values[column]) != str(original_value)
                        elif case == "body":
                            body["quantity"] = "999"
                        # Internally consistent digests cannot legitimize a substituted source.
                        body["source_award_digest"] = canonical_json_hash({
                            key: body[key] for key in SOURCE_AWARD_KEYS
                        })
                        body["obligation_digest"] = canonical_json_hash({
                            key: value for key, value in body.items() if key != "obligation_digest"
                        })
                        values.update(
                            source_award_digest=("sha256:" + "0" * 64 if case == "source_digest"
                                                 else body["source_award_digest"]),
                            obligation_digest=("sha256:" + "0" * 64 if case == "digest"
                                               else body["obligation_digest"]),
                            obligation_body=json.dumps(body),
                        )
                        values["initial_outbox_event_id"] = await _append_native_root_event(
                            session, award, values,
                        )
                        expected = ("generation unavailable" if case == "generation" else
                                    "ordinal or source differs" if case in {
                                        "source", "ordinal", "source_guard_removed",
                                    } else "root source differs")
                        if case == "valid":
                            await _insert_native_root(session, values)
                            await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                            await session.commit()
                        elif case == "source_guard_removed":
                            await session.execute(text("ALTER TABLE public.compensation_fulfillment_roots "
                                                       "DISABLE TRIGGER compensation_fulfillment_root_source"))
                            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                                with pytest.raises(DBAPIError, match=expected):
                                    await _insert_native_root(session, values)
                            await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                        else:
                            with pytest.raises(DBAPIError, match=expected):
                                await _insert_native_root(session, values)
                    finally:
                        await session.rollback()
                if case != "valid":
                    assert await _snapshot(h.factory) == before, case
            async with h.factory() as session:
                assert (await session.execute(text("""SELECT ordinal,
                    public.compensation_fulfillment_is_complete(award_id)
                    FROM public.compensation_fulfillment_roots ORDER BY ordinal"""))).all() == [
                        (1, True), (2, True),
                    ]


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
