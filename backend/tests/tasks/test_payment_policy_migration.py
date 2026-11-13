"""Real predecessor migration preserves retained facts instead of dropping them."""

import asyncio
import json
from pathlib import Path
import runpy

import pytest
from alembic import command
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.identifiers import new_record_id
from app.db import session as db_session
from tests.conftest import _drop_test_database_schema
from tests.migration_fixtures import _config, current_schema_revision
from tests.historical_submission_fixtures import historical_material_fixture

pytestmark = pytest.mark.postgres_schema_contract
TABLES = ("payment_policies", "workstream_tasks", "submissions", "task_command_receipts",
          "task_assignments", "contribution_policies", "contribution_policy_versions",
          "contribution_rules", "contribution_award_definitions")
FIELDS = ("base_amount", "currency", "payout_type", "locked_payment_policy_version")


def _upgrade(connection):
    migration = runpy.run_path(str(Path(__file__).resolve().parents[2] /
                                   "alembic/versions/0023_remove_task_payment_policy.py"))
    with Operations.context(MigrationContext.configure(connection)):
        migration["upgrade"]()


async def _snapshot(connection):
    rows = {}
    for table in TABLES:
        rows[table] = list(await connection.scalars(text(
            f"SELECT to_jsonb(t) FROM public.{table} AS t ORDER BY to_jsonb(t)::text")))
    columns = (await connection.execute(text(
        "SELECT table_name,column_name,data_type FROM information_schema.columns "
        "WHERE table_schema='public' ORDER BY table_name,ordinal_position"))).all()
    constraints = (await connection.execute(text(
        "SELECT conrelid::regclass::text,conname,pg_get_constraintdef(oid) "
        "FROM pg_constraint WHERE connamespace='public'::regnamespace ORDER BY 1,2"))).all()
    return rows, columns, constraints, await connection.scalar(text("SELECT version_num FROM public.alembic_version"))


async def _seed_old_policy(connection, task):
    await connection.execute(text(
        "INSERT INTO public.payment_policies(id,project_id,guide_version,base_amount,currency,payout_type) "
        "VALUES(:id,:project,:guide,25,'USD','fixed')"),
        {"id": new_record_id(), "project": task["project_id"], "guide": task["locked_guide_version"]})


