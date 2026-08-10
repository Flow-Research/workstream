"""PostgreSQL topology proof for AUTH compilation migration 0063."""

import asyncio
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import asyncpg
import pytest

pytestmark = pytest.mark.postgres_schema_contract


def _config() -> Config:
    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return config


async def _registry_state(database_url: str) -> tuple[str, int, int, int]:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        head = await connection.fetchval("select version_num from alembic_version")
        action = await connection.fetchval(
            "select count(*) from pg_constraint where conrelid='audit_events'::regclass "
            "and conname='ck_audit_events_authority_registries' and "
            "pg_get_constraintdef(oid) like '%project.guide_compilation.request%'"
        )
        evidence = await connection.fetchval(
            "select count(*) from pg_constraint where conrelid='audit_events'::regclass "
            "and conname='ck_audit_events_authorization_action_evidence' and "
            "pg_get_constraintdef(oid) like '%project.guide_compilation.request%'"
        )
        resource = await connection.fetchval(
            "select count(*) from pg_constraint where conrelid='audit_events'::regclass "
            "and conname='ck_audit_events_authority_privacy_bounds' and "
            "pg_get_constraintdef(oid) like '%project_guide_compilation_request%'"
        )
        return head, action, evidence, resource
    finally:
        await connection.close()


async def _insert_authority_evidence(database_url: str, action: str) -> str:
    event_id = str(uuid4())
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await connection.execute(
            "insert into audit_events "
            "(id,entity_type,entity_id,event_type,actor_id,actor_roles,claim_snapshot,"
            "auth_source,is_dev_auth,event_payload,event_domain,event_version,actor_ref_kind,"
            "request_id,correlation_id,permission_id,action_id,reason,denial_code,after_facts) "
            "values($1,'authorization_decision',$1,'SensitiveAuthorizationDenied',"
            "'workstream:system:bootstrap','[]'::json,'{}'::json,'local_authority',false,"
            "'{}'::json,'authority',1,'system_principal',$2,$3,$4,$4,"
            "'authorization_evaluation','permission_not_granted','{\"allowed\": false}'::json)",
            event_id,
            str(uuid4()),
            str(uuid4()),
            action,
        )
        return event_id
    finally:
        await connection.close()


async def _insert_permission_without_action(database_url: str, permission: str) -> str:
    event_id = str(uuid4())
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await connection.execute(
            "insert into audit_events "
            "(id,entity_type,entity_id,event_type,actor_id,actor_roles,claim_snapshot,"
            "auth_source,is_dev_auth,event_payload,event_domain,event_version,actor_ref_kind,"
            "request_id,correlation_id,permission_id,reason,denial_code,after_facts) "
            "values($1,'authorization_decision',$1,'SensitiveAuthorizationDenied',"
            "'workstream:system:bootstrap','[]'::json,'{}'::json,'local_authority',false,"
            "'{}'::json,'authority',1,'system_principal',$2,$3,$4,"
            "'authorization_evaluation','permission_not_granted','{\"allowed\": false}'::json)",
            event_id,
            str(uuid4()),
            str(uuid4()),
            permission,
        )
        return event_id
    finally:
        await connection.close()


async def _insert_compilation_registry_reference(
    database_url: str, permission: str
) -> str:
    event_id = str(uuid4())
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await connection.execute(
            "insert into audit_events "
            "(id,entity_type,entity_id,event_type,actor_id,actor_roles,claim_snapshot,"
            "auth_source,is_dev_auth,event_payload,event_domain,event_version,actor_ref_kind,"
            "request_id,correlation_id,permission_id,action_id,target_ref_kind,target_ref_id,"
            "reason,after_facts) values($1,'authorization_decision',$1,"
            "'SensitiveAuthorizationAllowed','workstream:system:bootstrap','[]'::json,"
            "'{}'::json,'local_authority',false,'{}'::json,'authority',1,"
            "'system_principal',$2,$3,'actor.profile.read_self','actor.profile.read_self',"
            "'permission_registry',$4,"
            "'authorization_evaluation','{\"allowed\": true}'::json)",
            event_id,
            str(uuid4()),
            str(uuid4()),
            permission,
        )
        return event_id
    finally:
        await connection.close()


