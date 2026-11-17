"""Exact original 0047 data and SQL validation for migration tests only.

Captured by the unmodified original owner at 1a4cd1e27a401308960d4d8e9fabe40282a9a79f
using its frozen dependencies. Synthetic evaluator/local-provider fixtures supply
stored data, not public checker or provider-object qualification. No historical
application writer or current-reader projection belongs in this module.
"""

from copy import deepcopy
from datetime import datetime, timedelta
import gzip
import hashlib
import json
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from sqlalchemy import text

from tests import conftest as suite_fixtures
from tests.historical_submission_fixtures import _restore_validated_snapshot_rows

_REVISION = "0047_revision_recovery"
_SOURCE = "1a4cd1e27a401308960d4d8e9fabe40282a9a79f"
_SCHEMA = "e4572d8ea010965ee2a943ed0cdf7f7946a4c7fcf97a14478e8a0a603ed13ae1"
_ARCHIVE = Path(__file__).with_name("fixtures") / "historical_revision_window_0047.json.gz"
_ARCHIVE_SHA256 = "65de7efe3e8e8ad4b14f289b51d2e4e3c7e10cee326cb7487f746c5d5a4e4768"


def captured_revision_window():
    """Load one pinned original capture, including its empty-table inventory."""
    encoded = _ARCHIVE.read_bytes()
    assert len(encoded) == 48987
    assert hashlib.sha256(encoded).hexdigest() == _ARCHIVE_SHA256
    raw = gzip.decompress(encoded)
    assert len(raw) == 344548
    capture = json.loads(raw)
    assert capture["schema_version"] == "workstream.historical_revision_window.v1"
    assert capture["source_revision"] == _SOURCE
    assert capture["source_schema_sha256"] == _SCHEMA
    assert capture["source_operation"] == "tests.test_submission_predecessor_custody._fixture_revision_context"
    assert capture["provider"] == "local" and capture["provider_objects_captured"] is False
    assert capture["snapshot"]["revision"] == _REVISION
    assert capture["snapshot"]["tables"]["alembic_version"] == [{"version_num": _REVISION}]
    assert len(capture["table_inventory"]) == len(set(capture["table_inventory"])) == 117
    assert set(capture["column_inventory"]) == set(capture["table_inventory"])
    assert len(capture["snapshot"]["tables"]) == 71
    assert set(capture["raw_row_sha256"]) == set(capture["snapshot"]["tables"])
    return capture


async def restore_revision_window(database_url, capture):
    """Restore literal 0047 rows, then independently validate their semantics."""
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        assert set(suite_fixtures.PROTECTED_TEST_TABLES).issubset(capture["table_inventory"])
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(suite_fixtures, "RESETTABLE_TEST_TABLES", tuple(
                name for name in capture["table_inventory"]
                if name not in suite_fixtures.PROTECTED_TEST_TABLES
            ))
            patch.setattr(suite_fixtures, "EXPECTED_PUBLIC_SCHEMA_SHA256", _SCHEMA)
            await suite_fixtures._assert_canonical_test_schema(connection)
        for table, expected in capture["column_inventory"].items():
            actual = await connection.fetchval("""SELECT array_agg(column_name ORDER BY ordinal_position)
                FROM information_schema.columns WHERE table_schema='public' AND table_name=$1""", table)
            assert list(actual) == expected, table
    finally:
        await connection.close()
    seed = await _restore_validated_snapshot_rows(
        database_url, capture["snapshot"], expected_revision=_REVISION,
    )
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        for table, expected in capture["raw_row_sha256"].items():
            assert table.replace("_", "").isalnum()
            rows = await connection.fetch(
                f'SELECT to_jsonb(r)::text AS body FROM public."{table}" r ORDER BY to_jsonb(r)::text'
            )
            actual = hashlib.sha256(_canonical_bytes([row["body"] for row in rows])).hexdigest()
            assert actual == expected, table
        await validate_revision_window(connection, seed, capture_time=_instant(capture["capture_time"]))
    finally:
        await connection.close()
    return deepcopy(seed)


def _canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _row(connection, table, record_id):
    assert table in {"task_revision_preparations", "task_post_submit_routing_manifests", "workstream_tasks", "task_assignments", "submissions", "revision_policies", "audit_events"}
    value = await connection.fetchval(f"SELECT to_jsonb(r)::text FROM public.{table} r WHERE id=$1::uuid", UUID(str(record_id)))
    assert value is not None, f"missing {table}"
    return json.loads(value)


