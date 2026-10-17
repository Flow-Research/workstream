"""Project work pages and the summary stay within budget on 10,000 tasks and 20,000 submissions.

The preparation list is timed over 10,000 seeded runs, so its project/queued
index carries the page and the ``failed`` filter scans every pending run. The
guide list (C1) and the contribution policy list (D1) are low-cardinality per
project and are not timed here.
"""

import json

from tests.contributor_reads.test_scale import (
    BUDGET_SECONDS,
    SUBMISSIONS_PER_TASK,
    TASKS,
    _seed,
    _timed,
)
from .support import as_manager, get_ok, project_path, submitted_case


async def test_project_pages_and_summary_meet_budget_at_scale(
    task_client, monkeypatch, task_database_env
):
    project, task, submission = await submitted_case(task_client, monkeypatch)
    await _seed(task_database_env, task, submission, preparations=TASKS)
    as_manager(monkeypatch)
    timings, pages = {}, {}
    for name, suffix, params in (
        ("submissions", "/submissions", {"limit": 100}),
        ("submissions_filtered", "/submissions", {"limit": 100, "status": "evaluation_pending"}),
        ("assignments", "/assignments", {"limit": 100}),
        ("summary", "/summary", {}),
        ("import_batches", "/task-import-batches", {"limit": 100}),
        ("preparations", "/submission-bundle-preparations", {"limit": 100}),
        (
            "preparations_failed",
            "/submission-bundle-preparations",
            {"limit": 100, "outcome": "failed"},
        ),
    ):
        timings[name], page = await _timed(task_client, project_path(project, suffix), **params)
        pages[name] = page
        if page.get("next_cursor"):
            timings[name + "_continued"], _ = await _timed(
                task_client, project_path(project, suffix), **params, cursor=page["next_cursor"]
            )
    # A seeding miss must fail: the timed page is full, and no seeded or real run failed.
    assert len(pages["preparations"]["items"]) == 100 and pages["preparations"]["next_cursor"]
    assert pages["preparations_failed"] == {"items": [], "next_cursor": None}
    summary = await get_ok(task_client, project_path(project, "/summary"))
    assert sum(summary["tasks"].values()) == TASKS + 1
    assert summary["assignments"]["active"] == TASKS + 1
    assert sum(summary["submissions"].values()) == TASKS * SUBMISSIONS_PER_TASK + 1
    print("project read timings (s):", json.dumps(timings, sort_keys=True))
    assert max(timings.values()) < BUDGET_SECONDS, timings
