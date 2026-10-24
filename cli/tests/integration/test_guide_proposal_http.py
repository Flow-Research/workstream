"""Built CLI inspects one exact public proposal; it does not execute decisions."""

from copy import deepcopy
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
    binding = {
        "requirement_id": "results",
        "capability_id": "results.present",
        "capability_version": "v1",
        "stage": "pre_submit",
        "parameters": [{"name": "required", "value": True}],
    }
    pre_specification = {
        "evaluation_method": "static_inspection",
        "execution_mode": "bounded_pre_submit",
        "maximum_duration_seconds": 45,
        "stage_rationale": "This bounded package inspection can finish before submission.",
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
        "runtime_dependencies": [
            {
                "dependency_id": "results_parser",
                "kind": "checker_tool",
                "provisioning": "checker_implementation",
                "purpose": "Parse and validate the results file.",
                "unavailable_code": "implementation_unavailable",
            }
        ],
        "infrastructure_failures": [
            {
                "code": "material_unavailable",
                "condition": "The submitted package cannot be read.",
            },
            {
                "code": "implementation_unavailable",
                "condition": "The required checker implementation is unavailable.",
            },
        ],
    }
    return {
        "target": {
            "project_id": PROJECT,
            "guide_id": GUIDE,
            "compilation_id": COMPILATION,
            "guide_version": "evaluation-guide",
            "source_snapshot_id": OTHER,
            "source_snapshot_hash": HASH,
            "setup_run_id": SETUP,
            "setup_generation": 1,
            "finalization_id": OTHER,
            "finalization_facts_digest": HASH,
            "result_hash": HASH,
            "component_hashes": dict.fromkeys(
                (
                    "sufficiency_hash",
                    "artifact_policy_hash",
                    "requirement_inventory_hash",
                    "pre_submit_hash",
                    "post_submit_hash",
                    "capability_suggestions_hash",
                    "setup_notes_hash",
                ),
                HASH,
            ),
            "pre_catalogue_id": "pre",
            "pre_catalogue_version": "v1",
            "pre_catalogue_schema_version": "v1",
            "pre_catalogue_manifest_hash": HASH,
            "post_catalogue_id": "post",
            "post_catalogue_version": "v1",
            "post_catalogue_schema_version": "v1",
            "post_catalogue_manifest_hash": HASH,
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
                    "requirement_id": "results",
                    "statement": "Provide evaluation results.",
                    "disposition": "supported_pre_submit",
                    "classification_rationale": "A bounded static check can evaluate this before submission.",
                    "check_specification": pre_specification,
                    "platform_coverage": {
                        "capability_id": "submission.zip",
                        "capability_version": "v1",
                        "stage": "pre_submit",
                    },
                    "evidence_refs": [location],
                },
                {
                    "requirement_id": "quality",
                    "statement": "Evaluate result quality after submission.",
                    "disposition": "supported_post_submit",
                    "classification_rationale": "Execution may take longer than the intake budget.",
                    "check_specification": pre_specification
                    | {
                        "evaluation_method": "isolated_execution",
                        "execution_mode": "background",
                        "maximum_duration_seconds": 300,
                        "stage_rationale": "Run the evaluator in the background.",
                        "runtime_dependencies": [
                            {
                                "dependency_id": "execution_runner",
                                "kind": "isolated_execution",
                                "provisioning": "current_runner",
                                "purpose": "Run the project evaluator offline.",
                                "unavailable_code": "implementation_unavailable",
                            }
                        ],
                    },
                    "platform_coverage": None,
                    "evidence_refs": [location],
                },
                {
                    "requirement_id": "review_decision",
                    "statement": "A reviewer makes the final decision.",
                    "disposition": "human_review",
                    "classification_rationale": "The guide explicitly assigns this judgment to a reviewer.",
                    "platform_coverage": None,
                    "evidence_refs": [location],
                },
            ],
            "pre_submit_bindings": [binding],
            "post_submit_bindings": [
                binding
                | {
                    "requirement_id": "quality",
                    "stage": "post_submit",
                    "parameters": [
                        {"name": "threshold", "value": 0.9},
                        {"name": "labels", "value": ["research", 2, True]},
                    ],
                }
            ],
            "capability_suggestions": [
                {
                    "requirement_id": "future",
                    "stage": "post_submit",
                    "title": "Additional evaluation",
                    "rationale": "An optional evaluator would help.",
                    "evidence_refs": [location],
                }
            ],
            "setup_notes": ["Proposal only."],
            "agent_name": "ProjectGuideCompilationAgent",
            "agent_version": "v1",
            "schema_version": "project_guide_compilation_result.v1",
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


