"""Retained attempts survive the additive configuration migration unchanged."""

import asyncio
import json
from project_create_fixtures import guide_example_columns
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import insert, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.modules.projects.guide_compilation.models import ProjectGuideCompilationAttempt
from .helpers import context, identity, ids, SHA256

pytestmark = pytest.mark.postgres_schema_contract


async def test_upgrade_preserves_unconfigured_attempt_and_refuses_dispatch(isolated_database_env, migration_lock, migration_schema_at):
    def migrate(target):
        with migration_lock():
            command.upgrade(Config("alembic.ini"), target)
    def prepare_prior_schema():
        with migration_lock():
            migration_schema_at("0014_project_role_scope")
    await asyncio.to_thread(prepare_prior_schema)
    values = await _seed_retained_attempt_parents(isolated_database_env)
    attempt_identity = identity(context(values))
    row = attempt_identity.model_dump(mode="json") | {
        "id": uuid4(), "provider_idempotency_key": attempt_identity.provider_idempotency_key(),
        "status": "compilation_reserved",
    }
    engine = create_async_engine(isolated_database_env)
    try:
        async with engine.begin() as connection:
            await connection.execute(insert(ProjectGuideCompilationAttempt).values(**row))
            before = await connection.scalar(text("select to_jsonb(a) from project_guide_compilation_attempts a"))
        await asyncio.to_thread(migrate, "head")
        async with engine.connect() as connection:
            after = await connection.scalar(text("select to_jsonb(a) from project_guide_compilation_attempts a"))
        assert after == before | {"runtime_configuration": None, "runtime_configuration_hash": None}
        async with engine.connect() as connection:
            assert await connection.scalar(text(
                "select retained_content_markdown from project_guides where id=:id"
            ), {"id": str(values["guide"])}) == "retained original text"
        for statement, params in (
            ("update project_guides set retained_content_markdown='replacement' where id=:id",
             {"id": str(values["guide"])}),
            ("insert into project_guides(id,project_id,version,status,retained_content_markdown,created_by,task_examples,task_examples_hash) "
             "values(:id,:project,'new-guide','draft','new inline body','fixture',cast(:examples as json),:examples_hash)",
             {"id": str(uuid4()), "project": str(values["project"]),
              "examples": json.dumps(guide_example_columns()["task_examples"]),
              "examples_hash": guide_example_columns()["task_examples_hash"]}),
        ):
            async with engine.begin() as connection:
                with pytest.raises(DBAPIError, match="retained guide content is read only") as error:
                    await connection.execute(text(statement), params)
                assert error.value.orig.sqlstate == "23514"
        async with engine.connect() as connection:
            assert await connection.scalar(text(
                "select retained_content_markdown from project_guides where id=:id"
            ), {"id": str(values["guide"])}) == "retained original text"
        async with engine.begin() as connection:
            with pytest.raises(DBAPIError, match="retained compilation runtime is read only") as error:
                await connection.execute(text("update project_guide_compilation_attempts set status='compilation_provider_uncertain',provider_uncertain_at=now() where id=:id"), {"id": row["id"]})
            assert error.value.orig.sqlstate == "23514"
        async with engine.connect() as connection:
            assert await connection.scalar(text("select to_jsonb(a) from project_guide_compilation_attempts a")) == after
    finally:
        await engine.dispose()


async def _seed_retained_attempt_parents(url):
    """Explicit pre-document schema fixture; never a callable product path."""
    from scripts.run_isolated_tests import NAME_RE
    values = ids()
    params = {key: str(value) for key, value in values.items()} | {"digest": SHA256}
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            assert NAME_RE.fullmatch(await connection.scalar(text("select current_database()")))
            for table in ("projects", "project_guides", "guide_source_snapshots", "project_setup_runs"):
                await connection.execute(text(f"alter table {table} disable trigger user"))
            for statement in (
                "insert into actor_profiles(id,actor_kind,status,provisioning_method,service_identity,created_by) values(:actor,'service','active','manual_service_provisioning','workstream.project.setup','fixture')",
                "insert into actor_identity_links(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by) values(:link,:actor,'workstream-internal','workstream.project.setup','service','active','fixture')",
                "insert into projects(id,name,slug,status) values(:project,'Retained guide',:project,'draft')",
                "insert into project_guides(id,project_id,version,status,content_markdown,created_by) values(:guide,:project,'v1','draft','retained original text','fixture')",
                "insert into guide_source_snapshots(id,project_id,guide_id,guide_version,manifest_schema_version,manifest_json,bundle_hash,captured_by) values(:snapshot,:project,:guide,'v1','guide_source_snapshot.v1','{}'::json,:digest,'fixture')",
                "insert into project_setup_runs(id,project_id,guide_id,guide_version,source_snapshot_id,source_snapshot_hash,setup_generation,status,current_step,created_by) values(:setup_1,:project,:guide,'v1',:snapshot,:digest,1,'queued','queued','fixture')",
            ):
                await connection.execute(text(statement), params)
            for table in ("project_setup_runs", "guide_source_snapshots", "project_guides", "projects"):
                await connection.execute(text(f"alter table {table} enable trigger user"))
    finally:
        await engine.dispose()
    return values
