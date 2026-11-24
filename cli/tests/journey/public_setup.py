"""Manager-authored setup driven exclusively through the built CLI."""

import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4


PILOT = Path(__file__).resolve().parents[3] / "pilots/terminal_systems/mvp"
GUIDE = (PILOT / "guide.md").read_bytes()
TASK = (PILOT / "task.md").read_text(encoding="utf-8")


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
    """Manager-authored suggestions for the real incident-summary PRE/POST image."""
    reference = {"document": "sha256:" + hashlib.sha256(GUIDE).hexdigest()}
    requirements = []
    for phase, check in (
        ("pre_submit", "incident_summary_layout"),
        ("post_submit", "incident_summary_counts"),
    ):
        post = phase == "post_submit"
        code = "terminal.incident_summary." + (
            "incorrect_counts" if post else "invalid_layout"
        )
        requirements.append(
            {
                "suggestion_id": f"incident.{phase}",
                "statement": (
                    "Verify the fixed event file and exact per-service counts."
                    if post
                    else "Require the fixed event file and a shaped summary."
                ),
                "stage": phase,
                "evidence_refs": [reference],
                "classification_rationale": (
                    "Offline image evaluation compares the submitted output with the fixed input."
                    if post
                    else "Offline image inspection checks required root files and JSON shape."
                ),
                "check_specification": {
                    "evaluation_method": "Execute the pinned offline incident-summary checker image.",
                    "inputs": [
                        {
                            "input_id": "incident_files",
                            "kind": "relative_file",
                            "relative_path": "summary.json",
                            "purpose": "Contributor output to inspect with the fixed events.jsonl input.",
                        }
                    ],
                    "check_steps": (
                        [
                            "Require root events.jsonl equal to the fixed seven incident events.",
                            "Require root summary.json with the services array and exact per-service total and error counts.",
                        ]
                        if post
                        else [
                            "Require root events.jsonl with the fixed seven incident events.",
                            "Require root summary.json as a JSON object with a nonempty services array.",
                        ]
                    ),
                    "pass_conditions": [
                        "The pinned image returns passed with no error findings."
                    ],
                    "failure_findings": [
                        {
                            "code": code,
                            "level": "error",
                            "condition": "The submitted files violate this phase's incident summary check.",
                            "message": "Correct the incident summary files and submit again.",
                        }
                    ],
                    "positive_tests": [
                        "The supplied correct ZIP passes the selected phase."
                    ],
                    "negative_tests": [
                        {
                            "name": "incorrect_counts" if post else "missing_summary",
                            "scenario": (
                                "The shaped summary has incorrect per-service counts."
                                if post
                                else "The summary.json root file is absent."
                            ),
                            "expected_verdict": "failed",
                            "expected_finding_codes": [code],
                        }
                    ],
                    "implementation_needs": [
                        "Use the registered incident-summary image and fixed events input."
                    ],
                    "inability_to_evaluate": [
                        {
                            "code": "terminal.incident_summary.unavailable",
                            "condition": "The pinned image or material is unavailable.",
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
                "message": "Fixed incident summary with pinned offline PRE and POST checks.",
                "evidence_refs": [reference],
            }
        ],
        "submission_artifact_policy": {
            "maximum_file_size_bytes": 1_000_000,
            "maximum_package_size_bytes": 5_000_000,
            "required_artifacts": ["events.jsonl"],
        },
        "requirements": requirements,
        "setup_notes": [],
    }


def validate_authored_rules_template():
    """Apply the production untrusted-result schema before starting a live run."""
    from app.interfaces.project_agents import ProjectGuideCompilationResult

    body = authored_rules()
    body.pop("format")
    reference = {
        "source_item_id": "018f0ebc-7966-7e8d-bc4d-1cae1e000001",
        "document_version_id": "018f0ebc-7966-7e8d-bc4d-1cae1e000002",
        "sha256": "sha256:" + hashlib.sha256(GUIDE).hexdigest(),
    }
    for item in (*body["findings"], *body["requirements"]):
        item["evidence_refs"] = [reference]
    body["agent_version"] = "v1"
    ProjectGuideCompilationResult.model_validate(body)


def configure_guide(client, tokens, project_id, *, human_review_required=False):
    manager = tokens["manager"]
    guide = client.write_and_replay(
        manager,
        "project",
        "guide",
        "create",
        project_id,
        body={
            "version": "incident-summary-v1",
            "change_summary": "Fixed incident-summary CLI journey",
            "task_examples": [{"content": TASK}],
            "documents": [
                {"label": "Guide.md", "media_type": "text/markdown"},
                {"label": "workstream-rules.json", "media_type": "text/markdown"},
            ],
        },
    )
    guide_id = guide["id"]
    policies = [
        (
            "set-revision-policy",
            {"max_revision_rounds": 2, "revision_deadline_hours": 48},
        ),
    ]
    if not human_review_required:
        policies.insert(
            0,
            (
                "set-review-policy",
                {
                    "human_review_required": False,
                    "review_preference_window_seconds": 3600,
                    "review_lease_duration_seconds": 1800,
                },
            ),
        )
    for command, body in policies:
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


def _request_compilation_with_unknown_recovery(client, token, command, setup_selector):
    """Observe same-setup custody before replaying one lost dispatch response."""
    project_id, guide_id = setup_selector[-2:]
    before = client.call(token, *setup_selector)
    if before["project_id"] != project_id or before["guide_id"] != guide_id:
        raise AssertionError("public setup identity differs before compilation")
    # A short JSON client deadline may lose only the dispatch acknowledgement.
    # Read the retained setup first, then replay the identical command/key.
    # The original failure remains in the CLI receipt evidence.
    for attempt in range(3):
        candidate = client.call(token, *command, expected_exit=None)
        if "error" not in candidate:
            if (
                candidate["setup_run_id"] != before["id"]
                or candidate["setup_generation"] != before["setup_generation"]
            ):
                raise AssertionError("guide dispatch acknowledgement changed setup")
            requested = candidate
            break
        if candidate["error"] != {
            "code": "service_unavailable",
            "outcome_unknown": True,
        }:
            raise AssertionError("guide dispatch failed conclusively")
        observed = client.call(token, *setup_selector)
        if any(
            observed[field] != before[field]
            for field in (
                "id",
                "project_id",
                "guide_id",
                "source_snapshot_id",
                "setup_generation",
            )
        ):
            raise AssertionError("guide setup changed during unknown dispatch")
        if observed["status"] in {
            "failed",
            "guide_blocked",
            "compilation_invalid_terminal",
        }:
            raise AssertionError("unknown guide dispatch reached failed terminal state")
        if attempt == 2:
            raise AssertionError(
                "guide dispatch remained outcome-unknown after observation"
            )
        time.sleep(1)
    else:
        raise AssertionError("guide dispatch produced no acknowledged receipt")
    return requested


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
    setup_selector = ("project", "guide", "setup", project_id, guide_id)
    requested = _request_compilation_with_unknown_recovery(
        client, token, command, setup_selector
    )
    replay = client.call(token, *command)
    # Dispatch status may advance while the same durable request is replayed.
    for field in ("operation_id", "setup_run_id", "setup_generation"):
        if requested[field] != replay[field]:
            raise AssertionError("compilation replay changed durable request identity")
    setup = poll(
        client,
        token,
        setup_selector,
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
                    "requirement_id": "terminal.pre.incident_summary_layout",
                    "registry_entry_id": registry_entries["pre"]["registry_entry_id"],
                    "registry_entry_digest": registry_entries["pre"]["entry_digest"],
                    "configuration": {"check": "incident_summary_layout"},
                }
            ],
            "post_submit_attachments": [
                {
                    "requirement_id": "terminal.post.incident_summary_counts",
                    "registry_entry_id": registry_entries["post"]["registry_entry_id"],
                    "registry_entry_digest": registry_entries["post"]["entry_digest"],
                    "configuration": {"check": "incident_summary_counts"},
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
