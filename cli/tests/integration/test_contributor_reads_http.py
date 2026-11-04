"""Built-process proof for the caller's own-work reads and manager task filters."""

from copy import deepcopy
import json
from urllib.parse import parse_qs, urlsplit

from test_contributor_task_http import COMPENSATION
from test_http_boundary import PROJECT, TOKEN, assert_failure, http_fixture
from test_submission_http import INTAKE_FEEDBACK
from test_task_context_http import REVISION_CONTEXT
from test_task_http_boundary import SUMMARY, TASK

ASSIGNMENT = "018f0ebc-7966-7e8d-bc4d-1cae1e000010"
SUBMISSION = "018f0ebc-7966-7e8d-bc4d-1cae1e000011"
PREPARATION = "018f0ebc-7966-7e8d-bc4d-1cae1e000012"
GUIDE = "018f0ebc-7966-7e8d-bc4d-1cae1e000013"
WHEN = "2026-10-02T00:00:00Z"
LATEST = {
    "submission_id": SUBMISSION,
    "version": 1,
    "status": "needs_revision",
    "status_reason": None,
    "submitted_at": WHEN,
    "decided_at": WHEN,
}
ASSIGNMENT_ROW = {
    "assignment_id": ASSIGNMENT,
    "project_id": PROJECT,
    "task_id": TASK,
    "title": "Work",
    "state": "active",
    "assignment_status": "active",
    "task_status": "needs_revision",
    "claimed_at": WHEN,
    "started_at": WHEN,
    "released_at": None,
    "locked_guide_version": "v1",
    "compensation": COMPENSATION,
    "latest_submission": LATEST,
    "revision": REVISION_CONTEXT,
    "next_action": "revise",
    "updated_at": WHEN,
}
COUNTS = {"blocking": 1, "warning": 0, "coverage_incomplete": 2}
SUBMISSION_ROW = {
    "submission_id": SUBMISSION,
    "project_id": PROJECT,
    "task_id": TASK,
    "title": "Work",
    "version": 1,
    "status": "needs_revision",
    "status_reason": None,
    "submitted_at": WHEN,
    "decided_at": WHEN,
    "finding_counts": COUNTS,
    "updated_at": WHEN,
}
PREPARATION_ROW = {
    "preparation_id": PREPARATION,
    "task_id": TASK,
    "assignment_id": ASSIGNMENT,
    "outcome": "passed",
    "state": "submitted",
    "storage_status": "observed_confirmed",
    "infrastructure_failure_code": None,
    "archive_sha256": "sha256:" + "a" * 64,
    "archive_byte_count": 2048,
    "finding_counts": COUNTS,
    "admission_id": None,
    "submission_id": SUBMISSION,
    "created_at": WHEN,
    "completed_at": WHEN,
}
PROJECT_ROW = {
    "project_id": PROJECT,
    "name": "Project",
    "status": "active",
    "admin_roles": [],
    "project_roles": ["submitter"],
    "active_guide": {"guide_id": GUIDE, "version": "v1"},
}
SUMMARY_BODY = {
    "project_id": None,
    "assignments": {"active": 1, "closed": 0},
    "submissions": {
        "evaluation_pending": 0,
        "review_pending": 0,
        "accepted": 0,
        "needs_revision": 1,
        "rejected": 0,
    },
    "award_totals": [{"instrument": "project_points", "unit": "PTS", "quantity": "7"}],
}
READS = (
    (("me", "projects"), "/api/v1/actors/me/projects", PROJECT_ROW),
    (("me", "assignments"), "/api/v1/actors/me/assignments", ASSIGNMENT_ROW),
    (("me", "submissions"), "/api/v1/actors/me/submissions", SUBMISSION_ROW),
    (
        ("task", "preparations", TASK),
        f"/api/v1/tasks/{TASK}/submission-bundle-preparations",
        PREPARATION_ROW,
    ),
)


def _page(row, cursor=None):
    return json.dumps({"items": [row], "next_cursor": cursor}).encode()


