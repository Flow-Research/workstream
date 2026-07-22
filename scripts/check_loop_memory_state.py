"""Validate merged loop memory is not left in a pre-merge state."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
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
    ".agent-loop/WORK_QUEUE.md",
    ".agent-loop/MANIFEST.json",
)
INITIATIVE_STATE_ROOT = ".agent-loop/INITIATIVE_STATE"
SCHEMA_VERSION = 2
STATE_BRANCH = "automation/loop-memory"
REQUIRED_CHECKS = ("agent-gates", "test", "CodeRabbit")
ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
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
    return (
        bool(normalized)
        and len(normalized) <= maximum
        and not any(ord(char) < 32 for char in normalized)
    )


def _is_valid_lifecycle_id(value: object) -> bool:
    """Return whether one lifecycle ID has canonical syntax and bounds."""
    return _is_bounded_single_line(value, 80) and bool(ID_PATTERN.fullmatch(value))


def _is_current_schema_version(value: object) -> bool:
    """Return whether value is exactly the supported integer schema version."""
    return type(value) is int and value == SCHEMA_VERSION


def _selection_failures(selection: object, event: dict, label: str) -> list[str]:
    """Independently validate one signed start-selection envelope."""
    required = {
        "schema_version", "mode", "phase", "contract_path",
        "contract_title", "contract_blob_sha",
    }
    if not isinstance(selection, dict) or set(selection) != required:
        return [f"{label}: invalid start selection schema"]
    failures = []
    if selection.get("schema_version") != 1 or selection.get("mode") not in {
        "declared_successor", "writer_directed"
    } or selection.get("phase") not in {"planning", "implementation"}:
        failures.append(f"{label}: unsupported start selection")
    path = selection.get("contract_path")
    initiative = event.get("initiative_id")
    chunk = event.get("chunk_id")
    parts = path.split("/") if isinstance(path, str) else []
    if (
        not isinstance(path, str)
        or len(parts) != 5
        or parts[:2] != [".agent-loop", "initiatives"]
        or not (parts[2] == initiative or parts[2].startswith(f"{initiative}-"))
        or parts[3] != "chunks"
        or not (
            parts[4] == f"{chunk}.md"
            or (parts[4].startswith(f"{chunk}-") and parts[4].endswith(".md"))
        )
    ):
        failures.append(f"{label}: invalid selected contract path")
    if not _is_bounded_single_line(selection.get("contract_title"), 160):
        failures.append(f"{label}: invalid selected contract title")
    blob = selection.get("contract_blob_sha")
    if not isinstance(blob, str) or not SHA_PATTERN.fullmatch(blob):
        failures.append(f"{label}: invalid selected contract blob")
    return failures


def _selection_tree_failures(event: dict, repository_root: Path, label: str) -> list[str]:
    """Independently bind signed selection evidence to its exact Git tree."""
    selection = event.get("selection")
    if not isinstance(selection, dict):
        return []
    main_sha = event.get("main_sha")
    path = selection.get("contract_path")
    if not isinstance(main_sha, str) or not isinstance(path, str):
        return [f"{label}: selected contract has no exact Git identity"]
    tree = subprocess.run(
        ["git", "-C", str(repository_root), "ls-tree", main_sha, "--", path],
        check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    expected = f"100644 blob {selection.get('contract_blob_sha')}\t{path}"
    if tree.returncode != 0 or tree.stdout.strip() != expected:
        return [f"{label}: selected contract does not match exact main tree"]
    blob = subprocess.run(
        ["git", "-C", str(repository_root), "cat-file", "blob", selection["contract_blob_sha"]],
        check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        text = blob.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return [f"{label}: selected contract blob is not UTF-8"]
    chunk = event.get("chunk_id")
    heading = text.splitlines()[0] if text.splitlines() else ""
    titles = [
        heading.removeprefix(prefix).strip()
        for prefix in (f"# Chunk Contract: {chunk} - ", f"# Chunk Contract: {chunk} — ")
        if heading.startswith(prefix)
    ]
    if blob.returncode != 0 or titles != [selection.get("contract_title")]:
        return [f"{label}: selected contract title does not match exact blob"]
    phase_headings = re.findall(r"(?m)^## Start phase\s*$", text)
    phase_matches = re.findall(
        r"(?m)^## Start phase\s*\n\s*`?(planning|implementation)`?\s*$", text
    )
    if len(phase_headings) > 1 or len(phase_matches) > 1:
        return [f"{label}: selected contract phase is ambiguous"]
    declared_phase = phase_matches[0] if phase_matches else None
    if declared_phase and declared_phase != selection.get("phase"):
        return [f"{label}: selected contract phase does not match exact blob"]
    if selection.get("mode") == "writer_directed" and declared_phase is None:
        return [f"{label}: writer-directed contract has no exact phase declaration"]
    return []


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
    if (
        isinstance(record, dict)
        and isinstance(record.get("event"), dict)
        and record["event"].get("type") == "cutover"
    ):
        event = record["event"]
        base = json.loads(json.dumps(record))
        base.pop("event")
        failures = _record_failures(base, label)
        if set(event) != {"type", "main_sha", "legacy_exemptions"}:
            failures.append(f"{label}: invalid cutover event schema")
        elif (
            event.get("main_sha") != record.get("source", {}).get("main_sha")
            or event.get("legacy_exemptions") != record.get("legacy_exemptions")
        ):
            failures.append(f"{label}: cutover event does not match signed state")
        return failures
    if isinstance(record, dict) and "event" in record:
        event = record.get("event")
        if not isinstance(event, dict) or event.get("type") not in {"start", "cancel"}:
            return [f"{label}: invalid authority event"]
        base = json.loads(json.dumps(record))
        base.pop("event")
        authority = base.pop("authority_state", None)
        metadata = base.get("completed_chunk", {})
        source = base.get("source", {})
        base["updated_at"] = source.get("merged_at")
        failures = _record_failures(base, label)
        if not isinstance(authority, dict) or set(authority) != {
            "source", "completed_chunk", "active", "gate"
        }:
            failures.append(f"{label}: invalid authority lifecycle state")
            return failures
        metadata = authority["completed_chunk"]
        lifecycle = json.loads(json.dumps(base))
        lifecycle.update(authority)
        lifecycle_source = lifecycle.get("source", {})
        lifecycle["updated_at"] = lifecycle_source.get("merged_at")
        lifecycle_metadata = lifecycle.get("completed_chunk", {})
        lifecycle["active"] = {"planning_chunk": None, "implementation_chunk": None}
        lifecycle["gate"] = {
            "status": "stopped_after_merge",
            "next_chunk_id": lifecycle_metadata.get("next_chunk_id"),
            "next_chunk_title": lifecycle_metadata.get("next_chunk_title"),
            "next_requires_explicit_start": lifecycle_metadata.get(
                "next_requires_explicit_start"
            ),
        }
        failures.extend(_record_failures(lifecycle, f"{label} authority basis"))
        historical_event_keys = {
            "type", "event_id", "run_id", "created_at", "dispatcher",
            "approvers", "reason", "main_sha", "prior_state_tip",
            "initiative_id", "chunk_id",
        }
        dispatcher_event_keys = historical_event_keys - {"approvers"} | {
            "authorization"
        }
        selected_start_keys = dispatcher_event_keys | {"selection"}
        selected_cancel_keys = historical_event_keys | {"selection"}
        if set(event) not in (
            historical_event_keys, dispatcher_event_keys,
            selected_start_keys, selected_cancel_keys,
        ):
            failures.append(f"{label}: invalid authority event schema")
            return failures
        run_id = event.get("run_id")
        event_type = event["type"]
        if type(run_id) is not int or run_id <= 0 or event.get("event_id") != f"github-actions:{run_id}:{event_type}":
            failures.append(f"{label}: invalid authority event identity")
        for field, maximum in (("dispatcher", 160), ("reason", 500)):
            if not _is_bounded_single_line(event.get(field), maximum):
                failures.append(f"{label}: invalid event {field}")
        if "approvers" in event:
            approvers = event["approvers"]
            if not isinstance(approvers, list) or not approvers or any(
                not _is_bounded_single_line(value, 160) for value in approvers
            ) or event.get("dispatcher") in approvers or len(set(approvers)) != len(approvers):
                failures.append(f"{label}: invalid event approvers")
        else:
            authorization = event.get("authorization")
            legacy = {
                "schema_version": 1,
                "type": "github_workflow_dispatch",
                "actor": event.get("dispatcher"),
            }
            repository_permission = {
                "schema_version": 2,
                "type": "github_repository_permission",
                "actor": event.get("dispatcher"),
                "permission": (
                    authorization.get("permission")
                    if isinstance(authorization, dict) else None
                ),
            }
            if (
                event.get("type") != "start"
                or authorization not in (legacy, repository_permission)
                or (
                    authorization == repository_permission
                    and authorization["permission"] not in {"write", "push", "maintain", "admin"}
                )
            ):
                failures.append(f"{label}: invalid dispatcher authorization")
        selection = event.get("selection")
        if selection is not None:
            failures.extend(_selection_failures(selection, event, label))
        for field in ("main_sha", "prior_state_tip"):
            value = event.get(field)
            if not isinstance(value, str) or not SHA_PATTERN.fullmatch(value):
                failures.append(f"{label}: invalid event {field}")
        if record.get("updated_at") != event.get("created_at"):
            failures.append(f"{label}: event time does not match state")
        if event.get("main_sha") != source.get("main_sha"):
            failures.append(f"{label}: event main does not match global state")
        if metadata.get("initiative_id") != event.get("initiative_id"):
            failures.append(f"{label}: event initiative does not match authority state")
        if selection is None and metadata.get("next_chunk_id") != event.get("chunk_id"):
            failures.append(f"{label}: event chunk does not match reviewed successor")
        selected_phase = selection.get("phase") if isinstance(selection, dict) else "implementation"
        selected_title = (
            selection.get("contract_title")
            if isinstance(selection, dict)
            else metadata.get("next_chunk_title")
        )
        expected_active = {
            "planning_chunk": event.get("chunk_id") if event_type == "start" and selected_phase == "planning" else None,
            "implementation_chunk": event.get("chunk_id") if event_type == "start" and selected_phase == "implementation" else None,
        }
        if authority.get("active") != expected_active:
            failures.append(f"{label}: authority active state is inconsistent")
        expected_gate = {
            "status": "active" if event_type == "start" else "stopped_after_cancel",
            "next_chunk_id": event.get("chunk_id"),
            "next_chunk_title": selected_title,
            "next_requires_explicit_start": True,
        }
        if authority.get("gate") != expected_gate:
            failures.append(f"{label}: authority gate is inconsistent")
        return failures
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
    if not isinstance(record, dict) or frozenset(record) not in {
        frozenset(expected),
        frozenset(expected | {"legacy_exemptions"}),
        frozenset(expected | {"planning_intake"}),
        frozenset(expected | {"planning_intake", "legacy_exemptions"}),
    }:
        return [f"{label}: invalid record schema"]
    failures: list[str] = []
    exemptions = record.get("legacy_exemptions")
    if exemptions is not None:
        identities = set()
        if not isinstance(exemptions, list):
            failures.append(f"{label}: legacy exemptions are not a list")
        else:
            for exemption in exemptions:
                if not isinstance(exemption, dict) or set(exemption) != {
                    "initiative_id", "chunk_id", "pr_number"
                }:
                    failures.append(f"{label}: invalid legacy exemption schema")
                    continue
                identity = (exemption.get("initiative_id"), exemption.get("chunk_id"))
                if (
                    not _is_valid_lifecycle_id(identity[0])
                    or not _is_valid_lifecycle_id(identity[1])
                    or not identity[1].startswith(f"{identity[0]}-")
                    or type(exemption.get("pr_number")) is not int
                    or exemption["pr_number"] <= 0
                    or identity in identities
                ):
                    failures.append(f"{label}: invalid or duplicate legacy exemption")
                identities.add(identity)
    planning_intake = record.get("planning_intake")
    if planning_intake is not None:
        intake_keys = {
            "schema_version",
            "initiative_directory",
            "base_tree_sha",
            "head_tree_sha",
            "first_parent_tree_sha",
            "merge_tree_sha",
            "delta_sha256",
            "changed_paths",
        }
        if not isinstance(planning_intake, dict) or set(planning_intake) != intake_keys:
            failures.append(f"{label}: invalid planning intake schema")
            planning_intake = {}
        if planning_intake.get("schema_version") != 1:
            failures.append(f"{label}: invalid planning intake version")
        directory = planning_intake.get("initiative_directory")
        paths = planning_intake.get("changed_paths")
        if (
            not isinstance(directory, str)
            or not isinstance(paths, list)
            or not paths
            or not all(isinstance(path, str) for path in paths)
            or paths != sorted(set(paths))
        ):
            failures.append(f"{label}: invalid planning intake paths")
        for field in (
            "base_tree_sha", "head_tree_sha", "first_parent_tree_sha", "merge_tree_sha"
        ):
            value = planning_intake.get(field)
            if not isinstance(value, str) or not SHA_PATTERN.fullmatch(value):
                failures.append(f"{label}: invalid planning intake {field}")
        digest = planning_intake.get("delta_sha256")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            failures.append(f"{label}: invalid planning intake delta digest")
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
        and source.get("pr_url") != f"https://github.com/{repository}/pull/{pr_number}"
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
        if planning_intake is not None:
            initiative_id = metadata.get("initiative_id")
            directory = planning_intake.get("initiative_directory")
            paths = planning_intake.get("changed_paths")
            intent_path = f".agent-loop/merge-intents/{initiative_id}-PLAN.json"
            prefix = f".agent-loop/initiatives/{directory}/"
            if (
                metadata.get("chunk_id") != f"{initiative_id}-PLAN"
                or not metadata.get("next_chunk_id")
                or metadata.get("next_requires_explicit_start") is not True
                or not isinstance(directory, str)
                or not directory.startswith(f"{initiative_id}-")
                or not isinstance(paths, list)
                or intent_path not in paths
                or any(path != intent_path and not path.startswith(prefix) for path in paths)
            ):
                failures.append(f"{label}: planning intake lifecycle identity is invalid")
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
            if planning_intake is not None and calculated is not True:
                failures.append(f"{label}: planning intake required checks did not pass")
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


def _is_merge_record(record: dict) -> bool:
    return "event" not in record or record.get("event", {}).get("type") in {
        "merge", "cutover"
    }


def _latest_merge_record(records: list[dict]) -> dict:
    return next(record for record in reversed(records) if _is_merge_record(record))


def _render_state(state: dict, records: list[dict] | None = None) -> str:
    """Independently render the expected human-readable state."""
    global_record = _latest_merge_record(records) if records is not None else state
    source = global_record["source"]
    completed = global_record["completed_chunk"]
    gate = state["gate"]
    checks = global_record["checks"]
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
    active_chunks = []
    planning_chunks = []
    if records is None:
        active = state["active"]["implementation_chunk"]
        active_chunks = [active] if active else []
        planning = state["active"]["planning_chunk"]
        planning_chunks = [planning] if planning else []
    else:
        active_chunks = sorted(
            record["active"]["implementation_chunk"]
            for record in _latest_by_initiative(records).values()
            if record["active"]["implementation_chunk"]
        )
        planning_chunks = sorted(
            record["active"]["planning_chunk"]
            for record in _latest_by_initiative(records).values()
            if record["active"]["planning_chunk"]
        )
    active_line = "- Active implementation chunks: " + (
        ", ".join(f"`{chunk}`" for chunk in active_chunks) if active_chunks else "none"
    )
    planning_line = "- Active planning chunks: " + (
        ", ".join(f"`{chunk}`" for chunk in planning_chunks) if planning_chunks else "none"
    )
    authority_lines = []
    if isinstance(state.get("event"), dict) and state["event"].get("type") in {
        "start", "cancel"
    }:
        event = state["event"]
        authority_lines = [
            f"- Latest authority event: `{event['type']}` for `{event['chunk_id']}`",
            f"- Authority initiative: `{event['initiative_id']}`",
        ]
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
            planning_line,
            active_line,
            *authority_lines,
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


def _latest_by_initiative(records: list[dict]) -> dict[str, dict]:
    """Return latest independently validated records by initiative."""
    latest = {}
    for record in records:
        projected = record
        if isinstance(record.get("authority_state"), dict):
            projected = json.loads(json.dumps(record))
            projected.update(projected["authority_state"])
        latest[projected["completed_chunk"]["initiative_id"]] = projected
    return latest


def _render_work_queue(records: list[dict]) -> str:
    """Independently render the generated work queue."""
    lines = [
        "# Generated Workstream Work Queue",
        "",
        "> Signed merge/start/cancel projection. Unsigned chat or worktree starts are not represented.",
        "",
        "| Initiative | Latest completed chunk | Gate | Next chunk | Explicit start |",
        "|---|---|---|---|---|",
    ]
    for initiative_id, record in sorted(_latest_by_initiative(records).items()):
        completed, gate = record["completed_chunk"], record["gate"]
        lines.append(
            f"| `{initiative_id}` | `{completed['chunk_id']}` | "
            f"`{gate['status']}` | `{gate['next_chunk_id'] or 'none'}` | "
            f"{'yes' if gate['next_requires_explicit_start'] else 'no'} |"
        )
    latest_merge = _latest_merge_record(records)
    lines.extend(["", f"Latest global merge: `{latest_merge['source']['main_sha']}`", ""])
    return "\n".join(lines)


def _render_initiative_state(record: dict) -> str:
    """Independently render one generated initiative projection."""
    source, completed, gate = (
        record["source"],
        record["completed_chunk"],
        record["gate"],
    )
    return "\n".join(
        [
            "# Generated Merge/Start Projection",
            "",
            "> Signed merge/start/cancel state. Unsigned chat or worktree starts are not represented.",
            "",
            f"- Initiative: `{completed['initiative_id']}`",
            f"- Latest completed chunk: `{completed['chunk_id']}` - {_markdown_text(completed['chunk_title'])}",
            f"- Gate: `{gate['status']}`",
            f"- Active planning chunk: `{record['active']['planning_chunk'] or 'none'}`",
            f"- Active implementation chunk: `{record['active']['implementation_chunk'] or 'none'}`",
            f"- Next chunk: `{gate['next_chunk_id'] or 'none'}`",
            f"- Separate explicit start required: `{str(gate['next_requires_explicit_start']).lower()}`",
            f"- Source PR: [#{source['pr_number']}]({source['pr_url']})",
            f"- Source merge: `{source['main_sha']}`",
            f"- Source event time: `{source['merged_at']}`",
            "",
        ]
    )


def _authority_transition_failures(
    record: dict, prior_records: list[dict], label: str
) -> list[str]:
    event = record.get("event")
    if not isinstance(event, dict) or event.get("type") not in {"start", "cancel"}:
        return []
    authority = record.get("authority_state", {})
    if authority.get("completed_chunk", {}).get("initiative_id") != event.get("initiative_id"):
        return [f"{label}: authority initiative does not match event"]
    latest = _latest_by_initiative(prior_records)
    basis = latest.get(event["initiative_id"])
    if basis is None:
        return [f"{label}: authority event has no preceding basis"]
    failures = []
    if authority.get("source") != basis.get("source") or authority.get(
        "completed_chunk"
    ) != basis.get("completed_chunk"):
        failures.append(f"{label}: authority lifecycle does not copy signed basis")
    if event["type"] == "start":
        if any(
            _is_merge_record(item)
            and item["completed_chunk"]["initiative_id"] == event["initiative_id"]
            and item["completed_chunk"]["chunk_id"] == event["chunk_id"]
            for item in prior_records
        ):
            failures.append(f"{label}: authority start selects completed work")
        if any(value is not None for value in basis["active"].values()):
            failures.append(f"{label}: authority start basis is already active")
        selection = event.get("selection")
        if selection is None and basis["gate"]["next_chunk_id"] != event["chunk_id"]:
            failures.append(f"{label}: authority start is not basis successor")
        if isinstance(selection, dict):
            mode = "declared_successor" if basis["gate"]["next_chunk_id"] == event["chunk_id"] else "writer_directed"
            if selection.get("mode") != mode:
                failures.append(f"{label}: start selection mode does not match basis")
    else:
        if event["chunk_id"] not in basis["active"].values():
            failures.append(f"{label}: authority cancel does not match active basis")
        if event.get("selection") != basis.get("event", {}).get("selection"):
            failures.append(f"{label}: authority cancel selection does not match start")
    return failures


def generated_state_failures(
    root: Path, repository_root: Path | None = None
) -> list[str]:
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
        work_queue = paths[3].read_text(encoding="utf-8")
        manifest = json.loads(paths[4].read_text(encoding="utf-8"))
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
        failures.extend(_authority_transition_failures(record, ledger_records, label))
        if repository_root is not None and isinstance(record.get("event"), dict):
            failures.extend(_selection_tree_failures(record["event"], repository_root, label))
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
        is_merge = "event" not in record or record.get("event", {}).get("type") in {
            "merge", "cutover"
        }
        if (
            is_merge
            and
            previous_main_sha is not None
            and source.get("first_parent_sha") != previous_main_sha
        ):
            failures.append(f"{label}: first-parent chain is invalid")
            break
        previous_hash = expected_hash
        previous_main_sha = (
            record["event"]["main_sha"] if not is_merge else source.get("main_sha")
        )
        ledger_records.append(record)
    if not ledger_records or ledger_records[-1] != state:
        failures.append(
            ".agent-loop/MERGE_LOG.jsonl: ledger tail does not match live state"
        )
    if not failures and rendered != _render_state(state, ledger_records):
        failures.append(
            ".agent-loop/LOOP_STATE.md: rendered state does not match canonical JSON"
        )
    latest = _latest_by_initiative(ledger_records) if ledger_records else {}
    if not failures and work_queue != _render_work_queue(ledger_records):
        failures.append(
            ".agent-loop/WORK_QUEUE.md: rendered queue does not match ledger"
        )
    expected_payloads = {
        ".agent-loop/STATE.json",
        ".agent-loop/LOOP_STATE.md",
        ".agent-loop/MERGE_LOG.jsonl",
        ".agent-loop/WORK_QUEUE.md",
        *(f"{INITIATIVE_STATE_ROOT}/{initiative_id}.md" for initiative_id in latest),
    }
    for initiative_id, record in latest.items():
        path = root / INITIATIVE_STATE_ROOT / f"{initiative_id}.md"
        if (
            not path.is_file()
            or path.is_symlink()
            or path.read_text(encoding="utf-8") != _render_initiative_state(record)
        ):
            failures.append(
                f"{path.relative_to(root)}: rendered initiative state does not match ledger"
            )
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "payloads",
    }:
        failures.append(".agent-loop/MANIFEST.json: invalid manifest schema")
        payloads = []
    else:
        payloads = manifest.get("payloads", [])
    observed_paths = []
    for item in payloads if isinstance(payloads, list) else []:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            failures.append(".agent-loop/MANIFEST.json: invalid payload entry")
            break
        relative = item["path"]
        payload_path = root / relative if isinstance(relative, str) else root
        observed_paths.append(relative)
        if (
            not isinstance(relative, str)
            or not payload_path.is_file()
            or payload_path.is_symlink()
        ):
            failures.append(".agent-loop/MANIFEST.json: unsafe payload path")
            break
        if hashlib.sha256(payload_path.read_bytes()).hexdigest() != item.get("sha256"):
            failures.append(f"{relative}: digest does not match manifest")
    if set(observed_paths) != expected_payloads or observed_paths != sorted(
        observed_paths
    ):
        failures.append(
            ".agent-loop/MANIFEST.json: payload path set or order is invalid"
        )
    expected_tree = expected_payloads | {".agent-loop/MANIFEST.json"}
    signature_path = root / ".agent-loop/STATE.sig"
    if signature_path.exists() or signature_path.is_symlink():
        expected_tree.add(".agent-loop/STATE.sig")
    actual_tree = {
        path.relative_to(root).as_posix()
        for path in (root / ".agent-loop").rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual_tree != expected_tree:
        failures.append(".agent-loop: generated tree does not match manifest")
    return failures


def build_parser() -> argparse.ArgumentParser:
    """Build the loop-memory validator parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--repository-root", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate generated automation state or authored main-branch memory."""
    args = build_parser().parse_args([] if argv is None else argv)
    if args.state_root:
        failures = generated_state_failures(args.state_root, args.repository_root)
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
