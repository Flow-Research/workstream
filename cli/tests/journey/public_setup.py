"""Manager-authored setup driven exclusively through the built CLI."""

import hashlib
import json
import time
from uuid import uuid4


GUIDE = b"""# Local CLI contract exercise
Submit proof.json at the ZIP root. This exercise checks the format of declared
proof claims only; it does not verify any remote work or award compensation.
Both intake and post-submission evaluation use the registered harnessy.work_proof
checker. Claims must use harnessy.work.proof.v1, a forty-digit hexadecimal commit,
GitHub HTTPS PR and CI URLs, success CI conclusion, and merged true.
"""


def poll(client, token, arguments, predicate):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        value = client.call(token, *arguments)
        if predicate(value):
            return value
        if value.get("status") in {
            "failed",
            "guide_blocked",
            "compilation_invalid_terminal",
        }:
            raise AssertionError("public setup reached a terminal unsuccessful state")
        time.sleep(1)
    raise AssertionError("public read did not reach its expected state within deadline")


def authored_rules():
    reference = {"document": "sha256:" + hashlib.sha256(GUIDE).hexdigest()}
    requirements = []
    for phase in ("pre_submit", "post_submit"):
        requirements.append(
            {
                "suggestion_id": f"proof.{phase}",
                "statement": "Validate the declared proof fields.",
                "stage": phase,
                "evidence_refs": [reference],
                "classification_rationale": "Static inspection can validate declared fields, without verifying remote work.",
                "check_specification": {
                    "evaluation_method": "Inspect the declared proof fields in proof.json.",
                    "inputs": [
                        {
                            "input_id": "proof",
                            "kind": "relative_file",
                            "relative_path": "proof.json",
                            "purpose": "Declared proof claims, without network verification.",
                        }
                    ],
                    "check_steps": [
                        "Require a regular proof.json of at most 65536 bytes containing a UTF-8 JSON object.",
                        "Require schema harnessy.work.proof.v1 and commit_sha of exactly 40 hexadecimal characters.",
                        "Require pr_url and ci_run_url with scheme https, authority github.com and a non-root path.",
                        "Require ci_conclusion success and merged equal to the JSON boolean true.",
                    ],
                    "pass_conditions": [
                        "All declared proof fields satisfy the static predicates."
                    ],
                    "failure_findings": [
                        {
                            "code": "harnessy.proof.invalid_json",
                            "level": "error",
                            "condition": "proof.json is not a UTF-8 JSON object.",
                            "message": "proof.json must contain a valid JSON object.",
                        }
                    ],
                    "positive_tests": [
                        "A JSON object satisfying every stated field predicate passes."
                    ],
                    "negative_tests": [
                        {
                            "name": "invalid_json",
                            "scenario": "proof.json contains malformed JSON.",
                            "expected_verdict": "failed",
                            "expected_finding_codes": ["harnessy.proof.invalid_json"],
                        }
                    ],
                    "implementation_needs": [
                        "Implement a JSON parser and the listed static field predicates."
                    ],
                    "inability_to_evaluate": [
                        {
                            "code": "harnessy.proof.unreadable",
                            "condition": "proof.json cannot be read as candidate content.",
                        }
                    ],
                },
            }
        )
    return {
        "format": "workstream.project_guide_rules.v1",
        "status": "draft_ready",
        "findings": [
            {
                "severity": "info",
                "code": "guide.ready",
                "message": "Explicit unpaid format-validation exercise.",
                "evidence_refs": [reference],
            }
        ],
        "submission_artifact_policy": {
            "maximum_file_size_bytes": 1000000,
            "maximum_package_size_bytes": 5000000,
            "required_artifacts": ["proof.json"],
        },
        "requirements": requirements,
        "setup_notes": [],
    }


def configure_guide(client, tokens, project_id):
    manager = tokens["manager"]
    guide = client.write_and_replay(
        manager,
        "project",
        "guide",
        "create",
        project_id,
        body={
            "version": "cli-exercise",
            "change_summary": "Unpaid local CLI journey",
            "task_examples": [{"content": "Prepare the declared proof fields."}],
            "documents": [
                {"label": "Guide.md", "media_type": "text/markdown"},
                {"label": "workstream-rules.json", "media_type": "text/markdown"},
            ],
        },
    )
    guide_id = guide["id"]
    for command, body in (
        (
            "set-review-policy",
            {
                "human_review_required": False,
                "review_preference_window_seconds": 3600,
                "review_lease_duration_seconds": 1800,
            },
        ),
        (
            "set-revision-policy",
            {"max_revision_rounds": 2, "revision_deadline_hours": 48},
        ),
    ):
        client.write_and_replay(
            manager,
            "project",
            "guide",
            command,
            project_id,
            guide_id,
            "--if-match",
            '"no-current-policy"',
            body=body,
        )
    for document, content in zip(
        guide["documents"], (GUIDE, json.dumps(authored_rules()).encode()), strict=True
    ):
        path = client.directory / (str(document["document_id"]) + ".md")
        path.write_bytes(content)
        receipt = client.call(
            manager,
            "project",
            "guide",
            "upload",
            project_id,
            guide_id,
            document["document_id"],
            "--file",
            str(path),
            "--media-type",
            "text/markdown",
            "--idempotency-key",
            str(uuid4()),
        )
        if receipt["sha256"] != "sha256:" + hashlib.sha256(
            content
        ).hexdigest() or receipt["byte_count"] != len(content):
            raise AssertionError("guide original receipt differs from uploaded bytes")
    return guide_id


