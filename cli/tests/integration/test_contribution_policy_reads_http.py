"""Built-process proof for the Finance list of every contribution policy version."""

import json
from urllib.parse import parse_qs, urlsplit

from test_contribution_policy_reads import VERSION, policy
from test_http_boundary import PROJECT, TOKEN, assert_failure, http_fixture

WHEN = "2026-10-02T00:00:00Z"
PUBLISHED = policy() | {"created_at": WHEN, "published_at": WHEN, "retired_at": None}
DRAFT = policy(empty=True) | {
    "contribution_policy_version_id": "018f0ebc-7966-7e8d-bc4d-1cae1e000078",
    "version_number": 2,
    "created_at": WHEN,
    "published_at": None,
    "retired_at": None,
}
RETIRED = PUBLISHED | {
    "policy_status": "retired",
    "version_status": "retired",
    "retired_at": WHEN,
}
PATH = f"/api/v1/projects/{PROJECT}/contribution-policies"


def _list(cli, origin, *flags, output="json"):
    return cli(
        origin,
        TOKEN,
        "project",
        "contribution-policy",
        "list",
        PROJECT,
        *flags,
        "-o",
        output,
    )


def _page(items, cursor=None):
    return json.dumps({"items": items, "next_cursor": cursor}).encode()


def test_version_list_preserves_body_wire_and_text(cli):
    with http_fixture() as (origin, response, requests):
        response["body"] = _page([PUBLISHED, DRAFT], "next")
        result = _list(cli, origin, "--limit", "2")
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert result.stdout.strip().encode() == response["body"]
        assert requests[-1] == ("GET", f"{PATH}?limit=2", "Bearer " + TOKEN)
        response["body"] = _page([RETIRED])
        text = _list(cli, origin, "--cursor", "next", output="text")
        assert text.returncode == 0, text.stderr
        assert parse_qs(urlsplit(requests[-1][1]).query) == {
            "limit": ["50"],
            "cursor": ["next"],
        }
        assert f"Version: {VERSION} #1 retired\n" in text.stdout
        assert f"Retired: {WHEN}\n" in text.stdout
        assert "Next cursor: —\n" in text.stdout


def test_version_list_rejects_malformed_success(cli):
    malformed = (
        [PUBLISHED | {"published_at": None}],
        [DRAFT | {"published_at": WHEN}],
        [PUBLISHED | {"retired_at": WHEN}],
        [RETIRED | {"retired_at": None}],
        [PUBLISHED | {"version_status": "superseded"}],
        [PUBLISHED | {"project_id": VERSION}],
        [PUBLISHED | {"extra": 1}],
        [{k: v for k, v in PUBLISHED.items() if k != "created_at"}],
        [PUBLISHED, PUBLISHED],
    )
    with http_fixture() as (origin, response, _requests):
        for items in malformed:
            response["body"] = _page(items)
            assert_failure(_list(cli, origin), "invalid_api_response")
        response["body"] = _page([PUBLISHED, DRAFT])
        assert_failure(_list(cli, origin, "--limit", "1"), "invalid_api_response")


def test_version_list_refuses_invalid_flags_before_any_request(cli):
    with http_fixture() as (origin, _response, requests):
        for flags in (("--limit", "0"), ("--limit", "101"), ("--cursor", "")):
            assert_failure(_list(cli, origin, *flags), "invalid_arguments", 2)
        bad = cli(
            origin,
            TOKEN,
            "project",
            "contribution-policy",
            "list",
            "nope",
            "-o",
            "json",
        )
        assert_failure(bad, "invalid_arguments", 2)
        assert requests == []
