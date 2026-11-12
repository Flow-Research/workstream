"""Built CLI proof of contributor context, locked rules and safe display."""

from copy import deepcopy
import json

import pytest

from test_contributor_task_http import CONTRIBUTOR
from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture
from test_task_http_boundary import TASK

POLICY = {"policy_id": ACTOR, "generation": 1, "policy_hash": "sha256:" + "a" * 64}
CONTEXT = {
    "task": CONTRIBUTOR,
    "project": {
        "id": PROJECT,
        "name": "Research",
        "slug": "research",
        "description": None,
    },
    "guide": {
        "id": ACTOR,
        "project_id": PROJECT,
        "version": "guide-1",
        "change_summary": "Read carefully\n\x1b[31m\u202e",
        "effective_at": "2026-10-01T00:00:00Z",
    },
    "review_policy": POLICY,
    "revision_policy": POLICY,
    "contribution_policy_version_id": ACTOR,
    "lifecycle": {"assigned_to_current_actor": False, "next_actions": ["claim"]},
    "guide_documents": [],
}
REVISION_LINEAGE = {
    "locked_guide_version": "guide-1",
    "locked_guide_source_snapshot_id": ACTOR,
    "locked_guide_source_snapshot_hash": "sha256:" + "a" * 64,
    "locked_effective_project_submission_artifact_policy_id": ACTOR,
    "locked_effective_project_submission_artifact_policy_hash": "sha256:" + "a" * 64,
    "locked_pre_submit_checker_policy_id": ACTOR,
    "locked_pre_submit_checker_bundle_hash": "sha256:" + "a" * 64,
    "locked_post_submit_checker_policy_id": ACTOR,
    "locked_post_submit_checker_policy_version": "post-1",
    "locked_post_submit_checker_policy_hash": "sha256:" + "a" * 64,
    "locked_review_policy_id": ACTOR,
    "locked_review_policy_generation": 1,
    "locked_review_policy_hash": "sha256:" + "a" * 64,
    "locked_revision_policy_id": ACTOR,
    "locked_revision_policy_generation": 1,
    "locked_revision_policy_hash": "sha256:" + "a" * 64,
    "locked_contribution_policy_version_id": ACTOR,
}
REVISION_SNAPSHOT = {
    "guide_id": ACTOR,
    "activation_operation_id": ACTOR,
    "activation_generation": 1,
    "activated_at": "2026-10-01T00:00:00Z",
    "lineage": REVISION_LINEAGE,
}
REVISION_CONTEXT = {
    "preparation_id": ACTOR,
    "preparation_sha256": "sha256:" + "b" * 64,
    "predecessor_preparation_id": None,
    "source_submission_id": ACTOR,
    "source_routing_manifest_id": ACTOR,
    "sequence": 1,
    "next_revision_round": 1,
    "max_revision_rounds": 2,
    "requested_at": "2026-10-14T10:00:00Z",
    "deadline_at": "2026-10-15T10:00:00Z",
    "clock_state": "running",
    "remaining_microseconds": None,
    "outcome": "kept",
    "disposition": "ready",
    "direction": "kept",
    "prior_reward_selection": {"compensation_mode": "unpaid", "task_size": "small",
                               "instrument": None, "unit": None, "quantity": None},
    "target_reward_selection": {"compensation_mode": "unpaid", "task_size": "small",
                                "instrument": None, "unit": None, "quantity": None},
    "prior": REVISION_SNAPSHOT,
    "target": REVISION_SNAPSHOT,
    "changes": [],
}
REQUIREMENTS = {
    "task_id": TASK,
    "project_id": PROJECT,
    "guide_version": "guide-1",
    "policy_schema_version": "artifact-policy",
    "merge_algorithm_version": None,
    "required_packet_fields": ["summary", "worker_attestation"],
    "required_artifacts": [
        {
            "key": "answer",
            "path": "answer.md",
            "hash_required": True,
            "required": True,
            "description": None,
        }
    ],
    "required_evidence": [
        {
            "key": "proof",
            "label": "References",
            "hash_required": False,
            "required": True,
            "description": "Explain\n\x1b[32m\u202e",
        }
    ],
    "forbidden_artifacts": [
        {
            "pattern": "*.secret",
            "reason": None,
            "worker_facing_fix": "Remove secrets",
            "severity": "error",
        }
    ],
    "attestation_terms": ["This is my work."],
    "manifest_required": False,
    "artifact_hash_required": True,
    "artifact_hash_algorithm": "sha256",
    "allowed_storage_schemes": ["s3"],
    "storage_reference_rules": {
        "allowed_storage_schemes": ["s3"],
        "allowed_uri_prefixes": ["s3://"],
        "credentials_allowed": False,
        "query_strings_allowed": False,
        "fragments_allowed": False,
        "path_traversal_allowed": False,
    },
    "maximum_file_size_bytes": 1024,
    "maximum_package_size_bytes": 2048,
    "maximum_archive_entries": 10,
    "maximum_archive_size_bytes": None,
    "packaging": {"package_required": True, "allowed_package_formats": ["zip"]},
}
CONTEXT_LABELS = (
    "Task",
    "Project",
    "Guide",
    "Review policy",
    "Revision policy",
    "Contribution policy version",
    "Lifecycle (server hints, not authorization)",
    "Guide documents",
)
REQUIREMENT_LABELS = (
    "Task",
    "Project",
    "Guide version",
    "Policy schema version",
    "Merge algorithm version",
    "Required packet fields",
    "Required artifacts",
    "Required evidence",
    "Forbidden artifacts",
    "Attestation terms",
    "Manifest required",
    "Artifact hash required",
    "Artifact hash algorithm",
    "Allowed storage schemes",
    "Storage reference rules",
    "Maximum file size bytes",
    "Maximum package size bytes",
    "Maximum archive entries",
    "Maximum archive size bytes",
    "Packaging",
)


