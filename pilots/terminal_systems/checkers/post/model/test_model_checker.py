"""Source parity, material safety and evidence-validation tests."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from assessment import AssessmentError, build_prompt, validate_assessment  # noqa: E402
from material import MaterialError, MaterialLimits, collect_material  # noqa: E402
from result import completed_result, infrastructure_result  # noqa: E402
from rubric import AGENT_CHECKS, BLOCKED_CHECKS, SUPPORTED_CHECKS, load_rubrics  # noqa: E402


HANDOFF = HERE.parents[1] / "setup-handoff.json"
LIMITS = MaterialLimits(
    maximum_entries=100,
    maximum_file_bytes=64 * 1024,
    maximum_total_bytes=256 * 1024,
)


def projected_handoff() -> dict:
    value = json.loads(HANDOFF.read_text(encoding="utf-8"))
    projection = {
        "source": value["source"],
        "requirements": [
            {
                "requirement_id": item["requirement_id"],
                "statement": item["statement"],
                "evidence_refs": item["evidence_refs"],
                "check_specification": {
                    key: item["check_specification"][key]
                    for key in (
                        "inputs",
                        "check_steps",
                        "pass_conditions",
                        "failure_findings",
                    )
                },
            }
            for item in value["requirements"]
            if item["disposition"] == "post_submit_capability_gap"
            and item["check_specification"]["evaluation_method"] == "model_evaluation"
        ],
    }
    verification = next(
        item
        for item in projection["requirements"]
        if item["requirement_id"] == "verification_independence"
    )
    verification["check_specification"]["inputs"].insert(
        1,
        {
            "input_id": "task_metadata",
            "kind": "relative_file",
            "relative_path": "task.toml",
            "purpose": "Supplies the authoritative reference and verification command selectors and working directories.",
        },
    )
    author_accuracy = next(
        item
        for item in projection["requirements"]
        if item["requirement_id"] == "author_evidence_accuracy"
    )
    author_accuracy["check_specification"]["failure_findings"].insert(
        2,
        {
            "code": "reproduction_procedure_unavailable",
            "level": "error",
            "condition": "An exact procedure needed to compare author claims with authenticated trials is absent or ambiguous, so accuracy cannot be established.",
            "message": "Author evidence cannot be established without an exact reproducible procedure.",
        },
    )
    return projection


class RubricParityTests(unittest.TestCase):
    def test_bundled_rubrics_are_retained_handoff_plus_source_correction(self):
        bundled = json.loads((HERE / "rubrics.json").read_text(encoding="utf-8"))
        self.assertEqual(bundled, projected_handoff())
        source, rubrics = load_rubrics()
        self.assertEqual(source, bundled["source"])
        self.assertEqual(
            set(rubrics), SUPPORTED_CHECKS | AGENT_CHECKS | set(BLOCKED_CHECKS)
        )

    def test_missing_runtime_owner_inputs_remain_explicit(self):
        self.assertEqual(
            BLOCKED_CHECKS,
            {},
        )


class MaterialTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "workspace").mkdir()
        (self.root / "solution").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "instruction.md").write_text("Solve the task.\n", encoding="utf-8")
        (self.root / "AUTHOR_NOTES.md").write_text(
            "Evidence notes.\n", encoding="utf-8"
        )
        (self.root / "task.toml").write_text("format_version = 1\n", encoding="utf-8")
        (self.root / "workspace" / "app.py").write_text(
            "print('start')\n", encoding="utf-8"
        )
        (self.root / "solution" / "app.py").write_text(
            "print('fixed')\n", encoding="utf-8"
        )
        (self.root / "tests" / "test_app.py").write_text(
            "assert True\n", encoding="utf-8"
        )
        _, self.rubrics = load_rubrics()

    def tearDown(self):
        self.temporary.cleanup()

    def test_package_scope_is_complete_deterministic_and_evidence_bound(self):
        rubric = self.rubrics["materials_reproducibility_and_notes"]
        first = collect_material(self.root, rubric, LIMITS)
        second = collect_material(self.root, rubric, LIMITS)
        self.assertEqual(first, second)
        self.assertEqual(first.evidence[0].evidence_id, "inventory")
        paths = [item.path for item in first.evidence[1:]]
        self.assertEqual(paths, sorted(paths))
        self.assertIn("workspace/app.py", paths)
        application = next(
            item for item in first.evidence if item.path == "workspace/app.py"
        )
        self.assertEqual(
            application.sha256,
            "sha256:" + hashlib.sha256(b"print('start')\n").hexdigest(),
        )

    def test_verification_rubric_includes_authoritative_task_commands(self):
        rubric = self.rubrics["verification_independence"]
        snapshot = collect_material(self.root, rubric, LIMITS)
        paths = {item.path for item in snapshot.evidence}
        self.assertIn("task.toml", paths)
        self.assertIn("solution/app.py", paths)
        self.assertIn("tests/test_app.py", paths)

    def test_symlink_and_capacity_do_not_become_partial_evidence(self):
        rubric = self.rubrics["materials_reproducibility_and_notes"]
        (self.root / "workspace" / "escape").symlink_to(self.root / "instruction.md")
        with self.assertRaisesRegex(MaterialError, "material_unavailable"):
            collect_material(self.root, rubric, LIMITS)
        (self.root / "workspace" / "escape").unlink()
        tiny = MaterialLimits(
            maximum_entries=3, maximum_file_bytes=10, maximum_total_bytes=20
        )
        with self.assertRaisesRegex(MaterialError, "capacity_exceeded"):
            collect_material(self.root, rubric, tiny)

    def test_binary_material_is_in_inventory_without_fabricated_text(self):
        (self.root / "workspace" / "fixture.bin").write_bytes(b"\xff\x00")
        rubric = self.rubrics["materials_reproducibility_and_notes"]
        snapshot = collect_material(self.root, rubric, LIMITS)
        fixture = next(
            item for item in snapshot.evidence if item.path == "workspace/fixture.bin"
        )
        self.assertIsNone(fixture.content_utf8)
        self.assertEqual(fixture.byte_count, 2)
        with self.assertRaisesRegex(AssessmentError, "material_unavailable"):
            build_prompt({}, rubric, snapshot)


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "instruction.md").write_text("Run tool check.\n", encoding="utf-8")
        (self.root / "task.toml").write_text("format_version = 1\n", encoding="utf-8")
        (self.root / "AUTHOR_NOTES.md").write_text("No extensions.\n", encoding="utf-8")
        (self.root / "workspace").mkdir()
        (self.root / "tests").mkdir()
        _, rubrics = load_rubrics()
        self.rubric = rubrics["solver_brief_and_extension_disclosure"]
        self.source, _ = load_rubrics()
        self.snapshot = collect_material(self.root, self.rubric, LIMITS)

    def tearDown(self):
        self.temporary.cleanup()

    def assessment(self, *, failed: bool = False) -> dict:
        instruction_evidence = next(
            item.evidence_id
            for item in self.snapshot.evidence
            if item.path == "instruction.md"
        )
        conditions = []
        findings = []
        for number in range(1, len(self.rubric.pass_conditions) + 1):
            is_failed = failed and number == 1
            conditions.append(
                {
                    "condition_number": number,
                    "status": "not_satisfied" if is_failed else "satisfied",
                    "evidence_ids": [instruction_evidence],
                    "finding_numbers": [1] if is_failed else [],
                }
            )
        if failed:
            findings.append(
                {
                    "code": "brief_incomplete",
                    "evidence_id": instruction_evidence,
                    "line": 1,
                }
            )
        return {
            "schema_version": "terminal_systems.model_assessment.v1",
            "requirement_id": self.rubric.requirement_id,
            "material_digest": self.snapshot.digest,
            "conditions": conditions,
            "findings": findings,
        }

    def validate(self, value: dict):
        return validate_assessment(json.dumps(value), self.rubric, self.snapshot)

    def test_complete_passing_assessment_cites_actual_material(self):
        self.assertEqual(self.validate(self.assessment()), ())

    def test_failed_assessment_uses_fixed_guide_message_and_safe_location(self):
        findings = self.validate(self.assessment(failed=True))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "brief_incomplete")
        self.assertEqual(findings[0].message, "Solver instructions are incomplete.")
        self.assertEqual(findings[0].evidence.path, "instruction.md")
        self.assertEqual(findings[0].line, 1)

    def test_schema_only_or_uncited_pass_is_invalid(self):
        value = self.assessment()
        value["conditions"][0]["evidence_ids"] = []
        with self.assertRaisesRegex(AssessmentError, "invalid_output"):
            self.validate(value)

    def test_unknown_or_unreferenced_finding_is_invalid(self):
        value = self.assessment(failed=True)
        value["findings"][0]["code"] = "invented"
        with self.assertRaisesRegex(AssessmentError, "invalid_output"):
            self.validate(value)
        value = self.assessment(failed=True)
        value["conditions"][0]["finding_numbers"] = []
        with self.assertRaisesRegex(AssessmentError, "invalid_output"):
            self.validate(value)

    def test_condition_cannot_borrow_finding_code_or_unlisted_evidence(self):
        value = self.assessment(failed=True)
        value["findings"][0]["code"] = "extension_explanation_missing"
        with self.assertRaisesRegex(AssessmentError, "invalid_output"):
            self.validate(value)

        author_notes = next(
            item.evidence_id
            for item in self.snapshot.evidence
            if item.path == "AUTHOR_NOTES.md"
        )
        value = self.assessment(failed=True)
        value["findings"][0]["evidence_id"] = author_notes
        value["findings"][0]["line"] = 1
        with self.assertRaisesRegex(AssessmentError, "invalid_output"):
            self.validate(value)

    def test_wrong_material_or_line_is_invalid(self):
        value = self.assessment(failed=True)
        value["material_digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(AssessmentError, "invalid_output"):
            self.validate(value)
        value = self.assessment(failed=True)
        value["findings"][0]["line"] = 999
        with self.assertRaisesRegex(AssessmentError, "invalid_output"):
            self.validate(value)

    def test_prompt_marks_submission_as_untrusted_and_contains_exact_contract(self):
        prompt = json.loads(build_prompt(self.source, self.rubric, self.snapshot))
        self.assertIn("untrusted", " ".join(prompt["security"]).lower())
        self.assertEqual(
            prompt["untrusted_evidence_data"]["material_digest"], self.snapshot.digest
        )
        self.assertEqual(
            [item["text"] for item in prompt["rubric"]["pass_conditions"]],
            list(self.rubric.pass_conditions),
        )
        self.assertEqual(
            prompt["rubric"]["pass_conditions"][0]["allowed_finding_codes"],
            ["brief_incomplete"],
        )
        self.assertEqual(
            prompt["output_contract"]["schema_version"],
            "terminal_systems.model_assessment.v1",
        )

    def test_extra_output_fields_are_rejected(self):
        value = self.assessment()
        value["confidence"] = 1
        with self.assertRaisesRegex(AssessmentError, "invalid_output"):
            self.validate(value)

    def test_duplicate_keys_non_json_constants_and_wrong_types_are_rejected(self):
        valid = json.dumps(self.assessment())
        duplicate_findings = valid.replace(
            '"findings": []', '"findings": [{"code": NaN}], "findings": []'
        )
        for raw in (
            duplicate_findings,
            valid.replace('"findings": []', '"findings": NaN'),
        ):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(AssessmentError, "invalid_output"):
                    validate_assessment(raw, self.rubric, self.snapshot)
        value = self.assessment()
        value["conditions"][0]["status"] = []
        with self.assertRaisesRegex(AssessmentError, "invalid_output"):
            self.validate(value)

    def request(self) -> dict:
        return {
            "request_digest": "sha256:" + "1" * 64,
            "identity": {"phase": "post_submit"},
            "registry": {
                "registry_entry_id": "018f6f49-66b8-7d2a-bf4d-0e2eeaa00001",
                "entry_digest": "sha256:" + "2" * 64,
            },
        }

    def test_normalized_result_uses_only_validated_fixed_findings(self):
        findings = self.validate(self.assessment(failed=True))
        result = completed_result(self.request(), self.rubric.requirement_id, findings)
        self.assertEqual(result["outcome"], "completed")
        self.assertEqual(result["verdict"], "failed")
        self.assertEqual(
            result["findings"],
            [
                {
                    "check_id": self.rubric.requirement_id,
                    "code": "brief_incomplete",
                    "level": "error",
                    "message": "Solver instructions are incomplete.",
                    "path": "instruction.md",
                    "line": 1,
                }
            ],
        )
        body = deepcopy(result)
        digest = body.pop("result_digest")
        encoded = json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        self.assertEqual(digest, "sha256:" + hashlib.sha256(encoded).hexdigest())

    def test_infrastructure_result_has_no_work_verdict_or_findings(self):
        result = infrastructure_result(self.request(), "material_unavailable")
        self.assertEqual(result["outcome"], "infrastructure_failed")
        self.assertIsNone(result["verdict"])
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["infrastructure_failure_code"], "material_unavailable")


if __name__ == "__main__":
    unittest.main()
