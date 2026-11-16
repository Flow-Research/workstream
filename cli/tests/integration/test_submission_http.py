"""Submission commands through the built process and hostile HTTP peers."""

import copy
import json
import os
from urllib.parse import parse_qs, urlsplit

from test_http_boundary import TOKEN, assert_failure, http_fixture
from http2_fixture import goaway_fixture

TASK = "018f0ebc-7966-7e8d-bc4d-1cae1e000010"
ASSIGNMENT = "018f0ebc-7966-7e8d-bc4d-1cae1e000011"
KEY = "018f0ebc-7966-7e8d-bc4d-1cae1e000012"
OPERATION = "018f0ebc-7966-7e8d-bc4d-1cae1e000013"
SUBMISSION = "018f0ebc-7966-7e8d-bc4d-1cae1e000015"
RUN = "018f0ebc-7966-7e8d-bc4d-1cae1e000016"
REVISION_PREPARATION = "018f0ebc-7966-7e8d-bc4d-1cae1e000017"
REVISION_DIGEST = "sha256:" + "a" * 64
HISTORY = {
    "id": SUBMISSION,
    "task_id": TASK,
    "version": 1,
    "status": "evaluation_pending",
    "status_reason": None,
    "summary": "Work complete",
    "submitted_at": "2026-10-14T10:00:00Z",
    "decided_at": None,
    "finding_counts": {"blocking": 0, "warning": 0, "coverage_incomplete": 0},
    "locked_at": None,
    "supersedes_submission_id": None,
    "evidence_items": [],
}
CHECKER = {
    "id": RUN,
    "task_id": TASK,
    "submission_id": SUBMISSION,
    "submission_version": 1,
    "status": "completed",
    "attempt_number": 1,
    "supersedes_checker_run_id": None,
    "is_current_for_submission": True,
    "created_at": "2026-10-14T10:00:00Z",
    "completed_at": "2026-10-14T10:01:00Z",
    "results": [
        {
            "id": KEY,
            "checker_name": "quality",
            "check_id": "quality.output",
            "path": "src/out.txt",
            "line": 4,
            "status": "failed",
            "severity": "error",
            "worker_message": "Fix \u202eunsafe\x1b text",
            "worker_suggested_fix": "Correct the output",
        }
    ],
}


def submit_args(path):
    return (
        "task",
        "submit",
        TASK,
        "--assignment",
        ASSIGNMENT,
        "--file",
        str(path),
        "--idempotency-key",
        KEY,
        "-o",
        "json",
    )


INTAKE_FEEDBACK = [
    {
        "source": "workstream_default",
        "check_id": "archive_safety",
        "status": "passed",
        "failure_code": None,
        "finding_count": 0,
    },
    {
        "source": "workstream_default",
        "status": "warning",
        "warning_code": "submission_summary_missing",
    },
    {
        "source": "project_external_checker",
        "requirement_id": "quality",
        "registry_entry_id": RUN,
        "registry_entry_digest": "sha256:" + "a" * 64,
        "status": "passed",
        "findings": [
            {
                "check_id": "coverage.files",
                "code": "coverage.unreadable",
                "level": "coverage_incomplete",
                "message": "One file was not evaluated.",
                "path": "results/vendor.bin",
                "line": None,
            }
        ],
    },
]


def acceptance(replayed=False):
    return {
        "operation_id": OPERATION,
        "task_id": TASK,
        "assignment_id": ASSIGNMENT,
        "status": "accepted",
        "accepted_at": "2026-10-14T10:00:00Z",
        "task_status_at_acceptance": "evaluation_pending",
        "processing_stage_at_acceptance": "finalization_pending",
        "replayed": replayed,
        "pre_submission_results": INTAKE_FEEDBACK,
    }


def respond(response, value, status=200):
    response.update(status=status, body=json.dumps(value, ensure_ascii=False).encode())


