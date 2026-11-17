"""Additive custody never manufactures dispatch or authority for retained data."""

import asyncio
import json
from datetime import datetime

import asyncpg
import pytest
from alembic import command

from app.db import session as db_session
from tests.historical_submission_fixtures import historical_material_fixture
from tests.migration_fixtures import _config, current_schema_revision

pytestmark = pytest.mark.postgres_schema_contract


async def test_upgrade_preserves_retained_owners_without_backfill(tmp_path, isolated_database_env, migration_lock):
    url = isolated_database_env.replace("+asyncpg", "")
    with migration_lock():
        await db_session.dispose_engine()
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0024_require_second_review_false")
        async with historical_material_fixture(tmp_path, isolated_database_env) as h:
            connection = await asyncpg.connect(url)
            tables = ("submissions", "submission_bundle_admissions", "artifact_bindings", "audit_events",
                      "checker_runs", "outbox_events", "workstream_tasks", "task_assignments")
            async def snapshot():
                return {table: await connection.fetchval(
                    f"SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY to_jsonb(r)::text),'[]') FROM public.{table} r"
                ) for table in tables}
            try:
                before = await snapshot()
                await asyncio.to_thread(command.upgrade, _config(), current_schema_revision())
                after = await snapshot()
                added_columns = {
                    "workstream_tasks": {"active_submission_operation_id"},
                    "outbox_events": {"not_before_at"},
                    "submissions": {
                        "selected_post_submit_policy_sha256", "selected_post_submit_policy_body",
                        "attempt_status", "status_reason", "decided_at", "updated_at",
                    },
                    "task_assignments": {"started_at", "updated_at"},
                    "checker_runs": {
                        "selected_post_submit_policy_sha256", "selected_post_submit_policy_body",
                    },
                    "submission_bundle_admissions": {
                        "checker_remediation_manifest_id", "selected_pre_submit_run_id",
                        "guide_id", "guide_version", "source_snapshot_id", "source_snapshot_sha256",
                        "effective_policy_id", "effective_policy_sha256", "pre_submit_policy_id",
                        "pre_submit_policy_sha256", "effective_plan_sha256", "selected_rules_sha256",
                        "selected_post_submit_policy_sha256", "selected_post_submit_policy_body",
                        "packet_sha256", "semantic_manifest_body",
                        "revision_preparation_id", "revision_preparation_sha256",
                    },
                }
                for table, columns_added in added_columns.items():
                    identity = "event_id" if table == "outbox_events" else "id"
                    retained_rows = sorted(json.loads(before.pop(table)), key=lambda row: row[identity])
                    upgraded_rows = sorted(json.loads(after.pop(table)), key=lambda row: row[identity])
                    assert len(upgraded_rows) == len(retained_rows)
                    for retained, upgraded in zip(retained_rows, upgraded_rows, strict=True):
                        assert set(upgraded) == set(retained) | columns_added
                        # 0048 backfills from retained owner evidence only: an unrouted
                        # attempt stays pending and its stamps come from its own facts.
                        backfilled = {
                            "attempt_status": "evaluation_pending",
                            "updated_at": retained.get("submitted_at"),
                        } if table == "submissions" else {}
                        if table == "task_assignments":
                            started = upgraded.pop("started_at")
                            stamps = [retained["assigned_at"], started, retained["released_at"]]
                            assert started is None or datetime.fromisoformat(
                                started
                            ) >= datetime.fromisoformat(retained["assigned_at"])
                            assert upgraded.pop("updated_at") == max(
                                (stamp for stamp in stamps if stamp is not None),
                                key=datetime.fromisoformat,
                            )
                        for column in columns_added - {"started_at", "updated_at"} if (
                            table == "task_assignments"
                        ) else columns_added:
                            assert upgraded.pop(column) == backfilled.get(column), column
                        assert upgraded == retained
                assert after == before
                columns = await connection.fetch("""
                    SELECT table_name,data_type,is_nullable
                    FROM information_schema.columns
                    WHERE table_schema='public'
                      AND table_name=ANY($1::text[])
                      AND column_name='checker_remediation_manifest_id'
                    ORDER BY table_name
                """, [
                    "pre_submit_evidence_sets",
                    "submission_bundle_admissions",
                    "submission_dispatches",
                ])
                assert [tuple(row) for row in columns] == [
                    ("pre_submit_evidence_sets", "uuid", "YES"),
                    ("submission_bundle_admissions", "uuid", "YES"),
                    ("submission_dispatches", "uuid", "YES"),
                ]
                for table in (
                    "pre_submit_evidence_sets",
                    "submission_bundle_admissions",
                    "submission_dispatches",
                ):
                    assert await connection.fetchval(
                        f"SELECT count(*) FROM public.{table} "
                        "WHERE checker_remediation_manifest_id IS NOT NULL"
                    ) == 0
                assert await connection.fetchval("SELECT count(*) FROM public.submission_dispatches") == 0
                assert await connection.fetchval("SELECT count(*) FROM public.submission_binding_receipts") == 0
                assert await connection.fetchval("SELECT status FROM public.submission_bundle_admissions WHERE id=$1", h.created["admission_id"]) == "consumed"
            finally:
                await connection.close()
