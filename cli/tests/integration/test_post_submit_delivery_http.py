"""Built CLI proof for exact, one-shot post-submit delivery operations."""

from copy import deepcopy
import json
from urllib.parse import parse_qs, urlsplit

from test_http_boundary import PROJECT, TOKEN, assert_failure, http_fixture
from test_contributor_task_mutations import canonical_error

EVENT = "018f0ebc-7966-7e8d-bc4d-1cae1e000201"
CHILD = "018f0ebc-7966-7e8d-bc4d-1cae1e000202"
OTHER = "018f0ebc-7966-7e8d-bc4d-1cae1e000203"
KEY = "018f0ebc-7966-7e8d-bc4d-1cae1e000204"
DIGEST = "sha256:" + "a" * 64


def source():
    return {
        "project_id": PROJECT,
        "event_id": EVENT,
        "event_type": "PostSubmissionEvaluationRequested",
        "event_version": 1,
        "aggregate_id": OTHER,
        "evaluation_request_id": KEY,
        "checker_run_id": OTHER,
        "evaluation_generation": 2**63,
        "claim_generation": 2**63 + 1,
        "payload_digest": DIGEST,
        "finalized_at": "2026-10-20T10:00:00Z",
        "delivery_state": "dead_letter",
        "error_code": "INVOKE_OUTCOME_UNKNOWN",
        "classification": "retry_safe",
        "reconciliation_event_id": None,
        "reconciliation_state": None,
    }


def receipt():
    item = source() | {
        "reconciliation_event_id": CHILD,
        "reconciliation_state": "pending",
    }
    return {
        "source": item,
        "successor": {
            "event_id": CHILD,
            "payload_digest": DIGEST,
            "occurred_at": "2026-10-20T10:00:01Z",
            "classification": "retry_safe",
        },
        "authorization_decision_id": OTHER,
    }


def invoke(cli, origin, *args, output="json"):
    return cli(origin, TOKEN, "-o", output, "operations", "delivery", *args)


def test_delivery_command_group_and_list_wire(cli):
    help_result = cli("", "", "operations", "--help")
    assert help_result.returncode == 0
    assert (
        sum(
            line.strip().startswith("delivery ")
            for line in help_result.stdout.splitlines()
        )
        == 1
    )
    with http_fixture() as (origin, response, requests):
        page = {
            "project_id": PROJECT,
            "items": [source()],
            "next_cursor": "next-opaque",
        }
        response["body"] = json.dumps(page).encode()
        result = invoke(
            cli, origin, "list", PROJECT, "--limit", "1", "--cursor", "prior"
        )
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert json.loads(result.stdout) == page
        assert len(requests) == 1
        method, target, bearer = requests[0]
        assert method == "GET" and bearer == "Bearer " + TOKEN
        assert (
            urlsplit(target).path
            == f"/api/v1/operations/projects/{PROJECT}/post-submit-deliveries"
        )
        assert parse_qs(urlsplit(target).query) == {"limit": ["1"], "cursor": ["prior"]}
        text = invoke(cli, origin, "list", PROJECT, output="text")
        assert text.returncode == 0 and "not reconciliation authority" in text.stdout


def test_delivery_list_rejects_foreign_duplicate_and_malformed_without_output(cli):
    with http_fixture() as (origin, response, requests):
        valid = {"project_id": PROJECT, "items": [source()], "next_cursor": None}
        variants = []
        for changed in (
            {"project_id": OTHER},
            {"items": [source(), source()]},
            {"items": [source() | {"event_id": OTHER, "project_id": OTHER}]},
            {"items": [source() | {"payload_digest": "bad"}]},
            {"items": [source() | {"claim_generation": 0}]},
            {"items": [source() | {"reconciliation_state": "held"}]},
            {"items": [source() | {"error_code": TOKEN}]},
            {"next_cursor": ""},
            {"next_cursor": "x" * 513},
        ):
            variants.append(valid | changed)
        variants.extend(
            [
                {"project_id": PROJECT, "items": None, "next_cursor": None},
                {
                    "project_id": PROJECT,
                    "items": [],
                    "next_cursor": None,
                    "secret": TOKEN,
                },
            ]
        )
        for page in variants:
            response["body"] = json.dumps(page).encode()
            assert_failure(invoke(cli, origin, "list", PROJECT), "invalid_api_response")
        before = len(requests)
        for args in (
            ("bad",),
            (PROJECT, "--limit", "0"),
            (PROJECT, "--cursor", "x" * 513),
        ):
            assert invoke(cli, origin, "list", *args).returncode != 0
        assert len(requests) == before


