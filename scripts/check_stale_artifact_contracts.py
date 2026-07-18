#!/usr/bin/env python3
"""Reject stale artifact contracts after each owning cutover activates."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# ARTIFACT_CONTRACT_PHASE: artifact_store_cutover
ARTIFACT_CONTRACT_PHASE = "artifact_store_cutover"

PHASES = (
    "foundation",
    "artifact_store_cutover",
    "guide_source_cutover",
    "upload_admission",
    "submission_cutover",
    "checker_cutover",
)

HISTORICAL_PREFIXES = (
    "docs/internal_reviews/",
    "docs/reference_specs/",
)
# Keep exact historical exceptions aligned with the authorization wording gate.
# Prefixes above remain useful for review/reference trees, while this set covers
# standalone closed records and implemented plans outside those trees.
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
AGENT_LOOP_INITIATIVE_PREFIX = ".agent-loop/initiatives/"
ACTIVE_POLICY_PREFIX = ".agent-loop/policies/"
ACTIVE_LOOP_PATHS = {
    ".agent-loop/LOOP_STATE.md",
    ".agent-loop/MEMORY.md",
    ".agent-loop/REVIEW_LOG.md",
    ".agent-loop/WORK_QUEUE.md",
}
TEXT_SUFFIXES = {
    ".html",
    ".json",
    ".lock",
    ".md",
    ".puml",
    ".py",
    ".rst",
    ".sh",
    ".svg",
    ".tf",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
FOUNDATION_INTERFACE_PATHS = {
    "backend/app/interfaces/artifacts.py",
    "backend/app/modules/artifacts/contracts.py",
}
FOUNDATION_INTERFACE_PREFIXES = ("contracts/artifact-store/",)
DEFERRED_PROVIDER_RUNTIME_PREFIXES = (
    "backend/app/",
    "backend/alembic/",
    "backend/scripts/",
    "backend/requirements",
    "frontend/",
    ".github/workflows/",
    "config/",
    "docker/",
    "ops/",
    "services/",
    "deploy/",
    "deployment/",
    "infra/",
    "infrastructure/",
    "k8s/",
    "helm/",
    "charts/",
)
DEFERRED_PROVIDER_RUNTIME_PATHS = {
    "backend/pyproject.toml",
    "backend/Pipfile",
    "backend/Pipfile.lock",
    "backend/poetry.lock",
    "backend/uv.lock",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}
R2_RUNTIME_FILENAMES = (
    "compose.",
    "docker-compose.",
    "Dockerfile",
    ".env",
)
R2_RUNTIME_PATTERN = re.compile(
    r"(?:\br2(?:[_A-Za-z0-9]+)?\b|"
    r"\b[A-Za-z][A-Za-z0-9_]*r2[A-Za-z0-9_]*\b|"
    r"r2\.cloudflarestorage\.com|"
    r"\bCloudflare[A-Za-z0-9_]*\b|\bcloudflare\b)",
    re.IGNORECASE,
)
R2_ACTIVATION_PATTERN = re.compile(
    r"(?:\b(?:Cloudflare\s+)?R2\b(?:[^.;!?]|\.(?=\d)){0,120}\bdeferred\b"
    r"(?:[^.;!?]|\.(?=\d)){0,80}"
    r"\b(?:but|yet|although|and)\b\s+(?:it\s+)?(?:is\s+)?(?:the\s+|an?\s+)?"
    r"(?:eligible|enabled|supported|active|production|hosted)\b|"
    r"\b(?:enable|activate|support|use)\s+(?:Cloudflare\s+)?R2\b|"
    r"\b(?:Cloudflare\s+)?R2\b[^.;!?]{0,180}"
    r"(?:\b(?:is|are|remains?|becomes?)\s+"
    r"(?!not\b|outside\b|deferred\b)[^.;!?]{0,50}"
    r"\b(?:eligible|enabled|supported|active|production|hosted)\b|"
    r"\b(?:for|in)\s+(?:v0\.1|production|hosted)\b|"
    r"\b(?:v0\.1|production|hosted)\s+(?:object[- ]store\s+)?provider\b))",
    re.IGNORECASE,
)
FLOW_NODE_ACTIVATION_PATTERN = re.compile(
    r"(?:\bFlow\s+Node\b(?:[^.;!?]|\.(?=\d)){0,120}\bdeferred\b"
    r"(?:[^.;!?]|\.(?=\d)){0,80}"
    r"\b(?:but|yet|although|and)\b\s+(?:it\s+)?(?:is\s+)?(?:the\s+|an?\s+)?"
    r"(?:eligible|enabled|supported|active|production|hosted)\b|"
    r"\bFlow\s+Node\b[^.;!?]{0,180}\b"
    r"(?:remains?|preserved\s+as|is)\b[^.;!?]{0,60}"
    r"\bv0\.1\s+production\s+(?:artifact\s+)?provider\b|"
    r"\b(?:enable|activate|support|use)\s+Flow\s+Node\b|"
    r"\bFlow\s+Node\b[^.;!?]{0,180}"
    r"(?:\b(?:is|are|remains?|becomes?|preserved\s+as)\s+"
    r"(?!not\b|outside\b|deferred\b)[^.;!?]{0,50}"
    r"\b(?:eligible|enabled|supported|active|production|hosted)\b|"
    r"\b(?:for|in)\s+(?:v0\.1|production|hosted)\b|"
    r"\b(?:v0\.1|production|hosted)\s+(?:artifact\s+)?provider\b))",
    re.IGNORECASE,
)
R2_DEFERRAL_OVERRIDE_PATTERN = re.compile(
    r"\b(?:Cloudflare\s+)?R2\b[^.;!?]{0,160}\b(?:shall|will|must|continues?|"
    r"ship(?:s|ped)?|deploy(?:s|ed)?)\b[^.;!?]{0,100}\b(?:active|"
    r"backend|hosted|production|provider|runtime|ship|deploy|alongside)\b",
    re.IGNORECASE,
)
FLOW_NODE_DEFERRAL_OVERRIDE_PATTERN = re.compile(
    r"\bFlow\s+Node\b[^.;!?]{0,160}\b(?:shall|will|must|continues?|"
    r"ship(?:s|ped)?|deploy(?:s|ed)?)\b[^.;!?]{0,100}\b(?:active|"
    r"backend|hosted|production|provider|runtime|ship|deploy|alongside)\b",
    re.IGNORECASE,
)
LEGACY_R2_RUNTIME_LINES = {
    "backend/app/modules/projects/service.py": (
        (
            "guide_source_cutover",
            'ALLOWED_SOURCE_REF_SCHEMES = {"https", "http", "repo", "inline", "import", "s3", "r2"}',
        ),
        (
            "submission_cutover",
            'DEFAULT_ALLOWED_STORAGE_SCHEMES = ["local", "s3", "r2"]',
        ),
    ),
    "backend/app/modules/projects/schemas.py": (
        (
            "submission_cutover",
            'allowed_storage_schemes: list[Literal["local", "s3", "r2"]] = Field(',
        ),
        (
            "submission_cutover",
            'default_factory=lambda: ["local", "s3", "r2"]',
        ),
    ),
    "backend/app/adapters/project_agents/openai_agent_sdk.py": (
        (
            "submission_cutover",
            '"allowed_storage_schemes": ["local", "s3", "r2"],',
        ),
    ),
    "backend/app/modules/checkers/runner.py": (
        (
            "submission_cutover",
            '"Add sha256:<token> hash values for evidence objects stored in local, R2, or S3 storage.",',
        ),
    ),
    "backend/scripts/api_contract_e2e.py": (
        (
            "submission_cutover",
            '"allowed_storage_schemes": ["local", "s3", "r2"],',
        ),
    ),
    "backend/app/modules/tasks/schemas.py": (
        (
            "submission_cutover",
            'ALLOWED_STORAGE_URI_PREFIXES = ("local://", "s3://", "r2://")',
        ),
        (
            "submission_cutover",
            'raise ValueError("uri must be a local, R2, or S3 object reference")',
        ),
        (
            "submission_cutover",
            'if matching_prefix in {"s3://", "r2://"} and (not parsed.netloc or not parsed.path.strip("/")):',
        ),
    ),
}
LIVE_RULE_PATHS = {
    "LEGACY_FLOW_NODE_RUNTIME": (*DEFERRED_PROVIDER_RUNTIME_PREFIXES,),
    "LEGACY_GUIDE_CONTENT_CID": (
        "backend/app/interfaces/project_agents.py",
        "backend/app/modules/projects/",
    ),
    "LEGACY_SUBMISSION_TRANSPORT": (
        "backend/app/modules/tasks/",
        "backend/app/modules/checkers/",
        "backend/scripts/api_contract_e2e.py",
        "backend/scripts/week2_api_e2e.py",
        "examples/terminal_benchmark/terminal_benchmark_api_e2e.py",
    ),
    "LEGACY_PROJECT_STORAGE_POLICY": (
        "backend/app/adapters/project_agents/",
        "backend/app/interfaces/project_agents.py",
        "backend/app/modules/projects/",
        "backend/app/modules/checkers/",
        "backend/app/modules/tasks/",
        "backend/scripts/api_contract_e2e.py",
        "backend/scripts/week2_api_e2e.py",
        "examples/terminal_benchmark/terminal_benchmark_api_e2e.py",
    ),
    "LEGACY_STORAGE_COMPILER_PRIMITIVE": (
        "backend/app/adapters/project_agents/",
        "backend/app/interfaces/project_agents.py",
        "backend/app/modules/projects/",
        "backend/app/modules/checkers/",
        "backend/app/modules/tasks/",
        "backend/scripts/week2_api_e2e.py",
        "examples/terminal_benchmark/terminal_benchmark_api_e2e.py",
    ),
    "LEGACY_CHECKER_ARTIFACT_COPY": (
        "backend/app/modules/tasks/",
        "backend/app/modules/checkers/",
    ),
}


def active_initiative_prefixes(root: Path = ROOT) -> tuple[str, ...]:
    """Derive live initiative directories from in-progress and planned rows."""
    queue_path = root / ".agent-loop/WORK_QUEUE.md"
    if not queue_path.is_file():
        return ()
    queue = queue_path.read_text(encoding="utf-8")
    try:
        in_progress = queue.split("## In Progress", maxsplit=1)[1].split(
            "## Planned Next",
            maxsplit=1,
        )[0]
        planned_next = queue.split("## Planned Next", maxsplit=1)[1].split(
            "## Completed",
            maxsplit=1,
        )[0]
    except IndexError as exc:
        raise ValueError("malformed Work Queue headings") from exc
    initiative_ids = {
        match.group(1)
        for chunk in re.findall(r"\| `([^`]+)` \|", in_progress + planned_next)
        if (match := re.match(r"([A-Z]+-[A-Z]+-\d+)", chunk))
    }
    initiative_root = root / AGENT_LOOP_INITIATIVE_PREFIX
    if not initiative_root.is_dir():
        return ()
    return tuple(
        f"{AGENT_LOOP_INITIATIVE_PREFIX}{path.name}/"
        for path in sorted(initiative_root.iterdir())
        if path.is_dir() and any(path.name.startswith(item) for item in initiative_ids)
    )


@dataclass(frozen=True)
class Rule:
    """One obsolete term and the phase that begins rejecting it."""

    code: str
    active_from: str
    pattern: re.Pattern[str]


RULES = (
    Rule(
        "STALE_AWS_RUNTIME_NO_LIST",
        "foundation",
        re.compile(
            r"\bRuntime credentials\b(?:"
            r"[^.!?]{0,180}\b(?:cannot|could not|must not|do not)\b"
            r"[^.!?]{0,80}\blist\b|"
            r"[^.!?]{0,180}[.!?]\s+They\s+"
            r"(?:cannot|could not|must not|do not)\b[^.!?]{0,80}\blist\b)",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "AMBIGUOUS_S3_ADAPTER_NAME",
        "foundation",
        re.compile(r"\bS3ArtifactStore\b"),
    ),
    Rule(
        "ACTIVE_R2_V01_PLAN",
        "foundation",
        re.compile(
            r"(?:\bWS-ART-001-02B[23]\b|\b(?:Cloudflare\s+)?R2\b)", re.IGNORECASE
        ),
    ),
    Rule(
        "OBSOLETE_FLOW_NODE_PLAN",
        "foundation",
        re.compile(
            r"(?:\bFN-ART-001\b|\bWS-ART-001-02-flow-node-adapter|"
            r"Flow Node[^.!?\n]{0,80}\b(?:v0\.1|production)\b|"
            r"\b(?:v0\.1|production)\b[^.!?\n]{0,80}Flow Node|"
            r"Flow Node[^.!?\n]{0,180}\b(?:hosted|active|enabled|supported)\s+"
            r"(?:backend|provider|runtime)\b)",
            re.IGNORECASE,
        ),
    ),
    Rule(
        "PROVIDER_SPECIFIC_GENERIC_INTERFACE",
        "foundation",
        re.compile(r"\b(?:cid|dag|pins?|pinned|pinning)\b", re.IGNORECASE),
    ),
    Rule(
        "LEGACY_FLOW_NODE_RUNTIME",
        "artifact_store_cutover",
        re.compile(r"\bflow_node\b", re.IGNORECASE),
    ),
    Rule(
        "LEGACY_GUIDE_CONTENT_CID",
        "guide_source_cutover",
        re.compile(r"\bcontent_cid\b"),
    ),
    Rule(
        "LEGACY_SUBMISSION_TRANSPORT",
        "submission_cutover",
        re.compile(
            r"\b(?:package_uri|package_hash|artifact_hash_manifest|worker_attestation)\b"
        ),
    ),
    Rule(
        "LEGACY_PROJECT_STORAGE_POLICY",
        "submission_cutover",
        re.compile(
            r"\b(?:manifest_required|artifact_hash_required|artifact_hash_algorithm|"
            r"allowed_storage_schemes)\b"
        ),
    ),
    Rule(
        "LEGACY_CALLER_STORAGE_SCHEME",
        "submission_cutover",
        re.compile(r"\b(?:local|s3|r2)://", re.IGNORECASE),
    ),
    Rule(
        "LEGACY_STORAGE_COMPILER_PRIMITIVE",
        "submission_cutover",
        re.compile(
            r"\b(?:enforce_storage_scheme|verify_hash|require_manifest_field)\b"
        ),
    ),
    Rule(
        "LEGACY_CHECKER_ARTIFACT_COPY",
        "checker_cutover",
        re.compile(r"\b(?:artifact_manifest_hash|checker_artifact_manifest)\b"),
    ),
)


def phase_index(phase: str) -> int:
    """Return the phase index or fail closed for an unknown marker."""
    if not isinstance(phase, str) or phase not in PHASES:
        raise ValueError(f"malformed artifact contract phase: {phase!r}")
    return PHASES.index(phase)


def rules_for_phase(phase: str) -> tuple[Rule, ...]:
    """Return rules whose owning phase is active at ``phase``."""
    current = phase_index(phase)
    return tuple(rule for rule in RULES if phase_index(rule.active_from) <= current)


def path_is_scannable(relative_path: str, root: Path = ROOT) -> bool:
    """Return whether a live source or document path should be scanned."""
    active_prefixes = active_initiative_prefixes(root)
    path = Path(relative_path)
    is_review_history = (
        relative_path.startswith(AGENT_LOOP_INITIATIVE_PREFIX)
        and "/reviews/" in relative_path
    )
    is_text_path = (
        path.suffix.lower() in TEXT_SUFFIXES
        or path.name.startswith(R2_RUNTIME_FILENAMES)
        or relative_path.startswith(DEFERRED_PROVIDER_RUNTIME_PREFIXES)
        or relative_path in DEFERRED_PROVIDER_RUNTIME_PATHS
    )
    return (
        is_text_path
        and not relative_path.startswith(HISTORICAL_PREFIXES)
        and relative_path not in HISTORICAL_PATHS
        and not is_review_history
        and (
            not relative_path.startswith(".agent-loop/")
            or relative_path in ACTIVE_LOOP_PATHS
            or relative_path.startswith(ACTIVE_POLICY_PREFIX)
            or relative_path.startswith(active_prefixes)
        )
        and relative_path != "scripts/check_stale_artifact_contracts.py"
    )


def path_is_active_contract(relative_path: str, root: Path = ROOT) -> bool:
    """Return whether a path carries current artifact architecture wording."""
    if relative_path == ".agent-loop/REVIEW_LOG.md":
        return False
    if relative_path in {"AGENTS.md", "README.md", *ACTIVE_LOOP_PATHS}:
        return True
    if relative_path.startswith(ACTIVE_POLICY_PREFIX):
        return True
    if relative_path.startswith("docs/"):
        return (
            not relative_path.startswith(HISTORICAL_PREFIXES)
            and relative_path not in HISTORICAL_PATHS
        )
    return relative_path.startswith(
        active_initiative_prefixes(root)
    ) and "/reviews/" not in (relative_path)


def active_work_queue_text(text: str) -> str:
    """Keep only live Work Queue sections while preserving source line numbers."""
    active_headings = {"## In Progress", "## Planned Next"}
    section = ""
    output: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            section = line.strip()
        output.append(
            line if section in active_headings else "\n" if line.endswith("\n") else ""
        )
    if not active_headings.issubset(set(text.splitlines())):
        raise ValueError("malformed Work Queue headings")
    return "".join(output)


def rule_applies_to_path(rule: Rule, relative_path: str, root: Path = ROOT) -> bool:
    """Limit each rule to its owning active contract or runtime boundary."""
    if rule.code == "PROVIDER_SPECIFIC_GENERIC_INTERFACE":
        return relative_path in FOUNDATION_INTERFACE_PATHS or relative_path.startswith(
            FOUNDATION_INTERFACE_PREFIXES
        )
    if rule.code == "ACTIVE_R2_V01_PLAN":
        return path_is_active_contract(relative_path, root)
    if rule.code == "OBSOLETE_FLOW_NODE_PLAN":
        return path_is_active_contract(relative_path, root)
    if rule.code in LIVE_RULE_PATHS:
        return (
            relative_path.startswith("docs/")
            and path_is_active_contract(relative_path, root)
        ) or relative_path.startswith(LIVE_RULE_PATHS[rule.code])
    if rule.code == "LEGACY_CALLER_STORAGE_SCHEME":
        return (
            relative_path.startswith("docs/")
            and path_is_active_contract(relative_path, root)
        ) or relative_path.startswith(
            (
                "backend/app/modules/projects/",
                "backend/app/modules/tasks/",
                "backend/app/modules/checkers/",
                "backend/scripts/api_contract_e2e.py",
                "backend/scripts/week2_api_e2e.py",
                "examples/terminal_benchmark/terminal_benchmark_api_e2e.py",
            )
        )
    return True


def has_explicit_r2_deferral(line_text: str) -> bool:
    """Accept only clauses that unambiguously keep R2 outside active v0.1."""
    if R2_ACTIVATION_PATTERN.search(line_text) or R2_DEFERRAL_OVERRIDE_PATTERN.search(
        line_text
    ):
        return False
    return bool(
        re.search(
            r"(?:\b(?:Cloudflare\s+)?R2\b[^\n]{0,240}"
            r"\b(?:is\s+)?(?:deferred|not\s+(?:an?\s+)?v0\.1|outside\s+v0\.1|"
            r"ha(?:s|ve)\s+no\s+active|ha(?:s|ve)\s+no\s+provider|"
            r"ha(?:s|ve)\s+no\s+v0\.1|"
            r"is\s+removed|(?:values?|tokens?|inputs?)\s+are\s+legacy|"
            r"legacy\s+input)\b|"
            r"\bdefer(?:red|s|ring)?\b[^\n]{0,80}\b(?:Cloudflare\s+)?R2\b|"
            r"\b(?:no|remove(?:d|s)?)\b[^\n]{0,80}\b(?:Cloudflare\s+)?R2\b|"
            r"\blater\s+(?:approved\s+)?(?:Cloudflare\s+)?R2\s+adoption\b)",
            line_text,
            re.IGNORECASE,
        )
    )


def has_explicit_flow_node_deferral(clause_text: str) -> bool:
    """Accept Flow Node wording only when it cannot activate v0.1."""
    if FLOW_NODE_ACTIVATION_PATTERN.search(
        clause_text
    ) or FLOW_NODE_DEFERRAL_OVERRIDE_PATTERN.search(clause_text):
        return False
    return bool(
        re.search(
            r"(?:\bFlow\s+Node\b[^\n]{0,180}\b(?:is\s+)?"
            r"(?:deferred|not\s+(?:an?\s+)?v0\.1|outside\s+v0\.1|"
            r"cannot\s+block|has\s+no\s+active|superseded)\b|"
            r"\bdefer(?:red|s|ring)?\b[^\n]{0,80}\bFlow\s+Node\b)",
            clause_text,
            re.IGNORECASE,
        )
    )


def is_r2_provider_reference(line_text: str) -> bool:
    """Distinguish Cloudflare R2 storage from unrelated revision/risk labels."""
    if re.search(r"\bCloudflare\s+R2\b|\br2://", line_text, re.IGNORECASE):
        return True
    return bool(
        re.search(r"\bR2\b", line_text, re.IGNORECASE)
        and re.search(
            r"\b(?:object|storage|store|provider|credential|runtime|adapter|"
            r"production|v0\.1|hosted|enable|support|eligible|dependency|"
            r"transport|endpoint|sidecar|secret|deployment)\b",
            line_text,
            re.IGNORECASE,
        )
    )


def clause_around(text: str, offset: int) -> str:
    """Return the bounded sentence/clause containing an artifact term."""
    lower_bound = max(0, offset - 320)
    upper_bound = min(len(text), offset + 320)
    before = text[lower_bound:offset]
    after = text[offset:upper_bound]
    delimiters = re.compile(r"[;!?]|(?<!\d)\.(?!\d)")
    previous_matches = list(delimiters.finditer(before))
    following_match = delimiters.search(after)
    start = (
        lower_bound + previous_matches[-1].end() if previous_matches else lower_bound
    )
    end = offset + following_match.end() if following_match else upper_bound
    return " ".join(text[start:end].split())


def scan_text(
    relative_path: str, text: str, phase: str, root: Path = ROOT
) -> list[str]:
    """Return deterministic stale-contract failures for one text file."""
    failures: list[str] = []
    if relative_path == ".agent-loop/WORK_QUEUE.md":
        text = active_work_queue_text(text)
    normalized_text = text.replace(r"\n", "  ")
    for rule in rules_for_phase(phase):
        if not rule_applies_to_path(rule, relative_path, root):
            continue
        for match in rule.pattern.finditer(normalized_text):
            line = normalized_text.count("\n", 0, match.start()) + 1
            line_text = text.splitlines()[line - 1]
            if rule.code == "ACTIVE_R2_V01_PLAN":
                if match.group(0).upper().startswith("WS-ART-001-02B"):
                    failures.append(f"{relative_path}:{line}: {rule.code}")
                    continue
                clause_text = clause_around(normalized_text, match.start())
                provider_reference_text = (
                    clause_text
                    if "cloudflare" in match.group(0).lower() or r"\n" in line_text
                    else line_text
                )
                if not is_r2_provider_reference(provider_reference_text):
                    continue
                if has_explicit_r2_deferral(clause_text):
                    continue
            if rule.code == "OBSOLETE_FLOW_NODE_PLAN":
                clause_text = clause_around(normalized_text, match.start())
                if has_explicit_flow_node_deferral(clause_text):
                    continue
            failures.append(f"{relative_path}:{line}: {rule.code}")
    is_r2_runtime_path = (
        relative_path.startswith(DEFERRED_PROVIDER_RUNTIME_PREFIXES)
        or relative_path in DEFERRED_PROVIDER_RUNTIME_PATHS
        or Path(relative_path).name.startswith(R2_RUNTIME_FILENAMES)
    )
    if is_r2_runtime_path:
        for match in R2_RUNTIME_PATTERN.finditer(normalized_text):
            line = normalized_text.count("\n", 0, match.start()) + 1
            line_text = text.splitlines()[line - 1].strip()
            if any(
                phase_index(phase) < phase_index(removal_phase)
                and line_text == allowed_line
                for removal_phase, allowed_line in LEGACY_R2_RUNTIME_LINES.get(
                    relative_path,
                    (),
                )
            ):
                continue
            failures.append(f"{relative_path}:{line}: DEFERRED_R2_RUNTIME")
    return list(dict.fromkeys(failures))


def git_lines(root: Path, *args: str) -> list[str]:
    """Return non-empty path lines from Git."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [line for line in result.stdout.splitlines() if line]


