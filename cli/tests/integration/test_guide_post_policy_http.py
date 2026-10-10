"""One exact public policy read, including historical and hostile wire packages."""

from copy import deepcopy
import json
from urllib.parse import quote

from test_contributor_task_mutations import canonical_error
from test_guide_approval_http import receipt
from test_guide_create_http import GUIDE, SETUP
from test_guide_proposal_http import COMPILATION, HASH, OTHER, proposal
from test_http_boundary import PROJECT, TOKEN, assert_failure, http_fixture

POLICY = "018f0ebc-7966-7e8d-bc4d-1cae1e00000c"
SELECTORS = (PROJECT, GUIDE, COMPILATION, POLICY)
LARGE = 9223372036854775808


def package():
    source = proposal()
    source["target"].update(
        post_catalogue_id="workstream.post_submission_checkers",
        post_catalogue_version="v0.1",
        post_catalogue_schema_version="post_submission_checker_capability_projection",
    )
    upstream = receipt()
    source.update(
        artifact_policy_status="approved",
        current_approval_operation_id=upstream["operation_id"],
        current_approval_output_digest=HASH,
        post_submit_policy_id=POLICY,
    )
    return {
        "target": {
            "proposal": deepcopy(source["target"]),
            "upstream": upstream,
            "upstream_output_digest": HASH,
            "policy_id": POLICY,
            "projection_operation_id": OTHER,
            "policy_hash": HASH,
            "predecessor_policy_id": None,
        },
        "policy": {
            "schema_version": "post_submit_checker_policy",
            "compiler_version": "workstream-post-submit-compiler",
            "project_id": PROJECT,
            "guide_version": source["target"]["guide_version"],
            "catalogue_id": source["target"]["post_catalogue_id"],
            "catalogue_source_version": "v0.1",
            "catalogue_schema_version": source["target"]["post_catalogue_schema_version"],
            "catalogue_manifest_sha256": HASH,
            "entries": [
                {
                    "checker_id": "content_required",
                    "definition_version": "v0.1",
                    "implementation_version": "content_required",
                    "classification": "platform_default",
                    "configuration": {},
                }
            ],
            "blocking_severities": ["critical", "high"],
        },
        "proposal": source,
        "activation_context": {
            "guide_mutation_generation": LARGE,
            "review": None,
            "revision": None,
            "contribution": None,
            "expected_previous_active_guide_id": None,
            "expected_previous_active_guide_generation": None,
            "post_approval_operation_id": None,
            "post_approval_output_digest": None,
        },
        "lifecycle_status": "compiled",
        "current": True,
        "approval_operation_id": None,
        "correction": None,
    }


def invoke(cli, origin, selectors=SELECTORS, output="json", token=TOKEN):
    return cli(origin, token, "-o", output, "project", "guide", "post-policy", *selectors)


def test_post_policy_exact_read_history_defaults_and_terminal_safety(cli):
    with http_fixture() as (origin, response, requests):
        bodies = [package()]
        approved = package()
        approved.update(lifecycle_status="approved", approval_operation_id=OTHER)
        approved["activation_context"].update(
            review={"policy_id": GUIDE, "generation": LARGE, "policy_hash": HASH},
            revision={"policy_id": SETUP, "generation": LARGE, "policy_hash": HASH},
            contribution={"contribution_policy_id": GUIDE, "contribution_policy_version_id": OTHER},
            expected_previous_active_guide_id=GUIDE,
            expected_previous_active_guide_generation=LARGE,
            post_approval_operation_id=OTHER,
            post_approval_output_digest=HASH,
        )
        bodies.append(approved)
        historical = deepcopy(approved)
        historical.update(
            lifecycle_status="superseded",
            current=False,
            correction={
                "operation_id": OTHER,
                "target_digest": HASH,
                "successor_setup_run_id": SETUP,
                "successor_setup_generation": LARGE,
                "feedback_hash": HASH,
                "status": "correction_requested",
            },
        )
        historical["proposal"].update(current=False, post_submit_policy_id=None)
        historical["target"]["predecessor_policy_id"] = GUIDE
        bodies.append(historical)
        defaults = deepcopy(historical)
        for key in (
            "schema_version",
            "compiler_version",
            "catalogue_id",
            "catalogue_source_version",
            "catalogue_schema_version",
        ):
            del defaults["policy"][key]
        del defaults["correction"]["status"]
        del defaults["target"]["predecessor_policy_id"]
        bodies.append(defaults)
        for value in bodies:
            response["body"] = json.dumps(value).encode()
            result = invoke(cli, origin)
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert json.loads(result.stdout) == value
            assert requests[-1] == (
                "GET",
                "/api/v1/projects/{}/guides/{}/compilations/{}/post-submission-policies/{}".format(
                    *SELECTORS
                ),
                "Bearer " + TOKEN,
            )
        compact = tuple(x.replace("-", "") for x in SELECTORS)
        assert invoke(cli, origin, compact).returncode == 0
        assert requests[-1][1].endswith("/" + quote(compact[-1]))
        historical["proposal"]["result"]["setup_notes"] = ["Untrusted \x1b[31m\r\npolicy"]
        response["body"] = json.dumps(historical).encode()
        result = invoke(cli, origin, output="text")
        assert result.returncode == 0 and result.stderr == ""
        assert "not approval or activation" in result.stdout
        assert "\x1b" not in result.stdout and "\r" not in result.stdout
        assert len(requests) == len(bodies) + 2


