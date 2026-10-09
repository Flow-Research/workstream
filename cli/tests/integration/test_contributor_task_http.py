"""Built-process contributor projection, route and failure-boundary proof."""

import json
from urllib.parse import parse_qs, urlsplit

from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture
from test_task_http_boundary import DETAIL, SUMMARY, SUMMARY_TEXT, TASK

POLICY = "22222222-2222-4222-8222-222222222222"
COMPENSATION = {
    "contribution_policy_version_id": POLICY,
    "accepted_submission": [
        {
            "instrument": "money",
            "unit": "USD",
            "quantity": "2.125000000000000001",
        },
        {"instrument": "project_points", "unit": "PTS", "quantity": "7"},
    ],
    "completed_review": "unpaid",
}

READY = {
    key: SUMMARY[key]
    for key in (
        "task_id",
        "project_id",
        "title",
        "task_type",
        "difficulty",
        "skill_tags",
        "estimated_time_minutes",
        "created_at",
    )
} | {"compensation": COMPENSATION}
CONTRIBUTOR = {
    key: value
    for key, value in DETAIL.items()
    if key
    not in {
        "source_type",
        "source_ref",
        "source_payload_hash",
        "import_batch_id",
        "external_task_id",
        "created_by",
        "assigned_to",
    }
} | {"status": "ready", "compensation": COMPENSATION}
READY_TEXT = (
    f"Task: {TASK}\nProject: {PROJECT}\nTitle: Work é\\u000A\\u001B[31m\n"
    "Type: evaluation\nDifficulty: medium\nSkills: analysis, tag\\u000A\n"
    "Estimated minutes: 17\nCreated: 2026-10-01T00:00:00Z\n"
    f"Contribution policy version: {POLICY}\n"
    "Accepted submission compensation: money USD 2.125000000000000001\n"
    "Accepted submission compensation: project_points PTS 7\n"
    "Completed review compensation: unpaid\n"
)
DETAIL_TEXT = SUMMARY_TEXT.replace("Status: draft", "Status: ready") + (
    f"Contribution policy version: {POLICY}\n"
    "Accepted submission compensation: money USD 2.125000000000000001\n"
    "Accepted submission compensation: project_points PTS 7\n"
    "Completed review compensation: unpaid\n"
    "Description: Instructions\\u000A\\u001B[32m\n"
    "Acceptance criteria: Accurate\nRejection criteria: Missing\n"
)


