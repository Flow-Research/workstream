#!/usr/bin/env python3
"""Reject obsolete authorization claims in active Workstream documentation."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_SUFFIXES = {".html", ".json", ".md", ".puml"}

# Exact reviewed history/archive paths. New files are active unless added here
# with an explicit rationale through normal review.
HISTORICAL_PATHS = {
    ".agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-06-canonical-actor-profile.md": "merged transitional implementation contract",
    ".agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-11-actor-identity-profile-registry.md": "merged transitional implementation contract",
    "docs/checker_trial_failure_catalog.md": "closed checker-trial evidence",
    "docs/internal_reviews/2026-06-11_chunk9_pre_review_gate.md": "closed internal review",
    "docs/internal_reviews/2026-06-11_revision_context_rebase.md": "closed internal review",
    "docs/internal_reviews/2026-06-12_chunk10_checker_trial.md": "closed internal review",
    "docs/internal_reviews/2026-06-12_week2_closeout_real_api_drill.md": "closed internal review",
    "docs/internal_reviews/2026-06-13_week1_week2_deterministic_hardening.md": "closed internal review",
    "docs/internal_reviews/2026-06-16_submission_artifact_policy_architecture.md": "closed internal review",
    "docs/reference_specs/WS-AUTH-001-actor-profile-role-and-authorization-service-specification.md": "immutable archival input",
    "docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification.md": "immutable archival input",
    "docs/reference_specs/WS-IMP-001-workstream-v0.1-coding-agent-implementation-specification.md": "immutable archival input",
    "docs/reference_specs/WS-REV-001-review-lifecycle-specification.md": "immutable archival input",
    "docs/roadmap_30_day_master_plan.md": "historical initial plan",
    "docs/roadmap_day_by_day_execution_plan.md": "historical execution plan",
    "docs/roadmap_pilot_plan.md": "historical pilot plan",
    "docs/roadmap_week1_backend_plan.md": "historical Week 1 plan",
    "docs/spec_chunk_1_backend_scaffold.md": "historical implemented chunk",
    "docs/spec_chunk_3_project_guide_foundation.md": "historical implemented chunk",
    "docs/spec_chunk_4_task_queue_assignment.md": "historical implemented chunk",
    "docs/spec_chunk_5_submission_packet_foundation.md": "historical implemented chunk",
    "docs/spec_chunk_6_checker_contract_records.md": "historical implemented chunk",
    "docs/spec_chunk_7_checker_runner_registry.md": "historical implemented chunk",
    "docs/spec_chunk_8_submission_artifact_policy_checkers.md": "historical implemented chunk",
    "docs/spec_chunk_9_pre_review_gate.md": "historical implemented chunk",
    "docs/spec_chunk_10_checker_trial.md": "historical implemented chunk",
    "docs/spec_week2_checker_framework.md": "historical implemented plan",
}


@dataclass(frozen=True)
class Rule:
    """One forbidden active-document pattern."""

    code: str
    pattern: re.Pattern[str]


RULES = (
    Rule("NON_CANONICAL_API_PREFIX", re.compile(r"(?<!/api)/v1(?:/|\b)")),
    Rule(
        "LEGACY_ADMIN_PROJECT_MANAGER_AUTHORITY",
        re.compile(r"`?admin`?\s*(?:/|or)\s*`?project_manager`?", re.IGNORECASE),
    ),
    Rule("LEGACY_ROLE_HELPER", re.compile(r"require_any_role", re.IGNORECASE)),
    Rule(
        "TRUSTED_ROLE_CLAIM_AUTHORITY",
        re.compile(r"trusted role claims", re.IGNORECASE),
    ),
    Rule(
        "CURRENT_TOKEN_ROLE_AUTHORITY",
        re.compile(r"role in the current verified token", re.IGNORECASE),
    ),
    Rule(
        "TOKEN_CARRIES_PRODUCT_ROLE",
        re.compile(r"token also carries an authorized Workstream role", re.IGNORECASE),
    ),
    Rule(
        "TYPED_PROFILE_AUTHORITY",
        re.compile(r"ActorProfile\s*\(\s*profile_type", re.IGNORECASE),
    ),
    Rule(
        "OBSOLETE_ROLE_ASSIGNMENT_MODEL",
        re.compile(r"WorkstreamRoleAssignment", re.IGNORECASE),
    ),
    Rule(
        "OPERATOR_NOT_A_ROLE",
        re.compile(
            r"Operator.{0,80}not a separate.{0,40}permission role", re.IGNORECASE
        ),
    ),
    Rule(
        "BROAD_ADMIN_OVERRIDE",
        re.compile(r"\badmin\s+(?:can|may|must)\s+override", re.IGNORECASE),
    ),
    Rule(
        "LEGACY_ADMIN_HEADING",
        re.compile(r"^#{2,4}\s+Admin\s*$", re.IGNORECASE | re.MULTILINE),
    ),
    Rule(
        "LEGACY_ROLE_MATRIX",
        re.compile(r"\|\s*Admin\s*\|.*\|\s*(?:Finance|Auditor)\s*\|", re.IGNORECASE),
    ),
    Rule(
        "ROLE_NAME_APPROVAL_PROVENANCE",
        re.compile(r"approved_by_role.{0,40}project_manager", re.IGNORECASE),
    ),
    Rule(
        "GENERIC_ADMIN_PRODUCT_AUTHORITY",
        re.compile(
            r"\badmin\s+(?:can|may|must|is allowed to)\s+"
            r"(?:create|approve|activate|manage|claim|review|submit|grant|revoke|read|update|delete)\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "TOKEN_ROLE_PRODUCT_AUTHORITY",
        re.compile(
            r"(?:token\s+roles?|roles?\s+(?:from|in)\s+(?:the\s+)?"
            r"(?:(?:current|verified|bearer)\s+)*token).{0,100}?"
            r"\b(?:grants?|authoriz(?:e[sd]?|ation)|permits?|allows?|approv(?:e[sd]?|al))\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "NAMED_ROLE_TOKEN_AUTHORITY",
        re.compile(
            r"\b(?:admin|project_manager|worker|reviewer|operator)\b.{0,24}?\btoken\b.{0,80}?"
            r"\b(?:can|may|must|grants?|authoriz(?:e[sd]?|ation)|permits?|allows?|approv(?:e[sd]?|al))\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "TYPED_PROFILE_PRODUCT_AUTHORITY",
        re.compile(
            r"ActorProfile.{0,60}?\b(?:profile_type|type)\b.{0,80}?"
            r"\b(?:grants?|authoriz(?:e[sd]?|ation)|permits?|allows?|approv(?:e[sd]?|al))\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "HUMAN_WORKER_VOCABULARY",
        re.compile(r"\bworkers?\b", re.IGNORECASE),
    ),
    Rule(
        "HUMAN_WORKER_IDENTIFIER",
        re.compile(
            r"\bworker_(?:id|attestation|message|suggested_fix|evidence_refs|"
            r"visible|claim_status|profile)\b|/api/v1/workers(?:/|\b)",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "TECHNICAL_WORKER_HUMAN_AUTHORITY",
        re.compile(
            r"\b(?:celery|checker|setup|system|background|reconciliation)\s+"
            r"workers?\b.{0,120}\b(?:"
            r"(?:is|acts?\s+as|becomes?)\s+(?:a\s+)?(?:contributor|human\s+"
            r"product\s+role)|"
            r"(?:has|receives|uses|holds|is\s+assigned)\s+(?:a\s+)?(?:submitter|"
            r"reviewer|both|contributor|human\s+administrative)\s+(?:grant|"
            r"authority|role)|"
            r"(?:claims?|submits?|reviews?|approves?)\b.{0,60}\b(?:task|packet|"
            r"submission|review\s+decision|project(?:\s+guide|\s+work)?)\b|"
            r"grants?\s+itself\s+project\s+access|"
            r"manages?\s+contributor\s+grants?|"
            r"creates?\s+(?:a\s+)?project|"
            r"(?:records?|creates?|issues?)\s+(?:a\s+)?review\s+decision|"
            r"(?:issues?|creates?|grants?|revokes?|approves?|manages?)\s+"
            r"(?:a\s+)?(?:submitter|reviewer|both|contributor)\s+grant|"
            r"(?:accepts?|rejects?)\s+(?:a\s+|the\s+)?(?:submission|task|"
            r"project\s+work)|"
            r"requests?\s+(?:a\s+)?(?:revision|needs_revision))\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "ACCESS_ADMIN_CATALOG_ADMINISTRATION",
        re.compile(
            r"\b(?:Access Administrator|access_administrator)\b[^.\n]{0,200}(?:"
            r"\b(?:manage(?:s|d|ment)?|administer(?:s|ed)?|administration|"
            r"own(?:s|ership))\b[^.\n]{0,100}\b(?:permission|action)[\s/-]+"
            r"catalog(?:ue)?\b|"
            r"\b(?:permission|action)[\s/-]+catalog(?:ue)?\b[^.\n]{0,100}"
            r"\b(?:management|administration|ownership)\b)",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "OPERATOR_CONTRIBUTION_POLICY_AUTHORITY",
        re.compile(
            r"(?:\bOperator\b.{0,180}\b(?:publish(?:es|ed)?|approve(?:s|d)?|"
            r"bind(?:s|ing)?|manage(?:s|d|ment)?|mutate(?:s|d)?|mutation|"
            r"reconcile(?:s|d)?|reconciliation)\b.{0,120}"
            r"\b(?:contribution polic(?:y|ies)|compensation-adapter binding)\b|"
            r"\b(?:contribution polic(?:y|ies)|compensation-adapter binding)\b"
            r".{0,180}\bOperator\b.{0,100}\b(?:publish|approve|bind|manage|"
            r"mutat|reconcil))",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "OPERATOR_COMPENSATION_MUTATION",
        re.compile(
            r"(?:\bOperator\b.{0,160}\b(?:reconcile(?:s|d)?|reconciliation|"
            r"mutate(?:s|d)?|mutation|create(?:s|d)?|update(?:s|d)?)\b.{0,120}"
            r"\b(?:contribution records?|compensation awards?|fulfillment records?)\b|"
            r"\b(?:contribution records?|compensation awards?|fulfillment records?)\b"
            r".{0,160}\bOperator\b.{0,100}\b(?:reconcil|mutat|creat|updat))",
            re.IGNORECASE,
        ),
    ),
)

FULL_INITIATIVE_RULE_CODES = {
    "ACCESS_ADMIN_CATALOG_ADMINISTRATION",
    "CURRENT_TOKEN_ROLE_AUTHORITY",
    "NAMED_ROLE_TOKEN_AUTHORITY",
    "OBSOLETE_ROLE_ASSIGNMENT_MODEL",
    "OPERATOR_COMPENSATION_MUTATION",
    "OPERATOR_CONTRIBUTION_POLICY_AUTHORITY",
    "TOKEN_CARRIES_PRODUCT_ROLE",
    "TOKEN_ROLE_PRODUCT_AUTHORITY",
    "TRUSTED_ROLE_CLAIM_AUTHORITY",
    "TYPED_PROFILE_AUTHORITY",
    "TYPED_PROFILE_PRODUCT_AUTHORITY",
}

ACTIVATION_CUSTODY_RULES = (
    Rule(
        "FEATURE_OWNED_AUTH_ACTIVATION",
        re.compile(
            r"(?:"
            r"actions?\s+remain\s+non-executable\s+until\s+(?:their\s+)?owning\s+"
            r"chunks?\s+activates?|"
            r"(?:later\s+)?owner\s+chunks?\s+activates?|"
            r"(?:an?\s+)?owning\s+(?:feature\s+)?cutover\s+chunks?\s+activates?|"
            r"feature\s+activation\s+blueprints?|"
            r"actions?\s+(?:is|are)\s+activated\s+by\s+(?:their\s+)?owning\s+"
            r"WS-(?:ART|REV|CON)\s+chunks?|"
            r"each\s+owning\s+WS-(?:ART|REV|CON)\s+chunk\s+activates?|"
            r"WS-(?:ART|REV|CON)[\w-]*\s+feature\s+chunk[\s\S]{0,120}?"
            r"actions?\s+it\s+activates?|"
            r"actions?\s+activated\s+by\s+that\s+chunk|"
            r"owning\s+WS-(?:ART|REV|CON)\s+activation\s+blueprint|"
            r"paired\s+owning\s+feature\s+activates?|"
            r"runtime\s+activation\s+remain\s+with\s+the\s+listed\s+owner|"
            r"route-owning\s+chunks?[\s\S]{0,120}?promote\s+an\s+action\s+to\s+active"
            r")",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "PLANNING_INITIATIVE_AUTH_ACTIVATION",
        re.compile(
            r"(?:\bAUTH\b.{0,160}\b(?:activates?|changes?\s+action\s+"
            r"availability)\b.{0,160}\bunder\s+`?WS-XINT-[\w-]+`?|"
            r"\bWS-XINT-[\w-]+`?\s+(?:is|acts?\s+as)\s+(?:the\s+)?"
            r"(?:AUTH\s+)?activation\s+custodian\b)",
            re.IGNORECASE,
        ),
    ),
)

ACTIVATION_CUSTODY_EXACT_PATHS = (
    "AGENTS.md",
    ".agent-loop/LOOP_STATE.md",
    ".agent-loop/WORK_QUEUE.md",
    "docs/spec_authorization_service.md",
)
TECHNICAL_WORKER_PREFIX = re.compile(
    r"(?:celery(?:[- ]backed)?|checker|setup|system|background|reconciliation|"
    r"execution|"
    r"service|job|queue|durable|project[- ]setup|pre[- ]review|post[- ]submit)"
    r"[\s/-]+$",
    re.IGNORECASE,
)

MATCH_EXEMPTIONS = {
    (
        "docs/reference_specs/README.md",
        "NON_CANONICAL_API_PREFIX",
    ): re.compile(
        r"^archival input uses `/v1`\. WS-AUTH-001 takes precedence over the current$"
    ),
}


def git_lines(root: Path, *args: str) -> list[str]:
    """Return non-empty lines from a Git command in ``root``."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [line for line in result.stdout.splitlines() if line]