def test_post_policy_rejects_valid_uuid_selected_policy_substitution(cli):
    with http_fixture() as (origin, response, requests):
        value = package()
        value["target"]["policy_id"] = OTHER
        response["body"] = json.dumps(value).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")
        assert len(requests) == 1


def test_post_policy_rejects_incomplete_malformed_and_cross_resource_packages(cli):
    mutations = [
        (("target", "proposal", "source_snapshot_id"), GUIDE),
        (("target", "upstream", "artifact_policy_id"), GUIDE),
        (("target", "upstream", "operation_id"), "not-uuid"),
        (("target", "upstream", "target_digest"), "sha256:" + "b" * 64),
        (("target", "projection_operation_id"), "not-uuid"),
        (("target", "policy_hash"), "bad"),
        (("target", "upstream", "acknowledged_warning_hashes"), [None]),
        (("target", "proposal", "setup_generation"), 0),
        (("policy", "project_id"), OTHER),
        (("policy", "guide_version"), "wrong"),
        (("policy", "catalogue_manifest_sha256"), "sha256:" + "b" * 64),
        (("policy", "entries"), [None]),
        (
            ("policy", "entries"),
            [
                {
                    "checker_id": "a",
                    "definition_version": "v0.1",
                    "implementation_version": "a",
                    "classification": "platform_default",
                    "configuration": {"unexpected": True},
                }
            ],
        ),
        (("policy", "blocking_severities"), [None, "high"]),
        (("policy", "schema_version"), None),
        (("activation_context", "guide_mutation_generation"), True),
        (
            ("activation_context", "review"),
            {"policy_id": GUIDE, "generation": None, "policy_hash": HASH},
        ),
        (
            ("activation_context", "contribution"),
            {"contribution_policy_id": "bad", "contribution_policy_version_id": OTHER},
        ),
        (("activation_context", "expected_previous_active_guide_id"), GUIDE),
        (("activation_context", "post_approval_operation_id"), OTHER),
        (("approval_operation_id",), OTHER),
        (("lifecycle_status",), "accepted"),
        (("proposal", "result", "findings"), [None]),
        (
            ("correction",),
            {
                "operation_id": OTHER,
                "target_digest": HASH,
                "successor_setup_run_id": SETUP,
                "successor_setup_generation": 0,
                "feedback_hash": HASH,
            },
        ),
    ]
    with http_fixture() as (origin, response, requests):
        for path, replacement in mutations:
            value = package()
            node = value
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = replacement
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        for field in package():
            value = package()
            del value[field]
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        for path in (
            ("target",),
            ("policy",),
            ("activation_context",),
            ("proposal",),
            ("proposal", "target"),
        ):
            value = package()
            node = value
            for key in path:
                node = node[key]
            node["unknown"] = 1
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        response["body"] = (
            json.dumps(package())
            .replace('"current": true', '"current": true, "current": false', 1)
            .encode()
        )
        assert_failure(invoke(cli, origin), "invalid_api_response")
        assert len(requests) == len(mutations) + len(package()) + 6


def test_post_policy_local_selectors_and_transport_fail_closed(cli):
    with http_fixture() as (origin, response, requests):
        for position in range(4):
            args = list(SELECTORS)
            args[position] = "../not-a-uuid"
            assert_failure(invoke(cli, origin, args), "invalid_arguments", exit_code=2)
        assert requests == []
        for status in (401, 403, 404):
            response.update(status=status, body=json.dumps(canonical_error()).encode())
            result = invoke(cli, origin)
            assert result.returncode == 1 and result.stdout == ""
            assert json.loads(result.stderr)["error"]["status"] == status
        response.update(status=302, headers={"Location": origin + "/other"}, body=b"")
        assert_failure(invoke(cli, origin), "redirect_refused")
        response.update(
            status=200,
            headers={"Content-Type": "application/json"},
            body=b" " * (8 * 1024 * 1024 + 1),
        )
        assert_failure(invoke(cli, origin), "invalid_api_response")
        response.update(body=b"{broken")
        assert_failure(invoke(cli, origin), "invalid_api_response")
        response.update(drop=True)
        assert_failure(invoke(cli, origin), "service_unavailable")
        assert len(requests) == 7
