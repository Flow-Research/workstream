"""Public create/import persists sizes; SQL and saved receipts retain exact custody."""

import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.artifacts.task_import_sources import ArtifactTaskImportSourceCommands
from app.modules.tasks.models import WorkstreamTask, TaskCommandReceipt
from tests.test_task_import_sources import (
    import_source_client as import_source_client,
    _project,
    _declare,
    _path,
)
from tests.test_tasks import auth_headers, task_database_env as task_database_env


async def test_public_creation_stores_default_and_each_exact_size(import_source_client):
    client = import_source_client
    project = await _project(client)
    created = []
    for index, (selection, expected) in enumerate(
        (
            ({}, "small"),
            ({"task_size": "small"}, "small"),
            ({"task_size": "medium"}, "medium"),
            ({"task_size": "large"}, "large"),
        )
    ):
        body = {"title": f"Task {index}", "description": "Instructions", **selection}
        headers = auth_headers() | {"Idempotency-Key": str(uuid4())}
        response = await client.post(
            f"/api/v1/projects/{project}/tasks", headers=headers, json=body
        )
        assert response.status_code == 201, response.text
        assert response.json()["task_size"] == expected
        original = response.json()
        replay = await client.post(f"/api/v1/projects/{project}/tasks", headers=headers, json=body)
        assert replay.status_code == 201 and replay.json() == original, replay.text
        if not selection:
            explicit = await client.post(f"/api/v1/projects/{project}/tasks", headers=headers,
                                         json=body | {"task_size": "small"})
            assert explicit.status_code == 201 and explicit.json() == original, explicit.text
            changed = await client.post(f"/api/v1/projects/{project}/tasks", headers=headers,
                                        json=body | {"task_size": "medium"})
            assert changed.status_code == 409, changed.text
        created.append(original)
        async with db_session.get_session_factory()() as session:
            task = await session.get(WorkstreamTask, original["id"])
            receipt = await session.scalar(
                select(TaskCommandReceipt).where(TaskCommandReceipt.task_id == task.id)
            )
            assert task.task_size == expected
            assert receipt.response == original
    for invalid in (
        {"task_size": None},
        {"task_size": "Small"},
        {"quantity": "10"},
        {"instrument_type": "money"},
        {"unit_code": "USD"},
    ):
        response = await client.post(
            f"/api/v1/projects/{project}/tasks",
            headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
            json={"title": "Bad", "description": "D", **invalid},
        )
        assert response.status_code == 422, response.text
    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                text("SELECT count(*) FROM workstream_tasks WHERE project_id=:project"),
                {"project": UUID(project)},
            )
            == 4
        )
    async with db_session.get_session_factory()() as session, session.begin():
        for value in (None, "large"):
            with pytest.raises(DBAPIError, match="task size is immutable"):
                async with session.begin_nested():
                    await session.execute(
                        text("UPDATE workstream_tasks SET task_size=:size WHERE id=:id"),
                        {"size": value, "id": UUID(created[0]["id"])},
                    )
        with pytest.raises(DBAPIError, match="new tasks require an explicit size"):
            async with session.begin_nested():
                await session.execute(
                    text(
                        "INSERT INTO workstream_tasks SELECT (jsonb_populate_record(NULL::workstream_tasks, (to_jsonb(t)-'task_size')||jsonb_build_object('id',CAST(:id AS uuid)))).* FROM workstream_tasks t WHERE t.id=:source"
                    ),
                    {"id": new_record_id(), "source": UUID(created[0]["id"])},
                )
        with pytest.raises(DBAPIError, match="new task commands must record the exact size"):
            async with session.begin_nested():
                await session.execute(
                    text("""INSERT INTO task_command_receipts
                    (id,actor_profile_id,action_id,idempotency_key,request_digest,task_id,status,locked_context_hash,response,committed_at)
                    VALUES(:id,:actor,'project.task.create',:key,:digest,:task,'committed',:digest,CAST(:response AS jsonb),now())"""),
                    {
                        "id": new_record_id(),
                        "actor": UUID(created[0]["created_by"]),
                        "key": uuid4(),
                        "digest": "sha256:" + "0" * 64,
                        "task": UUID(created[0]["id"]),
                        "response": json.dumps(
                            {key: value for key, value in created[0].items() if key != "task_size"}
                        ),
                    },
                )


async def test_verified_json_import_keeps_sizes_and_replays_without_provider_or_parser(
    import_source_client, monkeypatch
):
    client = import_source_client
    project = await _project(client)
    rows = [
        {"external_task_id": "a", "title": "Small", "description": "D"},
        {"external_task_id": "b", "title": "Medium", "description": "D", "task_size": "medium"},
        {"external_task_id": "c", "title": "Large", "description": "D", "task_size": "large"},
    ]
    raw = json.dumps({"schema_version": "workstream.task_import.v1", "tasks": rows}).encode()
    source = await _declare(client, project, raw)
    upload = await client.put(
        _path(project, source) + "/content",
        headers=auth_headers() | {"Content-Type": "application/json"},
        content=raw,
    )
    assert upload.status_code == 200, upload.text
    headers = auth_headers() | {"Idempotency-Key": str(uuid4())}
    path = f"/api/v1/projects/{project}/task-import-batches"
    body = {"source_id": source["source_id"]}
    response = await client.post(path, headers=headers, json=body)
    assert response.status_code == 201, response.text
    original = response.json()
    assert [task["task_size"] for task in original["tasks"]] == ["small", "medium", "large"]

    def forbidden(*args, **kwargs):
        raise AssertionError("saved import must not reopen or reparse source bytes")

    monkeypatch.setattr(ArtifactTaskImportSourceCommands, "open", forbidden)
    monkeypatch.setattr("app.modules.tasks.task_import_batches.parse_task_import", forbidden)
    replay = await client.post(path, headers=headers, json=body)
    assert replay.status_code == 201 and replay.json() == original, replay.text
    status = await client.get(path + "/" + original["batch_id"], headers=auth_headers())
    assert status.status_code == 200 and status.json()["creation"] == original, status.text
