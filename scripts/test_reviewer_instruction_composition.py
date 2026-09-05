"""Focused regression tests for composed reviewer instructions."""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.reviewer_contracts import (
    CODEX_CONFIG_PATH,
    MATRIX_PATH,
    PROOF_CASES_PATH,
    PROOF_OPTIONAL_PATTERNS,
    PROOF_CASE_CONTRACTS,
    PROOF_EXPECTATIONS_PATH,
    PROOF_RESULTS_PATH,
    PROOF_PATTERNS_PATH,
    PROOF_QUALITY_SHARED_REQUIREMENTS,
    PROOF_QUALITY_STATE_REQUIREMENTS,
    PROOF_STRENGTHS,
    PROOF_SUBJECT_PATHS,
    PROOF_SUPERSESSION_MODE,
    REVIEWERS,
    ROOT as CONTRACT_ROOT,
    SEMANTIC_SKILL_REQUIREMENTS,
    SHARED_PROTOCOL_PATH,
    SHARED_PROTOCOL_REQUIREMENTS,
    TRUST_WORKFLOW_REQUIREMENTS,
    contract_failures,
    _proof_subjects_match,
    proof_supersession_failures,
    proof_evaluation_failures,
    has_canonical_shared_protocol_directive,
)


def remove_contract_token(path: Path, token: str) -> str:
    original = path.read_text(encoding="utf-8")
    pattern = r"\s+".join(re.escape(part) for part in token.split())
    mutated, count = re.subn(pattern, " removed ", original)
    if count < 1:
        raise AssertionError(f"expected {token!r} in {path}")
    path.write_text(mutated, encoding="utf-8")
    return original


