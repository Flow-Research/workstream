"""PostgreSQL proof for the two-role v0.1 authority migration."""

import asyncio
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from project_create_fixtures import insert_historical_project

PRIOR = "0013_compilation_request_origin"
OWN = "0014_project_role_scope"
_ADJUDICATOR_ARRAY_TOKEN = ", ('adjudicator'::character varying)::text"
_EVENT_ARRAY_TOKEN = ",\'adjudicator\'"

pytestmark = pytest.mark.postgres_schema_contract


def _config() -> Config:
    return Config(Path(__file__).resolve().parents[2] / "alembic.ini")


async def _fetch(database_url: str, statement: str, *arguments):
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        return await connection.fetch(statement, *arguments)
    finally:
        await connection.close()


async def _value(database_url: str, statement: str, *arguments):
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        return await connection.fetchval(statement, *arguments)
    finally:
        await connection.close()


async def _seed_incompatible_snapshot(
    database_url: str,
    *,
    actor: str,
    grantor: str,
    grant: str,
    project: str,
    snapshot: str,
) -> None:
    engine = create_async_engine(database_url)
    try:
        async with async_sessionmaker(engine)() as session, session.begin():
            await session.execute(
                text(
                    "insert into actor_profiles "
                    "(id,actor_kind,status,provisioning_method,created_by) values "
                    "(:actor,'human','active','automatic_first_access','migration-test'),"
                    "(:grantor,'human','active','automatic_first_access','migration-test')"
                ),
                {"actor": actor, "grantor": grantor},
            )
            await session.execute(
                text(
                    "insert into actor_identity_links "
                    "(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by,"
                    "last_verified_at) values "
                    "(:actor_link,:actor,'https://migration.test','retained-role-actor',"
                    "'human','active','migration-test',clock_timestamp()),"
                    "(:grantor_link,:grantor,'https://migration.test','retained-role-grantor',"
                    "'human','active','migration-test',clock_timestamp())"
                ),
                {
                    "actor_link": str(uuid4()),
                    "actor": actor,
                    "grantor_link": str(uuid4()),
                    "grantor": grantor,
                },
            )
            await session.execute(
                text(
                    "insert into admin_role_grants "
                    "(id,target_actor_profile_id,role,scope_type,status,version,"
                    "granted_by_system_principal,grant_reason) values "
                    "(:grant,:grantor,'access_administrator','system','active',1,"
                    "'workstream:system:bootstrap','migration test')"
                ),
                {"grant": grant, "grantor": grantor},
            )
            await session.execute(
                text(
                    "update authority_control set bootstrap_completed=true,"
                    "bootstrap_grant_id=:grant,version=1 where id=1"
                ),
                {"grant": grant},
            )
            await insert_historical_project(
                session,
                project_id=project,
                name="Retained role history",
                slug="retained-role-history",
            )
            await session.execute(
                text(
                    "insert into project_role_qualification_snapshots "
                    "(id,project_id,actor_profile_id,requested_role,skills_snapshot,"
                    "reputation_snapshot,prior_project_work_refs,external_expertise_refs,"
                    "captured_by_actor_profile_id,captured_by_admin_role_grant_id) values "
                    "(:snapshot,:project,:actor,'adjudicator',"
                    "jsonb_build_object('availability','available','reference_ids',"
                    "jsonb_build_array('skill:test'),'unavailable_reason',null),"
                    "jsonb_build_object('availability','unavailable','reference_ids',"
                    "'[]'::jsonb,'unavailable_reason','no_record'),"
                    "'[]'::jsonb,'[]'::jsonb,:grantor,:grant)"
                ),
                {
                    "snapshot": snapshot,
                    "project": project,
                    "actor": actor,
                    "grantor": grantor,
                    "grant": grant,
                },
            )
    finally:
        await engine.dispose()


