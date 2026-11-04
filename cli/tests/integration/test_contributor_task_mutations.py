"""Built-process proof of public contributor writes, not local authority rules."""

from copy import deepcopy
import json
from urllib.parse import quote

from http2_fixture import goaway_fixture
from test_http_boundary import (
    ACTOR,
    PROFILE,
    PROJECT,
    TOKEN,
    assert_failure,
    http_fixture,
)
from test_task_http_boundary import TASK, SUMMARY_TEXT

KEY = "018f0ebc-7966-7e8d-bc4d-1cae1e000004"
POLICY = "018f0ebc-7966-7e8d-bc4d-1cae1e000005"
ASSIGNMENT = "018f0ebc-7966-7e8d-bc4d-1cae1e000006"
TASK_RESPONSE = {
    "id": TASK,
    "project_id": PROJECT,
    "locked_contribution_policy_version_id": POLICY,
    "locked_guide_version": "guide é\n",
    "locked_review_policy_id": POLICY,
    "locked_review_policy_generation": 1,
    "locked_review_policy_hash": "sha256:" + "a" * 64,
    "locked_revision_policy_id": POLICY,
    "locked_revision_policy_generation": 2,
    "locked_revision_policy_hash": "sha256:" + "b" * 64,
    "source_type": "manual",
    "title": "Work é\n\x1b[31m",
    "description": "Instructions\n\x1b[32m",
    "skill_tags": ["analysis", "tag\n"],
    "status": "in_progress",
    "created_at": PROFILE["created_at"],
    "updated_at": "2026-10-02T00:00:00Z",
}
ASSIGNMENT_RESPONSE = {
    "id": ASSIGNMENT,
    "task_id": TASK,
    "project_id": PROJECT,
    "submitter_contribution_policy_version_id": POLICY,
    "contributor_id": ACTOR,
    "assigned_by": ACTOR,
    "assigned_at": PROFILE["created_at"],
    "accepted_at": PROFILE["created_at"],
    "status": "active",
}


def body(action):
    task = deepcopy(TASK_RESPONSE)
    if action == "claim":
        return {"task": task, "assignment": deepcopy(ASSIGNMENT_RESPONSE)}
    raise AssertionError("unsupported contributor task mutation")


def invoke(cli, origin, action, *flags, selector=TASK, key=KEY, output="json"):
    return cli(
        origin,
        TOKEN,
        "-o",
        output,
        "task",
        action,
        selector,
        "--idempotency-key",
        key,
        *flags,
    )


def canonical_error(code="authorization_denied"):
    return {
        "error": {
            "code": code,
            "message": "Denied",
            "details": {},
            "correlation_id": KEY,
            "retryable": False,
        }
    }


def test_task_writes_preserve_body_key_selector_and_json(cli):
    with http_fixture() as (origin, response, requests):
        for action in ("claim",):
            response["body"] = json.dumps(body(action)).encode()
            for selector in (
                TASK,
                TASK.replace("-", ""),
                "{" + TASK + "}",
                "urn:uuid:" + TASK,
            ):
                for flags, expected in (
                    ((), {}),
                    (("--reason", ""), {"reason": ""}),
                    (("--reason", "Note é\n"), {"reason": "Note é\n"}),
                ):
                    result = invoke(
                        cli,
                        origin,
                        action,
                        *flags,
                        selector=selector,
                        key=KEY.replace("-", ""),
                    )
                    assert result.returncode == 0 and result.stderr == "", result.stderr
                    assert result.stdout.strip().encode() == response["body"]
                    assert requests[-1] == (
                        "POST",
                        f"/api/v1/tasks/{quote(selector, safe=':')}/{action}",
                        "Bearer " + TOKEN,
                    )
                    assert response["commands"][-1] == (
                        "application/json",
                        [KEY.replace("-", "")],
                        expected,
                    )
            boundary = "é" * 1000
            result = invoke(cli, origin, action, "--reason", boundary)
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert result.stdout.strip().encode() == response["body"]
            assert response["commands"][-1] == (
                "application/json",
                [KEY],
                {"reason": boundary},
            )
        assert len(requests) == len(response["commands"]) == 13