class ReviewerInstructionCompositionTests(unittest.TestCase):
    def test_handoff_taxonomy_accepts_only_source_supported_alternatives(self) -> None:
        cases = json.loads(PROOF_CASES_PATH.read_text(encoding="utf-8"))
        expectations = json.loads(PROOF_EXPECTATIONS_PATH.read_text(encoding="utf-8"))
        baseline = json.loads(PROOF_RESULTS_PATH.read_text(encoding="utf-8"))
        for patterns, accepted in (
            (["PQ-004"], True),
            (["PQ-007"], True),
            ([], False),
            (["PQ-001"], False),
            (["PQ-004", "PQ-001"], False),
            (["PQ-007", "PQ-001"], False),
            (["PQ-004", "PQ-007"], True),
        ):
            with self.subTest(patterns=patterns):
                results = copy.deepcopy(baseline)
                row = next(
                    row
                    for row in results["results"]
                    if row["case_id"] == "pq-product-partial-owner-handoff"
                )
                row["failure_pattern_ids"] = patterns
                failures = proof_evaluation_failures(
                    cases, expectations, results, check_supersession=False
                )
                self.assertEqual(not failures, accepted, failures)

    def test_clear_control_rejects_any_failure_pattern(self) -> None:
        cases = json.loads(PROOF_CASES_PATH.read_text(encoding="utf-8"))
        expectations = json.loads(PROOF_EXPECTATIONS_PATH.read_text(encoding="utf-8"))
        results = json.loads(PROOF_RESULTS_PATH.read_text(encoding="utf-8"))
        row = next(
            row
            for row in results["results"]
            if row["case_id"] == "pq-security-real-isolation-control"
        )
        row["failure_pattern_ids"] = ["PQ-011"]
        self.assertIn(
            "pq-security-real-isolation-control: unsupported proof pattern",
            proof_evaluation_failures(
                cases, expectations, results, check_supersession=False
            ),
        )

    def test_optional_source_labels_cannot_replace_required_defect(self) -> None:
        cases = json.loads(PROOF_CASES_PATH.read_text(encoding="utf-8"))
        expectations = json.loads(PROOF_EXPECTATIONS_PATH.read_text(encoding="utf-8"))
        baseline = json.loads(PROOF_RESULTS_PATH.read_text(encoding="utf-8"))
        for case_id, optional in PROOF_OPTIONAL_PATTERNS.items():
            with self.subTest(case_id=case_id):
                results = copy.deepcopy(baseline)
                row = next(
                    row for row in results["results"] if row["case_id"] == case_id
                )
                row["failure_pattern_ids"] = sorted(optional)
                self.assertIn(
                    f"{case_id}: required proof pattern missing",
                    proof_evaluation_failures(
                        cases, expectations, results, check_supersession=False
                    ),
                )
                row["failure_pattern_ids"] = sorted(
                    PROOF_CASE_CONTRACTS[case_id][3] | optional | {"PQ-011"}
                )
                self.assertIn(
                    f"{case_id}: unsupported proof pattern",
                    proof_evaluation_failures(
                        cases, expectations, results, check_supersession=False
                    ),
                )

    def test_fenced_skill_directive_cannot_supply_live_instruction(self) -> None:
        directive = "## Shared evidence\n\nRead `reviewer-evidence-protocol` first;\n"
        for fence in ("```", "~~~~"):
            with self.subTest(fence=fence):
                self.assertFalse(
                    has_canonical_shared_protocol_directive(
                        f"{fence}markdown\n{directive}{fence}\n"
                    )
                )
                self.assertFalse(
                    has_canonical_shared_protocol_directive(
                        f"{fence}markdown\n{directive}"
                    )
                )
        self.assertTrue(has_canonical_shared_protocol_directive(directive))

    def copied_contract_root(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        sources = {
            CODEX_CONFIG_PATH.relative_to(CONTRACT_ROOT),
            SHARED_PROTOCOL_PATH.relative_to(CONTRACT_ROOT),
            MATRIX_PATH.relative_to(CONTRACT_ROOT),
            Path(".ci/reviewer-evidence/evaluations/CASES.json"),
            PROOF_PATTERNS_PATH.relative_to(CONTRACT_ROOT),
            *map(Path, PROOF_QUALITY_STATE_REQUIREMENTS),
            *map(Path, TRUST_WORKFLOW_REQUIREMENTS),
        }
        for _, (agent_name, skill_name) in REVIEWERS.items():
            sources.add(Path(".codex/agents") / agent_name)
            sources.add(Path(".agents/skills") / skill_name / "SKILL.md")
        for source in sources:
            (root / source).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(CONTRACT_ROOT / source, root / source)
        return temporary, root

    def test_composed_contract_baseline_passes(self) -> None:
        self.assertEqual(contract_failures(), [])

    def test_shared_protocol_obligations_are_enforced_once(self) -> None:
        requirements = {
            **SHARED_PROTOCOL_REQUIREMENTS,
            **SEMANTIC_SKILL_REQUIREMENTS,
            **PROOF_QUALITY_SHARED_REQUIREMENTS,
        }
        temporary, root = self.copied_contract_root()
        try:
            protocol = root / SHARED_PROTOCOL_PATH.relative_to(CONTRACT_ROOT)
            for requirement_id, token in requirements.items():
                with self.subTest(requirement_id=requirement_id):
                    original = remove_contract_token(protocol, token)
                    self.assertTrue(
                        any(
                            failure.startswith(
                                f"shared protocol: missing {requirement_id}"
                            )
                            for failure in contract_failures(root)
                        )
                    )
                    protocol.write_text(original, encoding="utf-8")
        finally:
            temporary.cleanup()

    def test_every_pair_references_shared_protocol_and_specialty(self) -> None:
        temporary, root = self.copied_contract_root()
        try:
            for reviewer, (agent_name, skill_name) in REVIEWERS.items():
                agent = root / ".codex/agents" / agent_name
                skill = root / ".agents/skills" / skill_name / "SKILL.md"
                for surface, path, token, expected in (
                    (
                        "agent_protocol",
                        agent,
                        "reviewer-evidence-protocol",
                        f"{reviewer}: agent instructions differ from canonical loader",
                    ),
                    (
                        "agent_specialty",
                        agent,
                        skill_name,
                        f"{reviewer}: agent instructions differ from canonical loader",
                    ),
                    (
                        "skill_protocol",
                        skill,
                        "reviewer-evidence-protocol",
                        f"{reviewer}: skill missing canonical shared protocol directive",
                    ),
                ):
                    with self.subTest(reviewer=reviewer, surface=surface):
                        original = remove_contract_token(path, token)
                        self.assertIn(expected, contract_failures(root))
                        path.write_text(original, encoding="utf-8")
        finally:
            temporary.cleanup()

    def test_extra_tokens_do_not_rescue_wrong_agent_loader(self) -> None:
        temporary, root = self.copied_contract_root()
        try:
            agent = root / ".codex/agents/architecture-reviewer.toml"
            mutated = (
                agent.read_text(encoding="utf-8")
                .replace(
                    "reviewer-evidence-protocol",
                    "wrong-reviewer-evidence-protocol",
                )
                .replace(
                    "architecture-review/SKILL.md",
                    "wrong-architecture-review/SKILL.md",
                )
                .replace(
                    '\n"""\n',
                    "\nreviewer-evidence-protocol architecture-review\n" + '"""\n',
                    1,
                )
            )
            agent.write_text(mutated, encoding="utf-8")
            self.assertIn(
                "architecture: agent instructions differ from canonical loader",
                contract_failures(root),
            )
        finally:
            temporary.cleanup()

    def test_negated_or_prefixed_loaders_fail_structurally(self) -> None:
        temporary, root = self.copied_contract_root()
        try:
            agent = root / ".codex/agents/architecture-reviewer.toml"
            original_agent = agent.read_text(encoding="utf-8")
            agent.write_text(
                original_agent.replace("Read and follow", "Do not read and follow", 1),
                encoding="utf-8",
            )
            self.assertIn(
                "architecture: agent instructions differ from canonical loader",
                contract_failures(root),
            )
            agent.write_text(original_agent, encoding="utf-8")

            skill = root / ".agents/skills/architecture-review/SKILL.md"
            original_skill = skill.read_text(encoding="utf-8")
            for replacement in (
                "Do not read `reviewer-evidence-protocol` first;",
                "Read `wrong/reviewer-evidence-protocol` first;",
            ):
                with self.subTest(replacement=replacement):
                    skill.write_text(
                        original_skill.replace(
                            "Read `reviewer-evidence-protocol` first;",
                            replacement,
                            1,
                        )
                        + "\nRead `reviewer-evidence-protocol` first;\n",
                        encoding="utf-8",
                    )
                    self.assertIn(
                        "architecture: skill missing canonical shared protocol directive",
                        contract_failures(root),
                    )
            skill.write_text(original_skill, encoding="utf-8")
        finally:
            temporary.cleanup()

    def test_specialty_output_contract_is_required(self) -> None:
        temporary, root = self.copied_contract_root()
        try:
            skill = root / ".agents/skills/architecture-review/SKILL.md"
            remove_contract_token(skill, "## Output")
            self.assertIn(
                "architecture: skill missing '## Output'", contract_failures(root)
            )
        finally:
            temporary.cleanup()

    def test_reviewer_runtime_invariants_are_enforced(self) -> None:
        cases = (
            (
                'sandbox_mode = "read-only"',
                'sandbox_mode = "workspace-write"',
                "sandbox must be read-only",
            ),
            (
                'model = "gpt-5.6-sol"',
                'model = "gpt-5.5"',
                "model must be gpt-5.6-sol",
            ),
            (
                'model_reasoning_effort = "high"',
                'model_reasoning_effort = "low"',
                "reasoning must be high",
            ),
        )
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                temporary, root = self.copied_contract_root()
                try:
                    agent = root / ".codex/agents/architecture-reviewer.toml"
                    agent.write_text(
                        agent.read_text(encoding="utf-8").replace(old, new, 1),
                        encoding="utf-8",
                    )
                    self.assertTrue(
                        any(expected in failure for failure in contract_failures(root))
                    )
                finally:
                    temporary.cleanup()

    def test_lead_and_default_reviewer_models_are_enforced(self) -> None:
        cases = (
            ('model = "gpt-6-astra"', 'model = "gpt-5.6-sol"', "lead model"),
            (
                'default_subagent_model = "gpt-5.6-sol"',
                'default_subagent_model = "gpt-5.5"',
                "default reviewer model",
            ),
            (
                'default_subagent_reasoning_effort = "high"',
                'default_subagent_reasoning_effort = "low"',
                "default reviewer reasoning",
            ),
        )
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                temporary, root = self.copied_contract_root()
                try:
                    config = root / CODEX_CONFIG_PATH.relative_to(CONTRACT_ROOT)
                    config.write_text(
                        config.read_text(encoding="utf-8").replace(old, new, 1),
                        encoding="utf-8",
                    )
                    self.assertTrue(
                        any(expected in failure for failure in contract_failures(root))
                    )
                finally:
                    temporary.cleanup()

    def test_contract_inspection_is_a_schema_owned_proof_strength(self) -> None:
        self.assertIn("contract_inspection", PROOF_STRENGTHS)

    def test_current_evaluation_binds_exact_complete_subject_set(self) -> None:
        self.assertTrue(
            {
                ".agents/skills/reviewer-evidence-protocol/SKILL.md",
                ".agents/skills/reviewer-evidence-protocol/references/"
                "proof-quality-patterns.md",
                ".codex/config.toml",
                ".ci/reviewer-evidence/INTERNAL_REVIEW_RECEIPT.schema.json",
                ".ci/reviewer-evidence/evaluations/PROOF_CASES.json",
            }.issubset(PROOF_SUBJECT_PATHS)
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=CONTRACT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        results = {
            "evaluated_head": head,
            "supersession": {
                "mode": PROOF_SUPERSESSION_MODE,
                "subject_paths": sorted(PROOF_SUBJECT_PATHS),
            },
        }
        self.assertEqual(proof_supersession_failures(results), [])
        results["supersession"]["subject_paths"].remove(
            ".agents/skills/reviewer-evidence-protocol/SKILL.md"
        )
        self.assertIn(
            "proof supersession: subject coverage mismatch",
            proof_supersession_failures(results),
        )

    def test_proof_case_task_or_evidence_change_breaks_exact_binding(self) -> None:
        original = PROOF_CASES_PATH.read_bytes()
        parsed = json.loads(original)
        original_ids = [row["id"] for row in parsed["cases"]]
        for field in ("task", "evidence"):
            with self.subTest(field=field):
                mutated = copy.deepcopy(parsed)
                mutated["cases"][0][field] += " Material mutation."
                self.assertEqual([row["id"] for row in mutated["cases"]], original_ids)
                mutated_bytes = json.dumps(mutated, indent=2).encode() + b"\n"
                self.assertFalse(
                    _proof_subjects_match(
                        original,
                        mutated_bytes,
                        normalize_legacy_lifecycle=False,
                    )
                )


if __name__ == "__main__":
    unittest.main()
