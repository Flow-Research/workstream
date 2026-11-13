"""Actual 0071 upgrade and refusal preserve native retained earning evidence."""

import asyncio
import re

from alembic import command
import pytest
from sqlalchemy import text

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
from app.modules.reviews.lifecycle.models import JointLifecycleReleaseControl, JointLifecycleTransition
from tests.conftest import (
    _alembic_config, _drop_test_database_schema, _verify_test_database_schema,
)
from tests.finance.test_selected_reward_migration import _snapshot
from tests.reviews.lifecycle.transition_support import command_for
from tests.tasks.post_submit_routing.outcome_support import apply_outcome, authorized_routing_source

pytestmark = pytest.mark.postgres_schema_contract


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
        assert after[0]["alembic_version"] == ['{"version_num":"0072_fulfillment_roots"}']
        for table, rows in before[0].items():
            if table != "alembic_version":
                assert after[0][table] == rows
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
            history = JointLifecycleTransition(
                id=new_record_id(), operation_id=requested.operation_id,
                singleton_id=current.singleton_id, generation=current.generation + 1,
                previous_phase=current.phase.value, phase=requested.target_phase.value,
                facts_json=facts.model_dump(mode="json"), resource_context_digest=receipt.resource_context_digest,
                authorization_decision_event_id=str(receipt.decision_event_id),
            )
            session.add(history)
            await session.flush()
            control = await session.get(JointLifecycleReleaseControl, current.singleton_id, populate_existing=True)
            control.phase, control.generation, control.transition_id = history.phase, history.generation, history.id
            await session.flush()
            assert await session.scalar(text("SELECT public.joint_lifecycle_transition_valid(t) "
                "FROM public.joint_lifecycle_transitions t WHERE id=:id"), {"id": history.id}) is True


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