def discover_paths(root: Path = ROOT) -> list[Path]:
    """Discover tracked and untracked active text files."""
    relative_paths = git_lines(root, "ls-files")
    relative_paths.extend(git_lines(root, "ls-files", "--others", "--exclude-standard"))
    paths: list[Path] = []
    for relative_path in dict.fromkeys(relative_paths):
        if not path_is_scannable(relative_path, root):
            continue
        path = root / relative_path
        if path.is_file():
            paths.append(path)
    return paths


def scan(root: Path = ROOT, phase: str | None = None) -> list[str]:
    """Scan the repository at an explicitly validated artifact phase."""
    if phase is None:
        phase = ARTIFACT_CONTRACT_PHASE
    phase_index(phase)
    failures: list[str] = []
    for path in discover_paths(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            relative_path = path.relative_to(root).as_posix()
            failures.append(
                f"{relative_path}:0: UNREADABLE_ACTIVE_TEXT ({type(exc).__name__})"
            )
            continue
        failures.extend(scan_text(path.relative_to(root).as_posix(), text, phase, root))
    return failures


def main() -> int:
    """Run the phased stale artifact contract check."""
    try:
        failures = scan()
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"Stale artifact contract check failed closed: {exc}", file=sys.stderr)
        return 1

    if failures:
        print(
            f"Stale artifact contract check failed at phase {ARTIFACT_CONTRACT_PHASE}:",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"Stale artifact contract check passed at phase {ARTIFACT_CONTRACT_PHASE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
