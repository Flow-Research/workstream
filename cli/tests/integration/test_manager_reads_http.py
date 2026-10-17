"""Built-process proof for the Project Manager's project-wide work reads."""

import json
from urllib.parse import parse_qs, urlsplit

from test_contributor_reads_http import (
    ASSIGNMENT_ROW,
    SUBMISSION_ROW,
    SUMMARY_BODY,
    WHEN,
)
from test_http_boundary import PROJECT, TOKEN, assert_failure, http_fixture
from test_task_http_boundary import TASK

ACTOR = "018f0ebc-7966-7e8d-bc4d-1cae1e000020"
BATCH = "018f0ebc-7966-7e8d-bc4d-1cae1e000021"
SOURCE = "018f0ebc-7966-7e8d-bc4d-1cae1e000022"
STATUSES = (
    "draft",
    "screening",
    "ready",
    "claimed",
    "in_progress",
    "submitted",
    "evaluation_pending",
    "review_pending",
    "needs_revision",
    "accepted",
)
TASK_COUNTS = dict.fromkeys(STATUSES, 0) | {"draft": 2, "ready": 1}
PROJECT_SUBMISSION = SUBMISSION_ROW | {"submitter_actor_id": ACTOR}
PROJECT_ASSIGNMENT = ASSIGNMENT_ROW | {"contributor_actor_id": ACTOR}
BATCH_ROW = {
    "batch_id": BATCH,
    "source_id": SOURCE,
    "label": "Pilot import",
    "sha256": "sha256:" + "c" * 64,
    "byte_count": 512,
    "row_count": 3,
    "state": "committed",
    "created_at": WHEN,
    "committed_at": WHEN,
    "task_counts": TASK_COUNTS,
}
PROJECT_SUMMARY = {
    "project_id": PROJECT,
    "tasks": TASK_COUNTS,
    "assignments": SUMMARY_BODY["assignments"],
    "submissions": SUMMARY_BODY["submissions"],
    "acceptance_rate": 0.0,
    "checker_infrastructure_failures": 2,
    "award_totals": None,
}
READS = (
    ("submissions", "/submissions", PROJECT_SUBMISSION),
    ("assignments", "/assignments", PROJECT_ASSIGNMENT),
    ("import-batches", "/task-import-batches", BATCH_ROW),
)


def _page(row, cursor=None):
    return json.dumps({"items": [row], "next_cursor": cursor}).encode()


def test_project_pages_preserve_bodies_and_wire(cli):
    with http_fixture() as (origin, response, requests):
        for command, suffix, row in READS:
            response["body"] = _page(row, "next")
            result = cli(
                origin, TOKEN, "project", command, PROJECT, "--limit", "1", "-o", "json"
            )
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert result.stdout.strip().encode() == response["body"]
            assert requests[-1] == (
                "GET",
                f"/api/v1/projects/{PROJECT}{suffix}?limit=1",
                "Bearer " + TOKEN,
            )
            text = cli(origin, TOKEN, "project", command, PROJECT, "--cursor", "next")
            assert text.returncode == 0 and text.stderr == "", text.stderr
            assert "Next cursor: next\n" in text.stdout
        response["body"] = _page(PROJECT_ASSIGNMENT)
        text = cli(origin, TOKEN, "project", "assignments", PROJECT).stdout
        assert f"Contributor: {ACTOR}\n" in text and "Next action: revise\n" in text
        response["body"] = _page(BATCH_ROW)
        text = cli(origin, TOKEN, "project", "import-batches", PROJECT).stdout
        assert "State: committed\n" in text and "2 draft, 0 screening, 1 ready" in text


def test_project_filters_reach_the_query(cli):
    with http_fixture() as (origin, response, requests):
        response["body"] = _page(PROJECT_SUBMISSION)
        result = cli(
            origin,
            TOKEN,
            "project",
            "submissions",
            PROJECT,
            "--task",
            TASK,
            "--submitter",
            ACTOR,
            "--status",
            "needs_revision",
            "--updated-since",
            WHEN,
            "-o",
            "json",
        )
        assert result.returncode == 0, result.stderr
        assert parse_qs(urlsplit(requests[-1][1]).query) == {
            "limit": ["50"],
            "task_id": [TASK],
            "submitter_actor_id": [ACTOR],
            "status": ["needs_revision"],
            "updated_since": [WHEN],
        }
        response["body"] = _page(PROJECT_ASSIGNMENT)
        result = cli(
            origin, TOKEN, "project", "assignments", PROJECT, "--state", "active"
        )
        assert result.returncode == 0, result.stderr
        assert parse_qs(urlsplit(requests[-1][1]).query) == {
            "limit": ["50"],
            "state": ["active"],
        }


