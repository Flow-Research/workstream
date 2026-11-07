"""Explicit initial guide requests through the built CLI, without implicit retries."""

import json
from uuid import UUID

import pytest

from http2_fixture import goaway_fixture
from test_contributor_task_mutations import KEY, canonical_error
from test_guide_create_http import GUIDE, SETUP
from test_guide_post_approval_http import unknown
from test_guide_post_policy_http import LARGE
from test_guide_proposal_http import OTHER
from test_http_boundary import PROJECT, TOKEN, http_fixture

COMMANDS = (("assist", "setup"), ("compile-requirements", "requirements/compile"))


def receipt():
    return {
        "operation_id": OTHER,
        "setup_run_id": SETUP,
        "setup_generation": LARGE,
        "status": "enqueue_failed",
    }


def invoke(
    cli,
    origin,
    command,
    *,
    selectors=(PROJECT, GUIDE),
    key=KEY,
    token=TOKEN,
    output="json",
    **kwargs,
):
    return cli(
        origin,
        token,
        "project",
        "guide",
        command,
        *selectors,
        "--idempotency-key",
        key,
        "-o",
        output,
        **kwargs,
    )


@pytest.mark.parametrize(("command", "suffix"), COMMANDS)
def test_guide_dispatch_exact_bodyless_wire_and_manual_replay(cli, command, suffix):
    with http_fixture() as (origin, response, requests):
        response.update(status=202, body=json.dumps(receipt()).encode())
        selectors = (UUID(PROJECT).hex, UUID(GUIDE).hex)
        key = UUID(KEY).hex
        for status in (
            "enqueue_failed",
            "queued",
            "policy_draft_ready",
            "server diagnostic\n\x1b[31m",
        ):
            value = receipt() | {"status": status}
            response["body"] = json.dumps(value).encode()
            result = invoke(cli, origin, command, selectors=selectors, key=key)
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert json.loads(result.stdout) == value
            assert requests[-1] == (
                "POST",
                f"/api/v1/projects/{selectors[0]}/guides/{selectors[1]}/{suffix}",
                "Bearer " + TOKEN,
            )
            assert response["raw_commands"][-1] == b""
            assert response["commands"][-1][1] == [key]
        text = invoke(cli, origin, command, output="text")
        assert text.returncode == 0 and "not completion" in text.stdout
        assert "\x1b" not in text.stdout
        assert len(requests) == 5


@pytest.mark.parametrize(("command", "suffix"), COMMANDS)
def test_guide_dispatch_invalid_arguments_never_request(cli, command, suffix):
    with http_fixture() as (origin, _response, requests):
        for selectors, key in (
            (("../project", GUIDE), KEY),
            ((PROJECT, "../guide"), KEY),
            ((PROJECT, GUIDE), ""),
            ((PROJECT, GUIDE), "not-uuid"),
        ):
            result = invoke(cli, origin, command, selectors=selectors, key=key)
            assert result.returncode == 2 and result.stdout == ""
        assert requests == []


@pytest.mark.parametrize(("command", "suffix"), COMMANDS)
def test_guide_dispatch_strict_receipts_and_credential_reflection(cli, command, suffix):
    base = receipt()
    variants = [base | {"extra": True}]
    for field in base:
        variants += [
            {k: v for k, v in base.items() if k != field},
            base | {field: None},
        ]
    variants += [
        base | {"operation_id": "invalid"},
        base | {"setup_run_id": "invalid"},
        base | {"setup_generation": 0},
        base | {"setup_generation": -1},
        base | {"setup_generation": 1.5},
        base | {"setup_generation": "1"},
        base | {"status": 4},
        base | {"status": TOKEN},
    ]
    with http_fixture() as (origin, response, requests):
        response["status"] = 202
        for value in variants:
            response["body"] = json.dumps(value).encode()
            unknown(invoke(cli, origin, command))
        response["body"] = ('{"status":"queued",' + json.dumps(base)[1:]).encode()
        unknown(invoke(cli, origin, command))
        response["body"] = json.dumps(base).encode()
        for token in (UUID(OTHER).hex, UUID(SETUP).hex):
            unknown(invoke(cli, origin, command, token=token))
        assert len(requests) == len(variants) + 3


@pytest.mark.parametrize(("command", "suffix"), COMMANDS)
def test_guide_dispatch_known_denials_uncertain_responses_and_no_retry(
    cli, tmp_path, command, suffix
):
    with http_fixture() as (origin, response, requests):
        for status in (403, 404, 409, 422):
            response.update(
                status=status, body=json.dumps(canonical_error("not_allowed")).encode()
            )
            result = invoke(cli, origin, command)
            error = json.loads(result.stderr)["error"]
            assert result.returncode == 1 and result.stdout == ""
            assert error["status"] == status and "outcome_unknown" not in error
        for status, body, headers, drop, code in (
            (
                200,
                json.dumps(receipt()).encode(),
                {"Content-Type": "application/json"},
                False,
                "api_error",
            ),
            (202, b"{}", {"Content-Type": "text/plain"}, False, "invalid_api_response"),
            (
                202,
                b" " * 65537,
                {"Content-Type": "application/json"},
                False,
                "invalid_api_response",
            ),
            (500, b"failure", {"Content-Type": "text/plain"}, False, "api_error"),
            (302, b"", {"Location": origin + "/sink"}, False, "redirect_refused"),
            (
                202,
                b"",
                {"Content-Type": "application/json"},
                True,
                "service_unavailable",
            ),
        ):
            response.update(status=status, body=body, headers=headers, drop=drop)
            before = len(requests)
            unknown(invoke(cli, origin, command), code)
            assert len(requests) == before + 1
        result = invoke(cli, origin, command, output="text")
        assert "unchanged command, project, guide and idempotency key" in result.stderr
        assert not any(request[1] == "/sink" for request in requests)
    with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
        unknown(invoke(cli, origin, command, extra_env=env), "service_unavailable")
        assert bodies == [b""] and connections == ["h2"]