def test_task_write_text_is_complete_and_escaped(cli):
    optional = {
        "task_type": "evaluation",
        "difficulty": "medium",
        "estimated_time_minutes": 17,
        "deadline_at": "2026-10-03T00:00:00Z",
        "acceptance_criteria": "Accurate",
        "rejection_criteria": "Missing",
    }
    with http_fixture() as (origin, response, requests):
        for action in ("claim",):
            value = body(action)
            task = value["task"] if action == "claim" else value
            task.update(optional)
            response["body"] = json.dumps(value).encode()
            result = invoke(cli, origin, action, output="text")
            assert result.returncode == 0 and result.stderr == ""
            status = "in_progress"
            expected = SUMMARY_TEXT.replace("Status: draft", f"Status: {status}")
            expected += (
                "Description: Instructions\\u000A\\u001B[32m\nAcceptance criteria: Accurate\n"
                "Rejection criteria: Missing\nSource type: manual\n"
                f"Contribution policy: {POLICY}\nGuide version: guide é\\u000A\n"
                f"Review policy: {POLICY}\nReview generation: 1\nReview hash: sha256:{'a' * 64}\n"
                f"Revision policy: {POLICY}\nRevision generation: 2\nRevision hash: sha256:{'b' * 64}\n"
            )
            if action == "claim":
                expected += (
                    f"Assignment: {ASSIGNMENT}\nAssignment task: {TASK}\nAssignment project: {PROJECT}\n"
                    f"Submitter policy: {POLICY}\nContributor: {ACTOR}\nAssigned by: {ACTOR}\n"
                    "Assigned at: 2026-10-01T00:00:00Z\nAccepted at: 2026-10-01T00:00:00Z\n"
                    "Released at: —\nAssignment status: active\n"
                )
            assert result.stdout == expected
            # Explicit nullable fields remain valid and raw JSON is not rewritten.
            for name in optional:
                task[name] = None
            response["body"] = json.dumps(value).encode()
            result = invoke(cli, origin, action)
            assert (
                result.returncode == 0
                and result.stdout.strip().encode() == response["body"]
            )
        assert len(requests) == 2


def test_task_write_arguments_fail_before_network(cli):
    with http_fixture() as (origin, _response, requests):
        for action in ("claim",):
            for selector, key, flags in (
                ("not-uuid", KEY, ()),
                (TASK + "/start", KEY, ()),
                (TASK, "", ()),
                (TASK, "not-uuid", ()),
                (TASK, KEY, ("--reason", "é" * 1001)),
                (TASK, KEY, ("--reason", b"invalid-\xff")),
                (TASK, KEY, ("--actor-id", ACTOR)),
                (TASK, KEY, ("--project-id", PROJECT)),
                (TASK, KEY, ("--endpoint", "/private")),
            ):
                assert_failure(
                    invoke(cli, origin, action, *flags, selector=selector, key=key),
                    "invalid_arguments",
                    2,
                )
            assert_failure(
                cli(origin, TOKEN, "-o", "json", "task", action, TASK),
                "invalid_arguments",
                2,
            )
        assert requests == []


