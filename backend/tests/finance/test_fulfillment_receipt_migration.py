"""Actual0072 pending earning survives receipt installation without rewritten evidence."""

import asyncio

from alembic import command
import asyncpg
import pytest
from sqlalchemy import text

from app.db import session as db_session
from scripts.bootstrap_access_administrator import _run as run_bootstrap
from tests.conftest import (
    _alembic_config, _assert_owned_test_database, _drop_test_database_schema,
    _verify_test_database_schema,
)
from tests.finance.test_selected_reward_migration import _snapshot
from tests.reviews.lifecycle.transition_support import command_for, transition
from tests.tasks.post_submit_routing.outcome_support import apply_outcome, authorized_routing_source

pytestmark = pytest.mark.postgres_schema_contract


async def _prior_schema(url):
    await db_session.dispose_engine()
    await _drop_test_database_schema(url)
    await asyncio.to_thread(command.upgrade, _alembic_config(), "0072_fulfillment_roots")


async def _pending_earning(tmp_path, url, signed):
    """Run unchanged0072 owners; never project a later schema into prior data."""
    admin = await signed.actor("receipt-migration-admin")
    code, result = await run_bootstrap(admin.id, execute=True)
    assert code == 0, result
    operator = await signed.actor("receipt-migration-operator")
    await signed.grant(admin, operator, role="operator")
    await transition(await command_for(operator.id, "shadow"))
    await transition(await command_for(operator.id, "live"))
    async with authorized_routing_source(
        tmp_path, url, contribution_awards=("money",), human_review_required=False,
    ) as source:
        async with source.factory() as session, session.begin():
            result = await apply_outcome(session, source, 2)
            assert not result.replayed
        async with source.factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM public.compensation_fulfillment_roots")) == 1
            assert await session.scalar(text("SELECT count(*) FROM public.outbox_events "
                "WHERE event_type='compensation.obligation.deliver'")) == 1
    return operator


async def _physical_earning_rows(url):
    connection = await asyncpg.connect(url.replace("+asyncpg", "", 1))
    try:
        await _assert_owned_test_database(connection, url)
        result = {}
        for name in (
            "compensation_awards", "compensation_fulfillment_roots", "outbox_events",
            "audit_events", "joint_lifecycle_release_control", "joint_lifecycle_transitions",
        ):
            result[name] = await connection.fetch(
                f"SELECT jsonb_build_object('row',to_jsonb(t),'tableoid',t.tableoid::text,"
                f"'xmin',t.xmin::text)::text FROM public.{name} t ORDER BY 1"
            )
        return result
    finally:
        await connection.close()


async def _upgrade_and_preserve(url):
    before = await _snapshot(url)
    physical = await _physical_earning_rows(url)
    await db_session.dispose_engine()
    await asyncio.to_thread(command.upgrade, _alembic_config(), "head")
    await _verify_test_database_schema(url)
    after = await _snapshot(url)
    for name, rows in before[0].items():
        if name != "alembic_version":
            assert after[0][name] == rows, name
    assert after[0]["compensation_fulfillment_receipts"] == []
    assert after[0]["compensation_fulfillment_exceptions"] == []
    assert after[0]["alembic_version"] == ['{"version_num":"0073_fulfillment_evidence"}']
    assert await _physical_earning_rows(url) == physical
    await asyncio.to_thread(command.upgrade, _alembic_config(), "head")
    assert await _snapshot(url) == after


async def test_receipt_migration_installs_from_actual_empty_0072(isolated_database_env, migration_lock):
    with migration_lock():
        await _prior_schema(isolated_database_env)
        await _upgrade_and_preserve(isolated_database_env)


async def test_receipt_migration_preserves_pending_root_source_outbox_and_authority(
    tmp_path, isolated_database_env, signed_access, migration_lock,
):
    with migration_lock():
        await _prior_schema(isolated_database_env)
        operator = await _pending_earning(tmp_path, isolated_database_env, signed_access)
        before = await _snapshot(isolated_database_env)
        physical = await _physical_earning_rows(isolated_database_env)
        with pytest.raises(RuntimeError, match="requires the lifecycle disabled"):
            await asyncio.to_thread(command.upgrade, _alembic_config(), "head")
        assert await _snapshot(isolated_database_env) == before
        assert await _physical_earning_rows(isolated_database_env) == physical
        await transition(await command_for(operator.id, "draining"))
        await transition(await command_for(operator.id, "disabled"))
        await _upgrade_and_preserve(isolated_database_env)
