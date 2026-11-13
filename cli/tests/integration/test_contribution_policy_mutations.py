"""Built CLI Finance decisions: wire fidelity, receipt binding and no replay."""

from copy import deepcopy
import json

from http2_fixture import goaway_fixture
from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture
from test_contributor_task_mutations import KEY, POLICY, canonical_error
from test_contribution_policy_reads import VERSION

RULES = {
    "instrument_type": None,
    "unit_code": None,
    "adapter_binding_id": None,
    "rules": [
        {"contribution_type": "accepted_submission", "compensation_mode": "unpaid"},
        {
            "contribution_type": "completed_review",
            "compensation_mode": "unpaid",
        },
    ],
}


def receipt(action):
    return {
        "event_id": ACTOR,
        "operation_id": KEY,
        "request_digest": "sha256:" + "a" * 64,
        "event_type": {
            "create": "draft_created",
            "update": "draft_updated",
            "publish": "published",
            "retire": "retired",
        }[action],
        "actor_profile_id": ACTOR,
        "project_id": PROJECT,
        "contribution_policy_id": POLICY,
        "contribution_policy_version_id": VERSION,
        "version_number": 1,
        "prior_current_version_id": VERSION if action == "retire" else None,
        "prior_current_version_number": 1 if action == "retire" else None,
        "from_policy_status": None
        if action == "create"
        else "active"
        if action == "retire"
        else "draft",
        "to_policy_status": "retired"
        if action == "retire"
        else "active"
        if action == "publish"
        else "draft",
        "from_version_status": None
        if action == "create"
        else "published"
        if action == "retire"
        else "draft",
        "to_version_status": "retired"
        if action == "retire"
        else "published"
        if action == "publish"
        else "draft",
        "occurred_at": "2026-10-13T10:00:00Z",
    }


def invoke(
    cli,
    origin,
    action,
    file,
    *,
    project=PROJECT,
    policy=POLICY,
    version=VERSION,
    key=KEY,
    token=TOKEN,
    output="json",
    extra_env=None,
):
    selectors = (project,) if action == "create" else (project, policy, version)
    flags = ("--input", str(file)) if action in ("create", "update") else ()
    return cli(
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
        output,
        extra_env=extra_env,
    )


def input_for(action):
    return (
        {"name": "Governed project policy"}
        if action == "create"
        else RULES
        if action == "update"
        else {}
    )


def test_finance_decisions_exact_wire_and_complete_receipts(cli, tmp_path):
    file = tmp_path / "policy.json"
    with http_fixture() as (origin, response, requests):
        for action in ("create", "update", "publish", "retire"):
            body = input_for(action)
            file.write_text(json.dumps(body))
            value = receipt(action)
            response.update(
                status=201 if action == "create" else 200,
                body=json.dumps(value).encode(),
            )
            before = len(requests)
            result = invoke(
                cli,
                origin,
                action,
                file,
                project=PROJECT.replace("-", ""),
                policy=POLICY.replace("-", ""),
                version=VERSION.replace("-", ""),
                key=KEY.replace("-", ""),
            )
            assert result.returncode == 0 and json.loads(result.stdout) == value, (
                result.stderr
            )

            assert len(requests) == before + 1
            path = f"/api/v1/projects/{PROJECT.replace('-', '')}/contribution-policies"
            path += (
                "/drafts"
                if action == "create"
                else f"/{POLICY.replace('-', '')}/versions/{VERSION.replace('-', '')}"
            )
            path += {"publish": "/publication", "retire": "/retirement"}.get(action, "")
            assert requests[-1] == (
                "PUT" if action == "update" else "POST",
                path,
                "Bearer " + TOKEN,
            )
            assert response["commands"][-1] == (
                "application/json",
                [KEY.replace("-", "")],
                body,
            )
            text = invoke(cli, origin, action, file, output="text")
            assert (
                text.returncode == 0
                and json.loads(text.stdout.split(": ", 1)[1]) == value
            )

        # Complete replacement retains exact decimal strings and server-owned economics.
        body = deepcopy(RULES)
        body.update(instrument_type="money", unit_code="USD", adapter_binding_id=ACTOR)
        body["rules"][0].update(
            compensation_mode="compensated",
            quantities={
                "small": "99999999999999999999.123456789012345678",
                "medium": "20",
                "large": "10",
            },
        )
        file.write_text(json.dumps(body))
        response.update(status=200, body=json.dumps(receipt("update")).encode())
        assert invoke(cli, origin, "update", file).returncode == 0
        assert response["commands"][-1][2] == body


def test_finance_input_errors_never_dispatch(cli, tmp_path):
    file = tmp_path / "policy.json"
    with http_fixture() as (origin, _, requests):
        for action, bodies in (
            (
                "create",
                [
                    {},
                    {"name": None},
                    {"name": ""},
                    {"name": "x" * 201},
                    {"name": "ok", "extra": 1},
                ],
            ),
            (
                "update",
                [
                    {},
                    {"rules": None},
                    {"rules": [None, None]},
                    {"rules": []},
                    {
                        "rules": [
                            RULES["rules"][0],
                            RULES["rules"][1] | {"definitions": None},
                        ]
                    },
                    {
                        "rules": [
                            RULES["rules"][0] | {"contribution_type": "other"},
                            RULES["rules"][1],
                        ]
                    },
                    {
                        "rules": [
                            RULES["rules"][0]
                            | {
                                "definitions": [
                                    {
                                        "instrument_type": "money",
                                        "unit_code": "USD",
                                        "quantity": 1,
                                        "adapter_binding_id": ACTOR,
                                    }
                                ]
                            },
                            RULES["rules"][1],
                        ]
                    },
                ],
            ),
        ):
            for body in bodies:
                file.write_text(json.dumps(body))
                result = invoke(cli, origin, action, file)
                assert result.returncode != 0 and result.stdout == "", result.stderr
        file.write_text('{"name":"first","name":"second"}')
        assert invoke(cli, origin, "create", file).returncode != 0
        file.write_text(json.dumps(RULES))
        for args in (
            {"project": "../x"},
            {"policy": "../x"},
            {"version": "bad"},
            {"key": ""},
        ):
            assert invoke(cli, origin, "update", file, **args).returncode != 0
        assert requests == []