def test_own_work_pages_preserve_bodies_and_wire(cli):
    with http_fixture() as (origin, response, requests):
        for args, path, row in READS:
            response["body"] = _page(row, "next")
            result = cli(origin, TOKEN, *args, "--limit", "1", "-o", "json")
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert result.stdout.strip().encode() == response["body"]
            assert requests[-1] == ("GET", f"{path}?limit=1", "Bearer " + TOKEN)
            text = cli(origin, TOKEN, *args, "--limit", "1", "--cursor", "next")
            assert text.returncode == 0 and text.stderr == ""
            assert "Next cursor: next\n" in text.stdout
        response["body"] = _page(ASSIGNMENT_ROW)
        text = cli(origin, TOKEN, "me", "assignments").stdout
        assert "Next action: revise\n" in text
        assert (
            "Revision: round 1 of 2, kept, ready, deadline 2026-10-15T10:00:00Z\n"
            in text
        )


def test_assignment_revision_is_the_work_context_projection(cli):
    paused = deepcopy(REVISION_CONTEXT) | {
        "max_revision_rounds": 0,
        "next_revision_round": 0,
        "deadline_at": None,
        "clock_state": "paused",
        "remaining_microseconds": 3_600_000_000,
        "outcome": "blocked",
        "disposition": "context_blocked",
    }
    exhausted = ASSIGNMENT_ROW | {
        "state": "closed",
        "assignment_status": "revision_exhausted",
        "task_status": None,
        "revision": None,
        "next_action": "none",
    }
    with http_fixture() as (origin, response, _requests):
        for row in (ASSIGNMENT_ROW | {"revision": paused}, exhausted):
            response["body"] = _page(row)
            result = cli(origin, TOKEN, "me", "assignments", "-o", "json")
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert result.stdout.strip().encode() == response["body"]
        response["body"] = _page(ASSIGNMENT_ROW | {"revision": paused})
        text = cli(origin, TOKEN, "me", "assignments")
        assert text.returncode == 0, text.stderr
        assert "Revision: round 0 of 0, blocked, context_blocked, clock paused\n" in (
            text.stdout
        )


def test_own_work_filters_reach_the_query(cli):
    with http_fixture() as (origin, response, requests):
        response["body"] = _page(SUBMISSION_ROW)
        result = cli(
            origin,
            TOKEN,
            "me",
            "submissions",
            "--project",
            PROJECT,
            "--task",
            TASK,
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
            "project_id": [PROJECT],
            "task_id": [TASK],
            "status": ["needs_revision"],
            "updated_since": [WHEN],
        }
        response["body"] = _page(ASSIGNMENT_ROW)
        result = cli(
            origin, TOKEN, "me", "assignments", "--state", "active", "-o", "json"
        )
        assert result.returncode == 0, result.stderr
        assert parse_qs(urlsplit(requests[-1][1]).query) == {
            "limit": ["50"],
            "state": ["active"],
        }


