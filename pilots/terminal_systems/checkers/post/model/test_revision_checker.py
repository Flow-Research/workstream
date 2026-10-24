"""Owner-bound revision context and fresh rerun tests."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from model_transport import CompletedModelCall  # noqa: E402
from revision_checker import (  # noqa: E402
    REVISION_OBJECTIVE_REQUIREMENT,
    REVISION_RERUN_REQUIREMENT,
    execute_revision_objective_check,
    execute_revision_rerun_check,
)
from trial_plan import project_trial_projection_selector  # noqa: E402
from trial_transport import CompletedTrial  # noqa: E402


DIGEST = "sha256:" + "a" * 64
TASK_METADATA = """\
format_version = 1
id = "revision-task"
title = "Revision task"
[environment]
dockerfile = "environment/Dockerfile"
context = "."
platform = "linux/amd64"
[reference]
command = ["sh", "solution/apply.sh"]
working_directory = "."
[verification]
command = ["sh", "tests/run.sh"]
working_directory = "."
[resources]
cpu_millis = 1000
memory_bytes = 536870912
disk_bytes = 1073741824
build_timeout_seconds = 30
reference_timeout_seconds = 20
verification_timeout_seconds = 10
"""


def context(kind: str) -> dict[str, object]:
    if kind == "initial":
        return {
            "schema_version": "workstream.post_submit_evaluation_context.v1",
            "kind": "initial",
            "source": None,
            "predecessor": None,
            "feedback": None,
        }
    return {
        "schema_version": "workstream.post_submit_evaluation_context.v1",
        "kind": "checker_remediation",
        "source": {"revision_round": 1},
        "predecessor": {"content_sha256": DIGEST},
        "feedback": {"members": [{"code": "needs_change"}]},
    }


def request(requirement: str, kind: str) -> dict[str, object]:
    configuration = {"check": requirement}
    if requirement == REVISION_RERUN_REQUIREMENT:
        configuration.update(
            {
                "trial_profile_id": "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001",
                "trial_profile_version": 1,
                "trial_profile_digest": "sha256:" + "9" * 64,
                **project_trial_projection_selector(revision=True),
            }
        )
    return {
        "request_digest": "sha256:" + "1" * 64,
        "registry": {
            "registry_entry_id": "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001",
            "entry_digest": "sha256:" + "2" * 64,
        },
        "identity": {"phase": "post_submit"},
        "configuration": configuration,
        "input": {
            "requirement_id": requirement,
            "evaluation_context": context(kind),
        },
    }


class RevisionModel:
    def __init__(self, *, invalid_location: bool = False) -> None:
        self.calls = 0
        self.invalid_location = invalid_location

    def call(self, prompt: str, *, required_receipt_handles=()):
        self.calls += 1
        value = json.loads(prompt)
        if self.invalid_location:
            findings = [
                {
                    "code": "revision_change_unexplained",
                    "evidence_id": "prior_instruction",
                    "line": 1,
                }
            ]
            conditions = [
                {
                    "condition_number": 1,
                    "status": "not_satisfied",
                    "evidence_ids": ["prior_instruction"],
                    "finding_numbers": [1],
                },
                {
                    "condition_number": 2,
                    "status": "satisfied",
                    "evidence_ids": ["current_author_notes"],
                    "finding_numbers": [],
                },
                {
                    "condition_number": 3,
                    "status": "satisfied",
                    "evidence_ids": ["current_instruction"],
                    "finding_numbers": [],
                },
            ]
        else:
            findings = []
            condition_evidence = (
                "current_author_notes",
                "current_author_notes",
                "current_instruction",
            )
            conditions = [
                {
                    "condition_number": number,
                    "status": "satisfied",
                    "evidence_ids": [condition_evidence[number - 1]],
                    "finding_numbers": [],
                }
                for number in range(1, 4)
            ]
        output = {
            "schema_version": "terminal_systems.model_assessment.v1",
            "requirement_id": REVISION_OBJECTIVE_REQUIREMENT,
            "material_digest": value["untrusted_evidence_data"]["material_digest"],
            "conditions": conditions,
            "findings": findings,
        }
        return CompletedModelCall(0, json.dumps(output), DIGEST, True)


def trial_from_plan(
    plan: dict[str, object], *, verification_fails=False
) -> CompletedTrial:
    steps = []
    for order, item in enumerate(plan["steps"], start=1):
        outcome = (
            "exit_nonzero"
            if verification_fails and item["slot_id"] == "revision_verification"
            else "succeeded"
        )
        steps.append(
            {
                "slot_id": item["slot_id"],
                "operation_order": order,
                "outcome": outcome,
            }
        )
    observations = {
        "schema_version": "workstream.checker_trial_observations.v1",
        "terminal_state": "completed_work",
        "profile_digest": DIGEST,
        "engine_identity_digest": DIGEST,
        "plan_digest": DIGEST,
        "observation_digest": DIGEST,
        "build": {"outcome": "succeeded"},
        "steps": steps,
    }
    return CompletedTrial(
        "trial_receipt_" + "b" * 32,
        "sha256:" + "b" * 64,
        observations,
        json.dumps(observations).encode(),
    )


class RevisionCheckerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.current_temp = tempfile.TemporaryDirectory()
        self.prior_temp = tempfile.TemporaryDirectory()
        self.current = Path(self.current_temp.name)
        self.prior = Path(self.prior_temp.name)
        for root, label in ((self.current, "current"), (self.prior, "prior")):
            (root / "instruction.md").write_text(
                f"{label} objective\n", encoding="utf-8"
            )
            (root / "AUTHOR_NOTES.md").write_text(f"{label} notes\n", encoding="utf-8")
        (self.current / "task.toml").write_text(TASK_METADATA, encoding="utf-8")

    def tearDown(self) -> None:
        self.current_temp.cleanup()
        self.prior_temp.cleanup()

    def test_initial_submission_passes_both_conditional_rules_without_calls(self):
        model = RevisionModel()
        objective = execute_revision_objective_check(
            request(REVISION_OBJECTIVE_REQUIREMENT, "initial"),
            self.current,
            model,
            predecessor_root=self.prior,
        )
        rerun = execute_revision_rerun_check(
            request(REVISION_RERUN_REQUIREMENT, "initial"),
            self.current,
            lambda _plan: self.fail("initial submission must not run a revision trial"),
        )
        self.assertEqual((objective["verdict"], rerun["verdict"]), ("passed", "passed"))
        self.assertEqual(model.calls, 0)

    def test_revision_objective_uses_current_prior_and_feedback(self):
        model = RevisionModel()
        result = execute_revision_objective_check(
            request(REVISION_OBJECTIVE_REQUIREMENT, "checker_remediation"),
            self.current,
            model,
            predecessor_root=self.prior,
        )
        self.assertEqual(
            (result["outcome"], result["verdict"]), ("completed", "passed")
        )
        self.assertEqual(model.calls, 1)

    def test_revision_finding_cannot_point_at_hidden_predecessor_path(self):
        result = execute_revision_objective_check(
            request(REVISION_OBJECTIVE_REQUIREMENT, "checker_remediation"),
            self.current,
            RevisionModel(invalid_location=True),
            predecessor_root=self.prior,
        )
        self.assertEqual(result["outcome"], "infrastructure_failed")
        self.assertEqual(result["infrastructure_failure_code"], "invalid_output")

    def test_revision_rerun_is_exact_order_and_failure_is_work_evidence(self):
        plans = []

        def success(plan):
            plans.append(plan)
            return trial_from_plan(plan)

        passed = execute_revision_rerun_check(
            request(REVISION_RERUN_REQUIREMENT, "checker_remediation"),
            self.current,
            success,
        )
        self.assertEqual(passed["verdict"], "passed")
        self.assertEqual(
            [item["slot_id"] for item in plans[0]["steps"]],
            ["revision_reference", "revision_verification"],
        )

        failed = execute_revision_rerun_check(
            request(REVISION_RERUN_REQUIREMENT, "checker_remediation"),
            self.current,
            lambda plan: trial_from_plan(plan, verification_fails=True),
        )
        self.assertEqual(
            (failed["outcome"], failed["verdict"]), ("completed", "failed")
        )
        self.assertEqual(failed["findings"][0]["code"], "revision_rerun_failure")

    def test_missing_predecessor_material_is_infrastructure_not_work(self):
        (self.prior / "instruction.md").unlink()
        result = execute_revision_objective_check(
            request(REVISION_OBJECTIVE_REQUIREMENT, "checker_remediation"),
            self.current,
            RevisionModel(),
            predecessor_root=self.prior,
        )
        self.assertEqual(result["outcome"], "infrastructure_failed")
        self.assertEqual(result["infrastructure_failure_code"], "material_unavailable")
        self.assertEqual(result["findings"], [])


if __name__ == "__main__":
    unittest.main()