def test_explicit_submit_replay_preserves_packet_and_bytes(cli, tmp_path):
    path = tmp_path / "submission.zip"
    path.write_bytes(b"PK\x03\x04exact-archive")
    packet = ("--summary", "Completed work", "--attestation", "")
    with http_fixture() as (origin, response, requests):
        for replayed in (False, True):
            respond(response, acceptance(replayed), 202)
            result = cli(origin, TOKEN, *submit_args(path), *packet)
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout) == acceptance(replayed)
        assert len(requests) == 2  # Only caller-requested replay.
        assert response["raw_commands"] == [path.read_bytes()] * 2
        for headers in response["request_headers"]:
            assert headers["X-Task-Assignment-Id"] == ASSIGNMENT
            assert headers["X-Submission-Summary"] == "Completed work"
            assert headers["X-Contributor-Attestation"] == ""
            assert headers["Idempotency-Key"] == KEY
            assert headers["Content-Type"] == "application/zip"
        assert (
            requests
            == [("POST", f"/api/v1/tasks/{TASK}/submissions", "Bearer " + TOKEN)] * 2
        )


def test_accepted_submission_shows_nonblocking_intake_feedback(cli, tmp_path):
    path = tmp_path / "submission.zip"
    path.write_bytes(b"PK\x03\x04feedback")
    human = submit_args(path)[:-2]
    with http_fixture() as (origin, response, requests):
        respond(response, acceptance(), 202)
        result = cli(origin, TOKEN, *human)
        assert result.returncode == 0, result.stderr
        receipt_line = result.stdout.splitlines()[0]
        assert receipt_line.startswith("Submission accepted for evaluation")
        assert "pre_submission_results" not in receipt_line
        assert "Intake feedback: warning submission_summary_missing" in result.stdout
        assert (
            "Intake feedback: coverage_incomplete coverage.files results/vendor.bin: "
            "One file was not evaluated." in result.stdout
        )
        # An accepted receipt cannot carry blocking results or omit its feedback.
        blocked_check = copy.deepcopy(INTAKE_FEEDBACK)
        blocked_check[0] |= {
            "status": "failed",
            "failure_code": "secret_detected",
            "finding_count": 1,
        }
        error_finding = copy.deepcopy(INTAKE_FEEDBACK)
        error_finding[2]["findings"][0]["level"] = "error"
        failed_member = copy.deepcopy(INTAKE_FEEDBACK)
        failed_member[2]["status"] = "failed"
        missing = acceptance()
        missing.pop("pre_submission_results")
        for invalid in (
            acceptance() | {"pre_submission_results": blocked_check},
            acceptance() | {"pre_submission_results": error_finding},
            acceptance() | {"pre_submission_results": failed_member},
            acceptance() | {"pre_submission_results": None},
            missing,
        ):
            respond(response, invalid, 202)
            assert_failure(
                cli(origin, TOKEN, *submit_args(path)), "invalid_api_response"
            )
        assert len(requests) == 6


def test_revision_submit_requires_and_replays_exact_acknowledgement_headers(
    cli, tmp_path
):
    path = tmp_path / "revision.zip"
    path.write_bytes(b"PK\x03\x04revision")
    pair = (
        "--revision-preparation-id",
        REVISION_PREPARATION,
        "--revision-preparation-sha256",
        REVISION_DIGEST,
    )
    with http_fixture() as (origin, response, requests):
        for args in (
            ("--predecessor", SUBMISSION),
            pair,
            (
                "--predecessor",
                SUBMISSION,
                "--revision-preparation-id",
                REVISION_PREPARATION,
            ),
            (
                "--predecessor",
                SUBMISSION,
                "--revision-preparation-sha256",
                REVISION_DIGEST,
            ),
            ("--predecessor", SUBMISSION, *pair[:-1], "sha256:" + "A" * 64),
        ):
            assert_failure(
                cli(origin, TOKEN, *submit_args(path), *args), "invalid_arguments", 2
            )
        assert requests == []
        respond(response, acceptance(), 202)
        for _ in range(2):
            result = cli(
                origin, TOKEN, *submit_args(path), "--predecessor", SUBMISSION, *pair
            )
            assert result.returncode == 0, result.stderr
        assert len(requests) == 2
        for headers in response["request_headers"]:
            assert headers["X-Predecessor-Submission-Id"] == SUBMISSION
            assert headers["X-Revision-Preparation-Id"] == REVISION_PREPARATION
            assert headers["X-Revision-Preparation-Sha256"] == REVISION_DIGEST


