"""Actual 0071 upgrade and refusal preserve native retained earning evidence."""

import asyncio
import json
import re

from alembic import command
import pytest
from sqlalchemy import event, text

from app.adapters.auth import lifecycle_transition_authorization
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.authorization.runtime import (
    ActorKind, ActorStatus, HumanAuthorizationContext, IdentityLinkStatus,
)
from app.modules.compensation.fulfillment.service import CompensationFulfillmentParticipant
from app.modules.reviews.api.lifecycle import LifecycleTransitionFacts
from app.modules.reviews.lifecycle.fence import PostgresJointLifecycleMutationFence
from tests.conftest import (
    _alembic_config, _drop_test_database_schema, _verify_test_database_schema,
)
from tests.finance.test_selected_reward_migration import _snapshot
from tests.reviews.lifecycle.transition_support import command_for, transition
from tests.contributions.records.support import reviewer_contribution_source, insert_record, award_values, insert_award
from tests.tasks.post_submit_routing.outcome_support import apply_outcome, authorized_routing_source

pytestmark = pytest.mark.postgres_schema_contract


def _assert_preserved_0071_rows(before, after):
    for table, rows in before[0].items():
        if table == "alembic_version":
            continue
        if table in {"joint_lifecycle_release_control", "joint_lifecycle_transitions"}:
            observed = [json.loads(row) for row in after[0][table]]
            for row in observed:
                assert row.pop("fulfillment_source_instance_id") is None
            assert observed == [json.loads(row) for row in rows]
        else:
            assert after[0][table] == rows


def test_fulfillment_root_migration_fresh_and_0071_upgrade(isolated_database_env, migration_lock):
    config = _alembic_config()
    with migration_lock():
        asyncio.run(_verify_test_database_schema(isolated_database_env))
        asyncio.run(_drop_test_database_schema(isolated_database_env))
        command.upgrade(config, "0071_selected_task_reward")
        before = asyncio.run(_snapshot(isolated_database_env))
        command.upgrade(config, "head")
        asyncio.run(_verify_test_database_schema(isolated_database_env))
        after = asyncio.run(_snapshot(isolated_database_env))
        assert after[0]["compensation_fulfillment_roots"] == []
        assert after[0]["alembic_version"] == ['{"version_num":"0073_fulfillment_evidence"}']
        _assert_preserved_0071_rows(before, after)
        command.upgrade(config, "head")
        assert asyncio.run(_snapshot(isolated_database_env)) == after


async def _native_baseline_transition(actor_id, phase):
    """Prepare data under installed 0071 guards, using current AUTH and fence.

    No application validator, SQL function or runtime manifest is replaced.
    This is prior-schema data preparation, not a compatibility execution path.
    """
    factory = db_session.get_session_factory()
    async with factory() as session:
        definition = await session.scalar(text("SELECT pg_get_functiondef("
            "'public.joint_lifecycle_transition_valid(public.joint_lifecycle_transitions)'::regprocedure)"))
        manifests = set(re.findall(r"sha256:[0-9a-f]{64}", definition))
        assert len(manifests) == 1
    native_manifest = manifests.pop()
    requested = await command_for(actor_id, phase, reviewed_manifest_digest=native_manifest)
    async with factory() as session, session.begin():
        current = await PostgresJointLifecycleMutationFence(session).lock_controller()
        assert current.generation == requested.expected_generation
        retained_invalid = await session.scalar(text("""SELECT EXISTS(
            SELECT 1 FROM public.final_acceptances f
            LEFT JOIN public.task_post_submit_routing_manifests m ON m.id=f.source_routing_manifest_id
            WHERE m.id IS NULL OR NOT public.task_routing_receipt_valid(m))"""))
        assert retained_invalid is False
        facts = LifecycleTransitionFacts(command=requested, observations_digest=canonical_json_hash({
            "singleton_id": str(current.singleton_id), "generation": current.generation,
            "phase": current.phase.value, "retained_pre_authority_acceptance": False,
            "manifest": native_manifest,
        }))
        context = HumanAuthorizationContext(
            actor_profile_id=requested.actor_profile_id, identity_link_id=requested.identity_link_id,
            actor_kind=ActorKind.HUMAN, actor_status=ActorStatus.ACTIVE,
            identity_link_status=IdentityLinkStatus.ACTIVE, request_id=new_record_id(),
            correlation_id=requested.operation_id,
        )
        async with lifecycle_transition_authorization(session, context).lock_scope(requested) as authority:
            receipt = await authority.consume_new(facts)
            history_id = new_record_id()
            values = dict(
                id=history_id, operation=requested.operation_id, singleton=current.singleton_id,
                generation=current.generation + 1, previous=current.phase.value,
                phase=requested.target_phase.value, facts=json.dumps(facts.model_dump(mode="json")),
                digest=receipt.resource_context_digest, decision=receipt.decision_event_id,
            )
            # These are the actual installed 0071 columns, not a reconstructed runtime.
            await session.execute(text("""INSERT INTO public.joint_lifecycle_transitions
                (id,operation_id,singleton_id,generation,previous_phase,phase,facts_json,
                 resource_context_digest,authorization_decision_event_id)
                VALUES (:id,:operation,:singleton,:generation,:previous,:phase,CAST(:facts AS jsonb),
                 :digest,:decision)"""), values)
            await session.execute(text("""UPDATE public.joint_lifecycle_release_control
                SET phase=:phase,generation=:generation,transition_id=:id WHERE id=:singleton"""), values)
            assert await session.scalar(text("SELECT public.joint_lifecycle_transition_valid(t) "
                "FROM public.joint_lifecycle_transitions t WHERE id=:id"), {"id": history_id}) is True
    return requested


