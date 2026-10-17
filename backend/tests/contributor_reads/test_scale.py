"""List pages and the summary stay within budget on 10,000 tasks and 20,000 submissions."""

import json
import secrets
import time
from datetime import timedelta

import asyncpg

from app.core.identifiers import new_record_id
from tests.test_tasks import set_dev_actor
from .support import ME, MANAGER, OWNER, get_ok, preparations_path, submitted_case

TASKS, SUBMISSIONS_PER_TASK, PREPARATIONS = 10_000, 2, 30
BUDGET_SECONDS = 1.0
_TABLES = ("workstream_tasks", "task_assignments", "submissions", "selected_pre_submit_runs")

async def _clone(connection, table, template, varying, constant=None):
    """Insert copies of one real row; ``varying`` maps column -> (type, values)."""
    columns = await connection.fetchval(
        "SELECT array_agg(column_name::text ORDER BY ordinal_position) FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=$1", table)
    constant = constant or {}
    names = list(varying)
    select = ", ".join(
        f"c.{name}" if name in varying else constant.get(name, f"t.{name}") for name in columns
    )
    arrays = ", ".join(f"${index + 2}::{kind}[]" for index, (kind, _) in enumerate(varying.values()))
    await connection.execute(
        f"INSERT INTO public.{table} ({', '.join(columns)}) SELECT {select} "
        f"FROM public.{table} t, unnest({arrays}) AS c({', '.join(names)}) WHERE t.id=$1",
        template, *(values for _, values in varying.values()),
    )


async def _seed(database_url, task, submission, *, preparations=PREPARATIONS):
    """Clone the real claimed task, assignment, attempt and ``preparations`` runs under bulk restore."""
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        start = await connection.fetchval("SELECT updated_at FROM public.workstream_tasks WHERE id=$1", task)
        assignment = await connection.fetchval(
            "SELECT id FROM public.task_assignments WHERE task_id=$1", task)
        run = await connection.fetchval(
            "SELECT id FROM public.selected_pre_submit_runs WHERE task_id=$1", task)
        tasks = [new_record_id() for _ in range(TASKS)]
        stamps = [start + timedelta(milliseconds=index) for index in range(len(tasks))]
        assignments = [new_record_id() for _ in tasks]
        async with connection.transaction():
            # Fixture restore only: owner guards pause for exact clones of real rows;
            # foreign keys stay enforced and every guard resumes before commit.
            for table in _TABLES:
                await connection.execute(f"ALTER TABLE public.{table} DISABLE TRIGGER USER")
            await _clone(connection, "workstream_tasks", task, {
                "id": ("uuid", tasks), "created_at": ("timestamptz", stamps), "updated_at": ("timestamptz", stamps),
            })
            await _clone(connection, "task_assignments", assignment, {
                "id": ("uuid", assignments), "task_id": ("uuid", tasks), "updated_at": ("timestamptz", stamps),
            })
            for version in range(1, SUBMISSIONS_PER_TASK + 1):
                await _clone(connection, "submissions", submission, {
                    "id": ("uuid", [new_record_id() for _ in tasks]), "task_id": ("uuid", tasks),
                    "task_assignment_id": ("uuid", assignments), "updated_at": ("timestamptz", stamps),
                }, {"version": str(version), **dict.fromkeys((
                    "submission_bundle_admission_id", "artifact_binding_id", "artifact_content_id",
                    "supersedes_submission_id",
                ), "NULL")})
            runs = [new_record_id() for _ in range(preparations)]
            await _clone(connection, "selected_pre_submit_runs", run, {
                "id": ("uuid", runs), "idempotency_key": ("uuid", [new_record_id() for _ in runs]),
                "request_digest": ("text", ["sha256:" + secrets.token_hex(32) for _ in runs]),
                "queued_at": ("timestamptz", [start + timedelta(seconds=index + 1) for index in range(preparations)]),
            }, {"status": "'queued'", "lease_generation": "0", **dict.fromkeys((
                "terminal_json", "terminal_digest", "eligible", "lease_id", "lease_expires_at", "started_at",
                "completed_at", "execute_evidence_id", "finalize_evidence_id",
            ), "NULL")})
            for table in _TABLES:
                await connection.execute(f"ALTER TABLE public.{table} ENABLE TRIGGER USER")
        for table in _TABLES:
            await connection.execute(f"ANALYZE public.{table}")
        assert not await connection.fetchval(
            "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgenabled='D'")
        return runs
    finally:
        await connection.close()


async def _timed(client, path, **params):
    """Warm once, then return the slowest of three measured reads and the last page."""
    await get_ok(client, path, **params)
    slowest, page = 0.0, None
    for _ in range(3):
        started = time.perf_counter()
        page = await get_ok(client, path, **params)
        slowest = max(slowest, time.perf_counter() - started)
    return slowest, page


async def test_pages_and_summary_meet_budget_at_scale(task_client, monkeypatch, task_database_env):
    project, task, submission = await submitted_case(task_client, monkeypatch)
    runs = await _seed(task_database_env, task, submission)
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    timings = {}
    for name, path, params in (
        ("assignments", f"{ME}/assignments", {"limit": 100}),
        ("submissions", f"{ME}/submissions", {"limit": 100, "status": "evaluation_pending"}),
        ("summary", f"{ME}/summary", {}),
        ("preparations", preparations_path(task), {"limit": 100}),
    ):
        timings[name], page = await _timed(task_client, path, **params)
        if page.get("next_cursor"):
            timings[name + "_continued"], _ = await _timed(
                task_client, path, **params, cursor=page["next_cursor"])
    assert page["items"][0]["preparation_id"] == str(runs[-1])
    walked, cursor = [], None
    while True:
        step = await get_ok(task_client, preparations_path(task), limit=7, **({"cursor": cursor} if cursor else {}))
        walked += [item["preparation_id"] for item in step["items"]]
        if (cursor := step["next_cursor"]) is None:
            break
    assert walked[:PREPARATIONS] == [str(run) for run in reversed(runs)] and len(set(walked)) == PREPARATIONS + 1
    summary = await get_ok(task_client, f"{ME}/summary")
    assert summary["assignments"]["active"] == TASKS + 1
    assert sum(summary["submissions"].values()) == TASKS * SUBMISSIONS_PER_TASK + 1
    set_dev_actor(monkeypatch, roles="", subject=MANAGER)
    timings["project_tasks"], _ = await _timed(
        task_client, f"/api/v1/projects/{project}/tasks", limit=100, status="evaluation_pending")
    print("contributor read timings (s):", json.dumps(timings, sort_keys=True))
    assert max(timings.values()) < BUDGET_SECONDS, timings
