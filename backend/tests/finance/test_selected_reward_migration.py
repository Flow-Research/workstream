"""Actual predecessor upgrade/refusal preserves data without another runtime format."""

import asyncio
import json

from alembic import command
import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.projects import project_locked_policy_context_port
from app.core.identifiers import new_record_id
from app.modules.tasks.service import TaskService
from scripts.schema_baseline_manifest import build_manifest
from tests.conftest import (
    _alembic_config, _assert_owned_test_database, _drop_test_database_schema,
    _verify_test_database_schema,
)
from tests.post_submit_materialization_helpers import _material_storage
from tests.selected_policy_fixtures import approved_selected_policy_fixture
from tests.test_artifact_admission import _context, _seed_human_actor

pytestmark = pytest.mark.postgres_schema_contract


async def _snapshot(url):
    connection = await asyncpg.connect(url.replace("postgresql+asyncpg", "postgresql", 1))
    try:
        await _assert_owned_test_database(connection, url)
        tables = await connection.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        # Capture exact retained rows; reuse the complete schema inventory below.
        rows = {}
        for table in tables:
            name = table["tablename"]
            assert name.replace("_", "").isalnum()
            rows[name] = await connection.fetch(f'SELECT row_to_json(t)::text AS value FROM public."{name}" t ORDER BY 1')
            rows[name] = [row["value"] for row in rows[name]]
        return rows, await build_manifest(url)
    finally:
        await connection.close()


async def _screened_predecessor(url, tmp_path):
    """Prepare legal predecessor data using current guide owners and its exact SQL schema.

    The predecessor has no selection column. This is migration data preparation,
    not an application writer, decoder or compatibility path.
    """
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings, bootstrap, namespace, _store, _scratch, manager = _material_storage(tmp_path, "local", None, None, None)
    try:
        plan, _policy = await approved_selected_policy_fixture(
            factory, namespace, guide_version="initial", contribution_awards=("money",),
        )
        actor = _context()
        task_id = new_record_id()
        async with factory() as session, session.begin():
            await _seed_human_actor(session, actor)
            context = await project_locked_policy_context_port(session).lock_active_policy_context(plan.lineage.project_id)
            stamps = TaskService._policy_stamps(context)
            await session.execute(text("""INSERT INTO public.workstream_tasks
                (id,project_id,title,description,source_type,task_size,skill_tags,status,created_by)
                VALUES (:id,:project,'Retained Medium work','Exact approved work','manual','medium','[]'::json,'draft',:actor)"""),
                {"id": task_id, "project": plan.lineage.project_id, "actor": str(actor.actor_profile_id)})
            assignments = [f"{name}=" + (f"CAST(:{name} AS json)" if name.endswith("_body") else f":{name}")
                           for name in stamps]
            values = {name: json.dumps(value) if isinstance(value, dict) else value for name,value in stamps.items()}
            await session.execute(text("UPDATE public.workstream_tasks SET status='screening'," +
                                       ",".join(assignments) + " WHERE id=:task"), values | {"task": task_id})
        return task_id
    finally:
        manager.close()
        bootstrap.close()
        await engine.dispose()


def test_fresh_install_and_empty_current_upgrade(isolated_database_env, migration_lock):
    config = _alembic_config()
    with migration_lock():
        asyncio.run(_verify_test_database_schema(isolated_database_env))
        asyncio.run(_drop_test_database_schema(isolated_database_env))
        command.upgrade(config, "0070_task_size")
        before = asyncio.run(_snapshot(isolated_database_env))
        assert before[0]["alembic_version"] == ['{"version_num":"0070_task_size"}']
        command.upgrade(config, "head")
        asyncio.run(_verify_test_database_schema(isolated_database_env))
        current = asyncio.run(_snapshot(isolated_database_env))
        assert current[0]["alembic_version"] == ['{"version_num":"0071_selected_task_reward"}']
        for table, rows in before[0].items():
            if table != "alembic_version":
                assert current[0][table] == rows
        command.upgrade(config, "head")
        assert asyncio.run(_snapshot(isolated_database_env)) == current


def test_incompatible_facts_refuse_without_rewrite(isolated_database_env, migration_lock, tmp_path):
    config = _alembic_config()
    with migration_lock():
        asyncio.run(_drop_test_database_schema(isolated_database_env))
        command.upgrade(config, "0070_task_size")
        task = asyncio.run(_screened_predecessor(isolated_database_env, tmp_path))
        before = asyncio.run(_snapshot(isolated_database_env))
        assert any(str(task) in row for row in before[0]["workstream_tasks"])
        with pytest.raises(RuntimeError, match="refuses work without immutable selection evidence"):
            command.upgrade(config, "head")
        assert asyncio.run(_snapshot(isolated_database_env)) == before