def test_proposal_complete_exact_selector_and_terminal_safe_observation(cli):
    with http_fixture() as (origin, response, requests):
        for status, current in (
            ("draft_ready", True),
            ("draft_ready_with_warnings", True),
            ("guide_blocked", False),
        ):
            value = proposal()
            value["result"]["status"], value["current"] = status, current
            if status == "guide_blocked":
                value["result"]["submission_artifact_policy"] = None
                value["artifact_policy_status"] = None
                for key in (
                    "artifact_policy_id",
                    "artifact_policy_hash",
                    "artifact_projection_operation_id",
                    "artifact_projection_output_digest",
                ):
                    value["target"][key] = None
            for spell in (
                lambda x: x,
                lambda x: x.replace("-", ""),
                lambda x: "{" + x + "}",
                lambda x: "urn:uuid:" + x,
            ):
                selectors = tuple(spell(x) for x in (PROJECT, GUIDE, COMPILATION))
                response["body"] = json.dumps(value, indent=2).encode()
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
        text = invoke(cli, origin, output="text")
        assert text.returncode == 0 and text.stderr == "", text.stderr
        assert text.stdout.startswith("Guide proposal (inspection only)\nStatus: ")
        assert "\x1b" not in text.stdout and "\u202e" not in text.stdout
        assert "\\u000A\\u001B[32m\\u202E" in text.stdout
        assert "9223372036854775808" in text.stdout
        for section in (
            "Findings (1)",
            "Submission artifact policy",
            "PRE requirements (1)",
            "POST requirements (1)",
            "Non-checker requirements (1)",
            "Check steps",
            "Pass conditions",
            "Failure findings",
            "Positive tests",
            "Negative tests",
            "Runtime dependencies",
            "Infrastructure failures",
            "Capability suggestions (1)",
            "Setup notes (1)",
        ):
            assert section in text.stdout
        assert "document 1" in text.stdout
        assert "results_parser" in text.stdout
        assert "required=true" in text.stdout
        assert '"target":' not in text.stdout
        assert (
            len(requests) == 13
            and response["commands"] == []
            and response["updates"] == []
        )


def test_proposal_defaults_nullable_lineage_and_unbounded_integer(cli):
    value = proposal()
    for key in (
        "current_approval_operation_id",
        "current_approval_output_digest",
        "post_submit_policy_id",
    ):
        del value[key]
    value["result"] = {"status": "guide_blocked", "agent_version": "v1"}
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


def test_proposal_substituted_valid_resources_and_malformed_identities(cli):
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


