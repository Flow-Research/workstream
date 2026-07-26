#!/usr/bin/env python3
"""Fail-closed validation of machine-readable chunk scope contracts."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

MAX_CONTRACT_BYTES = 128 * 1024
MAX_ITEMS = 256
PHASES = {"implementation", "specification"}
RISKS = {"L0", "L1", "L2", "L3", "L4"}
REVIEWERS = {
    "senior engineering", "qa/test", "security/auth", "product/ops",
    "architecture", "ci integrity", "docs", "reuse/dedup", "test delta",
}
VERIFICATION_COMMANDS = {
    "chunk-scope-tests": "python3 scripts/test_check_chunk_contract.py",
    "agent-gate-tests": "python3 scripts/test_agent_gates.py",
    "internal-review-evidence": "python3 scripts/check_internal_review_evidence.py",
    "markdown-links": "python3 scripts/check_markdown_links.py",
    "stale-wording": "python3 scripts/check_stale_workstream_wording.py",
    "git-diff-check": "git diff --check origin/main...HEAD",
    "loop-memory-drift-tests": "python3 scripts/test_audit_loop_memory_drift.py",
    "loop-memory-property-tests": "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -p hypothesis.extra.pytestplugin -q scripts/test_loop_memory_properties.py",
    "authorization-property-tests": "python -m pytest -q tests/test_authorization_properties.py",
    "authorization-property-lint": "ruff check tests/test_authorization_properties.py",
    "mutation-policy-tests": "python -m pytest -q tests/test_mutation_policy.py",
    "mutation-policy-lint": "ruff check scripts/mutation_policy.py tests/test_mutation_policy.py",
    "review-log-archive-tests": "python3 scripts/test_check_review_log_archive.py",
    "review-log-archive-check": "python3 scripts/check_review_log_archive.py",
    "loop-memory-state": "python3 scripts/check_loop_memory_state.py",
    "stale-artifact-contracts": "python3 scripts/check_stale_artifact_contracts.py",
}
VERIFICATION_COMMAND_IDS = frozenset(VERIFICATION_COMMANDS)
KEYS = {
    "schema_version", "chunk_id", "phase", "risk_class", "allowed_paths",
    "forbidden_paths", "required_reviewers", "verification_commands",
}
CHUNK_RE = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+){3,}")
HEADING_RE = re.compile(
    r"\A# (?:Chunk Contract|Parent Chunk):\s+(?P<id>[A-Z][A-Z0-9]*(?:-[A-Z0-9]+){3,})(?:\s+[—-].*)?$",
    re.M,
)
FENCE_RE = re.compile(r"^```chunk-scope-json[ \t]*\n(?P<body>.*?)^```[ \t]*$", re.M | re.S)
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
GLOB_META_RE = re.compile(r"[*?\[\]{}!\\]")


class ContractError(ValueError):
    """A stable, user-facing contract validation failure."""


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise ContractError(f"{label} must be a non-empty string")
    if CONTROL_RE.search(value) or unicodedata.normalize("NFC", value) != value:
        raise ContractError(f"{label} contains control or non-NFC Unicode")
    return value


def _items(value: Any, label: str) -> tuple[str, ...]:
    if type(value) is not list or not value or len(value) > MAX_ITEMS:
        raise ContractError(f"{label} must be a non-empty list of at most {MAX_ITEMS} items")
    items = tuple(_text(item, f"{label} item") for item in value)
    if len(items) != len(set(items)):
        raise ContractError(f"{label} contains duplicate items")
    folded = [item.casefold() for item in items]
    if len(folded) != len(set(folded)):
        raise ContractError(f"{label} contains casefold-colliding items")
    return items


def validate_pattern(pattern: str) -> str:
    """Validate the closed grammar: a file, or a directory ending in '/**'."""
    _text(pattern, "path pattern")
    recursive = pattern.endswith("/**")
    stem = pattern[:-3] if recursive else pattern
    if not stem or stem.startswith("/") or "//" in stem or GLOB_META_RE.search(stem):
        raise ContractError(f"noncanonical path pattern: {pattern!r}")
    if stem.endswith("/") or PurePosixPath(stem).is_absolute():
        raise ContractError(f"noncanonical path pattern: {pattern!r}")
    parts = stem.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ContractError(f"path traversal is forbidden: {pattern!r}")
    if any(part.endswith(" ") or part.endswith(".") for part in parts):
        raise ContractError(f"platform-ambiguous path pattern: {pattern!r}")
    return pattern


@dataclass(frozen=True)
class ScopeContract:
    chunk_id: str
    phase: str
    risk_class: str
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    required_reviewers: tuple[str, ...]
    verification_commands: tuple[str, ...]


def parse_contract_bytes(raw: bytes) -> ScopeContract:
    if len(raw) > MAX_CONTRACT_BYTES:
        raise ContractError("contract exceeds size limit")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ContractError("contract is not valid UTF-8") from exc
    if "\r" in text or CONTROL_RE.search(text.replace("\n", "")):
        raise ContractError("contract contains noncanonical line endings or controls")
    if unicodedata.normalize("NFC", text) != text:
        raise ContractError("contract is not NFC-normalized")
    heading = HEADING_RE.match(text)
    if not heading:
        raise ContractError("missing canonical chunk heading")
    blocks = list(FENCE_RE.finditer(text))
    if len(blocks) != 1:
        raise ContractError("contract must contain exactly one `chunk-scope-json` block")
    try:
        data = json.loads(blocks[0].group("body"), object_pairs_hook=_object)
    except (json.JSONDecodeError, ContractError) as exc:
        raise ContractError(f"invalid scope JSON: {exc}") from exc
    if type(data) is not dict:
        raise ContractError("scope JSON must be an object")
    if set(data) != KEYS:
        raise ContractError(f"scope JSON keys must be exactly {sorted(KEYS)}")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ContractError("schema_version must be integer 1")
    chunk_id = _text(data["chunk_id"], "chunk_id")
    if not CHUNK_RE.fullmatch(chunk_id) or chunk_id != heading.group("id"):
        raise ContractError("JSON chunk_id does not match canonical heading")
    phase = _text(data["phase"], "phase")
    if phase not in PHASES:
        raise ContractError(f"unsupported phase: {phase}")
    phase_match = re.search(r"^## Start phase\n\n`([^`]+)`[ \t]*$", text, re.M)
    if not phase_match or phase_match.group(1) != phase:
        raise ContractError("machine phase disagrees with human Start phase")
    risk = _text(data["risk_class"], "risk_class")
    if risk not in RISKS:
        raise ContractError(f"unsupported risk class: {risk}")
    risk_match = re.search(r"^## Risk class\n\n([^\n]+)$", text, re.M)
    if not risk_match or risk_match.group(1).strip(" `") != risk:
        raise ContractError("machine risk disagrees with human Risk class")
    allowed = tuple(validate_pattern(p) for p in _items(data["allowed_paths"], "allowed_paths"))
    forbidden = tuple(validate_pattern(p) for p in _items(data["forbidden_paths"], "forbidden_paths"))
    reviewers = _items(data["required_reviewers"], "required_reviewers")
    unknown_reviewers = set(reviewers) - REVIEWERS
    if unknown_reviewers:
        raise ContractError(f"unknown reviewer identifiers: {sorted(unknown_reviewers)}")
    commands = _items(data["verification_commands"], "verification_commands")
    unknown_commands = set(commands) - VERIFICATION_COMMAND_IDS
    if unknown_commands:
        raise ContractError(f"unknown verification identifiers: {sorted(unknown_commands)}")
    verification_section = _section(text, "Verification commands")
    verification_fence = re.search(r"```bash\n(.*?)```", verification_section, re.S)
    if not verification_fence:
        raise ContractError("Verification commands must contain a bash fence")
    human_commands = tuple(
        line for line in verification_fence.group(1).splitlines()
        if line and not line.startswith("cd ")
    )
    expected_commands = tuple(VERIFICATION_COMMANDS[identifier] for identifier in commands)
    if set(human_commands) != set(expected_commands) or len(human_commands) != len(expected_commands):
        raise ContractError("machine verification identifiers disagree with human commands")
    human_allowed = _text_block_items(text, "Allowed files")
    if set(human_allowed) != set(allowed):
        raise ContractError("machine allowed_paths disagree with human Allowed files")
    human_reviewers = tuple(re.findall(r"^- \[[ xX]\] (.+)$", _section(text, "Required reviewers"), re.M))
    if {item.casefold() for item in human_reviewers} != {item.casefold() for item in reviewers}:
        raise ContractError("machine required_reviewers disagree with human section")
    return ScopeContract(chunk_id, phase, risk, allowed, forbidden, reviewers, commands)


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\n(?P<body>.*?)(?=^## |\Z)", text, re.M | re.S)
    if not match:
        raise ContractError(f"missing human section: {heading}")
    return match.group("body")


def _text_block_items(text: str, heading: str) -> tuple[str, ...]:
    section = _section(text, heading)
    match = re.search(r"```text\n(.*?)```", section, re.S)
    if not match:
        raise ContractError(f"{heading} must contain a text fence")
    items = tuple(line for line in match.group(1).splitlines() if line)
    for item in items:
        validate_pattern(item)
    return items


def validate_path_bytes(paths: Iterable[bytes]) -> tuple[str, ...]:
    decoded: list[str] = []
    byte_seen: set[bytes] = set()
    nfc_seen: set[str] = set()
    fold_seen: set[str] = set()
    for raw in paths:
        if raw in byte_seen:
            raise ContractError("duplicate byte path")
        byte_seen.add(raw)
        try:
            path = raw.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise ContractError("Git path is not valid UTF-8") from exc
        if CONTROL_RE.search(path):
            raise ContractError("Git path contains a control character")
        nfc = unicodedata.normalize("NFC", path)
        if nfc != path:
            raise ContractError("Git path is not NFC-normalized")
        validate_pattern(path)
        folded = nfc.casefold()
        if nfc in nfc_seen or folded in fold_seen:
            raise ContractError("Git paths collide after NFC or casefold normalization")
        nfc_seen.add(nfc)
        fold_seen.add(folded)
        decoded.append(path)
    return tuple(decoded)


def matches(pattern: str, path: str) -> bool:
    return path == pattern[:-3] or path.startswith(pattern[:-3] + "/") if pattern.endswith("/**") else path == pattern


def enforce_scope(contract: ScopeContract, paths: Iterable[bytes]) -> tuple[str, ...]:
    decoded = validate_path_bytes(tuple(dict.fromkeys(paths)))
    for path in decoded:
        if any(matches(pattern, path) for pattern in contract.forbidden_paths):
            raise ContractError(f"forbidden changed path: {path}")
        if not any(matches(pattern, path) for pattern in contract.allowed_paths):
            raise ContractError(f"changed path is outside allowed scope: {path}")
    return decoded


def parse_name_status_z(raw: bytes) -> list[tuple[str, tuple[bytes, ...]]]:
    if raw and not raw.endswith(b"\0"):
        raise ContractError("Git status is not NUL-terminated")
    fields = raw.split(b"\0")
    if fields[-1:] == [b""]:
        fields.pop()
    result: list[tuple[str, tuple[bytes, ...]]] = []
    index = 0
    while index < len(fields):
        try:
            status = fields[index].decode("ascii", "strict")
        except UnicodeDecodeError as exc:
            raise ContractError("non-ASCII Git status") from exc
        index += 1
        if not re.fullmatch(r"[ACDMRTUXB](?:\d{1,3})?", status):
            raise ContractError(f"unsupported Git status: {status!r}")
        count = 2 if status[0] in "RC" else 1
        if index + count > len(fields):
            raise ContractError("truncated NUL-delimited Git status")
        names = tuple(fields[index:index + count])
        index += count
        result.append((status, names))
    return result


def validate_raw_modes_z(raw: bytes) -> None:
    """Reject executable, symlink, gitlink and type modes on either diff side."""
    if raw and not raw.endswith(b"\0"):
        raise ContractError("raw Git diff is not NUL-terminated")
    fields = raw.split(b"\0")[:-1]
    index = 0
    while index < len(fields):
        metadata = fields[index]
        index += 1
        match = re.fullmatch(
            br":(?P<old>[0-7]{6}) (?P<new>[0-7]{6}) [0-9a-f]+ [0-9a-f]+ (?P<status>[ACDMRTUXB][0-9]{0,3})",
            metadata,
        )
        if not match:
            raise ContractError("malformed raw Git diff record")
        status = match.group("status")
        name_count = 2 if status[:1] in {b"R", b"C"} else 1
        if index + name_count > len(fields):
            raise ContractError("truncated raw Git diff record")
        index += name_count
        for mode in (match.group("old"), match.group("new")):
            if mode not in {b"000000", b"100644"}:
                labels = {b"100755": "executable", b"120000": "symlink", b"160000": "gitlink"}
                raise ContractError(f"raw Git diff has forbidden {labels.get(mode, 'type')} mode")


def tree_paths_z(raw: bytes) -> tuple[bytes, ...]:
    """Return paths from a recursive NUL tree for result-name collision checks."""
    paths: list[bytes] = []
    for record in (item for item in raw.split(b"\0") if item):
        metadata, separator, path = record.partition(b"\t")
        fields = metadata.split(b" ")
        if not separator or len(fields) != 3:
            raise ContractError("malformed resulting Git tree record")
        mode, kind, _blob = fields
        valid_entry = (
            (mode in {b"100644", b"100755", b"120000"} and kind == b"blob")
            or (mode == b"160000" and kind == b"commit")
        )
        if not valid_entry:
            raise ContractError("resulting tree has malformed mode/type")
        paths.append(path)
    return tuple(paths)


def _git(repo: Path, *args: str) -> bytes:
    proc = subprocess.run(["git", *args], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode:
        raise ContractError(f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout


def validate_untracked_files(repo: Path, raw_paths: Sequence[bytes]) -> None:
    """Accept only regular, non-executable untracked files without symlink walks."""
    paths = validate_path_bytes(raw_paths)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    root_fd = os.open(repo, directory_flags)
    try:
        for path in paths:
            parts = path.split("/")
            current_fd = root_fd
            opened: list[int] = []
            try:
                for component in parts[:-1]:
                    current_fd = os.open(component, directory_flags, dir_fd=current_fd)
                    opened.append(current_fd)
                info = os.stat(parts[-1], dir_fd=current_fd, follow_symlinks=False)
            except (FileNotFoundError, NotADirectoryError, OSError) as exc:
                raise ContractError(f"unsafe untracked path: {path}") from exc
            finally:
                for descriptor in reversed(opened):
                    os.close(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise ContractError(f"untracked path is not a regular file: {path}")
            if info.st_mode & 0o111:
                raise ContractError(f"untracked path is executable: {path}")
    finally:
        os.close(root_fd)


def _git_json(repo: Path, revision_path: str) -> dict[str, Any]:
    raw = _git(repo, "show", revision_path)
    try:
        value = json.loads(raw, object_pairs_hook=_object)
    except (json.JSONDecodeError, ContractError) as exc:
        raise ContractError(f"malformed signed state at {revision_path}: {exc}") from exc
    if type(value) is not dict:
        raise ContractError(f"signed state at {revision_path} is not an object")
    return value


def added_merge_intent(repo: Path, base: str, head: str) -> dict[str, str]:
    raw = _git(repo, "diff", "--name-only", "--diff-filter=A", "-z", f"{base}...{head}")
    paths = validate_path_bytes(path for path in raw.split(b"\0") if path)
    intents = [
        path for path in paths
        if re.fullmatch(r"\.agent-loop/merge-intents/[A-Z][A-Z0-9-]+\.json", path)
    ]
    if len(intents) != 1:
        raise ContractError("delta must add exactly one merge intent")
    data = _git_json(repo, f"{head}:{intents[0]}")
    initiative = data.get("initiative_id")
    chunk = data.get("chunk_id")
    if type(initiative) is not str or type(chunk) is not str or not CHUNK_RE.fullmatch(chunk):
        raise ContractError("merge intent has invalid initiative/chunk identity")
    if not chunk.startswith(initiative + "-"):
        raise ContractError("merge intent chunk does not belong to initiative")
    return {"path": intents[0], "initiative_id": initiative, "chunk_id": chunk}


@dataclass(frozen=True)
class SignedStart:
    ledger_index: int
    initiative_id: str
    chunk_id: str
    phase: str
    main_sha: str
    contract_path: str
    contract_blob_sha: str


def verify_state_ref(repo: Path, state_ref: str) -> None:
    """Authenticate and semantically validate the exact generated state tree."""
    raw = _git(repo, "ls-tree", "-rz", "--full-tree", state_ref)
    records = [record for record in raw.split(b"\0") if record]
    if not records:
        raise ContractError("state ref tree is empty")
    parsed: list[tuple[bytes, bytes]] = []
    raw_paths: list[bytes] = []
    for record in records:
        metadata, separator, path = record.partition(b"\t")
        fields = metadata.split(b" ")
        if not separator or len(fields) != 3:
            raise ContractError("malformed state-ref tree record")
        mode, kind, blob = fields
        if mode != b"100644" or kind != b"blob" or not re.fullmatch(b"[0-9a-f]{40,64}", blob):
            raise ContractError("state ref contains a non-ordinary blob")
        raw_paths.append(path)
        parsed.append((blob, path))
    paths = validate_path_bytes(raw_paths)
    if any(not path.startswith(".agent-loop/") for path in paths):
        raise ContractError("state ref contains a path outside the closed generated tree")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for (blob, _raw_path), path in zip(parsed, paths, strict=True):
            destination = root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(_git(repo, "cat-file", "blob", blob.decode("ascii")))
        public_key = repo / ".agent-loop/keys/loop-memory-signing-public.pem"
        if not public_key.is_file() or public_key.is_symlink():
            raise ContractError("trusted loop-memory public key is unavailable")
        try:
            from update_post_merge_memory import (
                LoopMemoryError,
                verify_generated_state_signature,
            )
            from check_loop_memory_state import generated_state_failures

            verify_generated_state_signature(root, public_key)
            failures = generated_state_failures(root, repo)
        except (ImportError, LoopMemoryError, OSError, UnicodeError, ValueError) as exc:
            raise ContractError(f"state-ref authentication failed: {exc}") from exc
        if failures:
            raise ContractError(
                "state-ref semantic validation failed: " + "; ".join(failures)
            )


def authenticated_ledger(repo: Path, state_ref: str) -> tuple[dict[str, Any], ...]:
    """Return ordered records from the already authenticated tip ledger."""
    raw = _git(repo, "show", f"{state_ref}:.agent-loop/MERGE_LOG.jsonl")
    records: list[dict[str, Any]] = []
    for number, line in enumerate(raw.splitlines(), 1):
        if not line:
            raise ContractError(f"authenticated ledger has blank line {number}")
        try:
            envelope = json.loads(line, object_pairs_hook=_object)
        except (json.JSONDecodeError, ContractError) as exc:
            raise ContractError(f"authenticated ledger line {number} is malformed: {exc}") from exc
        keys = {"schema_version", "previous_entry_hash", "record", "entry_hash"}
        if type(envelope) is not dict or set(envelope) != keys or type(envelope.get("record")) is not dict:
            raise ContractError(f"authenticated ledger line {number} has invalid envelope")
        records.append(envelope["record"])
    if not records:
        raise ContractError("authenticated ledger is empty")
    return tuple(records)


def _start_from_record(index: int, record: dict[str, Any], chunk_id: str) -> SignedStart | None:
    event = record.get("event")
    if type(event) is not dict or event.get("chunk_id") != chunk_id:
        return None
    if event.get("type") != "start":
        raise ContractError(f"latest signed event for {chunk_id} is not a start")
    selection = event.get("selection")
    if type(selection) is not dict:
        raise ContractError("signed start has no contract selection")
    values = (
        event.get("initiative_id"), event.get("chunk_id"), selection.get("phase"),
        event.get("main_sha"), selection.get("contract_path"), selection.get("contract_blob_sha"),
    )
    if not all(type(value) is str and value for value in values):
        raise ContractError("signed start binding is incomplete")
    return SignedStart(index, *values)  # type: ignore[arg-type]


def latest_signed_start(records: Sequence[dict[str, Any]], chunk_id: str) -> SignedStart:
    for index in range(len(records) - 1, -1, -1):
        record = records[index]
        event = record.get("event")
        if type(event) is dict and event.get("chunk_id") == chunk_id:
            start = _start_from_record(index, record, chunk_id)
            if start is None:  # pragma: no cover - guarded above
                break
            return start
    raise ContractError(f"no signed event found for {chunk_id}")


def reduce_active(records: Sequence[dict[str, Any]]) -> dict[str, tuple[str, str]]:
    """Reduce authenticated records into initiative-local active slots."""
    active: dict[str, tuple[str, str]] = {}
    for record in records:
        event = record.get("event")
        completed = record.get("completed_chunk")
        # Start/cancel snapshots repeat the latest completed chunk globally;
        # only a merge record (no event) completes and clears an initiative.
        if (event is None and type(completed) is dict
                and type(completed.get("initiative_id")) is str):
            active.pop(completed["initiative_id"], None)
        if type(event) is not dict:
            continue
        initiative = event.get("initiative_id")
        chunk = event.get("chunk_id")
        event_type = event.get("type")
        if event_type == "cutover":
            continue
        if type(initiative) is not str or type(chunk) is not str:
            raise ContractError("authenticated ledger event has invalid identity")
        if event_type == "start":
            selection = event.get("selection")
            phase = selection.get("phase") if type(selection) is dict else None
            if phase is None:
                authority = record.get("authority_state")
                slots = authority.get("active") if type(authority) is dict else None
                matches = [
                    candidate for candidate in ("planning", "implementation")
                    if type(slots) is dict and slots.get(f"{candidate}_chunk") == chunk
                ]
                phase = matches[0] if len(matches) == 1 else None
            if phase not in {"planning", "implementation", "specification"}:
                raise ContractError("authenticated start has invalid phase")
            if initiative in active:
                raise ContractError("authenticated ledger starts an already-active initiative")
            active[initiative] = (phase, chunk)
        elif event_type == "cancel":
            current = active.get(initiative)
            if current is None or current[1] != chunk:
                raise ContractError("authenticated cancellation does not target active chunk")
            active.pop(initiative)
        else:
            raise ContractError(f"unsupported authenticated event type: {event_type!r}")
    return active


def require_active_projection(repo: Path, state_ref: str, start: SignedStart) -> None:
    path = f".agent-loop/INITIATIVE_STATE/{start.initiative_id}.md"
    text = _git(repo, "show", f"{state_ref}:{path}").decode("utf-8", "strict")
    label = "planning" if start.phase == "planning" else "implementation"
    match = re.search(rf"^- Active {label} chunk: `([^`]+)`$", text, re.M)
    if not match or match.group(1) != start.chunk_id:
        raise ContractError("current signed initiative projection is not active for target chunk")


def signed_contract_blob(repo: Path, start: SignedStart, base: str) -> bytes:
    if _git(repo, "merge-base", "--is-ancestor", start.main_sha, base) != b"":
        # merge-base --is-ancestor has no output; _git already enforces its exit code.
        raise ContractError("unexpected ancestry output")
    tree = _git(repo, "ls-tree", start.main_sha, "--", start.contract_path).decode("utf-8").strip()
    expected = f"100644 blob {start.contract_blob_sha}\t{start.contract_path}"
    if tree != expected:
        raise ContractError("signed start contract path/blob does not match its trusted main")
    return _git(repo, "cat-file", "blob", start.contract_blob_sha)


def machine_block(raw: bytes) -> bytes:
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ContractError("contract is not valid UTF-8") from exc
    blocks = list(FENCE_RE.finditer(text))
    if len(blocks) != 1:
        raise ContractError("contract must contain exactly one machine scope block")
    return blocks[0].group("body").encode("utf-8")


def _human_phase_risk(raw: bytes) -> tuple[str, str]:
    text = raw.decode("utf-8", "strict")
    phase = re.search(r"^## Start phase\n\n`([^`]+)`[ \t]*$", text, re.M)
    risk = re.search(r"^## Risk class\n\n([^\n]+)$", text, re.M)
    if not phase or not risk:
        raise ContractError("signed contract lacks phase/risk sections")
    return phase.group(1), risk.group(1).strip(" `")


def select_contract(repo: Path, base: str, head: str, state_ref: str) -> tuple[ScopeContract | None, SignedStart]:
    intent = added_merge_intent(repo, base, head)
    verify_state_ref(repo, state_ref)
    records = authenticated_ledger(repo, state_ref)
    start = latest_signed_start(records, intent["chunk_id"])
    if start.initiative_id != intent["initiative_id"]:
        raise ContractError("signed start initiative disagrees with merge intent")
    active = reduce_active(records)
    if active.get(start.initiative_id) != (start.phase, start.chunk_id):
        raise ContractError("authenticated ledger is not active for target chunk")
    # Signed projection is a consistency cross-check, never event authority.
    require_active_projection(repo, state_ref, start)
    signed_raw = signed_contract_blob(repo, start, base)
    try:
        head_raw = _git(repo, "show", f"{head}:{start.contract_path}")
    except ContractError as exc:
        raise ContractError("head does not preserve signed contract path") from exc
    cutover_path = ".agent-loop/merge-intents/WS-ENG-008-01.json"
    cutover_present = subprocess.run(
        ["git", "cat-file", "-e", f"{base}:{cutover_path}"], cwd=repo,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0
    if machine_block_or_none(signed_raw) is not None:
        parsed = parse_contract_bytes(signed_raw)
        if machine_block(head_raw) != machine_block(signed_raw):
            raise ContractError("head changes the signed machine scope block")
        if parsed.chunk_id != start.chunk_id or parsed.phase != start.phase:
            raise ContractError("machine identity/phase disagrees with signed start")
        return parsed, start
    if start.chunk_id == "WS-ENG-008-01" and not cutover_present:
        parsed = parse_contract_bytes(head_raw)
        old_phase, old_risk = _human_phase_risk(signed_raw)
        old_allowed = _text_block_items(signed_raw.decode("utf-8"), "Allowed files")
        old_reviewers = tuple(re.findall(
            r"^- \[[ xX]\] (.+)$",
            _section(signed_raw.decode("utf-8"), "Required reviewers"), re.M,
        ))
        if (parsed.chunk_id != start.chunk_id or parsed.phase != start.phase
                or parsed.phase != old_phase or parsed.risk_class != old_risk
                or set(parsed.allowed_paths) != set(old_allowed)
                or {item.casefold() for item in parsed.required_reviewers}
                   != {item.casefold() for item in old_reviewers}):
            raise ContractError("bootstrap machine scope disagrees with signed human contract")
        return parsed, start
    if not cutover_present:
        raise ContractError("pre-cutover non-bootstrap contract has no machine scope")
    require_grandfather(records, start)
    return legacy_scope_from_signed_blob(signed_raw, start), start


def machine_block_or_none(raw: bytes) -> bytes | None:
    text = raw.decode("utf-8", "strict")
    blocks = list(FENCE_RE.finditer(text))
    if len(blocks) > 1:
        raise ContractError("duplicate machine scope blocks")
    return blocks[0].group("body").encode() if blocks else None


def legacy_scope_from_signed_blob(raw: bytes, start: SignedStart) -> ScopeContract:
    """Derive the only grandfather scope from the exact authenticated blob."""
    text = raw.decode("utf-8", "strict")
    allowed = tuple(
        validate_pattern(path) for path in _text_block_items(text, "Allowed files")
    )
    phase, risk = _human_phase_risk(raw)
    if phase != start.phase:
        raise ContractError("grandfather human phase disagrees with signed start")
    return ScopeContract(start.chunk_id, phase, risk, allowed, (), (), ())


def require_grandfather(records: Sequence[dict[str, Any]], start: SignedStart) -> None:
    cutover_index = None
    for index, record in enumerate(records):
        completed = record.get("completed_chunk")
        if (record.get("event") is None and type(completed) is dict
                and completed.get("chunk_id") == "WS-ENG-008-01"):
            if cutover_index is not None:
                raise ContractError("authenticated ledger contains ambiguous cutover records")
            cutover_index = index
    if cutover_index is None:
        raise ContractError("cannot locate exact cutover ledger record")
    active_at_cutover = reduce_active(records[:cutover_index + 1])
    if active_at_cutover.get(start.initiative_id) != (start.phase, start.chunk_id):
        raise ContractError("target was not signed-active at exact cutover")
    if start.ledger_index > cutover_index:
        raise ContractError("target start occurred or restarted after cutover")


def discover_changes(repo: Path, base: str, head: str) -> tuple[bytes, ...]:
    for ref in (base, head):
        _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    merge_base = _git(repo, "merge-base", base, head).strip()
    if not merge_base:
        raise ContractError("base and head have no merge base")
    outputs = [
        _git(repo, "diff", "--name-status", "-z", "--find-renames", "--find-copies-harder", f"{base}...{head}"),
        _git(repo, "diff", "--name-status", "-z", "--find-renames", "--find-copies-harder", "--cached"),
        _git(repo, "diff", "--name-status", "-z", "--find-renames", "--find-copies-harder"),
    ]
    raw_outputs = [
        _git(repo, "diff", "--raw", "-z", "--no-abbrev", "--find-renames", "--find-copies-harder", f"{base}...{head}"),
        _git(repo, "diff", "--raw", "-z", "--no-abbrev", "--find-renames", "--find-copies-harder", "--cached"),
        _git(repo, "diff", "--raw", "-z", "--no-abbrev", "--find-renames", "--find-copies-harder"),
    ]
    for raw_output in raw_outputs:
        validate_raw_modes_z(raw_output)
    statuses = [entry for output in outputs for entry in parse_name_status_z(output)]
    untracked = [p for p in _git(repo, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0") if p]
    validate_untracked_files(repo, untracked)
    head_tree_paths = tree_paths_z(_git(repo, "ls-tree", "-rz", "--full-tree", head))
    validate_path_bytes(head_tree_paths)
    paths = [path for _status, names in statuses for path in names] + untracked
    # Modes are part of authorization: only ordinary non-executable blobs are accepted.
    index = _git(repo, "ls-files", "--stage", "-z").split(b"\0")
    mode_by_path: dict[bytes, bytes] = {}
    for record in index:
        if not record:
            continue
        metadata, sep, name = record.partition(b"\t")
        if not sep:
            raise ContractError("malformed Git index record")
        mode_by_path[name] = metadata.split(b" ", 1)[0]
    validate_path_bytes((*mode_by_path, *untracked))
    for path in paths:
        mode = mode_by_path.get(path)
        if mode is not None and mode != b"100644":
            labels = {b"100755": "executable", b"120000": "symlink", b"160000": "gitlink"}
            raise ContractError(f"changed path has forbidden {labels.get(mode, 'type')} mode")
    # Both sides of rename/copy are checked; type-change and unmerged/unknown states fail.
    if any(status[0] in "TUXB" for status, _ in statuses):
        raise ContractError("type-changed, unmerged, unknown, or broken Git status")
    return tuple(paths)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--state-ref", default="origin/automation/loop-memory")
    parser.add_argument("--chunk-id")
    parser.add_argument("--phase", choices=sorted(PHASES))
    args = parser.parse_args(argv)
    try:
        if args.contract is None:
            contract, start = select_contract(args.repo, args.base_ref, args.head_ref, args.state_ref)
            if contract is None:
                # Grandfathering proves eligibility only; it never invents scope.
                discover_changes(args.repo, args.base_ref, args.head_ref)
                print(f"chunk contract check passed (exact cutover grandfather): {start.chunk_id}")
                return 0
        else:
            contract = parse_contract_bytes(args.contract.read_bytes())
        if args.chunk_id and args.chunk_id != contract.chunk_id:
            raise ContractError("signed-start chunk identity disagrees with contract")
        if args.phase and args.phase != contract.phase:
            raise ContractError("signed-start phase disagrees with contract")
        enforce_scope(contract, discover_changes(args.repo, args.base_ref, args.head_ref))
    except (ContractError, OSError) as exc:
        print(f"chunk contract check failed: {exc}", file=sys.stderr)
        return 1
    print(f"chunk contract check passed: {contract.chunk_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