async def _remove_authority_evidence(database_url: str, event_id: str) -> None:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        async with connection.transaction():
            await connection.execute("lock table audit_events in access exclusive mode")
            await connection.execute(
                "alter table audit_events disable trigger audit_events_reject_update_delete"
            )
            await connection.execute("delete from audit_events where id=$1", event_id)
            await connection.execute(
                "alter table audit_events enable trigger audit_events_reject_update_delete"
            )
    finally:
        await connection.close()


def test_0063_empty_round_trip_preserves_exact_request_registries(
    isolated_database_env: str, migration_lock
) -> None:
    config = _config()
    with migration_lock():
        try:
            command.downgrade(config, "0062_guide_compilation")
            assert asyncio.run(_registry_state(isolated_database_env)) == (
                "0062_guide_compilation",
                0,
                0,
                0,
            )
            command.upgrade(config, "0063_compilation_authority")
            assert asyncio.run(_registry_state(isolated_database_env)) == (
                "0063_compilation_authority",
                1,
                1,
                1,
            )
        finally:
            command.upgrade(config, "head")


@pytest.mark.parametrize(
    "permission",
    ["project.guide_compilation.request", "project.guide_compilation.execute"],
)
def test_0063_compilation_permissions_require_exact_action_evidence(
    isolated_database_env: str, migration_lock, permission: str
) -> None:
    with migration_lock():
        with pytest.raises(asyncpg.CheckViolationError):
            asyncio.run(
                _insert_permission_without_action(isolated_database_env, permission)
            )


def test_0063_refuses_historical_permission_only_execute_evidence(
    isolated_database_env: str, migration_lock
) -> None:
    config = _config()
    event_id = ""
    with migration_lock():
        try:
            command.downgrade(config, "0062_guide_compilation")
            event_id = asyncio.run(
                _insert_permission_without_action(
                    isolated_database_env,
                    "project.guide_compilation.execute",
                )
            )
            with pytest.raises(
                RuntimeError,
                match="permission-only execute evidence",
            ):
                command.upgrade(config, "0063_compilation_authority")
            assert asyncio.run(_registry_state(isolated_database_env))[0] == (
                "0062_guide_compilation"
            )
        finally:
            if event_id:
                asyncio.run(_remove_authority_evidence(isolated_database_env, event_id))
            command.upgrade(config, "head")


@pytest.mark.parametrize(
    "permission",
    ["project.guide_compilation.request", "project.guide_compilation.execute"],
)
def test_0063_downgrade_refuses_compilation_permission_registry_reference(
    isolated_database_env: str, migration_lock, permission: str
) -> None:
    config = _config()
    event_id = ""
    with migration_lock():
        try:
            event_id = asyncio.run(
                _insert_compilation_registry_reference(
                    isolated_database_env,
                    permission,
                )
            )
            with pytest.raises(RuntimeError, match="cannot downgrade retained"):
                command.downgrade(config, "0062_guide_compilation")
        finally:
            if event_id:
                asyncio.run(_remove_authority_evidence(isolated_database_env, event_id))
            command.upgrade(config, "head")


@pytest.mark.parametrize(
    "action", ["project.guide_compilation.request", "project.guide_compilation.execute"]
)
def test_0063_refuses_downgrade_after_retained_compilation_authority(
    isolated_database_env: str, migration_lock, action: str
) -> None:
    config = _config()
    with migration_lock():
        try:
            command.upgrade(config, "head")
            asyncio.run(_insert_authority_evidence(isolated_database_env, action))
            with pytest.raises(RuntimeError, match="cannot downgrade retained"):
                command.downgrade(config, "0062_guide_compilation")
        finally:
            command.upgrade(config, "head")
