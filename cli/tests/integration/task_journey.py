"""Public-only manager task setup and list/detail proof for the real API journey."""

import json
from uuid import uuid4


async def exercise_manager_task_reads(
    direct, cli, origin, tokens, profiles, project_id, other_project_id
):
    system_headers = {"Authorization": f"Bearer {tokens['cli-manager']}"}
    admin_headers = {"Authorization": f"Bearer {tokens['cli-admin']}"}
    scoped_token = tokens["cli-project-manager"]
    task_ids = []
    for index in range(2):
        created = await direct.post(
            f"/api/v1/projects/{project_id}/tasks",
            headers=system_headers | {"Idempotency-Key": str(uuid4())},
            json={
                "title": f"CLI task {index}",
                "description": "Inspect the supplied evidence.",
                "task_type": "evaluation",
                "difficulty": "medium",
                "skill_tags": ["analysis"],
                "estimated_time_minutes": 17,
                "acceptance_criteria": "Evidence is complete.",
                "rejection_criteria": "Evidence is missing.",
                "source_ref": "cli-proof",
                "external_task_id": f"external-{index}",
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["status"] == "draft"
        task_ids.append(created.json()["id"])

    empty = cli(
        origin,
        tokens["cli-manager"],
        "project",
        "tasks",
        other_project_id,
        "-o",
        "json",
    )
    assert empty.returncode == 0 and json.loads(empty.stdout) == {
        "project_id": other_project_id,
        "items": [],
        "next_cursor": None,
    }
    foreign_task = await direct.post(
        f"/api/v1/projects/{other_project_id}/tasks",
        headers=system_headers | {"Idempotency-Key": str(uuid4())},
        json={"title": "Foreign task", "description": "Stored cross-project control"},
    )
    assert foreign_task.status_code == 201, foreign_task.text

    cursor = None
    observed_ids = []
    first_cursor = None
    for _index in range(2):
        flags = () if cursor is None else ("--cursor", cursor)
        result = cli(
            origin,
            tokens["cli-manager"],
            "project",
            "tasks",
            project_id.replace("-", ""),
            "--limit",
            "1",
            *flags,
            "-o",
            "json",
        )
        assert result.returncode == 0 and result.stderr == "", result.stderr
        params = {"limit": "1"} if cursor is None else {"limit": "1", "cursor": cursor}
        expected = await direct.get(
            f"/api/v1/projects/{project_id}/tasks",
            headers=system_headers,
            params=params,
        )
        assert expected.status_code == 200
        page = json.loads(result.stdout)
        assert page == expected.json() and len(page["items"]) == 1
        observed_ids.append(page["items"][0]["task_id"])
        cursor = page["next_cursor"]
        if _index == 0:
            assert cursor is not None
            first_cursor = cursor
    assert observed_ids == task_ids and cursor is None

    for target_project, limit in ((project_id, "2"), (other_project_id, "1")):
        invalid = cli(
            origin,
            tokens["cli-manager"],
            "project",
            "tasks",
            target_project,
            "--limit",
            limit,
            "--cursor",
            first_cursor,
            "-o",
            "json",
        )
        assert invalid.returncode == 1 and invalid.stdout == ""
        assert json.loads(invalid.stderr)["error"]["status"] == 422

    async def issue_scoped_grant():
        grant = await direct.post(
            "/api/v1/admin-role-grants",
            headers=admin_headers | {"Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": profiles["cli-project-manager"][
                    "actor_profile_id"
                ],
                "role": "project_manager",
                "scope_type": "project",
                "scope_project_id": project_id,
                "reason": "CLI exact manager task proof",
            },
        )
        assert grant.status_code == 201, grant.text
        return grant.json()["resource_id"]

    async def positive_reads():
        headers = {"Authorization": f"Bearer {scoped_token}"}
        for command, path, params in (
            (
                ("tasks", project_id, "--limit", "1", "--cursor", first_cursor),
                f"/api/v1/projects/{project_id}/tasks",
                {"limit": "1", "cursor": first_cursor},
            ),
            (
                ("task", project_id.replace("-", ""), task_ids[0].replace("-", "")),
                f"/api/v1/projects/{project_id}/tasks/{task_ids[0]}",
                None,
            ),
        ):
            result = cli(origin, scoped_token, "project", *command, "-o", "json")
            assert result.returncode == 0 and result.stderr == "", result.stderr
            expected = await direct.get(path, headers=headers, params=params)
            assert expected.status_code == 200
            assert json.loads(result.stdout) == expected.json()
        detail = json.loads(result.stdout)
        assert detail["task_id"] == task_ids[0] and detail["project_id"] == project_id
        assert detail["created_by"] == profiles["cli-manager"]["actor_profile_id"]
        assert (
            detail["assigned_to"] is None
            and detail["description"] == "Inspect the supplied evidence."
        )

    def denied_reads():
        for command in (
            ("tasks", project_id, "--limit", "1", "--cursor", first_cursor),
            ("task", project_id, task_ids[0]),
        ):
            result = cli(origin, scoped_token, "project", *command, "-o", "json")
            assert result.returncode == 1 and result.stdout == ""
            assert json.loads(result.stderr)["error"]["status"] == 404

    grant_id = await issue_scoped_grant()
    await positive_reads()
    for command in (
        ("tasks", other_project_id, "--limit", "1", "--cursor", first_cursor),
        ("task", other_project_id, foreign_task.json()["id"]),
    ):
        denied = cli(origin, scoped_token, "project", *command, "-o", "json")
        assert denied.returncode == 1 and denied.stdout == ""
        assert json.loads(denied.stderr)["error"]["status"] == 404
    mismatch = cli(
        origin,
        tokens["cli-manager"],
        "project",
        "task",
        project_id,
        foreign_task.json()["id"],
        "-o",
        "json",
    )
    assert mismatch.returncode == 1 and mismatch.stdout == ""
    assert json.loads(mismatch.stderr)["error"]["status"] == 404
    revoked = await direct.post(
        f"/api/v1/admin-role-grants/{grant_id}/revoke",
        headers=admin_headers | {"Idempotency-Key": str(uuid4())},
        json={"reason": "CLI pagination reauthorizes after revoke"},
    )
    assert revoked.status_code == 200, revoked.text
    denied_reads()
    await issue_scoped_grant()
    await (
        positive_reads()
    )  # Suspension cannot pass merely because the grant remained revoked.
    suspended = await direct.post(
        f"/api/v1/actors/{profiles['cli-project-manager']['actor_profile_id']}/suspend",
        headers=admin_headers | {"Idempotency-Key": str(uuid4())},
        json={"reason": "CLI live task-read lifecycle proof"},
    )
    assert suspended.status_code == 200, suspended.text
    denied_reads()
    return task_ids
