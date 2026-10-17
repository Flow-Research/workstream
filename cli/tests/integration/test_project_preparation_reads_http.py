"""Built-process proof for a Project Manager's project-wide preparation list."""

import json
from urllib.parse import parse_qs, urlsplit

from test_contributor_reads_http import PREPARATION_ROW
from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture

ROW = PREPARATION_ROW | {"actor_profile_id": ACTOR}
FAILED = ROW | {
    "outcome": "failed",
    "state": "checks_failed",
    "storage_status": None,
    "submission_id": None,
}
PATH = f"/api/v1/projects/{PROJECT}/submission-bundle-preparations"


def _list(cli, origin, *flags, output="json"):
    return cli(origin, TOKEN, "project", "preparations", PROJECT, *flags, "-o", output)


def _page(items, cursor=None):
    return json.dumps({"items": items, "next_cursor": cursor}).encode()


def test_preparation_list_preserves_body_wire_and_text(cli):
    with http_fixture() as (origin, response, requests):
        response["body"] = _page([ROW], "next")
        result = _list(cli, origin, "--limit", "1")
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert result.stdout.strip().encode() == response["body"]
        assert requests[-1] == ("GET", f"{PATH}?limit=1", "Bearer " + TOKEN)
        response["body"] = _page([FAILED])
        text = _list(cli, origin, "--outcome", "failed", "--cursor", "c", output="text")
        assert text.returncode == 0, text.stderr
        assert parse_qs(urlsplit(requests[-1][1]).query) == {
            "limit": ["50"],
            "outcome": ["failed"],
            "cursor": ["c"],
        }
        assert f"Contributor: {ACTOR}\n" in text.stdout
        assert "Outcome: failed\nState: checks_failed\n" in text.stdout
        assert "Finding counts: 1 blocking, 0 warning, 2 coverage incomplete\n" in (
            text.stdout
        )


def test_preparation_list_rejects_findings_and_malformed_success(cli):
    malformed = (
        [ROW | {"findings": []}],
        [PREPARATION_ROW],
        [ROW | {"actor_profile_id": "someone"}],
        [ROW | {"outcome": "blocked"}],
        [ROW, ROW],
    )
    with http_fixture() as (origin, response, _requests):
        for items in malformed:
            response["body"] = _page(items)
            assert_failure(_list(cli, origin), "invalid_api_response")
        # The page must hold only the requested outcome.
        response["body"] = _page([ROW])
        assert_failure(
            _list(cli, origin, "--outcome", "failed"), "invalid_api_response"
        )


def test_preparation_list_refuses_invalid_flags_before_any_request(cli):
    with http_fixture() as (origin, _response, requests):
        for flags in (("--outcome", "checks_failed"), ("--limit", "0")):
            assert_failure(_list(cli, origin, *flags), "invalid_arguments", 2)
        bad = cli(origin, TOKEN, "project", "preparations", "nope", "-o", "json")
        assert_failure(bad, "invalid_arguments", 2)
        assert requests == []
