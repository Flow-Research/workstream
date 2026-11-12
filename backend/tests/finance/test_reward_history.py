"""Genuine archived rows preserve precise economics and original command replay."""

from copy import deepcopy
import asyncio
from decimal import Decimal
from uuid import UUID

from alembic import command
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id

from app.db import session as db_session
from app.modules.artifacts.task_import_sources import ArtifactTaskImportSourceCommands
from tests.finance.reward_history import reward_history, restore_reward_predecessor
from tests.migration_fixtures import _config
from tests.test_task_import_sources import import_source_client as import_source_client
from tests.test_tasks import auth_headers, task_database_env as task_database_env

pytestmark = pytest.mark.postgres_schema_contract


async def economic_snapshot():
    """Compare every retained economic field, excluding only new mechanical labels."""
    async with db_session.get_session_factory()() as session:
        result = {}
        for table in (
            "contribution_policy_versions",
            "contribution_rules",
            "contribution_award_definitions",
            "compensation_awards",
            "contribution_records",
            "final_acceptances",
        ):
            exclusions = "-'reward_model_version'-'task_size'"
            if table == "contribution_policy_versions":
                exclusions += "-'instrument_type'-'unit_code'-'adapter_binding_id'"
            result[table] = (
                await session.scalars(
                    text(
                        f"SELECT (to_jsonb(r){exclusions})::text FROM public.{table} r ORDER BY id"
                    )
                )
            ).all()
        return result


async def test_archived_dual_awards_restore_without_losing_decimal_precision(isolated_database_env):
    snapshot = reward_history("dual")
    await restore_reward_predecessor(isolated_database_env, snapshot)
    before = await economic_snapshot()
    with pytest.raises(RuntimeError, match="shared lifecycle disabled after drain"):
        await asyncio.to_thread(command.upgrade, _config(), "head")
    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(text("SELECT version_num FROM alembic_version"))
            == snapshot["source_revision"]
        )
    from tests.reviews.lifecycle.transition_support import command_for, transition

    operator = next(
        row["target_actor_profile_id"]
        for row in snapshot["tables"]["admin_role_grants"]
        if row["role"] == "operator"
    )
    for phase in ("draining", "disabled"):
        await transition(await command_for(UUID(operator), phase))
    await db_session.dispose_engine()
    await asyncio.to_thread(command.upgrade, _config(), "head")
    assert await economic_snapshot() == before
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(text("SELECT count(*) FROM workstream_tasks WHERE task_size IS NOT NULL")) == 0
    for table, message in (
        ("contribution_award_definitions", "new reward definitions require exact v2 policy"),
        ("contribution_records", "new contribution and award effects require v2"),
        ("compensation_awards", "new contribution and award effects require v2"),
    ):
        async with db_session.get_session_factory()() as session, session.begin():
            with pytest.raises(DBAPIError, match=message):
                async with session.begin_nested():
                    await session.execute(
                        text(
                            f"INSERT INTO public.{table} SELECT (jsonb_populate_record(NULL::public.{table}, "
                            "to_jsonb(source)||jsonb_build_object('id',CAST(:id AS uuid)))).* "
                            f"FROM public.{table} source ORDER BY source.id LIMIT 1"
                        ),
                        {"id": new_record_id()},
                    )
                    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert await economic_snapshot() == before
    async with db_session.get_session_factory()() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id,instrument_type,quantity FROM public.compensation_awards ORDER BY instrument_type"
                )
            )
        ).all()
        assert {row.instrument_type for row in rows} == {"money", "project_points"}
        assert rows[0].quantity == Decimal("2.125000000000000001")
        assert rows[1].quantity == Decimal("7")
        assert {str(row.id) for row in rows} == set(snapshot["seed"]["award_ids"])
        assert (
            await session.scalar(
                text("SELECT bool_and(reward_model_version=1) FROM compensation_awards")
            )
            is True
        )
        assert (
            await session.scalar(
                text(
                    "SELECT bool_and(public.task_routing_receipt_valid(m)) "
                    "FROM public.task_post_submit_routing_manifests m"
                )
            )
            is True
        )


async def test_archive_numeric_descriptor_cannot_reinterpret_other_fields(isolated_database_env):
    snapshot = deepcopy(reward_history("dual"))
    snapshot["numeric_columns"]["compensation_awards"] = ["contributor_id"]
    with pytest.raises(AssertionError, match="numeric columns differ"):
        await restore_reward_predecessor(isolated_database_env, snapshot)


async def command_snapshot():
    async with db_session.get_session_factory()() as session:
        return (
            await session.execute(
                text("""
            SELECT (SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM public.task_command_receipts r),
                   (SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM public.task_import_batches r),
                   (SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM public.task_import_batch_members r),
                   (SELECT count(*) FROM public.workstream_tasks),
                   (SELECT count(*) FROM public.compensation_awards),
                   (SELECT count(*) FROM public.task_import_batch_command_receipts)
        """)
            )
        ).one()


async def test_archived_omitted_size_create_and_import_replay_exactly_with_fresh_auth(
    import_source_client,
    monkeypatch,
):
    snapshot = reward_history("task_replay")
    await restore_reward_predecessor(db_session.get_database_url(), snapshot)
    await db_session.dispose_engine()
    await asyncio.to_thread(command.upgrade, _config(), "head")
    seed = snapshot["seed"]
    before = await command_snapshot()
    async with db_session.get_session_factory()() as session:
        decisions_before = await session.scalar(
            text("SELECT count(*) FROM public.audit_events WHERE event_domain='authority'")
        )

    def forbidden(*args, **kwargs):
        raise AssertionError("historical replay must not reopen provider bytes or reinterpret JSON")

    monkeypatch.setattr(ArtifactTaskImportSourceCommands, "open", forbidden)
    monkeypatch.setattr("app.modules.tasks.task_import_batches.parse_task_import", forbidden)
    client = import_source_client
    headers = auth_headers() | {"Idempotency-Key": seed["create_idempotency_key"]}
    response = await client.post(
        f"/api/v1/projects/{seed['project_id']}/tasks",
        headers=headers,
        json=seed["create_request"],
    )
    assert response.status_code == 201, response.text
    assert response.json() == seed["create_response"]
    imported = await client.post(
        f"/api/v1/projects/{seed['project_id']}/task-import-batches",
        headers=auth_headers() | {"Idempotency-Key": seed["import_idempotency_key"]},
        json=seed["import_request"],
    )
    assert imported.status_code == 201, imported.text
    assert imported.json() == seed["import_response"]
    read = await client.get(
        f"/api/v1/projects/{seed['project_id']}/task-import-batches/"
        f"{seed['import_response']['batch_id']}",
        headers=auth_headers(),
    )
    assert read.status_code == 200, read.text
    assert read.json()["creation"] == seed["import_response"]
    changed = await client.post(
        f"/api/v1/projects/{seed['project_id']}/tasks",
        headers=headers,
        json=seed["create_request"] | {"title": "Changed historical request"},
    )
    assert changed.status_code == 409, changed.text
    for size in ("small", "medium"):
        changed_size = await client.post(
            f"/api/v1/projects/{seed['project_id']}/tasks", headers=headers,
            json=seed["create_request"] | {"task_size": size},
        )
        assert changed_size.status_code == 409, changed_size.text
    assert "task_size" not in response.json()
    assert all("task_size" not in task for task in imported.json()["tasks"])
    assert await command_snapshot() == before
    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                text("SELECT count(*) FROM public.audit_events WHERE event_domain='authority'")
            )
            > decisions_before
        )
