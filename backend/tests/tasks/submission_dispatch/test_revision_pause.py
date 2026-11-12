"""Paused revision clocks preserve allowance and publish durable PM attention."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from app.modules.contributions.api import RewardSelectionFacts
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.adapters.tasks import task_post_submit_outcome, task_revision_recovery
from app.core.identifiers import new_record_id
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.api.revision import RevisionCandidate, RevisionContextSnapshot
from app.modules.tasks.api.revision_expiry import REVISION_CONTEXT_BLOCKED_EVENT, REVISION_EXPIRY_EVENT
from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from app.modules.tasks.post_submit_routing import outcome as routing_outcome
from app.modules.tasks.post_submit_routing.models import TaskPostSubmitRoutingManifest
from app.modules.tasks.revision.expiry_event import revision_preparation_event
from app.modules.tasks.revision.models import TaskRevisionPreparation
from app.modules.tasks.revision.service import candidate_from_packet, project_revision
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import activate_successor_guide
from tests.tasks.submission_dispatch.test_revision_expiry import _provision_expirer
from tests.tasks.submission_dispatch.clock_fixtures import source_window_clock
from tests.tasks.test_public_submission_intake import _client
from tests.test_submission_predecessor_custody import _fixture_revision_context


def _paused_row():
    """Build strict public lineage for a pure paused-clock projection proof."""
    start = datetime(2026, 10, 14, tzinfo=UTC)
    lineage = TaskPolicyLineage(**{
        name: new_record_id() if name.endswith("_id") else
        1 if name.endswith("_generation") else
        "sha256:" + "a" * 64 if name.endswith(("_hash", "_bundle_hash")) else "v1"
        for name in TaskPolicyLineage.model_fields
    })
    prior = RevisionContextSnapshot(
        guide_id=new_record_id(), activation_operation_id=new_record_id(),
        activation_generation=1, activated_at=start, lineage=lineage,
    )
    reward = RewardSelectionFacts(
        policy_version_id=prior.lineage.locked_contribution_policy_version_id,
        task_size="small", compensation_mode="unpaid", award_definition_id=None,
        instrument_type=None, unit_code=None, quantity=None, adapter_binding_id=None,
    )
    candidate = RevisionCandidate(
        prior_reward_selection=reward, target_reward_selection=None,
        prior=prior, target=None, max_revision_rounds=2, revision_deadline_hours=24,
    )
    return SimpleNamespace(
        id=new_record_id(), preparation_sha256="sha256:" + "b" * 64,
        predecessor_id=None, submission_id=str(new_record_id()), routing_manifest_id=new_record_id(),
        sequence=1, next_revision_round=1, max_revision_rounds=2, requested_at=start,
        deadline_at=None, remaining_microseconds=86_400_000_000,
        outcome="blocked", blocked_reason="context_blocked",
        packet={"candidate": candidate.model_dump(mode="json")},
    )


def test_paused_projection_never_spends_allowance_as_wall_time_passes():
    row = _paused_row()
    first = project_revision(row, row.requested_at)
    later = project_revision(row, row.requested_at + timedelta(days=100))
    assert first == later
    assert later.clock_state == "paused" and later.deadline_at is None
    assert later.remaining_microseconds == 86_400_000_000
    assert later.disposition == "context_blocked"
    wire = later.model_dump(mode="json", exclude_none=True)
    assert wire["target"] is None and wire["target_reward_selection"] is None
    assert wire["prior_reward_selection"] == {
        "compensation_mode": "unpaid", "task_size": "small",
        "instrument": None, "unit": None, "quantity": None,
    }
    assert wire["deadline_at"] is None
    assert wire["remaining_microseconds"] == row.remaining_microseconds


def test_lower_target_limit_blocks_context_and_respects_running_deadline():
    row = _paused_row()
    candidate = candidate_from_packet(row.packet)
    target = candidate.prior.model_copy(update={
        "activation_operation_id": new_record_id(), "activation_generation": 2,
        "lineage": candidate.prior.lineage.model_copy(update={
            "locked_revision_policy_id": new_record_id(),
            "locked_revision_policy_hash": "sha256:" + "c" * 64,
        }),
    })
    row.packet["candidate"] = candidate.model_copy(update={
        "target": target, "target_reward_selection": candidate.prior_reward_selection, "target_max_revision_rounds": 1, "target_post_policy_json": "{}",
    }).model_dump(mode="json")
    row.next_revision_round = 2
    row.blocked_reason = "context_blocked"
    row.deadline_at = row.requested_at + timedelta(hours=24)
    row.remaining_microseconds = None
    before = project_revision(row, row.requested_at)
    assert before.disposition == "context_blocked" and before.clock_state == "running"
    assert project_revision(row, row.deadline_at).disposition == "revision_deadline_expired"


def test_resumed_timer_keeps_root_identity_but_selects_new_effective_deadline():
    root = _paused_row()
    root.project_id, root.task_id = str(new_record_id()), str(new_record_id())
    root.assignment_id, root.contributor_id = str(new_record_id()), str(new_record_id())
    root.audit_event_id, root.authorization_decision_id = new_record_id(), new_record_id()
    manifest = SimpleNamespace(id=root.routing_manifest_id, outcome_event_id=new_record_id())
    notice = revision_preparation_event(manifest, root)
    assert notice.event_type == REVISION_CONTEXT_BLOCKED_EVENT
    assert notice.not_before_at is None
    assert notice.payload["remaining_microseconds"] == root.remaining_microseconds
    head = SimpleNamespace(**vars(root))
    head.id, head.predecessor_id, head.sequence = new_record_id(), root.id, 2
    head.deadline_at = root.requested_at + timedelta(days=100, hours=24)
    head.remaining_microseconds = None
    event = revision_preparation_event(manifest, root, head)
    assert event.event_type == REVISION_EXPIRY_EVENT
    assert event.idempotency_key == f"task.revision.expire:{manifest.id}:{head.id}"
    assert event.payload["root_preparation_id"] == str(root.id)
    assert event.payload["root_preparation_sha256"] == root.preparation_sha256
    assert event.not_before_at == head.deadline_at


async def _read_prep(h, preparation_id=None):
    async with h.factory() as session:
        return await session.get(TaskRevisionPreparation, preparation_id or h.revision_preparation_id)


async def _repair(client, h, parent, *, key=None):
    original = AuthorizedTaskCommands.repair_revision_context
    failures = []

    async def observed(command, *args, **kwargs):
        try:
            return await original(command, *args, **kwargs)
        except SQLAlchemyError as exc:
            failures.append(exc)
            raise

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(AuthorizedTaskCommands, "repair_revision_context", observed)
        response = await client.post(
            f"/api/v1/projects/{h.request.project_id}/tasks/{h.request.task_id}/revision-context/repair",
            json={"parent_preparation_id": str(parent.id),
                  "parent_preparation_sha256": parent.preparation_sha256,
                  "reason": "Adopt the complete current approved context"},
            headers={"Idempotency-Key": str(key or new_record_id())},
        )
    if failures:
        raise AssertionError("real PM repair database failure") from failures[0]
    assert response.status_code == 200, response.text
    return response.json()


async def test_fresh_blocked_failure_pauses_full_budget_and_is_visible_to_pm(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        await activate_successor_guide(h, max_revision_rounds=0)
        source_id = await _fixture_revision_context(h)
        root = await _read_prep(h)
        assert root.outcome == "blocked" and root.blocked_reason == "context_blocked"
        policy_budget = root.packet["candidate"]["revision_deadline_hours"] * 3_600_000_000
        assert root.deadline_at is None and root.remaining_microseconds == policy_budget
        async with h.factory() as session:
            manifest = await session.get(TaskPostSubmitRoutingManifest, source_id)
            expected = revision_preparation_event(manifest, root)
            notices = (await session.scalars(select(OutboxEvent).where(
                OutboxEvent.idempotency_key == expected.idempotency_key,
            ))).all()
            assert len(notices) == 1 and notices[0].payload == expected.payload
            assert await session.scalar(text(
                "SELECT count(*) FROM public.outbox_events WHERE event_type=:type "
                "AND correlation_id=:source"
            ), {"type": REVISION_EXPIRY_EVENT, "source": str(source_id)}) == 0
        assert await _fixture_revision_context(h) == source_id
        assert (await _read_prep(h)).preparation_sha256 == root.preparation_sha256
        async with _client(h, monkeypatch, isolated_database_env) as client:
            response = await client.get(
                f"/api/v1/projects/{h.request.project_id}/tasks/{h.request.task_id}/work-context",
            )
            assert response.status_code == 200, response.text
            view = response.json()["task"]["revision_context"]
            assert view["clock_state"] == "paused" and view["deadline_at"] is None
            assert view["remaining_microseconds"] == root.remaining_microseconds
            # The contributor's assignment list carries the same paused, zero-round projection.
            mine = await client.get("/api/v1/actors/me/assignments", params={"state": "active"})
            assert mine.status_code == 200, mine.text
            [item] = mine.json()["items"]
            present = {name: value for name, value in item["revision"].items() if value is not None}
            assert present == {name: value for name, value in view.items() if value is not None}
            assert item["next_action"] == "none"


async def _fixture_historical_missing_root(
    h, monkeypatch, *, remaining_seconds, recover_in_source_transaction,
):
    """Commit a guarded historical route whose old writer omitted revision effects."""
    omitted = []
    async with h.factory() as session, session.begin():
        outcome = task_post_submit_outcome(session, h.factory)
        append = outcome._outbox.append

        async def omit_preparation(*args, **kwargs):
            omitted.append("preparation")
            return None

        async def append_except_missing_revision(event):
            if event is None:
                omitted.append("event")
                return None
            return await append(event)

        with monkeypatch.context() as patch:
            patch.setattr(routing_outcome, "prepare_revision", omit_preparation)
            patch.setattr(routing_outcome, "revision_preparation_event", lambda *_args: None)
            patch.setattr(outcome._outbox, "append", append_except_missing_revision)
            async with source_window_clock(session, remaining_seconds) as source_guard:
                assert await outcome.observe_delivery_generation(h.envelope) is None
                result = await outcome.apply(h.envelope, current_generation=None)
                assert result.routing_recommendation == "needs_revision"
        if recover_in_source_transaction:
            assert await session.scalar(text(
                "SELECT pg_catalog.pg_get_functiondef("
                "'public.guard_task_post_submit_routing_source()'::regprocedure)"
            )) == source_guard
            assert await session.scalar(text("""
                SELECT xmin::text=pg_current_xact_id()::text
                FROM public.task_post_submit_routing_manifests WHERE id=:source
            """), {"source": result.routing_manifest_id}) is True
            assert await task_revision_recovery(session).recover(result.routing_manifest_id) is True
    assert omitted == ["preparation", "event"]
    async with h.factory() as session:
        assert await session.scalar(text(
            "SELECT pg_catalog.pg_get_functiondef("
            "'public.guard_task_post_submit_routing_source()'::regprocedure)"
        )) == source_guard
        assert await session.scalar(text(
            "SELECT count(*) FROM public.task_revision_preparations"
        )) == int(recover_in_source_transaction)
        assert await session.scalar(text("""
            SELECT count(*) FROM public.outbox_events
            WHERE correlation_id=:source AND event_type IN (
              'TaskRevisionExpiryRequested','TaskRevisionContextBlocked')
        """), {"source": str(result.routing_manifest_id)}) == int(
            recover_in_source_transaction
        )
        assert await session.scalar(text(
            "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgenabled='D'"
        )) == 0
    return result.routing_manifest_id


@pytest.mark.parametrize(("remaining_seconds", "blocked_reason", "recover_with_source"), [
    (136_800, "context_blocked", False),
    (-3_600, "revision_deadline_expired", False),
    (136_800, "context_blocked", True),
])
async def test_missing_root_recovery_preserves_original_unspent_or_due_window(
    tmp_path, isolated_database_env, monkeypatch,
    remaining_seconds, blocked_reason, recover_with_source,
):
    """Delayed service recovery cannot renew an old source's original allowance."""
    async with remediation_source(tmp_path, isolated_database_env) as h:
        await activate_successor_guide(h, max_revision_rounds=0)
        service_actor = await _provision_expirer(h.factory)
        source_id = await _fixture_historical_missing_root(
            h, monkeypatch, remaining_seconds=remaining_seconds,
            recover_in_source_transaction=recover_with_source,
        )
        async with h.factory() as session:
            source_window = (await session.execute(text("""
                SELECT m.created_at,
                       m.created_at+make_interval(hours=>p.revision_deadline_hours)
                FROM public.task_post_submit_routing_manifests m
                JOIN public.submissions s ON s.id=m.submission_id
                JOIN public.revision_policies p ON p.id=s.locked_revision_policy_id
                WHERE m.id=:source
            """), {"source": source_id})).one()
            assert source_window[1] - source_window[0] == timedelta(hours=48)
        if not recover_with_source:
            async with h.factory() as session, session.begin():
                assert await task_revision_recovery(session).recover(source_id) is True
        async with h.factory() as session:
            root = (await session.scalars(select(TaskRevisionPreparation).where(
                TaskRevisionPreparation.routing_manifest_id == source_id,
            ))).one()
            assert root.predecessor_id is None and root.sequence == 1
            assert root.repair_actor_id == service_actor
            assert root.repair_idempotency_key == source_id
            assert root.requested_at == source_window[0]
            assert root.outcome == "blocked" and root.blocked_reason == blocked_reason
            expected = revision_preparation_event(
                await session.get(TaskPostSubmitRoutingManifest, source_id), root,
            )
            event = (await session.scalars(select(OutboxEvent).where(
                OutboxEvent.idempotency_key == expected.idempotency_key,
            ))).one()
            assert event.event_type == expected.event_type
            assert event.not_before_at == expected.not_before_at
            assert event.payload == expected.payload
            if remaining_seconds > 0:
                expected_remaining = (
                    source_window[1] - root.clock_observed_at
                ) // timedelta(microseconds=1)
                assert 0 < root.remaining_microseconds == expected_remaining < 48 * 3_600_000_000
                assert root.deadline_at is None
                assert event.event_type == REVISION_CONTEXT_BLOCKED_EVENT
                assert event.payload["remaining_microseconds"] == expected_remaining
            else:
                assert root.deadline_at == source_window[1]
                assert root.remaining_microseconds is None
                assert event.event_type == REVISION_EXPIRY_EVENT
                assert event.not_before_at == source_window[1]
            before = await session.execute(text("""
                SELECT to_jsonb(p),to_jsonb(e),(
                  SELECT count(*) FROM public.audit_events a
                  WHERE a.event_type='TaskRevisionContextRepaired'
                    AND a.event_payload->'references'->>'routing_manifest_id'=:source)
                FROM public.task_revision_preparations p
                JOIN public.outbox_events e ON e.idempotency_key=:key WHERE p.id=:preparation
            """), {"source": str(source_id), "key": expected.idempotency_key,
                     "preparation": root.id})
            before = before.one()
        async with h.factory() as session, session.begin():
            assert await task_revision_recovery(session).recover(source_id) is False
        async with h.factory() as session:
            after = (await session.execute(text("""
                SELECT to_jsonb(p),to_jsonb(e),(
                  SELECT count(*) FROM public.audit_events a
                  WHERE a.event_type='TaskRevisionContextRepaired'
                    AND a.event_payload->'references'->>'routing_manifest_id'=:source)
                FROM public.task_revision_preparations p
                JOIN public.outbox_events e ON e.idempotency_key=:key WHERE p.id=:preparation
            """), {"source": str(source_id), "key": expected.idempotency_key,
                     "preparation": root.id})).one()
            assert after == before


