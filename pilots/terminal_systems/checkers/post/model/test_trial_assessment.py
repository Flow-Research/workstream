"""Runtime receipt assessment and false-pass guard tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from trial_assessment import (  # noqa: E402
    RUNTIME_REQUIREMENT,
    TrialAssessmentError,
    load_runtime_rubric,
    prepare_runtime_assessment,
    validate_runtime_assessment,
)
from trial_plan import SourceEvidence  # noqa: E402
from trial_transport import CompletedTrial  # noqa: E402


DIGEST = "sha256:" + "a" * 64


def plan() -> dict[str, object]:
    steps = []

    def add(identifier: str, kind: str) -> None:
        steps.append({"slot_id": identifier, "slot_kind": kind})

    add("starter_verification", "starter_verification")
    for number in range(1, 4):
        add(f"reference_apply_{number}", f"reference_apply_{number}")
        add(f"reference_verify_{number}", f"reference_verify_{number}")
    add("inspect_status", "documented_command")
    add("apply_incomplete", "incomplete_repair")
    add("apply_incomplete_verification", "incomplete_repair_verification")
    add("remove_output", "missing_output_mutation")
    add("remove_output_verification", "missing_output_mutation_verification")
    add("fabricate_output", "fabricated_output_mutation")
    add(
        "fabricate_output_verification",
        "fabricated_output_mutation_verification",
    )
    add("interrupt_work", "controlled_interruption")
    add("restart_work", "restart")
    add("restart_work_verification", "restart_verification")
    return {"steps": steps}


def operation(identifier: str, outcome: str = "succeeded") -> dict[str, object]:
    return {
        "terminal_state": "completed_work",
        "slot_id": identifier,
        "operation_order": 1,
        "outcome": outcome,
        "exit_code": 0 if outcome == "succeeded" else 2,
        "signal": None,
        "export_outcome": "exported",
        "stdout_sha256": DIGEST,
        "stdout_byte_count": 0,
        "stderr_sha256": DIGEST,
        "stderr_byte_count": 0,
        "workspace_before_sha256": DIGEST,
        "workspace_after_sha256": DIGEST,
        "measurements_available": True,
        "elapsed_ms": 1,
        "cpu_time_ms": 1,
        "peak_memory_bytes": 1,
        "peak_pids": 1,
        "written_bytes": 0,
        "written_entries": 0,
        "measurement_method": "cgroup_v2",
    }


def completed_trial() -> CompletedTrial:
    trial_plan = plan()
    steps = []
    expected_failures = {
        "starter_verification",
        "apply_incomplete_verification",
        "remove_output_verification",
        "fabricate_output_verification",
    }
    for order, item in enumerate(trial_plan["steps"], start=1):
        value = operation(
            item["slot_id"],
            "exit_nonzero" if item["slot_id"] in expected_failures else "succeeded",
        )
        value["operation_order"] = order
        steps.append(value)
    observations = {
        "schema_version": "workstream.checker_trial_observations.v1",
        "terminal_state": "completed_work",
        "profile_digest": DIGEST,
        "engine_identity_digest": DIGEST,
        "plan_digest": DIGEST,
        "observation_digest": DIGEST,
        "build": {
            "terminal_state": "completed_work",
            "outcome": "succeeded",
        },
        "steps": steps,
    }
    encoded = json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()
    return CompletedTrial(
        receipt_handle="trial_receipt_" + "b" * 32,
        receipt_digest="sha256:" + "b" * 64,
        observations=observations,
        canonical_observations=encoded,
    )


class RuntimeAssessmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = plan()
        self.trial = completed_trial()
        self.sources = (
            SourceEvidence("source_1", "instruction.md", DIGEST, "Task rules.\n", 1),
            SourceEvidence("source_2", "AUTHOR_NOTES.md", DIGEST, "Trial notes.\n", 1),
        )
        self.prepared = prepare_runtime_assessment(
            {
                "environment": {"platform": "linux/amd64"},
                "reference": {"command": ["apply"]},
                "verification": {"command": ["verify"]},
            },
            DIGEST,
            self.sources,
            self.plan,
            self.trial,
        )

    def assessment(
        self,
        *,
        failed_condition: int | None = None,
        finding_code: str | None = None,
        evidence_id: str = "trial_receipt",
    ) -> str:
        conditions = []
        findings = []
        if failed_condition is not None:
            findings.append(
                {"code": finding_code, "evidence_id": evidence_id, "line": None}
            )
        for number in range(1, len(self.prepared.rubric.pass_conditions) + 1):
            failed = number == failed_condition
            conditions.append(
                {
                    "condition_number": number,
                    "status": "not_satisfied" if failed else "satisfied",
                    "evidence_ids": [evidence_id if failed else "trial_receipt"],
                    "finding_numbers": [1] if failed else [],
                }
            )
        return json.dumps(
            {
                "schema_version": "terminal_systems.model_assessment.v1",
                "requirement_id": RUNTIME_REQUIREMENT,
                "material_digest": self.prepared.snapshot.digest,
                "conditions": conditions,
                "findings": findings,
            }
        )

    def test_runtime_rubric_is_exact_retained_execution_rule(self):
        retained = json.loads((HERE.parents[1] / "setup-handoff.json").read_text())
        expected = {
            "source": retained["source"],
            "requirements": [
                item
                for item in retained["requirements"]
                if item["requirement_id"]
                in {
                    RUNTIME_REQUIREMENT,
                    "revision_rerun_evidence",
                }
            ],
        }
        bundled = json.loads((HERE / "execution-rubrics.json").read_text())
        self.assertEqual(bundled, expected)
        source, rubric = load_runtime_rubric()
        self.assertEqual(rubric.requirement_id, RUNTIME_REQUIREMENT)
        self.assertEqual(len(rubric.pass_conditions), 11)
        self.assertEqual(
            source["guide_sha256"],
            "13d789d4b8df5d6b310d844c622336f265d53d2ddc38e8aa101b67765f9f7183",
        )

    def test_prompt_uses_opaque_handle_out_of_band_and_binds_receipt_digest(self):
        prompt = json.loads(self.prepared.prompt)
        self.assertEqual(
            self.prepared.required_receipt_handles,
            ("trial_receipt_" + "b" * 32,),
        )
        self.assertNotIn(
            self.prepared.required_receipt_handles[0], self.prepared.prompt
        )
        self.assertEqual(
            prompt["authenticated_trial_binding"]["receipt_digest"],
            self.trial.receipt_digest,
        )

    def test_all_observed_controls_allow_a_complete_semantic_pass(self):
        findings = validate_runtime_assessment(
            self.assessment(), self.prepared, self.trial
        )
        self.assertEqual(findings, ())

    def test_failed_reference_cannot_be_hidden_by_a_model_pass(self):
        changed = deepcopy(self.trial)
        step = next(
            item
            for item in changed.observations["steps"]
            if item["slot_id"] == "reference_verify_2"
        )
        step["outcome"] = "exit_nonzero"
        step["exit_code"] = 2
        with self.assertRaisesRegex(TrialAssessmentError, "invalid_output"):
            validate_runtime_assessment(self.assessment(), self.prepared, changed)

        findings = validate_runtime_assessment(
            self.assessment(
                failed_condition=6,
                finding_code="reference_trial_failure",
                evidence_id="trial_step.reference_verify_2",
            ),
            self.prepared,
            changed,
        )
        self.assertEqual([item.code for item in findings], ["reference_trial_failure"])

    def test_verifier_workspace_mutation_cannot_pass_invalid_output_control(self):
        changed = deepcopy(self.trial)
        step = next(
            item
            for item in changed.observations["steps"]
            if item["slot_id"] == "remove_output_verification"
        )
        step["workspace_after_sha256"] = "sha256:" + "c" * 64
        with self.assertRaisesRegex(TrialAssessmentError, "invalid_output"):
            validate_runtime_assessment(self.assessment(), self.prepared, changed)

    def test_resource_failure_cannot_pass_execution_contract(self):
        for outcome, export, exit_code in (
            ("deadline_exceeded", "unavailable", None),
            ("export_invalid", "invalid", 0),
            ("disk_exceeded", "capacity_exceeded", 0),
        ):
            changed = deepcopy(self.trial)
            step = next(
                item
                for item in changed.observations["steps"]
                if item["slot_id"] == "inspect_status"
            )
            step.update(outcome=outcome, export_outcome=export, exit_code=exit_code)
            with (
                self.subTest(outcome=outcome),
                self.assertRaisesRegex(TrialAssessmentError, "invalid_output"),
            ):
                validate_runtime_assessment(self.assessment(), self.prepared, changed)


if __name__ == "__main__":
    unittest.main()