def test_context_reads_preserve_wire_complete_output_and_optional_fields(cli):
    with http_fixture() as (origin, response, requests):
        for command, suffix, original, labels in (
            ("context", "work-context", CONTEXT, CONTEXT_LABELS),
            (
                "requirements",
                "submission-requirements",
                REQUIREMENTS,
                REQUIREMENT_LABELS,
            ),
        ):
            response["body"] = json.dumps(original, ensure_ascii=False).encode()
            for selector in (
                TASK,
                TASK.replace("-", ""),
                "{" + TASK + "}",
                "urn:uuid:" + TASK,
            ):
                before = len(requests)
                result = cli(origin, TOKEN, "task", command, selector, "-o", "json")
                assert result.returncode == 0 and result.stderr == "", result.stderr
                assert result.stdout.strip().encode() == response["body"]
                assert requests[before:] == [
                    (
                        "GET",
                        f"/api/v1/tasks/{selector.replace('{', '%7B').replace('}', '%7D')}/{suffix}",
                        "Bearer " + TOKEN,
                    )
                ]
            result = cli(origin, TOKEN, "task", command, TASK)
            assert result.returncode == 0 and result.stderr == ""
            assert [
                line.split(": ", 1)[0] for line in result.stdout.splitlines()
            ] == list(labels)
            assert "\x1b" not in result.stdout and "\u202e" not in result.stdout
            # Each complete nested value is displayed, not just a selected headline.
            for line, expected in zip(
                result.stdout.splitlines(), original.values(), strict=True
            ):
                displayed = json.loads(line.split(": ", 1)[1])
                assert displayed == expected
            assert len(requests) == (5 if command == "context" else 10)

        # Exercise the CLI's optional-value decoder; the API emits explicit nulls.
        context = deepcopy(CONTEXT)
        del context["project"]["description"]
        del context["guide"]["change_summary"]
        for key in (
            "task_type",
            "difficulty",
            "estimated_time_minutes",
            "deadline_at",
            "acceptance_criteria",
            "rejection_criteria",
        ):
            context["task"].pop(key, None)
        context["lifecycle"] = {"assigned_to_current_actor": True, "next_actions": []}
        requirements = deepcopy(REQUIREMENTS)
        for key in (
            "policy_schema_version",
            "merge_algorithm_version",
            "maximum_file_size_bytes",
            "maximum_package_size_bytes",
            "maximum_archive_entries",
            "maximum_archive_size_bytes",
        ):
            requirements.pop(key, None)
        requirements["required_artifacts"][0].pop("description")
        requirements["required_evidence"][0].pop("description")
        requirements["forbidden_artifacts"][0] = {"pattern": "*.secret"}
        for formats in (None, [], ["zip", "tar", "tar.gz", "tar.zst"]):
            requirements["packaging"]["allowed_package_formats"] = formats
            for command, value in (
                ("context", context),
                ("requirements", requirements),
            ):
                response["body"] = json.dumps(value).encode()
                result = cli(origin, TOKEN, "task", command, TASK, "-o", "json")
                assert result.returncode == 0 and json.loads(result.stdout) == value, (
                    result.stderr
                )
        del requirements["packaging"]["allowed_package_formats"]
        for key in (
            "required_artifacts",
            "required_evidence",
            "forbidden_artifacts",
            "required_packet_fields",
            "attestation_terms",
            "allowed_storage_schemes",
        ):
            requirements[key] = []
        response["body"] = json.dumps(requirements).encode()
        result = cli(origin, TOKEN, "task", "requirements", TASK, "-o", "json")
        assert result.returncode == 0 and json.loads(result.stdout) == requirements