def test_proposal_missing_null_unknown_and_private_nested_fields(cli):
    value = proposal()
    objects = [
        ((), ("target", "target_digest", "result", "current", "warning_hashes")),
        (
            ("target",),
            tuple(
                value["target"].keys()
                - {
                    "artifact_policy_id",
                    "artifact_policy_hash",
                    "artifact_projection_operation_id",
                    "artifact_projection_output_digest",
                }
            ),
        ),
        (("target", "component_hashes"), tuple(value["target"]["component_hashes"])),
        (("result",), ("status", "agent_version")),
        (("result", "findings", 0), ("severity", "code", "message")),
        (("result", "requirements", 0), ("requirement_id", "statement", "disposition")),
        (
            ("result", "requirements", 0, "check_specification"),
            (
                "evaluation_method",
                "execution_mode",
                "maximum_duration_seconds",
                "stage_rationale",
                "inputs",
                "check_steps",
                "pass_conditions",
                "failure_findings",
                "positive_tests",
                "negative_tests",
                "runtime_dependencies",
                "infrastructure_failures",
            ),
        ),
        (
            ("result", "requirements", 0, "check_specification", "inputs", 1),
            ("input_id", "kind", "purpose", "relative_path"),
        ),
        (
            ("result", "requirements", 0, "check_specification", "failure_findings", 0),
            ("code", "level", "condition", "message"),
        ),
        (
            ("result", "requirements", 0, "check_specification", "negative_tests", 0),
            ("name", "scenario", "expected_verdict", "expected_finding_codes"),
        ),
        (
            (
                "result",
                "requirements",
                0,
                "check_specification",
                "runtime_dependencies",
                0,
            ),
            ("dependency_id", "kind", "provisioning", "purpose", "unavailable_code"),
        ),
        (
            (
                "result",
                "requirements",
                0,
                "check_specification",
                "infrastructure_failures",
                0,
            ),
            ("code", "condition"),
        ),
        (
            ("result", "requirements", 0, "platform_coverage"),
            ("capability_id", "capability_version", "stage"),
        ),
        (
            ("result", "pre_submit_bindings", 0),
            ("requirement_id", "capability_id", "capability_version", "stage"),
        ),
        (("result", "pre_submit_bindings", 0, "parameters", 0), ("name", "value")),
        (("result", "post_submit_bindings", 0, "parameters", 0), ("name", "value")),
        (
            ("result", "capability_suggestions", 0),
            ("requirement_id", "stage", "title", "rationale", "evidence_refs"),
        ),
        (("result", "findings", 0, "evidence_refs", 0), ("document_number",)),
        (
            ("result", "submission_artifact_policy"),
            (),
        ),
    ]
    with http_fixture() as (origin, response, _):
        for path, required in objects:
            for key in (*required, "private_handle"):
                for mode in (
                    ("missing", "null") if key != "private_handle" else ("unknown",)
                ):
                    body = deepcopy(value)
                    obj = body
                    for component in path:
                        obj = obj[component]
                    if mode == "missing":
                        del obj[key]
                    else:
                        obj[key] = None if mode == "null" else "must-not-be-printed"
                    response["body"] = json.dumps(body).encode()
                    assert_failure(invoke(cli, origin), "invalid_api_response")
        for field in ("artifact_policy_status",):
            body = deepcopy(value)
            del body[field]
            response["body"] = json.dumps(body).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        for field in ("classification_rationale", "check_specification"):
            body = deepcopy(value)
            body["result"]["requirements"][0][field] = None
            response["body"] = json.dumps(body).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        for field in (
            "artifact_policy_id",
            "artifact_policy_hash",
            "artifact_projection_operation_id",
            "artifact_projection_output_digest",
        ):
            body = deepcopy(value)
            del body["target"][field]
            response["body"] = json.dumps(body).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        location = value["result"]["findings"][0]["evidence_refs"][0]
        for field in ("start_page", "end_page", "section"):
            body = deepcopy(value)
            del body["result"]["findings"][0]["evidence_refs"][0][field]
            response["body"] = json.dumps(body).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        assert location["document_number"] == 1
        response["body"] = (json.dumps(value)[:-1] + ', "current": false}').encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")


def test_proposal_rejects_null_array_members_and_parameter_objects(cli):
    with http_fixture() as (origin, response, _):
        for field in (
            "findings",
            "requirements",
            "pre_submit_bindings",
            "post_submit_bindings",
            "capability_suggestions",
            "setup_notes",
        ):
            for invalid in (None, [None]):
                value = proposal()
                value["result"][field] = invalid
                response["body"] = json.dumps(value).encode()
                assert_failure(invoke(cli, origin), "invalid_api_response")
        for invalid in (None, [None], ["x", None], {}, [{"instruction": "execute"}]):
            value = proposal()
            value["result"]["post_submit_bindings"][0]["parameters"][0]["value"] = (
                invalid
            )
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")


def test_proposal_accepts_backend_canonical_paths(cli):
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
            assert result.returncode == 0
            actual = json.loads(result.stdout)
            assert (
                actual["result"]["requirements"][0]["check_specification"]["inputs"][1][
                    "relative_path"
                ]
                == path
            )