def test_delivery_reconcile_exact_wire_replay_shape_and_no_local_read(cli):
    with http_fixture() as (origin, response, requests):
        response["status"] = 201
        response["body"] = json.dumps(receipt()).encode()
        result = invoke(
            cli,
            origin,
            "reconcile",
            PROJECT,
            EVENT,
            "--reason",
            "Manual check",
            "--idempotency-key",
            KEY,
        )
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert json.loads(result.stdout) == receipt()
        assert len(requests) == 1 and requests[0][0] == "POST"
        assert (
            urlsplit(requests[0][1]).path
            == f"/api/v1/operations/projects/{PROJECT}/post-submit-deliveries/{EVENT}/reconcile"
        )
        assert response["commands"] == [
            ("application/json", [KEY], {"reason": "Manual check"})
        ]
        # Exact replay may observe a later child state; it is not forced back to pending.
        replay = deepcopy(receipt())
        replay["source"]["reconciliation_state"] = "acknowledged"
        replay["source"]["classification"] = "committed"
        response["body"] = json.dumps(replay).encode()
        assert (
            invoke(
                cli,
                origin,
                "reconcile",
                PROJECT,
                EVENT,
                "--reason",
                "Manual check",
                "--idempotency-key",
                KEY,
            ).returncode
            == 0
        )
        assert len(requests) == 2 and all(item[0] == "POST" for item in requests)


def test_delivery_reconcile_rejects_crossed_receipts_and_unknown_outcomes(cli):
    with http_fixture() as (origin, response, requests):
        response["status"] = 201
        variants = []
        for part, changed in (
            ("source", {"project_id": OTHER}),
            ("source", {"event_id": OTHER}),
            ("source", {"reconciliation_event_id": OTHER}),
            ("source", {"classification": "committed"}),
            ("successor", {"event_id": EVENT}),
            ("successor", {"classification": "unresolved"}),
            ("successor", {"payload_digest": TOKEN}),
        ):
            value = receipt()
            value[part].update(changed)
            variants.append(value)
        for value in variants:
            response["body"] = json.dumps(value).encode()
            result = invoke(
                cli,
                origin,
                "reconcile",
                PROJECT,
                EVENT,
                "--reason",
                "Manual check",
                "--idempotency-key",
                KEY,
            )
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        response["drop"] = True
        before = len(requests)
        result = invoke(
            cli,
            origin,
            "reconcile",
            PROJECT,
            EVENT,
            "--reason",
            "Manual check",
            "--idempotency-key",
            KEY,
        )
        assert (
            result.returncode != 0
            and json.loads(result.stderr)["error"]["outcome_unknown"] is True
        )
        assert len(requests) == before + 1
        response["drop"] = False
        response["status"] = 404
        response["body"] = json.dumps(
            canonical_error("post_submit_delivery_not_found")
        ).encode()
        command = (
            "reconcile",
            PROJECT,
            EVENT,
            "--reason",
            "Manual check",
            "--idempotency-key",
            KEY,
        )
        before = len(requests)
        denied = invoke(cli, origin, *command)
        assert_failure(denied, "post_submit_delivery_not_found")
        assert "outcome_unknown" not in json.loads(denied.stderr)["error"]
        assert len(requests) == before + 1

        # A gateway's code-shaped but incomplete 404 cannot prove no effect.
        response["body"] = json.dumps(
            {
                "error": {
                    "code": "post_submit_delivery_not_found",
                    "message": "Not found",
                }
            }
        ).encode()
        before = len(requests)
        incomplete = invoke(cli, origin, *command)
        assert_failure(incomplete, "post_submit_delivery_not_found")
        assert json.loads(incomplete.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == before + 1


def test_delivery_reconcile_invalid_arguments_do_not_send(cli):
    with http_fixture() as (origin, _response, requests):
        for args in (
            ("bad", EVENT, "--reason", "x", "--idempotency-key", KEY),
            (PROJECT, EVENT, "--reason", " x", "--idempotency-key", KEY),
            (PROJECT, EVENT, "--reason", "x\n", "--idempotency-key", KEY),
            (PROJECT, EVENT, "--reason", "x", "--idempotency-key", "bad"),
            (PROJECT, EVENT, "--idempotency-key", KEY),
        ):
            assert invoke(cli, origin, "reconcile", *args).returncode != 0
        assert not requests


def test_explicit_abandonment_binds_action_to_unknown_successor(cli):
    with http_fixture() as (origin, response, requests):
        unresolved = receipt()
        unresolved["source"]["classification"] = "unresolved"
        unresolved["successor"]["classification"] = "unresolved"
        response.update(status=201, body=json.dumps(unresolved).encode())
        args = (
            "reconcile",
            PROJECT,
            EVENT,
            "--reason",
            "Expired unresolved run",
            "--idempotency-key",
            KEY,
        )
        assert invoke(cli, origin, *args, "--abandon-unknown").returncode == 0
        assert response["commands"][0][2]["action"] == "abandon_unknown"
        assert invoke(cli, origin, *args).returncode != 0
        assert len(requests) == 2