def publish_unpaid_terms(client, token, project_id):
    policy = client.write_and_replay(
        token,
        "project",
        "contribution-policy",
        "create",
        project_id,
        body={"name": "Unpaid CLI exercise"},
    )
    selectors = (
        project_id,
        policy["contribution_policy_id"],
        policy["contribution_policy_version_id"],
    )
    client.write_and_replay(
        token,
        "project",
        "contribution-policy",
        "update",
        *selectors,
        body={
            "rules": [
                {
                    "contribution_type": kind,
                    "compensation_mode": "unpaid",
                    "definitions": [],
                }
                for kind in ("accepted_submission", "completed_review")
            ]
        },
    )
    key = str(uuid4())
    arguments = (
        "project",
        "contribution-policy",
        "publish",
        *selectors,
        "--idempotency-key",
        key,
    )
    receipt = client.call(token, *arguments)
    if client.call(token, *arguments) != receipt:
        raise AssertionError("Finance publication replay changed receipt")
    return policy


def approve_and_activate(client, token, project_id, guide_id, registry_entries):
    command = (
        "project",
        "guide",
        "compile-requirements",
        project_id,
        guide_id,
        "--idempotency-key",
        str(uuid4()),
    )
    requested = client.call(token, *command)
    replay = client.call(token, *command)
    # Dispatch status may advance while the same durable request is replayed.
    for field in ("operation_id", "setup_run_id", "setup_generation"):
        if requested[field] != replay[field]:
            raise AssertionError("compilation replay changed durable request identity")
    setup = poll(
        client,
        token,
        ("project", "guide", "setup", project_id, guide_id),
        lambda value: value["finalized_compilation_id"] is not None,
    )
    if (
        setup["id"] != requested["setup_run_id"]
        or setup["setup_generation"] != requested["setup_generation"]
    ):
        raise AssertionError(
            "setup diagnostics no longer select the requested compilation"
        )
    selectors = (project_id, guide_id, setup["finalized_compilation_id"])
    proposal = client.call(token, "project", "guide", "proposal", *selectors)
    if proposal["warning_hashes"]:
        raise AssertionError(
            "unexpected warnings require human review, not automatic acknowledgement"
        )
    client.write_and_replay(
        token,
        "project",
        "guide",
        "approve-pre",
        *selectors,
        body={
            "target": proposal["target"],
            "pre_submit_attachments": [
                {
                    "requirement_id": "project.proof_pre",
                    "registry_entry_id": registry_entries["pre"]["registry_entry_id"],
                    "registry_entry_digest": registry_entries["pre"]["entry_digest"],
                    "configuration": {},
                }
            ],
            "post_submit_attachments": [
                {
                    "requirement_id": "project.proof_post",
                    "registry_entry_id": registry_entries["post"]["registry_entry_id"],
                    "registry_entry_digest": registry_entries["post"]["entry_digest"],
                    "configuration": {},
                }
            ],
            "acknowledged_warning_hashes": [],
        },
    )
    proposal = poll(
        client,
        token,
        ("project", "guide", "proposal", *selectors),
        lambda value: value["post_submit_policy_id"] is not None,
    )
    selectors = (*selectors, proposal["post_submit_policy_id"])
    post = client.call(token, "project", "guide", "post-policy", *selectors)
    client.write_and_replay(
        token,
        "project",
        "guide",
        "approve-post",
        *selectors,
        body={"target": post["target"]},
    )
    post = client.call(token, "project", "guide", "post-policy", *selectors)
    context = post["activation_context"]
    body = {
        "target": post["target"],
        **context["contribution"],
        **{
            name: context[name]
            for name in (
                "post_approval_operation_id",
                "post_approval_output_digest",
                "guide_mutation_generation",
                "review",
                "revision",
                "expected_previous_active_guide_id",
                "expected_previous_active_guide_generation",
            )
        },
    }
    return client.write_and_replay(
        token, "project", "guide", "activate", project_id, guide_id, body=body
    )