def test_proposal_matches_backend_prose_bounds(cli):
    from pydantic import ValidationError

    from app.modules.projects.api.guide_proposal_package import (
        GuideProposalReviewPackage,
    )

    with http_fixture() as (origin, response, _):
        for text in (" ", "\t\n", "結" * 1000):
            value = proposal()
            value["result"]["requirements"][0]["check_specification"][
                "stage_rationale"
            ] = text
            validated = GuideProposalReviewPackage.model_validate(value)
            response["body"] = validated.model_dump_json().encode()
            result = invoke(cli, origin)
            assert result.returncode == 0
            assert (
                json.loads(result.stdout)["result"]["requirements"][0][
                    "check_specification"
                ]["stage_rationale"]
                == text
            )

        for text in ("", "結" * 1001):
            value = proposal()
            value["result"]["requirements"][0]["check_specification"][
                "stage_rationale"
            ] = text
            with pytest.raises(ValidationError):
                GuideProposalReviewPackage.model_validate(value)
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")


def test_proposal_rejects_backend_invalid_unicode_paths(cli):
    from pydantic import ValidationError

    from app.modules.projects.api.guide_proposal_package import (
        GuideProposalReviewPackage,
    )

    with http_fixture() as (origin, response, _):
        for path in (
            "reports/\u200bhidden.txt",
            "reports/a\u0085b.txt",
            "結" * 501,
        ):
            value = proposal()
            value["result"]["requirements"][0]["check_specification"]["inputs"][1][
                "relative_path"
            ] = path
            with pytest.raises(ValidationError):
                GuideProposalReviewPackage.model_validate(value)
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")


def test_proposal_specification_stage_semantics_and_historical_omission(cli):
    with http_fixture() as (origin, response, _):
        historical = proposal()
        for field in ("classification_rationale", "check_specification"):
            del historical["result"]["requirements"][0][field]
        response["body"] = json.dumps(historical).encode()
        result = invoke(cli, origin)
        assert result.returncode == 0 and json.loads(result.stdout) == historical

        warning_only = proposal()
        spec = warning_only["result"]["requirements"][0]["check_specification"]
        spec["failure_findings"] = [spec["failure_findings"][1]]
        spec["negative_tests"] = [spec["negative_tests"][1]]
        response["body"] = json.dumps(warning_only).encode()
        assert invoke(cli, origin).returncode == 0

        invalid_values = []

        value = proposal()
        del value["result"]["requirements"][0]["classification_rationale"]
        invalid_values.append(value)

        value = proposal()
        del value["result"]["requirements"][0]["check_specification"]
        invalid_values.append(value)

        value = proposal()
        value["result"]["requirements"][0]["evidence_refs"] = []
        invalid_values.append(value)

        value = proposal()
        value["result"]["requirements"][0]["check_specification"][
            "maximum_duration_seconds"
        ] = 61
        invalid_values.append(value)

        value = proposal()
        value["result"]["requirements"][0]["check_specification"]["execution_mode"] = (
            "background"
        )
        invalid_values.append(value)

        value = proposal()
        value["result"]["requirements"][1]["check_specification"][
            "maximum_duration_seconds"
        ] = 3601
        invalid_values.append(value)

        value = proposal()
        value["result"]["requirements"][0]["check_specification"]["negative_tests"][0][
            "expected_verdict"
        ] = "passed"
        invalid_values.append(value)

        value = proposal()
        value["result"]["requirements"][0]["check_specification"]["negative_tests"][1][
            "expected_verdict"
        ] = "failed"
        invalid_values.append(value)

        value = proposal()
        value["result"]["requirements"][0]["check_specification"]["inputs"][1][
            "relative_path"
        ] = "../results.json"
        invalid_values.append(value)

        value = proposal()
        value["result"]["requirements"][0]["check_specification"][
            "runtime_dependencies"
        ][0]["unavailable_code"] = "capacity_exceeded"
        invalid_values.append(value)

        value = proposal()
        value["result"]["requirements"][2]["check_specification"] = deepcopy(
            value["result"]["requirements"][0]["check_specification"]
        )
        invalid_values.append(value)

        value = proposal()
        value["result"]["requirements"][0]["check_specification"]["check_steps"] = []
        invalid_values.append(value)

        for value in invalid_values:
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")


