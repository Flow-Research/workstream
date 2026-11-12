"""Checksum-bound predecessor rows for migration tests only.

The archive projects one-time predecessor captures to their declared schemas.
Snapshots from 0010 through 0024 also include the exact project-neutral POST
service actor and link captured by the same writer in the 0034 source snapshot;
the archive provenance names those two supplemental row IDs. It contains data,
not an executable checker implementation. Restore is confined to an isolated
predecessor database and finishes with every trigger and foreign key setting
restored before a migration test receives the fixture.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import asyncpg

from app.core.hashing import canonical_json_hash
from app.db import session as db_session
from conftest import _assert_owned_test_database


_ARCHIVE = Path(__file__).with_name("fixtures") / "pilot04_predecessor_rows.json.gz"
_ARCHIVE_SHA256 = "e24ab79e764452f92d41bf93ecb00c6a9e08fae427145c51a3e55160108ed054"
_SCHEMA_VERSION = "workstream.pilot04_predecessor_rows.v1"


def _asyncpg_url(database_url: str) -> str:
    return "postgresql" + database_url.removeprefix("postgresql+asyncpg")


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


@lru_cache(maxsize=1)
def _snapshots() -> dict[str, dict[str, object]]:
    encoded = _ARCHIVE.read_bytes()
    assert hashlib.sha256(encoded).hexdigest() == _ARCHIVE_SHA256, (
        "PILOT-04 predecessor row archive checksum mismatch"
    )
    body = json.loads(gzip.decompress(encoded))
    assert body["schema_version"] == _SCHEMA_VERSION
    return body["snapshots"]


async def _trigger_state(connection: asyncpg.Connection) -> tuple[tuple[object, ...], ...]:
    rows = await connection.fetch("""
        SELECT n.nspname, c.relname, t.tgname, t.tgenabled
        FROM pg_trigger t
        JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public'
        ORDER BY c.relname,t.tgname
    """)
    return tuple(tuple(row) for row in rows)


async def _assert_database_guards_enabled(connection: asyncpg.Connection) -> None:
    assert await connection.fetchval("SHOW session_replication_role") == "origin"
    assert await connection.fetchval("""
        SELECT count(*) FROM pg_trigger t
        JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND NOT t.tgisinternal
          AND t.tgenabled NOT IN ('O','A')
    """) == 0


async def _foreign_keys(connection: asyncpg.Connection) -> tuple[asyncpg.Record, ...]:
    return tuple(await connection.fetch("""
        SELECT con.oid, con.conname, child.relname AS child_table,
          parent.relname AS parent_table, con.condeferrable, con.condeferred,
          con.confmatchtype,
          array_agg(child_col.attname ORDER BY keys.ordinality) AS child_columns,
          array_agg(parent_col.attname ORDER BY keys.ordinality) AS parent_columns
        FROM pg_constraint con
        JOIN pg_class child ON child.oid=con.conrelid
        JOIN pg_class parent ON parent.oid=con.confrelid
        JOIN pg_namespace n ON n.oid=con.connamespace
        CROSS JOIN LATERAL unnest(con.conkey,con.confkey)
          WITH ORDINALITY AS keys(child_num,parent_num,ordinality)
        JOIN pg_attribute child_col
          ON child_col.attrelid=con.conrelid AND child_col.attnum=keys.child_num
        JOIN pg_attribute parent_col
          ON parent_col.attrelid=con.confrelid AND parent_col.attnum=keys.parent_num
        WHERE n.nspname='public' AND con.contype='f'
        GROUP BY con.oid,con.conname,child.relname,parent.relname,
          con.condeferrable,con.condeferred,con.confmatchtype
        ORDER BY child.relname,con.conname
    """))


async def _validate_foreign_keys(
    connection: asyncpg.Connection, foreign_keys: tuple[asyncpg.Record, ...]
) -> None:
    """Independently reject every orphan or partial MATCH FULL archived row."""
    for constraint in foreign_keys:
        child = _identifier(constraint["child_table"])
        parent = _identifier(constraint["parent_table"])
        child_columns = tuple(constraint["child_columns"])
        parent_columns = tuple(constraint["parent_columns"])
        all_present = " AND ".join(
            f"c.{_identifier(column)} IS NOT NULL" for column in child_columns
        )
        any_present = " OR ".join(
            f"c.{_identifier(column)} IS NOT NULL" for column in child_columns
        )
        any_missing = " OR ".join(
            f"c.{_identifier(column)} IS NULL" for column in child_columns
        )
        equal = " AND ".join(
            f"p.{_identifier(parent_column)} IS NOT DISTINCT FROM "
            f"c.{_identifier(child_column)}"
            for child_column, parent_column in zip(
                child_columns, parent_columns, strict=True
            )
        )
        invalid_full = (
            f" OR (({any_present}) AND ({any_missing}))"
            if constraint["confmatchtype"] == "f"
            else ""
        )
        count = await connection.fetchval(
            f"""SELECT count(*) FROM public.{child} c
                WHERE (({all_present}) AND NOT EXISTS (
                  SELECT 1 FROM public.{parent} p WHERE {equal}
                )){invalid_full}"""
        )
        assert count == 0, f"archived rows violate {constraint['conname']}"


async def _validate_material_custody(
    connection: asyncpg.Connection, seed: dict[str, object]
) -> None:
    """Bind the archived request to the exact Submission and native ART rows."""
    request = seed["request"]
    created = seed["created"]
    request_body = {key: value for key, value in request.items() if key != "request_sha256"}
    assert canonical_json_hash(request_body) == request["request_sha256"]
    row = await connection.fetchrow("""
        SELECT s.id::text AS submission_id,s.version,s.task_id::text,s.task_assignment_id::text,
          s.submission_bundle_admission_id::text AS admission_id,
          s.artifact_binding_id::text AS binding_id,s.artifact_content_id::text AS content_id,
          a.status,a.consumed_by_submission_id::text AS consumed_submission_id,
          a.consumed_by_submission_version,b.resource_type,b.resource_id::text,
          b.content_id::text AS binding_content_id,c.sha256,
          r.content_id::text AS replica_content_id,t.status AS task_status
        FROM public.submissions s
        JOIN public.submission_bundle_admissions a ON a.id=s.submission_bundle_admission_id
        JOIN public.artifact_bindings b ON b.id=s.artifact_binding_id
        JOIN public.artifact_contents c ON c.id=s.artifact_content_id
        JOIN public.artifact_replicas r ON r.id=$2::uuid
        JOIN public.workstream_tasks t ON t.id=s.task_id
        WHERE s.id=$1::uuid
    """, created["submission_id"], seed["replica_id"])
    assert row is not None
    assert row["submission_id"] == request["submission_id"] == created["submission_id"]
    assert row["version"] == request["submission_version"] == created["submission_version"]
    assert row["task_id"] == request["task_id"]
    assert row["task_assignment_id"] == request["assignment_id"]
    assert row["admission_id"] == created["admission_id"]
    assert row["binding_id"] == request["binding_id"] == created["artifact_binding_id"]
    assert row["content_id"] == request["content_id"] == created["artifact_content_id"]
    assert row["status"] == "consumed"
    assert row["consumed_submission_id"] == created["submission_id"]
    assert row["consumed_by_submission_version"] == created["submission_version"]
    assert (row["resource_type"], row["resource_id"]) == (
        "submission", created["submission_id"]
    )
    assert row["binding_content_id"] == row["replica_content_id"] == request["content_id"]
    assert row["sha256"] == request["content_sha256"]
    assert row["task_status"] == "submitted"


async def _restore_validated_snapshot_rows(
    database_url: str,
    snapshot: dict[str, object],
    *,
    expected_revision: str,
) -> dict[str, object]:
    """Restore one checksum-validated snapshot into its isolated predecessor."""
    connection = await asyncpg.connect(_asyncpg_url(database_url))
    try:
        await _assert_owned_test_database(connection, database_url)
        await _assert_database_guards_enabled(connection)
        revision = await connection.fetchval("SELECT version_num FROM public.alembic_version")
        assert expected_revision == revision
        tables = tuple(sorted(snapshot["tables"]))
        database_tables = tuple(row["tablename"] for row in await connection.fetch("""
            SELECT tablename FROM pg_tables
            WHERE schemaname='public' ORDER BY tablename
        """))
        assert set(tables).issubset(database_tables), "archived table inventory differs"
        table_columns: dict[str, tuple[str, ...]] = {}
        for table in tables:
            columns = tuple(await connection.fetchval("""
                SELECT array_agg(column_name ORDER BY ordinal_position)
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=$1
            """, table))
            table_columns[table] = columns
            assert all(set(row) == set(columns) for row in snapshot["tables"][table]), (
                f"archived columns differ for {table}"
            )
        original_triggers = await _trigger_state(connection)
        original_foreign_keys = await _foreign_keys(connection)
        original_fk_state = tuple(
            (row["oid"], row["condeferrable"], row["condeferred"])
            for row in original_foreign_keys
        )
        async with connection.transaction():
            # A faithful backup restore is setup, not a current writer proof.
            # User triggers resume before any migration assertion receives data.
            for table in database_tables:
                await connection.execute(
                    f"ALTER TABLE public.{_identifier(table)} DISABLE TRIGGER USER"
                )
            changed_constraints: list[tuple[str, str]] = []
            for constraint in original_foreign_keys:
                if not constraint["condeferrable"]:
                    table = _identifier(constraint["child_table"])
                    name = _identifier(constraint["conname"])
                    await connection.execute(
                        f"ALTER TABLE public.{table} ALTER CONSTRAINT {name} "
                        "DEFERRABLE INITIALLY DEFERRED"
                    )
                    changed_constraints.append(
                        (constraint["child_table"], constraint["conname"])
                    )
            await connection.execute("SET CONSTRAINTS ALL DEFERRED")
            for table in database_tables:
                await connection.execute(f"DELETE FROM public.{_identifier(table)}")
            for table in tables:
                await connection.execute(
                    f"INSERT INTO public.{_identifier(table)} "
                    f"SELECT * FROM jsonb_populate_recordset("
                    f"NULL::public.{_identifier(table)},$1::jsonb)",
                    json.dumps(
                        snapshot["tables"][table],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
            await connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
            await _validate_foreign_keys(connection, await _foreign_keys(connection))
            for table in database_tables:
                await connection.execute(
                    f"ALTER TABLE public.{_identifier(table)} ENABLE TRIGGER USER"
                )
            for table_name, constraint_name in changed_constraints:
                await connection.execute(
                    f"ALTER TABLE public.{_identifier(table_name)} "
                    f"ALTER CONSTRAINT {_identifier(constraint_name)} NOT DEFERRABLE"
                )
            assert await _trigger_state(connection) == original_triggers
            await _assert_database_guards_enabled(connection)
            final_foreign_keys = await _foreign_keys(connection)
            assert tuple(
                (row["oid"], row["condeferrable"], row["condeferred"])
                for row in final_foreign_keys
            ) == original_fk_state
            nonempty_tables: list[str] = []
            for table in database_tables:
                if await connection.fetchval(
                    f"SELECT EXISTS(SELECT 1 FROM public.{_identifier(table)})"
                ):
                    nonempty_tables.append(table)
            nonempty = tuple(nonempty_tables)
            assert nonempty == tables, "archived nonempty table inventory differs"
            for table in tables:
                actual = sorted(
                    (json.loads(row["value"]) for row in await connection.fetch(
                        f"SELECT to_jsonb(r)::text AS value "
                        f"FROM public.{_identifier(table)} r"
                    )),
                    key=lambda row: json.dumps(
                        row, sort_keys=True, separators=(",", ":")
                    ),
                )
                expected = sorted(
                    snapshot["tables"][table],
                    key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")),
                )
                assert actual == expected, f"archived rows differ for {table}"
            if "archived_material" in snapshot["seed"]:
                await _validate_material_custody(connection, snapshot["seed"])
        return deepcopy(snapshot["seed"])
    finally:
        await connection.close()


async def restore_archived_snapshot(
    database_url: str, snapshot_name: str | None = None
) -> dict[str, object]:
    """Restore literal rows into their exact isolated predecessor revision."""
    connection = await asyncpg.connect(_asyncpg_url(database_url))
    try:
        await _assert_owned_test_database(connection, database_url)
        await _assert_database_guards_enabled(connection)
        revision = await connection.fetchval("SELECT version_num FROM public.alembic_version")
    finally:
        await connection.close()
    key = snapshot_name or revision
    snapshot = deepcopy(_snapshots()[key])
    if snapshot_name is None:
        assert key == revision
    else:
        assert snapshot["revision"] == revision
    return await _restore_validated_snapshot_rows(
        database_url,
        snapshot,
        expected_revision=revision,
    )


@asynccontextmanager
async def historical_material_fixture(
    _tmp_path, database_url, *, snapshot_name: str | None = None
):
    """Yield plain archived facts after the isolated predecessor restore closes."""
    seed = await restore_archived_snapshot(database_url, snapshot_name)
    yield SimpleNamespace(
        factory=db_session.get_session_factory(),
        request=seed["request"],
        created=seed["created"],
        replica_id=seed["replica_id"],
        archived_members=tuple(seed["archived_members"]),
        archived_counts=seed["archived_counts"],
        archived_material=seed["archived_material"],
    )