async def validate_revision_window(connection, identities, *, capture_time):
    """Validate stored facts independently after both writer commit and backup restore."""
    assert await connection.fetchval("SELECT version_num FROM public.alembic_version") == "0047_revision_recovery"
    assert await connection.fetchval("SHOW session_replication_role") == "origin"
    assert await connection.fetchval("""SELECT count(*) FROM pg_trigger t
        JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND NOT t.tgisinternal AND t.tgenabled NOT IN ('O','A')""") == 0
    assert await connection.fetchval("SELECT count(*) FROM public.task_revision_preparations") == 1
    p = await _row(connection, "task_revision_preparations", identities["preparation_id"])
    m = await _row(connection, "task_post_submit_routing_manifests", identities["routing_manifest_id"])
    t = await _row(connection, "workstream_tasks", identities["task_id"])
    a = await _row(connection, "task_assignments", identities["assignment_id"])
    s = await _row(connection, "submissions", identities["submission_id"])
    policy = await _row(connection, "revision_policies", s["locked_revision_policy_id"])
    assert p["predecessor_id"] is None and p["sequence"] == 1
    assert p["outcome"] == "kept" and p["blocked_reason"] is None
    assert p["repair_actor_id"] is None
    assert p["routing_manifest_id"] == m["id"]
    assert t["status"] == m["routing_recommendation"] == "needs_revision"
    assert a["status"] == "active" and a["released_at"] is None
    for name in ("project_id", "task_id", "assignment_id", "submission_id", "contributor_id"):
        assert p[name] == m[name] == identities[name], name
    assert t["id"] == a["task_id"] == s["task_id"] == p["task_id"]
    assert t["project_id"] == a["project_id"] == p["project_id"]
    assert t["assigned_to"] == a["contributor_id"] == s["contributor_id"] == p["contributor_id"]
    assert s["task_assignment_id"] == a["id"] == p["assignment_id"]
    assert p["source_submission_version"] == m["submission_version"] == s["version"]
    assert s["contribution_policy_version_id"] == a["submitter_contribution_policy_version_id"] == t["locked_contribution_policy_version_id"]
    assert p["next_revision_round"] == await connection.fetchval("""SELECT count(*) FROM public.submissions
        WHERE task_assignment_id=$1::uuid AND version<=$2""", UUID(a["id"]), s["version"])
    assert 0 < p["next_revision_round"] <= p["max_revision_rounds"] == policy["max_revision_rounds"]
    assert _instant(p["requested_at"]) == _instant(m["created_at"])
    assert _instant(p["deadline_at"]) == _instant(p["requested_at"]) + timedelta(hours=policy["revision_deadline_hours"])
    assert _instant(p["requested_at"]) <= _instant(p["created_at"]) <= capture_time < _instant(p["deadline_at"])
    packet = p["packet"]
    assert p["preparation_sha256"] == "sha256:" + hashlib.sha256(_canonical_bytes(packet)).hexdigest(), "preparation digest mismatch"
    for name in ("id", "routing_manifest_id", "predecessor_id", "sequence", "source_submission_version", "next_revision_round", "max_revision_rounds", "outcome", "blocked_reason"):
        assert packet[name] == p[name], name
    assert _instant(packet["requested_at"]) == _instant(p["requested_at"])
    assert _instant(packet["deadline_at"]) == _instant(p["deadline_at"])
    lineage = await connection.fetchval("SELECT public.revision_task_lineage(to_jsonb(t))::text FROM public.workstream_tasks t WHERE id=$1::uuid", UUID(t["id"]))
    assert packet["previous_task_lineage"] == packet["candidate"]["prior"]["lineage"] == packet["candidate"]["target"]["lineage"] == json.loads(lineage)
    assert packet["candidate"]["prior"] == packet["candidate"]["target"]
    checks = await connection.fetchrow("""SELECT public.task_routing_receipt_valid(m) AS receipt,
        public.task_routing_context_valid(m) AS context, public.task_routing_outcome_complete(m) AS complete,
        public.task_routing_resource_digest(m) AS digest
        FROM public.task_post_submit_routing_manifests m WHERE id=$1::uuid""", UUID(m["id"]))
    assert checks is not None and all(checks[name] is True for name in ("receipt", "context", "complete"))
    assert p["authorization_decision_id"] == m["authorization_decision_id"]
    assert p["audit_event_id"] == m["audit_event_id"]
    auth = await _row(connection, "audit_events", p["authorization_decision_id"])
    audit = await _row(connection, "audit_events", p["audit_event_id"])
    assert auth["event_domain"] == "authority" and auth["event_type"] == "SensitiveAuthorizationAllowed"
    assert auth["action_id"] == auth["permission_id"] == "task.post_submit.route"
    assert auth["denial_code"] is None and auth["matched_grant_id"] is None
    assert auth["project_id"] == p["project_id"] and auth["actor_id"] == m["router_actor_id"]
    assert auth["resource_type"] == "task_post_submit_routing_manifest" and auth["resource_id"] == m["id"]
    assert auth["after_facts"] == {"allowed": True, "resource_context_digest": checks["digest"]}
    assert auth["request_id"] == auth["correlation_id"] == m["authority_context"]["request"]["route_operation_id"]
    assert audit["event_domain"] == "legacy_lifecycle" and audit["entity_type"] == "task" and audit["entity_id"] == p["task_id"]
    events = await connection.fetch("""SELECT to_jsonb(e)::text AS body FROM public.outbox_events e
        WHERE idempotency_key=$1""", "task.revision.expire:" + m["id"])
    assert len(events) == 1
    event = json.loads(events[0]["body"])
    assert event["event_type"] == "TaskRevisionExpiryRequested" and event["event_version"] == 1
    assert event["aggregate_type"] == "task" and event["aggregate_id"] == p["task_id"]
    assert event["project_id"] == p["project_id"] and event["correlation_id"] == m["id"]
    assert event["causation_event_id"] == m["outcome_event_id"]
    assert _instant(event["not_before_at"]) == _instant(p["deadline_at"])
    payload = event["payload"]
    assert set(payload) == {"project_id", "task_id", "assignment_id", "contributor_id", "source_submission_id", "routing_manifest_id", "root_preparation_id", "root_preparation_sha256", "deadline_at"}
    for name in ("project_id", "task_id", "assignment_id", "contributor_id", "routing_manifest_id"):
        assert payload[name] == p[name]
    assert payload["source_submission_id"] == p["submission_id"]
    assert payload["root_preparation_id"] == p["id"] and payload["root_preparation_sha256"] == p["preparation_sha256"]
    assert _instant(payload["deadline_at"]) == _instant(p["deadline_at"])
    return {"preparation_id": p["id"], "routing_manifest_id": m["id"], "expiry_event_id": event["event_id"], "deadline_at": p["deadline_at"]}