def test_proposal_rejects_pre_model_evaluation_and_validates_post_runtime_gaps(cli):
    from app.modules.projects.api.guide_proposal_package import (
        GuideProposalReviewPackage,
    )

    with http_fixture() as (origin, response, _):
        value = proposal()
        requirement = value["result"]["requirements"][0]
        requirement["disposition"] = "pre_submit_capability_gap"
        specification = deepcopy(requirement["check_specification"])
        requirement["check_specification"] = specification
        specification["evaluation_method"] = "model_evaluation"
        specification["runtime_dependencies"] = [
            {
                "dependency_id": "quality_model",
                "kind": "model_service",
                "provisioning": "runtime_gap",
                "purpose": "Evaluate the submitted results with the configured model.",
                "unavailable_code": "implementation_unavailable",
            }
        ]
        value["result"]["pre_submit_bindings"] = []
        value["result"]["capability_suggestions"] = [
            {
                "requirement_id": "results",
                "stage": "pre_submit",
                "title": "Model quality evaluation",
                "rationale": "A model service implementation is required.",
                "evidence_refs": requirement["evidence_refs"],
            }
        ]
        # The public object and specification are otherwise valid. The CLI
        # rejects only the forbidden PRE placement of model evaluation.
        GuideProposalReviewPackage.model_validate(value)
        response["body"] = json.dumps(value).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")

        requirement["disposition"] = "post_submit_capability_gap"
        specification["execution_mode"] = "background"
        specification["maximum_duration_seconds"] = 300
        specification["runtime_dependencies"].append(
            {
                "dependency_id": "worker_capacity",
                "kind": "execution_capacity",
                "provisioning": "runtime_gap",
                "purpose": "Provide enough background worker time for the evaluation.",
                "unavailable_code": "capacity_exceeded",
            }
        )
        prepared_dependency = {
            "dependency_id": "prepared_reference_cache",
            "kind": "prepared_material",
            "provisioning": "runtime_gap",
            "purpose": "Provide the prepared reference cache used by the evaluator.",
            "unavailable_code": "material_unavailable",
        }
        specification["runtime_dependencies"].append(prepared_dependency)
        specification["inputs"].append(
            {
                "input_id": "prepared_reference_cache",
                "kind": "prepared_material",
                "purpose": "Read the externally prepared reference cache.",
            }
        )
        specification["infrastructure_failures"].append(
            {
                "code": "capacity_exceeded",
                "condition": "The proposed evaluation exceeds the worker time budget.",
            }
        )
        value["result"]["capability_suggestions"][0]["stage"] = "post_submit"
        GuideProposalReviewPackage.model_validate(value)
        response["body"] = json.dumps(value).encode()
        accepted = invoke(cli, origin)
        assert accepted.returncode == 0 and json.loads(accepted.stdout) == value

        prepared_input = specification["inputs"].pop()
        response["body"] = json.dumps(value).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")
        specification["inputs"].append(prepared_input)

        specification["runtime_dependencies"].pop()
        response["body"] = json.dumps(value).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")

        specification["runtime_dependencies"].append(prepared_dependency)
        prepared_dependency["provisioning"] = "current_runner"
        response["body"] = json.dumps(value).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")

        prepared_dependency["provisioning"] = "runtime_gap"
        specification["runtime_dependencies"][1]["provisioning"] = "current_runner"
        response["body"] = json.dumps(value).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")