def test_contributor_reads_preserve_closed_fields_and_wire(cli):
    cursor = "opaque+/=&?#\n"
    with http_fixture() as (origin, response, requests):
        page = {"project_id": PROJECT, "items": [READY], "next_cursor": cursor}
        response["body"] = json.dumps(page).encode()
        result = cli(
            origin, TOKEN, "task", "ready", PROJECT, "--limit", "1", "-o", "json"
        )
        assert result.returncode == 0 and result.stderr == ""
        assert result.stdout.strip().encode() == response["body"]
        assert requests[-1] == (
            "GET",
            f"/api/v1/projects/{PROJECT}/tasks/ready?limit=1",
            "Bearer " + TOKEN,
        )
        result = cli(
            origin, TOKEN, "task", "ready", PROJECT, "--limit", "1", "--cursor", cursor
        )
        assert result.returncode == 0 and result.stderr == ""
        assert (
            result.stdout
            == f"Project: {PROJECT}\nReady tasks: 1\n"
            + READY_TEXT
            + "Next cursor: opaque+/=&?#\\u000A\n"
        )
        assert parse_qs(urlsplit(requests[-1][1]).query) == {
            "limit": ["1"],
            "cursor": [cursor],
        }

        for selector in (
            PROJECT.replace("-", ""),
            "{" + PROJECT + "}",
            "urn:uuid:" + PROJECT,
        ):
            result = cli(origin, TOKEN, "task", "ready", selector, "-o", "json")
            assert result.returncode == 0 and result.stderr == ""
            assert json.loads(result.stdout) == page
            assert (
                requests[-1][1]
                == f"/api/v1/projects/{selector.replace('{', '%7B').replace('}', '%7D')}/tasks/ready?limit=50"
            )

        nulls = READY | {
            key: None for key in ("task_type", "difficulty", "estimated_time_minutes")
        }
        response["body"] = json.dumps(
            page | {"items": [nulls], "next_cursor": None}
        ).encode()
        result = cli(origin, TOKEN, "task", "ready", PROJECT, "-o", "json")
        assert (
            result.returncode == 0
            and result.stdout.strip().encode() == response["body"]
        )
        result = cli(origin, TOKEN, "task", "ready", PROJECT)
        assert result.returncode == 0 and result.stdout == (
            f"Project: {PROJECT}\nReady tasks: 1\n"
            + READY_TEXT.replace("evaluation", "—")
            .replace("medium", "—")
            .replace("17", "—")
            + "Next cursor: —\n"
        )
        response["body"] = json.dumps(
            {"project_id": PROJECT, "items": [], "next_cursor": None}
        ).encode()
        result = cli(origin, TOKEN, "task", "ready", PROJECT)
        assert (
            result.returncode == 0
            and result.stdout == f"Project: {PROJECT}\nReady tasks: 0\nNext cursor: —\n"
        )

        response["body"] = json.dumps(CONTRIBUTOR).encode()
        for selector in (
            TASK,
            TASK.replace("-", ""),
            "{" + TASK + "}",
            "urn:uuid:" + TASK,
        ):
            result = cli(origin, TOKEN, "task", "show", selector, "-o", "json")
            assert result.returncode == 0 and result.stderr == ""
            assert result.stdout.strip().encode() == response["body"]
            assert requests[-1] == (
                "GET",
                "/api/v1/tasks/" + selector.replace("{", "%7B").replace("}", "%7D"),
                "Bearer " + TOKEN,
            )
        result = cli(origin, TOKEN, "task", "show", TASK)
        assert (
            result.returncode == 0
            and result.stderr == ""
            and result.stdout == DETAIL_TEXT
        )
        nullable_keys = {
            "task_type",
            "difficulty",
            "estimated_time_minutes",
            "deadline_at",
            "acceptance_criteria",
            "rejection_criteria",
        }
        for detail in (
            {
                key: value
                for key, value in CONTRIBUTOR.items()
                if key not in nullable_keys
            },
            CONTRIBUTOR | {key: None for key in nullable_keys},
        ):
            response["body"] = json.dumps(detail).encode()
            result = cli(origin, TOKEN, "task", "show", TASK, "-o", "json")
            assert (
                result.returncode == 0
                and result.stdout.strip().encode() == response["body"]
            )
            result = cli(origin, TOKEN, "task", "show", TASK)
            assert result.returncode == 0 and result.stdout == (
                DETAIL_TEXT.replace("evaluation", "—")
                .replace("medium", "—")
                .replace("17", "—")
                .replace("2026-10-03T00:00:00Z", "—")
                .replace("Accurate", "—")
                .replace("Missing", "—")
            )
        assert (
            len(requests) == 17
        )  # One request each; no authority preflight or automatic pages.


