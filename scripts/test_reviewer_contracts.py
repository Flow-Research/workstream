"""Regression tests for reviewer protocol adoption contracts."""

from __future__ import annotations

import copy
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.reviewer_contracts import CASE_CLASSES, REVIEWERS
from scripts.reviewer_contracts import contract_failures, fixture_failures, load_json
from scripts.reviewer_contracts import output_failures
from scripts.reviewer_contracts import CASES_PATH


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
        (root / matrix).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(matrix, root / matrix)
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

    def test_every_reviewer_has_every_blind_case_class(self) -> None:
        self.assertEqual(fixture_failures(self.cases, None), [])
        rows = self.cases["cases"]
        self.assertEqual(len(rows), len(REVIEWERS) * len(CASE_CLASSES))

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
            "result": "handoff",
            "finding_ids": ["ARCH-7"],
            "short_reason": "routed",
            "handoff_specialty": "ci_integrity",
            "uncertainty": [],
        }
        self.assertEqual(output_failures(output, expectation), [])
        for key in ("evaluated_head", "uncertainty"):
            broken = copy.deepcopy(output)
            broken.pop(key)
            self.assertTrue(output_failures(broken, expectation))
        broken = copy.deepcopy(output)
        broken["finding_ids"] = []
        self.assertIn("output: required finding not replayed", output_failures(broken, expectation))
        broken = copy.deepcopy(output)
        broken["handoff_specialty"] = "security"
        self.assertIn("output: wrong handoff", output_failures(broken, expectation))


if __name__ == "__main__":
    unittest.main()
