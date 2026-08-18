"""Regression tests for reviewer protocol adoption contracts."""

from __future__ import annotations

import copy
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.reviewer_contracts import (
    CASE_CLASSES,
    FAILURE_PATTERN_IDS,
    MATRIX_SPECIALTY_REQUIREMENTS,
    PROOF_PATTERNS_PATH,
    PROOF_QUALITY_AGENT_LIFECYCLE,
    PROOF_QUALITY_MATRIX_LIFECYCLE,
    PROOF_QUALITY_SHARED_REQUIREMENTS,
    PROOF_QUALITY_SKILL_LIFECYCLE,
    PROOF_QUALITY_STATE_REQUIREMENTS,
    PROOF_STRENGTHS,
    ROOT as CONTRACT_ROOT,
    REVIEWERS,
    SEMANTIC_AGENT_REQUIREMENTS,
    SEMANTIC_SKILL_REQUIREMENTS,
    SPECIALTY_PROOF_COMPLETION_REQUIREMENTS,
    SPECIALTY_PROOF_REQUIREMENTS,
)
from scripts.reviewer_contracts import (
    contract_failures,
    fixture_failures,
    load_json,
    main,
)
from scripts.reviewer_contracts import (
    output_failures,
    output_set_failures,
    receipt_failures,
)
from scripts.reviewer_contracts import CASES_PATH, EXPECTATIONS_PATH


