"""One real manager preparation journey reused by contributor claim proof."""

import json
from uuid import uuid4

from sqlalchemy import text


async def exercise_manager_task_preparation(
    direct, cli, origin, tokens, profiles, factory, project, foreign_project, input_file
):
    admin = {"Authorization": "Bearer " + tokens["cli-admin"]}
    system = {"Authorization": "Bearer " + tokens["cli-manager"]}
    actor_id = profiles["cli-project-manager"]["actor_profile_id"]
    scoped = tokens["cli-project-manager"]

    async def post(path, body, headers=admin):
        response = await direct.post(
            path, headers=headers | {"Idempotency-Key": str(uuid4())}, json=body
        )
        assert response.status_code in (200, 201), response.text
        return response.json()

    await post(
        f"/api/v1/actors/{actor_id}/reactivate",
        {"reason": "Independent manager mutation proof"},
    )
    grant = await post(
        "/api/v1/admin-role-grants",
        {
            "target_actor_profile_id": actor_id,
            "role": "project_manager",
            "scope_type": "project",
            "scope_project_id": project,
            "reason": "Exact project CLI preparation",
        },
    )
    payload = {
        "title": "Contributor work 0",
        "description": "Inspect the supplied evidence.",
        "task_type": "evaluation",
        "difficulty": "medium",
        "skill_tags": ["analysis"],
        "estimated_time_minutes": 17,
        "acceptance_criteria": "Evidence is complete.",
        "rejection_criteria": "Evidence is missing.",
        "source_ref": "manager-private-source",
        "source_type": "csv_import",
        "import_batch_id": "cli-manager-batch-2026",
        "deadline_at": "2030-01-01T02:00:00+02:00",
    }
    input_file.write_text(json.dumps(payload, indent=2) + "\n")
    task_id = None
    keys = {action: str(uuid4()) for action in ("create", "screen", "release")}

    def invoke(
        action,
        *,
        presented=scoped,
        selected_project=project,
        selected_task=None,
        key=None,
        reason="Explicit manager decision",
        status=None,
    ):
        args = (
            (selected_project, "--input", str(input_file))
            if action == "create"
            else (selected_project, selected_task or task_id, "--reason", reason)
        )
        result = cli(
            origin,
            presented,
            "project",
            "task",
            action,
            *args,
            "--idempotency-key",
            key or keys[action],
            "-o",
            "json",
        )
        if status is not None:
            assert result.returncode == 1 and result.stdout == "", result.stderr
            error = json.loads(result.stderr)["error"]
            assert error["status"] == status and "outcome_unknown" not in error
            return error
        assert result.returncode == 0 and result.stderr == "", result.stderr
        return json.loads(result.stdout)

    # Public routes and exact authority metadata, not hidden owner calls.
    specification = (await direct.get("/openapi.json")).json()["paths"]
    for action, path in (
        ("create", "/api/v1/projects/{project_id}/tasks"),
        ("screen", "/api/v1/tasks/{task_id}/screen"),
        ("release", "/api/v1/tasks/{task_id}/release"),
    ):
        assert (
            specification[path]["post"]["x-workstream-action-id"]
            == "project.task." + action
        )

    receipts = {}
    for action in ("create", "screen", "release"):
        if action == "release":
            error = invoke(action, reason="", key=str(uuid4()), status=422)
            assert error["code"] == "invalid_request"
        receipts[action] = invoke(action)
        task_id = receipts[action]["id"]
        assert receipts[action]["project_id"] == project
        assert receipts[action]["created_by"] == actor_id
        assert (
            receipts[action]["status"]
            == {"create": "draft", "screen": "screening", "release": "ready"}[action]
        )
        assert invoke(action) == receipts[action]
        path = (
            f"/api/v1/projects/{project}/tasks"
            if action == "create"
            else f"/api/v1/tasks/{task_id}/{action}"
        )
        body = (
            payload if action == "create" else {"reason": "Explicit manager decision"}
        )
        replay = await direct.post(
            path,
            headers={
                "Authorization": "Bearer " + scoped,
                "Idempotency-Key": keys[action],
            },
            json=body,
        )
        assert replay.status_code == (201 if action == "create" else 200), replay.text
        assert replay.json() == receipts[action]
        if action == "create":
            input_file.write_text(json.dumps(payload | {"title": "Changed input"}))
            assert invoke(action, status=409)["code"] == "idempotency_mismatch"
            input_file.write_text(json.dumps(payload))
        else:
            assert (
                invoke(action, reason="Changed reason", status=409)["code"]
                == "idempotency_mismatch"
            )

    async def stored():
        async with factory() as session:
            row = (
                (
                    await session.execute(
                        text("SELECT * FROM workstream_tasks WHERE id=:id"),
                        {"id": task_id},
                    )
                )
                .mappings()
                .one()
            )
            audits = list(
                (
                    await session.execute(
                        text(
                            "SELECT event_type FROM audit_events WHERE entity_id=:id AND event_type IN ('TaskCreated','TaskScreened','TaskReleased') ORDER BY event_type"
                        ),
                        {"id": task_id},
                    )
                ).scalars()
            )
            commands = list(
                (
                    await session.execute(
                        text(
                            "SELECT action_id,status,response FROM task_command_receipts WHERE task_id=:id ORDER BY action_id"
                        ),
                        {"id": task_id},
                    )
                ).mappings()
            )
            return dict(row), audits, [dict(c) for c in commands]

    before = await stored()
    row, audits, commands = before
    assert row["status"] == "ready" and row["assigned_to"] is None
    assert row["deadline_at"].isoformat() == "2030-01-01T00:00:00+00:00"
    assert audits == ["TaskCreated", "TaskReleased", "TaskScreened"]
    assert len(commands) == 3 and all(c["status"] == "committed" for c in commands)
    for command in commands:
        action = command["action_id"].rsplit(".", 1)[-1]
        assert command["response"] == receipts[action]
    for field, value in receipts["release"].items():
        if field.startswith("locked_"):
            assert str(row[field]) == str(value)
            assert receipts["screen"][field] == value
    locked_keys = {key for key in receipts["release"] if key.startswith("locked_")}
    assert "locked_guide_version" in locked_keys
    assert {
        key: value
        for key, value in receipts["create"].items()
        if key.startswith("locked_")
    } == dict.fromkeys(locked_keys)

    foreign = await post(f"/api/v1/projects/{foreign_project}/tasks", payload, system)
    for action in ("create", "screen", "release"):
        invoke(
            action,
            selected_project=foreign_project,
            selected_task=foreign["id"],
            key=str(uuid4()),
            status=403,
        )
        invoke(action, presented=tokens["cli-outsider"], key=str(uuid4()), status=403)
        invoke(action, presented="not-a-valid-flow-token", key=str(uuid4()), status=401)
    await post(
        f"/api/v1/actors/{actor_id}/suspend",
        {"reason": "Fresh active-grant mutation denial"},
    )
    invoke("release", status=403)
    await post(
        f"/api/v1/actors/{actor_id}/reactivate",
        {"reason": "Separate grant revocation control"},
    )
    assert invoke("release") == receipts["release"]
    await post(
        f"/api/v1/admin-role-grants/{grant['resource_id']}/revoke",
        {"reason": "Fresh manager replay authority"},
    )
    invoke("release", status=403)
    assert await stored() == before
    foreign_after = await direct.get(
        f"/api/v1/projects/{foreign_project}/tasks/{foreign['id']}", headers=system
    )
    assert (
        foreign_after.status_code == 200 and foreign_after.json()["status"] == "draft"
    )
    return task_id