def test_submit_rejects_untransportable_packet_before_request(cli, tmp_path):
    path = tmp_path / "submission.zip"
    path.write_bytes(b"zip")
    with http_fixture() as (origin, _, requests):
        for summary in ("é", "line\nbreak", " leading", "trailing ", "x" * 65537):
            result = cli(origin, TOKEN, *submit_args(path), "--summary", summary)
            assert_failure(result, "invalid_arguments", 2)
        assert requests == []


def test_submit_detects_file_change_and_never_confirms_success(cli, tmp_path):
    path = tmp_path / "submission.zip"
    for changed in (b"original-appended", b"modified"):
        path.write_bytes(b"original")
        with http_fixture() as (origin, response, requests):
            respond(response, acceptance(), 202)
            response["after_body"] = lambda: path.write_bytes(changed)
            result = cli(origin, TOKEN, *submit_args(path))
            assert_failure(result, "submission_source_changed")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
            assert len(requests) == 1


def test_submission_rejects_empty_nonregular_and_oversized_sources_without_request(
    cli, tmp_path
):
    empty, oversized, pipe = (
        tmp_path / name for name in ("empty.zip", "large.zip", "pipe.zip")
    )
    empty.touch()
    with oversized.open("wb") as stream:
        stream.truncate(500 * 1024 * 1024 + 1)  # Sparse; never allocates a huge upload.
    os.mkfifo(pipe)
    with http_fixture() as (origin, _, requests):
        for path in (empty, tmp_path, pipe, oversized):
            assert_failure(
                cli(origin, TOKEN, *submit_args(path)), "invalid_arguments", 2
            )
        assert requests == []


def test_submission_uncertain_responses_are_not_retried(cli, tmp_path):
    path = tmp_path / "submission.zip"
    path.write_bytes(b"zip")
    with http_fixture() as (origin, response, requests):
        for args in (submit_args(path),):
            for drop, status, body in (
                (True, 200, {}),
                (False, 503, {}),
                (
                    False,
                    409,
                    {
                        "error": {
                            "code": "conflict",
                            "message": "conflict",
                            "details": None,
                            "correlation_id": RUN,
                            "retryable": False,
                        },
                    },
                ),
            ):
                response["drop"] = drop
                respond(response, body, status)
                before = len(requests)
                result = cli(origin, TOKEN, *args)
                assert result.returncode == 1 and result.stdout == ""
                failure = json.loads(result.stderr)["error"]
                assert failure["outcome_unknown"] is True
                assert len(requests) == before + 1


def test_submission_receipts_fail_closed_and_preserve_uuid_identity(cli, tmp_path):
    path = tmp_path / "submission.zip"
    path.write_bytes(b"zip")
    with http_fixture() as (origin, response, requests):
        valid = acceptance() | {"assignment_id": ASSIGNMENT.replace("-", "")}
        respond(response, valid, 202)
        result = cli(origin, TOKEN, *submit_args(path))
        assert result.returncode == 0 and json.loads(result.stdout) == valid
        changes = (
            {"assignment_id": KEY},
            {"task_id": KEY},
            {"operation_id": "bad"},
            {"accepted_at": "bad"},
            {"status": "completed"},
            {"task_status_at_acceptance": "accepted"},
            {"processing_stage_at_acceptance": "post_pending"},
            {"replayed": None},
            {"submission_id": SUBMISSION},
            {"internal_url": "private"},
        )
        for change in changes:
            respond(response, acceptance() | change, 202)
            result = cli(origin, TOKEN, *submit_args(path))
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == 1 + len(changes)


