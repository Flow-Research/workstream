"""Built-process proof for the public manager list-to-detail journey."""

from copy import deepcopy
import json
from urllib.parse import parse_qs, urlsplit

from test_http_boundary import (
    ACTOR,
    PROFILE,
    PROJECT,
    TOKEN,
    assert_failure,
    http_fixture,
)

TASK = "018f0ebc-7966-7e8d-bc4d-1cae1e000003"
SUMMARY = {
    "task_id": TASK,
    "project_id": PROJECT,
    "title": "Work é\n\x1b[31m",
    "task_type": "evaluation",
    "difficulty": "medium",
    "skill_tags": ["analysis", "tag\n"],
    "estimated_time_minutes": 17,
    "status": "draft",
    "deadline_at": "2026-10-03T00:00:00Z",
    "created_at": PROFILE["created_at"],
    "updated_at": "2026-10-02T00:00:00Z",
}
DETAIL = SUMMARY | {
    "task_size": "small",
    "description": "Instructions\n\x1b[32m",
    "acceptance_criteria": "Accurate",
    "rejection_criteria": "Missing",
    "source_type": "manual",
    "source_ref": "reference",
    "source_payload_hash": "hash",
    "import_batch_id": "batch",
    "external_task_id": "external",
    "created_by": ACTOR,
    "assigned_to": ACTOR,
}
SUMMARY_TEXT = (
    f"Task: {TASK}\nProject: {PROJECT}\nTitle: Work é\\u000A\\u001B[31m\n"
    "Status: draft\nType: evaluation\nDifficulty: medium\nSkills: analysis, tag\\u000A\n"
    "Estimated minutes: 17\nDeadline: 2026-10-03T00:00:00Z\n"
    "Created: 2026-10-01T00:00:00Z\nUpdated: 2026-10-02T00:00:00Z\n"
)