async def test_payment_cleanup_refuses_each_retained_fact_then_preserves_current_lineage(
    tmp_path, isolated_database_env, migration_lock,
):
    await db_session.dispose_engine()
    with migration_lock():
        await _drop_test_database_schema(isolated_database_env)
        await asyncio.to_thread(command.upgrade, _config(), "0022_submission_packet_custody")
        async with historical_material_fixture(tmp_path, isolated_database_env) as h:
            async with db_session.get_engine().connect() as connection:
                task = await connection.scalar(text("SELECT to_jsonb(t) FROM public.workstream_tasks t WHERE id=:id"),
                                               {"id": h.request["task_id"]})
                await connection.rollback()
                cases = [
                    ("submission_stamp", "retained Submission payment stamp"),
                    ("locked_payment_policy_version", "retained TASK payment stamp"),
                    ("base_amount", "retained TASK base amount"),
                    ("currency", "retained TASK currency"),
                    ("payout_type", "retained TASK payout type"),
                    ("policy", "retained PaymentPolicy rows"),
                    *[(f"receipt:{nested}:{field}", "retained TASK payment response")
                      for nested in (False, True) for field in FIELDS],
                ]
                for case, message in cases:
                    async with connection.begin():
                        if case in {"submission_stamp", "locked_payment_policy_version", "policy"}:
                            await _seed_old_policy(connection, task)
                        if case in {"submission_stamp", "locked_payment_policy_version"}:
                            await connection.execute(text("UPDATE public.workstream_tasks "
                                "SET locked_payment_policy_version=locked_guide_version WHERE id=:id"),
                                {"id": h.request["task_id"]})
                        if case == "submission_stamp":
                            await connection.execute(text("UPDATE public.submissions "
                                "SET locked_payment_policy_version=locked_guide_version WHERE id=:id"),
                                {"id": h.request["submission_id"]})
                        if case in {"base_amount", "currency", "payout_type"}:
                            value = {"base_amount": 0, "currency": "USD", "payout_type": "fixed"}[case]
                            await connection.execute(text(f"UPDATE public.workstream_tasks SET {case}=:value WHERE id=:id"),
                                                     {"value": value, "id": h.request["task_id"]})
                        if case.startswith("receipt:"):
                            _, nested, field = case.split(":")
                            payload = {field: None} if nested == "False" else {"task": {field: None}}
                            await connection.execute(text("""INSERT INTO public.task_command_receipts
                                (id,actor_profile_id,action_id,idempotency_key,request_digest,task_id,status,
                                 assignment_id,contributor_id,locked_context_hash,response,committed_at)
                                VALUES(:id,:actor,:action,:key,:digest,:task,'committed',
                                       :assignment,:contributor,:digest,CAST(:response AS jsonb),CURRENT_TIMESTAMP)"""),
                                {"id": new_record_id(), "actor": task["assigned_to"], "key": new_record_id(),
                                 "digest": "sha256:" + "a" * 64, "task": h.request["task_id"],
                                 "action": "task.claim" if nested == "True" else "project.task.create",
                                 "assignment": h.request["assignment_id"] if nested == "True" else None,
                                 "contributor": task["assigned_to"] if nested == "True" else None,
                                 "response": json.dumps(payload)})
                        # All pre-existing FKs must pass before the intended refusal.
                        await connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                        before = await _snapshot(connection)
                        with pytest.raises(IntegrityError, match=message):
                            async with connection.begin_nested():
                                await connection.run_sync(_upgrade)
                        assert await _snapshot(connection) == before, case
                        await connection.rollback()
                async with connection.begin():
                    before = await _snapshot(connection)
            # Full Alembic upgrade: current records exist, but obsolete facts do not.
            await asyncio.to_thread(command.upgrade, _config(), "head")
            async with db_session.get_engine().connect() as connection:
                assert await connection.scalar(text("SELECT to_regclass('public.payment_policies')")) is None
                for table, fields in (("workstream_tasks", FIELDS), ("submissions", (FIELDS[-1],))):
                    actual = set(await connection.scalars(text("SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name=:table"), {"table": table}))
                    assert actual.isdisjoint(fields)
                for table in TABLES[1:]:
                    actual = list(await connection.scalars(text(
                        f"SELECT to_jsonb(t) FROM public.{table} t ORDER BY to_jsonb(t)::text")))
                    removed = FIELDS if table == "workstream_tasks" else (FIELDS[-1],) if table == "submissions" else ()
                    expected = [{k: v for k, v in row.items() if k not in removed} for row in before[0][table]]
                    # Later migrations add columns; 0048 backfills unrouted attempts
                    # and unstarted assignments from their own retained timestamps.
                    added = {
                        "workstream_tasks": {"active_submission_operation_id": None},
                        "submissions": {
                            "selected_post_submit_policy_sha256": None,
                            "selected_post_submit_policy_body": None,
                            "attempt_status": "evaluation_pending", "status_reason": None,
                            "decided_at": None, "updated_at": "submitted_at",
                        },
                        "task_command_receipts": {"batch_transition_receipt_id": None},
                        "task_assignments": {"started_at": None, "updated_at": "assigned_at"},
                    }.get(table, {})
                    if added:
                        actual.sort(key=lambda row: row["id"])
                        expected.sort(key=lambda row: row["id"])
                        assert len(actual) == len(expected)
                        for upgraded, retained in zip(actual, expected, strict=True):
                            assert set(upgraded) == set(retained) | set(added)
                            for column, source in added.items():
                                value = retained[source] if column == "updated_at" else source
                                assert upgraded.pop(column) == value, (table, column)
                    assert actual == expected, table
                assert (
                    await connection.scalar(text("SELECT version_num FROM public.alembic_version"))
                    == current_schema_revision()
                )
