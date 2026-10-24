"""Composed project plan→trial→assessment checker-core tests."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from model_transport import CompletedModelCall  # noqa: E402
from author_checker import AUTHOR_REQUIREMENT, execute_author_accuracy_check  # noqa: E402
from runtime_checker import RUNTIME_REQUIREMENT, execute_runtime_check  # noqa: E402
from trial_plan import project_trial_projection_selector  # noqa: E402
from trial_transport import CompletedTrial, TrialUnavailable  # noqa: E402


DIGEST = "sha256:" + "a" * 64
TASK_METADATA = """\
format_version = 1
id = "restart-safe-queue"
title = "Repair a restart-safe queue"
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
INSTRUCTION = "# Task\nInspect status with `queue status`.\n"
AUTHOR_NOTES = """\
# Reproduction
Apply incomplete with `sh solution/incomplete.sh`.
Remove output with `sh tests/remove-output.sh`.
Fabricate output with `sh tests/fabricate-output.sh`.
Interrupt with `sh tests/interrupt.sh`.
Restart with `sh tests/restart.sh`.
"""


def request(check: str = RUNTIME_REQUIREMENT) -> dict[str, object]:
    return {
        "request_digest": "sha256:" + "1" * 64,
        "registry": {
            "registry_entry_id": "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001",
            "entry_digest": "sha256:" + "2" * 64,
        },
        "identity": {"phase": "post_submit"},
        "configuration": {
            "check": check,
            "trial_profile_id": "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001",
            "trial_profile_version": 1,
            "trial_profile_digest": "sha256:" + "9" * 64,
            **project_trial_projection_selector(),
        },
        "input": {"requirement_id": check},
    }


def procedure(
    identifier: str,
    purpose: str,
    command_text: str,
    state_source: str,
    evidence_id: str,
    line: int,
) -> dict[str, object]:
    return {
        "procedure_id": identifier,
        "purpose": purpose,
        "command_text": command_text,
        "command": command_text.split(),
        "working_directory": ".",
        "state_source": state_source,
        "evidence_id": evidence_id,
        "start_line": line,
        "end_line": line,
    }


class FakeModelSession:
    def __init__(
        self, *, coverage_complete: bool = True, exhausted: bool = False
    ) -> None:
        self.coverage_complete = coverage_complete
        self.exhausted = exhausted
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def call(
        self, prompt: str, *, required_receipt_handles: tuple[str, ...] = ()
    ) -> CompletedModelCall:
        self.calls.append((prompt, required_receipt_handles))
        value = json.loads(prompt)
        index = len(self.calls) - 1
        if index == 0:
            output = self._plan(value)
        else:
            output = self._assessment(value)
        return CompletedModelCall(
            call_index=index,
            output=json.dumps(output),
            receipt_digest="sha256:" + str(index + 3) * 64,
            session_exhausted=self.exhausted and index == 0,
        )

    def _plan(self, prompt: dict[str, object]) -> dict[str, object]:
        procedures = [
            procedure(
                "inspect_status",
                "documented_command",
                "queue status",
                "fresh",
                "source_1",
                2,
            )
        ]
        remaining = [
            (
                "apply_incomplete",
                "incomplete_repair",
                "sh solution/incomplete.sh",
                "fresh",
                2,
            ),
            (
                "remove_output",
                "missing_output_mutation",
                "sh tests/remove-output.sh",
                "reference_baseline",
                3,
            ),
            (
                "fabricate_output",
                "fabricated_output_mutation",
                "sh tests/fabricate-output.sh",
                "reference_baseline",
                4,
            ),
            (
                "interrupt_work",
                "controlled_interruption",
                "sh tests/interrupt.sh",
                "fresh",
                5,
            ),
            (
                "restart_work",
                "restart",
                "sh tests/restart.sh",
                "interrupt_work",
                6,
            ),
        ]
        if self.coverage_complete:
            procedures.extend(
                procedure(identifier, purpose, command, state, "source_2", line)
                for identifier, purpose, command, state, line in remaining
            )
            gaps = []
        else:
            gaps = [
                {
                    "purpose": purpose,
                    "evidence_id": "source_2",
                    "start_line": 1,
                    "end_line": 1,
                }
                for _, purpose, _, _, _ in remaining
            ]
        return {
            "schema_version": "terminal_systems.trial_plan_proposal.v1",
            "material_digest": prompt["material_digest"],
            "coverage_complete": self.coverage_complete,
            "procedures": procedures,
            "coverage_gaps": gaps,
        }

    @staticmethod
    def _assessment(prompt: dict[str, object]) -> dict[str, object]:
        return {
            "schema_version": "terminal_systems.model_assessment.v1",
            "requirement_id": prompt["rubric"]["requirement_id"],
            "material_digest": prompt["untrusted_evidence_data"]["material_digest"],
            "conditions": [
                {
                    "condition_number": item["condition_number"],
                    "status": "satisfied",
                    "evidence_ids": ["trial_receipt"],
                    "finding_numbers": [],
                }
                for item in prompt["rubric"]["pass_conditions"]
            ],
            "findings": [],
        }