async def _definitions(database_url: str) -> dict[str, str]:
    rows = await _fetch(
        database_url,
        "select c.conname as name,pg_get_constraintdef(c.oid) as definition "
        "from pg_constraint c join pg_class t on t.oid=c.conrelid "
        "where (t.relname,c.conname) in "
        "(('project_role_grants','ck_project_role_grants_role'),"
        "('project_role_qualification_snapshots',"
        "'ck_project_role_qualification_snapshots_role')) order by c.conname",
    )
    result = {row["name"]: row["definition"] for row in rows}
    for signature in (
        "authority_event_facts_are_safe(text,json,json,text)",
        "validate_linked_authority_event()",
    ):
        result[signature] = await _value(
            database_url,
            "select pg_get_functiondef(to_regprocedure($1))",
            signature,
        )
    return result


def test_project_role_scope_round_trip_preserves_unrelated_contracts(
    isolated_database_env: str, migration_lock, migration_schema_at
) -> None:
    with migration_lock():
        migration_schema_at(PRIOR)
        before = asyncio.run(_definitions(isolated_database_env))
        command.upgrade(_config(), OWN)
        narrowed = asyncio.run(_definitions(isolated_database_env))

        for name in (
            "ck_project_role_grants_role",
            "ck_project_role_qualification_snapshots_role",
        ):
            assert _ADJUDICATOR_ARRAY_TOKEN in before[name]
            assert _ADJUDICATOR_ARRAY_TOKEN not in narrowed[name]
            assert (
                narrowed[name].replace(
                    "('reviewer'::character varying)::text",
                    "('reviewer'::character varying)::text" + _ADJUDICATOR_ARRAY_TOKEN,
                    1,
                )
                == before[name]
            )
        assert before["authority_event_facts_are_safe(text,json,json,text)"].count(
            _EVENT_ARRAY_TOKEN
        ) == 3
        assert "adjudicator" not in narrowed[
            "authority_event_facts_are_safe(text,json,json,text)"
        ]
        assert "adjudicator" in before["validate_linked_authority_event()"]
        assert "adjudicator" not in narrowed["validate_linked_authority_event()"]

        command.downgrade(_config(), PRIOR)
        assert asyncio.run(_definitions(isolated_database_env)) == before
        command.upgrade(_config(), OWN)
        assert asyncio.run(_definitions(isolated_database_env)) == narrowed


def test_project_role_scope_database_accepts_only_current_role_audit_facts(
    isolated_database_env: str,
) -> None:
    project = str(uuid4())
    statement = (
        "select authority_event_facts_are_safe('ProjectRoleGrantIssued',null,"
        "json_build_object('status','active','role',$1::text,'scope_type','project',"
        "'scope_id',$2::text,'effective',true),$2::text)"
    )
    assert asyncio.run(_value(isolated_database_env, statement, "submitter", project)) is True
    assert asyncio.run(_value(isolated_database_env, statement, "reviewer", project)) is True
    assert asyncio.run(_value(isolated_database_env, statement, "adjudicator", project)) is False
    definitions = asyncio.run(_definitions(isolated_database_env))
    assert all(
        "adjudicator" not in definition for definition in definitions.values()
    )


def test_project_role_scope_upgrade_refuses_incompatible_retained_history_atomically(
    isolated_database_env: str, migration_lock, migration_schema_at
) -> None:
    with migration_lock():
        migration_schema_at(PRIOR)
    actor, grantor, project, grant, snapshot = (str(uuid4()) for _ in range(5))
    asyncio.run(
        _seed_incompatible_snapshot(
            isolated_database_env,
            actor=actor,
            grantor=grantor,
            grant=grant,
            project=project,
            snapshot=snapshot,
        )
    )
    before = asyncio.run(_definitions(isolated_database_env))
    with migration_lock(), pytest.raises(
        RuntimeError, match="retained adjudicator authority history prevents role narrowing"
    ):
        command.upgrade(_config(), OWN)
    assert asyncio.run(_value(isolated_database_env, "select version_num from alembic_version")) == PRIOR
    assert asyncio.run(_definitions(isolated_database_env)) == before
    assert asyncio.run(
        _value(
            isolated_database_env,
            "select requested_role from project_role_qualification_snapshots where id=$1::uuid",
            snapshot,
        )
    ) == "adjudicator"
