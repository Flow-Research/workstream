"""Check for stale Workstream wording outside explicit allowlisted files."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN_PATTERNS = (
    re.compile(r"task-production control plane", re.IGNORECASE),
    re.compile(r"garden roadmap", re.IGNORECASE),
    re.compile(r"ApprovedTaskArtifactBinding", re.IGNORECASE),
    re.compile(r"EffectiveTaskSubmissionArtifactPolicy", re.IGNORECASE),
    re.compile(r"EffectiveSubmissionArtifactPolicy", re.IGNORECASE),
    re.compile(r"ProjectPreSubmitCheckerSpec", re.IGNORECASE),
    re.compile(r"task_artifact_binding", re.IGNORECASE),
    re.compile(r"task artifact binding", re.IGNORECASE),
    re.compile(r"effective_task_submission", re.IGNORECASE),
    re.compile(r"effective task submission artifact policy", re.IGNORECASE),
    re.compile(r"effective task policy", re.IGNORECASE),
    re.compile(r"effective_project_policy_hash", re.IGNORECASE),
    re.compile(r"effective project policy hash(?:es)?", re.IGNORECASE),
    re.compile(r"effective policy hash(?:es)?", re.IGNORECASE),
    re.compile(r"locked_task_artifact_binding_id", re.IGNORECASE),
    re.compile(r"locked_effective_task_submission_artifact_policy_hash", re.IGNORECASE),
    re.compile(r"generated task pre-submit", re.IGNORECASE),
    re.compile(r"task-level PreSubmitCheckerPolicy", re.IGNORECASE),
    re.compile(r"task-level pre-submit", re.IGNORECASE),
    re.compile(r"project/task policy", re.IGNORECASE),
    re.compile(r"profile-scoped", re.IGNORECASE),
    re.compile(r"project/profile", re.IGNORECASE),
    re.compile(r"pre-submit checker policy hash(?:es)?", re.IGNORECASE),
    re.compile(r"pre_submit_checker_policy_hash", re.IGNORECASE),
    re.compile(r"project pre-submit checker policy hash(?:es)?", re.IGNORECASE),
    re.compile(r"project checker hash(?:es)?", re.IGNORECASE),
    re.compile(r"PreSubmitCheckerPolicy hash(?:es)?", re.IGNORECASE),
    re.compile(r"PreSubmitCheckerPolicy snapshot/hash(?:es)?", re.IGNORECASE),
    re.compile(r"auto_checking", re.IGNORECASE),
    re.compile(r"auto\s*[\"']?\s*\\?\s*\+\s*[\"']?_checking", re.IGNORECASE),
    re.compile(r"needs_revision:\s+no payment owed yet", re.IGNORECASE),
    re.compile(r"no accepted task without payment record", re.IGNORECASE),
    re.compile(r"accepted work creates (?:a )?pending payment record", re.IGNORECASE),
    re.compile(r"contribution record is created when work is accepted", re.IGNORECASE),
    re.compile(r"the evidence-backed record that accepted work", re.IGNORECASE),
    re.compile(r"accepted tasks?.{0,80}payment records?", re.IGNORECASE),
    re.compile(r"payment records?.{0,80}accepted tasks?", re.IGNORECASE),
    re.compile(r"acceptance.{0,80}payment records?", re.IGNORECASE),
    re.compile(r"accepted transition.{0,80}payment records?", re.IGNORECASE),
    re.compile(r"payment record (?:moves to pending|can be generated)", re.IGNORECASE),
    re.compile(r"payment\s+NONE\s*->\s*PAID.{0,80}accepted task", re.IGNORECASE),
    re.compile(r"every accepted task updates payment", re.IGNORECASE),
)
FULL_TEXT_FORBIDDEN_PATTERNS = {
    "auto\\s*[\"']?\\s*\\\\?\\s*\\+\\s*[\"']?_checking",
}
FORBIDDEN_PATH_PATTERNS = (
    re.compile(r"(^|/)\.claude(/|$)", re.IGNORECASE),
    re.compile(r"(^|/)claude\.md$", re.IGNORECASE),
)
ACTIVE_SHARED_CONTRACT_PATTERNS = (
    re.compile(r"\bOperator\s*/\s*Access Admin(?:istrator)?\b", re.IGNORECASE),
    re.compile(
        r"\bcontribution\s*/\s*payment\s*/\s*reputation records\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bProject Manager\b[^\n]{0,120}\b(?:manage[sd]?|creat(?:e|es))\b"
        r"[^\n]{0,80}\bpolicies\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:\bPM\b|\bProject Manager\b)[^\n]{0,160}"
        r"\b(?:contribution policy|compensation-adapter binding)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bsubmitter\s*/\s*both\b", re.IGNORECASE),
    re.compile(r"\breviewer\s*/\s*both\b", re.IGNORECASE),
    re.compile(r"\bSubmitter\s+or\s+Both\s+grant\b", re.IGNORECASE),
    re.compile(r"\bReviewer\s+or\s+Both\s+grant\b", re.IGNORECASE),
    re.compile(
        r"\bProjectRoleGrant\s*\(\s*submitter\|reviewer\|both\s*\)",
        re.IGNORECASE,
    ),
    re.compile(r"`submitter`,\s*`reviewer`,\s*or\s*`both`", re.IGNORECASE),
    re.compile(r"\|\s*Both\s*\|\s*exact project", re.IGNORECASE),
    re.compile(r"\bActive submitter, reviewer, and both grants\b", re.IGNORECASE),
    re.compile(
        r"\bProjectRoleGrant\s+values\s+are\s+exactly\s+"
        r"`?submitter`?\s*(?:,|and)\s*`?reviewer`?\s*[.;]",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bProject issue roles are exactly\s+`?submitter`?\s+or\s+"
        r"`?reviewer`?\s*[.;]",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bindependent\s+`?submitter`?\s+and\s+`?reviewer`?\s+"
        r"ProjectRoleGrants?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\badjudicat(?:ion actions?|or actions?)\s+remain\s+unavailable\s+"
        r"until\s+(?:their|that)\s+(?:separate\s+)?lifecycle\s+is\s+activated",
        re.IGNORECASE,
    ),
    re.compile(
        r"\badjudicat(?:ion|or) actions\s+(?:remain\s+)?unavailable\s+until\s+"
        r"separately\s+activated",
        re.IGNORECASE,
    ),
    re.compile(r"\blocks actor/link/grant/assignment rows\b", re.IGNORECASE),
    re.compile(r"\bservice-assignment authority\b", re.IGNORECASE),
    re.compile(r"\bservice-actor assignment\b", re.IGNORECASE),
    re.compile(r"\bfixed service principals?/assignments?\b", re.IGNORECASE),
    re.compile(r"\bservice assignments?\b", re.IGNORECASE),
    re.compile(
        r"\bservice principals?\s+and\s+(?:exact\s+)?planned\s+assignments?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bidentity/action assignment source\b", re.IGNORECASE),
    re.compile(r"\bservice-action assignments?\b", re.IGNORECASE),
    re.compile(r"\bservice identities and exact assignments?\b", re.IGNORECASE),
    re.compile(r"\bservice identities, exact assignments?\b", re.IGNORECASE),
    re.compile(r"\bAUTH-09 assigns\b", re.IGNORECASE),
    re.compile(r"\bplanned assignment remains inert\b", re.IGNORECASE),
    re.compile(
        r"\bPermissionId mapping, or exact assignment\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bAUTH-09 persists (?:these )?exact service actors and assignments\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bdo not become normal ActorProfiles\b", re.IGNORECASE),
    re.compile(
        r"Proposed after 02C3,\s*AUTH-09,\s*and AUTH custody registration",
        re.IGNORECASE,
    ),
    re.compile(r"\bworker, reviewer, or project manager\b", re.IGNORECASE),
    re.compile(r"\boperators?, workers?, reviewers?\b", re.IGNORECASE),
    re.compile(r"\breviews?,\s+and\s+payments?\b", re.IGNORECASE),
    re.compile(r"\bowning compensation authority\b", re.IGNORECASE),
    re.compile(r"\bFinance\s+(?:reconciles|follows)\b", re.IGNORECASE),
    re.compile(r"\bcompensation\s+publication\b", re.IGNORECASE),
    re.compile(r"\bpublished\s+compensation\s+definition\b", re.IGNORECASE),
    re.compile(r"\bCompensationPolicyVersion\b"),
    re.compile(r"\bCompensationPolicy\b"),
    re.compile(r"\bCompensationRule\b"),
    re.compile(r"\bCompensationAwardDefinition\b"),
    re.compile(r"\bCompensation\s+Policy\s*Version\b", re.IGNORECASE),
    re.compile(r"\bCompensation\s+Policy\b", re.IGNORECASE),
    re.compile(r"\bCompensation\s+Rule\b", re.IGNORECASE),
    re.compile(r"\bCompensation\s+Award\s*Definition\b", re.IGNORECASE),
    re.compile(r"\bcompensation_policy\b", re.IGNORECASE),
    re.compile(r"\bcompensation_rule_id\b", re.IGNORECASE),
    re.compile(r"\bcompensation\s+polic(?:y|ies)\b", re.IGNORECASE),
    re.compile(r"\bcompensation\s+versions?\b", re.IGNORECASE),
    re.compile(r"\bcompensation\s+rules?\b", re.IGNORECASE),
    re.compile(r"\bPaymentPolicy\b"),
    re.compile(r"\bPaymentRecord\b"),
    re.compile(r"\bPaymentAdjustment\b"),
    re.compile(r"\bPayment\s+Policy\b", re.IGNORECASE),
    re.compile(r"\bPayment\s+Record\b", re.IGNORECASE),
    re.compile(r"\bPayment\s+Adjustment\b", re.IGNORECASE),
    re.compile(r"\bpayment(?:[-_]|\s+)policy\b", re.IGNORECASE),
    re.compile(r"\bpayment(?:[-_]|\s+)record\b", re.IGNORECASE),
    re.compile(r"\bpayment_ledger\b", re.IGNORECASE),
    re.compile(r"\bpayment_adjustment\b", re.IGNORECASE),
    re.compile(r"\b(?:locked_payment_policy_version)\b", re.IGNORECASE),
    re.compile(r"\bpayment_reconciliation\b", re.IGNORECASE),
    re.compile(r"\bpayment truth\b", re.IGNORECASE),
    re.compile(r"\bPayment And Reputation\b"),
    re.compile(r"\bcompensation fulfillment/payment status\b", re.IGNORECASE),
    re.compile(r"\bpayment status\b", re.IGNORECASE),
    re.compile(r"\bpayment\s+polic(?:y|ies)\b", re.IGNORECASE),
    re.compile(r"\bpayment\s+records?\b", re.IGNORECASE),
    re.compile(r"\bpayment\s+ledger\b", re.IGNORECASE),
    re.compile(r"\bpayment exposure\b", re.IGNORECASE),
    re.compile(r"\bpayment follow-up\b", re.IGNORECASE),
    re.compile(r"\bpayment adjustment record\b", re.IGNORECASE),
    re.compile(r"\baccepted[- ]unpaid\b", re.IGNORECASE),
    re.compile(r"\baccepted but unpaid\b", re.IGNORECASE),
    re.compile(r"\bcontribution record generated on acceptance\b", re.IGNORECASE),
    re.compile(r"\bcontribution record creation after acceptance\b", re.IGNORECASE),
    re.compile(r"\baccepted paid output\b", re.IGNORECASE),
    re.compile(r"\baward/payment record\b", re.IGNORECASE),
    re.compile(r"\bPAYOUT_SUBMITTED\b"),
    re.compile(r"\bPAID\b"),
    re.compile(r"\bDISPUTED\b"),
)
ACTIVE_SHARED_CONTRACT_EXCLUDED_PREFIXES = (
    "docs/internal_reviews/",
    "docs/reference_specs/",
)
# Exact reviewed history/archive paths. Keep this set in parity with the
# authorization and artifact contract scanners; unknown future files remain
# active by default.
HISTORICAL_PATHS = {
    ".agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-06-canonical-actor-profile.md",
    ".agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/WS-POL-001-11-actor-identity-profile-registry.md",
    "docs/checker_trial_failure_catalog.md",
    "docs/internal_reviews/2026-06-11_chunk9_pre_review_gate.md",
    "docs/internal_reviews/2026-06-11_revision_context_rebase.md",
    "docs/internal_reviews/2026-06-12_chunk10_checker_trial.md",
    "docs/internal_reviews/2026-06-12_week2_closeout_real_api_drill.md",
    "docs/internal_reviews/2026-06-13_week1_week2_deterministic_hardening.md",
    "docs/internal_reviews/2026-06-16_submission_artifact_policy_architecture.md",
    "docs/reference_specs/WS-AUTH-001-actor-profile-role-and-authorization-service-specification.md",
    "docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification.md",
    "docs/reference_specs/WS-IMP-001-workstream-v0.1-coding-agent-implementation-specification.md",
    "docs/reference_specs/WS-REV-001-review-lifecycle-specification.md",
    "docs/roadmap_30_day_master_plan.md",
    "docs/roadmap_day_by_day_execution_plan.md",
    "docs/roadmap_pilot_plan.md",
    "docs/roadmap_week1_backend_plan.md",
    "docs/spec_chunk_1_backend_scaffold.md",
    "docs/spec_chunk_3_project_guide_foundation.md",
    "docs/spec_chunk_4_task_queue_assignment.md",
    "docs/spec_chunk_5_submission_packet_foundation.md",
    "docs/spec_chunk_6_checker_contract_records.md",
    "docs/spec_chunk_7_checker_runner_registry.md",
    "docs/spec_chunk_8_submission_artifact_policy_checkers.md",
    "docs/spec_chunk_9_pre_review_gate.md",
    "docs/spec_chunk_10_checker_trial.md",
    "docs/spec_week2_checker_framework.md",
}
CURRENT_RUNTIME_CONTRACT_PATHS = {
    "docs/current_system_data_flow.html",
}
ACTIVE_COMPENSATION_LINE_EXEMPTIONS = {
    ".agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/chunks/"
    "WS-XINT-001-PLAN-boundary-reconciliation.md": (
        "`PaymentPolicy` and `PaymentRecord` are retired and removed names",
    ),
}
UNIMPLEMENTED_CURRENT_RUNTIME_COMPENSATION_PATTERNS = (
    re.compile(r"\bContributionPolicy\b"),
    re.compile(r"\bContributionPolicyVersion\b"),
    re.compile(r"\bContributionRule\b"),
    re.compile(r"\bContributionAwardDefinition\b"),
    re.compile(r"\bProjectCompensationAdapterBinding\b"),
    re.compile(r"\bReviewLease\b"),
    re.compile(r"\bContributionRecord\b"),
    re.compile(r"\bCompensationAward\b"),
    re.compile(r"\bCompensationFulfillmentReceipt\b"),
    re.compile(r"\bCompensationStatusProjection\b"),
)
SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "downloads",
    "sheets",
}
SKIP_PREFIXES = ("docs/internal_reviews/",)
SKIP_FILES = {
    "scripts/check_stale_workstream_wording.py",
}
ALLOWLISTED_LINES = {
    "AGENTS.md": ("Do not use old names such as",),
}
ALLOWLISTED_PATTERN_LINES = {
    "auto_checking": {
        ".agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/chunks/"
        "WS-POL-001-05-revision-resubmission-real-api-drill.md": (
            "`auto_checking` to `evaluation_pending`",
            "and audit-event `from_status`/`to_status` values from `auto_checking` to",
            "scripts, active docs, or real API drill output still depend on `auto_checking`.",
            "can contain `auto_checking`.",
            "The status rename is part of this proof. `auto_checking` is vague",
            "Those docs may only be changed to replace `auto_checking` with the canonical",
            "`auto_checking` with the canonical `evaluation_pending` lifecycle wording",
            "- [ ] `auto_checking` is replaced in current runtime code, tests, scripts, and",
            "already contain `auto_checking`. If the PR does not add a migration",
            "`auto_checking`.",
            "`audit_events.to_status` contains `auto_checking` after upgrade/drill.",
            "scripts, docs, or real API drill output still depend on `auto_checking`.",
            "replaces `auto_checking`.",
        ),
        "backend/alembic/versions/0009_evaluation_pending_status.py": (
            'OLD_STATUS = "auto_checking"',
        ),
        "backend/tests/test_alembic.py": (
            'LEGACY_EVALUATION_STATUS = "auto_checking"',
        ),
        "backend/scripts/week2_api_e2e.py": (
            'LEGACY_EVALUATION_STATUS = "auto_checking"',
        ),
    },
    "auto\\s*[\"']?\\s*\\\\?\\s*\\+\\s*[\"']?_checking": {},
}


def tracked_and_new_files() -> list[Path]:
    """Return tracked and untracked files that should be scanned."""
    tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"],
        text=True,
    ).splitlines()
    paths = []
    for raw_path in tracked + untracked:
        path = Path(raw_path)
        if (
            raw_path in HISTORICAL_PATHS
            or raw_path in SKIP_FILES
            or raw_path.startswith(SKIP_PREFIXES)
            or any(part in SKIP_DIRS for part in path.parts)
        ):
            continue
        if path.is_file():
            paths.append(path)
    return paths


def forbidden_path_failures(paths: list[Path]) -> list[str]:
    """Return failures for forbidden tool-specific files or directories."""
    failures: list[str] = []
    for path in paths:
        raw_path = path.as_posix()
        for pattern in FORBIDDEN_PATH_PATTERNS:
            if pattern.search(raw_path):
                failures.append(
                    f"{raw_path}: forbidden Codex-incompatible path /{pattern.pattern}/i"
                )
    return failures


def is_active_shared_contract_path(path: Path) -> bool:
    """Return whether a path defines the live cross-subsystem product contract."""
    raw_path = path.as_posix()
    if raw_path in HISTORICAL_PATHS:
        return False
    if raw_path in {"AGENTS.md", "README.md"}:
        return True
    if raw_path in {".agent-loop/LOOP_STATE.md", ".agent-loop/WORK_QUEUE.md"}:
        return True
    if raw_path.startswith(".agent-loop/initiatives/"):
        return "/reviews/" not in raw_path and path.suffix in {".json", ".md"}
    if raw_path.startswith(".agent-loop/policies/"):
        return path.suffix == ".md"
    if not raw_path.startswith("docs/") or path.suffix not in {".html", ".md", ".puml"}:
        return False
    if raw_path.startswith(ACTIVE_SHARED_CONTRACT_EXCLUDED_PREFIXES):
        return False
    return True


def read_text(path: Path) -> str | None:
    """Read text files and ignore binary or unreadable files."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    allowed_prefixes = ALLOWLISTED_LINES.get(path.as_posix(), ())
    if allowed_prefixes:
        return "\n".join(
            line
            for line in text.splitlines()
            if not any(allowed_prefix in line for allowed_prefix in allowed_prefixes)
        )
    return text


