#!/usr/bin/env python3
"""Reject obsolete review/revision claims in active Workstream contracts."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".html", ".md", ".puml"}

# These supplied files are immutable evidence, not active repository policy.
ARCHIVAL_PATHS = {
    "docs/reference_specs/WS-AUTH-001-actor-profile-role-and-authorization-service-specification.md",
    "docs/reference_specs/WS-REV-001-review-lifecycle-specification.md",
    "docs/reference_specs/WS-IMP-001-workstream-v0.1-coding-agent-implementation-specification.md",
}

# Closed engineering/product reviews may describe earlier contracts verbatim.
HISTORICAL_PATHS = {
    "docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification.md",
    "docs/internal_reviews/2026-06-11_chunk9_pre_review_gate.md",
    "docs/internal_reviews/2026-06-11_revision_context_rebase.md",
    "docs/internal_reviews/2026-06-12_chunk10_checker_trial.md",
    "docs/internal_reviews/2026-06-12_week2_closeout_real_api_drill.md",
    "docs/internal_reviews/2026-06-13_week1_week2_deterministic_hardening.md",
    "docs/internal_reviews/2026-06-16_submission_artifact_policy_architecture.md",
    "docs/review_adversarial_quality_review.md",
    "docs/review_architecture_review.md",
    "docs/review_closure.md",
    "docs/review_final_adversarial_review.md",
    "docs/review_final_architecture_review.md",
    "docs/review_final_product_strategy_review.md",
    "docs/review_operations_review.md",
    "docs/review_process_baseline_operations_review.md",
    "docs/review_process_pattern_baseline_review.md",
    "docs/review_product_strategy_review.md",
    "docs/review_systems_architecture_review.md",
    "docs/spec_chunk_9_pre_review_gate.md",
}

NON_PRODUCT_REVIEW_PATHS = {
    "docs/operations_subagent_review_protocol.md",
}

# Exact active surfaces governed by this adoption. A newly named review or
# revision document must be deliberately classified instead of escaping review.
ACTIVE_PATHS = {
    "README.md",
    "docs/architecture_brief/task_lifecycle_sequence.puml",
    "docs/architecture_brief/workstream_architecture_brief.md",
    "docs/architecture_data_model.md",
    "docs/architecture_lifecycle_state_machine.md",
    "docs/architecture_lockdown.md",
    "docs/architecture_system_architecture.md",
    "docs/decision_0001_core_scope.md",
    "docs/decision_0009_review_decisions_are_canonical.md",
    "docs/decision_0003_project_guides_are_first_class.md",
    "docs/decision_0010_revision_context_rebase.md",
    "docs/decision_0012_workstream_authorization_service.md",
    "docs/decision_0013_immutable_artifact_storage_boundary.md",
    "docs/decision_0015_project_contributor_roles_are_independent.md",
    "docs/diagrams/backend_v01_components.md",
    "docs/diagrams/backend_v01_components.puml",
    "docs/diagrams/task_lifecycle_sequence.md",
    "docs/diagrams/workstream_v01_container.md",
    "docs/diagrams/workstream_v01_container.puml",
    "docs/glossary.md",
    "docs/operations_operator_workflow.md",
    "docs/operations_payment_reputation.md",
    "docs/operations_project_operating_manual.md",
    "docs/operations_queue_policy.md",
    "docs/operations_reviewer_workflow.md",
    "docs/operations_revision_replay.md",
    "docs/operations_roles_permissions.md",
    "docs/principles.md",
    "docs/product_first_user_flows.md",
    "docs/product_principles.md",
    "docs/reference_specs/README.md",
    "docs/risk_register.md",
    "docs/roadmap_30_day_master_plan.md",
    "docs/roadmap_day_by_day_execution_plan.md",
    "docs/roadmap_implementation_backlog.md",
    "docs/roadmap_pilot_plan.md",
    "docs/roles_permissions.md",
    "docs/spec_chunk_3_project_guide_foundation.md",
    "docs/spec_review_lifecycle.md",
    "docs/template_prior_feedback_checklist.md",
    "docs/template_project_guide.md",
    "docs/template_review_packet.md",
    "docs/template_revision_replay.md",
    "docs/template_task_status.md",
}


@dataclass(frozen=True)
class Rule:
    """One prohibited active-contract phrase."""

    code: str
    pattern: re.Pattern[str]


RULES = (
    Rule("NON_CANONICAL_API_PREFIX", re.compile(r"(?<!/api)/v1(?:/|\b)")),
    Rule(
        "ACTIVE_FLOW_NODE_PROVIDER",
        re.compile(
            r"\bFlow\s+Node\b[^.\n]{0,100}\b(?:is|as|remains|uses?)\b"
            r"[^.\n]{0,60}\b(?:active|hosted|production|provider)\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "FULL_REVIEWER_BACKLOG",
        re.compile(
            r"\breviewer(?:s)?\s+(?:opens?|browses?|selects?|chooses?)\b"
            r"[^.\n]{0,80}\b(?:review\s+queue|review_pending|backlog|task)\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "LEGACY_REVIEW_SEVERITY",
        re.compile(
            r"(?:ReviewFinding|review\s+finding|prior\s+finding|finding)"
            r"[^.\n]{0,80}(?:\b(?:high|medium|low)[- ]severity\b|"
            r"\bseverity\s*[:=|]\s*(?:high|medium|low)\b)|"
            r"\bPrior\s+Severity\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "LEGACY_FINDING_CLOSURE",
        re.compile(
            r"\b(?:contributor_claim_status|reviewer_closure_status|"
            r"closed_fixed|closed_rebutted|partially_closed|still_open)\b|"
            r"\bclosed\s*/\s*still\s+open\b|"
            r"\bclose\s+prior\s+revision\s+findings\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "POLICY_SELECTED_LATEST_REBASE",
        re.compile(
            r"revision\s+policy\s+(?:decides?|controls?)\b[^.\n]{0,120}"
            r"\b(?:latest|current)\s+active\s+(?:guide|context)",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "REVIEWER_REBASE",
        re.compile(
            r"\breviewer\b[^.\n]{0,100}\b(?:rebases?|"
            r"performs?\s+(?:an?\s+)?rebase|runs?\s+(?:an?\s+)?rebase)\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "SYNTHETIC_REJECT",
        re.compile(
            r"\b(?:checker|artifact|storage|revision\s+(?:limit|deadline))\b"
            r"[^.\n]{0,100}\b(?:creates?|records?|sets?|moves?)\b"
            r"[^.\n]{0,30}\b(?:reject|rejected)\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "DIRECT_ACCEPT_TO_SUBMITTER_CONTRIBUTION",
        re.compile(
            r"\baccept(?:ed|ance)?\b[^.\n]{0,120}"
            r"\b(?:directly\s+)?creates?\b[^.\n]{0,100}"
            r"\b(?:submitter\s+contribution|accepted_submission)\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "AUTO_REJECT_REVISION_LIMIT",
        re.compile(
            r"\bauto_reject_after_limit\b[`\"']?\s*(?::|=)\s*"
            r"[`\"']?(?:true|1|yes)\b|"
            r"\b(?:revision\s+(?:limit|deadline)|limit\s+or\s+deadline)\b"
            r"[^.\n]{0,100}\b(?:automatically\s+reject(?:s|ed)?|auto-reject)\b|"
            r"\b(?:automatically\s+reject(?:s|ed)?|auto-reject)\b[^.\n]{0,100}"
            r"\brevision\s+(?:limit|deadline)\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "REJECT_REQUIRES_FINDING",
        re.compile(
            r"\breject(?:ed|ion)?\b[^.\n]{0,100}\brequires?\b"
            r"[^.\n]{0,60}\b(?:a\s+)?finding\b|"
            r"\b(?:needs_revision\s+and\s+reject|reject\s+and\s+needs_revision)\b"
            r"[^.\n]{0,80}\brequire\b[^.\n]{0,40}\bfinding\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "REVIEW_REPUTATION_SIDE_EFFECT",
        re.compile(
            r"\b(?:review|accept(?:ed|ance)?|reject(?:ed|ion)?)\b"
            r"[^.\n]{0,120}\b(?:creates?|records?|updates?|applies?|"
            r"are\s+recorded)\b[^.\n]{0,60}"
            r"\breputation\s+(?:event|effect|update)s?\b|"
            r"\b(?:review|accept(?:ed|ance)?|reject(?:ed|ion)?)\b"
            r"[^.\n]{0,120}\breputation\s+(?:event|effect|update)s?\b"
            r"[^.\n]{0,60}\bare\s+recorded\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "ACTIVE_REPUTATION_LEDGER",
        re.compile(
            r"^#{2,4}\s+Day\s+\d+:\s+Reputation\s+Ledger\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    Rule(
        "UNCONDITIONAL_REVIEW_PAYMENT",
        re.compile(
            r"\baccepted\s+(?:work|task)\b[^.\n]{0,100}"
            r"\b(?:creates?|must\s+have|without)\b[^.\n]{0,60}"
            r"\b(?:pending\s+)?payment\s+(?:record|status)?\b|"
            r"\bno\s+accepted\s+task\b[^.\n]{0,60}"
            r"\b(?:without|missing)\b[^.\n]{0,30}\bpayment\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "ADJUDICATION_ACTIVATION_PROMISE",
        re.compile(
            r"\badjudicat(?:ion|or)\b[^.\n]{0,100}\b(?:until|when)\b"
            r"[^.\n]{0,80}\b(?:activate|enabled|implemented)\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "BROAD_REVIEW_BYPASS",
        re.compile(
            r"\b(?:admin|operator|project\s+manager)\b[^.\n]{0,60}"
            r"\b(?:override|bypass)\b[^.\n]{0,80}\b(?:review|accept|decision)\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "HUMAN_PRE_REVIEW_ADMISSION",
        re.compile(
            r"^#{2,4}\s+(?:Pre[- ]?Review|Checker\s+Admission)\s+Gate\b"
            r"[\s\S]{0,600}\b(?:reviewer[- ]simulation|"
            r"assigned\s+simulation\s+reviewer|reviewer\s+lead|quality\s+lead)\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    Rule(
        "DISPUTED_REJECT_PATH",
        re.compile(r"\breviewer\s+lead\s+if\s+disputed\b", re.IGNORECASE),
    ),
)


def git_lines(root: Path, *args: str) -> list[str]:
    """Return non-empty path lines from Git, failing closed on Git errors."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [line for line in result.stdout.splitlines() if line]