def test_summary_and_preparation_detail_decode(cli):
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(SUMMARY_BODY).encode()
        result = cli(origin, TOKEN, "me", "summary")
        assert result.returncode == 0, result.stderr
        assert "Award total: project_points PTS 7\n" in result.stdout
        assert requests[-1][1] == "/api/v1/actors/me/summary"
        detail = PREPARATION_ROW | {"findings": INTAKE_FEEDBACK}
        response["body"] = json.dumps(detail).encode()
        result = cli(
            origin, TOKEN, "task", "preparation", TASK, PREPARATION, "-o", "json"
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == detail
        assert requests[-1][1] == (
            f"/api/v1/tasks/{TASK}/submission-bundle-preparations/{PREPARATION}"
        )


def test_own_work_reads_reject_malformed_success(cli):
    malformed = (
        (("me", "assignments"), ASSIGNMENT_ROW | {"state": "closed"}),
        (("me", "assignments"), ASSIGNMENT_ROW | {"next_action": "celebrate"}),
        (("me", "assignments"), ASSIGNMENT_ROW | {"next_action": "start"}),
        (("me", "assignments"), ASSIGNMENT_ROW | {"task_status": "claimed"}),
        (("me", "assignments"), ASSIGNMENT_ROW | {"task_status": "invented"}),
        (
            ("me", "assignments"),
            ASSIGNMENT_ROW | {"revision": REVISION_CONTEXT | {"clock_state": "paused"}},
        ),
        (
            ("me", "assignments"),
            ASSIGNMENT_ROW
            | {
                "revision": {
                    key: REVISION_CONTEXT[key]
                    for key in (
                        "next_revision_round",
                        "max_revision_rounds",
                        "deadline_at",
                        "outcome",
                    )
                }
            },
        ),
        (("me", "submissions"), SUBMISSION_ROW | {"decided_at": None}),
        (("me", "projects"), PROJECT_ROW | {"project_roles": ["owner"]}),
        (("task", "preparations", TASK), PREPARATION_ROW | {"submission_id": None}),
        (("task", "preparations", TASK), PREPARATION_ROW | {"extra": 1}),
    )
    with http_fixture() as (origin, response, _requests):
        for args, row in malformed:
            response["body"] = _page(row)
            assert_failure(
                cli(origin, TOKEN, *args, "-o", "json"), "invalid_api_response"
            )
        for findings in ([None], [{"arbitrary": True}]):
            response["body"] = json.dumps(
                PREPARATION_ROW | {"findings": findings}
            ).encode()
            assert_failure(
                cli(
                    origin,
                    TOKEN,
                    "task",
                    "preparation",
                    TASK,
                    PREPARATION,
                    "-o",
                    "json",
                ),
                "invalid_api_response",
            )
        response["body"] = json.dumps(SUMMARY_BODY | {"project_id": PROJECT}).encode()
        assert_failure(
            cli(origin, TOKEN, "me", "summary", "-o", "json"), "invalid_api_response"
        )


def test_own_work_reads_refuse_invalid_flags_before_any_request(cli):
    with http_fixture() as (origin, _response, requests):
        for args in (
            ("me", "assignments", "--state", "open"),
            ("me", "submissions", "--status", "finished"),
            ("me", "submissions", "--updated-since", "yesterday"),
            ("me", "assignments", "--project", "not-a-uuid"),
            ("me", "projects", "--limit", "0"),
            ("task", "preparation", TASK, "not-a-uuid"),
        ):
            assert_failure(
                cli(origin, TOKEN, *args, "-o", "json"), "invalid_arguments", 2
            )
        assert requests == []


def test_manager_task_filters_reach_the_query_and_bind_status(cli):
    with http_fixture() as (origin, response, requests):
        page = {
            "project_id": PROJECT,
            "items": [SUMMARY | {"status": "ready"}],
            "next_cursor": None,
        }
        response["body"] = json.dumps(page).encode()
        result = cli(
            origin,
            TOKEN,
            "project",
            "tasks",
            PROJECT,
            "--status",
            "ready",
            "--assignee",
            TASK,
            "--import-batch",
            ASSIGNMENT,
            "--updated-since",
            WHEN,
            "-o",
            "json",
        )
        assert result.returncode == 0, result.stderr
        assert parse_qs(urlsplit(requests[-1][1]).query) == {
            "limit": ["50"],
            "status": ["ready"],
            "assignee_actor_id": [TASK],
            "import_batch_id": [ASSIGNMENT],
            "updated_since": [WHEN],
        }
        page["items"] = [SUMMARY | {"status": "draft"}]
        response["body"] = json.dumps(page).encode()
        mismatch = cli(
            origin,
            TOKEN,
            "project",
            "tasks",
            PROJECT,
            "--status",
            "ready",
            "-o",
            "json",
        )
        assert_failure(mismatch, "invalid_api_response")
        count = len(requests)
        bad = cli(
            origin,
            TOKEN,
            "project",
            "tasks",
            PROJECT,
            "--status",
            "finished",
            "-o",
            "json",
        )
        assert_failure(bad, "invalid_arguments", 2)
        assert len(requests) == count