def test_contributor_reads_reject_malformed_and_management_disclosure(cli):
    with http_fixture() as (origin, response, _requests):
        page = {"project_id": PROJECT, "items": [READY], "next_cursor": None}
        bad_pages = [
            None,
            [],
            {},
            page | {"project_id": ACTOR},
            page | {"items": None},
            page | {"items": [None]},
            page | {"unknown": True},
            page | {"next_cursor": ""},
            page | {"next_cursor": "x" * 513},
            page | {"next_cursor": 3},
            page | {"items": [], "next_cursor": "cursor"},
        ]
        bad_pages.extend(
            {key: value for key, value in page.items() if key != missing}
            for missing in page
        )
        bad_items = [
            READY | {"project_id": ACTOR},
            READY | {"task_id": "bad"},
            READY | {"created_at": "2026-10-01"},
            READY | {"skill_tags": [None]},
            READY | {"compensation": None},
            READY | {"compensation": COMPENSATION | {"route_key": "private"}},
            READY
            | {
                "compensation": COMPENSATION | {"contribution_policy_version_id": "bad"}
            },
            READY | {"compensation": COMPENSATION | {"accepted_submission": 2.125}},
            READY | {"compensation": COMPENSATION | {"accepted_submission": []}},
            READY
            | {
                "compensation": COMPENSATION
                | {
                    "accepted_submission": [
                        {"instrument": "money", "unit": "USD", "quantity": "0"}
                    ]
                }
            },
            READY
            | {"compensation": COMPENSATION | {"accepted_submission": "compensated"}},
            READY
            | {
                "compensation": COMPENSATION
                | {
                    "accepted_submission": [
                        {
                            "instrument": "money",
                            "unit": "USD",
                            "quantity": "2.125",
                            "adapter_binding_id": ACTOR,
                        }
                    ]
                }
            },
        ]
        bad_items.extend(
            {key: value for key, value in READY.items() if key != missing}
            for missing in READY
        )
        bad_items.extend(
            READY | {key: None}
            for key in ("task_id", "project_id", "title", "created_at", "skill_tags")
        )
        bad_items.extend(
            READY | {key: SUMMARY[key]}
            for key in ("status", "deadline_at", "updated_at")
        )
        bad_pages.extend(page | {"items": [bad]} for bad in bad_items)
        for bad in bad_pages:
            response["body"] = json.dumps(bad).encode()
            assert_failure(
                cli(origin, TOKEN, "task", "ready", PROJECT, "-o", "json"),
                "invalid_api_response",
            )
        # limit=2 lets the duplicate reach identity validation, not page-size rejection.
        for duplicate_id in (TASK, TASK.replace("-", "")):
            response["body"] = json.dumps(
                page | {"items": [READY, READY | {"task_id": duplicate_id}]}
            ).encode()
            assert_failure(
                cli(
                    origin,
                    TOKEN,
                    "task",
                    "ready",
                    PROJECT,
                    "--limit",
                    "2",
                    "-o",
                    "json",
                ),
                "invalid_api_response",
            )
        response["body"] = json.dumps(
            page | {"items": [READY, READY | {"task_id": ACTOR}]}
        ).encode()
        assert_failure(
            cli(origin, TOKEN, "task", "ready", PROJECT, "--limit", "1", "-o", "json"),
            "invalid_api_response",
        )

        bad_details = [
            None,
            {},
            CONTRIBUTOR | {"task_id": ACTOR},
            CONTRIBUTOR | {"project_id": "bad"},
            CONTRIBUTOR | {"deadline_at": "bad"},
            CONTRIBUTOR | {"skill_tags": [None]},
            CONTRIBUTOR | {"compensation": COMPENSATION | {"binding_status": "active"}},
        ]
        required = (
            "task_id",
            "project_id",
            "title",
            "description",
            "status",
            "skill_tags",
            "created_at",
            "updated_at",
        )
        bad_details.extend(
            {key: value for key, value in CONTRIBUTOR.items() if key != missing}
            for missing in required
        )
        bad_details.extend(CONTRIBUTOR | {key: None} for key in required)
        bad_details.extend(
            CONTRIBUTOR | {key: DETAIL[key]} for key in DETAIL if key not in CONTRIBUTOR
        )
        for bad in bad_details:
            response["body"] = json.dumps(bad).encode()
            assert_failure(
                cli(origin, TOKEN, "task", "show", TASK, "-o", "json"),
                "invalid_api_response",
            )
        for command, body in (
            (("ready", PROJECT), json.dumps(page).replace('"title":', '"Title":')),
            (
                ("ready", PROJECT),
                json.dumps(page).replace('"title":', '"title":"duplicate","title":'),
            ),
            (
                ("show", TASK),
                json.dumps(CONTRIBUTOR).replace(
                    '"description":', '"description":"duplicate","description":'
                ),
            ),
        ):
            response["body"] = body.encode()
            assert_failure(
                cli(origin, TOKEN, "task", *command, "-o", "json"),
                "invalid_api_response",
            )
        response["body"] = json.dumps(
            CONTRIBUTOR | {"description": "x" * 65537}
        ).encode()
        assert_failure(
            cli(origin, TOKEN, "task", "show", TASK, "-o", "json"),
            "invalid_api_response",
        )


def test_contributor_reads_bound_inputs_and_preserve_failure_transport(cli):
    with http_fixture() as (origin, response, requests):
        for command in (
            ("ready", "bad"),
            ("show", "bad"),
            ("show", TASK + "/extra"),
            ("ready", PROJECT, "--limit", "0"),
            ("ready", PROJECT, "--limit", "101"),
            ("ready", PROJECT, "--cursor", ""),
            ("ready", PROJECT, "--cursor", "x" * 513),
        ):
            result = cli(origin, TOKEN, "-o", "json", "task", *command)
            assert result.returncode == 2 and result.stdout == ""
        assert requests == []
        for command in (("ready", PROJECT), ("show", TASK)):
            response.update(
                status=404,
                body=b'{"error":{"code":"project_authorization_resource_not_found"}}',
            )
            denied = cli(origin, TOKEN, "task", *command, "-o", "json")
            assert_failure(denied, "project_authorization_resource_not_found")
            assert json.loads(denied.stderr)["error"]["status"] == 404
            response.update(
                status=302, headers={"Location": origin + "/capture"}, body=b""
            )
            assert_failure(
                cli(origin, TOKEN, "task", *command, "-o", "json"), "redirect_refused"
            )
        assert len(requests) == 4 and all(
            "/capture" not in entry[1] for entry in requests
        )
