#!/usr/bin/env python3
"""Validate reviewer adoption contracts and isolated evaluation output."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
INITIATIVE = ROOT / ".ci/reviewer-evidence"
CASES_PATH = INITIATIVE / "evaluations/CASES.json"
EXPECTATIONS_PATH = INITIATIVE / "evaluations/EXPECTATIONS.json"
PROOF_CASES_PATH = INITIATIVE / "evaluations/PROOF_CASES.json"
PROOF_EXPECTATIONS_PATH = INITIATIVE / "evaluations/PROOF_EXPECTATIONS.json"
PROOF_RESULTS_PATH = INITIATIVE / "evaluations/PROOF_RESULTS.json"
MATRIX_PATH = INITIATIVE / "REVIEWER_MATRIX.md"
RECEIPT_SCHEMA_PATH = ROOT / ".ci/reviewer-evidence/INTERNAL_REVIEW_RECEIPT.schema.json"
PROOF_PATTERNS_PATH = (
    ROOT
    / ".agents/skills/reviewer-evidence-protocol/references/proof-quality-patterns.md"
)
SHARED_PROTOCOL_PATH = ROOT / ".agents/skills/reviewer-evidence-protocol/SKILL.md"
CODEX_CONFIG_PATH = ROOT / ".codex/config.toml"
CASE_CLASSES = {"positive", "negative", "stale_replay", "output_contract", "handoff"}
OUTCOMES = {"finding", "clear", "replayed", "provisional", "handoff"}
RECEIPT_SCHEMA = json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))
PROOF_STRENGTHS = set(RECEIPT_SCHEMA["$defs"]["proof_strength"]["enum"])
PROOF_CUSTODY_MATRIX = RECEIPT_SCHEMA["x-proof-custody-matrix"]
PASSING_VERDICTS = {"PASS", "PASS AFTER FIXES", "PASS WITH LOW RISKS"}
FAILURE_PATTERN_IDS = {f"PQ-{number:03d}" for number in range(1, 14)}
FAILURE_PATTERN_ROW = re.compile(r"^\| `(PQ-[0-9]{3})` \|", re.MULTILINE)
PROOF_CASE_CONTRACTS = {
    "pq-architecture-composite-owner": ("architecture", "finding", None, {"PQ-007"}),
    "pq-architecture-public-port-control": ("architecture", "clear", None, set()),
    "pq-ci-mocked-rollback": ("ci_integrity", "finding", None, {"PQ-002"}),
    "pq-ci-real-transaction-control": ("ci_integrity", "clear", None, set()),
    "pq-docs-untrusted-instruction": ("documentation", "finding", None, {"PQ-011"}),
    "pq-docs-consistent-state-control": ("documentation", "clear", None, set()),
    "pq-product-partial-owner-handoff": (
        "product_ops",
        "handoff",
        "security",
        {"PQ-007"},
    ),
    "pq-product-advisory-control": ("product_ops", "clear", None, set()),
    "pq-qa-malformed-public-input": ("qa", "finding", None, {"PQ-008"}),
    "pq-qa-nondiscriminating-input": ("qa", "finding", None, {"PQ-013"}),
    "pq-qa-public-validation-control": ("qa", "clear", None, set()),
    "pq-qa-discriminating-input-control": ("qa", "clear", None, set()),
    "pq-reuse-canonical-rule-drift": ("reuse_dedup", "finding", None, {"PQ-005"}),
    "pq-reuse-canonical-owner-control": ("reuse_dedup", "clear", None, set()),
    "pq-security-label-only-fake": ("security", "finding", None, {"PQ-001"}),
    "pq-security-sql-null-guard": ("security", "finding", None, {"PQ-006"}),
    "pq-security-missing-row-isolation": ("security", "finding", None, {"PQ-003"}),
    "pq-security-real-isolation-control": ("security", "clear", None, set()),
    "pq-senior-setup-only-failure": ("senior_engineering", "finding", None, {"PQ-012"}),
    "pq-senior-target-reached-control": ("senior_engineering", "clear", None, set()),
    "pq-test-delta-setup-only-failure": ("test_delta", "finding", None, {"PQ-012"}),
    "pq-test-delta-real-mutation-control": ("test_delta", "clear", None, set()),
}
PROOF_CASE_IDS = set(PROOF_CASE_CONTRACTS)
PROOF_SUBJECT_PATHS = {
    *{
        f".agents/skills/{name}-review/SKILL.md"
        for name in (
            "architecture",
            "ci-integrity",
            "docs",
            "product-ops",
            "qa",
            "reuse-dedup",
            "security",
            "senior-engineer",
            "test-delta",
        )
    },
    *{
        f".codex/agents/{name}-reviewer.toml"
        for name in (
            "architecture",
            "ci-integrity",
            "docs",
            "product-ops",
            "qa",
            "reuse-dedup",
            "security",
            "senior-engineer",
            "test-delta",
        )
    },
    ".ci/reviewer-evidence/REVIEWER_MATRIX.md",
}
PROOF_SUBJECT_EVALUATED_PATH = {
    ".ci/reviewer-evidence/REVIEWER_MATRIX.md": (
        ".agent-loop/initiatives/WS-CI-004-review-evidence-integrity/"
        "REVIEWER_MATRIX.md"
    ),
}
PROOF_SUPERSESSION_MODE = "evaluated-ancestor-with-lifecycle-only-normalization"
ANSWER_LEAK_RE = re.compile(
    r"expected\s+(?:answer|outcome|classification)|required\s+(?:pattern|finding)|"
    r"(?:classification|outcome|result|finding\s+id)\s*:|"
    r"failure_pattern_ids|finding_id|\bPQ-[0-9]{3}\b",
    re.IGNORECASE,
)
TRUST_WORKFLOW_REQUIREMENTS = {
    ".agents/skills/evidence-gate/SKILL.md": (
        "A passing summary does not claim private session-receipt custody"
    ),
    ".agents/skills/pr-trust-bundle/SKILL.md": (
        "Never copy private session receipts into Git"
    ),
    ".agents/skills/task-chunk-loop/SKILL.md": (
        "without copying private session receipts into Git"
    ),
}
SEMANTIC_SKILL_REQUIREMENTS = {
    "semantic.atomization": "Atomize every material criterion",
    "semantic.ownership": "record its owner",
    "semantic.implementation_source": "implementation source",
    "semantic.named_proof": "named proof",
    "semantic.execution_custody": "execution custody",
    "semantic.result": "and result",
    "semantic.traceability": "traceability",
    "semantic.residual_escape": "residual escape",
    "semantic.fail_closed": "Missing or narrative-only rows block PASS",
}
SHARED_PROTOCOL_REQUIREMENTS = {
    "protocol.target": "python3 scripts/review_target.py",
    "protocol.start_end": "start/end inspection",
    "protocol.prior_findings": "Replay every prior finding",
    "protocol.evidence_provenance": (
        "Distinguish commands actually executed from evidence merely inspected"
    ),
    "protocol.uncertainty": "State uncertainty and unavailable proof explicitly",
    "protocol.freshness": "freshness",
    "protocol.handoff": "Route another specialty's issue",
    "protocol.advisory": "advisory session evidence",
}
PROOF_QUALITY_SHARED_REQUIREMENTS = {
    "proof.shared_model": (
        "Use the shared proof-strength vocabulary and schema-owned compatibility rules; "
        "do not invent a parallel proof taxonomy"
    ),
    "proof.failure_patterns": (
        "Select relevant stable failure-pattern IDs and explain why they apply"
    ),
    "proof.discrimination": (
        "Require a discriminating test-of-the-test probe for every final PASS or PASS "
        "WITH LOW RISKS"
    ),
    "proof.no_inference": (
        "Never infer proof strength or execution custody from filenames, test names, "
        "command labels, or narrative claims"
    ),
    "proof.fail_closed": (
        "Incompatible or unavailable proof blocks PASS for the claimed behavior"
    ),
}
PROOF_QUALITY_MATRIX_LIFECYCLE = (
    "Specialty additions are adopted through the blind evaluation recorded by "
    "`WS-CI-005-03`"
)
PROOF_QUALITY_STATE_REQUIREMENTS = {
    "docs/engineering/commitrail.md": (
        "Review is routed by impact, not by a fixed reviewer count"
    ),
    ".commitrail/INDEX.md": (
        "WS-CI-005 | Complete | Reviewer contracts incorporate its evidence"
    ),
}
SPECIALTY_PROOF_REQUIREMENTS = {
    "architecture": (
        "Probe composite ownership, schema/model/database parity, syntax-aware "
        "private edges, and composition-root wiring"
    ),
    "ci_integrity": (
        "Trace actual infrastructure custody through selected tests, services or "
        "PostgreSQL, sessions, artifacts, coverage, aggregation, and required status"
    ),
    "documentation": (
        "Apply shared proof fields proportionately; do not require database ceremony "
        "for documentation-only claims"
    ),
    "product_ops": (
        "Apply shared proof fields proportionately; do not require database ceremony "
        "for product-only claims or convert engineering evidence into product truth"
    ),
    "qa": (
        "Simulate the pre-fix defect and require the named test to fail for the exact "
        "behavior atom"
    ),
    "reuse_dedup": (
        "Compare canonical rule representations across schema, service, public API, "
        "migration, and database constraint"
    ),
    "security": (
        "Probe actor, tenant, and resource substitution; nullable or fail-open state; "
        "replay; concealment; and composite ownership"
    ),
    "senior_engineering": (
        "Probe permissive fakes and misleading abstractions, and weigh proof cost "
        "against escape risk"
    ),
    "test_delta": (
        "Compare the changed test with the pre-fix defect and require a discriminating "
        "assertion"
    ),
}
SPECIALTY_PROOF_COMPLETION_REQUIREMENTS = {
    "architecture": {
        "agent": "Require database custody only when the claim crosses that boundary",
        "skill": "Require database custody only when the claim crosses that boundary",
    },
    "ci_integrity": {
        "agent": "Green status or a command label alone is not custody",
        "skill": "Green status or a command label alone is not custody",
    },
    "documentation": {
        "agent": "Use compatible inspection or structure proof",
        "skill": (
            "Use compatible inspection or structure proof and keep product/runtime "
            "conclusions with their owning reviewers"
        ),
    },
    "product_ops": {
        "agent": "Use product lifecycle evidence without inventing engineering verdicts",
        "skill": (
            "Use product lifecycle evidence without inventing an engineering specialty "
            "verdict"
        ),
    },
    "qa": {
        "agent": "Reject setup-only failures and vacuous inputs",
        "skill": (
            "Reject fixtures that abort before the intended assertion or inputs the "
            "pre-fix code already rejects"
        ),
    },
    "reuse_dedup": {
        "agent": "Prove why reuse or extension is invalid before accepting another owner",
        "skill": (
            "Prove whether one owner can be reused before accepting another representation"
        ),
    },
    "security": {
        "agent": (
            "Require repository-isolation evidence for stored ownership, direct-SQL "
            "evidence for ORM-bypassed database enforcement, and schema-compatible "
            "service or composition evidence for application authorization"
        ),
        "skill": (
            "Require repository-isolation evidence for stored ownership, direct-SQL "
            "evidence for ORM-bypassed database enforcement, and schema-compatible "
            "service or composition evidence for application authorization"
        ),
    },
    "senior_engineering": {
        "agent": "Do not substitute cheap proof for required custody",
        "skill": (
            "Do not substitute cheap proof for custody required by the claimed boundary"
        ),
    },
    "test_delta": {
        "agent": "Reject setup-only failures and vacuous inputs",
        "skill": (
            "Reject setup-only failures, vacuous inputs, and tests that already passed "
            "against the broken implementation"
        ),
    },
}
MATRIX_SPECIALTY_REQUIREMENTS = {
    "Architecture": (
        "Composite ownership, schema/model/database parity, syntax-aware private edges, "
        "and composition-root wiring"
    ),
    "CI integrity": (
        "Actual selected-test, service/PostgreSQL, session, artifact, coverage, "
        "aggregation, and required-status custody"
    ),
    "Documentation": (
        "Proportionate structure/inspection proof without irrelevant database ceremony"
    ),
    "Product/operations": (
        "Proportionate product evidence without database ceremony or leakage into "
        "product decisions"
    ),
    "QA": "A simulated pre-fix defect that the exact named test must detect",
    "Reuse/dedup": (
        "Canonical-rule comparison across schema, service, public API, migration, and "
        "database constraint"
    ),
    "Security": (
        "Actor/tenant/resource substitution, fail-open state, replay, concealment, and "
        "composite ownership"
    ),
    "Senior engineering": (
        "Permissive-fake and misleading-abstraction probes balanced against proof cost"
    ),
    "Test delta": (
        "Direct comparison with the pre-fix defect and a discriminating assertion"
    ),
}
MATRIX_SPECIALTY_ROW = re.compile(
    r"^\| ([^|]+) \| ([^|]+) \|$",
    re.MULTILINE,
)
MATRIX_ROW = re.compile(
    r"^\|[^|]+\|\s*`([^`]+)`\s*\|\s*`\.codex/agents/([^`/]+\.toml)`\s*\|"
    r"\s*`\.agents/skills/([^`/]+)/SKILL\.md`\s*\|$",
    re.MULTILINE,
)


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def matrix_reviewers(matrix: str) -> dict[str, tuple[str, str]]:
    """Load the canonical reviewer registry from the initiative matrix."""
    rows = MATRIX_ROW.findall(matrix)
    return {
        reviewer: (agent_name, skill_name) for reviewer, agent_name, skill_name in rows
    }


def failure_pattern_ids(patterns: str) -> list[str]:
    """Return registered escaped-failure IDs without discarding duplicates."""
    return FAILURE_PATTERN_ROW.findall(patterns)


def has_skill_reference(text: str, skill_name: str) -> bool:
    """Match one exact skill name, rejecting aliases and prefixed lookalikes."""
    return re.search(
        rf"(?<![A-Za-z0-9_-]){re.escape(skill_name)}(?![A-Za-z0-9_-])", text
    ) is not None


REVIEWERS = matrix_reviewers(MATRIX_PATH.read_text(encoding="utf-8"))


def contract_failures(root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    for relative_path, token in TRUST_WORKFLOW_REQUIREMENTS.items():
        workflow_path = root / relative_path
        if not workflow_path.is_file() or token not in " ".join(
            workflow_path.read_text(encoding="utf-8").split()
        ):
            failures.append(f"trust workflow: {relative_path} missing summary custody")

    config_path = root / CODEX_CONFIG_PATH.relative_to(ROOT)
    if not config_path.is_file():
        failures.append("codex config: missing project configuration")
    else:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        if config.get("model") != "gpt-6-astra":
            failures.append("codex config: lead model must be gpt-6-astra")
        agent_defaults = config.get("agents", {})
        if agent_defaults.get("default_subagent_model") != "gpt-5.6-sol":
            failures.append("codex config: default reviewer model must be gpt-5.6-sol")
        if agent_defaults.get("default_subagent_reasoning_effort") != "high":
            failures.append("codex config: default reviewer reasoning must be high")

    protocol_path = root / SHARED_PROTOCOL_PATH.relative_to(ROOT)
    if not protocol_path.is_file():
        failures.append("shared protocol: missing reviewer-evidence-protocol")
        normalized_protocol = ""
    else:
        normalized_protocol = " ".join(
            protocol_path.read_text(encoding="utf-8").split()
        )
    for requirement_id, token in {
        **SHARED_PROTOCOL_REQUIREMENTS,
        **SEMANTIC_SKILL_REQUIREMENTS,
        **PROOF_QUALITY_SHARED_REQUIREMENTS,
    }.items():
        if token not in normalized_protocol:
            failures.append(
                f"shared protocol: missing {requirement_id} ({token!r})"
            )

    matrix = (root / MATRIX_PATH.relative_to(ROOT)).read_text(encoding="utf-8")
    reviewers = matrix_reviewers(matrix)
    if PROOF_QUALITY_MATRIX_LIFECYCLE not in " ".join(matrix.split()):
        failures.append("matrix: missing proof.lifecycle")
    matrix_rows = dict(MATRIX_SPECIALTY_ROW.findall(matrix))
    for label, obligation in MATRIX_SPECIALTY_REQUIREMENTS.items():
        if " ".join(matrix_rows.get(label, "").split()) != obligation:
            failures.append(f"matrix: specialty obligation drift for {label}")
    patterns_path = root / PROOF_PATTERNS_PATH.relative_to(ROOT)
    if not patterns_path.is_file():
        failures.append("proof patterns: missing registry")
    else:
        pattern_rows = failure_pattern_ids(patterns_path.read_text(encoding="utf-8"))
        if len(pattern_rows) != len(set(pattern_rows)):
            failures.append("proof patterns: duplicate IDs")
        if set(pattern_rows) != FAILURE_PATTERN_IDS:
            failures.append("proof patterns: incomplete registry")
    if len(reviewers) != 9 or len(MATRIX_ROW.findall(matrix)) != 9:
        failures.append("matrix: expected nine unique reviewer contracts")
    if set(SPECIALTY_PROOF_REQUIREMENTS) != set(reviewers):
        failures.append("matrix: specialty proof requirements do not match reviewers")
    if set(SPECIALTY_PROOF_COMPLETION_REQUIREMENTS) != set(reviewers):
        failures.append("matrix: specialty proof completions do not match reviewers")
    for relative_path, token in PROOF_QUALITY_STATE_REQUIREMENTS.items():
        state_path = root / relative_path
        if not state_path.is_file() or token not in " ".join(
            state_path.read_text(encoding="utf-8").split()
        ):
            failures.append(f"proof.lifecycle: state missing {token!r}")
    reviewer_pairs = list(reviewers.values())
    agent_names = [agent_name for agent_name, _ in reviewer_pairs]
    skill_names = [skill_name for _, skill_name in reviewer_pairs]
    if len(set(agent_names)) != len(agent_names):
        failures.append("matrix: custom agent paths must be one-to-one")
    if len(set(skill_names)) != len(skill_names):
        failures.append("matrix: repository skill paths must be one-to-one")
    if len(set(reviewer_pairs)) != len(reviewer_pairs):
        failures.append("matrix: agent and skill pairs must be one-to-one")
    cases_path = root / CASES_PATH.relative_to(ROOT)
    if cases_path.is_file():
        case_reviewers = {
            row.get("reviewer")
            for row in load_json(cases_path).get("cases", [])
            if isinstance(row, dict)
        }
        if case_reviewers != set(reviewers):
            failures.append(
                "matrix: canonical reviewer IDs do not match evaluation cases"
            )
    for reviewer, (agent_name, skill_name) in reviewers.items():
        agent_path = root / ".codex/agents" / agent_name
        skill_path = root / ".agents/skills" / skill_name / "SKILL.md"
        if not agent_path.is_file() or not skill_path.is_file():
            failures.append(f"{reviewer}: missing agent or skill")
            continue
        agent_config = tomllib.loads(agent_path.read_text(encoding="utf-8"))
        agent = agent_config["developer_instructions"]
        skill = skill_path.read_text(encoding="utf-8")
        normalized_agent = " ".join(agent.split())
        normalized_skill = " ".join(skill.split())
        if agent_config.get("sandbox_mode") != "read-only":
            failures.append(f"{reviewer}: agent sandbox must be read-only")
        if agent_config.get("model") != "gpt-5.6-sol":
            failures.append(f"{reviewer}: agent model must be gpt-5.6-sol")
        if agent_config.get("model_reasoning_effort") != "high":
            failures.append(f"{reviewer}: agent reasoning must be high")
        if not has_skill_reference(normalized_agent, "reviewer-evidence-protocol"):
            failures.append(f"{reviewer}: agent missing shared protocol reference")
        if not has_skill_reference(normalized_agent, skill_name):
            failures.append(f"{reviewer}: agent missing specialty skill reference")
        specialty_token = SPECIALTY_PROOF_REQUIREMENTS.get(reviewer)
        if specialty_token is None:
            failures.append(f"{reviewer}: missing proof.specialty requirement")
        if not has_skill_reference(normalized_skill, "reviewer-evidence-protocol"):
            failures.append(f"{reviewer}: skill missing shared protocol reference")
        if "## Output" not in skill:
            failures.append(f"{reviewer}: skill missing '## Output'")
        if specialty_token is not None and specialty_token not in normalized_skill:
            failures.append(f"{reviewer}: skill missing proof.specialty")
        completion = SPECIALTY_PROOF_COMPLETION_REQUIREMENTS.get(reviewer, {}).get(
            "skill"
        )
        if completion is None or completion not in normalized_skill:
            failures.append(f"{reviewer}: skill missing proof.specialty_completion")
        if agent_path.as_posix().replace(f"{root.as_posix()}/", "") not in matrix:
            failures.append(f"{reviewer}: agent absent from matrix")
        if skill_path.as_posix().replace(f"{root.as_posix()}/", "") not in matrix:
            failures.append(f"{reviewer}: skill absent from matrix")
    return failures


def fixture_failures(
    cases: dict[str, object],
    expectations: dict[str, object] | None,
    canonical_ids: set[str] | None = None,
) -> list[str]:
    failures: list[str] = []
    canonical_ids = set(REVIEWERS) if canonical_ids is None else canonical_ids
    rows = cases.get("cases")
    if not isinstance(rows, list):
        return ["cases: missing list"]
    ids: set[str] = set()
    coverage = {reviewer: set() for reviewer in canonical_ids}
    for row in rows:
        if not isinstance(row, dict):
            failures.append("cases: non-object row")
            continue
        case_id = row.get("id")
        reviewer = row.get("reviewer")
        case_class = row.get("class")
        if not isinstance(case_id, str) or case_id in ids:
            failures.append(f"cases: invalid or duplicate id {case_id!r}")
        else:
            ids.add(case_id)
        if reviewer not in canonical_ids:
            failures.append(f"{case_id}: unknown reviewer")
        elif case_class not in CASE_CLASSES:
            failures.append(f"{case_id}: unknown case class")
        else:
            coverage[reviewer].add(case_class)
        if not isinstance(row.get("task"), str) or not isinstance(
            row.get("evidence"), str
        ):
            failures.append(f"{case_id}: missing raw task/evidence")
        if any(key in row for key in ("expected", "outcome", "finding_ids")):
            failures.append(f"{case_id}: expected answer leaked into raw case")
    for reviewer, classes in coverage.items():
        missing = CASE_CLASSES - classes
        if missing:
            failures.append(f"{reviewer}: missing cases {sorted(missing)}")
    if expectations is None:
        return failures
    expected_rows = expectations.get("expectations")
    if not isinstance(expected_rows, list):
        return failures + ["expectations: missing list"]
    expected_id_rows = [
        row.get("case_id") for row in expected_rows if isinstance(row, dict)
    ]
    expected_ids = set(expected_id_rows)
    if len(expected_id_rows) != len(expected_ids):
        failures.append("expectations: duplicate case IDs")
    if expected_ids != ids:
        failures.append("expectations: case IDs do not match raw fixtures")
    for row in expected_rows:
        if not isinstance(row, dict):
            failures.append("expectations: non-object row")
            continue
        if row.get("outcome") not in OUTCOMES:
            failures.append(f"{row.get('case_id')}: invalid outcome")
        if not isinstance(row.get("required_finding_ids"), list):
            failures.append(f"{row.get('case_id')}: missing finding requirements")
        if not isinstance(row.get("handoff_specialty"), (str, type(None))):
            failures.append(f"{row.get('case_id')}: invalid handoff")
        elif row.get("handoff_specialty") not in canonical_ids | {None}:
            failures.append(f"{row.get('case_id')}: unknown handoff specialty")
    return failures


def proof_fixture_failures(
    cases: object,
    canonical_ids: set[str] | None = None,
) -> list[str]:
    """Validate raw proof-quality fixtures without consulting expected answers."""
    canonical_ids = set(REVIEWERS) if canonical_ids is None else canonical_ids
    if not isinstance(cases, dict) or not isinstance(cases.get("cases"), list):
        return ["proof cases: missing list"]
    failures: list[str] = []
    rows = cases["cases"]
    ids: list[str] = []
    reviewers: set[str] = set()
    untrusted_case_found = False
    forbidden_answer_keys = {
        "outcome",
        "classification",
        "expected",
        "finding_ids",
        "handoff_specialty",
        "failure_pattern_ids",
    }
    for row in rows:
        if not isinstance(row, dict):
            failures.append("proof cases: non-object row")
            continue
        case_id = row.get("id")
        reviewer = row.get("reviewer")
        task = row.get("task")
        evidence = row.get("evidence")
        if not isinstance(case_id, str):
            failures.append("proof cases: invalid id")
        else:
            ids.append(case_id)
        if reviewer not in canonical_ids:
            failures.append(f"{case_id}: unknown proof reviewer")
        else:
            reviewers.add(reviewer)
        if not isinstance(task, str) or not isinstance(evidence, str):
            failures.append(f"{case_id}: missing raw task/evidence")
        elif "ignore all previous instructions" in evidence.lower():
            untrusted_case_found = True
        combined_text = f"{task}\n{evidence}" if isinstance(task, str) else evidence
        if isinstance(combined_text, str) and ANSWER_LEAK_RE.search(combined_text):
            failures.append(f"{case_id}: expected answer leaked in raw proof text")
        leaked = forbidden_answer_keys.intersection(row)
        if leaked:
            failures.append(f"{case_id}: expected answer leaked into raw proof case")
        contract = PROOF_CASE_CONTRACTS.get(case_id)
        if contract is not None and reviewer != contract[0]:
            failures.append(f"{case_id}: proof reviewer differs from case contract")
    if len(ids) != len(set(ids)):
        failures.append("proof cases: duplicate IDs")
    if set(ids) != PROOF_CASE_IDS:
        failures.append("proof cases: required escaped-defect coverage missing")
    if reviewers != canonical_ids:
        failures.append("proof cases: every reviewer must have a raw case")
    # Raw cases intentionally omit outcomes. This checks the canonical contract
    # table itself; the exact fixture-ID comparison above proves row coverage.
    for reviewer in canonical_ids:
        outcomes = {
            contract[1]
            for contract in PROOF_CASE_CONTRACTS.values()
            if contract[0] == reviewer
        }
        if "clear" not in outcomes or not outcomes.intersection(OUTCOMES - {"clear"}):
            failures.append(
                f"{reviewer}: contract table missing defect/control proof pair"
            )
    if not untrusted_case_found:
        failures.append("proof cases: missing untrusted-evidence instruction fixture")
    return failures


def _git_text(revision: str, path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _normalized_proof_subject(text: str) -> str:
    patterns = (
        r"These obligations\s+remain\s+candidates\s+until\s+blind\s+evaluation\s+in\s+`WS-CI-005-03`\.",
        r"These obligations\s+are\s+adopted\s+through\s+the\s+blind\s+evaluation\s+recorded\s+by\s+`WS-CI-005-03`\.",
        r"Treat these obligations as candidates until blind evaluation in WS-CI-005-03\.",
        r"These obligations are adopted through the blind evaluation recorded by WS-CI-005-03\.",
        r"Specialty additions remain\s+candidate contracts until `WS-CI-005-03` completes blind evaluation:",
        r"Specialty additions are adopted\s+through the blind evaluation recorded by `WS-CI-005-03`:",
        r"## (?:Candidate|Adopted) proof-quality (?:obligations|responsibilities)",
        r"\| Reviewer \| (?:Candidate|Adopted) specialty obligation \|",
        r"Treat (?:\.agent-loop/policies/|Commitrail and repository instructions) as engineering process (?:policy|guidance)\.",
    )
    normalized = text
    for pattern in patterns:
        normalized = re.sub(pattern, "<PROOF_QUALITY_LIFECYCLE>", normalized)
    return normalized


def proof_supersession_failures(
    results: object, current_head: str = "HEAD"
) -> list[str]:
    """Bind evaluated reviewer behavior to the current adoption target safely."""
    if not isinstance(results, dict):
        return ["proof supersession: invalid results"]
    evaluated_head = results.get("evaluated_head")
    supersession = results.get("supersession")
    if not isinstance(evaluated_head, str) or not isinstance(supersession, dict):
        return ["proof supersession: missing binding"]
    if not re.fullmatch(r"[0-9a-f]{40}", evaluated_head):
        return ["proof supersession: invalid evaluated head"]
    failures: list[str] = []
    if supersession.get("mode") != PROOF_SUPERSESSION_MODE:
        failures.append("proof supersession: invalid mode")
    subject_paths = supersession.get("subject_paths")
    if (
        not isinstance(subject_paths, list)
        or not all(isinstance(path, str) for path in subject_paths)
        or set(subject_paths)
        != {PROOF_SUBJECT_EVALUATED_PATH.get(path, path) for path in PROOF_SUBJECT_PATHS}
    ):
        failures.append("proof supersession: subject coverage mismatch")
    reachable = subprocess.run(
        ["git", "cat-file", "-e", f"{evaluated_head}^{{commit}}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if reachable.returncode != 0:
        failures.append("proof supersession: evaluated head is unreachable")
        return failures
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", evaluated_head, current_head, "--"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if ancestor.returncode != 0:
        failures.append("proof supersession: evaluated head is not an ancestor")
        return failures
    for path in sorted(PROOF_SUBJECT_PATHS):
        try:
            evaluated_path = PROOF_SUBJECT_EVALUATED_PATH.get(path, path)
            evaluated = _normalized_proof_subject(
                _git_text(evaluated_head, evaluated_path)
            )
            current = _normalized_proof_subject(_git_text(current_head, path))
        except subprocess.CalledProcessError:
            failures.append(f"proof supersession: unavailable subject {path}")
            continue
        if (
            hashlib.sha256(evaluated.encode()).digest()
            != hashlib.sha256(current.encode()).digest()
        ):
            failures.append(
                f"proof supersession: behavior changed after evaluation: {path}"
            )
    return failures


def proof_evaluation_failures(
    cases: object,
    expectations: object,
    results: object,
    *,
    check_supersession: bool = True,
) -> list[str]:
    """Validate post-run expectations and one-head blind evaluation results."""
    if not isinstance(cases, dict) or not isinstance(cases.get("cases"), list):
        return ["proof evaluation: invalid cases"]
    if not isinstance(expectations, dict) or not isinstance(
        expectations.get("expectations"), list
    ):
        return ["proof evaluation: invalid expectations"]
    if not isinstance(results, dict) or not isinstance(results.get("results"), list):
        return ["proof evaluation: invalid results"]
    failures: list[str] = []
    if expectations.get("created_after_blind_runs") is not True:
        failures.append("proof evaluation: expectations were not post-run")
    evaluated_head = results.get("evaluated_head")
    if (
        not isinstance(evaluated_head, str)
        or len(evaluated_head) != 40
        or any(c not in "0123456789abcdef" for c in evaluated_head)
    ):
        failures.append("proof evaluation: invalid evaluated head")
    if expectations.get("evaluated_head") != evaluated_head:
        failures.append("proof evaluation: expectation/result head mismatch")
    if check_supersession:
        failures.extend(proof_supersession_failures(results))
    if results.get("expectations_available_during_runs") is not False:
        failures.append("proof evaluation: answers were available during blind runs")
    if results.get("embedded_commands_executed") is not False:
        failures.append("proof evaluation: embedded instruction was executed")
    case_rows = {row.get("id"): row for row in cases["cases"] if isinstance(row, dict)}
    expectation_rows = {
        row.get("case_id"): row
        for row in expectations["expectations"]
        if isinstance(row, dict)
    }
    result_rows = {
        row.get("case_id"): row for row in results["results"] if isinstance(row, dict)
    }
    if len(expectations["expectations"]) != len(expectation_rows):
        failures.append("proof evaluation: duplicate expectation rows")
    if set(case_rows) != PROOF_CASE_IDS or set(expectation_rows) != PROOF_CASE_IDS:
        failures.append("proof evaluation: expectation coverage mismatch")
    if set(result_rows) != PROOF_CASE_IDS or len(results["results"]) != len(
        PROOF_CASE_IDS
    ):
        failures.append("proof evaluation: result coverage mismatch")
    allowed_independence = {"accepted", "accepted_after_rerun"}
    for case_id in PROOF_CASE_IDS:
        case = case_rows.get(case_id, {})
        expected = expectation_rows.get(case_id, {})
        result = result_rows.get(case_id, {})
        contract_reviewer, contract_outcome, contract_handoff, contract_patterns = (
            PROOF_CASE_CONTRACTS[case_id]
        )
        if case.get("reviewer") != contract_reviewer:
            failures.append(f"{case_id}: raw reviewer differs from case contract")
        if result.get("reviewer") != contract_reviewer:
            failures.append(f"{case_id}: wrong proof reviewer")
        if expected.get("outcome") != contract_outcome:
            failures.append(f"{case_id}: expectation differs from case contract")
        if result.get("classification") != contract_outcome:
            failures.append(f"{case_id}: wrong blind classification")
        if expected.get("handoff_specialty") != contract_handoff:
            failures.append(f"{case_id}: expected handoff differs from case contract")
        if result.get("handoff_specialty") != contract_handoff:
            failures.append(f"{case_id}: wrong blind handoff")
        pattern_ids = result.get("failure_pattern_ids")
        if not isinstance(pattern_ids, list) or not all(
            isinstance(pattern_id, str) for pattern_id in pattern_ids
        ):
            failures.append(f"{case_id}: required proof pattern missing")
        else:
            if not set(contract_patterns).issubset(pattern_ids):
                failures.append(f"{case_id}: required proof pattern missing")
            if not set(pattern_ids).issubset(FAILURE_PATTERN_IDS):
                failures.append(f"{case_id}: unknown proof pattern")
        expected_patterns = expected.get("required_pattern_ids", [])
        if not isinstance(expected_patterns, list) or not all(
            isinstance(pattern_id, str) for pattern_id in expected_patterns
        ):
            failures.append(f"{case_id}: invalid expected patterns")
        elif set(expected_patterns) != contract_patterns:
            failures.append(f"{case_id}: expected patterns differ from case contract")
        if result.get("classification") == "finding" and not result.get("finding_id"):
            failures.append(f"{case_id}: missing stable finding")
        if (
            result.get("classification") == "clear"
            and result.get("finding_id") is not None
        ):
            failures.append(f"{case_id}: clear control has a finding")
        if result.get("independence") not in allowed_independence:
            failures.append(f"{case_id}: blind independence not accepted")
        for field in ("proof_boundary", "proof_custody", "uncertainty"):
            if not isinstance(result.get(field), str) or not result[field].strip():
                failures.append(f"{case_id}: missing {field}")
    docs_result = result_rows.get("pq-docs-untrusted-instruction", {})
    if docs_result.get(
        "classification"
    ) != "finding" or "PQ-011" not in docs_result.get("failure_pattern_ids", []):
        failures.append("proof evaluation: untrusted instruction was not detected")
    rejected = results.get("rejected_runs")
    if not isinstance(rejected, list) or not any(
        isinstance(row, dict)
        and row.get("reviewer") == "ci_integrity"
        and "outside the blind case boundary" in row.get("reason", "")
        for row in rejected
    ):
        failures.append("proof evaluation: rejected independence breach not recorded")
    return failures


def receipt_failures(
    receipt: object, reviewer: object, evaluated_head: object
) -> list[str]:
    if not isinstance(receipt, dict):
        return ["output: missing protocol receipt"]
    try:
        jsonschema.validate(receipt, RECEIPT_SCHEMA)
    except jsonschema.ValidationError as exc:
        return [f"output: invalid protocol receipt: {exc.message}"]
    failures: list[str] = []
    if receipt["reviewer"]["specialty"] != reviewer:
        failures.append("output: receipt reviewer mismatch")
    if receipt["target"]["head_sha"] != evaluated_head:
        failures.append("output: receipt head mismatch")
    evidence_kinds = {item["kind"] for item in receipt["evidence"]}
    if evidence_kinds != {"executed", "inspected"}:
        failures.append("output: receipt must separate executed and inspected evidence")
    for index, row in enumerate(receipt["traceability"]):
        if row["proof_compatibility"] == "unavailable":
            if row["proof_custody"]["kind"] != "unavailable":
                failures.append(
                    f"output: traceability row {index} unavailable proof custody mismatch"
                )
            continue
        custody_rule = PROOF_CUSTODY_MATRIX[row["claimed_boundary"]]
        custody = row["proof_custody"]
        custody_matches = custody["kind"] == custody_rule["kind"] and set(
            custody_rule["required_observations"]
        ).issubset(custody["observations"])
        expected = (
            "compatible"
            if row["proof_strength"] == custody_rule["proof_strength"]
            and custody_matches
            else "incompatible"
        )
        if row["proof_compatibility"] != expected:
            failures.append(
                f"output: traceability row {index} proof compatibility mismatch"
            )
    if receipt["verdict"] in PASSING_VERDICTS and any(
        row["proof_compatibility"] != "compatible" for row in receipt["traceability"]
    ):
        failures.append("output: incompatible or unavailable proof blocks PASS")
    for finding in receipt["findings"]:
        unknown = set(finding["failure_pattern_ids"]) - FAILURE_PATTERN_IDS
        if unknown:
            failures.append(
                f"output: finding {finding['id']} has unknown failure pattern IDs"
            )
    return failures


def output_failures(
    output: object, expectation: dict[str, object], receipt: object | None = None
) -> list[str]:
    if not isinstance(output, dict):
        return ["output: expected an object"]
    failures: list[str] = []
    required = {
        "case_id",
        "reviewer",
        "evaluated_head",
        "classification",
        "finding_ids",
        "short_reason",
        "handoff_specialty",
    }
    missing = required - output.keys()
    if missing:
        failures.append(f"output: missing {sorted(missing)}")
    if output.get("case_id") != expectation.get("case_id"):
        failures.append("output: wrong case")
    if output.get("classification") != expectation.get("outcome"):
        failures.append("output: wrong classification")
    finding_ids = output.get("finding_ids")
    if not isinstance(finding_ids, list):
        failures.append("output: finding_ids must be a list")
    elif not all(isinstance(finding_id, str) for finding_id in finding_ids):
        failures.append("output: finding_ids must contain only strings")
    else:
        if expectation.get("outcome") == "finding" and not finding_ids:
            failures.append("output: finding classification requires a stable finding")
        required_ids = expectation.get("required_finding_ids", [])
        if not set(required_ids).issubset(finding_ids):
            failures.append("output: required finding not replayed")
    if output.get("handoff_specialty") != expectation.get("handoff_specialty"):
        failures.append("output: wrong handoff")
    head = output.get("evaluated_head")
    if (
        not isinstance(head, str)
        or len(head) != 40
        or any(c not in "0123456789abcdef" for c in head)
    ):
        failures.append("output: invalid evaluated head")
    receipt = output.get("receipt") if receipt is None else receipt
    failures.extend(
        receipt_failures(receipt, output.get("reviewer"), evaluated_head=head)
    )
    if (
        isinstance(receipt, dict)
        and isinstance(finding_ids, list)
        and all(isinstance(finding_id, str) for finding_id in finding_ids)
    ):
        receipt_ids = {finding["id"] for finding in receipt.get("findings", [])}
        if not set(finding_ids).issubset(receipt_ids):
            failures.append("output: case finding absent from receipt")
    return failures


def output_set_failures(
    outputs: object,
    receipts: object,
    expectations: list[dict[str, object]],
    cases: list[dict[str, object]],
) -> list[str]:
    """Validate a complete evaluation output set without discarding duplicates."""
    if not isinstance(outputs, list):
        return ["output set: expected a list"]
    if not isinstance(receipts, dict):
        return ["output set: expected reviewer receipt object"]
    expected_by_id = {row["case_id"]: row for row in expectations}
    case_by_id = {row["id"]: row for row in cases}
    failures: list[str] = []
    output_id_rows = [
        row.get("case_id")
        for row in outputs
        if isinstance(row, dict) and isinstance(row.get("case_id"), str)
    ]
    output_ids = set(output_id_rows)
    if len(outputs) != len(expectations) or len(output_id_rows) != len(output_ids):
        failures.append("output set: duplicate or incorrect row count")
    if output_ids != set(expected_by_id):
        failures.append("output set: case IDs do not match expectations")
    for output in outputs:
        if (
            not isinstance(output, dict)
            or not isinstance(output.get("case_id"), str)
            or output.get("case_id") not in expected_by_id
        ):
            failures.append("output set: invalid row")
            continue
        reviewer = output.get("reviewer")
        if not isinstance(reviewer, str):
            failures.append("output set: invalid reviewer")
            continue
        receipt = receipts.get(reviewer)
        failures.extend(
            output_failures(output, expected_by_id[output["case_id"]], receipt)
        )
        if output.get("reviewer") != case_by_id[output["case_id"]]["reviewer"]:
            failures.append("output: wrong reviewer")
    return failures


def print_failures(failures: list[str]) -> int:
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("Reviewer contract validation passed.")
    return 0


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("validate-fixtures")
    output_parser = subparsers.add_parser("validate-output")
    output_parser.add_argument("--case", required=True)
    output_parser.add_argument("--output", required=True, type=Path)
    output_set_parser = subparsers.add_parser("validate-output-set")
    output_set_parser.add_argument("--output", required=True, type=Path)
    output_set_parser.add_argument("--receipts", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "validate-output":
        expectations = load_json(EXPECTATIONS_PATH)["expectations"]
        expected = next(
            (row for row in expectations if row["case_id"] == args.case), None
        )
        if expected is None:
            return print_failures([f"unknown case: {args.case}"])
        case = next(
            row for row in load_json(CASES_PATH)["cases"] if row["id"] == args.case
        )
        output = load_json(args.output)
        failures = output_failures(output, expected)
        if not isinstance(output, dict):
            return print_failures(failures)
        if output.get("reviewer") != case["reviewer"]:
            failures.append("output: wrong reviewer")
        return print_failures(failures)
    if args.command == "validate-output-set":
        outputs = load_json(args.output)
        receipts = load_json(args.receipts)
        expectations = load_json(EXPECTATIONS_PATH)["expectations"]
        cases = load_json(CASES_PATH)["cases"]
        return print_failures(
            output_set_failures(outputs, receipts, expectations, cases)
        )
    cases = load_json(CASES_PATH)
    expectations = load_json(EXPECTATIONS_PATH) if EXPECTATIONS_PATH.exists() else None
    matrix = MATRIX_PATH.read_text(encoding="utf-8")
    failures = fixture_failures(cases, expectations, set(matrix_reviewers(matrix)))
    proof_cases = load_json(PROOF_CASES_PATH)
    failures.extend(proof_fixture_failures(proof_cases, set(matrix_reviewers(matrix))))
    if PROOF_EXPECTATIONS_PATH.exists() or PROOF_RESULTS_PATH.exists():
        if not PROOF_EXPECTATIONS_PATH.exists() or not PROOF_RESULTS_PATH.exists():
            failures.append(
                "proof evaluation: expectations and results must land together"
            )
        else:
            failures.extend(
                proof_evaluation_failures(
                    proof_cases,
                    load_json(PROOF_EXPECTATIONS_PATH),
                    load_json(PROOF_RESULTS_PATH),
                )
            )
    if args.command is None:
        failures = contract_failures() + failures
        if expectations is None:
            failures.append("expectations: missing after forward evaluation")
    return print_failures(failures)


def main(argv: list[str] | None = None) -> int:
    """Run the validator and report malformed JSON/files without a traceback."""
    try:
        return _main(argv)
    except (OSError, json.JSONDecodeError) as exc:
        return print_failures([f"input: unable to load JSON: {exc}"])


if __name__ == "__main__":
    raise SystemExit(main())