def discover_documents(root: Path = ROOT) -> list[Path]:
    """Auto-discover tracked and untracked active documentation."""
    raw_paths = git_lines(root, "ls-files")
    raw_paths.extend(git_lines(root, "ls-files", "--others", "--exclude-standard"))
    documents: list[Path] = []
    for raw_path in dict.fromkeys(raw_paths):
        path_parts = Path(raw_path).parts
        is_public_document = raw_path == "README.md" or raw_path.startswith("docs/")
        is_policy = raw_path.startswith(".agent-loop/policies/")
        is_initiative_contract = (
            raw_path.startswith(".agent-loop/initiatives/")
            and "reviews" not in path_parts
        )
        if not (is_public_document or is_policy or is_initiative_contract):
            continue
        if Path(raw_path).suffix.lower() not in DOCUMENT_SUFFIXES:
            continue
        if raw_path in HISTORICAL_PATHS:
            continue
        path = root / raw_path
        if path.is_file():
            documents.append(path)
    return documents


def discover_activation_custody_documents(root: Path = ROOT) -> list[Path]:
    """Return active contracts that may assign authorization activation custody."""
    documents = set(discover_documents(root))
    documents.update(
        root / relative_path
        for relative_path in ACTIVATION_CUSTODY_EXACT_PATHS
        if (root / relative_path).is_file()
    )
    policy_root = root / ".agent-loop/policies"
    if policy_root.is_dir():
        documents.update(policy_root.glob("*.md"))
    initiative_root = root / ".agent-loop/initiatives"
    if initiative_root.is_dir():
        documents.update(
            candidate
            for candidate in initiative_root.rglob("*")
            if candidate.is_file()
            and candidate.suffix in {".json", ".md"}
            and "reviews" not in candidate.relative_to(initiative_root).parts
            and candidate.relative_to(root).as_posix() not in HISTORICAL_PATHS
        )
    return sorted(documents)


