"""A Project Manager lists the project's native import batches with state and member counts."""

import json
from uuid import uuid4

from tests.tasks.test_task_import_contract import document
from tests.test_task_import_sources import (
    _declare, _path, _project, import_source_client as import_source_client,
)
from tests.test_tasks import auth_headers, create_active_project, set_dev_actor, task_database_env as task_database_env
from .support import EXACT_MANAGER, OWNER, as_admin, as_manager, get_ok, project_path


async def _import(client, project, rows, prefix):
    """Import one real verified JSON file through the public source and batch routes."""
    value = document(rows)
    for index, task in enumerate(value["tasks"]):
        task.update(external_task_id=f"{prefix}-{index}", acceptance_criteria="Accurate, complete work",
                    rejection_criteria="Incomplete work")
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    source = await _declare(client, project, raw)
    uploaded = await client.put(_path(project, source) + "/content", content=raw,
                                headers=auth_headers() | {"Content-Type": "application/json"})
    assert uploaded.status_code == 200, uploaded.text
    response = await client.post(project_path(project, "/task-import-batches"), headers=auth_headers(),
                                 json={"source_id": source["source_id"]})
    assert response.status_code == 201, response.text
    return response.json()


async def test_batches_list_in_creation_order_with_state_and_member_counts(import_source_client, monkeypatch):
    client = import_source_client
    project = (await create_active_project(client, slug="batch-list-" + uuid4().hex))["id"]
    batches = [await _import(client, project, rows, f"batch-{uuid4().hex[:8]}") for rows in (3, 1, 2)]
    screened = await client.post(
        f"/api/v1/tasks/{batches[1]['tasks'][0]['id']}/screen", headers=auth_headers(),
        json={"reason": "screening checklist passed"},
    )
    assert screened.status_code == 200, screened.text
    rows, cursor = [], None
    while True:
        page = await get_ok(client, project_path(project, "/task-import-batches"),
                            limit=2, **({"cursor": cursor} if cursor else {}))
        rows += page["items"]
        if (cursor := page["next_cursor"]) is None:
            break
    assert [row["batch_id"] for row in rows] == [batch["batch_id"] for batch in batches]
    for row, batch in zip(rows, batches, strict=True):
        assert (row["source_id"], row["sha256"], row["byte_count"], row["row_count"], row["label"]) == (
            batch["source_id"], batch["sha256"], batch["byte_count"], batch["row_count"], batch["label"])
        assert row["state"] == "committed" and row["committed_at"] is not None
        assert sum(row["task_counts"].values()) == batch["row_count"]
    assert rows[0]["task_counts"]["draft"] == 3
    assert rows[1]["task_counts"]["draft"] == 0  # its one member moved on
    assert rows[2]["task_counts"]["draft"] == 2


async def test_batch_list_is_project_scoped_and_concealed_from_other_callers(import_source_client, monkeypatch):
    client = import_source_client
    project, other = await _project(client), await _project(client)
    await _import(client, project, 1, f"scoped-{uuid4().hex[:8]}")
    assert (await get_ok(client, project_path(other, "/task-import-batches")))["items"] == []
    await as_admin(client, monkeypatch, EXACT_MANAGER, "project_manager", project=other)
    assert (await client.get(project_path(project, "/task-import-batches"),
                             headers=auth_headers())).status_code == 404
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    await client.get("/api/v1/actors/me", headers=auth_headers())
    assert (await client.get(project_path(project, "/task-import-batches"),
                             headers=auth_headers())).status_code == 404
    as_manager(monkeypatch)
    [listed] = (await get_ok(client, project_path(project, "/task-import-batches")))["items"]
    assert listed["row_count"] == 1