def test_submission_posts_are_not_replayed_after_http2_goaway(cli, tmp_path):
    path = tmp_path / "submission.zip"
    path.write_bytes(b"zip-bytes")
    with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
        result = cli(origin, TOKEN, *submit_args(path), extra_env=env)
        assert_failure(result, "service_unavailable")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert connections == ["h2"] and bodies == [path.read_bytes()]


def test_submission_feedback_is_closed_safe_and_not_a_submission(cli, tmp_path):
    path = tmp_path / "submission.zip"
    path.write_bytes(b"zip")
    details = {
        "status": "failed",
        "eligible_to_submit": False,
        "results": [
            {
                "source": "project_external_checker",
                "requirement_id": "quality",
                "registry_entry_id": RUN,
                "registry_entry_digest": "sha256:" + "a" * 64,
                "status": "failed",
                "findings": [
                    {
                        "check_id": "quality.output",
                        "code": "quality",
                        "level": "error",
                        "message": "Fix \u202eunsafe\x1b text",
                        "path": "../../not-a-local-file",
                        "line": 2,
                    }
                ],
            }
        ],
    }
    envelope = {
        "error": {
            "code": "pre_submission_checker_failed",
            "message": "blocked",
            "details": details,
            "correlation_id": RUN,
            "retryable": False,
        }
    }
    with http_fixture() as (origin, response, requests):
        respond(response, envelope, 422)
        result = cli(origin, TOKEN, *submit_args(path))
        assert_failure(result, "pre_submission_checker_failed")
        error = json.loads(result.stderr)["error"]
        assert error["details"] == details and not error.get("outcome_unknown", False)
        assert "\u202e" not in result.stderr and "\x1b" not in result.stderr
        for invalid in (
            details | {"storage_key": "secret"},
            details | {"results": [None]},
            details | {"eligible_to_submit": True},
        ):
            respond(response, {"error": envelope["error"] | {"details": invalid}}, 422)
            assert_failure(
                cli(origin, TOKEN, *submit_args(path)), "invalid_api_response"
            )
        reflected = copy.deepcopy(envelope)
        reflected["error"]["details"]["results"][0]["findings"][0]["message"] = TOKEN
        respond(response, reflected, 422)
        assert_failure(cli(origin, TOKEN, *submit_args(path)), "invalid_api_response")
        assert len(requests) == 5


