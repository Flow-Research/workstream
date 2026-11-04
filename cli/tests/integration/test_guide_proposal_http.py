"""Built CLI inspects one exact public proposal; it does not execute decisions."""

import json
from urllib.parse import quote

import pytest

from test_contributor_task_mutations import canonical_error
from test_guide_create_http import GUIDE, SETUP
from test_http_boundary import PROJECT, TOKEN, assert_failure, http_fixture

COMPILATION = "018f0ebc-7966-7e8d-bc4d-1cae1e00000a"
OTHER = "018f0ebc-7966-7e8d-bc4d-1cae1e00000b"
HASH = "sha256:" + "a" * 64


def proposal():
    location = {
        "document_number": 1,
        "start_page": None,
        "end_page": None,
        "section": None,
    }
    specification = {
        "evaluation_method": "Inspect the submitted results.",
        "inputs": [
            {
                "input_id": "submission_package",
                "kind": "package",
                "purpose": "Inspect the submitted package.",
            },
            {
                "input_id": "results_file",
                "kind": "relative_file",
                "relative_path": "reports/results.json",
                "purpose": "Read the required results.",
            },
        ],
        "check_steps": ["Open the results file and validate its required fields."],
        "pass_conditions": ["The required results are present and valid."],
        "failure_findings": [
            {
                "code": "results.missing",
                "level": "error",
                "condition": "The results file is absent.",
                "message": "Add the required results file.",
            },
            {
                "code": "results.extra",
                "level": "warning",
                "condition": "The results include an optional extra field.",
                "message": "Review the optional field.",
            },
        ],
        "positive_tests": ["A package with a complete results file passes."],
        "negative_tests": [
            {
                "name": "missing_results",
                "scenario": "The package omits the results file.",
                "expected_verdict": "failed",
                "expected_finding_codes": ["results.missing"],
            },
            {
                "name": "extra_results_field",
                "scenario": "The results file includes an optional extra field.",
                "expected_verdict": "passed",
                "expected_finding_codes": ["results.extra"],
            },
        ],
        "implementation_needs": [
            "Read the submitted package and inspect the named results file."
        ],
        "inability_to_evaluate": [
            {
                "code": "material_unavailable",
                "condition": "The submitted package cannot be read.",
            },
        ],
    }
    return {
        "target": {
            "project_id": PROJECT,
            "guide_id": GUIDE,
            "compilation_id": COMPILATION,
            "result_schema_version": "project_guide_check_specification.v1",
            "guide_version": "evaluation-guide",
            "source_snapshot_id": OTHER,
            "source_snapshot_hash": HASH,
            "setup_run_id": SETUP,
            "setup_generation": 1,
            "finalization_id": OTHER,
            "finalization_facts_digest": HASH,
            "result_hash": HASH,
            "component_hashes": {
                "schema_version": "project_guide_check_specification_hashes.v1",
                **dict.fromkeys(
                    (
                        "sufficiency_hash",
                        "artifact_policy_hash",
                        "requirement_inventory_hash",
                        "pre_submit_hash",
                        "post_submit_hash",
                    ),
                    HASH,
                ),
            },
            "artifact_policy_id": OTHER,
            "artifact_policy_hash": HASH,
            "artifact_projection_operation_id": OTHER,
            "artifact_projection_output_digest": HASH,
        },
        "target_digest": HASH,
        "result": {
            "status": "draft_ready_with_warnings",
            "findings": [
                {
                    "severity": "warning",
                    "code": "guide.warning",
                    "message": "Confirm the required evidence.",
                    "evidence_refs": [location],
                }
            ],
            "submission_artifact_policy": {
                "packaging": "zip",
                "maximum_file_size_bytes": 1000,
                "maximum_package_size_bytes": 10000,
                "maximum_archive_size_bytes": None,
                "maximum_archive_entries": 9223372036854775808,
                "allowed_storage_schemes": ["artifact"],
                "required_artifacts": ["answer.md"],
                "forbidden_artifacts": ["secret*"],
                "required_evidence": ["results"],
                "attestation_terms": ["rights_confirmed"],
            },
            "requirements": [
                {
                    "suggestion_id": "results",
                    "statement": "Provide evaluation results.",
                    "stage": "pre_submit",
                    "classification_rationale": "The guide asks for results before submission.",
                    "check_specification": specification,
                    "evidence_refs": [location],
                },
                {
                    "suggestion_id": "quality",
                    "statement": "Evaluate result quality after submission.",
                    "stage": "post_submit",
                    "classification_rationale": "The guide asks for quality evidence after submission.",
                    "check_specification": specification
                    | {
                        "evaluation_method": "Assess the submitted results against the rubric."
                    },
                    "evidence_refs": [location],
                },
            ],
            "setup_notes": ["Proposal only."],
            "agent_name": "ProjectGuideCompilationAgent",
            "agent_version": "v1",
            "schema_version": "project_guide_check_specification.v1",
        },
        "current": True,
        "artifact_policy_status": "draft",
        "warning_hashes": [HASH],
        "current_approval_operation_id": None,
        "current_approval_output_digest": None,
        "post_submit_policy_id": None,
    }