def line_number_for_offset(text: str, offset: int) -> int:
    """Return the one-based line number for a character offset."""
    return text.count("\n", 0, offset) + 1


def line_at_offset(text: str, offset: int) -> str:
    """Return the full line containing a character offset."""
    line_start = text.rfind("\n", 0, offset) + 1
    line_end = text.find("\n", offset)
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end]


def main() -> int:
    """Run the stale wording check."""
    paths = tracked_and_new_files()
    failures: list[str] = forbidden_path_failures(paths)
    for path in paths:
        text = read_text(path)
        if text is None:
            continue
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.pattern in FULL_TEXT_FORBIDDEN_PATTERNS:
                matches = pattern.finditer(text)
            else:
                matches = pattern.finditer(text)
            for match in matches:
                line_number = line_number_for_offset(text, match.start())
                line = line_at_offset(text, match.start())
                allowed_lines = ALLOWLISTED_PATTERN_LINES.get(pattern.pattern, {})
                allowed_fragments = allowed_lines.get(path.as_posix(), ())
                if any(fragment in line for fragment in allowed_fragments):
                    continue
                failures.append(
                    f"{path}:{line_number}: contains stale wording /{pattern.pattern}/i"
                )
        if is_active_shared_contract_path(path):
            for pattern in ACTIVE_SHARED_CONTRACT_PATTERNS:
                for match in pattern.finditer(text):
                    line_number = line_number_for_offset(text, match.start())
                    line = line_at_offset(text, match.start())
                    exempt_fragments = ACTIVE_COMPENSATION_LINE_EXEMPTIONS.get(
                        path.as_posix(), ()
                    )
                    if any(fragment in line for fragment in exempt_fragments):
                        continue
                    failures.append(
                        f"{path}:{line_number}: active shared contract contains retired "
                        f"compensation wording /{pattern.pattern}/i"
                    )
        if path.as_posix() in CURRENT_RUNTIME_CONTRACT_PATHS:
            for pattern in UNIMPLEMENTED_CURRENT_RUNTIME_COMPENSATION_PATTERNS:
                for match in pattern.finditer(text):
                    line_number = line_number_for_offset(text, match.start())
                    failures.append(
                        f"{path}:{line_number}: current runtime walkthrough claims "
                        f"unimplemented compensation record /{pattern.pattern}/"
                    )

    if failures:
        print("Stale wording check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Stale wording check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
