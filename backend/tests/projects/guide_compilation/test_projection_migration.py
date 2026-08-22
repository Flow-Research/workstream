"""Database custody proofs for unified-compilation projections."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import asyncpg
import pytest

from .helpers import seed_database
from .test_projection_postgresql import _project_both


def _url(value: str) -> str:
    return value.replace("+asyncpg", "")


def _config() -> Config:
    return Config(Path(__file__).resolve().parents[3] / "alembic.ini")


async def _version(database_url: str) -> str:
    connection = await asyncpg.connect(_url(database_url))
    try:
        return await connection.fetchval("select version_num from alembic_version")
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_sql_digest_vectors_match_python_and_each_field_is_sensitive(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    await _project_both(clean_postgres_database, values)
    connection = await asyncpg.connect(_url(clean_postgres_database))
    try:
        rows = await connection.fetch(
            "select o.*,project_guide_projection_facts_digest(o) as sql_facts,"
            "project_guide_projection_authority_digest(o) as sql_authority "
            "from project_guide_component_projection_operations o order by component"
        )
        assert len(rows) == 2
        for row in rows:
            assert row["sql_facts"] == row["facts_digest"]
            assert row["sql_authority"] == row["authority_resource_digest"]

        common_mutations = {
            "attempt_id": str(uuid4()),
            "celery_task_id": str(uuid4()),
            "compilation_agent_name": "ChangedAgent",
            "compilation_agent_version": "v2",
            "compilation_id": str(uuid4()),
            "component_hash": "sha256:" + "b" * 64,
            "guide_id": str(uuid4()),
            "guide_version": "v2",
            "project_id": str(uuid4()),
            "provider_idempotency_key": str(uuid4()),
            "request_operation_id": str(uuid4()),
            "result_hash": "sha256:" + "b" * 64,
            "result_schema_version": "changed.v1",
            "setup_generation": 2,
            "setup_run_id": str(uuid4()),
            "source_snapshot_hash": "sha256:" + "b" * 64,
            "source_snapshot_id": str(uuid4()),
            "source_state_digest": "sha256:" + "b" * 64,
        }
        component_mutations = {
            "guide_sufficiency": {
                "material_byte_count": 42,
                "material_sha256": "sha256:" + "b" * 64,
                "output_digest": "sha256:" + "b" * 64,
                "output_id": str(uuid4()),
            },
            "submission_artifact_policy": {
                "output_digest": "sha256:" + "b" * 64,
                "output_id": str(uuid4()),
                "prior_operation_id": str(uuid4()),
                "prior_output_digest": "sha256:" + "b" * 64,
                "prior_output_id": str(uuid4()),
            },
        }
        for row in rows:
            mutations = common_mutations | component_mutations[row["component"]]
            for field, replacement in mutations.items():
                mutated = await connection.fetchval(
                    "select project_guide_projection_facts_digest("
                    "jsonb_populate_record(null::project_guide_component_projection_operations,"
                    "to_jsonb(o)||jsonb_build_object($2::text,$3::jsonb))) "
                    "from project_guide_component_projection_operations o "
                    "where operation_id=$1",
                    row["operation_id"],
                    field,
                    json.dumps(replacement),
                )
                assert mutated != row["facts_digest"], field

        authority_mutations = {
            "action_id": "changed.action",
            "actor_profile_id": str(uuid4()),
            "facts_digest": "sha256:" + "b" * 64,
            "identity_link_id": str(uuid4()),
            "operation_id": str(uuid4()),
            "permission_id": "changed.permission",
            "project_id": str(uuid4()),
            "service_identity": "changed.service",
        }
        for row in rows:
            for field, replacement in authority_mutations.items():
                mutated = await connection.fetchval(
                    "select project_guide_projection_authority_digest("
                    "jsonb_populate_record(null::project_guide_component_projection_operations,"
                    "to_jsonb(o)||jsonb_build_object($2::text,$3::jsonb))) "
                    "from project_guide_component_projection_operations o "
                    "where operation_id=$1",
                    row["operation_id"],
                    field,
                    json.dumps(replacement),
                )
                assert mutated != row["authority_resource_digest"], field
    finally:
        await connection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "statement",
    [
        "update project_guide_component_projection_operations set guide_version='v2'",
        "delete from project_guide_component_projection_operations",
        "truncate project_guide_component_projection_operations",
        "update guide_sufficiency_reports set summary='changed'",
        "delete from guide_sufficiency_reports",
        "truncate guide_sufficiency_reports",
        "update guide_sufficiency_report_source_usages set item_order=99",
        "delete from guide_sufficiency_report_source_usages",
        "truncate guide_sufficiency_report_source_usages",
        "update submission_artifact_policies set policy_body='{}'::json",
        "delete from submission_artifact_policies",
        "truncate submission_artifact_policies",
    ],
)
async def test_projection_custody_rejects_direct_sql_changes(
    clean_postgres_database: str,
    statement: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    await _project_both(clean_postgres_database, values)
    connection = await asyncpg.connect(_url(clean_postgres_database))
    try:
        with pytest.raises(asyncpg.PostgresError):
            async with connection.transaction():
                await connection.execute(statement)
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_verified_reports_allow_same_snapshot_across_setup_generations(
    clean_postgres_database: str,
) -> None:
    """Prove the migrated canonical identity is snapshot plus generation."""
    values = await seed_database(clean_postgres_database, generations=2)
    connection = await asyncpg.connect(_url(clean_postgres_database))
    try:
        for generation in (1, 2):
            await connection.execute(
                "insert into guide_sufficiency_reports(id,project_id,guide_id,"
                "guide_version,source_snapshot_id,source_snapshot_hash,status,findings,"
                "project_setup_run_id,setup_generation,agent_material_sha256,"
                "agent_material_byte_count,created_by) values($1,$2,$3,'v1',$4,$5,"
                "'passed','[]'::json,$6,$7,$5,1,'migration-test')",
                str(uuid4()),
                str(values["project"]),
                str(values["guide"]),
                str(values["snapshot"]),
                "sha256:" + "a" * 64,
                str(values[f"setup_{generation}"]),
                generation,
            )
        assert await connection.fetchval(
            "select count(*) from guide_sufficiency_reports where source_snapshot_id=$1",
            str(values["snapshot"]),
        ) == 2
    finally:
        await connection.close()


def test_empty_projection_migration_downgrades_and_reupgrades(
    isolated_database_env: str,
    migration_lock,
) -> None:
    clean_postgres_database = isolated_database_env
    with migration_lock():
        command.downgrade(_config(), "0008_guide_compilation_authorized_persistence")
    assert asyncio.run(_version(clean_postgres_database)) == (
        "0008_guide_compilation_authorized_persistence"
    )
    with migration_lock():
        command.upgrade(_config(), "0009_guide_compilation_projections")
        command.upgrade(_config(), "0009_guide_compilation_projections")
    assert asyncio.run(_version(clean_postgres_database)) == (
        "0009_guide_compilation_projections"
    )


def test_populated_projection_migration_refuses_downgrade(
    isolated_database_env: str,
    migration_lock,
) -> None:
    clean_postgres_database = isolated_database_env
    values = asyncio.run(seed_database(clean_postgres_database))
    asyncio.run(_project_both(clean_postgres_database, values))
    with migration_lock(), pytest.raises(
        RuntimeError, match="guide projection custody is non-empty"
    ):
        command.downgrade(_config(), "0008_guide_compilation_authorized_persistence")
    assert asyncio.run(_version(clean_postgres_database)) == (
        "0009_guide_compilation_projections"
    )