def invoke(
    cli, origin, selectors=(PROJECT, GUIDE, COMPILATION), output="json", token=TOKEN
):
    return cli(origin, token, "-o", output, "project", "guide", "proposal", *selectors)


def test_proposal_exact_selector_raw_bytes_and_escaped_text(cli):
    with http_fixture() as (origin, response, requests):
        for spell in (
            lambda x: x,
            lambda x: x.replace("-", ""),
            lambda x: "{" + x + "}",
            lambda x: "urn:uuid:" + x,
        ):
            selectors = tuple(spell(x) for x in (PROJECT, GUIDE, COMPILATION))
            response["body"] = json.dumps(proposal(), indent=2).encode()
            result = invoke(cli, origin, selectors)
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert result.stdout.strip().encode() == response["body"]
            assert requests[-1] == (
                "GET",
                "/api/v1/projects/{}/guides/{}/compilations/{}/proposal".format(
                    *(quote(x, safe=":") for x in selectors)
                ),
                "Bearer " + TOKEN,
            )
        value = proposal()
        value["result"]["findings"][0]["message"] = "Diagnostic é\n\x1b[32m\u202e"
        response["body"] = json.dumps(value, ensure_ascii=False).encode()
        rendered = invoke(cli, origin, output="text")
        assert rendered.returncode == 0 and rendered.stderr == "", rendered.stderr
        assert rendered.stdout.startswith("Guide proposal (inspection only)\nStatus: ")
        assert "\x1b" not in rendered.stdout and "\u202e" not in rendered.stdout
        assert "\\u000A\\u001B[32m\\u202E" in rendered.stdout
        for section in (
            "Findings (1)",
            "Submission artifact policy",
            "PRE check suggestions (1)",
            "POST check suggestions (1)",
            "Check steps",
            "Pass conditions",
            "Failure findings",
            "Positive tests",
            "Negative tests",
            "Implementation needs",
            "Cannot evaluate when",
            "Setup notes (1)",
        ):
            assert section in rendered.stdout
        assert "document 1" in rendered.stdout
        assert "material_unavailable" in rendered.stdout
        assert "9223372036854775808" in rendered.stdout
        assert '"target":' not in rendered.stdout
        assert response["commands"] == [] and response["updates"] == []


def test_proposal_nullable_lineage_and_large_integer(cli):
    value = proposal()
    for key in (
        "current_approval_operation_id",
        "current_approval_output_digest",
        "post_submit_policy_id",
    ):
        del value[key]
    value["result"].update(
        status="guide_blocked", requirements=[], submission_artifact_policy=None
    )
    value["result"].pop("setup_notes")
    with http_fixture() as (origin, response, _):
        for generation in (1, 9223372036854775808):
            value["target"]["setup_generation"] = generation
            response["body"] = json.dumps(value).encode()
            result = invoke(cli, origin)
            assert result.returncode == 0 and json.loads(result.stdout) == value, (
                result.stderr
            )
        for malformed in ('"1"', "1.5", "1e2", "true", "{}", "[]"):
            response["body"] = (
                json.dumps(value)
                .replace(
                    '"setup_generation": 9223372036854775808',
                    '"setup_generation": ' + malformed,
                )
                .encode()
            )
            assert_failure(invoke(cli, origin), "invalid_api_response")


def test_proposal_rejects_substituted_selectors_and_invalid_record_ids(cli):
    with http_fixture() as (origin, response, _):
        for key in ("project_id", "guide_id", "compilation_id"):
            value = proposal()
            value["target"][key] = OTHER
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        for key in (
            "source_snapshot_id",
            "setup_run_id",
            "finalization_id",
            "artifact_policy_id",
            "artifact_projection_operation_id",
        ):
            value = proposal()
            value["target"][key] = "not-uuid"
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        for key in (
            "current_approval_operation_id",
            "post_submit_policy_id",
            "current_approval_output_digest",
            "target_digest",
        ):
            response["body"] = json.dumps(proposal() | {key: "not-identity"}).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")


