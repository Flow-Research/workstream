"""Read the real stored role decisions through public AUTH and the built CLI."""

import json
from datetime import datetime
from uuid import UUID


def role_read(cli, origin, token, project, *command, status=None):
    action, *flags = command
    result = cli(
        origin,
        token,
        "project",
        "role-grant",
        action,
        project.replace("-", ""),
        *flags,
        "-o",
        "json",
    )
    if status is not None:
        assert result.returncode == 1 and result.stdout == "", result.stderr
        error = json.loads(result.stderr)["error"]
        assert error["status"] == status and "outcome_unknown" not in error, error
        return error
    assert result.returncode == 0 and result.stderr == "", result.stderr
    return json.loads(result.stdout)


async def inspect_role_history(
    direct,
    cli,
    origin,
    token,
    project,
    foreign_project,
    first,
    reviewer,
    self_grant,
    foreign,
    contributor,
    qualification,
):
    path = f"/api/v1/projects/{project}/role-grants"
    headers = {"Authorization": "Bearer " + token}
    paths = (await direct.get("/openapi.json")).json()["paths"]
    for route, action in (
        ("/api/v1/projects/{project_id}/role-grants", "list"),
        ("/api/v1/projects/{project_id}/role-grants/{grant_id}", "read"),
    ):
        assert (
            paths[route]["get"]["x-workstream-action-id"]
            == "project_role_grant." + action
        )
    # History orders by the stored transaction timestamp and UUID, not request
    # completion order. A host clock adjustment can reverse granted_at values.
    granted = []
    for issued in (first, reviewer, self_grant):
        response = await direct.get(path + "/" + issued["id"], headers=headers)
        assert response.status_code == 200, response.text
        row = response.json()
        assert (row["id"], row["project_id"], row["actor_profile_id"], row["role"]) == (
            issued["id"], project, issued["actor_profile_id"], issued["role"]
        )
        granted.append(row)
    expected_order = [
        row["id"] for row in sorted(
            granted, key=lambda row: (
                datetime.fromisoformat(row["granted_at"]), UUID(row["id"])
            ),
        )
    ]
    cursor, first_cursor, seen = None, None, []
    for index in range(3):
        flags = () if cursor is None else ("--cursor", cursor)
        page = role_read(cli, origin, token, project, "list", "--limit", "1", *flags)
        params = {"limit": "1"} | ({} if cursor is None else {"cursor": cursor})
        expected = await direct.get(path, headers=headers, params=params)
        assert expected.status_code == 200, expected.text
        assert page == expected.json() and len(page["items"]) == 1
        seen.append(page["items"][0]["id"])
        cursor = page["next_cursor"]
        if index == 0:
            assert cursor is not None
            first_cursor = cursor
    assert seen == expected_order and cursor is None, (
        seen, [(row["id"], row["granted_at"]) for row in granted], cursor is not None
    )
    selected = role_read(
        cli, origin, token, project, "show", first["id"].replace("-", "")
    )
    expected = await direct.get(path + "/" + first["id"], headers=headers)
    assert expected.status_code == 200 and selected == expected.json()
    assert (
        selected["project_id"],
        selected["actor_profile_id"],
        selected["status"],
        selected["version"],
    ) == (project, first["actor_profile_id"], "active", 1)
    snapshot = selected["qualification_snapshot"]
    assert snapshot["id"] == first["qualification_snapshot_id"]
    assert snapshot["requested_role"] == first["role"]
    for name, value in qualification.items():
        assert snapshot[name] == value
    for status, role, ids in (
        ("active", "reviewer", [reviewer["id"]]),
        ("revoked", "submitter", []),
    ):
        page = role_read(
            cli, origin, token, project, "list", "--status", status, "--role", role
        )
        assert [row["id"] for row in page["items"]] == ids and page[
            "next_cursor"
        ] is None
    for flags in (
        ("--limit", "2"),
        ("--limit", "1", "--status", "revoked"),
        ("--limit", "1", "--role", "reviewer"),
    ):
        denied = role_read(
            cli,
            origin,
            token,
            project,
            "list",
            *flags,
            "--cursor",
            first_cursor,
            status=400,
        )
        assert denied["code"] == "invalid_cursor"
    # A real foreign stored row, not a nonexistent UUID control.
    role_read(cli, origin, token, project, "show", foreign["id"], status=404)
    role_read(cli, origin, token, foreign_project, "show", foreign["id"], status=404)
    role_read(
        cli,
        origin,
        token,
        foreign_project,
        "list",
        "--limit",
        "1",
        "--cursor",
        first_cursor,
        status=404,
    )
    deny_role_history(cli, origin, contributor, project, first["id"], first_cursor)
    return first_cursor, snapshot


def deny_role_history(cli, origin, token, project, grant, cursor):
    for command in (("list", "--limit", "1", "--cursor", cursor), ("show", grant)):
        error = role_read(cli, origin, token, project, *command, status=404)
        assert error["code"] == "project_authorization_resource_not_found"


async def inspect_revoked_history(
    direct, cli, origin, token, project, first, snapshot, reason
):
    value = role_read(cli, origin, token, project, "show", first["id"])
    expected = await direct.get(
        f"/api/v1/projects/{project}/role-grants/{first['id']}",
        headers={"Authorization": "Bearer " + token},
    )
    assert expected.status_code == 200 and value == expected.json()
    assert (value["status"], value["version"], value["revoked_reason"]) == (
        "revoked",
        2,
        reason,
    )
    assert value["qualification_snapshot"] == snapshot
    page = role_read(
        cli,
        origin,
        token,
        project,
        "list",
        "--status",
        "revoked",
        "--role",
        "submitter",
    )
    assert page == {"items": [value], "next_cursor": None}