def test_manager_task_reads_preserve_fields_and_wire(cli):
    cursor = "opaque+/=&?#\n"
    with http_fixture() as (origin, response, requests):
        page = {"project_id": PROJECT, "items": [SUMMARY], "next_cursor": cursor}
        response["body"] = json.dumps(page).encode()
        result = cli(
            origin, TOKEN, "project", "tasks", PROJECT, "--limit", "1", "-o", "json"
        )
        assert result.returncode == 0 and result.stderr == ""
        assert result.stdout.strip().encode() == response["body"]
        assert requests[-1] == (
            "GET",
            f"/api/v1/projects/{PROJECT}/tasks?limit=1",
            "Bearer " + TOKEN,
        )
        text = cli(
            origin,
            TOKEN,
            "project",
            "tasks",
            PROJECT,
            "--limit",
            "1",
            "--cursor",
            cursor,
        )
        assert text.returncode == 0 and text.stderr == ""
        assert (
            text.stdout
            == f"Project: {PROJECT}\nTasks: 1\n"
            + SUMMARY_TEXT
            + "Next cursor: opaque+/=&?#\\u000A\n"
        )
        query = parse_qs(urlsplit(requests[-1][1]).query)
        assert query == {"limit": ["1"], "cursor": [cursor]}
        for selector in (
            TASK,
            TASK.replace("-", ""),
            "{" + TASK + "}",
            "urn:uuid:" + TASK,
        ):
            response["body"] = json.dumps(DETAIL).encode()
            result = cli(
                origin,
                TOKEN,
                "project",
                "task",
                PROJECT.replace("-", ""),
                selector,
                "-o",
                "json",
            )
            assert result.returncode == 0 and result.stderr == ""
            assert result.stdout.strip().encode() == response["body"]
            assert requests[-1] == (
                "GET",
                f"/api/v1/projects/{PROJECT.replace('-', '')}/tasks/"
                + selector.replace("{", "%7B").replace("}", "%7D"),
                "Bearer " + TOKEN,
            )
        text = cli(origin, TOKEN, "project", "task", PROJECT, TASK)
        assert text.returncode == 0 and text.stderr == ""
        assert text.stdout == SUMMARY_TEXT + (
            "Task size: small\nDescription: Instructions\\u000A\\u001B[32m\nAcceptance criteria: Accurate\n"
            "Rejection criteria: Missing\nSource type: manual\nSource reference: reference\n"
            f"Source hash: hash\nImport batch: batch\nExternal task: external\nCreated by: {ACTOR}\nAssigned to: {ACTOR}\n"
        )
        nullable = {
            key: value
            for key, value in DETAIL.items()
            if key
            in {
                "task_id",
                "project_id",
                "task_size",
                "title",
                "status",
                "skill_tags",
                "created_at",
                "updated_at",
                "description",
                "source_type",
                "created_by",
            }
        }
        for value in (
            nullable,
            DETAIL | {key: None for key in DETAIL if key not in nullable},
        ):
            response["body"] = json.dumps(value).encode()
            result = cli(origin, TOKEN, "project", "task", PROJECT, TASK, "-o", "json")
            assert result.returncode == 0 and result.stderr == ""
            assert json.loads(result.stdout) == value
            text = cli(origin, TOKEN, "project", "task", PROJECT, TASK)
            assert text.returncode == 0 and text.stderr == ""
            assert text.stdout == (
                f"Task: {TASK}\nProject: {PROJECT}\nTitle: Work é\\u000A\\u001B[31m\n"
                "Status: draft\nType: —\nDifficulty: —\nSkills: analysis, tag\\u000A\n"
                "Estimated minutes: —\nDeadline: —\nCreated: 2026-10-01T00:00:00Z\n"
                "Updated: 2026-10-02T00:00:00Z\nTask size: small\nDescription: Instructions\\u000A\\u001B[32m\n"
                "Acceptance criteria: —\nRejection criteria: —\nSource type: manual\n"
                "Source reference: —\nSource hash: —\nImport batch: —\nExternal task: —\n"
                f"Created by: {ACTOR}\nAssigned to: —\n"
            )
        nullable_summary = SUMMARY | {
            "task_type": None,
            "difficulty": None,
            "estimated_time_minutes": None,
            "deadline_at": None,
        }
        response["body"] = json.dumps(
            {
                "project_id": PROJECT,
                "items": [nullable_summary],
                "next_cursor": None,
            }
        ).encode()
        result = cli(origin, TOKEN, "project", "tasks", PROJECT, "-o", "json")
        assert result.returncode == 0 and result.stderr == ""
        assert result.stdout.strip().encode() == response["body"]
        text = cli(origin, TOKEN, "project", "tasks", PROJECT)
        assert text.returncode == 0 and text.stderr == ""
        assert text.stdout == (
            f"Project: {PROJECT}\nTasks: 1\nTask: {TASK}\nProject: {PROJECT}\n"
            "Title: Work é\\u000A\\u001B[31m\nStatus: draft\nType: —\nDifficulty: —\n"
            "Skills: analysis, tag\\u000A\nEstimated minutes: —\nDeadline: —\n"
            "Created: 2026-10-01T00:00:00Z\nUpdated: 2026-10-02T00:00:00Z\nNext cursor: —\n"
        )
        response["body"] = json.dumps(
            {"project_id": PROJECT, "items": [], "next_cursor": None}
        ).encode()
        result = cli(origin, TOKEN, "project", "tasks", PROJECT)
        assert (
            result.returncode == 0
            and result.stdout == f"Project: {PROJECT}\nTasks: 0\nNext cursor: —\n"
        )
        assert len(requests) == 14  # One call each, no preflight or automatic pages.