def line_number(text: str, offset: int) -> int:
    """Return a one-based line number for ``offset``."""
    return text.count("\n", 0, offset) + 1


def containing_line(text: str, offset: int) -> str:
    """Return the full line containing ``offset``."""
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    return text[start:] if end == -1 else text[start:end]


def exempt_match(relative_path: str, rule: Rule, text: str, offset: int) -> bool:
    """Return whether one exact reviewed archival marker match is allowed."""
    exemption = MATCH_EXEMPTIONS.get((relative_path, rule.code))
    return bool(exemption and exemption.fullmatch(containing_line(text, offset)))


def technical_worker_match(text: str, match: re.Match[str]) -> bool:
    """Return whether the matched worker token is service-qualified."""
    token = re.search(
        r"\bworkers?(?:_(?:id|attestation|message|suggested_fix|evidence_refs|"
        r"visible|claim_status|profile))?\b",
        match.group(0),
        re.IGNORECASE,
    )
    if token is None:
        return False
    worker_offset = match.start() + token.start()
    prefix = text[max(0, worker_offset - 120) : worker_offset]
    token_end = worker_offset + len(token.group(0))
    suffix = text[token_end : token_end + 20]
    exact_code_path = token.group(0).lower() == "workers" and (
        (
            re.search(r"(?:^|[^A-Za-z0-9_.-])(?:backend/)?app/$", prefix)
            is not None
            and suffix.startswith("/")
        )
        or (
            re.search(r"(?:^|[^A-Za-z0-9_.-])app\.$", prefix) is not None
            and suffix.startswith(".")
        )
    )
    exact_technical_cli_flag = (
        token.group(0).lower() == "worker"
        and prefix.endswith("--start-api-")
        and re.match(r"^-beat(?:\s|$)", suffix) is not None
    ) or (
        token.group(0).lower() == "workers"
        and prefix.endswith("--require-")
        and (not suffix or suffix[0].isspace())
    )
    exact_celery_cli = bool(
        re.search(
            r"(?:^|\n)[^;\n]*\bcelery\s+-A\s+[^;\n]+$",
            prefix,
            re.IGNORECASE,
        )
        and suffix.startswith(" --")
    )
    return bool(
        TECHNICAL_WORKER_PREFIX.search(prefix)
        or exact_code_path
        or exact_celery_cli
        or exact_technical_cli_flag
    )


