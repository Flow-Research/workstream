"""Registry migration remains public-schema pinned under a hostile search path."""

from __future__ import annotations

import asyncio

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from app.db import session as db_session
from app.core.identifiers import new_record_id
from scripts.run_isolated_tests import NAME_RE, ROLE_RE
from tests.conftest import _drop_test_database_schema
from tests.migration_fixtures import current_schema_revision


def _config() -> Config:
    return Config("alembic.ini")


async def _audit_constraint_snapshot(
    url: str,
) -> tuple[str, str]:
    connection = await asyncpg.connect(url)
    try:
        return (
            await connection.fetchval("select version_num from public.alembic_version"),
            await connection.fetchval(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid='public.audit_events'::regclass "
                "and conname='ck_audit_events_authorization_action_evidence'"
            ),
        )
    finally:
        await connection.close()


async def _insert_audit_pair(
    connection: asyncpg.Connection, *, action_id: str, permission_id: str
) -> None:
    """Insert one privacy-bounded authority decision directly into PostgreSQL."""
    event_id = new_record_id()
    await connection.execute(
        """
        insert into public.audit_events (
            id, entity_type, entity_id, event_type, actor_id, actor_roles,
            claim_snapshot, auth_source, is_dev_auth, reason, event_payload,
            event_domain, event_version, actor_ref_kind, request_id,
            correlation_id, matched_grant_id, permission_id, action_id,
            after_facts, occurred_at
        ) values (
            $1, 'authorization_decision', $1, 'SensitiveAuthorizationAllowed',
            $2, '[]'::json, '{}'::json, 'local_authority', false,
            'authorization_evaluation', '{}'::json, 'authority', 1,
            'actor_profile', $3, $4, $5, $6, $7, '{"allowed":true}'::json,
            clock_timestamp()
        )
        """,
        event_id,
        str(new_record_id()),
        new_record_id(),
        new_record_id(),
        str(new_record_id()),
        permission_id,
        action_id,
    )


async def test_registry_upgrade_targets_public_schema_with_shadow_search_path(
    isolated_database_env,
    migration_lock,
) -> None:
    assert len(current_schema_revision()) <= 32
    shadow = "pilot04_registry_shadow"
    url = isolated_database_env.replace("+asyncpg", "")
    with migration_lock():
        await db_session.dispose_engine()
        await _drop_test_database_schema(isolated_database_env)
        await asyncio.to_thread(command.upgrade, _config(), "0028_lifecycle_transitions")
        connection = await asyncpg.connect(url)
        role, database = await connection.fetchrow("select current_user,current_database()")
        assert ROLE_RE.fullmatch(role) and NAME_RE.fullmatch(database)
        try:
            await connection.execute(f"create schema {shadow}")
            await connection.execute(
                f"create table {shadow}.audit_events (like public.audit_events including all)"
            )
            shadow_before = await connection.fetchval(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid=to_regclass($1) "
                "and conname='ck_audit_events_authorization_action_evidence'",
                f"{shadow}.audit_events",
            )
            await connection.execute(
                f'alter role "{role}" in database "{database}" set search_path={shadow},public'
            )
        finally:
            await connection.close()

        try:
            await asyncio.to_thread(command.upgrade, _config(), "head")
            probe = await asyncpg.connect(url)
            try:
                assert (
                    await probe.fetchval("select version_num from public.alembic_version")
                    == current_schema_revision()
                )
                assert await probe.fetchval(
                    "select to_regclass('public.external_checker_registry_entries') is not null"
                )
                assert await probe.fetchval(
                    "select to_regclass($1) is null", f"{shadow}.external_checker_registry_entries"
                )
                public_definition = await probe.fetchval(
                    "select pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid='public.audit_events'::regclass "
                    "and conname='ck_audit_events_authorization_action_evidence'"
                )
                shadow_after = await probe.fetchval(
                    "select pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid=to_regclass($1) "
                    "and conname='ck_audit_events_authorization_action_evidence'",
                    f"{shadow}.audit_events",
                )
                exact_pairs = (
                    ("checker.registry.read", "operations.status.read"),
                    ("operations.checker_retry_source.list", "operations.status.read"),
                )
                assert "checker.registry.register" in public_definition
                assert all(
                    action in public_definition and permission in public_definition
                    for action, permission in exact_pairs
                )
                assert shadow_after == shadow_before
                for action, permission in exact_pairs:
                    await _insert_audit_pair(probe, action_id=action, permission_id=permission)
                    with pytest.raises(asyncpg.CheckViolationError) as error:
                        await _insert_audit_pair(
                            probe,
                            action_id=action,
                            permission_id="operations.reconcile.run",
                        )
                    assert error.value.constraint_name == (
                        "ck_audit_events_authorization_action_evidence"
                    )
            finally:
                await probe.close()
        finally:
            cleanup = await asyncpg.connect(url)
            try:
                await cleanup.execute(
                    f'alter role "{role}" in database "{database}" reset search_path'
                )
                await cleanup.execute(f"drop schema if exists {shadow} cascade")
            finally:
                await cleanup.close()


async def test_operational_read_audit_one_step_downgrade_refuses_without_mutation(
    isolated_database_env,
    migration_lock,
) -> None:
    url = isolated_database_env.replace("+asyncpg", "")
    with migration_lock():
        await db_session.dispose_engine()
        await _drop_test_database_schema(isolated_database_env)
        await asyncio.to_thread(
            command.upgrade,
            _config(),
            "0051_operational_read_audit",
        )
        try:
            before = await _audit_constraint_snapshot(url)
            assert before[0] == "0051_operational_read_audit"

            with pytest.raises(
                RuntimeError,
                match=("Workstream v0.1 migrations cannot be downgraded; recreate the database"),
            ):
                await asyncio.to_thread(
                    command.downgrade,
                    _config(),
                    "0050_contributor_reads",
                )

            assert await _audit_constraint_snapshot(url) == before
        finally:
            await _drop_test_database_schema(isolated_database_env)
            await asyncio.to_thread(
                command.upgrade,
                _config(),
                current_schema_revision(),
            )