def trial_from_plan(
    trial_plan: dict[str, object], *, failed_reference: bool = False
) -> CompletedTrial:
    steps = []
    expected_failures = {
        "starter_verification",
        "incomplete_repair_verification",
        "missing_output_mutation_verification",
        "fabricated_output_mutation_verification",
    }
    for order, planned in enumerate(trial_plan["steps"], start=1):
        outcome = (
            "exit_nonzero" if planned["slot_kind"] in expected_failures else "succeeded"
        )
        if failed_reference and planned["slot_kind"] == "reference_verify_2":
            outcome = "exit_nonzero"
        steps.append(
            {
                "terminal_state": "completed_work",
                "slot_id": planned["slot_id"],
                "operation_order": order,
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
        )
    observations = {
        "schema_version": "workstream.checker_trial_observations.v1",
        "terminal_state": "completed_work",
        "profile_digest": DIGEST,
        "engine_identity_digest": DIGEST,
        "plan_digest": DIGEST,
        "observation_digest": DIGEST,
        "build": {"terminal_state": "completed_work", "outcome": "succeeded"},
        "steps": steps,
    }
    encoded = json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()
    return CompletedTrial(
        receipt_handle="trial_receipt_" + "b" * 32,
        receipt_digest="sha256:" + "b" * 64,
        observations=observations,
        canonical_observations=encoded,
    )


class RuntimeCheckerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "task.toml").write_text(TASK_METADATA, encoding="utf-8")
        (self.root / "instruction.md").write_text(INSTRUCTION, encoding="utf-8")
        (self.root / "AUTHOR_NOTES.md").write_text(AUTHOR_NOTES, encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_composed_runtime_check_uses_plan_call_then_receipt_bound_assessment(self):
        session = FakeModelSession()
        plans = []

        def execute(value):
            plans.append(value)
            return trial_from_plan(value)

        result = execute_runtime_check(request(), self.root, session, execute)
        self.assertEqual(
            (result["outcome"], result["verdict"]), ("completed", "passed")
        )
        self.assertEqual(len(plans), 1)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[0][1], ())
        self.assertEqual(session.calls[1][1], ("trial_receipt_" + "b" * 32,))

    def test_cited_incomplete_coverage_is_a_work_finding_without_execution(self):
        session = FakeModelSession(coverage_complete=False)

        def forbidden(_value):
            self.fail("incomplete coverage must not execute an invented plan")

        result = execute_runtime_check(request(), self.root, session, forbidden)
        self.assertEqual(
            (result["outcome"], result["verdict"]), ("completed", "failed")
        )
        self.assertEqual(
            [item["code"] for item in result["findings"]],
            ["behavioral_coverage_incomplete"],
        )
        self.assertEqual(len(session.calls), 1)

    def test_exhausted_planner_session_cannot_skip_required_assessment(self):
        result = execute_runtime_check(
            request(),
            self.root,
            FakeModelSession(exhausted=True),
            lambda value: trial_from_plan(value),
        )
        self.assertEqual(result["outcome"], "infrastructure_failed")
        self.assertEqual(
            result["infrastructure_failure_code"], "implementation_unavailable"
        )

    def test_trial_infrastructure_unavailability_never_becomes_a_work_finding(self):
        def unavailable(_value):
            raise TrialUnavailable("cleanup_unsettled")

        result = execute_runtime_check(
            request(), self.root, FakeModelSession(), unavailable
        )
        self.assertEqual(result["outcome"], "infrastructure_failed")
        self.assertEqual(result["findings"], [])

    def test_model_cannot_pass_a_failed_reference_observation(self):
        result = execute_runtime_check(
            request(),
            self.root,
            FakeModelSession(),
            lambda value: trial_from_plan(value, failed_reference=True),
        )
        self.assertEqual(result["outcome"], "infrastructure_failed")
        self.assertEqual(result["infrastructure_failure_code"], "invalid_output")

    def test_project_profile_cannot_relax_three_runs_or_protected_exclusions(self):
        for mutate in (
            lambda value: value["configuration"].update(
                trial_projection_digest="sha256:" + "0" * 64
            ),
            lambda value: value["configuration"].update(
                trial_execution={"material_projections": []}
            ),
            lambda value: value["configuration"].update(
                trial_future_authority="forbidden"
            ),
        ):
            selected = deepcopy(request())
            mutate(selected)
            result = execute_runtime_check(
                selected,
                self.root,
                FakeModelSession(),
                lambda value: trial_from_plan(value),
            )
            self.assertEqual(result["outcome"], "infrastructure_failed")
            self.assertEqual(result["infrastructure_failure_code"], "invalid_output")

    def test_author_accuracy_executes_same_invocation_trial_before_assessment(self):
        session = FakeModelSession()
        result = execute_author_accuracy_check(
            request(AUTHOR_REQUIREMENT),
            self.root,
            session,
            trial_from_plan,
        )
        self.assertEqual(
            (result["outcome"], result["verdict"]), ("completed", "passed")
        )
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[1][1], ("trial_receipt_" + "b" * 32,))

    def test_author_plan_gap_uses_fresh_proposal_finding_without_trial(self):
        session = FakeModelSession(coverage_complete=False)

        def forbidden(_value):
            self.fail("an ambiguous procedure cannot be executed")

        result = execute_author_accuracy_check(
            request(AUTHOR_REQUIREMENT), self.root, session, forbidden
        )
        self.assertEqual(
            (result["outcome"], result["verdict"]), ("completed", "failed")
        )
        self.assertEqual(
            [item["code"] for item in result["findings"]],
            ["reproduction_procedure_unavailable"],
        )


if __name__ == "__main__":
    unittest.main()