def test_summary_distinguishes_hidden_and_visible_award_totals(cli):
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(PROJECT_SUMMARY).encode()
        result = cli(origin, TOKEN, "project", "summary", PROJECT)
        assert result.returncode == 0, result.stderr
        assert "Acceptance rate: 0.0000\n" in result.stdout
        assert "Checker infrastructure failures: 2\n" in result.stdout
        assert "Award totals: not shown" in result.stdout
        assert requests[-1][1] == f"/api/v1/projects/{PROJECT}/summary"
        visible = PROJECT_SUMMARY | {
            "award_totals": [
                {"instrument": "money", "unit": "USD", "quantity": "12.50"}
            ]
        }
        response["body"] = json.dumps(visible).encode()
        result = cli(origin, TOKEN, "project", "summary", PROJECT, "-o", "json")
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == visible
        text = cli(origin, TOKEN, "project", "summary", PROJECT).stdout
        assert "Award total: money USD 12.50\n" in text


def test_project_reads_reject_malformed_success(cli):
    other_project = "018f0ebc-7966-7e8d-bc4d-1cae1e000099"
    pages = (
        ("submissions", PROJECT_SUBMISSION | {"submitter_actor_id": "nobody"}),
        ("submissions", SUBMISSION_ROW),
        ("submissions", PROJECT_SUBMISSION | {"project_id": other_project}),
        ("submissions", PROJECT_SUBMISSION | {"extra": 1}),
        ("assignments", ASSIGNMENT_ROW),
        ("assignments", PROJECT_ASSIGNMENT | {"next_action": "celebrate"}),
        ("import-batches", BATCH_ROW | {"state": "finished"}),
        ("import-batches", BATCH_ROW | {"committed_at": None}),
        ("import-batches", BATCH_ROW | {"row_count": 4}),
        (
            "import-batches",
            BATCH_ROW
            | {"task_counts": {k: v for k, v in TASK_COUNTS.items() if k != "draft"}},
        ),
    )
    with http_fixture() as (origin, response, _requests):
        for command, row in pages:
            response["body"] = _page(row)
            assert_failure(
                cli(origin, TOKEN, "project", command, PROJECT, "-o", "json"),
                "invalid_api_response",
            )
        decided_free = dict.fromkeys(SUMMARY_BODY["submissions"], 0)
        for body in (
            PROJECT_SUMMARY | {"acceptance_rate": 1.5},
            PROJECT_SUMMARY | {"submissions": decided_free},
            PROJECT_SUMMARY | {"project_id": other_project},
            PROJECT_SUMMARY | {"tasks": TASK_COUNTS | {"retired": 0}},
            {k: v for k, v in PROJECT_SUMMARY.items() if k != "award_totals"},
            PROJECT_SUMMARY
            | {
                "award_totals": [
                    {"instrument": "money", "unit": "USD", "quantity": "1"},
                    {"instrument": "money", "unit": "USD", "quantity": "2"},
                ]
            },
        ):
            response["body"] = json.dumps(body).encode()
            assert_failure(
                cli(origin, TOKEN, "project", "summary", PROJECT, "-o", "json"),
                "invalid_api_response",
            )


def test_project_reads_refuse_invalid_flags_before_any_request(cli):
    with http_fixture() as (origin, _response, requests):
        for args in (
            ("submissions", "not-a-uuid"),
            ("submissions", PROJECT, "--submitter", "someone"),
            ("submissions", PROJECT, "--status", "finished"),
            ("submissions", PROJECT, "--updated-since", "yesterday"),
            ("assignments", PROJECT, "--state", "open"),
            ("import-batches", PROJECT, "--limit", "0"),
            ("summary", "not-a-uuid"),
        ):
            assert_failure(
                cli(origin, TOKEN, "project", *args, "-o", "json"),
                "invalid_arguments",
                2,
            )
        assert requests == []
