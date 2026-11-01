"""Real Flow/PostgreSQL public-API continuation for the Operator task CLI."""

import json
from uuid import uuid4

from sqlalchemy import func, select

from api_contract_e2e import flow_settings, issue_flow_token
from app.db import session as db_session
from app.modules.tasks.models import AuditEvent, TaskAssignment


async def exercise_operator_task_journey(
    direct,
    cli,
    origin,
    tokens,
    env,
    project,
    foreign_project,
    claimed_task,
    contributor,
):
    paths = (await direct.get("/openapi.json", timeout=60)).json()["paths"]
    for route, method, action in (
        (
            "/api/v1/operations/projects/{project_id}/tasks",
            "get",
            "operations.task.queue.read",
        ),
        (
            "/api/v1/operations/projects/{project_id}/tasks/{task_id}/locked-context",
            "get",
            "operations.task.locked_context.read",
        ),
    ):
        assert paths[route][method]["x-workstream-action-id"] == action

    assert "/api/v1/operations/tasks/{task_id}/start" not in paths

    issuer, audience, secret = flow_settings(env)
    operator_token = issue_flow_token(
        "cli-task-operator", [], issuer=issuer, audience=audience, secret=secret
    )
    operator_headers = {"Authorization": "Bearer " + operator_token}
    admin_headers = {"Authorization": "Bearer " + tokens["cli-admin"]}
    manager_headers = {"Authorization": "Bearer " + tokens["cli-manager"]}
    admitted = await direct.get("/api/v1/actors/me", headers=operator_headers)
    assert admitted.status_code == 200, admitted.text
    operator_id = admitted.json()["actor_profile_id"]

    def run(*args, token=operator_token, status=None):
        result = cli(origin, token, "operations", "task", *args, "-o", "json")
        if status is not None:
            assert result.returncode == 1 and result.stdout == "", result.stderr
            error = json.loads(result.stderr)["error"]
            assert error["status"] == status and "outcome_unknown" not in error
            return error
        assert result.returncode == 0 and result.stderr == "", result.stderr
        return json.loads(result.stdout)

    run("list", project, status=404)
    run("locked-context", project, claimed_task, status=404)

    issued = await direct.post(
        "/api/v1/admin-role-grants",
        headers=admin_headers | {"Idempotency-Key": str(uuid4())},
        json={
            "target_actor_profile_id": operator_id,
            "role": "operator",
            "scope_type": "system",
            "scope_project_id": None,
            "reason": "CLI exact task inspection proof",
        },
    )
    assert issued.status_code == 201, issued.text
    grant_id = issued.json()["resource_id"]

    before = await direct.get(
        f"/api/v1/projects/{project}/assignments", headers=manager_headers
    )
    assert before.status_code == 200, before.text
    assignment = next(
        item for item in before.json()["items"] if item["task_id"] == claimed_task
    )
    assignment_id = assignment["assignment_id"]
    assert assignment["contributor_actor_id"] == contributor

    first = run("list", project.replace("-", ""), "--limit", "1")
    expected = await direct.get(
        f"/api/v1/operations/projects/{project}/tasks",
        headers=operator_headers,
        params={"limit": 1},
    )
    assert expected.status_code == 200 and first == expected.json()
    assert first["project_id"] == project and first["next_cursor"] is not None
    assert set(first["items"][0]) == {
        "task_id",
        "project_id",
        "status",
        "created_at",
        "updated_at",
    }
    continued = run("list", project, "--limit", "1", "--cursor", first["next_cursor"])
    expected = await direct.get(
        f"/api/v1/operations/projects/{project}/tasks",
        headers=operator_headers,
        params={"limit": 1, "cursor": first["next_cursor"]},
    )
    assert expected.status_code == 200 and continued == expected.json()
    run(
        "list",
        foreign_project,
        "--limit",
        "1",
        "--cursor",
        first["next_cursor"],
        status=422,
    )
    run("locked-context", foreign_project, claimed_task, status=404)

    context = run(
        "locked-context", project.replace("-", ""), claimed_task.replace("-", "")
    )
    expected = await direct.get(
        f"/api/v1/operations/projects/{project}/tasks/{claimed_task}/locked-context",
        headers=operator_headers,
    )
    assert expected.status_code == 200 and context == expected.json()
    assert context["task_id"] == claimed_task and context["project_id"] == project
    assert (
        "locked_post_submit_checker_policy_hash" in context
        and "policy_body" not in context
    )

    after = await direct.get(
        f"/api/v1/projects/{project}/assignments", headers=manager_headers
    )
    assert after.status_code == 200, after.text
    same = next(
        item for item in after.json()["items"] if item["task_id"] == claimed_task
    )
    assert (
        same["assignment_id"] == assignment_id
        and same["contributor_actor_id"] == contributor
    )

    async with db_session.get_session_factory()() as session:
        row = await session.get(TaskAssignment, assignment_id)
        assert row.contributor_id == contributor and row.task_id == claimed_task
        assert row.started_at == row.assigned_at and row.started_at is not None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.entity_id == claimed_task,
                    AuditEvent.event_type == "TaskStartOverridden",
                )
            )
            == 0
        )

    revoked = await direct.post(
        f"/api/v1/admin-role-grants/{grant_id}/revoke",
        headers=admin_headers | {"Idempotency-Key": str(uuid4())},
        json={"reason": "Inspection requires current Operator authority"},
    )
    assert revoked.status_code == 200, revoked.text
    run("list", project, status=404)
    run("locked-context", project, claimed_task, status=404)
