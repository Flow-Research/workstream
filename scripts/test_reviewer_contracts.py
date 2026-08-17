"""Regression tests for reviewer protocol adoption contracts."""

from __future__ import annotations

import copy
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.reviewer_contracts import CASE_CLASSES, REVIEWERS, SEMANTIC_SKILL_REQUIREMENTS
from scripts.reviewer_contracts import contract_failures, fixture_failures, load_json, main
from scripts.reviewer_contracts import output_failures, output_set_failures
from scripts.reviewer_contracts import CASES_PATH, EXPECTATIONS_PATH


class ReviewerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_json(CASES_PATH)

    def test_all_agent_skill_contracts_compose_with_protocol(self) -> None:
        self.assertEqual(contract_failures(), [])

    def copied_contract_root(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        for _, (agent_name, skill_name) in REVIEWERS.items():
            agent = Path(".codex/agents") / agent_name
            skill = Path(".agents/skills") / skill_name / "SKILL.md"
            (root / agent).parent.mkdir(parents=True, exist_ok=True)
            (root / skill).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(agent, root / agent)
            shutil.copy2(skill, root / skill)
        matrix = Path(
            ".agent-loop/initiatives/WS-CI-004-review-evidence-integrity/REVIEWER_MATRIX.md"
        )
        cases = Path(
            ".agent-loop/initiatives/WS-CI-004-review-evidence-integrity/evaluations/CASES.json"
        )
        (root / matrix).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(matrix, root / matrix)
        (root / cases).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cases, root / cases)
        return temporary, root

    def test_missing_protocol_output_or_handoff_contract_fails(self) -> None:
        for token in ("reviewer-evidence-protocol", "Protocol envelope", "hand off"):
            with self.subTest(token=token):
                temporary, root = self.copied_contract_root()
                try:
                    skill = root / ".agents/skills/architecture-review/SKILL.md"
                    skill.write_text(
                        skill.read_text(encoding="utf-8").replace(token, "removed", 1),
                        encoding="utf-8",
                    )
                    self.assertTrue(contract_failures(root))
                finally:
                    temporary.cleanup()

    def test_each_semantic_skill_requirement_is_independently_enforced(self) -> None:
        for requirement_id, token in SEMANTIC_SKILL_REQUIREMENTS.items():
            with self.subTest(requirement_id=requirement_id):
                temporary, root = self.copied_contract_root()
                try:
                    skill = root / ".agents/skills/architecture-review/SKILL.md"
                    skill.write_text(
                        skill.read_text(encoding="utf-8").replace(token, "removed"),
                        encoding="utf-8",
                    )
                    self.assertTrue(
                        any(requirement_id in failure for failure in contract_failures(root))
                    )
                finally:
                    temporary.cleanup()

    def test_agent_handoff_contract_and_matrix_ids_are_enforced(self) -> None:
        temporary, root = self.copied_contract_root()
        try:
            agent = root / ".codex/agents/architecture-reviewer.toml"
            agent.write_text(
                agent.read_text(encoding="utf-8").replace("hand off", "route away", 1),
                encoding="utf-8",
            )
            self.assertTrue(any("agent missing 'hand off'" in item for item in contract_failures(root)))
        finally:
            temporary.cleanup()
        temporary, root = self.copied_contract_root()
        try:
            matrix = root / ".agent-loop/initiatives/WS-CI-004-review-evidence-integrity/REVIEWER_MATRIX.md"
            matrix.write_text(
                matrix.read_text(encoding="utf-8").replace("`architecture`", "`architecture_typo`", 1),
                encoding="utf-8",
            )
            self.assertTrue(any("canonical reviewer IDs" in item for item in contract_failures(root)))
        finally:
            temporary.cleanup()

    def test_matrix_agent_and_skill_pairs_are_one_to_one(self) -> None:
        temporary, root = self.copied_contract_root()
        try:
            matrix = root / ".agent-loop/initiatives/WS-CI-004-review-evidence-integrity/REVIEWER_MATRIX.md"
            matrix.write_text(
                matrix.read_text(encoding="utf-8")
                .replace("security-reviewer.toml", "qa-reviewer.toml", 1)
                .replace("security-review/SKILL.md", "qa-review/SKILL.md", 1),
                encoding="utf-8",
            )
            failures = contract_failures(root)
            self.assertIn("matrix: custom agent paths must be one-to-one", failures)
            self.assertIn("matrix: repository skill paths must be one-to-one", failures)
            self.assertIn("matrix: agent and skill pairs must be one-to-one", failures)
        finally:
            temporary.cleanup()

    def test_every_reviewer_has_every_blind_case_class(self) -> None:
        self.assertEqual(fixture_failures(self.cases, None), [])
        rows = self.cases["cases"]
        self.assertGreaterEqual(len(rows), len(REVIEWERS) * len(CASE_CLASSES))

    def test_missing_reviewer_or_case_class_fails(self) -> None:
        cases = copy.deepcopy(self.cases)
        cases["cases"] = [row for row in cases["cases"] if row["reviewer"] != "security"]
        self.assertTrue(any("security: missing cases" in item for item in fixture_failures(cases, None)))
        cases = copy.deepcopy(self.cases)
        cases["cases"] = [row for row in cases["cases"] if row["id"] != "qa-handoff"]
        self.assertTrue(any("qa: missing cases" in item for item in fixture_failures(cases, None)))

    def test_raw_case_cannot_contain_expected_answer(self) -> None:
        cases = copy.deepcopy(self.cases)
        cases["cases"][0]["outcome"] = "finding"
        self.assertTrue(any("leaked" in item for item in fixture_failures(cases, None)))

    def test_expectations_must_cover_every_case_and_closed_outcome(self) -> None:
        expectations = {
            "expectations": [
                {
                    "case_id": row["id"],
                    "outcome": "clear",
                    "required_finding_ids": [],
                    "handoff_specialty": None,
                }
                for row in self.cases["cases"]
            ]
        }
        self.assertEqual(fixture_failures(self.cases, expectations), [])
        expectations["expectations"].pop()
        self.assertIn(
            "expectations: case IDs do not match raw fixtures",
            fixture_failures(self.cases, expectations),
        )
        expectations["expectations"][0]["outcome"] = "maybe"
        self.assertTrue(any("invalid outcome" in item for item in fixture_failures(self.cases, expectations)))

    def test_duplicate_expectations_and_unknown_handoffs_fail(self) -> None:
        expectations = copy.deepcopy(load_json(EXPECTATIONS_PATH))
        expectations["expectations"].append(copy.deepcopy(expectations["expectations"][0]))
        self.assertIn("expectations: duplicate case IDs", fixture_failures(self.cases, expectations))
        expectations = copy.deepcopy(load_json(EXPECTATIONS_PATH))
        expectations["expectations"][0]["handoff_specialty"] = "security_typo"
        self.assertTrue(
            any("unknown handoff specialty" in item for item in fixture_failures(self.cases, expectations))
        )

    def test_duplicate_output_rows_fail(self) -> None:
        expectations = load_json(EXPECTATIONS_PATH)["expectations"]
        cases = self.cases["cases"]
        duplicate = [{"case_id": row["case_id"]} for row in expectations]
        duplicate[-1] = copy.deepcopy(duplicate[0])
        failures = output_set_failures(duplicate, {}, expectations, cases)
        self.assertIn("output set: duplicate or incorrect row count", failures)

    def test_unhashable_output_identity_values_fail_cleanly(self) -> None:
        expectations = load_json(EXPECTATIONS_PATH)["expectations"]
        cases = self.cases["cases"]
        for invalid_case_id in ([], {}):
            with self.subTest(case_id=invalid_case_id):
                outputs = [{"case_id": row["case_id"]} for row in expectations]
                outputs[0]["case_id"] = invalid_case_id
                self.assertIn(
                    "output set: invalid row",
                    output_set_failures(outputs, {}, expectations, cases),
                )
        outputs = [{"case_id": row["case_id"]} for row in expectations]
        outputs[0]["reviewer"] = []
        self.assertIn(
            "output set: invalid reviewer",
            output_set_failures(outputs, {}, expectations, cases),
        )

    def test_direct_output_rejects_non_object_and_malformed_json_cleanly(self) -> None:
        expectation = load_json(EXPECTATIONS_PATH)["expectations"][0]
        self.assertEqual(output_failures([], expectation), ["output: expected an object"])
        for payload in ("[]", '"invalid"', "{"):
            with self.subTest(payload=payload):
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as output_file:
                    output_file.write(payload)
                    output_file.flush()
                    self.assertEqual(
                        main(["validate-output", "--case", expectation["case_id"], "--output", output_file.name]),
                        1,
                    )

    def test_output_requires_envelope_replay_and_exact_handoff(self) -> None:
        expectation = {
            "case_id": "architecture-handoff",
            "outcome": "handoff",
            "required_finding_ids": ["ARCH-7"],
            "handoff_specialty": "ci_integrity",
        }
        output = {
            "case_id": "architecture-handoff",
            "reviewer": "architecture",
            "evaluated_head": "a" * 40,
            "classification": "handoff",
            "finding_ids": ["ARCH-7"],
            "short_reason": "routed",
            "handoff_specialty": "ci_integrity",
        }
        receipt = {
            "schema_version": 2,
            "custody": "advisory_session",
            "target": {"base_sha": "a" * 40, "merge_base_sha": "a" * 40, "head_sha": "a" * 40},
            "reviewer": {"specialty": "architecture", "run_id": "eval-1"},
            "inspections": {"start": {"cleanliness": "dirty"}, "end": {"cleanliness": "dirty"}},
            "evidence": [
                {"kind": "executed", "source": "review target", "result": "pass"},
                {"kind": "inspected", "source": "raw case", "result": "pass"},
            ],
            "impact_cone": [
                {"source": "case owner", "relevance": "owns evaluated behavior"}
            ],
            "adversarial_probes": [
                {"hypothesis": "case bypass", "method": "inspect raw case", "result": "pass"}
            ],
            "traceability": [
                {"criterion": "routing", "behavior": "route finding", "owner": "architecture", "implementation_source": "raw case", "proof_source": "inspection", "execution_custody": "review session", "result": "verified"}
            ],
            "residual_escape": {"hypothesis": "a second route is hidden", "method": "inspect supplied evidence", "result": "falsified"},
            "findings": [
                {"id": "ARCH-7", "severity": "Medium", "location": "case", "blocks_pr": False, "disposition": "fixed", "verification": "replayed"}
            ],
            "uncertainty": [],
            "freshness": "current",
            "verdict": "PROVISIONAL",
        }
        self.assertEqual(output_failures(output, expectation, receipt), [])
        for key in ("evaluated_head", "classification"):
            broken = copy.deepcopy(output)
            broken.pop(key)
            self.assertTrue(output_failures(broken, expectation, receipt))
        broken = copy.deepcopy(output)
        broken["finding_ids"] = []
        self.assertIn(
            "output: required finding not replayed", output_failures(broken, expectation, receipt)
        )
        broken = copy.deepcopy(output)
        broken["finding_ids"] = [{}]
        self.assertIn(
            "output: finding_ids must contain only strings",
            output_failures(broken, expectation, receipt),
        )
        broken = copy.deepcopy(output)
        broken["handoff_specialty"] = "security"
        self.assertIn("output: wrong handoff", output_failures(broken, expectation, receipt))

        # A case classification is not a final review verdict. The canonical
        # receipt remains PROVISIONAL while its start/end inspections are dirty.
        self.assertEqual(receipt["verdict"], "PROVISIONAL")

        for path in (
            ("target", "base_sha"),
            ("reviewer", "run_id"),
            ("inspections", "end"),
            ("traceability",),
            ("residual_escape",),
            ("uncertainty",),
            ("freshness",),
            ("verdict",),
        ):
            with self.subTest(path=path):
                broken_receipt = copy.deepcopy(receipt)
                parent = broken_receipt
                for key in path[:-1]:
                    parent = parent[key]
                parent.pop(path[-1])
                self.assertTrue(output_failures(output, expectation, broken_receipt))
        broken_receipt = copy.deepcopy(receipt)
        broken_receipt["evidence"] = [broken_receipt["evidence"][0]]
        self.assertIn(
            "output: receipt must separate executed and inspected evidence",
            output_failures(output, expectation, broken_receipt),
        )
        passing_receipt = copy.deepcopy(receipt)
        passing_receipt["inspections"] = {"start": {"cleanliness": "clean"}, "end": {"cleanliness": "clean"}}
        passing_receipt["verdict"] = "PASS"
        for result in ("missing", "unavailable"):
            passing_receipt["traceability"][0]["result"] = result
            self.assertTrue(output_failures(output, expectation, passing_receipt))
        passing_receipt["traceability"][0]["result"] = "verified"
        second_row = copy.deepcopy(passing_receipt["traceability"][0])
        second_row["behavior"] = "second independent behavior"
        second_row["result"] = "missing"
        passing_receipt["traceability"].append(second_row)
        self.assertTrue(output_failures(output, expectation, passing_receipt))
        passing_receipt["traceability"].pop()
        for result in ("survives", "unavailable"):
            passing_receipt["residual_escape"]["result"] = result
            self.assertTrue(output_failures(output, expectation, passing_receipt))

    def test_positive_finding_requires_stable_receipt_finding(self) -> None:
        expectation = {
            "case_id": "architecture-positive",
            "outcome": "finding",
            "required_finding_ids": [],
            "handoff_specialty": None,
        }
        output = {
            "case_id": "architecture-positive",
            "reviewer": "architecture",
            "evaluated_head": "a" * 40,
            "classification": "finding",
            "finding_ids": [],
            "short_reason": "defect detected",
            "handoff_specialty": None,
        }
        receipt = {
            "schema_version": 2,
            "custody": "advisory_session",
            "target": {"base_sha": "a" * 40, "merge_base_sha": "a" * 40, "head_sha": "a" * 40},
            "reviewer": {"specialty": "architecture", "run_id": "eval-positive"},
            "inspections": {"start": {"cleanliness": "dirty"}, "end": {"cleanliness": "dirty"}},
            "evidence": [
                {"kind": "executed", "source": "review target", "result": "pass"},
                {"kind": "inspected", "source": "raw case", "result": "pass"},
            ],
            "impact_cone": [
                {"source": "case owner", "relevance": "owns evaluated behavior"}
            ],
            "adversarial_probes": [
                {"hypothesis": "case bypass", "method": "inspect raw case", "result": "pass"}
            ],
            "traceability": [
                {"criterion": "finding", "behavior": "detect defect", "owner": "architecture", "implementation_source": "raw case", "proof_source": "inspection", "execution_custody": "review session", "result": "verified"}
            ],
            "residual_escape": {"hypothesis": "defect is concealed", "method": "inspect supplied evidence", "result": "falsified"},
            "findings": [],
            "uncertainty": [],
            "freshness": "current",
            "verdict": "PROVISIONAL",
        }
        self.assertIn(
            "output: finding classification requires a stable finding",
            output_failures(output, expectation, receipt),
        )


if __name__ == "__main__":
    unittest.main()