def test_revision_context_accepts_absent_null_and_valid_projection_but_rejects_bad_lineage(
    cli,
):
    with http_fixture() as (origin, response, _):
        paused = REVISION_CONTEXT | {
            "deadline_at": None,
            "remaining_microseconds": 1800000000,
            "clock_state": "paused",
            "outcome": "blocked",
            "disposition": "context_blocked",
        }
        for revision in (None, REVISION_CONTEXT, paused):
            value = deepcopy(CONTEXT)
            value["revision_context"] = deepcopy(revision)
            response["body"] = json.dumps(value).encode()
            result = cli(origin, TOKEN, "task", "context", TASK, "-o", "json")
            assert result.returncode == 0 and json.loads(result.stdout) == value, (
                result.stderr
            )
            text_result = cli(origin, TOKEN, "task", "context", TASK)
            assert text_result.returncode == 0, text_result.stderr
            if revision is None:
                assert "Revision context:" not in text_result.stdout
            else:
                assert (
                    json.loads(text_result.stdout.split("Revision context: ", 1)[1])
                    == revision
                )
        for change in (
            {"preparation_sha256": "sha256:" + "B" * 64},
            {"sequence": 0},
            {"clock_state": "paused"},
            {"clock_state": "unknown"},
            {"remaining_microseconds": 1},
            {"deadline_at": None},
            {"disposition": "accepted"},
            {
                "prior": REVISION_SNAPSHOT
                | {"lineage": REVISION_LINEAGE | {"unknown": "secret"}}
            },
            {"changes": [{"component": "unknown", "before": "a", "after": "b"}]},
        ):
            value = deepcopy(CONTEXT)
            value["revision_context"] = deepcopy(REVISION_CONTEXT) | change
            response["body"] = json.dumps(value).encode()
            assert_failure(
                cli(origin, TOKEN, "task", "context", TASK, "-o", "json"),
                "invalid_api_response",
            )


@pytest.mark.parametrize(
    "field",
    (
        "maximum_file_size_bytes",
        "maximum_package_size_bytes",
        "maximum_archive_entries",
        "maximum_archive_size_bytes",
    ),
)
def test_requirements_preserve_backend_integer_limits(cli, field):
    from app.modules.projects.schemas import SubmissionArtifactPolicyInput
    from app.modules.tasks.schemas import ContributorTaskSubmissionRequirements

    with http_fixture() as (origin, response, requests):
        for limit in (None, 1, 2**63 - 1, 2**63, 2**64 + 1, 10**100 + 1):
            policy = SubmissionArtifactPolicyInput.model_validate({field: limit})
            assert getattr(policy, field) == limit
            value = REQUIREMENTS | {field: limit}
            backend = ContributorTaskSubmissionRequirements.model_validate_json(
                json.dumps(value)
            )
            assert getattr(backend, field) == limit
            response["body"] = backend.model_dump_json().encode()
            expected = json.loads(response["body"])
            for flags in (("-o", "json"), ()):
                before = len(requests)
                result = cli(origin, TOKEN, "task", "requirements", TASK, *flags)
                assert result.returncode == 0 and result.stderr == "", (
                    field,
                    limit,
                    result.stderr,
                )
                if flags:
                    assert result.stdout.strip().encode() == response["body"]
                else:
                    assert [
                        json.loads(line.split(": ", 1)[1])
                        for line in result.stdout.splitlines()
                    ] == list(expected.values())
                assert requests[before:] == [
                    (
                        "GET",
                        f"/api/v1/tasks/{TASK}/submission-requirements",
                        "Bearer " + TOKEN,
                    )
                ]

        # Omission stays distinct from a concrete integer; text displays null.
        value = {key: item for key, item in REQUIREMENTS.items() if key != field}
        response["body"] = json.dumps(value).encode()
        result = cli(origin, TOKEN, "task", "requirements", TASK, "-o", "json")
        assert result.returncode == 0 and json.loads(result.stdout) == value
        result = cli(origin, TOKEN, "task", "requirements", TASK)
        assert result.returncode == 0 and result.stderr == ""
        label = REQUIREMENT_LABELS[list(REQUIREMENTS).index(field)]
        assert f"{label}: null" in result.stdout.splitlines()

        # Arbitrary precision must not mean accepting arbitrary JSON values.
        for token in ('"9223372036854775808"', "true", "1.5", "1e3", "{}", "[]"):
            body = json.dumps(REQUIREMENTS | {field: "invalid-limit-marker"})
            response["body"] = body.replace('"invalid-limit-marker"', token).encode()
            assert_failure(
                cli(origin, TOKEN, "task", "requirements", TASK, "-o", "json"),
                "invalid_api_response",
            )


