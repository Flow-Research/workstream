"""Strict project trial-plan extraction and construction tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from trial_plan import (  # noqa: E402
    MAXIMUM_DOCUMENTED_COMMANDS,
    PURPOSE_ORDER,
    TrialPlanError,
    TrialPlanLimits,
    build_plan_prompt,
    build_revision_rerun_plan,
    build_runtime_trial_plan,
    collect_plan_sources,
    parse_task_metadata,
    project_slot_templates,
    project_revision_trial_execution_projection,
    project_trial_execution_projection,
    validate_plan_proposal,
)


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

INSTRUCTION = """\
# Queue task
Inspect status with `queue status`.
The exact output contract is documented here.
"""

AUTHOR_NOTES = """\
# Reproduction
Apply the incomplete repair with `sh solution/incomplete.sh`.
Remove a required output with `sh tests/remove-output.sh`.
Fabricate one output with `sh tests/fabricate-output.sh`.
Stop at the commit boundary with `sh tests/interrupt.sh`.
Restart retained work with `sh tests/restart.sh`.
"""


class TrialPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "task.toml").write_text(TASK_METADATA, encoding="utf-8")
        (self.root / "instruction.md").write_text(INSTRUCTION, encoding="utf-8")
        (self.root / "AUTHOR_NOTES.md").write_text(AUTHOR_NOTES, encoding="utf-8")
        self.material_digest, self.evidence = collect_plan_sources(self.root)
        self.metadata = parse_task_metadata(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def proposal(self) -> dict[str, object]:
        procedures = [
            self.procedure(
                "inspect_status",
                "documented_command",
                "queue status",
                "fresh",
                "source_1",
                2,
            ),
            self.procedure(
                "apply_incomplete",
                "incomplete_repair",
                "sh solution/incomplete.sh",
                "fresh",
                "source_2",
                2,
            ),
            self.procedure(
                "remove_output",
                "missing_output_mutation",
                "sh tests/remove-output.sh",
                "reference_baseline",
                "source_2",
                3,
            ),
            self.procedure(
                "fabricate_output",
                "fabricated_output_mutation",
                "sh tests/fabricate-output.sh",
                "reference_baseline",
                "source_2",
                4,
            ),
            self.procedure(
                "interrupt_work",
                "controlled_interruption",
                "sh tests/interrupt.sh",
                "fresh",
                "source_2",
                5,
            ),
            self.procedure(
                "restart_work",
                "restart",
                "sh tests/restart.sh",
                "interrupt_work",
                "source_2",
                6,
            ),
        ]
        return {
            "schema_version": "terminal_systems.trial_plan_proposal.v1",
            "material_digest": self.material_digest,
            "coverage_complete": True,
            "procedures": procedures,
            "coverage_gaps": [],
        }

    @staticmethod
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

    def validated(self, value: dict[str, object] | None = None):
        return validate_plan_proposal(
            json.dumps(value or self.proposal()),
            self.material_digest,
            self.evidence,
        )

    def test_source_cited_plan_preserves_exact_metadata_and_three_fresh_references(
        self,
    ):
        prompt = json.loads(
            build_plan_prompt(self.metadata, self.material_digest, self.evidence)
        )
        self.assertEqual(prompt["required_purpose_order"], list(PURPOSE_ORDER))
        self.assertEqual(
            prompt["maximum_documented_commands"], MAXIMUM_DOCUMENTED_COMMANDS
        )

        plan = build_runtime_trial_plan(
            self.metadata,
            self.validated(),
            TrialPlanLimits(maximum_entries=10_000, pids=64, maximum_steps=35),
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan["environment"], self.metadata["environment"])
        steps = plan["steps"]
        references = [
            item for item in steps if item["slot_kind"].startswith("reference_apply_")
        ]
        self.assertEqual(len(references), 3)
        self.assertEqual({item["state_source"] for item in references}, {"fresh"})
        self.assertEqual(
            {tuple(item["command"]) for item in references},
            {("sh", "solution/apply.sh")},
        )
        for number in range(1, 4):
            verification = next(
                item
                for item in steps
                if item["slot_id"] == f"reference_verify_{number}"
            )
            self.assertEqual(verification["state_source"], f"reference_apply_{number}")
        missing = next(item for item in steps if item["slot_id"] == "remove_output")
        self.assertEqual(missing["state_source"], "reference_verify_3")
        self.assertNotIn("workspace_seed", missing["visible_roles"])
        for identifier in (
            "apply_incomplete",
            "remove_output",
            "fabricate_output",
            "restart_work",
        ):
            followup = next(
                item
                for item in steps
                if item["slot_id"] == f"{identifier}_verification"
            )
            self.assertEqual(followup["state_source"], identifier)
            self.assertEqual(followup["command"], ["sh", "tests/run.sh"])

    def test_plan_digest_binds_task_metadata_without_exposing_it_as_argv_evidence(self):
        original = self.material_digest
        (self.root / "task.toml").write_text(
            TASK_METADATA.replace(
                "reference_timeout_seconds = 20", "reference_timeout_seconds = 21"
            ),
            encoding="utf-8",
        )
        changed, evidence = collect_plan_sources(self.root)
        self.assertNotEqual(changed, original)
        self.assertEqual(
            [item.path for item in evidence], ["instruction.md", "AUTHOR_NOTES.md"]
        )

    def test_project_templates_make_all_three_reference_runs_mandatory(self):
        templates = project_slot_templates()
        by_kind = {item["slot_kind"]: item for item in templates}
        for number in range(1, 4):
            for prefix in ("reference_apply", "reference_verify"):
                item = by_kind[f"{prefix}_{number}"]
                self.assertEqual(item["minimum_occurrences"], 1)
                self.assertEqual(item["maximum_occurrences"], 1)
        self.assertEqual(
            by_kind["documented_command"]["maximum_occurrences"],
            MAXIMUM_DOCUMENTED_COMMANDS,
        )
        self.assertEqual(
            sum(item["maximum_occurrences"] for item in templates),
            35,
        )

    def test_project_projection_excludes_author_only_build_material(self):
        projection = project_trial_execution_projection()
        build = projection["material_projections"][0]
        self.assertEqual(build["source_role"], "submission_archive")
        self.assertEqual(build["exclusions"], ["AUTHOR_NOTES.md", "solution", "tests"])
        by_role = {item["role"]: item for item in projection["material_projections"]}
        self.assertEqual(by_role["workspace_seed"]["source_relative"], "workspace")
        self.assertEqual(by_role["workspace_seed"]["destination_relative"], "workspace")
        self.assertEqual(by_role["reference"]["projection_kind"], "state_overlay")
        self.assertEqual(by_role["verification"]["projection_kind"], "state_overlay")
        self.assertEqual(projection["slot_templates"], list(project_slot_templates()))

    def test_revision_projection_runs_exact_fresh_reference_then_full_suite(self):
        projection = project_revision_trial_execution_projection()
        self.assertEqual(
            [item["slot_kind"] for item in projection["slot_templates"]],
            ["revision_reference", "revision_verification"],
        )
        self.assertTrue(projection["slot_templates"][0]["fresh_workspace"])
        self.assertFalse(projection["slot_templates"][1]["fresh_workspace"])
        revision = build_revision_rerun_plan(
            self.metadata,
            TrialPlanLimits(maximum_entries=100, pids=16, maximum_steps=2),
        )
        self.assertEqual(
            [item["slot_kind"] for item in revision["steps"]],
            ["revision_reference", "revision_verification"],
        )
        self.assertEqual(revision["steps"][0]["state_source"], "fresh")
        self.assertEqual(revision["steps"][1]["state_source"], "revision_reference")

    def test_complete_plan_rejects_missing_reordered_or_invented_procedures(self):
        missing = self.proposal()
        missing["procedures"] = missing["procedures"][:-1]
        reordered = self.proposal()
        reordered["procedures"][1], reordered["procedures"][2] = (
            reordered["procedures"][2],
            reordered["procedures"][1],
        )
        invented = self.proposal()
        invented["procedures"][0]["command_text"] = "queue erase-everything"
        invented["procedures"][0]["command"] = ["queue", "erase-everything"]
        for value in (missing, reordered, invented):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(TrialPlanError, "invalid_output"),
            ):
                self.validated(value)

    def test_noncanonical_paths_and_wrong_typed_model_fields_fail_closed(self):
        for alias in ("a//b", "a/./b", "./a"):
            value = self.proposal()
            value["procedures"][0]["working_directory"] = alias
            with (
                self.subTest(alias=alias),
                self.assertRaisesRegex(TrialPlanError, "invalid_output"),
            ):
                self.validated(value)
        for field, invalid in (
            ("purpose", []),
            ("evidence_id", {}),
            ("state_source", []),
        ):
            value = self.proposal()
            value["procedures"][0][field] = invalid
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(TrialPlanError, "invalid_output"),
            ):
                self.validated(value)
        incomplete = self.proposal()
        incomplete["coverage_complete"] = False
        incomplete["procedures"] = incomplete["procedures"][:-1]
        incomplete["coverage_gaps"] = [
            {
                "purpose": "restart",
                "evidence_id": [],
                "start_line": 1,
                "end_line": 1,
            }
        ]
        with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
            self.validated(incomplete)

    def test_duplicate_keys_and_non_json_constants_are_rejected(self):
        encoded = json.dumps(self.proposal())
        duplicate = encoded.replace(
            '"coverage_complete": true',
            '"coverage_complete": true, "coverage_complete": true',
            1,
        )
        non_json = encoded.replace(
            '"coverage_complete": true', '"coverage_complete": NaN'
        )
        for raw in (duplicate, non_json):
            with (
                self.subTest(raw=raw),
                self.assertRaisesRegex(TrialPlanError, "invalid_output"),
            ):
                validate_plan_proposal(raw, self.material_digest, self.evidence)

    def test_incomplete_coverage_requires_cited_gap_for_every_omitted_purpose(self):
        value = self.proposal()
        value["coverage_complete"] = False
        value["procedures"] = value["procedures"][:1]
        value["coverage_gaps"] = [
            {
                "purpose": purpose,
                "evidence_id": "source_2",
                "start_line": 1,
                "end_line": 1,
            }
            for purpose in PURPOSE_ORDER[1:]
        ]
        proposal = self.validated(value)
        self.assertIsNone(
            build_runtime_trial_plan(
                self.metadata,
                proposal,
                TrialPlanLimits(maximum_entries=100, pids=16, maximum_steps=35),
            )
        )
        value["coverage_gaps"].pop()
        with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
            self.validated(value)

    def test_trusted_step_ceiling_rejects_otherwise_valid_model_plan(self):
        with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
            build_runtime_trial_plan(
                self.metadata,
                self.validated(),
                TrialPlanLimits(maximum_entries=100, pids=16, maximum_steps=16),
            )

    def test_metadata_is_closed_and_platform_is_explicit_linux(self):
        invalid_values = (
            TASK_METADATA + "\nunknown = 1\n",
            TASK_METADATA.replace('platform = "linux/amd64"', 'platform = "amd64"'),
            TASK_METADATA.replace("cpu_millis = 1000", "cpu_millis = true"),
            TASK_METADATA.replace('context = "."', 'context = "a//b"'),
            TASK_METADATA.replace('context = "."', 'context = "a/./b"'),
            TASK_METADATA.replace('context = "."', 'context = "./a"'),
        )
        for content in invalid_values:
            with self.subTest(content=content):
                (self.root / "task.toml").write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(TrialPlanError, "material_unavailable"):
                    parse_task_metadata(self.root)

    def test_runtime_ids_cannot_collide_with_server_generated_followup(self):
        value = deepcopy(self.proposal())
        value["procedures"][0]["procedure_id"] = "apply_incomplete_verification"
        proposal = self.validated(value)
        with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
            build_runtime_trial_plan(
                self.metadata,
                proposal,
                TrialPlanLimits(maximum_entries=100, pids=16, maximum_steps=35),
            )


if __name__ == "__main__":
    unittest.main()