def test_task_mutation_malformed_and_substituted_success_is_unknown(cli):
    with http_fixture() as (origin, response, requests):
        variants = [
            {"id": PROJECT},
            {"project_id": "bad"},
            {"locked_contribution_policy_version_id": "bad"},
            {"locked_guide_version": None},
            {"locked_review_policy_id": "bad"},
            {"locked_review_policy_generation": None},
            {"locked_review_policy_generation": 0},
            {"locked_review_policy_hash": "bad"},
            {"locked_revision_policy_id": None},
            {"locked_revision_policy_generation": "1"},
            {"locked_revision_policy_hash": "bad"},
            {"status": "ready"},
            {"status": "claimed"},
            {"title": None},
            {"description": None},
            {"skill_tags": [None]},
            {"skill_tags": None},
            {"created_at": "bad"},
            {"updated_at": None},
            {"deadline_at": "bad"},
            *[
                {field: None}
                for field in (
                    "base_amount",
                    "currency",
                    "payout_type",
                    "locked_payment_policy_version",
                )
            ],
            {"estimated_time_minutes": "10"},
        ]
        for action in ("claim",):
            for delta in variants + [
                {name: None}
                for name in (
                    "created_by",
                    "assigned_to",
                    "source_ref",
                    "source_payload_hash",
                    "import_batch_id",
                    "external_task_id",
                    "locked_guide_source_snapshot_id",
                    "locked_guide_source_snapshot_hash",
                    "locked_effective_project_submission_artifact_policy_id",
                    "locked_effective_project_submission_artifact_policy_hash",
                    "locked_pre_submit_checker_policy_id",
                    "locked_pre_submit_checker_bundle_hash",
                )
            ]:
                value = body(action)
                (value["task"] if action == "claim" else value).update(delta)
                response["body"] = json.dumps(value).encode()
                result = invoke(cli, origin, action)
                assert_failure(result, "invalid_api_response")
                assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
            value = body(action)
            for malformed in (
                b"null",
                b"[]",
                b"{}",
                json.dumps(value)
                .encode()
                .replace(b'"id":', b'"id": "' + TASK.encode() + b'", "id":', 1),
            ):
                response["body"] = malformed
                assert_failure(invoke(cli, origin, action), "invalid_api_response")
        for delta in (
            {"id": "bad"},
            {"task_id": PROJECT},
            {"project_id": TASK},
            {"submitter_contribution_policy_version_id": TASK},
            {"assigned_by": PROJECT},
            {"contributor_id": "bad"},
            {"status": "released"},
            {"assigned_at": None},
            {"accepted_at": None},
            {"accepted_at": "bad"},
            {"released_at": PROFILE["created_at"]},
            {"private": "secret"},
        ):
            value = body("claim")
            value["assignment"].update(delta)
            response["body"] = json.dumps(value).encode()
            result = invoke(cli, origin, "claim")
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == len(variants) + 12 + 4 + 12


def test_task_write_uncertainty_and_no_retry(cli):
    with http_fixture() as (origin, response, requests):
        cases = (
            (403, canonical_error(), "application/json", False),
            (409, canonical_error("idempotency_mismatch"), "application/json", False),
            (422, canonical_error("validation_error"), "application/json", False),
            (
                403,
                {"error": canonical_error()["error"] | {"details": None}},
                "application/json",
                True,
            ),
            (408, {"error": {"code": "gateway_timeout"}}, "application/json", True),
            (403, canonical_error(), "text/html", True),
            (403, canonical_error() | {"unexpected": True}, "application/json", True),
            (503, canonical_error(), "application/json", True),
            (302, {}, "application/json", True),
            (201, body("claim"), "application/json", True),
            (200, body("claim"), "text/html", True),
            (200, {}, "application/json", True),
        )
        for action in ("claim",):
            for status, value, content_type, unknown in cases:
                response.update(
                    status=status,
                    body=json.dumps(value).encode(),
                    headers={
                        "Content-Type": content_type,
                        "Location": origin + "/private",
                    },
                )
                result = invoke(cli, origin, action)
                assert result.returncode == 1 and result.stdout == ""
                assert (
                    json.loads(result.stderr)["error"].get("outcome_unknown", False)
                    is unknown
                )
            response.update(
                status=200,
                body=b" " * 65537,
                headers={"Content-Type": "application/json"},
            )
            result = invoke(cli, origin, action)
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
            response["drop"] = True
            result = invoke(
                cli,
                origin,
                action,
                "--reason",
                "Received before disconnect",
                output="text",
            )
            assert result.returncode == 1 and result.stdout == ""
            assert (
                "task outcome unknown" in result.stderr
                and "unchanged action, task, reason and idempotency key"
                in result.stderr
            )
            assert "whoami" not in result.stderr
            assert response["commands"][-1][2] == {
                "reason": "Received before disconnect"
            }
            response["drop"] = False
        assert len(requests) == len(response["commands"]) == len(cases) + 2


def test_task_posts_are_not_replayed_after_http2_goaway(cli, tmp_path):
    for action in ("claim",):
        with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
            result = cli(
                origin,
                TOKEN,
                "-o",
                "json",
                "task",
                action,
                TASK,
                "--idempotency-key",
                KEY,
                "--reason",
                "Received before GOAWAY",
                extra_env=env,
            )
            assert_failure(result, "service_unavailable")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
            assert connections == ["h2"]
            assert [json.loads(value) for value in bodies] == [
                {"reason": "Received before GOAWAY"}
            ]


def test_removed_task_start_command_sends_no_request(cli):
    with http_fixture() as (origin, _response, requests):
        assert_failure(invoke(cli, origin, "start"), "invalid_arguments", 2)
        assert requests == []