def test_finance_receipts_bind_targets_events_and_nullable_history(cli, tmp_path):
    file = tmp_path / "policy.json"
    with http_fixture() as (origin, response, _):
        for action in ("create", "update", "publish", "retire"):
            file.write_text(json.dumps(input_for(action)))
            value = receipt(action)
            response.update(
                status=201 if action == "create" else 200,
                body=json.dumps(value).encode(),
            )
            assert invoke(cli, origin, action, file).returncode == 0
            changes = [
                {"project_id": ACTOR},
                {"operation_id": ACTOR},
                {"actor_profile_id": "bad"},
                {"event_id": None},
                {"request_digest": "a" * 64},
                {"event_type": "other"},
                {"occurred_at": "yesterday"},
                {"version_number": None},
                {"version_number": 0},
                {"version_number": 1.5},
                {
                    "prior_current_version_id": ACTOR,
                    "prior_current_version_number": None,
                },
                {"prior_current_version_id": None, "prior_current_version_number": 1},
                {"prior_current_version_id": ACTOR, "prior_current_version_number": 0},
                {"to_version_status": "other"},
                {"to_policy_status": "other"},
                {"extra": True},
            ]
            changes += (
                [
                    {"contribution_policy_id": "bad"},
                    {"contribution_policy_version_id": "bad"},
                ]
                if action == "create"
                else [
                    {"contribution_policy_id": ACTOR},
                    {"contribution_policy_version_id": ACTOR},
                ]
            )
            if action == "retire":
                changes += [
                    {"prior_current_version_id": ACTOR},
                    {"prior_current_version_number": 2},
                ]
            for change in changes:
                response["body"] = json.dumps(value | change).encode()
                result = invoke(cli, origin, action, file)
                assert_failure(result, "invalid_api_response")
                assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
            for missing in value:
                malformed = value.copy()
                del malformed[missing]
                response["body"] = json.dumps(malformed).encode()
                assert_failure(
                    invoke(cli, origin, action, file), "invalid_api_response"
                )
            # Unbounded integers, successor receipts and original historical event state.
            if action != "retire":
                value.update(
                    from_policy_status="active",
                    to_policy_status="active",
                    prior_current_version_id=ACTOR,
                    prior_current_version_number=2**100,
                    version_number=2**100 + 1,
                )
            else:
                value.update(version_number=2**100, prior_current_version_number=2**100)
            response["body"] = json.dumps(value).encode()
            result = invoke(cli, origin, action, file)
            assert result.returncode == 0 and json.loads(result.stdout) == value, (
                result.stderr
            )

            if action != "retire":
                contradictory = [
                    {"prior_current_version_id": VERSION.replace("-", "")},
                    {"prior_current_version_number": value["version_number"]},
                    {"prior_current_version_number": value["version_number"] + 1},
                ]
                if action in ("update", "publish"):
                    contradictory += [
                        {
                            "prior_current_version_id": None,
                            "prior_current_version_number": None,
                        },
                        {
                            "from_policy_status": "draft",
                            "to_policy_status": "draft"
                            if action == "update"
                            else "active",
                        },
                    ]
                for change in contradictory:
                    response["body"] = json.dumps(value | change).encode()
                    result = invoke(cli, origin, action, file)
                    assert_failure(result, "invalid_api_response")
                    assert json.loads(result.stderr)["error"]["outcome_unknown"] is True


def test_finance_failures_preserve_uncertainty_and_credentials(cli, tmp_path):
    file = tmp_path / "policy.json"
    file.write_text(json.dumps(RULES))
    with http_fixture() as (origin, response, requests):
        response.update(
            status=409,
            body=json.dumps(canonical_error("contribution_policy_conflict")).encode(),
        )
        result = invoke(cli, origin, "update", file)
        assert_failure(result, "contribution_policy_conflict")
        assert "outcome_unknown" not in json.loads(result.stderr)["error"]
        malformed = canonical_error("contribution_policy_conflict")
        malformed["error"]["details"] = None
        response["body"] = json.dumps(malformed).encode()
        result = invoke(cli, origin, "update", file)
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        response.update(status=200, body=json.dumps(receipt("update")).encode())
        # A structurally valid UUID or digest can itself be the credential.
        for credential in (ACTOR, "a" * 64):
            assert_failure(
                invoke(cli, origin, "update", file, token=credential),
                "invalid_api_response",
            )
        response["drop"] = True
        before = len(requests)
        result = invoke(cli, origin, "update", file)
        assert len(requests) == before + 1
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        text = invoke(cli, origin, "update", file, output="text")
        assert text.returncode == 1 and text.stdout == ""
        assert "unchanged action" in text.stderr
        assert len(requests) == before + 2


def test_finance_post_and_put_are_not_replayed_after_http2_goaway(cli, tmp_path):
    file = tmp_path / "policy.json"
    for action in ("create", "update", "publish", "retire"):
        body = input_for(action)
        file.write_text(json.dumps(body))
        with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
            result = invoke(cli, origin, action, file, extra_env=env)
            assert_failure(result, "service_unavailable")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
            assert connections == ["h2"] and [
                json.loads(value) for value in bodies
            ] == [body]
