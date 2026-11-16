"""Retained checker failures gain exact expiry coverage through service discovery."""

import asyncio
import json
from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.adapters.tasks import scan_task_revision_sources, task_revision_recovery
from app.core.identifiers import new_record_id
from app.modules.outbox.models import OutboxEvent
from app.modules.projects.api import ProjectLockedPolicyContextUnavailable
from app.modules.tasks.revision.expiry_event import revision_preparation_event
from app.modules.tasks.revision.models import TaskRevisionPreparation
from app.modules.tasks.post_submit_routing.models import TaskPostSubmitRoutingManifest
from app.modules.tasks.repository import TaskRepository
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import activate_successor_guide
from tests.tasks.submission_dispatch.test_revision_capacity import _retain_pre_revision_source
from tests.tasks.submission_dispatch.test_revision_expiry import _provision_expirer
from tests.test_submission_predecessor_custody import _fixture_revision_context


async def _recovery_source_custody(h, source_id):
    """Include immutable evidence and physical rows without new recovery receipts."""
    async with h.factory() as session:
        return (await session.execute(text("""
            SELECT to_jsonb(t),t.xmin::text,to_jsonb(a),a.xmin::text,
              to_jsonb(s),s.xmin::text,to_jsonb(m),m.xmin::text,
              (SELECT jsonb_agg(jsonb_build_array(to_jsonb(p),p.xmin::text) ORDER BY p.sequence)
                 FROM public.task_revision_preparations p WHERE p.routing_manifest_id=m.id),
              (SELECT count(*) FROM public.task_revision_exhaustions),
              (SELECT count(*) FROM public.task_revision_expirations)
            FROM public.task_post_submit_routing_manifests m
            JOIN public.workstream_tasks t ON t.id=m.task_id
            JOIN public.task_assignments a ON a.id=m.assignment_id
            JOIN public.submissions s ON s.id=m.submission_id WHERE m.id=:id
        """), {"id": source_id})).one()


@pytest.mark.parametrize("existing_root", [False, True])
async def test_unavailable_locked_policy_preserves_existing_root_event_recovery(
    tmp_path, isolated_database_env, monkeypatch, existing_root,
):
    """A missing PROJECT context cannot prevent exact frozen-head event recovery."""
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        await _provision_expirer(h.factory)
        if existing_root:
            async with h.factory() as session, session.begin():
                root = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
                manifest = await session.get(TaskPostSubmitRoutingManifest, source_id)
                expected = revision_preparation_event(manifest, root)
                await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                await session.execute(text(
                    "ALTER TABLE public.outbox_events DISABLE TRIGGER outbox_events_custody"
                ))
                removed = await session.execute(text("""
                    DELETE FROM public.outbox_events WHERE idempotency_key=:key
                      AND event_type='TaskRevisionExpiryRequested' AND attempt_count=0
                      AND claimed_at IS NULL AND delivery_state='pending' RETURNING event_id
                """), {"key": expected.idempotency_key})
                assert len(removed.all()) == 1
                await session.execute(text(
                    "ALTER TABLE public.outbox_events ENABLE TRIGGER outbox_events_custody"
                ))
        else:
            await _retain_pre_revision_source(h, source_id)
        before = await _recovery_source_custody(h, source_id)
        unavailable_calls = []

        async def unavailable(request):
            unavailable_calls.append(request)
            assert request.project_id == h.request.project_id
            raise ProjectLockedPolicyContextUnavailable("project_locked_policy_context_changed")

        for attempt in range(2):
            async with h.factory() as session, session.begin():
                recovery = task_revision_recovery(session)
                monkeypatch.setattr(recovery._projects, "lock_locked_policy_context", unavailable)
                assert await recovery.recover(source_id) is (existing_root and attempt == 0)
            assert await _recovery_source_custody(h, source_id) == before
        if existing_root:
            assert unavailable_calls == []  # Frozen root recovery never needs mutable guide facts.
        else:
            assert unavailable_calls  # A new context still fails closed against its current owner.
        async with h.factory() as session:
            events = (await session.scalars(select(OutboxEvent).where(
                OutboxEvent.idempotency_key == f"task.revision.expire:{source_id}",
            ))).all()
            assert len(events) == int(existing_root)
            if existing_root:
                event = events[0]
                assert event.project_id == str(expected.project_id)
                for field in ("event_type", "event_version", "aggregate_type", "aggregate_id",
                              "correlation_id", "causation_event_id",
                              "idempotency_key", "payload", "not_before_at"):
                    assert getattr(event, field) == getattr(expected, field), field
            assert await session.scalar(text("""
                SELECT count(*) FROM public.audit_events
                WHERE event_type='TaskRevisionContextRepaired'
                  AND event_payload->'references'->>'routing_manifest_id'=:source
            """), {"source": str(source_id)}) == int(existing_root)


