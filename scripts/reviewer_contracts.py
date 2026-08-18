#!/usr/bin/env python3
"""Validate reviewer adoption contracts and isolated evaluation output."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
INITIATIVE = ROOT / ".agent-loop/initiatives/WS-CI-004-review-evidence-integrity"
CASES_PATH = INITIATIVE / "evaluations/CASES.json"
EXPECTATIONS_PATH = INITIATIVE / "evaluations/EXPECTATIONS.json"
MATRIX_PATH = INITIATIVE / "REVIEWER_MATRIX.md"
RECEIPT_SCHEMA_PATH = ROOT / ".agent-loop/templates/INTERNAL_REVIEW_RECEIPT.schema.json"
PROOF_PATTERNS_PATH = (
    ROOT
    / ".agents/skills/reviewer-evidence-protocol/references/proof-quality-patterns.md"
)
CASE_CLASSES = {"positive", "negative", "stale_replay", "output_contract", "handoff"}
OUTCOMES = {"finding", "clear", "replayed", "provisional", "handoff"}
RECEIPT_SCHEMA = json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))
PROOF_STRENGTHS = set(RECEIPT_SCHEMA["$defs"]["proof_strength"]["enum"])
PROOF_CUSTODY_MATRIX = RECEIPT_SCHEMA["x-proof-custody-matrix"]
PASSING_VERDICTS = {"PASS", "PASS AFTER FIXES", "PASS WITH LOW RISKS"}
FAILURE_PATTERN_IDS = {f"PQ-{number:03d}" for number in range(1, 14)}
FAILURE_PATTERN_ROW = re.compile(r"^\| `(PQ-[0-9]{3})` \|", re.MULTILINE)
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
SEMANTIC_AGENT_REQUIREMENTS = {
    **SEMANTIC_SKILL_REQUIREMENTS,
    "semantic.atomization": "Atomize material criteria",
    "semantic.ownership": "to owner",
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
        "Require a discriminating test-of-the-test probe for every final PASS"
    ),
    "proof.no_inference": (
        "Never infer proof strength or execution custody from filenames, test names, "
        "command labels, or narrative claims"
    ),
    "proof.fail_closed": (
        "Incompatible or unavailable proof blocks PASS for the claimed behavior"
    ),
}
PROOF_QUALITY_AGENT_LIFECYCLE = (
    "Treat these obligations as candidates until blind evaluation in WS-CI-005-03"
)
PROOF_QUALITY_SKILL_LIFECYCLE = (
    "These obligations remain candidates until blind evaluation in `WS-CI-005-03`"
)
PROOF_QUALITY_MATRIX_LIFECYCLE = (
    "Specialty additions remain candidate contracts until `WS-CI-005-03` completes "
    "blind evaluation"
)
PROOF_QUALITY_STATE_REQUIREMENTS = {
    ".agent-loop/CURRENT_STATE.md": "behavioral adoption remains unclaimed",
    ".agent-loop/initiatives/WS-CI-005-semantic-proof-quality/STATUS.md": (
        "remain unadopted until blind forward evaluation passes"
    ),
    ".agent-loop/initiatives/WS-CI-005-semantic-proof-quality/CHUNK_MAP.md": (
        "candidate contracts installed, adoption unclaimed"
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
            "Use real repository or direct-SQL custody when the claim depends on database "
            "enforcement"
        ),
        "skill": (
            "Use real repository or direct-SQL custody when the claim depends on stored "
            "ownership or database enforcement"
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


REVIEWERS = matrix_reviewers(MATRIX_PATH.read_text(encoding="utf-8"))


def contract_failures(root: Path = ROOT) -> list[str]:
    failures: list[str] = []
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
        agent = tomllib.loads(agent_path.read_text(encoding="utf-8"))[
            "developer_instructions"
        ]
        skill = skill_path.read_text(encoding="utf-8")
        normalized_agent = " ".join(agent.split())
        normalized_skill = " ".join(skill.split())
        for token in (
            "reviewer-evidence-protocol",
            skill_name,
            "scripts/review_target.py",
            "start and end",
            "prior finding",
            "executed from inspected",
            "uncertainty",
            "freshness",
            "hand off",
            "python3 scripts/review_target.py",
            "Atomize material criteria",
            "traceability",
            "residual escape hypothesis",
            "Missing or narrative-only rows block PASS",
        ):
            if token not in normalized_agent:
                failures.append(f"{reviewer}: agent missing {token!r}")
        for requirement_id, token in SEMANTIC_AGENT_REQUIREMENTS.items():
            if token not in normalized_agent:
                failures.append(
                    f"{reviewer}: agent missing {requirement_id} ({token!r})"
                )
        for requirement_id, token in PROOF_QUALITY_SHARED_REQUIREMENTS.items():
            if token not in normalized_agent:
                failures.append(
                    f"{reviewer}: agent missing {requirement_id} ({token!r})"
                )
        if PROOF_QUALITY_AGENT_LIFECYCLE not in normalized_agent:
            failures.append(f"{reviewer}: agent missing proof.lifecycle")
        specialty_token = SPECIALTY_PROOF_REQUIREMENTS.get(reviewer)
        if specialty_token is None:
            failures.append(f"{reviewer}: missing proof.specialty requirement")
        elif specialty_token not in normalized_agent:
            failures.append(f"{reviewer}: agent missing proof.specialty")
        completion = SPECIALTY_PROOF_COMPLETION_REQUIREMENTS.get(reviewer, {}).get(
            "agent"
        )
        if completion is None or completion not in normalized_agent:
            failures.append(f"{reviewer}: agent missing proof.specialty_completion")
        for token in (
            "reviewer-evidence-protocol",
            "exact target",
            "prior findings",
            "executed from inspected",
            "uncertainty",
            "freshness",
            "hand off",
            "Medium",
            "Low/Informational",
            "Protocol envelope",
        ):
            if token not in normalized_skill:
                failures.append(f"{reviewer}: skill missing {token!r}")
        for requirement_id, token in SEMANTIC_SKILL_REQUIREMENTS.items():
            if token not in normalized_skill:
                failures.append(
                    f"{reviewer}: skill missing {requirement_id} ({token!r})"
                )
        for requirement_id, token in PROOF_QUALITY_SHARED_REQUIREMENTS.items():
            if token not in normalized_skill:
                failures.append(
                    f"{reviewer}: skill missing {requirement_id} ({token!r})"
                )
        if PROOF_QUALITY_SKILL_LIFECYCLE not in normalized_skill:
            failures.append(f"{reviewer}: skill missing proof.lifecycle")
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
