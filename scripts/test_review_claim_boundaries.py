"""Regression tests for review receipt claim and finding boundaries."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import jsonschema

from scripts.reviewer_contracts import receipt_failures


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / ".ci/reviewer-evidence/INTERNAL_REVIEW_RECEIPT.schema.json"
PASSING_VERDICTS = ("PASS", "PASS AFTER FIXES", "PASS WITH LOW RISKS")
SHA = "a" * 40


def valid_receipt() -> dict[str, object]:
    return {
        "schema_version": 3,
        "custody": "advisory_session",
        "target": {"base_sha": SHA, "merge_base_sha": SHA, "head_sha": SHA},
        "reviewer": {"specialty": "architecture", "run_id": "claim-boundary-test"},
        "inspections": {
            "start": {"cleanliness": "clean"},
            "end": {"cleanliness": "clean"},
        },
        "evidence": [
            {"kind": "executed", "source": "focused test", "result": "pass"},
            {"kind": "inspected", "source": "source review", "result": "pass"},
        ],
        "impact_cone": [{"source": "owner", "relevance": "owns behavior"}],
        "adversarial_probes": [
            {
                "hypothesis": "proof misses the defect",
                "method": "introduce the named counterexample",
                "defect": "contract contradiction",
                "expected_observation": "inspection identifies the contradiction",
                "actual_observation": "inspection identified the contradiction",
                "proof_survived": False,
                "result": "pass",
            }
        ],
        "traceability": [
            {
                "criterion": "owner guard",
                "behavior": "invalid input is denied",
                "owner": "architecture",
                "implementation_source": "owner.py",
                "proof_source": "focused test",
                "execution_custody": "local unit",
                "claimed_boundary": "service",
                "proof_strength": "service",
                "proof_custody": {
                    "kind": "executed",
                    "observations": ["service_orchestration"],
                },
                "proof_compatibility": "compatible",
                "result": "verified",
            }
        ],
        "residual_escape": {
            "hypothesis": "another path bypasses the guard",
            "method": "inspect all entry points",
            "result": "falsified",
        },
        "findings": [],
        "uncertainty": [],
        "freshness": "current",
        "verdict": "PASS",
    }


def finding(
    severity: str, disposition: str, *, blocks_pr: bool = False
) -> dict[str, object]:
    return {
        "id": f"{severity.upper()}-{disposition}",
        "severity": severity,
        "location": "owner.py:1",
        "source_target": SHA,
        "blocks_pr": blocks_pr,
        "disposition": disposition,
        "verification": "reviewed against the frozen target",
        "failure_pattern_ids": [],
    }


class ReviewClaimBoundaryTests(unittest.TestCase):
    def test_fixed_or_not_valid_findings_require_nonblank_verification(self) -> None:
        for severity in ("Critical", "High", "Medium"):
            for disposition in ("fixed", "not_valid"):
                for verification in ("", " ", "\n\t"):
                    with self.subTest(
                        severity=severity,
                        disposition=disposition,
                        verification=repr(verification),
                    ):
                        receipt = valid_receipt()
                        row = finding(severity, disposition)
                        row["verification"] = verification
                        receipt["findings"] = [row]
                        with self.assertRaises(jsonschema.ValidationError):
                            self.validator.validate(receipt)
                        self.assertTrue(receipt_failures(receipt, "architecture", SHA))

    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(cls.schema)
        cls.validator = jsonschema.Draft202012Validator(cls.schema)

    def assert_schema_valid(self, receipt: dict[str, object]) -> None:
        self.validator.validate(receipt)

    def assert_schema_invalid(self, receipt: dict[str, object]) -> None:
        with self.assertRaises(jsonschema.ValidationError):
            self.validator.validate(receipt)

    def inspected_receipt(
        self, boundary: str, observation: str
    ) -> dict[str, object]:
        receipt = valid_receipt()
        receipt["traceability"][0].update(
            claimed_boundary=boundary,
            proof_strength="contract_inspection",
            proof_custody={"kind": "inspected", "observations": [observation]},
            execution_custody="advisory source inspection",
            proof_source="frozen contract sources",
        )
        return receipt

    def test_plan_contract_inspection_is_compatible(self) -> None:
        receipt = self.inspected_receipt("plan_contract", "contract_counterexample")
        self.assert_schema_valid(receipt)
        self.assertEqual(receipt_failures(receipt, "architecture", SHA), [])

    def test_document_consistency_inspection_is_compatible(self) -> None:
        receipt = self.inspected_receipt(
            "document_consistency", "source_comparison"
        )
        self.assert_schema_valid(receipt)
        self.assertEqual(receipt_failures(receipt, "architecture", SHA), [])

    def test_inspection_claim_requires_its_concrete_observation(self) -> None:
        mismatches = (
            ("plan_contract", "source_comparison"),
            ("document_consistency", "contract_counterexample"),
        )
        for boundary, wrong_observation in mismatches:
            with self.subTest(boundary=boundary):
                receipt = self.inspected_receipt(boundary, wrong_observation)
                self.assert_schema_valid(receipt)
                self.assertIn(
                    "output: traceability row 0 proof compatibility mismatch",
                    receipt_failures(receipt, "architecture", SHA),
                )

    def test_inspection_proof_cannot_launder_a_runtime_claim(self) -> None:
        runtime_boundaries = (
            "pure",
            "service",
            "repository",
            "repository_isolation",
            "transaction",
            "concurrency",
            "direct_sql",
            "composition",
        )
        for boundary in runtime_boundaries:
            with self.subTest(boundary=boundary):
                receipt = self.inspected_receipt(boundary, "contract_counterexample")
                self.assert_schema_valid(receipt)
                self.assertIn(
                    "output: traceability row 0 proof compatibility mismatch",
                    receipt_failures(receipt, "architecture", SHA),
                )

    def test_existing_runtime_custody_remains_executed_and_compatible(self) -> None:
        runtime_contracts = {
            "pure": ("pure", ["pure_result"]),
            "service": ("service", ["service_orchestration"]),
            "repository": ("repository", ["stored_row"]),
            "repository_isolation": (
                "repository",
                ["stored_row", "stored_foreign_resource"],
            ),
            "transaction": ("transaction", ["staged_state", "final_state"]),
            "concurrency": ("concurrency", ["independent_sessions"]),
            "direct_sql": ("direct_sql", ["orm_bypassed"]),
            "composition": ("composition", ["composition_root"]),
        }
        for boundary, (strength, observations) in runtime_contracts.items():
            with self.subTest(boundary=boundary):
                receipt = valid_receipt()
                receipt["traceability"][0].update(
                    claimed_boundary=boundary,
                    proof_strength=strength,
                    proof_custody={
                        "kind": "executed",
                        "observations": observations,
                    },
                )
                self.assert_schema_valid(receipt)
                self.assertEqual(receipt_failures(receipt, "architecture", SHA), [])

    def test_unresolved_material_finding_blocks_every_passing_verdict(self) -> None:
        for verdict in PASSING_VERDICTS:
            for severity in ("Critical", "High", "Medium"):
                with self.subTest(verdict=verdict, severity=severity):
                    receipt = valid_receipt()
                    receipt["verdict"] = verdict
                    receipt["findings"] = [finding(severity, "unresolved")]
                    self.assert_schema_invalid(receipt)

    def test_critical_or_high_risk_cannot_be_accepted_or_deferred_for_pass(self) -> None:
        for verdict in PASSING_VERDICTS:
            for severity in ("Critical", "High"):
                for disposition in ("accepted_risk", "deferred_with_owner"):
                    with self.subTest(
                        verdict=verdict,
                        severity=severity,
                        disposition=disposition,
                    ):
                        receipt = valid_receipt()
                        receipt["verdict"] = verdict
                        receipt["findings"] = [finding(severity, disposition)]
                        self.assert_schema_invalid(receipt)

    def test_critical_or_high_finding_must_be_fixed_or_not_valid_for_pass(self) -> None:
        for severity in ("Critical", "High"):
            for disposition in ("fixed", "not_valid"):
                with self.subTest(severity=severity, disposition=disposition):
                    receipt = valid_receipt()
                    receipt["findings"] = [finding(severity, disposition)]
                    self.assert_schema_valid(receipt)

    def test_medium_accepted_or_deferred_and_low_unresolved_remain_passable(self) -> None:
        allowed = (
            finding("Medium", "accepted_risk"),
            finding("Medium", "deferred_with_owner"),
            finding("Low", "unresolved"),
        )
        for allowed_finding in allowed:
            with self.subTest(finding_id=allowed_finding["id"]):
                receipt = valid_receipt()
                receipt["findings"] = [copy.deepcopy(allowed_finding)]
                self.assert_schema_valid(receipt)


if __name__ == "__main__":
    unittest.main()
