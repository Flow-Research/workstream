"""Current-schema proof for AUTH guide-compilation authority."""

import asyncio
from uuid import uuid4

import asyncpg
import pytest

pytestmark = pytest.mark.postgres_schema_contract


async def _registry_state(database_url: str) -> tuple[str, int, int, int]:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        return (
            await connection.fetchval("select version_num from alembic_version"),
            await connection.fetchval(
                "select count(*) from pg_constraint where conrelid='audit_events'::regclass "
                "and conname='ck_audit_events_authority_registries' and "
                "pg_get_constraintdef(oid) like '%project.guide_compilation.request%'"
            ),
            await connection.fetchval(
                "select count(*) from pg_constraint where conrelid='audit_events'::regclass "
                "and conname='ck_audit_events_authorization_action_evidence' and "
                "pg_get_constraintdef(oid) like '%project.guide_compilation.request%'"
            ),
            await connection.fetchval(
                "select count(*) from pg_constraint where conrelid='audit_events'::regclass "
                "and conname='ck_audit_events_authority_privacy_bounds' and "
                "pg_get_constraintdef(oid) like '%project_guide_compilation_request%'"
            ),
        )
    finally:
        await connection.close()


async def _insert_permission_without_action(database_url: str, permission: str) -> None:
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
    finally:
        await connection.close()


def test_current_schema_preserves_exact_compilation_registries(
    isolated_database_env: str,
) -> None:
    assert asyncio.run(_registry_state(isolated_database_env)) == (
        "0008_guide_compilation_authorized_persistence",
        1,
        1,
        1,
    )


@pytest.mark.parametrize(
    "permission",
    ["project.guide_compilation.request", "project.guide_compilation.execute"],
)
def test_compilation_permissions_require_exact_action_evidence(
    isolated_database_env: str,
    permission: str,
) -> None:
    with pytest.raises(asyncpg.CheckViolationError):
        asyncio.run(_insert_permission_without_action(isolated_database_env, permission))