def test_work_context_rejects_foreign_guide_project(cli):
    with http_fixture() as (origin, response, _requests):
        response["body"] = json.dumps(CONTEXT).encode()
        assert cli(origin, TOKEN, "task", "context", TASK, "-o", "json").returncode == 0
        substituted = deepcopy(CONTEXT)
        substituted["guide"]["project_id"] = (
            ACTOR  # Valid UUID; only composite identity differs.
        )
        response["body"] = json.dumps(substituted).encode()
        assert_failure(
            cli(origin, TOKEN, "task", "context", TASK, "-o", "json"),
            "invalid_api_response",
        )


def test_work_context_rejects_incomplete_nested_or_management_facts(cli):
    with http_fixture() as (origin, response, _requests):
        cases = [None, [], {}, CONTEXT | {"unexpected": True}]
        for key in CONTEXT:
            cases.append(
                {name: value for name, value in CONTEXT.items() if name != key}
            )
            cases.append(CONTEXT | {key: None})
        for section, fields in (
            ("project", ("id", "name", "slug")),
            ("guide", ("id", "project_id", "version", "effective_at")),
            ("review_policy", ("policy_id", "generation", "policy_hash")),
            ("revision_policy", ("policy_id", "generation", "policy_hash")),
            ("lifecycle", ("assigned_to_current_actor", "next_actions")),
        ):
            for field in fields:
                for remove in (False, True):
                    value = deepcopy(CONTEXT)
                    if remove:
                        del value[section][field]
                    else:
                        value[section][field] = None
                    cases.append(value)
            cases.extend(
                CONTEXT | {section: wrong}
                for wrong in ([], "wrong", CONTEXT[section] | {"unknown": True})
            )
        for section, field, wrong in (
            ("project", "id", ACTOR),
            ("guide", "id", "bad"),
            ("guide", "version", " \t"),
            ("guide", "effective_at", "2026-10-01"),
            ("task", "task_id", ACTOR),
            ("task", "project_id", ACTOR),
            ("task", "skill_tags", [None]),
            ("task", "created_at", "bad"),
            ("task", "description", None),
            ("task", "created_by", ACTOR),
            ("review_policy", "generation", 0),
            ("review_policy", "generation", True),
            ("revision_policy", "generation", 1.5),
            ("revision_policy", "policy_id", "bad"),
            ("review_policy", "policy_hash", "sha256:" + "A" * 64),
            ("revision_policy", "policy_hash", "sha256:" + "a" * 63),
            ("lifecycle", "assigned_to_current_actor", "false"),
            ("lifecycle", "next_actions", [None]),
            ("lifecycle", "next_actions", ["accept"]),
            ("lifecycle", "next_actions", ["claim", "start"]),
            ("lifecycle", "next_actions", ["start"]),
        ):
            value = deepcopy(CONTEXT)
            value[section][field] = wrong
            cases.append(value)
        cases.append(CONTEXT | {"contribution_policy_version_id": "bad"})
        for value in cases:
            response["body"] = json.dumps(value).encode()
            assert_failure(
                cli(origin, TOKEN, "task", "context", TASK, "-o", "json"),
                "invalid_api_response",
            )
        for body in (
            json.dumps(CONTEXT).replace(
                '"generation": 1', '"generation": 1, "generation": 2', 1
            ),
            json.dumps(CONTEXT).replace(
                '"description": null', '"description": null, "description": null', 1
            ),
        ):
            response["body"] = body.encode()
            assert_failure(
                cli(origin, TOKEN, "task", "context", TASK, "-o", "json"),
                "invalid_api_response",
            )


