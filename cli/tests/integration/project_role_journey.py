"""Explicit CLI role decisions in the retained real contributor journey."""

import json
from pathlib import Path
import tempfile
from uuid import uuid4

from sqlalchemy import text

from project_role_read_journey import (
    inspect_role_history,
    deny_role_history,
    inspect_revoked_history,
)
from contributor_candidate_journey import (
    inspect_contributor_candidates,
    deny_contributor_candidates,
)


async def exercise_project_role_decisions(
    direct,
    cli,
    origin,
    tokens,
    profiles,
    factory,
    project,
    foreign_project,
    qualification,
    reviewer_id,
    control_actor_id,
    control_token,
):
    admin = {"Authorization": "Bearer " + tokens["cli-admin"]}
    system = {"Authorization": "Bearer " + tokens["cli-manager"]}
    scoped = tokens["cli-project-manager"]
    manager_id = profiles["cli-project-manager"]["actor_profile_id"]
    target = profiles["cli-outsider"]["actor_profile_id"]
    issue_key, revoke_key = str(uuid4()), str(uuid4())
    body = {
        "target_actor_profile_id": target,
        "role": "submitter",
        "qualification": qualification,
        "reason": "CLI explicit qualification",
    }

    async def post(path, payload, headers=None):
        response = await direct.post(
            path,
            headers=(admin if headers is None else headers)
            | {"Idempotency-Key": str(uuid4())},
            json=payload,
        )
        assert response.status_code in (200, 201), response.text
        return response.json()

    async def manager_grant():
        # CLI19 deliberately revokes its covering grant before returning.
        return await post(
            "/api/v1/admin-role-grants",
            {
                "target_actor_profile_id": manager_id,
                "role": "project_manager",
                "scope_type": "project",
                "scope_project_id": project,
                "reason": "Exact project role decision proof",
            },
        )

    # The retained journey's bootstrap administrator already performs many
    # distinct setup/lifecycle controls. Give this independent control actor
    # its real public authority instead of exceeding that actor's 30/minute
    # limiter, disabling rate controls, clearing counters or retrying requests.
    await post(
        "/api/v1/admin-role-grants",
        {
            "target_actor_profile_id": control_actor_id,
            "role": "access_administrator",
            "scope_type": "system",
            "scope_project_id": None,
            "reason": "Independent CLI role lifecycle proof",
        },
    )
    admin = {"Authorization": "Bearer " + control_token}
    covering = await manager_grant()
    candidate_cursor = await inspect_contributor_candidates(
        direct,
        cli,
        origin,
        scoped,
        tokens["cli-manager"],
        tokens["cli-outsider"],
        project,
        foreign_project,
        manager_id,
        target,
        factory,
    )
    original_covering_id = covering["resource_id"]
    paths = (await direct.get("/openapi.json")).json()["paths"]
    for path, action in (
        ("/api/v1/projects/{project_id}/role-grants", "issue"),
        ("/api/v1/projects/{project_id}/role-grants/{grant_id}/revoke", "revoke"),
    ):
        assert (
            paths[path]["post"]["x-workstream-action-id"]
            == "project_role_grant." + action
        )

    def invoke(
        action,
        payload,
        *,
        grant=None,
        selected_project=project,
        presented=scoped,
        key=None,
        status=None,
    ):
        with tempfile.TemporaryDirectory(prefix="ws-cli-role-input-") as directory:
            file = Path(directory) / "decision.json"
            file.write_text(json.dumps(payload, indent=2) + "\n")
            selectors = (selected_project.replace("-", ""),)
            if action == "revoke":
                selectors += (grant.replace("-", ""),)
            result = cli(
                origin,
                presented,
                "project",
                "role-grant",
                action,
                *selectors,
                "--input",
                str(file),
                "--idempotency-key",
                key or str(uuid4()),
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

    first = invoke("issue", body, key=issue_key)
    assert first["project_id"] == project and first["actor_profile_id"] == target
    assert first["role"] == "submitter" and (first["status"], first["version"]) == (
        "active",
        1,
    )
    assert invoke("issue", body, key=issue_key) == first
    replay = await direct.post(
        f"/api/v1/projects/{project}/role-grants",
        headers={"Authorization": "Bearer " + scoped, "Idempotency-Key": issue_key},
        json=body,
    )
    assert replay.status_code == 201 and replay.json() == first, replay.text
    assert (
        invoke(
            "issue", body | {"reason": "Changed decision"}, key=issue_key, status=409
        )["code"]
        == "idempotency_mismatch"
    )
    assert invoke("issue", body, status=409)["code"] == "project_role_grant_exists"
    reviewer_body = body | {"target_actor_profile_id": reviewer_id, "role": "reviewer"}
    reviewer = invoke("issue", reviewer_body)
    assert (
        reviewer["actor_profile_id"] == reviewer_id and reviewer["role"] == "reviewer"
    )

    async def stored():
        async with factory() as session:
            grants = [
                dict(row)
                for row in (
                    await session.execute(
                        text(
                            "SELECT * FROM project_role_grants WHERE project_id IN (:project,:foreign) ORDER BY id"
                        ),
                        {"project": project, "foreign": foreign_project},
                    )
                ).mappings()
            ]
            snapshots = [
                dict(row)
                for row in (
                    await session.execute(
                        text(
                            "SELECT * FROM project_role_qualification_snapshots WHERE project_id IN (:project,:foreign) ORDER BY id"
                        ),
                        {"project": project, "foreign": foreign_project},
                    )
                ).mappings()
            ]
            events = list(
                (
                    await session.execute(
                        text(
                            "SELECT event_type,entity_id FROM audit_events WHERE entity_id IN (:grant,:snapshot) AND event_type IN ('ProjectRoleGrantIssued','ProjectRoleGrantRevoked','ProjectRoleQualificationSnapshotCaptured') ORDER BY event_type"
                        ),
                        {
                            "grant": first["id"],
                            "snapshot": first["qualification_snapshot_id"],
                        },
                    )
                ).all()
            )
            all_role_events = list(
                (
                    await session.execute(
                        text(
                            "SELECT id,event_type,entity_id FROM audit_events WHERE event_type IN ('ProjectRoleGrantIssued','ProjectRoleGrantRevoked','ProjectRoleQualificationSnapshotCaptured') ORDER BY id"
                        )
                    )
                ).all()
            )
            return grants, snapshots, events, all_role_events

    foreign = await post(
        f"/api/v1/projects/{foreign_project}/role-grants",
        reviewer_body | {"role": "submitter"},
        system,
    )
    self_grant = await post(
        f"/api/v1/projects/{project}/role-grants",
        body | {"target_actor_profile_id": manager_id},
        system,
    )
    before = await stored()
    read_cursor, read_snapshot = await inspect_role_history(
        direct,
        cli,
        origin,
        scoped,
        project,
        foreign_project,
        first,
        reviewer,
        self_grant,
        foreign,
        tokens["cli-outsider"],
        qualification,
    )
    assert await stored() == before
    grants, snapshots, events, _all_role_events = before
    row = next(row for row in grants if str(row["id"]) == first["id"])
    snapshot = next(
        row for row in snapshots if str(row["id"]) == first["qualification_snapshot_id"]
    )
    assert str(row["qualification_snapshot_id"]) == str(snapshot["id"])
    assert str(row["actor_profile_id"]) == str(snapshot["actor_profile_id"]) == target
    assert str(row["project_id"]) == str(snapshot["project_id"]) == project
    assert row["role"] == snapshot["requested_role"] == "submitter"
    assert row["grant_reason"] == body["reason"]
    assert (
        str(row["granted_by_actor_profile_id"])
        == str(snapshot["captured_by_actor_profile_id"])
        == manager_id
    )
    assert (
        str(row["granted_by_admin_role_grant_id"])
        == str(snapshot["captured_by_admin_role_grant_id"])
        == original_covering_id
    )
    for name, value in qualification.items():
        assert snapshot[name] == value
    assert [event[0] for event in events] == [
        "ProjectRoleGrantIssued",
        "ProjectRoleQualificationSnapshotCaptured",
    ]
    async with factory() as session:
        retained = (
            (
                await session.execute(
                    text(
                        "SELECT status,response_resource_id,response_resource_version,response_http_status FROM authority_idempotency_records WHERE actor_ref=:actor AND operation='project_role_grant.issue' AND idempotency_key=:key"
                    ),
                    {"actor": manager_id, "key": issue_key},
                )
            )
            .mappings()
            .one()
        )
        assert (
            retained["status"] == "committed"
            and str(retained["response_resource_id"]) == first["id"]
        )
        assert (
            retained["response_resource_version"],
            retained["response_http_status"],
        ) == (1, 201)

    invoke("issue", body, selected_project=foreign_project, status=404)
    invoke(
        "revoke",
        {"reason": "Foreign stored grant"},
        grant=foreign["id"],
        selected_project=foreign_project,
        status=404,
    )
    invoke("issue", reviewer_body, presented=tokens["cli-outsider"], status=404)
    invoke(
        "revoke",
        {"reason": "Submitter is not a manager"},
        grant=reviewer["id"],
        presented=tokens["cli-outsider"],
        status=404,
    )
    invoke("issue", body | {"target_actor_profile_id": manager_id}, status=403)
    invoke(
        "revoke",
        {"reason": "Cannot revoke own role"},
        grant=self_grant["id"],
        status=403,
    )
    await post(
        f"/api/v1/actors/{manager_id}/suspend",
        {"reason": "Fresh role replay admission"},
    )
    # These sensitive AUTH mutations conceal suspended admission with 404,
    # unlike the separately owned task mutation routes.
    invoke("issue", body, key=issue_key, status=404)
    invoke("revoke", {"reason": "Suspended manager"}, grant=first["id"], status=404)
    deny_role_history(cli, origin, scoped, project, first["id"], read_cursor)
    deny_contributor_candidates(cli, origin, scoped, project, candidate_cursor)
    await post(
        f"/api/v1/actors/{manager_id}/reactivate",
        {"reason": "Independent scoped revocation"},
    )
    assert invoke("issue", body, key=issue_key) == first
    await post(
        f"/api/v1/admin-role-grants/{covering['resource_id']}/revoke",
        {"reason": "Fresh role replay authority"},
    )
    invoke("issue", body, key=issue_key, status=404)
    invoke("revoke", {"reason": "Revoked manager"}, grant=first["id"], status=404)
    deny_role_history(cli, origin, scoped, project, first["id"], read_cursor)
    deny_contributor_candidates(cli, origin, scoped, project, candidate_cursor)
    assert await stored() == before
    covering = await manager_grant()

    async def revoke_first():
        payload = {"reason": "Discovery must reauthorize"}
        revoked = invoke("revoke", payload, grant=first["id"], key=revoke_key)
        assert revoked == first | {"status": "revoked", "version": 2}
        assert invoke("revoke", payload, grant=first["id"], key=revoke_key) == revoked
        assert (
            invoke(
                "revoke",
                {"reason": "Changed reason"},
                grant=first["id"],
                key=revoke_key,
                status=409,
            )["code"]
            == "idempotency_mismatch"
        )
        assert (
            invoke("issue", body, key=issue_key, status=409)["code"]
            == "project_role_grant_replay_state_changed"
        )
        grants_after, snapshots_after, events_after, all_events_after = await stored()
        # The retained journey has legitimately issued other roles meanwhile.
        # Every original immutable snapshot must remain unchanged.
        after_by_id = {str(row["id"]): row for row in snapshots_after}
        assert all(after_by_id[str(row["id"])] == row for row in snapshots)
        grants_by_id = {str(row["id"]): row for row in grants_after}
        assert all(
            grants_by_id[str(row["id"])] == row
            for row in grants
            if str(row["id"]) != first["id"]
        )
        changed = next(row for row in grants_after if str(row["id"]) == first["id"])
        assert changed["status"] == "revoked" and changed["version"] == 2
        assert changed["revoked_reason"] == payload["reason"]
        assert str(changed["revoked_by_actor_profile_id"]) == manager_id
        assert str(changed["revoked_by_admin_role_grant_id"]) == covering["resource_id"]
        assert [event[0] for event in events_after] == [
            "ProjectRoleGrantIssued",
            "ProjectRoleGrantRevoked",
            "ProjectRoleQualificationSnapshotCaptured",
        ]
        await inspect_revoked_history(
            direct,
            cli,
            origin,
            scoped,
            project,
            first,
            read_snapshot,
            payload["reason"],
        )
        assert await stored() == (
            grants_after,
            snapshots_after,
            events_after,
            all_events_after,
        )
        # Cleanup only this helper's extra management authority; contributor
        # state and the existing claim denial assertions remain independent.
        await post(
            f"/api/v1/admin-role-grants/{covering['resource_id']}/revoke",
            {"reason": "Role CLI proof complete"},
        )
        invoke("revoke", payload, grant=first["id"], key=revoke_key, status=404)
        deny_role_history(cli, origin, scoped, project, first["id"], read_cursor)

    return revoke_first
