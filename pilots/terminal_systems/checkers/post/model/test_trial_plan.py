"""Strict project trial-plan extraction and construction tests."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from trial_plan import (  # noqa: E402
    MAXIMUM_DOCUMENTED_COMMANDS,
    MAXIMUM_SOURCE_QUOTE_BYTES,
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
The exact output contract includes recovery after interruption without duplicate effects.
"""

AUTHOR_NOTES = """\
# Reproduction
Apply the incomplete repair with `sh solution/incomplete.sh`.
Remove a required output with `sh tests/remove-output.sh`.
Fabricate one output with `sh tests/fabricate-output.sh`.
Stop at the commit boundary with `sh tests/interrupt.sh`.
Restart retained work with `sh tests/restart.sh`.
"""

INSTRUCTION_WITH_BLANK_LINES = (
    "\n# Queue task\n\nInspect status with `queue status`.\n\n"
)


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
                "reference_baseline",
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
            "schema_version": "terminal_systems.trial_plan_proposal.v2",
            "material_digest": self.material_digest,
            "recovery_applicability": {
                "required": True,
                "evidence_id": "source_1",
                "start_line": 1,
                "end_line": next(
                    item.line_count
                    for item in self.evidence
                    if item.path == "instruction.md"
                ),
            },
            "coverage_complete": True,
            "procedures": procedures,
            "coverage_gaps": [],
        }

    def procedure(
        self,
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
            "source_quote": next(
                item.content.splitlines()[line - 1]
                for item in self.evidence
                if item.evidence_id == evidence_id
            ),
        }

    def validated(self, value: dict[str, object] | None = None):
        return validate_plan_proposal(
            json.dumps(value or self.proposal()),
            self.material_digest,
            self.evidence,
        )

    def test_command_citation_error_identifies_its_procedure_indices(self):
        value = self.proposal()
        value["procedures"][1]["source_quote"] = "absent exact source line"
        with self.assertRaisesRegex(TrialPlanError, "invalid_output") as caught:
            self.validated(value)
        self.assertEqual(caught.exception.procedure_indices, (1,))
        self.assertEqual(str(caught.exception), "invalid_output")
        value = self.proposal()
        value["procedures"][1]["command"] = ["sh", "solution/different.sh"]
        with self.assertRaisesRegex(TrialPlanError, "invalid_output") as caught:
            self.validated(value)
        self.assertEqual(caught.exception.procedure_indices, ())

    def test_all_independent_citation_failures_are_reported_after_structural_validation(
        self,
    ):
        value = self.proposal()
        value["procedures"][1]["source_quote"] = "absent exact source line"
        value["procedures"][2]["source_quote"] = "# Reproduction"
        value["procedures"][3]["source_quote"] = "flattened source paragraph"
        with self.assertRaisesRegex(TrialPlanError, "invalid_output") as caught:
            self.validated(value)
        self.assertEqual(caught.exception.procedure_indices, (1, 2, 3))
        for change in (
            {"evidence_id": "unknown_source"},
            {"command": ["invented"]},
            {"source_quote": []},
            {"extra": "member"},
            {"procedure_id": "apply_incomplete"},
        ):
            invalid = deepcopy(value)
            invalid["procedures"][4].update(change)
            with (
                self.subTest(change=change),
                self.assertRaises(TrialPlanError) as caught,
            ):
                self.validated(invalid)
            self.assertEqual(caught.exception.procedure_indices, ())
        invalid = deepcopy(value)
        invalid["procedures"][4] = None
        with self.assertRaises(TrialPlanError) as caught:
            self.validated(invalid)
        self.assertEqual(caught.exception.procedure_indices, ())
        invalid = deepcopy(value)
        invalid["coverage_gaps"] = [{"purpose": "restart", "evidence_id": "unknown"}]
        with self.assertRaises(TrialPlanError) as caught:
            self.validated(invalid)
        self.assertEqual(caught.exception.procedure_indices, ())

    def test_non_recovery_scope_allows_four_purposes_without_recovery_steps(self):
        """A controlled batch-correlation contract, not a live qualified package."""
        (self.root / "instruction.md").write_text(
            "# Deterministic event correlation\nInspect output with `queue status`.\n"
            "Correlate shuffled events using their identities and normalized timestamps.\n"
        )
        self.material_digest, self.evidence = collect_plan_sources(self.root)
        value = self.proposal()
        value["recovery_applicability"]["required"] = False
        value["procedures"] = value["procedures"][:-2]
        proposal = self.validated(value)
        plan = build_runtime_trial_plan(
            self.metadata, proposal, TrialPlanLimits(10000, 64, 35)
        )
        kinds = [step["slot_kind"] for step in plan["steps"]]
        self.assertNotIn("controlled_interruption", kinds)
        self.assertNotIn("restart", kinds)
        self.assertNotIn("restart_verification", kinds)
        self.assertEqual(kinds.count("reference_verify_3"), 1)

    def test_required_recovery_cannot_be_omitted_or_only_half_declared(self):
        # A real submitted metadata extension is not authority to opt out of
        # the instruction's recovery promise.
        (self.root / "task.toml").write_text(
            TASK_METADATA + "\n[extensions]\nrecovery_required = false\n"
        )
        self.metadata = parse_task_metadata(self.root)
        self.material_digest, self.evidence = collect_plan_sources(self.root)
        for remove in (1, 2):
            value = self.proposal()
            value["procedures"] = value["procedures"][:-remove]
            with (
                self.subTest(remove=remove),
                self.assertRaisesRegex(TrialPlanError, "invalid_output"),
            ):
                self.validated(value)
        value = self.proposal()
        value["recovery_applicability"]["required"] = False
        with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
            self.validated(
                value
            )  # non-applicability cannot also authorize recovery procedures

    def test_scope_citation_is_complete_instruction_not_notes_or_metadata(self):
        for key, bad in (
            ("required", 0),
            ("evidence_id", "source_2"),
            ("start_line", 2),
            ("end_line", 1),
        ):
            value = self.proposal()
            value["recovery_applicability"][key] = bad
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(TrialPlanError, "invalid_output"),
            ):
                self.validated(value)
        value = self.proposal()
        del value["recovery_applicability"]
        with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
            self.validated(value)

    def test_source_cited_plan_preserves_exact_metadata_and_three_fresh_references(
        self,
    ):
        prompt = json.loads(
            build_plan_prompt(self.metadata, self.material_digest, self.evidence)
        )
        self.assertEqual(prompt["purpose_order"], list(PURPOSE_ORDER))
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

    def test_plan_prompt_numbers_original_lines_without_changing_source_identity(self):
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=repr(newline)):
                raw = INSTRUCTION_WITH_BLANK_LINES.replace("\n", newline).encode()
                path = self.root / "instruction.md"
                path.write_bytes(raw)
                digest, sources = collect_plan_sources(self.root)
                prompt = json.loads(build_plan_prompt(self.metadata, digest, sources))
                source = prompt["untrusted_source_evidence"][0]
                self.assertNotIn("content", source)
                self.assertEqual(
                    source["numbered_content"],
                    "1 | \n2 | # Queue task\n3 | \n"
                    "4 | Inspect status with `queue status`.\n5 | ",
                )
                self.assertEqual(source["line_count"], 5)
                self.assertEqual(
                    source["sha256"], "sha256:" + hashlib.sha256(raw).hexdigest()
                )
                self.assertEqual(prompt["material_digest"], digest)
                self.assertEqual(sources[0].content.encode(), raw)
                self.assertEqual(path.read_bytes(), raw)
                self.assertEqual(collect_plan_sources(self.root), (digest, sources))

    def test_source_quotes_derive_lines_without_model_offsets(self):
        (self.root / "instruction.md").write_text(INSTRUCTION_WITH_BLANK_LINES)
        self.material_digest, self.evidence = collect_plan_sources(self.root)
        value = self.proposal()
        value["procedures"][0]["source_quote"] = "Inspect status with `queue status`."
        proposal = self.validated(value)
        self.assertEqual(proposal.procedures[0]["start_line"], 4)
        self.assertEqual(proposal.procedures[0]["end_line"], 4)
        contract = json.loads(
            build_plan_prompt(self.metadata, self.material_digest, self.evidence)
        )["output_contract"]["procedures"][0]
        self.assertIn("source_quote", contract)
        self.assertNotIn("start_line", contract)
        self.assertNotIn("end_line", contract)

        for field, wrong in (
            ("source_quote", "queue status"),
            ("source_quote", "4 | Inspect status with `queue status`."),
            ("command_text", "4 | queue status"),
            ("command", ["queue", "erase-everything"]),
            ("evidence_id", "source_2"),
        ):
            invalid = deepcopy(value)
            invalid["procedures"][0][field] = wrong
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(TrialPlanError, "invalid_output"),
            ):
                self.validated(invalid)

    def test_old_procedure_line_fields_are_rejected(self):
        for keys in ({"start_line": 2, "end_line": 2}, {"start_line": 2}):
            value = self.proposal()
            value["procedures"][0].update(keys)
            with (
                self.subTest(keys=keys),
                self.assertRaisesRegex(TrialPlanError, "invalid_output"),
            ):
                self.validated(value)
        value = self.proposal()
        del value["procedures"][0]["source_quote"]
        value["procedures"][0].update(start_line=2, end_line=2)
        with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
            self.validated(value)

    def test_ambiguous_quote_requires_unique_surrounding_full_lines(self):
        text = "# First\nInspect status with `queue status`.\n# Second\nInspect status with `queue status`.\n"
        (self.root / "instruction.md").write_text(text)
        self.material_digest, self.evidence = collect_plan_sources(self.root)
        value = self.proposal()
        with self.assertRaisesRegex(TrialPlanError, "invalid_output") as caught:
            self.validated(value)
        self.assertEqual(caught.exception.procedure_indices, (0,))
        value["procedures"][0]["source_quote"] = (
            "# Second\nInspect status with `queue status`."
        )
        procedure = self.validated(value).procedures[0]
        self.assertEqual((procedure["start_line"], procedure["end_line"]), (3, 4))

    def test_quotes_preserve_multiline_encoding_and_old_source_authority(self):
        command = "python3 -c 'print(\"café\")\nprint(2)'"
        instruction = "# Queue task\n\n```sh\n" + command + "\n```\n"
        for newline in ("\n", "\r\n"):
            raw = instruction.replace("\n", newline).encode("utf-8")
            (self.root / "instruction.md").write_bytes(raw)
            self.material_digest, self.evidence = collect_plan_sources(self.root)
            value = self.proposal()
            value["procedures"][0].update(
                command_text=command, command=shlex.split(command), source_quote=command
            )
            proposal = self.validated(value)
            self.assertEqual(proposal.procedures[0]["start_line"], 4)
            self.assertEqual(proposal.procedures[0]["end_line"], 5)
            self.assertEqual(
                self.evidence[0].sha256, "sha256:" + hashlib.sha256(raw).hexdigest()
            )
            for procedure in proposal.procedures:
                source = next(
                    item
                    for item in self.evidence
                    if item.evidence_id == procedure["evidence_id"]
                )
                # Every new accepted quote maps to the previous source/argv
                # checks with engine-derived bounds; it adds no argv authority.
                cited = "\n".join(
                    source.content.splitlines()[
                        procedure["start_line"] - 1 : procedure["end_line"]
                    ]
                )
                self.assertIn(procedure["command_text"], cited)
                self.assertEqual(
                    shlex.split(procedure["command_text"], posix=True),
                    procedure["command"],
                )
            invalid = deepcopy(value)
            invalid["procedures"][0]["source_quote"] = command.replace("café", "cafe")
            with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
                self.validated(invalid)
            if newline == "\r\n":
                invalid["procedures"][0]["source_quote"] = command.replace("\n", "\r\n")
                with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
                    self.validated(invalid)

    def test_quote_size_is_utf8_bounded_and_invalid_text_fails_closed(self):
        prefix = "Inspect `queue status`. "
        remaining = MAXIMUM_SOURCE_QUOTE_BYTES - len(prefix.encode("utf-8"))
        exact = prefix + "é" * (remaining // 2) + " " * (remaining % 2)
        for quote in (exact, exact + "é"):
            (self.root / "instruction.md").write_text("# Task\n" + quote + "\n")
            self.material_digest, self.evidence = collect_plan_sources(self.root)
            value = self.proposal()
            self.assertEqual(value["procedures"][0]["source_quote"], quote)
            if len(quote.encode("utf-8")) == MAXIMUM_SOURCE_QUOTE_BYTES:
                self.assertTrue(self.validated(value).coverage_complete)
            else:
                with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
                    self.validated(value)
        for quote in ("\ud800", "", [], True):
            value = self.proposal()
            value["procedures"][0]["source_quote"] = quote
            with (
                self.subTest(quote_type=type(quote).__name__),
                self.assertRaisesRegex(TrialPlanError, "invalid_output"),
            ):
                self.validated(value)

    def test_overlapping_source_windows_are_ambiguous_without_context(self):
        line = "Inspect status with `queue status`."
        (self.root / "instruction.md").write_text("\n".join([line] * 3))
        self.material_digest, self.evidence = collect_plan_sources(self.root)
        value = self.proposal()
        value["procedures"][0]["source_quote"] = "\n".join([line] * 2)
        with self.assertRaisesRegex(TrialPlanError, "invalid_output"):
            self.validated(value)
        value["procedures"][0]["source_quote"] = "\n".join([line] * 3)
        procedure = self.validated(value).procedures[0]
        self.assertEqual((procedure["start_line"], procedure["end_line"]), (1, 3))

    def test_interruption_requires_repaired_baseline_even_for_partial_coverage(self):
        prompt = json.loads(
            build_plan_prompt(self.metadata, self.material_digest, self.evidence)
        )
        self.assertEqual(
            prompt["state_rules"]["controlled_interruption"], "reference_baseline"
        )
        for complete in (True, False):
            value = self.proposal()
            value["procedures"][-2]["state_source"] = "fresh"
            if not complete:
                value["coverage_complete"] = False
                value["procedures"].pop(0)
                value["coverage_gaps"] = [
                    {
                        "purpose": "documented_command",
                        "evidence_id": "source_1",
                        "start_line": 2,
                        "end_line": 2,
                    }
                ]
            with (
                self.subTest(complete=complete),
                self.assertRaisesRegex(TrialPlanError, "invalid_output"),
            ):
                self.validated(value)

    def test_repaired_recovery_uses_retained_code_and_exact_parent_states(self):
        # Local subprocess semantics only: the shared runtime owns isolation and
        # authenticated exports. The deliberately broken code cannot recover a
        # pending commit; the reference changes that code, not expected output.
        for directory in ("workspace", "solution", "tests"):
            (self.root / directory).mkdir()
        worker = """\
import os
from pathlib import Path
import signal
import sys

state = Path(sys.argv[2])
state.mkdir(exist_ok=True)
pending = state / 'pending'
committed = state / 'committed'
if sys.argv[1] == 'interrupt':
    pending.write_text('durable-job-result')
    os.kill(os.getpid(), signal.SIGTERM)
elif sys.argv[1] == 'restart' and pending.exists():
    pass  # broken recovery
"""
        repaired = worker.replace(
            "pass  # broken recovery", "pending.replace(committed)"
        )
        (self.root / "workspace/worker.py").write_text(worker)
        (self.root / "solution/repaired.py").write_text(repaired)
        (self.root / "solution/apply.sh").write_text(
            "cp solution/repaired.py workspace/worker.py\n"
        )
        (self.root / "tests/interrupt.sh").write_text(
            f"exec {sys.executable} workspace/worker.py interrupt workspace/state\n"
        )
        (self.root / "tests/restart.sh").write_text(
            f"exec {sys.executable} workspace/worker.py restart workspace/state\n"
        )
        (self.root / "tests/verify.py").write_text("""\
from pathlib import Path
import subprocess
import sys
import tempfile

with tempfile.TemporaryDirectory() as temporary:
    state = Path(temporary)
    (state / 'pending').write_text('durable-job-result')
    subprocess.run([sys.executable, 'workspace/worker.py', 'restart', temporary], check=True)
    assert (state / 'committed').read_text() == 'durable-job-result'
state = Path('workspace/state')
if state.exists():
    assert not (state / 'pending').exists()
    assert (state / 'committed').read_text() == 'durable-job-result'
""")
        (self.root / "tests/run.sh").write_text(
            f"exec {sys.executable} tests/verify.py\n"
        )
        plan = build_runtime_trial_plan(
            self.metadata,
            self.validated(),
            TrialPlanLimits(maximum_entries=100, pids=16, maximum_steps=35),
        )
        steps = {item["slot_id"]: item for item in plan["steps"]}
        templates = {item["slot_kind"]: item for item in project_slot_templates()}
        interruption = templates["controlled_interruption"]
        self.assertFalse(interruption["fresh_workspace"])
        self.assertEqual(interruption["seed_roles"], [])
        self.assertTrue(templates["incomplete_repair"]["fresh_workspace"])
        self.assertEqual(steps["apply_incomplete"]["state_source"], "fresh")
        self.assertEqual(steps["interrupt_work"]["state_source"], "reference_verify_3")
        self.assertEqual(steps["restart_work"]["state_source"], "interrupt_work")
        self.assertEqual(
            steps["restart_work_verification"]["state_source"], "restart_work"
        )
        exports = {}
        for identifier, expected in (
            ("starter_verification", 1),
            ("reference_apply_3", 0),
            ("reference_verify_3", 0),
            ("interrupt_work", -15),
            ("restart_work", 0),
            ("restart_work_verification", 0),
        ):
            step = steps[identifier]
            template = templates[step["slot_kind"]]
            state = Path(self.temporary.name) / identifier
            state.mkdir()
            source = step["state_source"]
            if source == "fresh":
                self.assertIn("workspace_seed", template["seed_roles"])
                shutil.copytree(self.root / "workspace", state / "workspace")
            else:
                self.assertFalse(template["fresh_workspace"])
                shutil.copytree(exports[source], state / "workspace")
            for role in step["visible_roles"]:
                self.assertIn(role, template["visible_roles"])
                directory = {"verification": "tests", "reference": "solution"}[role]
                shutil.copytree(self.root / directory, state / directory)
            if identifier in {
                "interrupt_work",
                "restart_work",
                "restart_work_verification",
            }:
                self.assertEqual(step["visible_roles"], ["verification"])
                self.assertEqual(template["visible_roles"], ["verification"])
                self.assertFalse((state / "solution").exists())
            result = subprocess.run(
                step["command"], cwd=state, capture_output=True, timeout=5
            )
            with self.subTest(slot=identifier):
                if identifier == "starter_verification":
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(b"committed", result.stderr)
                else:
                    self.assertEqual(result.returncode, expected, result.stderr)
            exports[identifier] = state / "workspace"

    def test_project_templates_make_all_three_reference_runs_mandatory(self):
        templates = project_slot_templates()
        by_kind = {item["slot_kind"]: item for item in templates}
        for number in range(1, 4):
            for prefix in ("reference_apply", "reference_verify"):
                item = by_kind[f"{prefix}_{number}"]
                self.assertEqual(item["minimum_occurrences"], 1)
                self.assertEqual(item["maximum_occurrences"], 1)
        for kind in ("controlled_interruption", "restart", "restart_verification"):
            self.assertEqual(by_kind[kind]["minimum_occurrences"], 0)
            self.assertEqual(by_kind[kind]["maximum_occurrences"], 1)
        self.assertEqual(
            by_kind["documented_command"]["maximum_occurrences"],
            MAXIMUM_DOCUMENTED_COMMANDS,
            MAXIMUM_SOURCE_QUOTE_BYTES,
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