def test_submission_history_and_findings_are_bounded_and_preserve_evidence(cli):
    with http_fixture() as (origin, response, requests):
        respond(response, HISTORY)
        result = cli(origin, TOKEN, "submission", "show", SUBMISSION, "-o", "json")
        assert result.returncode == 0 and json.loads(result.stdout) == HISTORY
        page = {"items": [HISTORY], "next_cursor": "next-page"}
        respond(response, page)
        result = cli(
            origin, TOKEN, "task", "submissions", TASK, "--limit", "1", "-o", "json"
        )
        assert result.returncode == 0 and json.loads(result.stdout) == page
        respond(response, {"items": [CHECKER], "next_cursor": None})
        result = cli(
            origin,
            TOKEN,
            "submission",
            "findings",
            SUBMISSION,
            "--limit",
            "1",
            "--cursor",
            "previous",
            "-o",
            "json",
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["items"] == [CHECKER]
        assert "\u202e" not in result.stdout and "\x1b" not in result.stdout
        assert parse_qs(urlsplit(requests[-1][1]).query) == {
            "limit": ["1"],
            "cursor": ["previous"],
        }
        respond(response, CHECKER)
        result = cli(
            origin,
            TOKEN,
            "submission",
            "findings",
            SUBMISSION,
            "--run",
            RUN,
            "-o",
            "json",
        )
        assert result.returncode == 0 and json.loads(result.stdout) == CHECKER
        assert requests[-1][1] == f"/api/v1/submissions/{SUBMISSION}/checker-runs/{RUN}"
        assert len(requests) == 4
        # History does not carry current revision preparation. Explain the
        # distinct read without silently fetching or attaching today's context.
        for args, value in (
            (("submission", "show", SUBMISSION), HISTORY),
            (("task", "submissions", TASK), page),
        ):
            respond(response, value)
            before = len(requests)
            shown = cli(origin, TOKEN, *args)
            assert shown.returncode == 0, shown.stderr
            assert "not included in" in shown.stdout
            assert f"workstream task context {TASK}" in shown.stdout
            assert (
                "current task revision context, not historical submission context"
                in shown.stdout
            )
            assert "unavailable in the current public API" not in shown.stdout
            assert len(requests) == before + 1
        coverage = CHECKER | {
            "results": [
                CHECKER["results"][0]
                | {
                    "id": ASSIGNMENT,
                    "check_id": "coverage.files",
                    "path": None,
                    "line": None,
                    "status": "coverage_incomplete",
                    "severity": "medium",
                }
            ]
        }
        respond(response, coverage)
        shown = cli(
            origin,
            TOKEN,
            "submission",
            "findings",
            SUBMISSION,
            "--run",
            RUN,
            "-o",
            "json",
        )
        assert shown.returncode == 0 and json.loads(shown.stdout) == coverage, (
            shown.stderr
        )


DECIDED = "2026-10-14T11:00:00Z"


def test_submission_history_displays_only_exact_revision_deadline_reason(cli):
    with http_fixture() as (origin, response, _):
        for history in (
            HISTORY,
            HISTORY | {"status": "review_pending"},
            HISTORY | {"status": "accepted", "decided_at": DECIDED},
            HISTORY
            | {
                "status": "needs_revision",
                "decided_at": DECIDED,
                "finding_counts": {
                    "blocking": 2,
                    "warning": 1,
                    "coverage_incomplete": 1,
                },
            },
            HISTORY
            | {
                "status": "rejected",
                "status_reason": "revision_deadline_expired",
                "decided_at": DECIDED,
            },
            HISTORY
            | {
                "status": "needs_revision",
                "status_reason": "checker_coverage_incomplete",
                "decided_at": DECIDED,
            },
        ):
            respond(response, history)
            result = cli(origin, TOKEN, "submission", "show", SUBMISSION, "-o", "json")
            assert result.returncode == 0 and json.loads(result.stdout) == history, (
                result.stderr
            )
            text = cli(origin, TOKEN, "submission", "show", SUBMISSION)
            assert text.returncode == 0, text.stderr
            displayed = json.loads(text.stdout.splitlines()[0].split(": ", 1)[1])
            assert displayed.get("status_reason") == history.get("status_reason")
            respond(response, {"items": [history], "next_cursor": None})
            page = cli(origin, TOKEN, "task", "submissions", TASK, "-o", "json")
            assert page.returncode == 0 and json.loads(page.stdout)["items"] == [
                history
            ]
        for history in (
            HISTORY | {"status_reason": "revision_deadline_expired"},
            HISTORY
            | {"status": "rejected", "decided_at": DECIDED, "status_reason": "other"},
            HISTORY
            | {"status": "rejected", "decided_at": DECIDED, "status_reason": ""},
            HISTORY | {"status": "rejected", "decided_at": DECIDED, "status_reason": 1},
            HISTORY | {"status": "submitted"},
            HISTORY
            | {
                "status": "accepted",
                "decided_at": DECIDED,
                "status_reason": "checker_coverage_incomplete",
            },
            HISTORY
            | {
                "status": "needs_revision",
                "decided_at": DECIDED,
                "status_reason": "revision_deadline_expired",
            },
            HISTORY | {"status": "accepted"},
            HISTORY | {"decided_at": DECIDED},
            HISTORY
            | {
                "finding_counts": {
                    "blocking": -1,
                    "warning": 0,
                    "coverage_incomplete": 0,
                }
            },
            HISTORY | {"finding_counts": {"blocking": 0, "warning": 0}},
            {key: value for key, value in HISTORY.items() if key != "status_reason"},
        ):
            respond(response, history)
            assert_failure(
                cli(origin, TOKEN, "submission", "show", SUBMISSION, "-o", "json"),
                "invalid_api_response",
            )


def test_submission_reads_reject_substitution_private_fields_and_duplicate_identity(
    cli,
):
    with http_fixture() as (origin, response, _):
        for change in (
            {"id": KEY},
            {"task_id": "bad"},
            {"evidence_items": [None]},
            {"locked_at": "bad"},
            {"storage_key": "private"},
        ):
            respond(response, HISTORY | change)
            assert_failure(
                cli(origin, TOKEN, "submission", "show", SUBMISSION, "-o", "json"),
                "invalid_api_response",
            )
        for items in (
            [HISTORY, HISTORY | {"id": SUBMISSION.replace("-", "")}],
            [HISTORY | {"task_id": KEY}],
        ):
            respond(response, {"items": items, "next_cursor": None})
            assert_failure(
                cli(origin, TOKEN, "task", "submissions", TASK, "-o", "json"),
                "invalid_api_response",
            )
        result = CHECKER["results"][0]
        for change in (
            {"submission_id": KEY},
            {"id": KEY},
            {"results": [None]},
            {"attempt_number": None},
            {"raw_output": "private"},
            {"results": [result | {"line": 4, "path": None}]},
            {"results": [result | {"line": 0}]},
            {"results": [result | {"check_id": ""}]},
            {"results": [{k: v for k, v in result.items() if k != "check_id"}]},
            {"results": [result | {"status": "not_run"}]},
        ):
            respond(response, CHECKER | change)
            assert_failure(
                cli(
                    origin,
                    TOKEN,
                    "submission",
                    "findings",
                    SUBMISSION,
                    "--run",
                    RUN,
                    "-o",
                    "json",
                ),
                "invalid_api_response",
            )


def test_history_cursor_contract_preserves_1024_characters_without_widening_task_lists(
    cli,
):
    selections = (("task", "submissions", TASK), ("submission", "findings", SUBMISSION))
    with http_fixture() as (origin, response, requests):
        for args, item in zip(selections, (HISTORY, CHECKER), strict=True):
            for cursor in ("a" * 513, "b" * 1024, "é" * 1024):
                respond(response, {"items": [item], "next_cursor": cursor})
                result = cli(origin, TOKEN, *args, "--cursor", cursor, "-o", "json")
                assert result.returncode == 0, result.stderr
                assert json.loads(result.stdout)["next_cursor"] == cursor
                assert parse_qs(urlsplit(requests[-1][1]).query)["cursor"] == [cursor]
            before = len(requests)
            assert_failure(
                cli(origin, TOKEN, *args, "--cursor", "a" * 1025, "-o", "json"),
                "invalid_arguments",
                2,
            )
            assert len(requests) == before
            respond(response, {"items": [item], "next_cursor": "a" * 1025})
            assert_failure(
                cli(origin, TOKEN, *args, "-o", "json"), "invalid_api_response"
            )
        before = len(requests)
        assert_failure(
            cli(
                origin,
                TOKEN,
                "task",
                "ready",
                TASK,
                "--cursor",
                "a" * 513,
                "-o",
                "json",
            ),
            "invalid_arguments",
            2,
        )
        assert len(requests) == before


def test_submission_response_caps_reject_otherwise_valid_oversized_json(cli, tmp_path):
    path = tmp_path / "submission.zip"
    path.write_bytes(b"zip")
    cap = 2 * 1024 * 1024
    cases = (
        (submit_args(path), acceptance(), 202),
        (("submission", "show", SUBMISSION, "-o", "json"), HISTORY, 200),
        (
            ("task", "submissions", TASK, "-o", "json"),
            {"items": [HISTORY], "next_cursor": None},
            200,
        ),
        (
            ("submission", "findings", SUBMISSION, "--run", RUN, "-o", "json"),
            CHECKER,
            200,
        ),
        (
            ("submission", "findings", SUBMISSION, "-o", "json"),
            {"items": [CHECKER], "next_cursor": None},
            200,
        ),
    )
    with http_fixture() as (origin, response, requests):
        for args, value, status in cases:
            respond(response, value, status)
            control = cli(origin, TOKEN, *args)
            assert control.returncode == 0, control.stderr
            # JSON whitespace leaves the independently valid projection intact.
            # Removing the transport cap must make this counterexample succeed.
            response["body"] = b" " * (cap + 1) + response["body"]
            result = cli(origin, TOKEN, *args)
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"].get("outcome_unknown", False) == (
                status == 202
            )
        assert len(requests) == len(cases) * 2


