"""Built-binary proof of the public Operator task inspection contracts."""

from copy import deepcopy
import json
from urllib.parse import quote

from test_contributor_task_mutations import KEY
from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture
from test_task_context_http import REVISION_LINEAGE
from test_task_http_boundary import TASK

SUMMARY = {
    "task_id": TASK,
    "project_id": PROJECT,
    "status": "in_progress",
    "created_at": "2026-10-01T00:00:00Z",
    "updated_at": "2026-10-02T00:00:00Z",
}
CONTEXT = {"task_id": TASK, "project_id": PROJECT} | REVISION_LINEAGE


def invoke(cli, origin, *args, output="json"):
    return cli(origin, TOKEN, "-o", output, "operations", "task", *args)


def test_operator_reads_use_only_exact_restricted_routes_and_projection(cli):
    with http_fixture() as (origin, response, requests):
        page = {"project_id": PROJECT, "items": [SUMMARY], "next_cursor": "opaque-1"}
        response["body"] = json.dumps(page).encode()
        result = invoke(cli, origin, "list", PROJECT, "--limit", "1")
        assert result.returncode == 0 and json.loads(result.stdout) == page
        assert requests[-1] == (
            "GET",
            f"/api/v1/operations/projects/{PROJECT}/tasks?limit=1",
            "Bearer " + TOKEN,
        )
        result = invoke(
            cli,
            origin,
            "list",
            PROJECT,
            "--limit",
            "1",
            "--cursor",
            "opaque-1",
            output="text",
        )
        assert result.returncode == 0 and result.stderr == ""
        assert result.stdout == (
            f"Project: {PROJECT}\nOperator tasks: 1\nTask: {TASK}\nProject: {PROJECT}\n"
            "Status: in_progress\nCreated: 2026-10-01T00:00:00Z\n"
            "Updated: 2026-10-02T00:00:00Z\n"
            "Next cursor (observation, not authority): opaque-1\n"
        )
        assert requests[-1] == (
            "GET",
            f"/api/v1/operations/projects/{PROJECT}/tasks?cursor=opaque-1&limit=1",
            "Bearer " + TOKEN,
        )
        response["body"] = json.dumps(CONTEXT).encode()
        for project, task in (
            (PROJECT, TASK),
            (PROJECT.replace("-", ""), "{" + TASK + "}"),
        ):
            result = invoke(cli, origin, "locked-context", project, task)
            assert result.returncode == 0 and result.stderr == ""
            assert json.loads(result.stdout) == CONTEXT
            assert requests[-1] == (
                "GET",
                f"/api/v1/operations/projects/{project}/tasks/{quote(task, safe=':')}/locked-context",
                "Bearer " + TOKEN,
            )
        result = invoke(cli, origin, "locked-context", PROJECT, TASK, output="text")
        assert result.returncode == 0 and result.stderr == ""
        assert result.stdout.startswith("Operator locked context (references only): {")
        assert '"locked_post_submit_checker_policy_hash"' in result.stdout
        assert "policy_body" not in result.stdout
        assert len(requests) == 5  # One public request per invocation; no preflight.


def test_operator_reads_reject_substituted_or_malformed_success(cli):
    with http_fixture() as (origin, response, requests):
        page = {"project_id": PROJECT, "items": [SUMMARY], "next_cursor": None}
        bad_pages = [
            page | {"project_id": ACTOR},
            page | {"items": [SUMMARY, SUMMARY]},
            page | {"items": [SUMMARY | {"project_id": ACTOR}]},
            page | {"items": [SUMMARY | {"title": "manager-only"}]},
            page | {"items": [SUMMARY | {"status": "unknown"}]},
            page | {"items": [SUMMARY | {"updated_at": "bad"}]},
            page | {"items": [], "next_cursor": "opaque"},
            page | {"next_cursor": ""},
            page | {"extra": True},
        ]
        for field in SUMMARY:
            item = deepcopy(SUMMARY)
            del item[field]
            bad_pages.append(page | {"items": [item]})
        for body in bad_pages:
            response["body"] = json.dumps(body).encode()
            assert_failure(invoke(cli, origin, "list", PROJECT), "invalid_api_response")

        bad_contexts = [
            CONTEXT | {"project_id": ACTOR},
            CONTEXT | {"task_id": ACTOR},
            CONTEXT | {"locked_review_policy_generation": 0},
            CONTEXT | {"locked_review_policy_generation": -1},
            CONTEXT | {"locked_review_policy_generation": "1"},
            CONTEXT | {"locked_review_policy_generation": 1.5},
            CONTEXT | {"locked_revision_policy_generation": None},
            CONTEXT | {"locked_post_submit_checker_policy_hash": "bad"},
            CONTEXT | {"locked_contribution_policy_version_id": "bad"},
            CONTEXT | {"policy_body": {"private": True}},
        ]
        for field in CONTEXT:
            body = deepcopy(CONTEXT)
            del body[field]
            bad_contexts.append(body)
        for body in bad_contexts:
            response["body"] = json.dumps(body).encode()
            assert_failure(
                invoke(cli, origin, "locked-context", PROJECT, TASK),
                "invalid_api_response",
            )
        response["body"] = json.dumps(
            CONTEXT
            | {
                "locked_review_policy_generation": 2**100,
                "locked_revision_policy_generation": 2**100,
            }
        ).encode()
        accepted = invoke(cli, origin, "locked-context", PROJECT, TASK)
        assert accepted.returncode == 0, accepted.stderr
        assert json.loads(accepted.stdout)["locked_review_policy_generation"] == 2**100
        assert len(requests) == len(bad_pages) + len(bad_contexts) + 1


def test_operator_task_invalid_arguments_and_removed_start_never_send(cli):
    with http_fixture() as (origin, _response, requests):
        for args in (
            ("start", TASK, "--reason", "ready", "--idempotency-key", KEY),
            ("list", "bad"),
            ("list", PROJECT, "--limit", "0"),
            ("list", PROJECT, "--cursor", ""),
            ("locked-context", "bad", TASK),
            ("locked-context", PROJECT, "bad"),
        ):
            assert_failure(invoke(cli, origin, *args), "invalid_arguments", 2)
        assert requests == []