@pytest.mark.parametrize("stage", ["pre_submit", "post_submit"])
def test_proposal_trial_proxy_and_offline_material_are_post_only(cli, stage):
    from app.modules.projects.api.guide_proposal_package import (
        GuideProposalReviewPackage,
    )

    with http_fixture() as (origin, response, _):
        value = proposal()
        index = 0 if stage == "pre_submit" else 1
        requirement = value["result"]["requirements"][index]
        specification = deepcopy(requirement["check_specification"])
        requirement["check_specification"] = specification
        dependencies = specification["runtime_dependencies"]
        dependencies.extend(
            [
                {
                    "dependency_id": "isolated_trial",
                    "kind": "nested_sandbox",
                    "provisioning": "trial_proxy",
                    "purpose": "Run the submitted environment.",
                    "unavailable_code": "implementation_unavailable",
                },
                {
                    "dependency_id": "offline_cache",
                    "kind": "prepared_material",
                    "provisioning": "trial_proxy",
                    "purpose": "Use the approved offline cache.",
                    "unavailable_code": "material_unavailable",
                },
            ]
        )
        specification["inputs"].append(
            {
                "input_id": "offline_cache",
                "kind": "prepared_material",
                "purpose": "Supply the profile-pinned offline base to the trial tool.",
            }
        )
        GuideProposalReviewPackage.model_validate(value)
        response["body"] = json.dumps(value).encode()
        if stage == "pre_submit":
            assert_failure(invoke(cli, origin), "invalid_api_response")
            return
        accepted = invoke(cli, origin)
        assert accepted.returncode == 0 and json.loads(accepted.stdout) == value

        nested = dependencies.pop(-2)
        response["body"] = json.dumps(value).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")
        dependencies.append(nested)
        nested["provisioning"] = "runtime_gap"
        response["body"] = json.dumps(value).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")


def test_proposal_accepts_supported_execution_with_model_proxy(cli):
    from app.modules.projects.api.guide_proposal_package import (
        GuideProposalReviewPackage,
    )

    with http_fixture() as (origin, response, _):
        value = proposal()
        dependencies = value["result"]["requirements"][1]["check_specification"][
            "runtime_dependencies"
        ]
        dependencies.append(
            {
                "dependency_id": "quality_model",
                "kind": "model_service",
                "provisioning": "model_proxy",
                "purpose": "Assess the authenticated execution observations.",
                "unavailable_code": "implementation_unavailable",
            }
        )
        GuideProposalReviewPackage.model_validate(value)
        response["body"] = json.dumps(value).encode()
        accepted = invoke(cli, origin)
        assert accepted.returncode == 0 and json.loads(accepted.stdout) == value

        dependencies[-1]["provisioning"] = "runtime_gap"
        response["body"] = json.dumps(value).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")


def test_proposal_rejects_pre_check_with_model_assistance(cli):
    with http_fixture() as (origin, response, _):
        value = proposal()
        dependencies = value["result"]["requirements"][0]["check_specification"][
            "runtime_dependencies"
        ]
        dependencies.append(
            {
                "dependency_id": "quality_model",
                "kind": "model_service",
                "provisioning": "model_proxy",
                "purpose": "Assist the bounded static inspection.",
                "unavailable_code": "implementation_unavailable",
            }
        )
        response["body"] = json.dumps(value).encode()
        assert_failure(invoke(cli, origin), "invalid_api_response")