def scan_text(
    relative_path: str,
    text: str,
    *,
    enforced_line_numbers: frozenset[int] | None = None,
) -> list[str]:
    """Return deterministic rule failures for one active document."""
    failures: list[str] = []
    for rule in RULES:
        for match in rule.pattern.finditer(text):
            match_line_number = line_number(text, match.start())
            match_end_line_number = line_number(
                text, max(match.start(), match.end() - 1)
            )
            enforce_full_initiative = (
                relative_path.startswith(".agent-loop/initiatives/")
                and rule.code in FULL_INITIATIVE_RULE_CODES
            )
            if (
                enforced_line_numbers is not None
                and not enforce_full_initiative
                and enforced_line_numbers.isdisjoint(
                    range(match_line_number, match_end_line_number + 1)
                )
            ):
                continue
            if exempt_match(relative_path, rule, text, match.start()):
                continue
            if rule.code in {
                "HUMAN_WORKER_VOCABULARY",
                "HUMAN_WORKER_IDENTIFIER",
            } and technical_worker_match(text, match):
                continue
            failures.append(f"{relative_path}:{match_line_number}: {rule.code}")
    return failures


def initiative_changed_line_numbers(
    root: Path, relative_path: str
) -> frozenset[int] | None:
    """Return changed initiative lines, or ``None`` for a new/non-initiative file."""
    if not relative_path.startswith(".agent-loop/initiatives/"):
        return None
    baseline = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"origin/main:{relative_path}"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if baseline.returncode != 0:
        return None
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "diff",
            "--unified=0",
            "--no-color",
            "origin/main",
            "--",
            relative_path,
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    changed_lines: set[int] = set()
    hunk_pattern = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
    for line in result.stdout.splitlines():
        match = hunk_pattern.match(line)
        if match is None:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        changed_lines.update(range(start, start + count))
    return frozenset(changed_lines)


def scan_activation_custody_text(relative_path: str, text: str) -> list[str]:
    """Reject feature-owned authorization activation in current contracts."""
    failures: list[str] = []
    for rule in ACTIVATION_CUSTODY_RULES:
        failures.extend(
            f"{relative_path}:{line_number(text, match.start())}: {rule.code}"
            for match in rule.pattern.finditer(text)
        )
    return failures


def scan(root: Path = ROOT) -> list[str]:
    """Scan every discovered active document."""
    failures: list[str] = []
    for path in discover_documents(root):
        relative_path = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            failures.append(f"{relative_path}: unreadable active document: {exc}")
            continue
        failures.extend(
            scan_text(
                relative_path,
                text,
                enforced_line_numbers=initiative_changed_line_numbers(
                    root, relative_path
                ),
            )
        )
    for path in discover_activation_custody_documents(root):
        relative_path = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            failures.append(f"{relative_path}: unreadable custody contract: {exc}")
            continue
        failures.extend(scan_activation_custody_text(relative_path, text))
    return failures


def main() -> int:
    """Run the stale authorization documentation gate."""
    failures = scan()
    if failures:
        print("Stale authorization documentation check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Stale authorization documentation check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
