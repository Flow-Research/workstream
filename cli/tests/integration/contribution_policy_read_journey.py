"""CLI Finance lifecycle inside the retained real public guide-activation journey."""

import json
from uuid import uuid4

from sqlalchemy import text

from tests.contributions.public_policy.support import UNPAID


async def publish_with_policy_reads(
    direct,
    cli,
    origin,
    factory,
    project,
    foreign_project,
    finance_token,
    finance_id,
    finance_grant,
    manager_token,
    manager_id,
    other_token,
    foreign_finance_token,
    admin,
    tmp_path,
):
    root = f"/api/v1/projects/{project}/contribution-policies"
    finance = {"Authorization": "Bearer " + finance_token}
    tables = (
        "contribution_policies",
        "contribution_policy_versions",
        "contribution_rules",
        "contribution_award_definitions",
        "project_compensation_units",
        "iso_4217_currency_codes",
        "contribution_policy_transition_custody",
        "contribution_policy_lifecycle_events",
        "project_guides",
        "projects",
    )

    async def stored():
        async with factory() as session:
            return {
                table: [
                    dict(row)
                    for row in (
                        await session.execute(text(f"SELECT * FROM {table} ORDER BY 1"))
                    ).mappings()
                ]
                for table in tables
            }

    async def write(method, path, body, headers=finance):
        response = await direct.request(
            method, path, headers=headers | {"Idempotency-Key": str(uuid4())}, json=body
        )
        assert response.status_code in (200, 201), response.text
        return response.json()

    async def mutate(
        action,
        *,
        policy=None,
        version=None,
        body=None,
        key=None,
        token=finance_token,
        actor_id=finance_id,
        selected_project=project,
        status=None,
    ):
        key = key or str(uuid4())
        body = {} if body is None else body
        selectors = (str(selected_project).replace("-", ""),)
        path = f"/api/v1/projects/{selected_project}/contribution-policies"
        method = "POST"
        if action == "create":
            path += "/drafts"
        else:
            selectors += (str(policy).replace("-", ""), str(version).replace("-", ""))
            path += f"/{policy}/versions/{version}"
            path += {"publish": "/publication", "retire": "/retirement"}.get(action, "")
            if action == "update":
                method = "PUT"
        flags = ()
        if action in ("create", "update"):
            file = tmp_path / "finance-policy-input.json"
            file.write_text(json.dumps(body))
            flags = ("--input", str(file))
        before = await stored()
        result = cli(
            origin,
            token,
            "project",
            "contribution-policy",
            action,
            *selectors,
            *flags,
            "--idempotency-key",
            key,
            "-o",
            "json",
        )
        if status is not None:
            assert result.returncode == 1 and result.stdout == "", result.stderr
            error = json.loads(result.stderr)["error"]
            assert error["status"] == status and "outcome_unknown" not in error, error
            assert await stored() == before
            return error
        assert result.returncode == 0 and result.stderr == "", result.stderr
        value = json.loads(result.stdout)
        after = await stored()
        # Direct REST replay must recover the very same immutable event.
        replay = await direct.request(
            method,
            path,
            headers={"Authorization": "Bearer " + token, "Idempotency-Key": key},
            json=body,
        )
        assert replay.status_code == (201 if action == "create" else 200), replay.text
        assert replay.json() == value and await stored() == after
        events = [
            row
            for row in after["contribution_policy_lifecycle_events"]
            if str(row["id"]) == value["event_id"]
        ]
        assert len(events) == 1 and str(events[0]["operation_id"]) == key
        assert str(events[0]["actor_profile_id"]) == str(actor_id)
        assert (
            str(events[0]["contribution_policy_version_id"])
            == value["contribution_policy_version_id"]
        )
        return value

    def call(
        action,
        *,
        policy=None,
        version=None,
        selected_project=project,
        token=finance_token,
        status=None,
    ):
        args = (str(selected_project).replace("-", ""),)
        if action == "show":
            args += (str(policy).replace("-", ""),)
        if version is not None:
            args += ("--version", str(version).replace("-", ""))
        result = cli(
            origin, token, "project", "contribution-policy", action, *args, "-o", "json"
        )
        if status is not None:
            assert result.returncode == 1 and result.stdout == "", result.stderr
            error = json.loads(result.stderr)["error"]
            assert error["status"] == status and "outcome_unknown" not in error, error
            if status == 404:
                assert error["code"] == "contribution_policy_not_found"
            return error
        assert result.returncode == 0 and result.stderr == "", result.stderr
        return json.loads(result.stdout)

    async def inspect(
        receipt, published_id, draft_id, *, explicit=None, expected_status=None
    ):
        before = await stored()
        current = call("current")
        assert current == {
            "project_id": str(project),
            "contribution_policy_id": receipt["contribution_policy_id"],
            "current_published_version_id": published_id,
            "open_draft_version_id": draft_id,
        }
        expected = await direct.get(root + "/current", headers=finance)
        assert expected.status_code == 200 and current == expected.json()
        viewed = call(
            "show", policy=receipt["contribution_policy_id"], version=explicit
        )
        expected = await direct.get(
            root + "/" + receipt["contribution_policy_id"],
            headers=finance,
            params={} if explicit is None else {"version_id": explicit},
        )
        assert expected.status_code == 200 and viewed == expected.json()
        if explicit is not None:
            assert viewed["contribution_policy_version_id"] == explicit
        if expected_status is not None:
            assert viewed["version_status"] == expected_status
        assert (
            await stored() == before
        )  # AUTH read evidence is intentionally outside these tables.
        return viewed

    spec = (await direct.get("/openapi.json")).json()["paths"]
    for route in (
        "/api/v1/projects/{project_id}/contribution-policies/current",
        "/api/v1/projects/{project_id}/contribution-policies/{policy_id}",
    ):
        assert (
            spec[route]["get"]["x-workstream-action-id"] == "contribution.policy.read"
        )
    create_key = str(uuid4())
    for presented in (other_token, foreign_finance_token):
        await mutate("create", body={"name": "Denied"}, token=presented, status=404)
    first = await mutate(
        "create", body={"name": "Governed project policy"}, key=create_key
    )
    first_id = first["contribution_policy_version_id"]
    empty = await inspect(
        first, None, first_id, explicit=first_id, expected_status="draft"
    )
    assert empty["rules"] == [] and empty["version_number"] == 1
    await mutate("create", body={"name": "Changed intent"}, key=create_key, status=409)
    first_update_key = str(uuid4())
    first_update = await mutate(
        "update",
        policy=first["contribution_policy_id"],
        version=first_id,
        body=UNPAID,
        key=first_update_key,
    )
    for presented in (other_token, foreign_finance_token):
        await mutate(
            "update",
            policy=first["contribution_policy_id"],
            version=first_id,
            body=UNPAID,
            token=presented,
            status=404,
        )
        await mutate(
            "publish",
            policy=first["contribution_policy_id"],
            version=first_id,
            token=presented,
            status=404,
        )
    first_publish_key = str(uuid4())
    first_published = await mutate(
        "publish",
        policy=first["contribution_policy_id"],
        version=first_id,
        key=first_publish_key,
    )
    view = await inspect(first, first_id, None, expected_status="published")
    assert (
        call("current", token=manager_token)["current_published_version_id"] == first_id
    )
    assert (
        call("show", policy=first["contribution_policy_id"], token=manager_token)
        == view
    )
    assert {rule["contribution_type"] for rule in view["rules"]} == {
        "accepted_submission",
        "completed_review",
    }
    assert all(
        rule["compensation_mode"] == "unpaid" and rule["definitions"] == []
        for rule in view["rules"]
    )
    successor = await mutate("create", body={"name": "Governed project policy"})
    next_id = successor["contribution_policy_version_id"]
    default = await inspect(first, first_id, next_id, expected_status="published")
    assert default["contribution_policy_version_id"] == first_id
    next_view = await inspect(
        first, first_id, next_id, explicit=next_id, expected_status="draft"
    )
    assert next_view["rules"] == [] and next_view["version_number"] == 2
    await mutate(
        "update", policy=first["contribution_policy_id"], version=next_id, body=UNPAID
    )
    publish_key = str(uuid4())
    published = await mutate(
        "publish",
        policy=first["contribution_policy_id"],
        version=next_id,
        key=publish_key,
    )
    assert (
        await mutate(
            "update",
            policy=first["contribution_policy_id"],
            version=first_id,
            body=UNPAID,
            key=first_update_key,
        )
        == first_update
    )
    assert (
        await mutate(
            "publish",
            policy=first["contribution_policy_id"],
            version=first_id,
            key=first_publish_key,
        )
        == first_published
    )
    old = await inspect(
        first, next_id, None, explicit=first_id, expected_status="retired"
    )
    assert old["policy_status"] == "active" and old["rules"] == view["rules"]
    await inspect(first, next_id, None, expected_status="published")

    # Stored foreign aggregate/version, created by real foreign-project Finance.
    foreign = await write(
        "POST",
        f"/api/v1/projects/{foreign_project}/contribution-policies/drafts",
        {"name": "Foreign policy"},
        {"Authorization": "Bearer " + foreign_finance_token},
    )
    before = await stored()
    for presented in (other_token, foreign_finance_token):
        await mutate(
            "retire",
            policy=first["contribution_policy_id"],
            version=next_id,
            token=presented,
            status=404,
        )
        call("current", token=presented, status=404)
        call(
            "show",
            policy=first["contribution_policy_id"],
            version=next_id,
            token=presented,
            status=404,
        )
    call(
        "show",
        policy=foreign["contribution_policy_id"],
        version=foreign["contribution_policy_version_id"],
        status=404,
    )
    call(
        "show",
        policy=first["contribution_policy_id"],
        version=foreign["contribution_policy_version_id"],
        status=404,
    )
    call("current", selected_project=foreign_project, status=404)
    call(
        "show",
        selected_project=foreign_project,
        policy=foreign["contribution_policy_id"],
        status=404,
    )
    call("current", token="invalid-token", status=401)
    await mutate(
        "retire",
        policy=first["contribution_policy_id"],
        version=next_id,
        token="invalid-token",
        status=401,
    )
    await mutate(
        "retire",
        policy=foreign["contribution_policy_id"],
        version=foreign["contribution_policy_version_id"],
        status=404,
    )
    await mutate(
        "retire",
        policy=first["contribution_policy_id"],
        version=foreign["contribution_policy_version_id"],
        status=404,
    )
    await mutate(
        "create", selected_project=foreign_project, body={"name": "Denied"}, status=404
    )
    assert await stored() == before

    async def denied():
        before = await stored()
        call("current", status=404)
        call(
            "show", policy=first["contribution_policy_id"], version=next_id, status=404
        )
        await mutate(
            "retire",
            policy=first["contribution_policy_id"],
            version=next_id,
            status=404,
        )
        await mutate(
            "publish",
            policy=first["contribution_policy_id"],
            version=next_id,
            key=publish_key,
            status=404,
        )
        assert await stored() == before

    await write(
        "POST",
        f"/api/v1/actors/{finance_id}/suspend",
        {"reason": "Finance read admission proof"},
        admin,
    )
    await denied()
    await write(
        "POST",
        f"/api/v1/actors/{finance_id}/reactivate",
        {"reason": "Restore Finance read admission"},
        admin,
    )
    await inspect(first, next_id, None, expected_status="published")
    await write(
        "POST",
        f"/api/v1/admin-role-grants/{finance_grant}/revoke",
        {"reason": "Finance read current authority proof"},
        admin,
    )
    await denied()
    await write(
        "POST",
        "/api/v1/admin-role-grants",
        {
            "target_actor_profile_id": str(finance_id),
            "role": "finance_authority",
            "scope_type": "project",
            "scope_project_id": str(project),
            "reason": "Restore exact-project Finance authority",
        },
        admin,
    )
    await inspect(first, next_id, None, expected_status="published")

    async def retire_and_inspect():
        retired = await mutate(
            "retire",
            policy=first["contribution_policy_id"],
            version=next_id,
            token=manager_token,
            actor_id=manager_id,
        )
        assert retired["prior_current_version_id"] == next_id
        assert (
            await mutate(
                "publish",
                policy=first["contribution_policy_id"],
                version=next_id,
                key=publish_key,
            )
            == published
        )
        before = await stored()
        historical = call(
            "show", policy=first["contribution_policy_id"], version=next_id
        )
        expected = await direct.get(
            root + "/" + first["contribution_policy_id"],
            headers=finance,
            params={"version_id": next_id},
        )
        assert expected.status_code == 200 and historical == expected.json()
        assert (historical["policy_status"], historical["version_status"]) == (
            "retired",
            "retired",
        )
        call("current", status=404)
        assert await stored() == before

    return published, retire_and_inspect