def test_manager_task_reads_reject_malformed_or_substituted_success(cli):
    with http_fixture() as (origin, response, _requests):
        page = {"project_id": PROJECT, "items": [SUMMARY], "next_cursor": None}
        bad_pages = [
            None,
            [],
            {},
            page | {"project_id": ACTOR},
            page | {"items": None},
            page | {"items": [None]},
            page | {"items": [SUMMARY, SUMMARY]},
            page | {"next_cursor": ""},
            page | {"next_cursor": 3},
            page | {"next_cursor": "a" * 513},
            page | {"items": [], "next_cursor": "cursor"},
            page | {"unknown": True},
        ]
        for key in page:
            bad_pages.append({k: v for k, v in page.items() if k != key})
        for key in SUMMARY:
            bad = deepcopy(page)
            del bad["items"][0][key]
            bad_pages.append(bad)
        for field, value in (
            ("task_id", "bad"),
            ("project_id", ACTOR),
            ("title", None),
            ("status", None),
            ("created_at", "bad"),
            ("updated_at", None),
            ("deadline_at", "bad"),
            ("skill_tags", None),
            ("skill_tags", [None]),
            ("estimated_time_minutes", 1.2),
            ("difficulty", []),
            ("private", True),
        ):
            bad_pages.append(page | {"items": [SUMMARY | {field: value}]})
        for value in bad_pages:
            response["body"] = json.dumps(value).encode()
            assert_failure(
                cli(
                    origin,
                    TOKEN,
                    "project",
                    "tasks",
                    PROJECT,
                    "--limit",
                    "1",
                    "-o",
                    "json",
                ),
                "invalid_api_response",
            )
        # Two duplicate IDs must fail independently of the page-size guard.
        response["body"] = json.dumps(page | {"items": [SUMMARY, SUMMARY]}).encode()
        assert_failure(
            cli(
                origin, TOKEN, "project", "tasks", PROJECT, "--limit", "2", "-o", "json"
            ),
            "invalid_api_response",
        )
        for field, value in (
            ("task_id", ACTOR),
            ("project_id", ACTOR),
            ("created_by", "bad"),
            ("assigned_to", "bad"),
            ("description", None),
            ("source_type", None),
            ("skill_tags", [None]),
            ("title", None),
            ("private", True),
        ):
            response["body"] = json.dumps(DETAIL | {field: value}).encode()
            assert_failure(
                cli(origin, TOKEN, "project", "task", PROJECT, TASK, "-o", "json"),
                "invalid_api_response",
            )
        for key in (
            "task_id",
            "project_id",
            "created_by",
            "description",
            "source_type",
            "skill_tags",
            "created_at",
            "updated_at",
        ):
            response["body"] = json.dumps(
                {k: v for k, v in DETAIL.items() if k != key}
            ).encode()
            assert_failure(
                cli(origin, TOKEN, "project", "task", PROJECT, TASK, "-o", "json"),
                "invalid_api_response",
            )
        for args, body in (
            (
                ("tasks", PROJECT),
                json.dumps(page).replace('"project_id":', '"Project_id":', 1),
            ),
            (
                ("task", PROJECT, TASK),
                json.dumps(DETAIL)[:-1] + ',"task_id":"' + TASK + '"}',
            ),
            (("tasks", PROJECT), json.dumps(page)[:-1] + ',"items":[]}'),
            (
                ("task", PROJECT, TASK),
                json.dumps(DETAIL | {"description": "a" * 65536}),
            ),
        ):
            response["body"] = body.encode()
            assert_failure(
                cli(origin, TOKEN, "project", *args, "-o", "json"),
                "invalid_api_response",
            )


def test_manager_task_reads_bound_inputs_and_reuse_failure_transport(cli):
    with http_fixture() as (origin, response, requests):
        for args in (
            ("tasks", "../actors"),
            ("task", PROJECT, "../actors"),
            ("tasks", PROJECT, "--limit", "0"),
            ("tasks", PROJECT, "--limit", "101"),
            ("tasks", PROJECT, "--cursor", ""),
            ("tasks", PROJECT, "--cursor", "a" * 513),
            ("tasks", PROJECT, "--unknown"),
            ("task", PROJECT),
        ):
            assert_failure(
                cli(origin, TOKEN, "-o", "json", "project", *args),
                "invalid_arguments",
                2,
            )
        assert requests == []
        for command in (("tasks", PROJECT), ("task", PROJECT, TASK)):
            response.update(status=403, body=b'{"error":{"code":"denied"}}')
            assert_failure(
                cli(origin, TOKEN, "project", *command, "-o", "json"), "denied"
            )
            with http_fixture() as (other, _response, other_requests):
                response.update(status=302, headers={"Location": other + "/private"})
                assert_failure(
                    cli(origin, TOKEN, "project", *command, "-o", "json"),
                    "redirect_refused",
                )
                assert other_requests == []
            response.update(status=200, drop=True)
            assert_failure(
                cli(origin, TOKEN, "project", *command, "-o", "json"),
                "service_unavailable",
            )
            response["drop"] = False
        assert (
            len(requests) == 6
        )  # No retry on failure, no redirect credential forwarding.