async def test_pm_pause_and_resume_preserve_only_remaining_database_time(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        root = await _read_prep(h)
        await activate_successor_guide(h, max_revision_rounds=0)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            paused_view = await _repair(client, h, root)
            paused = await _read_prep(h, UUID(paused_view["preparation_id"]))
            expected_remaining = (root.deadline_at - paused.clock_observed_at) // timedelta(microseconds=1)
            assert paused.deadline_at is None
            original_budget = (root.deadline_at - root.requested_at) // timedelta(microseconds=1)
            assert 0 < paused.remaining_microseconds == expected_remaining < original_budget
            await activate_successor_guide(h, max_revision_rounds=2, version="v3")
            key = new_record_id()
            resumed_view = await _repair(client, h, paused, key=key)
            resumed = await _read_prep(h, UUID(resumed_view["preparation_id"]))
            assert resumed.deadline_at == resumed.clock_observed_at + timedelta(
                microseconds=paused.remaining_microseconds,
            )
            assert resumed.deadline_at > root.deadline_at
            assert resumed.remaining_microseconds is None and resumed.outcome == "rebased"
            assert await _repair(client, h, paused, key=key) == resumed_view
        async with h.factory() as session:
            heads = (await session.scalars(select(TaskRevisionPreparation).where(
                TaskRevisionPreparation.routing_manifest_id == source_id,
            ).order_by(TaskRevisionPreparation.sequence))).all()
            assert [head.id for head in heads] == [root.id, paused.id, resumed.id]
            assert heads[0].deadline_at == root.deadline_at
            manifest = await session.get(TaskPostSubmitRoutingManifest, source_id)
            for head in heads:
                expected = revision_preparation_event(manifest, root, head)
                event = await session.scalar(select(OutboxEvent).where(
                    OutboxEvent.idempotency_key == expected.idempotency_key,
                ))
                assert event is not None and event.payload == expected.payload
