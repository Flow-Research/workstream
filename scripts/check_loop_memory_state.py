"""Validate merged loop memory is not left in a pre-merge state."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKED_FILES = (
    ".agent-loop/LOOP_STATE.md",
    ".agent-loop/WORK_QUEUE.md",
    ".agent-loop/REVIEW_LOG.md",
)
INITIATIVE_STATUS_FILES = tuple(
    str(path.relative_to(ROOT))
    for path in (ROOT / ".agent-loop/initiatives").glob("*/STATUS.md")
)
STATUS_BEARING_CONTRACT_FILES = (
    (
        ".agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/chunks/"
        "WS-ART-001-OBJECT-STORAGE-AMENDMENT.md"
    ),
)
FORBIDDEN_PATTERNS = (
    (re.compile(r"PR #\d+ open", re.IGNORECASE), "merged main cannot list an open PR"),
    (
        re.compile(r"awaiting human merge decision", re.IGNORECASE),
        "merged main cannot await a merge decision",
    ),
    (
        re.compile(r"human merge checkpoint", re.IGNORECASE),
        "merged main cannot remain at the human merge checkpoint",
    ),
    (
        re.compile(r"CI ready for final rerun", re.IGNORECASE),
        "merged main cannot wait for final CI rerun",
    ),
    (
        re.compile(r"Push the reviewed revision", re.IGNORECASE),
        "merged main cannot instruct pushing reviewed revision",
    ),
    (
        re.compile(
            r"CodeRabbit, then stop for the user-owned merge decision", re.IGNORECASE
        ),
        "merged main cannot wait for external review before merge",
    ),
    (
        re.compile(
            r"\|\s*`[^`]+`\s*\|[^|]+\|[^|]+\|\s*In progress\s*\|", re.IGNORECASE
        ),
        "merged main cannot keep a completed chunk in active In progress state",
    ),
    (
        re.compile(r"AUTH-05B[^\n]*publication is pending", re.IGNORECASE),
        "PR #119 is merged; AUTH-05B publication cannot remain pending",
    ),
    (
        re.compile(
            r"AUTH-05B.{0,300}(?:current gate is\s+PR publication|external checks)",
            re.IGNORECASE | re.DOTALL,
        ),
        "PR #119 is merged; AUTH-05B cannot remain at publication or external checks",
    ),
    (
        re.compile(r"`WS-AUTH-001-05B`\s*\|\s*In review", re.IGNORECASE),
        "PR #119 is merged; AUTH-05B cannot remain in review",
    ),
    (
        re.compile(r"PR #120's branch", re.IGNORECASE),
        "PR #120 is merged; its branch cannot remain active state",
    ),
    (
        re.compile(
            r"WS-ART-001-OBJECT-STORAGE-AMENDMENT.{0,200}Active planning",
            re.IGNORECASE | re.DOTALL,
        ),
        "PR #120 is merged; the artifact amendment cannot remain active",
    ),
    (
        re.compile(r"PR #122[^\n]*(?:pending|active)", re.IGNORECASE),
        "PR #122 is merged; it cannot remain pending or active",
    ),
    (
        re.compile(
            r"PR publication and external (?:review|checks) remain pending",
            re.IGNORECASE,
        ),
        "merged authored state cannot retain a pending publication claim",
    ),
)
GENERATED_FILES = (
    ".agent-loop/STATE.json",
    ".agent-loop/LOOP_STATE.md",
    ".agent-loop/MERGE_LOG.jsonl",
)
SCHEMA_VERSION = 2
STATE_BRANCH = "automation/loop-memory"
REQUIRED_CHECKS = ("agent-gates", "test", "CodeRabbit")
ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def checked_paths() -> list[Path]:
    """Return loop memory paths that must not contain pre-merge state."""
    paths = [ROOT / path for path in CHECKED_FILES]
    paths.extend(ROOT / path for path in INITIATIVE_STATUS_FILES)
    paths.extend(ROOT / path for path in STATUS_BEARING_CONTRACT_FILES)
    return paths


def _is_bounded_single_line(value: object, maximum: int) -> bool:
    """Return whether one value is a bounded non-empty single-line string."""
    if not isinstance(value, str):
        return False
    normalized = value.strip()
    return bool(normalized) and len(normalized) <= maximum and not any(
        ord(char) < 32 for char in normalized
    )


def _is_valid_lifecycle_id(value: object) -> bool:
    """Return whether one lifecycle ID has canonical syntax and bounds."""
    return _is_bounded_single_line(value, 80) and bool(ID_PATTERN.fullmatch(value))


def _is_current_schema_version(value: object) -> bool:
    """Return whether value is exactly the supported integer schema version."""
    return type(value) is int and value == SCHEMA_VERSION


def _metadata_failures(metadata: object, label: str) -> list[str]:
    """Independently validate one completed-chunk metadata object."""
    expected = {
        "schema_version",
        "initiative_id",
        "chunk_id",
        "chunk_title",
        "next_chunk_id",
        "next_chunk_title",
        "next_requires_explicit_start",
    }
    if not isinstance(metadata, dict) or set(metadata) != expected:
        return [f"{label}: invalid completed-chunk schema"]
    failures: list[str] = []
    if not _is_current_schema_version(metadata.get("schema_version")):
        failures.append(f"{label}: unsupported completed-chunk schema version")
    initiative_id = metadata.get("initiative_id")
    chunk_id = metadata.get("chunk_id")
    next_chunk_id = metadata.get("next_chunk_id")
    next_chunk_title = metadata.get("next_chunk_title")
    if not _is_valid_lifecycle_id(initiative_id):
        failures.append(f"{label}: invalid initiative id")
    if (
        not _is_valid_lifecycle_id(chunk_id)
        or not isinstance(initiative_id, str)
        or not chunk_id.startswith(f"{initiative_id}-")
    ):
        failures.append(f"{label}: completed chunk does not belong to initiative")
    if not _is_bounded_single_line(metadata.get("chunk_title"), 160):
        failures.append(f"{label}: invalid completed chunk title")
    if (next_chunk_id is None) != (next_chunk_title is None):
        failures.append(f"{label}: incomplete next chunk metadata")
    if next_chunk_id is not None and (
        not _is_valid_lifecycle_id(next_chunk_id)
        or not isinstance(initiative_id, str)
        or not next_chunk_id.startswith(f"{initiative_id}-")
    ):
        failures.append(f"{label}: next chunk does not belong to initiative")
    if next_chunk_title is not None and not _is_bounded_single_line(
        next_chunk_title, 160
    ):
        failures.append(f"{label}: invalid next chunk title")
    if not isinstance(metadata.get("next_requires_explicit_start"), bool):
        failures.append(f"{label}: invalid explicit-start flag")
    return failures


def _record_failures(record: object, label: str) -> list[str]:
    """Independently validate one complete schema-v2 state record."""
    expected = {
        "schema_version",
        "repository",
        "state_branch",
        "updated_at",
        "source",
        "completed_chunk",
        "active",
        "gate",
        "checks",
    }
    if not isinstance(record, dict) or set(record) != expected:
        return [f"{label}: invalid record schema"]
    failures: list[str] = []
    if not _is_current_schema_version(record.get("schema_version")):
        failures.append(f"{label}: unsupported schema version")
    if record.get("state_branch") != STATE_BRANCH:
        failures.append(f"{label}: unexpected state branch")
    repository = record.get("repository")
    if not isinstance(repository, str) or not REPOSITORY_PATTERN.fullmatch(repository):
        failures.append(f"{label}: invalid repository")
    source = record.get("source")
    expected_source = {
        "main_sha",
        "first_parent_sha",
        "pr_number",
        "pr_url",
        "pr_title",
        "head_sha",
        "head_ref",
        "merged_at",
        "merged_by",
        "intent_path",
        "intent_blob_sha",
    }
    if not isinstance(source, dict) or set(source) != expected_source:
        failures.append(f"{label}: invalid source")
        source = {}
    for field in ("main_sha", "first_parent_sha", "head_sha", "intent_blob_sha"):
        value = source.get(field)
        if not isinstance(value, str) or not SHA_PATTERN.fullmatch(value):
            failures.append(f"{label}: invalid source {field}")
    pr_number = source.get("pr_number")
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number <= 0:
        failures.append(f"{label}: invalid source pr_number")
    if (
        isinstance(repository, str)
        and isinstance(pr_number, int)
        and not isinstance(pr_number, bool)
        and source.get("pr_url")
        != f"https://github.com/{repository}/pull/{pr_number}"
    ):
        failures.append(f"{label}: invalid source pr_url")
    for field, maximum in (("pr_title", 240), ("head_ref", 240), ("merged_by", 160)):
        value = source.get(field)
        if not _is_bounded_single_line(value, maximum):
            failures.append(f"{label}: invalid source {field}")
    merged_at = source.get("merged_at")
    try:
        parsed_time = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        failures.append(f"{label}: invalid source merged_at")
    else:
        if parsed_time.tzinfo is None:
            failures.append(f"{label}: source merged_at has no timezone")
    if record.get("updated_at") != merged_at:
        failures.append(f"{label}: updated_at does not match merged_at")
    metadata = record.get("completed_chunk")
    failures.extend(_metadata_failures(metadata, label))
    if isinstance(metadata, dict):
        expected_path = f".agent-loop/merge-intents/{metadata.get('chunk_id')}.json"
        if source.get("intent_path") != expected_path:
            failures.append(f"{label}: intent path does not match completed chunk")
        expected_gate = {
            "status": "stopped_after_merge",
            "next_chunk_id": metadata.get("next_chunk_id"),
            "next_chunk_title": metadata.get("next_chunk_title"),
            "next_requires_explicit_start": metadata.get(
                "next_requires_explicit_start"
            ),
        }
        if record.get("gate") != expected_gate:
            failures.append(f"{label}: next gate does not match completed chunk")
    if record.get("active") != {
        "planning_chunk": None,
        "implementation_chunk": None,
    }:
        failures.append(f"{label}: post-merge active state is not empty")
    checks = record.get("checks")
    if not isinstance(checks, dict) or set(checks) != {
        "required",
        "all_required_passed",
    }:
        failures.append(f"{label}: invalid check evidence")
    else:
        required = checks.get("required")
        if not isinstance(required, dict) or set(required) != set(REQUIRED_CHECKS):
            failures.append(f"{label}: incomplete required-check evidence")
        else:
            for name in REQUIRED_CHECKS:
                result = required[name]
                if not isinstance(result, dict) or set(result) != {
                    "kind",
                    "conclusion",
                    "url",
                }:
                    failures.append(f"{label}: invalid check evidence for {name}")
                    continue
                if not isinstance(result.get("kind"), str):
                    failures.append(f"{label}: invalid check kind for {name}")
                conclusion = result.get("conclusion")
                if conclusion is not None and not isinstance(conclusion, str):
                    failures.append(f"{label}: invalid check conclusion for {name}")
                url = result.get("url")
                if url is not None and not isinstance(url, str):
                    failures.append(f"{label}: invalid check URL for {name}")
            calculated = all(
                isinstance(required[name], dict)
                and required[name].get("conclusion") == "success"
                for name in REQUIRED_CHECKS
            )
            if checks.get("all_required_passed") is not calculated:
                failures.append(f"{label}: inconsistent aggregate check evidence")
    return failures


def _markdown_text(value: str) -> str:
    """Escape one bounded value for the independently rendered Markdown."""
    return (
        value.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _render_state(state: dict) -> str:
    """Independently render the expected human-readable state."""
    source = state["source"]
    completed = state["completed_chunk"]
    gate = state["gate"]
    checks = state["checks"]
    next_line = "- Next chunk: none recorded."
    if gate["next_chunk_id"]:
        start = (
            "requires a separate explicit start"
            if gate["next_requires_explicit_start"]
            else "may use an existing start signal"
        )
        next_line = (
            f"- Next chunk: `{gate['next_chunk_id']}` - "
            f"{_markdown_text(gate['next_chunk_title'])}; {start}."
        )
    check_lines = [
        f"  - `{name}`: `{checks['required'][name]['conclusion'] or 'missing'}`"
        for name in REQUIRED_CHECKS
    ]
    integrity = "passed" if checks["all_required_passed"] else "attention required"
    return "\n".join(
        [
            "# Generated Workstream Loop State",
            "",
            "> Canonical generated view. Do not edit this branch by hand.",
            "",
            f"- Repository: `{state['repository']}`",
            f"- Last merged PR: [#{source['pr_number']}]({source['pr_url']}) - "
            f"{_markdown_text(source['pr_title'])}",
            f"- Merge commit: `{source['main_sha']}`",
            f"- Final PR head: `{source['head_sha']}`",
            f"- Merged at: `{source['merged_at']}` by `{source['merged_by']}`",
            f"- Merge intent: `{source['intent_path']}` at blob "
            f"`{source['intent_blob_sha']}`",
            f"- Completed chunk: `{completed['chunk_id']}` - "
            f"{_markdown_text(completed['chunk_title'])}",
            "- Active planning chunk: none",
            "- Active implementation chunk: none",
            f"- Current gate: `{gate['status']}`",
            next_line,
            f"- Required check evidence: {integrity}",
            *check_lines,
            "",
            "Machine-readable state: `.agent-loop/STATE.json`",
            "Append-only merge ledger: `.agent-loop/MERGE_LOG.jsonl`",
            "",
        ]
    )


def generated_state_failures(root: Path) -> list[str]:
    """Return consistency failures for generated automation-branch state."""
    paths = [root / path for path in GENERATED_FILES]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        return [
            f"{path.relative_to(root)}: missing generated loop memory file"
            for path in missing
        ]
    try:
        state = json.loads(paths[0].read_text(encoding="utf-8"))
        ledger = [
            json.loads(line)
            for line in paths[2].read_text(encoding="utf-8").splitlines()
            if line
        ]
        rendered = paths[1].read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"generated loop memory is unreadable: {exc.__class__.__name__}"]
    if not isinstance(state, dict):
        return [".agent-loop/STATE.json: expected a JSON object"]
    failures = _record_failures(state, ".agent-loop/STATE.json")
    previous_hash = None
    previous_main_sha = None
    ledger_records = []
    expected_keys = {
        "schema_version",
        "previous_entry_hash",
        "record",
        "entry_hash",
    }
    for index, entry in enumerate(ledger):
        label = f".agent-loop/MERGE_LOG.jsonl:{index + 1}"
        if (
            not isinstance(entry, dict)
            or set(entry) != expected_keys
            or not _is_current_schema_version(entry.get("schema_version"))
        ):
            failures.append(f"{label}: invalid entry schema")
            break
        record = entry.get("record")
        if not isinstance(record, dict):
            failures.append(f"{label}: entry record is not an object")
            break
        failures.extend(_record_failures(record, label))
        payload = (
            f"{previous_hash or ''}\n"
            f"{json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=True)}"
        ).encode("utf-8")
        expected_hash = hashlib.sha256(payload).hexdigest()
        if (
            entry.get("previous_entry_hash") != previous_hash
            or entry.get("entry_hash") != expected_hash
        ):
            failures.append(f"{label}: hash chain is invalid")
            break
        source = record.get("source", {})
        if (
            previous_main_sha is not None
            and source.get("first_parent_sha") != previous_main_sha
        ):
            failures.append(f"{label}: first-parent chain is invalid")
            break
        previous_hash = expected_hash
        previous_main_sha = source.get("main_sha")
        ledger_records.append(record)
    if not ledger_records or ledger_records[-1] != state:
        failures.append(
            ".agent-loop/MERGE_LOG.jsonl: ledger tail does not match live state"
        )
    if not failures and rendered != _render_state(state):
        failures.append(
            ".agent-loop/LOOP_STATE.md: rendered state does not match canonical JSON"
        )
    return failures


def build_parser() -> argparse.ArgumentParser:
    """Build the loop-memory validator parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate generated automation state or authored main-branch memory."""
    args = build_parser().parse_args([] if argv is None else argv)
    if args.state_root:
        failures = generated_state_failures(args.state_root)
        if failures:
            print("Generated loop memory state is invalid:", file=sys.stderr)
            for failure in failures:
                print(f"- {failure}", file=sys.stderr)
            return 1
        print("Generated loop memory state check passed.")
        return 0

    failures: list[str] = []
    for path in checked_paths():
        if not path.exists():
            failures.append(f"{path.relative_to(ROOT)}: missing loop memory file")
            continue
        text = path.read_text(encoding="utf-8")
        for pattern, message in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(ROOT)}: {message}")

    if failures:
        print("Loop memory state is stale:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Loop memory state check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
