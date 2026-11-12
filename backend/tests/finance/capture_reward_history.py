"""One-time genuine pre-v2 history capture; run explicitly before replacing the writer.

This file is not an ordinary collected test. Its output is immutable migration
input, not a way to originate v1 work after the reward writer changes.
"""

import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from sqlalchemy import text

from app.db import session as db_session
from tests.contributions.records.support import authorized_submitter_source
from tests.tasks.test_task_import_batches import _batch_path, _verified_source
from tests.tasks.test_task_import_contract import document
from tests.test_task_import_sources import (
    _project,
    import_source_client as import_source_client,
)
from tests.test_tasks import (
    auth_headers,
    complete_task_payload,
    task_database_env as task_database_env,
)

WRITER_COMMIT = "70a60846b6bb122a835f1a1d6928edf326cbfdef"
ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).parents[1] / "fixtures"


async def capture(name: str, seed: dict) -> None:
    """Export real rows only from the runner-owned pre-v2 database."""
    subprocess.run(
        [
            "git",
            "diff",
            "--exit-code",
            WRITER_COMMIT,
            "--",
            "backend/app/modules/contributions",
            "backend/app/modules/compensation/awards",
            "backend/app/modules/tasks",
            "backend/alembic/versions",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    target = OUTPUT / name
    if target.exists():
        raise RuntimeError("retained reward capture already exists; do not overwrite history")
    async with db_session.get_session_factory()() as session:
        database, role = (
            await session.execute(text("SELECT current_database(),current_user"))
        ).one()
        assert database.startswith("workstream_test_") and role.startswith("workstream_role_")
        assert database.removeprefix("workstream_test_") == role.removeprefix("workstream_role_")
        revision = await session.scalar(text("SELECT version_num FROM public.alembic_version"))
        assert revision == "0068_issuer_profile_email"
        names = (
            await session.scalars(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
            )
        ).all()
        tables = {}
        numeric_columns = {}
        for table in names:
            quoted = '"' + table.replace('"', '""') + '"'
            numeric = (
                await session.scalars(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name=:table AND data_type='numeric' "
                        "ORDER BY ordinal_position"
                    ),
                    {"table": table},
                )
            ).all()
            projection = "to_jsonb(r)"
            for column in numeric:
                identifier = '"' + column.replace('"', '""') + '"'
                literal = "'" + column.replace("'", "''") + "'"
                projection += f" || jsonb_build_object({literal},r.{identifier}::text)"
            rows = (
                await session.scalars(
                    text(f"SELECT {projection} FROM public.{quoted} r LIMIT 5001")
                )
            ).all()
            assert len(rows) <= 5000, "capture fixture unexpectedly large"
            if rows:
                tables[table] = sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))
                numeric_columns[table] = numeric
    body = {
        "schema_version": "workstream.reward_history.v1",
        "source_revision": revision,
        "writer_commit": WRITER_COMMIT,
        "seed": seed,
        "tables": tables,
        "numeric_columns": numeric_columns,
    }
    for expected in seed.get("awards", []):
        stored = next(row for row in tables["compensation_awards"] if row["id"] == expected["id"])
        assert stored["quantity"] == expected["quantity"], "captured award precision changed"
    encoded = gzip.compress(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode(), mtime=0
    )
    target.write_bytes(encoded)
    print(name, hashlib.sha256(encoded).hexdigest())


async def test_capture_dual_awards(tmp_path, isolated_database_env, live_acceptance_lifecycle):
    async with authorized_submitter_source(tmp_path, isolated_database_env, paid=True) as h:
        await capture(
            "finance_reward_v1_dual.json.gz",
            {
                "project_id": str(h.submitter_record.project_id),
                "task_id": str(h.submitter_record.task_id),
                "submission_id": str(h.submitter_record.submission_id),
                "contribution_record_id": str(h.submitter_record.id),
                "final_acceptance_id": str(h.acceptance.id),
                "award_ids": [str(award.id) for award in h.participation.awards],
                "awards": [
                    {
                        "id": str(award.id),
                        "instrument_type": award.instrument_type.value,
                        "quantity": format(award.quantity, "f"),
                        "unit_code": award.unit_code,
                    }
                    for award in h.participation.awards
                ],
            },
        )


async def test_capture_omitted_size_create_and_import(import_source_client):
    client = import_source_client
    project = await _project(client)
    payload, headers = complete_task_payload(), auth_headers()
    created = await client.post(f"/api/v1/projects/{project}/tasks", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    assert "task_size" not in created.json()
    replay = await client.post(f"/api/v1/projects/{project}/tasks", json=payload, headers=headers)
    assert replay.json() == created.json()
    value = document(2)
    source = await _verified_source(client, project, value)
    import_headers = auth_headers()
    imported = await client.post(
        _batch_path(project), headers=import_headers, json={"source_id": source["source_id"]}
    )
    assert imported.status_code == 201, imported.text
    assert all("task_size" not in item for item in imported.json()["tasks"])
    await capture(
        "finance_reward_v1_task_replay.json.gz",
        {
            "project_id": project,
            "create_request": payload,
            "create_idempotency_key": headers["Idempotency-Key"],
            "create_response": created.json(),
            "import_request": {"source_id": source["source_id"]},
            "import_idempotency_key": import_headers["Idempotency-Key"],
            "import_document": value,
            "import_response": imported.json(),
        },
    )