def operation_progress():
    return {
        "operation_id": OPERATION,
        "task_id": TASK,
        "assignment_id": ASSIGNMENT,
        "idempotency_key": KEY,
        "operation_state": "finalization_pending",
        "processing_stage": "finalization_pending",
        "accepted_at": "2026-11-16T12:00:00Z",
        "task_status_at_acceptance": "evaluation_pending",
        "current_task_status": None,
        "submission_id": None,
        "submission_version": None,
        "evaluation_request_id": None,
        "pre_submission_results": [],
        "failure_code": None,
        "operationally_stalled": False,
        "next_action": "wait",
    }


def test_operation_inspection_is_one_read_with_exact_selector(cli):
    with http_fixture() as (origin, response, requests):
        respond(response, operation_progress())
        for flag, value, query in (
            ("--operation-id", OPERATION, "operation_id"),
            ("--idempotency-key", KEY, "idempotency_key"),
        ):
            result = cli(
                origin,
                TOKEN,
                "--output",
                "json",
                "task",
                "submission-operation",
                TASK,
                flag,
                value,
            )
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout) == operation_progress()
            method, path, authorization = requests[-1]
            assert method == "GET" and authorization == "Bearer " + TOKEN
            assert urlsplit(path).path == f"/api/v1/tasks/{TASK}/submission-operations"
            assert parse_qs(urlsplit(path).query) == {query: [value]}
        assert len(requests) == 2
        for flags in (
            (),
            ("--operation-id", OPERATION, "--idempotency-key", KEY),
            ("--operation-id", ""),
            ("--operation-id", "invalid"),
        ):
            result = cli(
                origin,
                TOKEN,
                "--output",
                "json",
                "task",
                "submission-operation",
                TASK,
                *flags,
            )
            assert result.returncode != 0
        assert len(requests) == 2
        text_result = cli(
            origin,
            TOKEN,
            "task",
            "submission-operation",
            TASK,
            "--operation-id",
            OPERATION,
        )
        assert text_result.returncode == 0, text_result.stderr
        assert (
            "finalization_pending" in text_result.stdout
            and "wait" in text_result.stdout
        )
        assert len(requests) == 3


def test_operation_inspection_refuses_foreign_or_private_response(cli):
    with http_fixture() as (origin, response, requests):
        for changed in (
            {"operation_id": RUN},
            {"task_id": RUN},
            {"provider_key": "private"},
            {"processing_stage": "invented"},
            {"next_action": "submit_now"},
        ):
            respond(response, operation_progress() | changed)
            result = cli(
                origin,
                TOKEN,
                "--output",
                "json",
                "task",
                "submission-operation",
                TASK,
                "--operation-id",
                OPERATION,
            )
            assert_failure(result, "invalid_api_response")
        assert len(requests) == 5