def test_proposal_accepts_warning_only_check_and_rejects_incomplete_policy_identity(
    cli,
):
    with http_fixture() as (origin, response, _):
        value = proposal()
        for suggestion in value["result"]["requirements"]:
            specification = suggestion["check_specification"]
            specification["failure_findings"] = [specification["failure_findings"][1]]
            specification["negative_tests"] = [specification["negative_tests"][1]]
        response["body"] = json.dumps(value).encode()
        assert invoke(cli, origin).returncode == 0

        for field in (
            "artifact_policy_id",
            "artifact_policy_hash",
            "artifact_projection_operation_id",
            "artifact_projection_output_digest",
        ):
            changed = proposal()
            changed["target"][field] = None
            response["body"] = json.dumps(changed).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")


@pytest.mark.parametrize(
    "path,invalid",
    [
        (("target", "result_schema_version"), "other"),
        (("target", "pre_catalogue_id"), "old-catalogue"),
        (("target", "component_hashes", "schema_version"), "other"),
        (("target", "component_hashes", "post_submit_hash"), "not-digest"),
        (("result", "schema_version"), "other"),
        (("result", "requirements", 0, "stage"), "human_review"),
        (("result", "requirements", 0, "suggestion_id"), "Invalid"),
        (("result", "requirements", 0, "evidence_refs"), []),
        (
            (
                "result",
                "requirements",
                0,
                "check_specification",
                "runtime_dependencies",
            ),
            [],
        ),
        (("result", "requirements", 0, "check_specification", "check_steps"), []),
        (
            (
                "result",
                "requirements",
                0,
                "check_specification",
                "inputs",
                0,
                "relative_path",
            ),
            "../secret",
        ),
        (
            (
                "result",
                "requirements",
                0,
                "check_specification",
                "failure_findings",
                0,
                "level",
            ),
            "coverage_incomplete",
        ),
        (
            (
                "result",
                "requirements",
                0,
                "check_specification",
                "negative_tests",
                0,
                "expected_verdict",
            ),
            "passed",
        ),
        (
            (
                "result",
                "requirements",
                0,
                "check_specification",
                "inability_to_evaluate",
                0,
                "code",
            ),
            "results.missing",
        ),
        (("result", "capability_suggestions"), []),
        (("result", "submission_artifact_policy", "maximum_archive_entries"), "20"),
    ],
)
def test_proposal_rejects_obsolete_or_malformed_nested_contract(cli, path, invalid):
    value = proposal()
    target = value
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = invalid
    with http_fixture() as (origin, response, _):
        response["body"] = json.dumps(value).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")


@pytest.mark.parametrize(
    "field",
    [
        "target",
        "target_digest",
        "result",
        "current",
        "warning_hashes",
    ],
)
def test_proposal_missing_required_outer_field_rejected(cli, field):
    value = proposal()
    del value[field]
    with http_fixture() as (origin, response, _):
        response["body"] = json.dumps(value).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")


@pytest.mark.parametrize(
    "field",
    [
        "status",
        "agent_version",
        "agent_name",
        "schema_version",
        "findings",
        "requirements",
        "submission_artifact_policy",
    ],
)
def test_proposal_missing_required_result_field_rejected(cli, field):
    value = proposal()
    del value["result"][field]
    with http_fixture() as (origin, response, _):
        response["body"] = json.dumps(value).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")


@pytest.mark.parametrize(
    "field",
    [
        "status",
        "agent_version",
        "agent_name",
        "schema_version",
        "findings",
        "requirements",
    ],
)
def test_proposal_null_required_result_field_rejected(cli, field):
    value = proposal()
    value["result"][field] = None
    with http_fixture() as (origin, response, _):
        response["body"] = json.dumps(value).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")


def test_proposal_rejects_private_nested_fields_and_null_array_members(cli):
    with http_fixture() as (origin, response, _):
        for field in (
            "source_item_id",
            "document_version_id",
            "sha256",
            "provider_url",
            "raw_excerpt",
        ):
            value = proposal()
            value["result"]["requirements"][0]["evidence_refs"][0][field] = "private"
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        for field in ("findings", "requirements", "warning_hashes"):
            value = proposal()
            if field == "warning_hashes":
                value[field] = [None]
            else:
                value["result"][field] = [None]
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")