async def test_upgrade_preserves_reviewer_awards_and_exact_transition_replay(
    tmp_path, isolated_database_env, migration_lock, admin_access,
):
    from scripts.bootstrap_access_administrator import _run as bootstrap
    from tests.contributions.exports.support import export_path

    with migration_lock():
        await db_session.dispose_engine()
        await _drop_test_database_schema(isolated_database_env)
        await asyncio.to_thread(command.upgrade, _alembic_config(), "0071_selected_task_reward")
        await db_session.dispose_engine()
        admin = await admin_access.signed.actor("reviewer-upgrade-admin", roles=("viewer",))
        operator = await admin_access.signed.actor("reviewer-upgrade-operator", roles=("viewer",))
        code, _receipt = await bootstrap(admin.id, execute=True)
        assert code == 0
        await admin_access.signed.grant(admin, operator)
        commands = [await _native_baseline_transition(operator.id, phase)
                    for phase in ("shadow", "live", "draining", "disabled")]
        async with reviewer_contribution_source(tmp_path, isolated_database_env, paid=True) as h:
            async with h.factory() as session, session.begin():
                await insert_record(session, h.reviewer_record)
                awards = await award_values(session, h.reviewer_record)
                assert len(awards) == 1
                await insert_award(session, awards[0])
            before = await _snapshot(isolated_database_env)
            await asyncio.to_thread(command.upgrade, _alembic_config(), "head")
            await _verify_test_database_schema(isolated_database_env)
            after = await _snapshot(isolated_database_env)
            _assert_preserved_0071_rows(before, after)
            assert after[0]["compensation_fulfillment_roots"] == []
            writes = []
            engine = db_session.get_session_factory().kw["bind"].sync_engine

            def observe(_connection, _cursor, statement, _parameters, _context, _many):
                if statement.lstrip().split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
                    writes.append(statement)

            event.listen(engine, "before_cursor_execute", observe)
            try:
                for retained in commands:
                    replay = await transition(retained)
                    assert replay.operation_id == retained.operation_id
                    assert replay.generation == retained.expected_generation + 1
            finally:
                event.remove(engine, "before_cursor_execute", observe)
            assert writes == []
            assert await _snapshot(isolated_database_env) == after
            reader = await admin_access.signed.actor("retained-reviewer-reader")
            await admin_access.signed.grant(admin, reader, role="project_manager",
                                           project_id=h.reviewer_record.project_id)
            path = export_path(h.reviewer_record.project_id)
            response = await admin_access.signed.client.get(path, headers=reader.headers)
            assert response.status_code == 200, response.text
            (record,) = response.json()["items"]
            assert record["contribution_id"] == str(h.reviewer_record.id)
            assert record["awards"][0]["award_id"] == str(awards[0]["id"])
            response = await admin_access.signed.client.get(path, params={"format": "csv"},
                                                          headers=reader.headers)
            assert response.status_code == 200, response.text
            assert str(awards[0]["id"]) in response.text


async def test_fulfillment_root_migration_refuses_retained_award_without_rewrite(
    tmp_path, isolated_database_env, migration_lock, admin_access, monkeypatch,
):
    from scripts.bootstrap_access_administrator import _run as bootstrap

    with migration_lock():
        await db_session.dispose_engine()
        await _drop_test_database_schema(isolated_database_env)
        await asyncio.to_thread(command.upgrade, _alembic_config(), "0071_selected_task_reward")
        await db_session.dispose_engine()
        admin = await admin_access.signed.actor("root-migration-admin", roles=("viewer",))
        operator = await admin_access.signed.actor("root-migration-operator", roles=("viewer",))
        code, _receipt = await bootstrap(admin.id, execute=True)
        assert code == 0
        await admin_access.signed.grant(admin, operator)
        await _native_baseline_transition(operator.id, "shadow")
        await _native_baseline_transition(operator.id, "live")

        async def not_installed(_owner, _request, _awards):
            """0071 has no root extension; retain a real native earning for preflight."""
            return None

        async with authorized_routing_source(tmp_path, isolated_database_env,
                                             contribution_awards=("money",)) as h:
            with monkeypatch.context() as setup:
                setup.setattr(CompensationFulfillmentParticipant, "complete", not_installed)
                async with h.factory() as session, session.begin():
                    result = await apply_outcome(session, h, 2)
            async with h.factory() as session:
                assert await session.scalar(text("SELECT count(*) FROM public.compensation_awards")) == 1
                assert await session.scalar(text("SELECT to_regclass('public.compensation_fulfillment_roots') IS NULL"))
                assert await session.scalar(text("SELECT public.task_routing_receipt_valid(m) "
                    "AND public.task_routing_outcome_complete(m) FROM public.task_post_submit_routing_manifests m "
                    "WHERE id=:id"), {"id": result.routing_manifest_id}) is True
                assert await session.scalar(text("SELECT public.accepted_submission_award_set_is_complete(c.id) "
                    "FROM public.contribution_records c")) is True
            await _native_baseline_transition(operator.id, "draining")
            await _native_baseline_transition(operator.id, "disabled")
            before = await _snapshot(isolated_database_env)
            with pytest.raises(RuntimeError, match="refuses retained awards without original root custody"):
                await asyncio.to_thread(command.upgrade, _alembic_config(), "head")
            assert await _snapshot(isolated_database_env) == before