def valid_receipt() -> dict[str, object]:
    sha = "a" * 40
    return {
        "schema_version": 3,
        "custody": "advisory_session",
        "target": {"base_sha": sha, "merge_base_sha": sha, "head_sha": sha},
        "reviewer": {"specialty": "architecture", "run_id": "proof-test"},
        "inspections": {
            "start": {"cleanliness": "clean"},
            "end": {"cleanliness": "clean"},
        },
        "evidence": [
            {"kind": "executed", "source": "focused test", "result": "pass"},
            {"kind": "inspected", "source": "owner source", "result": "pass"},
        ],
        "impact_cone": [{"source": "owner", "relevance": "owns behavior"}],
        "adversarial_probes": [
            {
                "hypothesis": "proof misses the defect",
                "method": "remove the owner guard",
                "defect": "owner guard removed",
                "expected_observation": "focused test fails",
                "actual_observation": "focused test failed",
                "proof_survived": False,
                "result": "pass",
            }
        ],
        "traceability": [
            {
                "criterion": "owner guard",
                "behavior": "invalid owner is denied",
                "owner": "architecture",
                "implementation_source": "owner",
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
            "hypothesis": "another owner path bypasses",
            "method": "inspect all owner entry points",
            "result": "falsified",
        },
        "findings": [],
        "uncertainty": [],
        "freshness": "current",
        "verdict": "PASS",
    }


def remove_contract_token(path: Path, token: str) -> str:
    original = path.read_text(encoding="utf-8")
    pattern = r"\s+".join(re.escape(part) for part in token.split())
    mutated, count = re.subn(pattern, " removed ", original)
    if count < 1:
        raise AssertionError(f"expected {token!r} in {path}")
    path.write_text(mutated, encoding="utf-8")
    return original


class ReviewerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_json(CASES_PATH)

    def test_all_agent_skill_contracts_compose_with_protocol(self) -> None:
        self.assertEqual(contract_failures(), [])

    def assert_receipt_invalid(self, receipt: dict[str, object], message: str) -> None:
        self.assertTrue(
            any(
                message in failure
                for failure in receipt_failures(receipt, "architecture", "a" * 40)
            )
        )

    def test_receipt_rejects_unknown_proof_strength(self) -> None:
        self.assertEqual(
            PROOF_STRENGTHS,
            {
                "pure",
                "service",
                "repository",
                "transaction",
                "concurrency",
                "direct_sql",
                "composition",
                "negative_structure",
            },
        )
        receipt = valid_receipt()
        receipt["traceability"][0]["proof_strength"] = "integration"
        self.assert_receipt_invalid(receipt, "invalid protocol receipt")

    def test_receipt_requires_boundary_and_strength_per_trace_row(self) -> None:
        for field in (
            "claimed_boundary",
            "proof_strength",
            "proof_custody",
            "proof_compatibility",
        ):
            with self.subTest(field=field):
                receipt = valid_receipt()
                receipt["traceability"][0].pop(field)
                self.assert_receipt_invalid(receipt, "invalid protocol receipt")

    def test_reviewer_cannot_self_attest_compatibility(self) -> None:
        receipt = valid_receipt()
        row = receipt["traceability"][0]
        row.update(
            claimed_boundary="repository",
            proof_strength="service",
            proof_custody={
                "kind": "executed",
                "observations": ["service_orchestration"],
            },
            proof_compatibility="compatible",
        )
        self.assert_receipt_invalid(receipt, "proof compatibility mismatch")

    def test_weaker_proof_cannot_satisfy_infrastructure_claims(self) -> None:
        for boundary in (
            "repository",
            "transaction",
            "concurrency",
            "direct_sql",
            "composition",
        ):
            with self.subTest(boundary=boundary):
                receipt = valid_receipt()
                row = receipt["traceability"][0]
                row.update(
                    claimed_boundary=boundary,
                    proof_strength="service",
                    proof_custody={
                        "kind": "executed",
                        "observations": ["service_orchestration"],
                    },
                    proof_compatibility="compatible",
                )
                self.assert_receipt_invalid(receipt, "proof compatibility mismatch")

    def test_isolation_proof_rejects_missing_row_mock(self) -> None:
        receipt = valid_receipt()
        row = receipt["traceability"][0]
        row.update(
            claimed_boundary="repository_isolation",
            proof_strength="repository",
            proof_custody={"kind": "executed", "observations": ["stored_row"]},
            proof_compatibility="compatible",
            proof_source="mock returns None instead of a stored foreign row",
        )
        self.assert_receipt_invalid(receipt, "proof compatibility mismatch")

    def test_matching_infrastructure_labels_require_observed_custody(self) -> None:
        weak_custody = {
            "repository": {"kind": "inspected", "observations": []},
            "transaction": {"kind": "executed", "observations": ["staged_state"]},
            "concurrency": {"kind": "executed", "observations": []},
            "direct_sql": {"kind": "inspected", "observations": ["syntax_or_registry"]},
        }
        for boundary, custody in weak_custody.items():
            with self.subTest(boundary=boundary):
                receipt = valid_receipt()
                receipt["traceability"][0].update(
                    claimed_boundary=boundary,
                    proof_strength=boundary,
                    proof_custody=custody,
                    proof_compatibility="compatible",
                )
                self.assert_receipt_invalid(receipt, "proof compatibility mismatch")

    def test_infrastructure_custody_observations_are_compatible(self) -> None:
        valid_custody = {
            "repository": {"kind": "executed", "observations": ["stored_row"]},
            "repository_isolation": {
                "kind": "executed",
                "observations": ["stored_row", "stored_foreign_resource"],
            },
            "transaction": {
                "kind": "executed",
                "observations": ["staged_state", "final_state"],
            },
            "concurrency": {
                "kind": "executed",
                "observations": ["independent_sessions"],
            },
            "direct_sql": {"kind": "executed", "observations": ["orm_bypassed"]},
            "composition": {
                "kind": "executed",
                "observations": ["composition_root"],
            },
        }
        for boundary, custody in valid_custody.items():
            with self.subTest(boundary=boundary):
                receipt = valid_receipt()
                receipt["traceability"][0].update(
                    claimed_boundary=boundary,
                    proof_strength=(
                        "repository" if boundary == "repository_isolation" else boundary
                    ),
                    proof_custody=custody,
                    proof_compatibility="compatible",
                )
                self.assertEqual(
                    receipt_failures(receipt, "architecture", "a" * 40), []
                )

    def test_unavailable_proof_blocks_pass(self) -> None:
        receipt = valid_receipt()
        receipt["traceability"][0]["proof_compatibility"] = "unavailable"
        receipt["traceability"][0]["proof_custody"] = {
            "kind": "unavailable",
            "observations": [],
        }
        self.assert_receipt_invalid(receipt, "'compatible' was expected")

    def test_provisional_receipt_can_record_unavailable_proof(self) -> None:
        receipt = valid_receipt()
        receipt["verdict"] = "PROVISIONAL"
        receipt["traceability"][0].update(
            proof_compatibility="unavailable",
            proof_custody={"kind": "unavailable", "observations": []},
            result="unavailable",
        )
        receipt["residual_escape"]["result"] = "unavailable"
        self.assertEqual(receipt_failures(receipt, "architecture", "a" * 40), [])

    def test_compatible_pure_and_service_proof_types_pass(self) -> None:
        for proof_type in ("pure", "service"):
            with self.subTest(proof_type=proof_type):
                receipt = valid_receipt()
                receipt["traceability"][0].update(
                    claimed_boundary=proof_type,
                    proof_strength=proof_type,
                    proof_custody={
                        "kind": "executed",
                        "observations": [
                            "pure_result"
                            if proof_type == "pure"
                            else "service_orchestration"
                        ],
                    },
                    proof_compatibility="compatible",
                )
                self.assertEqual(
                    receipt_failures(receipt, "architecture", "a" * 40), []
                )

    def test_proof_types_are_not_a_strength_hierarchy(self) -> None:
        for boundary, strength in (("pure", "direct_sql"), ("service", "repository")):
            with self.subTest(boundary=boundary, strength=strength):
                receipt = valid_receipt()
                row = receipt["traceability"][0]
                row.update(
                    claimed_boundary=boundary,
                    proof_strength=strength,
                    proof_custody={
                        "kind": "executed",
                        "observations": [
                            "orm_bypassed" if strength == "direct_sql" else "stored_row"
                        ],
                    },
                    proof_compatibility="compatible",
                )
                self.assert_receipt_invalid(receipt, "proof compatibility mismatch")

    def test_pass_requires_test_of_the_test_probe(self) -> None:
        for field in (
            "defect",
            "expected_observation",
            "actual_observation",
            "proof_survived",
        ):
            with self.subTest(field=field):
                receipt = valid_receipt()
                receipt["adversarial_probes"][0].pop(field)
                self.assert_receipt_invalid(receipt, "invalid protocol receipt")
        receipt = valid_receipt()
        receipt["adversarial_probes"][0]["proof_survived"] = True
        self.assert_receipt_invalid(receipt, "invalid protocol receipt")

    def test_unknown_failure_pattern_id_is_rejected(self) -> None:
        receipt = valid_receipt()
        receipt["findings"] = [
            {
                "id": "ARCH-1",
                "severity": "Low",
                "location": "owner:1",
                "source_target": "a" * 40,
                "blocks_pr": False,
                "disposition": "fixed",
                "verification": "replayed",
                "failure_pattern_ids": ["PQ-999"],
            }
        ]
        self.assert_receipt_invalid(receipt, "unknown failure pattern IDs")

    def test_failure_pattern_ids_are_required_and_unique(self) -> None:
        finding = {
            "id": "ARCH-1",
            "severity": "Low",
            "location": "owner:1",
            "source_target": "a" * 40,
            "blocks_pr": False,
            "disposition": "fixed",
            "verification": "replayed",
            "failure_pattern_ids": ["PQ-009"],
        }
        receipt = valid_receipt()
        receipt["findings"] = [finding]
        self.assertEqual(receipt_failures(receipt, "architecture", "a" * 40), [])
        for field in ("location", "source_target"):
            with self.subTest(field=field):
                receipt = valid_receipt()
                incomplete_finding = copy.deepcopy(finding)
                incomplete_finding.pop(field)
                receipt["findings"] = [incomplete_finding]
                self.assert_receipt_invalid(receipt, "invalid protocol receipt")
        receipt = valid_receipt()
        invalid_source = copy.deepcopy(finding)
        invalid_source["source_target"] = "narrative-head"
        receipt["findings"] = [invalid_source]
        self.assert_receipt_invalid(receipt, "invalid protocol receipt")
        receipt = valid_receipt()
        finding_without_ids = copy.deepcopy(finding)
        finding_without_ids.pop("failure_pattern_ids")
        receipt["findings"] = [finding_without_ids]
        self.assert_receipt_invalid(receipt, "invalid protocol receipt")
        receipt = valid_receipt()
        duplicate_ids = copy.deepcopy(finding)
        duplicate_ids["failure_pattern_ids"] = ["PQ-009", "PQ-009"]
        receipt["findings"] = [duplicate_ids]
        self.assert_receipt_invalid(receipt, "invalid protocol receipt")

    def test_failure_pattern_registry_is_complete_and_unique(self) -> None:
        self.assertEqual(
            FAILURE_PATTERN_IDS, {f"PQ-{number:03d}" for number in range(1, 14)}
        )
        self.assertEqual(contract_failures(), [])
        temporary, root = self.copied_contract_root()
        try:
            patterns = root / PROOF_PATTERNS_PATH.relative_to(CONTRACT_ROOT)
            patterns.write_text(
                patterns.read_text(encoding="utf-8").replace("`PQ-013`", "`PQ-012`"),
                encoding="utf-8",
            )
            failures = contract_failures(root)
            self.assertIn("proof patterns: duplicate IDs", failures)
            self.assertIn("proof patterns: incomplete registry", failures)
        finally:
            temporary.cleanup()

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
        patterns = PROOF_PATTERNS_PATH.relative_to(CONTRACT_ROOT)
        (root / patterns).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(patterns, root / patterns)
        for relative_path in PROOF_QUALITY_STATE_REQUIREMENTS:
            source = Path(relative_path)
            (root / source).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, root / source)
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
                    remove_contract_token(skill, token)
                    self.assertTrue(
                        any(
                            requirement_id in failure
                            for failure in contract_failures(root)
                        )
                    )
                finally:
                    temporary.cleanup()

    def test_each_semantic_agent_requirement_is_independently_enforced(self) -> None:
        for requirement_id, token in SEMANTIC_AGENT_REQUIREMENTS.items():
            with self.subTest(requirement_id=requirement_id):
                temporary, root = self.copied_contract_root()
                try:
                    agent = root / ".codex/agents/architecture-reviewer.toml"
                    remove_contract_token(agent, token)
                    self.assertTrue(
                        any(
                            requirement_id in failure
                            for failure in contract_failures(root)
                        )
                    )
                finally:
                    temporary.cleanup()

    def test_all_reviewer_contracts_require_shared_proof_quality(self) -> None:
        self.assertEqual(set(SPECIALTY_PROOF_REQUIREMENTS), set(REVIEWERS))
        for reviewer, (agent_name, skill_name) in REVIEWERS.items():
            with self.subTest(reviewer=reviewer):
                agent = " ".join(
                    (Path(".codex/agents") / agent_name)
                    .read_text(encoding="utf-8")
                    .split()
                )
                skill = " ".join(
                    (Path(".agents/skills") / skill_name / "SKILL.md")
                    .read_text(encoding="utf-8")
                    .split()
                )
                for token in PROOF_QUALITY_SHARED_REQUIREMENTS.values():
                    self.assertIn(token, agent)
                    self.assertIn(token, skill)
                self.assertIn(SPECIALTY_PROOF_REQUIREMENTS[reviewer], agent)
                self.assertIn(SPECIALTY_PROOF_REQUIREMENTS[reviewer], skill)

    def test_each_proof_quality_skill_requirement_is_independently_enforced(
        self,
    ) -> None:
        for reviewer, (_, skill_name) in REVIEWERS.items():
            temporary, root = self.copied_contract_root()
            try:
                for requirement_id, token in PROOF_QUALITY_SHARED_REQUIREMENTS.items():
                    with self.subTest(reviewer=reviewer, requirement_id=requirement_id):
                        skill = root / ".agents/skills" / skill_name / "SKILL.md"
                        original = remove_contract_token(skill, token)
                        self.assertTrue(
                            any(
                                f"{reviewer}:" in failure and requirement_id in failure
                                for failure in contract_failures(root)
                            )
                        )
                        skill.write_text(original, encoding="utf-8")
            finally:
                temporary.cleanup()

    def test_each_proof_quality_agent_requirement_is_independently_enforced(
        self,
    ) -> None:
        for reviewer, (agent_name, _) in REVIEWERS.items():
            temporary, root = self.copied_contract_root()
            try:
                for requirement_id, token in PROOF_QUALITY_SHARED_REQUIREMENTS.items():
                    with self.subTest(reviewer=reviewer, requirement_id=requirement_id):
                        agent = root / ".codex/agents" / agent_name
                        original = remove_contract_token(agent, token)
                        self.assertTrue(
                            any(
                                f"{reviewer}:" in failure and requirement_id in failure
                                for failure in contract_failures(root)
                            )
                        )
                        agent.write_text(original, encoding="utf-8")
            finally:
                temporary.cleanup()

    def test_candidate_lifecycle_is_independently_enforced_for_every_pair(
        self,
    ) -> None:
        for reviewer, (agent_name, skill_name) in REVIEWERS.items():
            with self.subTest(reviewer=reviewer, surface="agent"):
                temporary, root = self.copied_contract_root()
                try:
                    remove_contract_token(
                        root / ".codex/agents" / agent_name,
                        PROOF_QUALITY_AGENT_LIFECYCLE,
                    )
                    self.assertTrue(
                        any(
                            f"{reviewer}: agent missing proof.lifecycle" in failure
                            for failure in contract_failures(root)
                        )
                    )
                finally:
                    temporary.cleanup()
            with self.subTest(reviewer=reviewer, surface="skill"):
                temporary, root = self.copied_contract_root()
                try:
                    remove_contract_token(
                        root / ".agents/skills" / skill_name / "SKILL.md",
                        PROOF_QUALITY_SKILL_LIFECYCLE,
                    )
                    self.assertTrue(
                        any(
                            f"{reviewer}: skill missing proof.lifecycle" in failure
                            for failure in contract_failures(root)
                        )
                    )
                finally:
                    temporary.cleanup()

    def test_candidate_lifecycle_is_independently_enforced_in_state(self) -> None:
        for relative_path, token in PROOF_QUALITY_STATE_REQUIREMENTS.items():
            with self.subTest(path=relative_path):
                temporary, root = self.copied_contract_root()
                try:
                    remove_contract_token(root / relative_path, token)
                    self.assertTrue(
                        any(
                            "proof.lifecycle: state missing" in failure
                            for failure in contract_failures(root)
                        )
                    )
                finally:
                    temporary.cleanup()

    def test_candidate_lifecycle_is_independently_enforced_in_matrix(self) -> None:
        temporary, root = self.copied_contract_root()
        try:
            matrix = root / (
                ".agent-loop/initiatives/WS-CI-004-review-evidence-integrity/"
                "REVIEWER_MATRIX.md"
            )
            remove_contract_token(matrix, PROOF_QUALITY_MATRIX_LIFECYCLE)
            self.assertIn("matrix: missing proof.lifecycle", contract_failures(root))
        finally:
            temporary.cleanup()

    def test_matrix_specialty_obligations_are_independently_enforced(self) -> None:
        temporary, root = self.copied_contract_root()
        try:
            matrix = root / (
                ".agent-loop/initiatives/WS-CI-004-review-evidence-integrity/"
                "REVIEWER_MATRIX.md"
            )
            for label, token in MATRIX_SPECIALTY_REQUIREMENTS.items():
                with self.subTest(label=label):
                    original = remove_contract_token(matrix, token)
                    self.assertIn(
                        f"matrix: specialty obligation drift for {label}",
                        contract_failures(root),
                    )
                    matrix.write_text(original, encoding="utf-8")
        finally:
            temporary.cleanup()

    def assert_specialty_pair(self, reviewer: str) -> None:
        agent_name, skill_name = REVIEWERS[reviewer]
        token = SPECIALTY_PROOF_REQUIREMENTS[reviewer]
        self.assertIn(
            token,
            " ".join(
                (Path(".codex/agents") / agent_name).read_text(encoding="utf-8").split()
            ),
        )
        self.assertIn(
            token,
            " ".join(
                (Path(".agents/skills") / skill_name / "SKILL.md")
                .read_text(encoding="utf-8")
                .split()
            ),
        )

    def test_qa_and_test_delta_require_discrimination_probe(self) -> None:
        self.assert_specialty_pair("qa")
        self.assert_specialty_pair("test_delta")

    def test_architecture_and_security_require_database_integrity_probe(self) -> None:
        self.assert_specialty_pair("architecture")
        self.assert_specialty_pair("security")

    def test_reuse_requires_canonical_rule_comparison(self) -> None:
        self.assert_specialty_pair("reuse_dedup")

    def test_ci_requires_execution_custody_trace(self) -> None:
        self.assert_specialty_pair("ci_integrity")

    def test_docs_and_product_contracts_remain_proportionate(self) -> None:
        self.assert_specialty_pair("documentation")
        self.assert_specialty_pair("product_ops")

    def test_specialty_obligations_are_independently_enforced(self) -> None:
        for reviewer, token in SPECIALTY_PROOF_REQUIREMENTS.items():
            with self.subTest(reviewer=reviewer):
                temporary, root = self.copied_contract_root()
                try:
                    agent_name, skill_name = REVIEWERS[reviewer]
                    for path in (
                        root / ".codex/agents" / agent_name,
                        root / ".agents/skills" / skill_name / "SKILL.md",
                    ):
                        original = remove_contract_token(path, token)
                        self.assertTrue(
                            any(
                                f"{reviewer}:" in failure
                                and "proof.specialty" in failure
                                for failure in contract_failures(root)
                            )
                        )
                        path.write_text(original, encoding="utf-8")
                finally:
                    temporary.cleanup()

    def test_specialty_completion_obligations_are_independently_enforced(
        self,
    ) -> None:
        for reviewer, tokens in SPECIALTY_PROOF_COMPLETION_REQUIREMENTS.items():
            agent_name, skill_name = REVIEWERS[reviewer]
            for surface, path, token in (
                ("agent", Path(".codex/agents") / agent_name, tokens["agent"]),
                (
                    "skill",
                    Path(".agents/skills") / skill_name / "SKILL.md",
                    tokens["skill"],
                ),
            ):
                with self.subTest(reviewer=reviewer, surface=surface):
                    temporary, root = self.copied_contract_root()
                    try:
                        remove_contract_token(root / path, token)
                        self.assertTrue(
                            any(
                                f"{reviewer}: {surface} missing "
                                "proof.specialty_completion" in failure
                                for failure in contract_failures(root)
                            )
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
            self.assertTrue(
                any(
                    "agent missing 'hand off'" in item
                    for item in contract_failures(root)
                )
            )
        finally:
            temporary.cleanup()
        temporary, root = self.copied_contract_root()
        try:
            matrix = (
                root
                / ".agent-loop/initiatives/WS-CI-004-review-evidence-integrity/REVIEWER_MATRIX.md"
            )
            matrix.write_text(
                matrix.read_text(encoding="utf-8").replace(
                    "`architecture`", "`architecture_typo`", 1
                ),
                encoding="utf-8",
            )
            self.assertTrue(
                any(
                    "canonical reviewer IDs" in item for item in contract_failures(root)
                )
            )
        finally:
            temporary.cleanup()

    def test_matrix_agent_and_skill_pairs_are_one_to_one(self) -> None:
        temporary, root = self.copied_contract_root()
        try:
            matrix = (
                root
                / ".agent-loop/initiatives/WS-CI-004-review-evidence-integrity/REVIEWER_MATRIX.md"
            )
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
        cases["cases"] = [
            row for row in cases["cases"] if row["reviewer"] != "security"
        ]
        self.assertTrue(
            any(
                "security: missing cases" in item
                for item in fixture_failures(cases, None)
            )
        )
        cases = copy.deepcopy(self.cases)
        cases["cases"] = [row for row in cases["cases"] if row["id"] != "qa-handoff"]
        self.assertTrue(
            any("qa: missing cases" in item for item in fixture_failures(cases, None))
        )

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
        self.assertTrue(
            any(
                "invalid outcome" in item
                for item in fixture_failures(self.cases, expectations)
            )
        )

    def test_duplicate_expectations_and_unknown_handoffs_fail(self) -> None:
        expectations = copy.deepcopy(load_json(EXPECTATIONS_PATH))
        expectations["expectations"].append(
            copy.deepcopy(expectations["expectations"][0])
        )
        self.assertIn(
            "expectations: duplicate case IDs",
            fixture_failures(self.cases, expectations),
        )
        expectations = copy.deepcopy(load_json(EXPECTATIONS_PATH))
        expectations["expectations"][0]["handoff_specialty"] = "security_typo"
        self.assertTrue(
            any(
                "unknown handoff specialty" in item
                for item in fixture_failures(self.cases, expectations)
            )
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
        self.assertEqual(
            output_failures([], expectation), ["output: expected an object"]
        )
        for payload in ("[]", '"invalid"', "{"):
            with self.subTest(payload=payload):
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8"
                ) as output_file:
                    output_file.write(payload)
                    output_file.flush()
                    self.assertEqual(
                        main(
                            [
                                "validate-output",
                                "--case",
                                expectation["case_id"],
                                "--output",
                                output_file.name,
                            ]
                        ),
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
            "schema_version": 3,
            "custody": "advisory_session",
            "target": {
                "base_sha": "a" * 40,
                "merge_base_sha": "a" * 40,
                "head_sha": "a" * 40,
            },
            "reviewer": {"specialty": "architecture", "run_id": "eval-1"},
            "inspections": {
                "start": {"cleanliness": "dirty"},
                "end": {"cleanliness": "dirty"},
            },
            "evidence": [
                {"kind": "executed", "source": "review target", "result": "pass"},
                {"kind": "inspected", "source": "raw case", "result": "pass"},
            ],
            "impact_cone": [
                {"source": "case owner", "relevance": "owns evaluated behavior"}
            ],
            "adversarial_probes": [
                {
                    "hypothesis": "case bypass",
                    "method": "inspect raw case",
                    "defect": "remove the required route",
                    "expected_observation": "inspection detects the missing route",
                    "actual_observation": "inspection detected the missing route",
                    "proof_survived": False,
                    "result": "pass",
                }
            ],
            "traceability": [
                {
                    "criterion": "routing",
                    "behavior": "route finding",
                    "owner": "architecture",
                    "implementation_source": "raw case",
                    "proof_source": "inspection",
                    "execution_custody": "review session",
                    "claimed_boundary": "negative_structure",
                    "proof_strength": "negative_structure",
                    "proof_custody": {
                        "kind": "inspected",
                        "observations": ["syntax_or_registry"],
                    },
                    "proof_compatibility": "compatible",
                    "result": "verified",
                }
            ],
            "residual_escape": {
                "hypothesis": "a second route is hidden",
                "method": "inspect supplied evidence",
                "result": "falsified",
            },
            "findings": [
                {
                    "id": "ARCH-7",
                    "severity": "Medium",
                    "location": "case",
                    "source_target": "a" * 40,
                    "blocks_pr": False,
                    "disposition": "fixed",
                    "verification": "replayed",
                    "failure_pattern_ids": ["PQ-009"],
                }
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
            "output: required finding not replayed",
            output_failures(broken, expectation, receipt),
        )
        broken = copy.deepcopy(output)
        broken["finding_ids"] = [{}]
        self.assertIn(
            "output: finding_ids must contain only strings",
            output_failures(broken, expectation, receipt),
        )
        broken = copy.deepcopy(output)
        broken["handoff_specialty"] = "security"
        self.assertIn(
            "output: wrong handoff", output_failures(broken, expectation, receipt)
        )

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
        passing_receipt["inspections"] = {
            "start": {"cleanliness": "clean"},
            "end": {"cleanliness": "clean"},
        }
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
            "schema_version": 3,
            "custody": "advisory_session",
            "target": {
                "base_sha": "a" * 40,
                "merge_base_sha": "a" * 40,
                "head_sha": "a" * 40,
            },
            "reviewer": {"specialty": "architecture", "run_id": "eval-positive"},
            "inspections": {
                "start": {"cleanliness": "dirty"},
                "end": {"cleanliness": "dirty"},
            },
            "evidence": [
                {"kind": "executed", "source": "review target", "result": "pass"},
                {"kind": "inspected", "source": "raw case", "result": "pass"},
            ],
            "impact_cone": [
                {"source": "case owner", "relevance": "owns evaluated behavior"}
            ],
            "adversarial_probes": [
                {
                    "hypothesis": "case bypass",
                    "method": "inspect raw case",
                    "defect": "remove the expected defect",
                    "expected_observation": "inspection detects the missing defect",
                    "actual_observation": "inspection detected the missing defect",
                    "proof_survived": False,
                    "result": "pass",
                }
            ],
            "traceability": [
                {
                    "criterion": "finding",
                    "behavior": "detect defect",
                    "owner": "architecture",
                    "implementation_source": "raw case",
                    "proof_source": "inspection",
                    "execution_custody": "review session",
                    "claimed_boundary": "negative_structure",
                    "proof_strength": "negative_structure",
                    "proof_custody": {
                        "kind": "inspected",
                        "observations": ["syntax_or_registry"],
                    },
                    "proof_compatibility": "compatible",
                    "result": "verified",
                }
            ],
            "residual_escape": {
                "hypothesis": "defect is concealed",
                "method": "inspect supplied evidence",
                "result": "falsified",
            },
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
