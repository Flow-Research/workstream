"""Exact queue audit pairs and retained evidence under the real forward migration."""

import asyncio
from app.core.identifiers import new_record_id

import asyncpg
from alembic import command
import pytest

from tests.migration_fixtures import _config as config

pytestmark = pytest.mark.postgres_schema_contract
CONSTRAINT = "ck_audit_events_authorization_action_evidence"
PAIRS = (
    ("task.queue.read", "task.queue.read"),
    ("project.task.queue.read", "project.task.manage"),
    ("operations.task.queue.read", "operations.status.read"),
)


async def insert(connection, action, permission, *, allowed=True):
    identity, project = str(new_record_id()), str(new_record_id())
    await connection.execute(
        """insert into audit_events(
        id,entity_type,entity_id,event_type,actor_id,actor_roles,claim_snapshot,
        auth_source,is_dev_auth,event_payload,event_domain,event_version,actor_ref_kind,
        request_id,correlation_id,permission_id,action_id,reason,project_id,resource_type,
        resource_id,after_facts,matched_grant_id,target_ref_kind,target_ref_id,denial_code)
        values($1,'authorization_decision',$1,$2,$3,'[]','{}','local_authority',false,'{}',
        'authority',1,'actor_profile',$4,$5,$6,$7,'authorization_evaluation',$8::uuid,'project',($8::uuid)::text,
        json_build_object('allowed',$9::boolean,'resource_context_digest','sha256:'||repeat('a',64)),
        $10,'project',($8::uuid)::text,$11)""",
        identity, "SensitiveAuthorizationAllowed" if allowed else "SensitiveAuthorizationDenied",
        str(new_record_id()), str(new_record_id()), str(new_record_id()), permission, action, project, allowed,
        str(new_record_id()) if allowed else None, None if allowed else "permission_not_granted",
    )
    return await connection.fetchval("select to_jsonb(a)::text from audit_events a where id=$1", identity)


def test_upgrade_preserves_authorization_evidence(isolated_database_env, migration_lock):
    with migration_lock():
        async def reset():
            connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
            try:
                await connection.execute("drop schema public cascade; create schema public")
            finally:
                await connection.close()
        asyncio.run(reset())
        command.upgrade(config(), "0001_uuid7_v01")
        async def seed():
            connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
            try:
                return await insert(connection, "project.read", "project.read")
            finally:
                await connection.close()
        before = asyncio.run(seed())
        command.upgrade(config(), "0002_task_queue_authority")
        async def read():
            connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
            try:
                return await connection.fetchval("select to_jsonb(a)::text from audit_events a")
            finally:
                await connection.close()
        assert asyncio.run(read()) == before
        command.upgrade(config(), "head")
        assert asyncio.run(read()) == before


@pytest.mark.parametrize("remove_guard", [False, True])
def test_queue_audit_permission_pairs_are_closed(isolated_database_env, migration_lock, remove_guard):
    with migration_lock():
        async def probe():
            connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
            try:
                if remove_guard:
                    await connection.execute(f"alter table audit_events drop constraint {CONSTRAINT}")
                for action, permission in PAIRS:
                    for allowed in (False, True):
                        assert await insert(connection, action, permission, allowed=allowed)
                        with pytest.raises(asyncpg.CheckViolationError) as failure:
                            await insert(connection, action, "project.read", allowed=allowed)
                        assert failure.value.constraint_name == CONSTRAINT
            finally:
                await connection.close()
        if remove_guard:
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                asyncio.run(probe())
        else:
            asyncio.run(probe())


async def test_contributor_read_audit_permission_pairs_are_closed(isolated_database_env):
    """The head allows both exact pairs and rejects a substituted permission."""
    connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
    try:
        for action in ("task.assignment.read", "project.contributor_guide.read"):
            for allowed in (False, True):
                assert await insert(connection, action, "submission.read_own", allowed=allowed)
                with pytest.raises(asyncpg.CheckViolationError) as failure:
                    await insert(connection, action, "project.read", allowed=allowed)
                assert failure.value.constraint_name == CONSTRAINT
    finally:
        await connection.close()