async def retained_revision_rows(session, manifest_id):
    """Compare retained bytes plus table and physical row identities across ADD COLUMN."""
    selectors = {
        "revision_policies": "id=(SELECT s.locked_revision_policy_id FROM public.submissions s "
        "JOIN public.task_post_submit_routing_manifests m ON m.submission_id=s.id WHERE m.id=:id)",
        "workstream_tasks": "id=(SELECT task_id FROM public.task_post_submit_routing_manifests WHERE id=:id)",
        "task_assignments": "id=(SELECT assignment_id FROM public.task_post_submit_routing_manifests WHERE id=:id)",
        "submissions": "id=(SELECT submission_id FROM public.task_post_submit_routing_manifests WHERE id=:id)",
        "task_revision_preparations": "routing_manifest_id=:id",
        "task_post_submit_routing_manifests": "id=:id",
        "audit_events": "id IN (SELECT authorization_decision_id FROM public.task_revision_preparations "
        "WHERE routing_manifest_id=:id UNION SELECT audit_event_id FROM public.task_revision_preparations "
        "WHERE routing_manifest_id=:id)",
        "outbox_events": "idempotency_key='task.revision.expire:'||CAST(CAST(:id AS uuid) AS text)",
    }
    result = {}
    for table, where in selectors.items():
        excluded = ("remaining_microseconds", "clock_observed_at") if table == "task_revision_preparations" else ()
        values = await session.execute(text(
            f"SELECT (to_jsonb(row)-CAST(:excluded AS text[]))::text,tableoid::bigint,"
            f"xmin::text FROM public.{table} row WHERE {where} ORDER BY 1"
        ), {"id": manifest_id, "excluded": list(excluded)})
        result[table] = [tuple(row) for row in values]
        assert len(result[table]) == (2 if table == "audit_events" else 1), table
    return result


async def assert_historical_revision_guards(factory, revision: str) -> None:
    """Confirm the exact migration revision and enabled native guards."""
    async with factory() as session:
        assert await session.scalar(text("SELECT version_num FROM alembic_version")) == revision
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' "
                    "AND NOT t.tgisinternal AND t.tgenabled='D'"
                )
            )
            == 0
        )