@pytest.mark.parametrize("new_active_guide", [False, True])
async def test_discovery_freezes_original_retained_window_without_pm_or_rebase(
    tmp_path, isolated_database_env, new_active_guide,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        await _retain_pre_revision_source(h, source_id)
        if new_active_guide:
            await activate_successor_guide(h)
        service_actor = await _provision_expirer(h.factory)
        async with h.factory() as session:
            before = await session.scalar(text(
                "SELECT public.revision_task_lineage(to_jsonb(t)) "
                "FROM public.workstream_tasks t WHERE t.id=:task"
            ), {"task": h.request.task_id})
            source_window = (await session.execute(text("""
                SELECT m.created_at,
                       m.created_at+make_interval(hours=>p.revision_deadline_hours)
                FROM public.task_post_submit_routing_manifests m
                JOIN public.submissions s ON s.id=m.submission_id
                JOIN public.revision_policies p ON p.id=s.locked_revision_policy_id
                WHERE m.id=:source
            """), {"source": source_id})).one()

        recovered, _ = await scan_task_revision_sources(h.factory, None)
        if recovered != 1:
            # The scheduler deliberately isolates one bad source. Re-run the
            # same locked operation in a rolled-back test transaction to show
            # only bounded validation locations and types in a failure.
            try:
                async with h.factory() as session, session.begin():
                    await task_revision_recovery(session).recover(source_id)
                    raise AssertionError("recovery source was skipped without an error")
            except ValidationError as exc:
                pytest.fail(str([(item["loc"], item["type"]) for item in exc.errors()]))
        assert recovered == 1
        repeated, _ = await scan_task_revision_sources(h.factory, None)
        assert repeated == 0
        async with h.factory() as session:
            rows = (await session.scalars(select(TaskRevisionPreparation).where(
                TaskRevisionPreparation.routing_manifest_id == source_id,
            ))).all()
            assert len(rows) == 1
            root = rows[0]
            assert root.predecessor_id is None and root.sequence == 1
            assert root.repair_actor_id == service_actor
            assert root.repair_idempotency_key == source_id
            assert root.requested_at == source_window[0]
            assert root.deadline_at == (None if new_active_guide else source_window[1])
            assert root.remaining_microseconds == (
                (source_window[1] - root.clock_observed_at) // timedelta(microseconds=1)
                if new_active_guide else None
            )
            if new_active_guide:
                assert 0 < root.remaining_microseconds < (
                    source_window[1] - source_window[0]
                ) // timedelta(microseconds=1)
            assert root.outcome == ("blocked" if new_active_guide else "kept")
            assert root.blocked_reason == ("context_blocked" if new_active_guide else None)
            if new_active_guide:
                assert root.packet["candidate"]["target"] is None
            else:
                assert root.packet["candidate"]["target"] == root.packet["candidate"]["prior"]
            assert await session.scalar(text(
                "SELECT public.revision_task_lineage(to_jsonb(t)) "
                "FROM public.workstream_tasks t WHERE t.id=:task"
            ), {"task": h.request.task_id}) == before
            action = await session.scalar(text(
                "SELECT action_id FROM public.audit_events WHERE id=:decision"
            ), {"decision": root.authorization_decision_id})
            assert action == "task.revision.recover"
            from app.modules.tasks.revision.expiry_event import revision_preparation_event

            expected = revision_preparation_event(
                await session.get(TaskPostSubmitRoutingManifest, source_id), root,
            )
            event = await session.scalar(select(OutboxEvent).where(
                OutboxEvent.idempotency_key == expected.idempotency_key,
            ))
            assert event is not None
            assert event.not_before_at == root.deadline_at
            assert event.payload == expected.payload
        if not new_active_guide:
            # The same root, packet, digest and service decision cannot be
            # replayed with a different AUTH request/correlation receipt.
            with pytest.raises(IntegrityError, match="revision repair authorization unavailable"):
                async with h.factory() as session, session.begin():
                    row = await session.scalar(text(
                        "SELECT to_jsonb(p) FROM public.task_revision_preparations p WHERE p.id=:id"
                    ), {"id": root.id})
                    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                    await session.execute(text(
                        "ALTER TABLE public.task_revision_preparations "
                        "DISABLE TRIGGER revision_preparation_immutable"
                    ))
                    await session.execute(text(
                        "DELETE FROM public.task_revision_preparations WHERE id=:id"
                    ), {"id": root.id})
                    await session.execute(text(
                        "ALTER TABLE public.task_revision_preparations "
                        "ENABLE TRIGGER revision_preparation_immutable"
                    ))
                    await session.execute(text(
                        "ALTER TABLE public.audit_events "
                        "DISABLE TRIGGER audit_events_reject_update_delete"
                    ))
                    await session.execute(text(
                        "UPDATE public.audit_events SET request_id=:other,correlation_id=:other "
                        "WHERE id=:decision"
                    ), {"other": new_record_id(), "decision": root.authorization_decision_id})
                    await session.execute(text(
                        "ALTER TABLE public.audit_events "
                        "ENABLE TRIGGER audit_events_reject_update_delete"
                    ))
                    row["creation_xid"] = await session.scalar(text("SELECT pg_current_xact_id()::text"))
                    # Supply the canonical INSERT clock inputs so the intended
                    # changed AUTH receipt, rather than an earlier clock guard, rejects.
                    for field in ("deadline_at", "remaining_microseconds", "clock_observed_at"):
                        row[field] = None
                        row["packet"][field] = None
                    await session.execute(text(
                        "INSERT INTO public.task_revision_preparations SELECT * FROM "
                        "jsonb_populate_record(NULL::public.task_revision_preparations, CAST(:row AS jsonb))"
                    ), {"row": json.dumps(row)})


async def test_discovery_registers_missing_root_event_once_under_race(
    tmp_path, isolated_database_env,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        original_root_id = h.revision_preparation_id
        await _provision_expirer(h.factory)
        async with h.factory() as session, session.begin():
            await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            await session.execute(text(
                "ALTER TABLE public.outbox_events DISABLE TRIGGER outbox_events_custody"
            ))
            removed = await session.execute(text("""
                DELETE FROM public.outbox_events
                WHERE event_type='TaskRevisionExpiryRequested'
                  AND idempotency_key=:key AND attempt_count=0
                  AND claimed_at IS NULL AND delivery_state='pending'
                RETURNING event_id
            """), {"key": f"task.revision.expire:{source_id}"})
            assert len(removed.all()) == 1
            await session.execute(text(
                "ALTER TABLE public.outbox_events ENABLE TRIGGER outbox_events_custody"
            ))
        counts = await asyncio.gather(*(
            scan_task_revision_sources(h.factory, None)
            for _ in range(2)
        ))
        assert sum(count for count, _ in counts) == 1
        async with h.factory() as session:
            roots = (await session.scalars(select(TaskRevisionPreparation).where(
                TaskRevisionPreparation.routing_manifest_id == source_id,
            ))).all()
            assert len(roots) == 1
            assert UUID(str(roots[0].id)) == original_root_id
            assert roots[0].repair_actor_id is None
            events = (await session.scalars(select(OutboxEvent).where(
                OutboxEvent.idempotency_key == f"task.revision.expire:{source_id}",
            ))).all()
            assert len(events) == 1
            assert events[0].not_before_at == roots[0].deadline_at
            repairs = await session.scalar(text("""
                SELECT count(*) FROM public.audit_events
                WHERE event_type='TaskRevisionContextRepaired'
                  AND event_payload->'references'->>'routing_manifest_id'=:source
            """), {"source": str(source_id)})
            assert repairs == 1


async def test_concurrent_missing_root_recovery_commits_one_complete_effect(
    tmp_path, isolated_database_env, monkeypatch,
):
    """Two actual recoveries wait on TASK before creating the absent root."""
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        await _retain_pre_revision_source(h, source_id)
        service_actor = await _provision_expirer(h.factory)
        async with h.factory() as session:
            custody_before = (await session.execute(text("""
                SELECT to_jsonb(t),to_jsonb(a),to_jsonb(s)
                FROM public.workstream_tasks t
                JOIN public.task_assignments a ON a.id=:assignment
                JOIN public.submissions s ON s.id=:submission WHERE t.id=:task
            """), {"assignment": h.request.assignment_id,
                   "submission": h.created.submission_id, "task": h.request.task_id})).one()
            repairs_before = await session.scalar(text("""
                SELECT count(*) FROM public.audit_events
                WHERE event_type='TaskRevisionContextRepaired'
                  AND event_payload->'references'->>'routing_manifest_id'=:source
            """), {"source": str(source_id)})

        held, release = asyncio.Event(), asyncio.Event()
        first_name = f"revision-root-first-{new_record_id().hex}"
        waiter_name = f"revision-root-second-{new_record_id().hex}"
        original_lock = TaskRepository.lock_project_task

        async def ordered_lock(repository, *args, **kwargs):
            current = asyncio.current_task()
            if current.get_name() == waiter_name:
                await repository._session.execute(text(
                    "SELECT set_config('application_name',:name,true)"
                ), {"name": waiter_name})
            task = await original_lock(repository, *args, **kwargs)
            if current.get_name() == first_name:
                held.set()
                await asyncio.wait_for(release.wait(), 15)
            return task

        async def recover():
            async with h.factory() as session, session.begin():
                return await task_revision_recovery(session).recover(source_id)

        contenders = []
        with monkeypatch.context() as patch:
            patch.setattr(TaskRepository, "lock_project_task", ordered_lock)
            try:
                contenders.append(asyncio.create_task(recover(), name=first_name))
                await asyncio.wait_for(held.wait(), 15)
                contenders.append(asyncio.create_task(recover(), name=waiter_name))
                await asyncio.wait_for(wait_for_named_database_lock(
                    isolated_database_env, waiter_name,
                ), 15)
                assert not contenders[1].done()
                release.set()
                assert await asyncio.wait_for(asyncio.gather(*contenders), 30) == [True, False]
            finally:
                release.set()
                for contender in contenders:
                    if not contender.done():
                        contender.cancel()
                await asyncio.gather(*contenders, return_exceptions=True)

        async with h.factory() as session:
            roots = (await session.scalars(select(TaskRevisionPreparation).where(
                TaskRevisionPreparation.routing_manifest_id == source_id,
            ))).all()
            assert len(roots) == 1
            root = roots[0]
            assert root.sequence == 1 and root.predecessor_id is None
            assert root.repair_actor_id == service_actor
            assert root.repair_idempotency_key == source_id
            events = (await session.scalars(select(OutboxEvent).where(
                OutboxEvent.idempotency_key == f"task.revision.expire:{source_id}",
            ))).all()
            assert len(events) == 1
            assert events[0].not_before_at == root.deadline_at
            assert events[0].payload["root_preparation_id"] == str(root.id)
            assert events[0].payload["root_preparation_sha256"] == root.preparation_sha256
            # The loser must return before AUTH/audit writes as well as before
            # preparation and outbox insertion.
            assert await session.scalar(text("""
                SELECT count(*) FROM public.audit_events
                WHERE action_id='task.revision.recover'
            """)) == 1
            assert await session.scalar(text("""
                SELECT count(*) FROM public.audit_events
                WHERE event_type='TaskRevisionContextRepaired'
                  AND event_payload->'references'->>'routing_manifest_id'=:source
            """), {"source": str(source_id)}) == repairs_before + 1
            repair = (await session.execute(text("""
                SELECT event_payload->'references'->>'revision_preparation_id',
                       event_payload->'references'->>'outbox_event_id'
                FROM public.audit_events WHERE id=:id
            """), {"id": root.audit_event_id})).one()
            assert repair == (str(root.id), str(events[0].event_id))
            assert (await session.execute(text("""
                SELECT to_jsonb(t),to_jsonb(a),to_jsonb(s)
                FROM public.workstream_tasks t
                JOIN public.task_assignments a ON a.id=:assignment
                JOIN public.submissions s ON s.id=:submission WHERE t.id=:task
            """), {"assignment": h.request.assignment_id,
                   "submission": h.created.submission_id,
                   "task": h.request.task_id})).one() == custody_before