def test_proposal_check_input_paths_and_prose_match_backend(cli):
    from pydantic import ValidationError
    from app.modules.projects.api.guide_proposal_package import (
        GuideProposalReviewPackage,
    )

    with http_fixture() as (origin, response, _):
        for path in (
            "reports/{summary}",
            "reports/result}",
            "reports/Café.txt",
            "reports/結果.txt",
            "reports/á" + "\u0301" * 31 + ".txt",
            "結" * 500,
        ):
            value = proposal()
            value["result"]["requirements"][0]["check_specification"]["inputs"][1][
                "relative_path"
            ] = path
            validated = GuideProposalReviewPackage.model_validate(value)
            response["body"] = validated.model_dump_json().encode()
            result = invoke(cli, origin)
            assert result.returncode == 0, result.stderr
            assert (
                json.loads(result.stdout)["result"]["requirements"][0][
                    "check_specification"
                ]["inputs"][1]["relative_path"]
                == path
            )

        for path in ("reports/\u200bhidden.txt", "reports/a\u0085b.txt", "結" * 501):
            value = proposal()
            value["result"]["requirements"][0]["check_specification"]["inputs"][1][
                "relative_path"
            ] = path
            with pytest.raises(ValidationError):
                GuideProposalReviewPackage.model_validate(value)
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")

        for prose in (" ", "\t\n", "結" * 1000):
            value = proposal()
            value["result"]["requirements"][0]["check_specification"][
                "evaluation_method"
            ] = prose
            validated = GuideProposalReviewPackage.model_validate(value)
            response["body"] = validated.model_dump_json().encode()
            assert invoke(cli, origin).returncode == 0

        for prose in ("", "結" * 1001):
            value = proposal()
            value["result"]["requirements"][0]["check_specification"][
                "evaluation_method"
            ] = prose
            with pytest.raises(ValidationError):
                GuideProposalReviewPackage.model_validate(value)
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")


def test_proposal_response_bound_and_safe_failures(cli):
    from app.modules.projects.api.guide_proposal_package import (
        GuideProposalReviewPackage,
    )

    with http_fixture() as (origin, response, requests):
        value = proposal()
        suggestion = value["result"]["requirements"][0]
        value["result"]["requirements"] = [
            suggestion | {"suggestion_id": f"check_{index}", "statement": "x" * 1000}
            for index in range(100)
        ]
        GuideProposalReviewPackage.model_validate(value)
        response["body"] = json.dumps(value).encode()
        assert len(response["body"]) > 65536
        assert invoke(cli, origin).returncode == 0
        response["body"] = b" " * (8 * 1024 * 1024) + b"{}"
        assert_failure(invoke(cli, origin), "invalid_api_response")
        response["headers"]["Content-Type"] = "text/plain"
        response["body"] = json.dumps(proposal()).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")
        response["headers"]["Content-Type"] = "application/json"
        response["status"] = 404
        response["body"] = json.dumps(canonical_error("proposal_unavailable")).encode()
        denied = invoke(cli, origin)
        assert_failure(denied, "proposal_unavailable")
        assert json.loads(denied.stderr)["error"]["status"] == 404
        response["body"] = json.dumps(canonical_error("credential_canary_AAA")).encode()
        assert_failure(invoke(cli, origin, token="credential_canary_AAA"), "api_error")
        response["status"] = 302
        response["headers"]["Location"] = origin + "/credential-sink"
        response["body"] = b""
        count = len(requests)
        assert_failure(invoke(cli, origin), "redirect_refused")
        assert len(requests) == count + 1 and not any(
            x[1] == "/credential-sink" for x in requests
        )
        count = len(requests)
        for index in range(3):
            selectors = [PROJECT, GUIDE, COMPILATION]
            selectors[index] = "../other"
            assert_failure(invoke(cli, origin, selectors), "invalid_arguments", 2)
        assert len(requests) == count


def test_proposal_intake_integer_boundaries_and_nulls(cli):
    from app.modules.projects.api.guide_proposal_package import (
        GuideProposalReviewPackage,
    )

    ceiling = 10 * 1024**3
    with http_fixture() as (origin, response, _):
        for field in (
            "maximum_file_size_bytes",
            "maximum_package_size_bytes",
            "maximum_archive_size_bytes",
            "maximum_archive_entries",
        ):
            upper = (
                ceiling
                if field in ("maximum_file_size_bytes", "maximum_package_size_bytes")
                else 9223372036854775808
            )
            for boundary in (1, upper):
                value = proposal()
                policy = value["result"]["submission_artifact_policy"]
                policy["maximum_file_size_bytes"] = 1
                policy["maximum_package_size_bytes"] = ceiling
                policy[field] = boundary
                GuideProposalReviewPackage.model_validate(value)
                response["body"] = json.dumps(value).encode()
                assert invoke(cli, origin).returncode == 0
            for boundary in (-1, 0):
                value = proposal()
                value["result"]["submission_artifact_policy"][field] = boundary
                response["body"] = json.dumps(value).encode()
                assert_failure(invoke(cli, origin), "invalid_api_response")
        for omit in (False, True):
            value = proposal()
            policy = value["result"]["submission_artifact_policy"]
            for field in ("maximum_file_size_bytes", "maximum_package_size_bytes"):
                if omit:
                    del policy[field]
                else:
                    policy[field] = None
            GuideProposalReviewPackage.model_validate(value)
            response["body"] = json.dumps(value).encode()
            assert invoke(cli, origin).returncode == 0