def discover_paths(root: Path = ROOT) -> list[Path]:
    """Discover tracked, staged/modified, untracked, and newly added text files."""
    relative_paths = git_lines(root, "ls-files")
    relative_paths.extend(git_lines(root, "ls-files", "--others", "--exclude-standard"))
    paths: list[Path] = []
    for relative_path in dict.fromkeys(relative_paths):
        path = root / relative_path
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            paths.append(path)
    return paths


def classification(relative_path: str) -> str:
    """Return the durable review-contract classification for a path."""
    if relative_path in ARCHIVAL_PATHS:
        return "archival"
    if relative_path in HISTORICAL_PATHS:
        return "historical"
    if relative_path in NON_PRODUCT_REVIEW_PATHS:
        return "non_product_review"
    if relative_path in ACTIVE_PATHS:
        return "active"
    if relative_path.startswith("docs/reference_specs/"):
        return "unclassified"
    if relative_path.startswith("docs/"):
        return "active"
    return "unclassified"


def line_number(text: str, offset: int) -> int:
    """Return a one-based line number for a match offset."""
    return text.count("\n", 0, offset) + 1


def scan_text(relative_path: str, text: str) -> list[str]:
    """Return stale-contract failures for one active document."""
    failures: list[str] = []
    for rule in RULES:
        for match in rule.pattern.finditer(text):
            failures.append(
                f"{relative_path}:{line_number(text, match.start())}: {rule.code}"
            )
    return failures


def scan(root: Path = ROOT) -> list[str]:
    """Scan all exact active paths and reject unclassified review documents."""
    failures: list[str] = []
    discovered = discover_paths(root)
    discovered_relative = {path.relative_to(root).as_posix() for path in discovered}

    for required_path in sorted(ACTIVE_PATHS):
        if required_path not in discovered_relative:
            failures.append(f"{required_path}:0: MISSING_ACTIVE_REVIEW_CONTRACT")

    for path in discovered:
        relative_path = path.relative_to(root).as_posix()
        path_class = classification(relative_path)
        if path_class == "unclassified" and relative_path.startswith("docs/"):
            failures.append(f"{relative_path}:0: UNCLASSIFIED_ACTIVE_DOCUMENT")
            continue
        if path_class != "active":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            failures.append(
                f"{relative_path}:0: UNREADABLE_ACTIVE_REVIEW_CONTRACT "
                f"({type(exc).__name__})"
            )
            continue
        failures.extend(scan_text(relative_path, text))
    return failures


def main() -> int:
    """Run the stale review/revision contract gate."""
    try:
        failures = scan()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Stale review contract check failed closed: {exc}", file=sys.stderr)
        return 1
    if failures:
        print("Stale review contract check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Stale review contract check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