def test_requirements_reject_missing_null_or_substituted_facts(cli):
    optional = {
        "policy_schema_version",
        "merge_algorithm_version",
        "maximum_file_size_bytes",
        "maximum_package_size_bytes",
        "maximum_archive_entries",
        "maximum_archive_size_bytes",
    }
    with http_fixture() as (origin, response, _requests):
        cases = [None, [], {}, REQUIREMENTS | {"unknown": True}]
        for key in REQUIREMENTS.keys() - optional:
            cases.append(
                {name: value for name, value in REQUIREMENTS.items() if name != key}
            )
            cases.append(REQUIREMENTS | {key: None})
        for key, wrong in (
            ("task_id", ACTOR),
            ("project_id", "bad"),
            ("guide_version", " \t"),
            ("artifact_hash_algorithm", "md5"),
            ("manifest_required", "false"),
            ("artifact_hash_required", 0),
            ("maximum_file_size_bytes", 1.5),
            ("maximum_package_size_bytes", True),
            ("policy_schema_version", {}),
        ):
            cases.append(REQUIREMENTS | {key: wrong})
        for key in (
            "required_packet_fields",
            "attestation_terms",
            "allowed_storage_schemes",
        ):
            cases.append(REQUIREMENTS | {key: [None]})
        for key, required in (
            ("required_artifacts", ("key", "path", "hash_required", "required")),
            ("required_evidence", ("key", "label", "hash_required", "required")),
            ("forbidden_artifacts", ("pattern",)),
        ):
            cases.extend(
                REQUIREMENTS | {key: [wrong]}
                for wrong in (None, [], {}, REQUIREMENTS[key][0] | {"private": True})
            )
            for field in required:
                for remove in (False, True):
                    value = deepcopy(REQUIREMENTS)
                    if remove:
                        del value[key][0][field]
                    else:
                        value[key][0][field] = None
                    cases.append(value)
        for field in REQUIREMENTS["storage_reference_rules"]:
            for remove in (False, True):
                value = deepcopy(REQUIREMENTS)
                if remove:
                    del value["storage_reference_rules"][field]
                else:
                    value["storage_reference_rules"][field] = None
                cases.append(value)
        for formats in ([None], ["rar"], "zip", [1]):
            cases.append(
                REQUIREMENTS
                | {
                    "packaging": {
                        "package_required": True,
                        "allowed_package_formats": formats,
                    }
                }
            )
        cases.extend(
            REQUIREMENTS | {"packaging": wrong}
            for wrong in (
                [],
                {},
                {"package_required": None},
                {"package_required": True, "unknown": True},
            )
        )
        cases.append(
            REQUIREMENTS
            | {
                "storage_reference_rules": REQUIREMENTS["storage_reference_rules"]
                | {"allowed_uri_prefixes": [None]}
            }
        )
        for value in cases:
            response["body"] = json.dumps(value).encode()
            assert_failure(
                cli(origin, TOKEN, "task", "requirements", TASK, "-o", "json"),
                "invalid_api_response",
            )
        response["body"] = (
            json.dumps(REQUIREMENTS)
            .replace(
                '"manifest_required": false',
                '"manifest_required": false, "manifest_required": true',
            )
            .encode()
        )
        assert_failure(
            cli(origin, TOKEN, "task", "requirements", TASK, "-o", "json"),
            "invalid_api_response",
        )


def test_context_reads_use_current_failure_bounds_without_partial_output(cli):
    with http_fixture() as (origin, response, requests):
        for command, value in (("context", CONTEXT), ("requirements", REQUIREMENTS)):
            for selector in ("bad", TASK + "/..", "x" * 101):
                before = len(requests)
                result = cli(origin, TOKEN, "-o", "json", "task", command, selector)
                assert result.returncode == 2 and result.stdout == ""
                assert requests[before:] == []
            oversized = deepcopy(value)
            if command == "context":
                # Document-bearing context has its own 2 MiB wire bound.
                # The separate 100-document test proves legitimate >64 KiB
                # content succeeds; excess still fails without partial output.
                oversized["project"]["name"] = "x" * (2 * 1024 * 1024)
            else:
                oversized["attestation_terms"] = ["x" * 65536]
            response["body"] = json.dumps(oversized).encode()
            assert_failure(
                cli(origin, TOKEN, "task", command, TASK, "-o", "json"),
                "invalid_api_response",
            )
            response["body"] = b'{"error":{"code":"resource_not_found"}}'
            for status in (403, 404, 422):
                response["status"] = status
                result = cli(origin, TOKEN, "task", command, TASK, "-o", "json")
                assert_failure(result, "resource_not_found")
                assert json.loads(result.stderr)["error"]["status"] == status
                assert "outcome_unknown" not in json.loads(result.stderr)["error"]
            before = len(requests)
            response["status"] = 302
            response["headers"]["Location"] = origin + "/must-not-follow"
            redirected = cli(origin, TOKEN, "task", command, TASK, "-o", "json")
            assert_failure(redirected, "redirect_refused")
            assert json.loads(redirected.stderr)["error"]["status"] == 302
            assert len(requests) == before + 1
            response["status"] = 200