def test_proposal_rejects_malformed_nested_types_and_incomplete_policy_identity(cli):
    cases = [
        (("current",), "yes"),
        (("warning_hashes",), [None]),
        (("artifact_policy_status",), "activated"),
        (("result", "status"), "accepted"),
        (("result", "agent_name"), None),
        (("result", "schema_version"), "other-protocol"),
        (("result", "findings", 0, "severity"), "critical"),
        (("result", "findings", 0, "message"), {"not": "text"}),
        (("result", "findings", 0, "evidence_refs"), [None]),
        (("result", "findings", 0, "evidence_refs", 0, "document_number"), "1"),
        (("result", "findings", 0, "evidence_refs", 0, "start_page"), "1"),
        (("result", "findings", 0, "evidence_refs", 0, "section"), {}),
        (("result", "requirements", 0, "disposition"), "approved"),
        (("result", "requirements", 0, "platform_coverage"), {}),
        (("result", "pre_submit_bindings", 0, "stage"), "human_acceptance"),
        (("result", "post_submit_bindings", 0, "parameters"), [None]),
        (("result", "post_submit_bindings", 0, "parameters", 0, "value"), []),
        (("result", "capability_suggestions", 0, "evidence_refs"), []),
        (("result", "submission_artifact_policy", "maximum_archive_entries"), "20"),
        (("result", "submission_artifact_policy", "maximum_archive_size_bytes"), 1.5),
        (("result", "submission_artifact_policy", "packaging"), None),
        (("target", "component_hashes", "post_submit_hash"), "not-digest"),
    ]
    cases.extend(
        (("target", key), None)
        for key in (
            "artifact_policy_id",
            "artifact_policy_hash",
            "artifact_projection_operation_id",
            "artifact_projection_output_digest",
        )
    )
    with http_fixture() as (origin, response, _):
        for path, invalid in cases:
            value = proposal()
            obj = value
            for component in path[:-1]:
                obj = obj[component]
            obj[path[-1]] = invalid
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        for field in (
            "allowed_storage_schemes",
            "required_artifacts",
            "forbidden_artifacts",
            "required_evidence",
            "attestation_terms",
        ):
            value = proposal()
            value["result"]["submission_artifact_policy"][field] = [None]
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")


def test_proposal_response_bound_and_existing_safe_failures(cli):
    from app.modules.projects.api.guide_proposal_package import (
        GuideProposalReviewPackage,
    )

    with http_fixture() as (origin, response, requests):
        value = proposal()
        requirement = value["result"]["requirements"][0]
        value["result"]["requirements"] = [
            requirement
            | {"requirement_id": f"requirement_{index}", "statement": "x" * 1000}
            for index in range(100)
        ]
        # The larger successful envelope must be a supported public shape,
        # not permissive-fake data used to justify widening a response limit.
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
        assert "outcome_unknown" not in json.loads(denied.stderr)["error"]
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


def test_proposal_intake_integer_field_boundaries(cli):
    from app.modules.projects.api.guide_proposal_package import (
        GuideProposalReviewPackage,
    )

    ceiling = 10 * 1024**3
    fields = (
        "maximum_file_size_bytes",
        "maximum_package_size_bytes",
        "maximum_archive_size_bytes",
        "maximum_archive_entries",
    )
    with http_fixture() as (origin, response, _):
        for field in fields:
            upper = ceiling if field in fields[:2] else 9223372036854775808
            for boundary in (1, upper):
                value = proposal()
                policy = value["result"]["submission_artifact_policy"]
                # Keep cross-field policy coherence in valid controls; this
                # client check covers only the four declared field ranges.
                policy["maximum_file_size_bytes"] = 1
                policy["maximum_package_size_bytes"] = ceiling
                policy[field] = boundary
                GuideProposalReviewPackage.model_validate(value)
                response["body"] = json.dumps(value).encode()
                result = invoke(cli, origin)
                assert result.returncode == 0 and json.loads(result.stdout) == value, (
                    result.stderr
                )
            invalid = (-1, 0, ceiling + 1) if field in fields[:2] else (-1, 0)
            for boundary in invalid:
                value = proposal()
                value["result"]["submission_artifact_policy"][field] = boundary
                response["body"] = json.dumps(value).encode()
                assert_failure(invoke(cli, origin), "invalid_api_response")


def test_proposal_without_project_size_overrides_preserves_nulls(cli):
    from app.modules.projects.api.guide_proposal_package import (
        GuideProposalReviewPackage,
    )

    with http_fixture() as (origin, response, _):
        for fields in (
            ("maximum_file_size_bytes",),
            ("maximum_package_size_bytes",),
            ("maximum_file_size_bytes", "maximum_package_size_bytes"),
        ):
            for omit in (False, True):
                value = proposal()
                policy = value["result"]["submission_artifact_policy"]
                for field in fields:
                    if omit:
                        del policy[field]
                    else:
                        policy[field] = None
                GuideProposalReviewPackage.model_validate(value)
                response["body"] = json.dumps(value).encode()
                result = invoke(cli, origin)
                assert result.returncode == 0 and json.loads(result.stdout) == value, (
                    result.stderr
                )
