"""Record trusted merged-PR loop state on the automation memory branch."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
STATE_BRANCH = "automation/loop-memory"
STATE_PATH = Path(".agent-loop/STATE.json")
RENDERED_PATH = Path(".agent-loop/LOOP_STATE.md")
LEDGER_PATH = Path(".agent-loop/MERGE_LOG.jsonl")
WORK_QUEUE_PATH = Path(".agent-loop/WORK_QUEUE.md")
MANIFEST_PATH = Path(".agent-loop/MANIFEST.json")
INITIATIVE_STATE_ROOT = Path(".agent-loop/INITIATIVE_STATE")
SIGNATURE_PATH = Path(".agent-loop/STATE.sig")
LEGACY_EXEMPTIONS_PATH = Path(
    ".agent-loop/policies/loop-memory-legacy-start-exemptions.json"
)
START_AUTHORITIES_PATH = Path(
    ".agent-loop/policies/loop-memory-start-authorities.json"
)
RECOVERY_POLICY_PATH = Path(".agent-loop/policies/loop-memory-recovery.json")
INTENT_PREFIX = ".agent-loop/merge-intents/"
BOOTSTRAP_INTENT_PATH = f"{INTENT_PREFIX}WS-ENG-001-03.json"
CHUNK_CONTRACT_ROOT = ".agent-loop/initiatives/"
ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
REQUIRED_CHECKS = ("agent-gates", "test", "CodeRabbit")
REQUIRED_METADATA_KEYS = {
    "schema_version",
    "initiative_id",
    "chunk_id",
    "chunk_title",
    "next_chunk_id",
    "next_chunk_title",
    "next_requires_explicit_start",
}
PLANNING_INTAKE_VERSION = 1
PLANNING_ROOT_FILES = frozenset(
    {
        "INTENT.md",
        "DISCOVERY.md",
        "PLAN.md",
        "CHUNK_MAP.md",
        "STATUS.md",
        "RISKS.md",
        "DECISIONS.md",
    }
)
GITHUB_ACTIONS_APP_ID = 15368
GITHUB_ACTIONS_APP_SLUG = "github-actions"
CHECK_RUN_CONCLUSIONS = frozenset({
    "action_required", "cancelled", "failure", "neutral", "skipped", "stale",
    "success", "timed_out",
})


class LoopMemoryError(RuntimeError):
    """Raised when merge memory cannot be derived without guessing."""


@dataclass(frozen=True)
class LoopMetadata:
    """Machine-readable lifecycle metadata supplied by the merged PR."""

    schema_version: int
    initiative_id: str
    chunk_id: str
    chunk_title: str
    next_chunk_id: str | None
    next_chunk_title: str | None
    next_requires_explicit_start: bool


class GitHubClient:
    """Minimal authenticated GitHub JSON client."""

    def __init__(self, token: str, api_url: str = "https://api.github.com") -> None:
        if not token:
            raise LoopMemoryError("GitHub token is required")
        self._token = token
        self._api_url = api_url.rstrip("/")

    def get_json(self, path: str) -> Any:
        """Return decoded JSON for one GitHub API path."""
        request = urllib.request.Request(
            f"{self._api_url}{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "workstream-loop-memory/1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            status = getattr(exc, "code", "network")
            raise LoopMemoryError(
                f"GitHub API request failed ({status}) for {path}"
            ) from exc

    def get_paginated(self, path: str) -> list[Any]:
        """Return all items from a bounded GitHub list endpoint."""
        items: list[Any] = []
        separator = "&" if "?" in path else "?"
        for page in range(1, 101):
            payload = self.get_json(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(payload, list):
                raise LoopMemoryError("paginated GitHub response is not a list")
            items.extend(payload)
            if len(payload) < 100:
                return items
        raise LoopMemoryError("paginated GitHub response exceeded 100 pages")


def _bounded_text(value: Any, field: str, maximum: int = 160) -> str:
    """Validate one bounded single-line metadata string."""
    if not isinstance(value, str):
        raise LoopMemoryError(f"{field} must be a string")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > maximum
        or any(ord(char) < 32 for char in normalized)
    ):
        raise LoopMemoryError(f"{field} must be a non-empty bounded single-line string")
    return normalized


def _optional_id(value: Any, field: str) -> str | None:
    """Validate an optional lifecycle identifier."""
    if value is None:
        return None
    normalized = _bounded_text(value, field, maximum=80)
    if not ID_PATTERN.fullmatch(normalized):
        raise LoopMemoryError(f"{field} is not a canonical lifecycle identifier")
    return normalized


def _is_current_schema_version(value: Any) -> bool:
    """Return whether value is exactly the supported integer schema version."""
    return type(value) is int and value == SCHEMA_VERSION


def parse_loop_metadata(intent_text: str) -> LoopMetadata:
    """Parse and strictly validate one committed merge-intent document."""
    if not isinstance(intent_text, str):
        raise LoopMemoryError("merge intent must be text")
    try:
        payload = json.loads(intent_text)
    except json.JSONDecodeError as exc:
        raise LoopMemoryError("merge intent must contain valid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != REQUIRED_METADATA_KEYS:
        raise LoopMemoryError("merge intent has missing or unexpected keys")
    if not _is_current_schema_version(payload["schema_version"]):
        raise LoopMemoryError(
            f"unsupported loop-state schema version: {payload['schema_version']!r}"
        )

    initiative_id = _optional_id(payload["initiative_id"], "initiative_id")
    chunk_id = _optional_id(payload["chunk_id"], "chunk_id")
    if initiative_id is None or chunk_id is None:
        raise LoopMemoryError("initiative_id and chunk_id are required")
    if not chunk_id.startswith(f"{initiative_id}-"):
        raise LoopMemoryError("chunk_id must belong to initiative_id")

    chunk_title = _bounded_text(payload["chunk_title"], "chunk_title")
    next_chunk_id = _optional_id(payload["next_chunk_id"], "next_chunk_id")
    next_title_value = payload["next_chunk_title"]
    next_chunk_title = (
        None
        if next_title_value is None
        else _bounded_text(
            next_title_value,
            "next_chunk_title",
        )
    )
    if (next_chunk_id is None) != (next_chunk_title is None):
        raise LoopMemoryError(
            "next_chunk_id and next_chunk_title must both be null or both be set"
        )
    if next_chunk_id is not None and not next_chunk_id.startswith(f"{initiative_id}-"):
        raise LoopMemoryError("next_chunk_id must belong to initiative_id")
    explicit_start = payload["next_requires_explicit_start"]
    if not isinstance(explicit_start, bool):
        raise LoopMemoryError("next_requires_explicit_start must be a boolean")

    return LoopMetadata(
        schema_version=SCHEMA_VERSION,
        initiative_id=initiative_id,
        chunk_id=chunk_id,
        chunk_title=chunk_title,
        next_chunk_id=next_chunk_id,
        next_chunk_title=next_chunk_title,
        next_requires_explicit_start=explicit_start,
    )


def _validate_sha(merge_sha: Any) -> None:
    """Validate one untrusted Git commit identifier."""
    if not isinstance(merge_sha, str) or not SHA_PATTERN.fullmatch(merge_sha):
        raise LoopMemoryError(
            "merge SHA must contain 40 lowercase hexadecimal characters"
        )


def _validate_repository_and_sha(repository: Any, merge_sha: Any) -> None:
    """Validate untrusted workflow inputs before constructing API paths."""
    if not isinstance(repository, str) or not REPOSITORY_PATTERN.fullmatch(repository):
        raise LoopMemoryError("repository must be owner/name")
    _validate_sha(merge_sha)


def _intent_path(metadata: LoopMetadata) -> str:
    """Return the only canonical repository path for one merge intent."""
    return f"{INTENT_PREFIX}{metadata.chunk_id}.json"


def _contract_title(contract_text: str, chunk_id: str) -> str | None:
    """Return the title from one canonical chunk-contract heading."""
    lines = contract_text.splitlines()
    first_line = lines[0] if lines else ""
    prefixes = (
        f"# Chunk Contract: {chunk_id} - ",
        f"# Chunk Contract: {chunk_id} — ",
    )
    prefix = next((value for value in prefixes if first_line.startswith(value)), None)
    if prefix is None:
        return None
    title = first_line[len(prefix) :].strip()
    return title or None


def _contract_start_phase(contract_text: str) -> str | None:
    """Return one explicit writer-directed lifecycle phase from a contract."""
    headings = re.findall(r"(?m)^## Start phase\s*$", contract_text)
    matches = re.findall(
        r"(?m)^## Start phase\s*\n\s*`?(planning|implementation)`?\s*$",
        contract_text,
    )
    if not headings:
        return None
    if len(headings) != 1 or len(matches) != 1:
        raise LoopMemoryError("start phase declaration is ambiguous or invalid")
    return matches[0]


def _initiative_directory_from_path(path: str, initiative_id: str) -> str | None:
    """Return the matching top-level initiative directory from one path."""
    if not path.startswith(CHUNK_CONTRACT_ROOT):
        return None
    initiative_directory = path[len(CHUNK_CONTRACT_ROOT) :].split("/", 1)[0]
    if initiative_directory == initiative_id or initiative_directory.startswith(
        f"{initiative_id}-"
    ):
        return initiative_directory
    return None


def _is_chunk_contract_path(path: str, initiative_directory: str) -> bool:
    """Return whether one path is a direct child of one canonical chunks directory."""
    prefix = f"{CHUNK_CONTRACT_ROOT}{initiative_directory}/chunks/"
    return (
        path.startswith(prefix)
        and "/" not in path[len(prefix) :]
        and path.endswith(".md")
    )


def _successor_contract_name_matches(name: str, chunk_id: str) -> bool:
    """Return whether one Markdown filename claims a successor chunk ID."""
    return name == f"{chunk_id}.md" or (
        name.startswith(f"{chunk_id}-") and name.endswith(".md")
    )


def _git_output(repository_root: Path, *args: str) -> str:
    """Return one bounded Git result or fail closed."""
    result = subprocess.run(
        ["git", "-C", str(repository_root), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or not value:
        raise LoopMemoryError("cannot resolve reviewed contract from current main")
    return value


def resolve_start_selection(
    repository_root: Path,
    *,
    initiative_id: str,
    chunk_id: str,
    phase: str,
    main_sha: str,
    declared_successor: bool,
) -> dict[str, Any]:
    """Bind one start selection to a unique regular contract on exact main."""
    _validate_sha(main_sha)
    if phase not in {"planning", "implementation"}:
        raise LoopMemoryError("start phase is invalid")
    if _git_output(repository_root, "rev-parse", "HEAD") != main_sha:
        raise LoopMemoryError("start contract tree is not exact current main")
    tree_output = _git_output(repository_root, "ls-tree", "-r", "--full-tree", "HEAD")
    tree_rows: list[tuple[str, str, str, str]] = []
    for line in tree_output.splitlines():
        try:
            metadata, path = line.split("\t", 1)
            mode, kind, blob_sha = metadata.split(" ", 2)
        except ValueError as exc:
            raise LoopMemoryError("current-main contract tree is malformed") from exc
        tree_rows.append((mode, kind, blob_sha, path))
    initiative_directories = sorted(
        {
            directory
            for _mode, _kind, _blob, path in tree_rows
            if (directory := _initiative_directory_from_path(path, initiative_id))
        }
    )
    if len(initiative_directories) != 1:
        raise LoopMemoryError("start initiative directory is not unique on current main")
    initiative_directory = initiative_directories[0]
    all_candidates = sorted(
        row
        for row in tree_rows
        if _successor_contract_name_matches(row[3].rsplit("/", 1)[-1], chunk_id)
        and row[3].startswith(CHUNK_CONTRACT_ROOT)
    )
    if any(
        _initiative_directory_from_path(path, initiative_id) != initiative_directory
        for _mode, _kind, _blob, path in all_candidates
    ):
        raise LoopMemoryError("start chunk contract crosses initiative directory")
    candidates = [
        row
        for row in all_candidates
        if row[0] == "100644"
        and row[1] == "blob"
        and _is_chunk_contract_path(row[3], initiative_directory)
    ]
    if len(candidates) != 1:
        raise LoopMemoryError("start chunk contract is not one regular file on current main")
    _mode, _kind, blob_sha, relative = candidates[0]
    _validate_sha(blob_sha)
    result = subprocess.run(
        ["git", "-C", str(repository_root), "cat-file", "blob", blob_sha],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        raw = result.stdout
        if result.returncode != 0 or len(raw) > 262144:
            raise LoopMemoryError("start chunk contract exceeds 262144 bytes")
        contract_text = raw.decode("utf-8")
        title = _contract_title(contract_text, chunk_id)
    except UnicodeDecodeError as exc:
        raise LoopMemoryError("cannot read start chunk contract") from exc
    if not title:
        raise LoopMemoryError("start chunk contract has no canonical heading")
    declared_phase = _contract_start_phase(contract_text)
    expected_phase = declared_phase or ("implementation" if declared_successor else None)
    if expected_phase is None:
        raise LoopMemoryError("writer-directed contract has no explicit start phase")
    if phase != expected_phase:
        raise LoopMemoryError("requested start phase does not match reviewed contract")
    return {
        "schema_version": 1,
        "mode": "declared_successor" if declared_successor else "writer_directed",
        "phase": phase,
        "contract_path": relative,
        "contract_title": title,
        "contract_blob_sha": blob_sha,
    }


def _validate_start_selection(selection: Any, event: dict[str, Any]) -> dict[str, Any]:
    """Validate the closed signed contract-selection envelope."""
    required = {
        "schema_version", "mode", "phase", "contract_path",
        "contract_title", "contract_blob_sha",
    }
    if not isinstance(selection, dict) or set(selection) != required:
        raise LoopMemoryError("start selection has an invalid schema")
    if selection.get("schema_version") != 1 or selection.get("mode") not in {
        "declared_successor", "writer_directed"
    } or selection.get("phase") not in {"planning", "implementation"}:
        raise LoopMemoryError("start selection is unsupported")
    path = selection.get("contract_path")
    title = selection.get("contract_title")
    blob = selection.get("contract_blob_sha")
    initiative_directory = (
        _initiative_directory_from_path(path, event["initiative_id"])
        if isinstance(path, str) else None
    )
    if (
        initiative_directory is None
        or not _is_chunk_contract_path(path, initiative_directory)
        or not _successor_contract_name_matches(path.rsplit("/", 1)[-1], event["chunk_id"])
    ):
        raise LoopMemoryError("start selection contract path is invalid")
    _bounded_text(title, "start selection title", maximum=160)
    _validate_sha(blob)
    return selection


def _validate_local_successor_contract(
    repository_root: Path, metadata: LoopMetadata
) -> None:
    """Bind a non-null successor to one matching local chunk contract."""
    if metadata.next_chunk_id is None:
        return
    initiatives_root = repository_root / CHUNK_CONTRACT_ROOT
    initiative_directories = sorted(
        path.name
        for path in initiatives_root.iterdir()
        if path.is_dir()
        and (
            path.name == metadata.initiative_id
            or path.name.startswith(f"{metadata.initiative_id}-")
        )
    )
    if len(initiative_directories) != 1:
        raise LoopMemoryError(
            "initiative_id must resolve to exactly one initiative directory"
        )
    initiative_directory = initiative_directories[0]
    all_candidates = sorted(
        path
        for path in initiatives_root.glob("*/chunks/*.md")
        if _successor_contract_name_matches(path.name, metadata.next_chunk_id)
    )
    foreign_candidates = [
        path
        for path in all_candidates
        if path.parent.parent.name != initiative_directory
    ]
    if foreign_candidates:
        raise LoopMemoryError(
            "next_chunk_id must not exist under another initiative directory"
        )
    chunks_root = initiatives_root / initiative_directory / "chunks"
    candidates = sorted(
        path
        for path in chunks_root.glob("*.md")
        if _successor_contract_name_matches(path.name, metadata.next_chunk_id)
    )
    if len(candidates) != 1:
        raise LoopMemoryError(
            "next_chunk_id must resolve to exactly one chunk contract"
        )
    try:
        title = _contract_title(
            candidates[0].read_text(encoding="utf-8"), metadata.next_chunk_id
        )
    except (OSError, UnicodeDecodeError) as exc:
        raise LoopMemoryError("cannot read next chunk contract") from exc
    if title != metadata.next_chunk_title:
        raise LoopMemoryError("next chunk contract heading does not match intent")


def _decode_github_blob(payload: Any, label: str, maximum: int) -> tuple[str, str]:
    """Decode one bounded GitHub base64 blob response."""
    if not isinstance(payload, dict) or payload.get("encoding") != "base64":
        raise LoopMemoryError(f"{label} content response has an invalid shape")
    blob_sha = payload.get("sha")
    content = payload.get("content")
    if not isinstance(blob_sha, str) or not SHA_PATTERN.fullmatch(blob_sha):
        raise LoopMemoryError(f"{label} blob has no canonical SHA")
    if not isinstance(content, str):
        raise LoopMemoryError(f"{label} blob has no encoded content")
    try:
        normalized_content = re.sub(r"[ \t\r\n]", "", content)
        raw = base64.b64decode(normalized_content, validate=True)
        if len(raw) > maximum:
            raise LoopMemoryError(f"{label} document exceeds {maximum} bytes")
        text = raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise LoopMemoryError(f"{label} content is not valid base64 UTF-8") from exc
    return text, blob_sha


def _validate_remote_successor_contract(
    client: GitHubClient,
    repository: str,
    head_sha: str,
    metadata: LoopMetadata,
) -> None:
    """Bind a non-null successor to one contract on the reviewed PR head."""
    if metadata.next_chunk_id is None:
        return
    tree = client.get_json(f"/repos/{repository}/git/trees/{head_sha}?recursive=1")
    if (
        not isinstance(tree, dict)
        or tree.get("truncated") is not False
        or not isinstance(tree.get("tree"), list)
    ):
        raise LoopMemoryError("reviewed-head repository tree is incomplete")
    initiative_directories = sorted(
        {
            initiative_directory
            for item in tree["tree"]
            if isinstance(item, dict) and isinstance(item.get("path"), str)
            if (
                initiative_directory := _initiative_directory_from_path(
                    item["path"], metadata.initiative_id
                )
            )
        }
    )
    if len(initiative_directories) != 1:
        raise LoopMemoryError(
            "initiative_id must resolve to exactly one reviewed-head initiative directory"
        )
    initiative_directory = initiative_directories[0]
    candidates = []
    foreign_candidates = []
    for item in tree["tree"]:
        if not isinstance(item, dict) or item.get("type") != "blob":
            continue
        path = item.get("path")
        blob_sha = item.get("sha")
        if not isinstance(path, str) or not isinstance(blob_sha, str):
            continue
        name = path.rsplit("/", 1)[-1]
        if not _successor_contract_name_matches(name, metadata.next_chunk_id):
            continue
        relative = path.removeprefix(CHUNK_CONTRACT_ROOT)
        parts = relative.split("/")
        if (
            not path.startswith(CHUNK_CONTRACT_ROOT)
            or len(parts) != 3
            or parts[1] != "chunks"
        ):
            continue
        if parts[0] != initiative_directory:
            foreign_candidates.append((path, blob_sha))
        elif _is_chunk_contract_path(path, initiative_directory):
            candidates.append((path, blob_sha))
    if foreign_candidates:
        raise LoopMemoryError(
            "next_chunk_id must not exist under another reviewed-head initiative directory"
        )
    if len(candidates) != 1:
        raise LoopMemoryError(
            "next_chunk_id must resolve to exactly one reviewed-head chunk contract"
        )
    _, blob_sha = candidates[0]
    if not SHA_PATTERN.fullmatch(blob_sha):
        raise LoopMemoryError("next chunk contract has no canonical blob SHA")
    contract_text, returned_sha = _decode_github_blob(
        client.get_json(f"/repos/{repository}/git/blobs/{blob_sha}"),
        "next chunk contract",
        262144,
    )
    if returned_sha != blob_sha:
        raise LoopMemoryError("next chunk contract blob identity does not match tree")
    title = _contract_title(contract_text, metadata.next_chunk_id)
    if title != metadata.next_chunk_title:
        raise LoopMemoryError("next chunk contract heading does not match intent")


def load_committed_merge_intent(
    client: GitHubClient,
    repository: str,
    pr_number: int,
    head_sha: str,
) -> tuple[LoopMetadata, str, str]:
    """Load the one newly added merge intent from the reviewed PR head."""
    files = client.get_paginated(f"/repos/{repository}/pulls/{pr_number}/files")
    intent_changes = [
        item
        for item in files
        if isinstance(item, dict)
        and isinstance(item.get("filename"), str)
        and item["filename"].startswith(INTENT_PREFIX)
    ]
    if len(intent_changes) != 1 or intent_changes[0].get("status") != "added":
        raise LoopMemoryError(
            "merged pull request must add exactly one merge-intent file"
        )
    path = intent_changes[0]["filename"]
    encoded_path = urllib.parse.quote(path, safe="/")
    payload = client.get_json(
        f"/repos/{repository}/contents/{encoded_path}?ref={head_sha}"
    )
    text, blob_sha = _decode_github_blob(payload, "merge-intent", 8192)
    metadata = parse_loop_metadata(text)
    if path != _intent_path(metadata):
        raise LoopMemoryError("merge-intent path does not match its chunk_id")
    _validate_remote_successor_contract(client, repository, head_sha, metadata)
    return metadata, path, blob_sha


def validate_local_merge_intent(repository_root: Path, base_ref: str) -> LoopMetadata:
    """Validate one newly added merge intent in the local PR diff."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository_root),
            "diff",
            "--name-status",
            f"{base_ref}...HEAD",
            "--",
            INTENT_PREFIX,
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise LoopMemoryError(f"cannot resolve merge-intent base ref {base_ref!r}")
    changes = [line.split("\t", 1) for line in result.stdout.splitlines() if line]
    if len(changes) != 1 or len(changes[0]) != 2 or changes[0][0] != "A":
        raise LoopMemoryError("pull request must add exactly one merge-intent file")
    path = changes[0][1]
    intent_path = repository_root / path
    try:
        metadata = parse_loop_metadata(intent_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise LoopMemoryError("cannot read local merge-intent file") from exc
    if path != _intent_path(metadata):
        raise LoopMemoryError("merge-intent path does not match its chunk_id")
    _validate_local_successor_contract(repository_root, metadata)
    return metadata


def _git_lines(repository_root: Path, arguments: list[str], failure: str) -> list[str]:
    """Run one read-only Git query and return its non-empty output lines."""
    result = subprocess.run(
        ["git", "-C", str(repository_root), *arguments],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise LoopMemoryError(failure)
    return [line for line in result.stdout.splitlines() if line]


def _is_ancestor(repository_root: Path, ancestor: str, descendant: str) -> bool:
    """Return whether one commit is an ancestor, failing on an invalid Git query."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository_root),
            "merge-base",
            "--is-ancestor",
            ancestor,
            descendant,
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode not in (0, 1):
        raise LoopMemoryError("cannot resolve main commit ancestry")
    return result.returncode == 0


def plan_reconciliation_commits(
    repository_root: Path, target_sha: str, current_sha: str | None
) -> list[str]:
    """List every first-parent commit needed to reach one protected-main target."""
    _validate_sha(target_sha)
    if current_sha:
        _validate_sha(current_sha)
        if _is_ancestor(repository_root, target_sha, current_sha):
            return []
        if not _is_ancestor(repository_root, current_sha, target_sha):
            raise LoopMemoryError("canonical state is not on the target main ancestry")
        return _git_lines(
            repository_root,
            ["rev-list", "--reverse", "--first-parent", f"{current_sha}..{target_sha}"],
            "cannot enumerate unrecorded main commits",
        )

    bootstrap_commits = _git_lines(
        repository_root,
        [
            "rev-list",
            "--reverse",
            "--first-parent",
            target_sha,
            "--",
            BOOTSTRAP_INTENT_PATH,
        ],
        "cannot resolve the loop-memory bootstrap commit",
    )
    if len(bootstrap_commits) != 1 or not SHA_PATTERN.fullmatch(bootstrap_commits[0]):
        raise LoopMemoryError("target main history has no unique loop-memory bootstrap")
    bootstrap_sha = bootstrap_commits[0]
    successors = _git_lines(
        repository_root,
        ["rev-list", "--reverse", "--first-parent", f"{bootstrap_sha}..{target_sha}"],
        "cannot enumerate commits after the loop-memory bootstrap",
    )
    return [bootstrap_sha, *successors]


def resolve_reconciliation_target(
    repository_root: Path,
    event_name: str,
    event_sha: str,
    current_main_sha: str,
) -> str:
    """Bind one workflow event to the current protected-main commit."""
    _validate_sha(event_sha)
    _validate_sha(current_main_sha)
    if event_name == "repository_dispatch":
        if event_sha != current_main_sha:
            raise LoopMemoryError(
                "replay target is stale; dispatch current protected-main SHA"
            )
        return current_main_sha
    if event_name == "push":
        if not _is_ancestor(repository_root, event_sha, current_main_sha):
            raise LoopMemoryError(
                "push event SHA is not on current protected-main ancestry"
            )
        return current_main_sha
    raise LoopMemoryError("unsupported loop-memory event")


def _latest_named(
    items: list[dict[str, Any]], name_key: str, time_key: str
) -> dict[str, dict[str, Any]]:
    """Return the latest observed result for each named check or status."""
    latest: dict[str, dict[str, Any]] = {}
    for item in items:
        name = item.get(name_key)
        if not isinstance(name, str) or not name:
            continue
        current = latest.get(name)
        if current is None or str(item.get(time_key) or "") >= str(
            current.get(time_key) or ""
        ):
            latest[name] = item
    return latest


def _check_evidence(
    check_runs: list[dict[str, Any]], statuses: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build bounded required-check evidence without treating it as merge authority."""
    latest_checks = _latest_named(check_runs, "name", "started_at")
    latest_statuses = _latest_named(statuses, "context", "updated_at")
    observed: dict[str, dict[str, str | None]] = {}
    for name in REQUIRED_CHECKS:
        if name in latest_checks:
            item = latest_checks[name]
            observed[name] = {
                "kind": "check_run",
                "conclusion": item.get("conclusion") or item.get("status"),
                "url": item.get("details_url"),
            }
        elif name in latest_statuses:
            item = latest_statuses[name]
            observed[name] = {
                "kind": "status",
                "conclusion": item.get("state"),
                "url": item.get("target_url"),
            }
        else:
            observed[name] = {"kind": "missing", "conclusion": None, "url": None}
    passed = all(item["conclusion"] == "success" for item in observed.values())
    return {"required": observed, "all_required_passed": passed}


def _commit_tree_sha(payload: Any, label: str) -> str:
    """Return one canonical tree SHA from a GitHub commit payload."""
    tree_sha = (
        payload.get("commit", {}).get("tree", {}).get("sha")
        if isinstance(payload, dict)
        else None
    )
    _validate_sha(tree_sha)
    return tree_sha


def _validate_protected_actions_checks(
    client: GitHubClient, repository: str, head_sha: str
) -> None:
    """Require exact protected GitHub Actions checks on one reviewed head."""
    payload = client.get_json(
        f"/repos/{repository}/commits/{head_sha}/check-runs?per_page=100"
    )
    runs = payload.get("check_runs") if isinstance(payload, dict) else None
    total = payload.get("total_count") if isinstance(payload, dict) else None
    if not isinstance(runs, list) or type(total) is not int or total != len(runs):
        raise LoopMemoryError("planning intake check-run evidence is incomplete")
    seen_ids: set[int] = set()
    for name in ("agent-gates", "test"):
        matches = [item for item in runs if isinstance(item, dict) and item.get("name") == name]
        if not matches:
            raise LoopMemoryError(f"planning intake check {name} is missing")
        candidates: list[tuple[datetime, int, dict[str, Any]]] = []
        for item in matches:
            app = item.get("app")
            check_id = item.get("id")
            started_at = _rfc3339_instant(item.get("started_at"))
            completed_at = _rfc3339_instant(item.get("completed_at"))
            if (
                type(check_id) is not int
                or check_id <= 0
                or check_id in seen_ids
                or item.get("head_sha") != head_sha
                or item.get("status") != "completed"
                or item.get("conclusion") not in CHECK_RUN_CONCLUSIONS
                or completed_at < started_at
                or not isinstance(app, dict)
                or app.get("id") != GITHUB_ACTIONS_APP_ID
                or app.get("slug") != GITHUB_ACTIONS_APP_SLUG
            ):
                raise LoopMemoryError(f"planning intake check {name} has invalid provenance")
            seen_ids.add(check_id)
            candidates.append((started_at, check_id, item))
        item = max(candidates, key=lambda candidate: (candidate[0], candidate[1]))[2]
        if item.get("conclusion") != "success":
            raise LoopMemoryError(f"planning intake check {name} has invalid provenance")


def _rfc3339_instant(value: Any) -> datetime:
    """Return one timezone-aware RFC3339 instant or fail closed."""
    if not isinstance(value, str) or not RFC3339_PATTERN.fullmatch(value):
        raise LoopMemoryError("planning intake check timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LoopMemoryError("planning intake check timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LoopMemoryError("planning intake check timestamp is invalid")
    return parsed


def _tree_entries(
    client: GitHubClient, repository: str, tree_sha: str, label: str
) -> dict[str, tuple[str, str, str]]:
    """Return a complete canonical path-to-entry map for one Git tree."""
    tree = client.get_json(f"/repos/{repository}/git/trees/{tree_sha}?recursive=1")
    entries = tree.get("tree") if isinstance(tree, dict) else None
    truncated = tree.get("truncated") if isinstance(tree, dict) else None
    if truncated is not False or not isinstance(entries, list):
        raise LoopMemoryError(f"planning intake {label} tree is incomplete")
    result: dict[str, tuple[str, str, str]] = {}
    seen_paths: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise LoopMemoryError(f"planning intake {label} tree is malformed")
        path, mode, kind, sha = (
            item.get("path"), item.get("mode"), item.get("type"), item.get("sha")
        )
        if (
            not isinstance(path, str)
            or not path
            or path in seen_paths
            or path.startswith("/")
            or "\x00" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or not isinstance(mode, str)
            or not isinstance(kind, str)
            or not isinstance(sha, str)
            or not SHA_PATTERN.fullmatch(sha)
        ):
            raise LoopMemoryError(f"planning intake {label} tree is malformed")
        seen_paths.add(path)
        if kind == "tree":
            if mode != "040000":
                raise LoopMemoryError(
                    f"planning intake {label} tree has unsupported entry mode"
                )
            continue
        if (kind == "blob" and mode in {"100644", "100755", "120000"}) or (
            kind == "commit" and mode == "160000"
        ):
            result[path] = (mode, kind, sha)
            continue
        raise LoopMemoryError(
            f"planning intake {label} tree has unsupported entry mode"
        )
    retained_paths = set(result)
    for path in seen_paths:
        parts = path.split("/")
        if any("/".join(parts[:index]) in retained_paths for index in range(1, len(parts))):
            raise LoopMemoryError(
                f"planning intake {label} tree has conflicting leaf paths"
            )
    return result


def _tree_delta(
    before: dict[str, tuple[str, str, str]],
    after: dict[str, tuple[str, str, str]],
) -> dict[str, tuple[str, str, str] | None]:
    """Return the exact path delta between two complete trees."""
    return {
        path: after.get(path)
        for path in sorted(set(before) | set(after))
        if before.get(path) != after.get(path)
    }


def _planning_intake_directory(path: str, initiative_id: str) -> str | None:
    """Return one canonical new-initiative directory for a planning path."""
    prefix = f"{CHUNK_CONTRACT_ROOT}{initiative_id}-"
    if not path.startswith(prefix):
        return None
    relative = path[len(CHUNK_CONTRACT_ROOT) :]
    directory = relative.split("/", 1)[0]
    pattern = re.compile(rf"^{re.escape(initiative_id)}-[a-z0-9]+(?:-[a-z0-9]+)*$")
    return directory if pattern.fullmatch(directory) and "/" in relative else None


def _planning_chunk_name_matches(filename: str, initiative_id: str) -> bool:
    """Return whether a planning intake chunk uses one canonical contract name."""
    pattern = re.compile(
        rf"^{re.escape(initiative_id)}-[A-Z0-9]+(?:-[A-Z0-9]+)*"
        r"(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?\.md$"
    )
    return bool(pattern.fullmatch(filename))


def _collect_planning_intake(
    client: GitHubClient,
    repository: str,
    *,
    metadata: LoopMetadata,
    pr_number: int,
    head_sha: str,
    base_sha: str,
    first_parent_sha: str,
    merge_commit: dict[str, Any],
) -> dict[str, Any] | None:
    """Validate and describe one closed planning-only first-initiative PR."""
    if metadata.chunk_id != f"{metadata.initiative_id}-PLAN":
        return None
    if not isinstance(base_sha, str) or not SHA_PATTERN.fullmatch(base_sha):
        raise LoopMemoryError("planning intake has no canonical reviewed base SHA")
    if (
        metadata.next_chunk_id is None
        or not metadata.next_requires_explicit_start
    ):
        raise LoopMemoryError("planning intake requires one explicit-start successor")
    files = client.get_paginated(f"/repos/{repository}/pulls/{pr_number}/files")
    if not files:
        raise LoopMemoryError("planning intake has no reviewed files")
    changed_paths: list[str] = []
    initiative_directory: str | None = None
    intent_path = _intent_path(metadata)
    for item in files:
        if not isinstance(item, dict) or not {"filename", "status"}.issubset(item):
            raise LoopMemoryError("planning intake file evidence is malformed")
        path = item.get("filename")
        if not isinstance(path, str) or item.get("status") != "added":
            raise LoopMemoryError("planning intake permits additive files only")
        if path != intent_path:
            directory = _planning_intake_directory(path, metadata.initiative_id)
            if directory is None:
                raise LoopMemoryError("planning intake contains a foreign path")
            if initiative_directory is None:
                initiative_directory = directory
            elif initiative_directory != directory:
                raise LoopMemoryError("planning intake contains multiple initiative directories")
        changed_paths.append(path)
    if initiative_directory is None or len(changed_paths) != len(set(changed_paths)):
        raise LoopMemoryError("planning intake path set is invalid")
    root = f"{CHUNK_CONTRACT_ROOT}{initiative_directory}/"
    root_files: set[str] = set()
    chunks: list[str] = []
    reviews: set[str] = set()
    for path in changed_paths:
        if path == intent_path:
            continue
        relative = path.removeprefix(root)
        parts = relative.split("/")
        if any(part.startswith(".") for part in parts) or any(
            part.casefold() == "agents.md" for part in parts
        ):
            raise LoopMemoryError("planning intake path grammar is invalid")
        if "/" not in relative:
            root_files.add(relative)
        elif (
            relative.startswith("chunks/")
            and relative.count("/") == 1
            and _planning_chunk_name_matches(parts[-1], metadata.initiative_id)
        ):
            chunks.append(path)
        elif relative.startswith("reviews/") and relative.count("/") == 1:
            reviews.add(relative.removeprefix("reviews/"))
        else:
            raise LoopMemoryError("planning intake path grammar is invalid")
    if root_files not in {PLANNING_ROOT_FILES, PLANNING_ROOT_FILES | {"REVIEW_LOG.md"}}:
        raise LoopMemoryError("planning intake root file set is invalid")
    expected_reviews = {
        f"{metadata.initiative_id}-PLAN-internal-review-evidence.md",
        f"{metadata.initiative_id}-PLAN-pr-trust-bundle.md",
    }
    if reviews != expected_reviews or not chunks:
        raise LoopMemoryError("planning intake review or contract set is invalid")
    successor_matches = [
        path for path in chunks
        if _successor_contract_name_matches(path.rsplit("/", 1)[-1], metadata.next_chunk_id)
    ]
    if len(successor_matches) != 1:
        raise LoopMemoryError("planning intake successor contract is not exact")
    successor_payload = client.get_json(
        f"/repos/{repository}/contents/"
        f"{urllib.parse.quote(successor_matches[0], safe='/')}?ref={head_sha}"
    )
    successor_text, _successor_blob = _decode_github_blob(
        successor_payload, "planning successor", 262144
    )
    if _contract_start_phase(successor_text) != "implementation":
        raise LoopMemoryError("planning intake successor is not implementation phase")
    status_path = f"{root}STATUS.md"
    status_payload = client.get_json(
        f"/repos/{repository}/contents/{urllib.parse.quote(status_path, safe='/')}?ref={head_sha}"
    )
    status_text, _status_blob = _decode_github_blob(status_payload, "planning status", 65536)
    if not re.search(r"(?mi)^- Active planning chunk:\s*(?:`?none`?)\s*$", status_text) or not re.search(
        r"(?mi)^- Active implementation chunk:\s*(?:`?none`?)\s*$", status_text
    ):
        raise LoopMemoryError("planning intake status claims active work")
    head_commit = client.get_json(f"/repos/{repository}/commits/{head_sha}")
    base_commit = client.get_json(f"/repos/{repository}/commits/{base_sha}")
    first_parent_commit = client.get_json(
        f"/repos/{repository}/commits/{first_parent_sha}"
    )
    head_tree = _commit_tree_sha(head_commit, "reviewed head")
    base_tree = _commit_tree_sha(base_commit, "reviewed base")
    first_parent_tree = _commit_tree_sha(first_parent_commit, "first parent")
    merge_tree = _commit_tree_sha(merge_commit, "merge")
    base_entries = _tree_entries(client, repository, base_tree, "reviewed base")
    head_entries = _tree_entries(client, repository, head_tree, "reviewed head")
    first_parent_entries = _tree_entries(
        client, repository, first_parent_tree, "first parent"
    )
    merge_entries = _tree_entries(client, repository, merge_tree, "merge")
    reviewed_delta = _tree_delta(base_entries, head_entries)
    merged_delta = _tree_delta(first_parent_entries, merge_entries)
    if reviewed_delta != merged_delta or sorted(reviewed_delta) != sorted(changed_paths):
        raise LoopMemoryError("planning intake authoritative tree delta does not match")
    if any(
        path in base_entries or entry != ("100644", "blob", entry[2])
        for path, entry in reviewed_delta.items()
        if entry is not None
    ) or any(entry is None for entry in reviewed_delta.values()):
        raise LoopMemoryError("planning intake file mode is invalid")
    delta_sha256 = hashlib.sha256(
        _canonical_json(reviewed_delta).encode("utf-8")
    ).hexdigest()
    _validate_protected_actions_checks(client, repository, head_sha)
    return {
        "schema_version": PLANNING_INTAKE_VERSION,
        "initiative_directory": initiative_directory,
        "base_tree_sha": base_tree,
        "head_tree_sha": head_tree,
        "first_parent_tree_sha": first_parent_tree,
        "merge_tree_sha": merge_tree,
        "delta_sha256": delta_sha256,
        "changed_paths": sorted(changed_paths),
    }


def collect_merge_record(
    client: GitHubClient,
    repository: str,
    merge_sha: str,
) -> dict[str, Any]:
    """Collect one exact merged PR and its bounded loop metadata from GitHub."""
    _validate_repository_and_sha(repository, merge_sha)
    associated = client.get_json(
        f"/repos/{repository}/commits/{merge_sha}/pulls?per_page=100"
    )
    if not isinstance(associated, list):
        raise LoopMemoryError("associated pull request response is not a list")
    matches = [
        pr
        for pr in associated
        if pr.get("merge_commit_sha") == merge_sha
        and pr.get("merged_at")
        and pr.get("base", {}).get("ref") == "main"
        and pr.get("state") == "closed"
    ]
    if len(matches) != 1:
        raise LoopMemoryError(
            "merge SHA must resolve to exactly one merged pull request targeting main"
        )
    associated_pr = matches[0]
    pr_number = associated_pr.get("number")
    if not isinstance(pr_number, int) or pr_number <= 0:
        raise LoopMemoryError("merged pull request has no positive number")
    pr = client.get_json(f"/repos/{repository}/pulls/{pr_number}")
    if not isinstance(pr, dict):
        raise LoopMemoryError("merged pull request response is not an object")
    if (
        pr.get("merge_commit_sha") != merge_sha
        or pr.get("merged_at") != associated_pr.get("merged_at")
        or pr.get("base", {}).get("ref") != "main"
    ):
        raise LoopMemoryError(
            "full pull request facts do not match the associated merge"
        )
    head_sha = pr.get("head", {}).get("sha")
    if not isinstance(head_sha, str) or not SHA_PATTERN.fullmatch(head_sha):
        raise LoopMemoryError("merged pull request has no canonical head SHA")
    base_sha = pr.get("base", {}).get("sha")
    metadata, intent_path, intent_blob_sha = load_committed_merge_intent(
        client,
        repository,
        pr_number,
        head_sha,
    )

    commit_payload = client.get_json(f"/repos/{repository}/commits/{merge_sha}")
    parents = (
        commit_payload.get("parents") if isinstance(commit_payload, dict) else None
    )
    if (
        not isinstance(parents, list)
        or not parents
        or not isinstance(parents[0], dict)
        or not isinstance(parents[0].get("sha"), str)
        or not SHA_PATTERN.fullmatch(parents[0]["sha"])
    ):
        raise LoopMemoryError("merged main commit has no canonical first parent")
    first_parent_sha = parents[0]["sha"]

    check_payload = client.get_json(
        f"/repos/{repository}/commits/{head_sha}/check-runs?per_page=100"
    )
    status_payload = client.get_json(
        f"/repos/{repository}/commits/{head_sha}/status?per_page=100"
    )
    check_runs = (
        check_payload.get("check_runs", []) if isinstance(check_payload, dict) else []
    )
    statuses = (
        status_payload.get("statuses", []) if isinstance(status_payload, dict) else []
    )
    if not isinstance(check_runs, list) or not isinstance(statuses, list):
        raise LoopMemoryError("GitHub check evidence has an invalid shape")

    merged_at = pr["merged_at"]
    _parse_timestamp(merged_at, "merged_at")
    merged_by = pr.get("merged_by", {}).get("login")
    if not isinstance(merged_by, str) or not merged_by:
        raise LoopMemoryError("merged pull request has no merged_by identity")
    expected_pr_url = f"https://github.com/{repository}/pull/{pr_number}"
    if pr.get("html_url") != expected_pr_url:
        raise LoopMemoryError(
            "merged pull request URL does not match repository and number"
        )

    record = {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "state_branch": STATE_BRANCH,
        "updated_at": merged_at,
        "source": {
            "main_sha": merge_sha,
            "first_parent_sha": first_parent_sha,
            "pr_number": pr_number,
            "pr_url": expected_pr_url,
            "pr_title": _bounded_text(
                pr.get("title"), "pull request title", maximum=240
            ),
            "head_sha": head_sha,
            "head_ref": _bounded_text(
                pr.get("head", {}).get("ref"), "head ref", maximum=240
            ),
            "merged_at": merged_at,
            "merged_by": merged_by,
            "intent_path": intent_path,
            "intent_blob_sha": intent_blob_sha,
        },
        "completed_chunk": asdict(metadata),
        "active": {"planning_chunk": None, "implementation_chunk": None},
        "gate": {
            "status": "stopped_after_merge",
            "next_chunk_id": metadata.next_chunk_id,
            "next_chunk_title": metadata.next_chunk_title,
            "next_requires_explicit_start": metadata.next_requires_explicit_start,
        },
        "checks": _check_evidence(check_runs, statuses),
    }
    planning_intake = _collect_planning_intake(
        client,
        repository,
        metadata=metadata,
        pr_number=pr_number,
        head_sha=head_sha,
        base_sha=base_sha,
        first_parent_sha=first_parent_sha,
        merge_commit=commit_payload,
    )
    if planning_intake is not None:
        record["planning_intake"] = planning_intake
    return record


def _parse_timestamp(value: Any, field: str) -> datetime:
    """Parse one UTC GitHub timestamp."""
    if not isinstance(value, str):
        raise LoopMemoryError(f"{field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LoopMemoryError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise LoopMemoryError(f"{field} must include a timezone")
    return parsed


def _event_type(record: dict[str, Any]) -> str:
    """Return the typed event name, treating pre-04B records as merges."""
    event = record.get("event")
    if event is None:
        return "merge"
    if not isinstance(event, dict) or event.get("type") not in {
        "merge",
        "cutover",
        "start",
        "cancel",
    }:
        raise LoopMemoryError("loop-memory event has an invalid type")
    return event["type"]


def _validate_event(event: Any) -> str:
    """Validate one closed, attributable authority-event envelope."""
    if not isinstance(event, dict):
        raise LoopMemoryError("loop-memory event must be an object")
    event_type = event.get("type")
    historical = {
        "type",
        "event_id",
        "run_id",
        "created_at",
        "dispatcher",
        "approvers",
        "reason",
        "main_sha",
        "prior_state_tip",
        "initiative_id",
        "chunk_id",
    }
    dispatcher_authorized = historical - {"approvers"} | {"authorization"}
    selected_start = dispatcher_authorized | {"selection"}
    selected_cancel = historical | {"selection"}
    if event_type not in {"start", "cancel"} or frozenset(event) not in {
        frozenset(historical),
        frozenset(dispatcher_authorized),
        frozenset(selected_start),
        frozenset(selected_cancel),
    }:
        raise LoopMemoryError("authority event has an invalid schema")
    run_id = event.get("run_id")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
        raise LoopMemoryError("authority event run_id must be positive")
    if event.get("event_id") != f"github-actions:{run_id}:{event_type}":
        raise LoopMemoryError("authority event ID does not match its run")
    _parse_timestamp(event.get("created_at"), "event created_at")
    for field, maximum in (("dispatcher", 160), ("reason", 500)):
        _bounded_text(event.get(field), f"event {field}", maximum=maximum)
    if "approvers" in event:
        approvers = event["approvers"]
        if not isinstance(approvers, list) or not approvers:
            raise LoopMemoryError("authority event needs an approving reviewer")
        normalized = [_bounded_text(value, "event approver") for value in approvers]
        if len(set(normalized)) != len(normalized):
            raise LoopMemoryError("authority event approvers must be unique")
        if event["dispatcher"] in normalized:
            raise LoopMemoryError("authority event reviewer must differ from dispatcher")
    else:
        authorization = event["authorization"]
        legacy_authorization = {
            "schema_version": 1,
            "type": "github_workflow_dispatch",
            "actor": event["dispatcher"],
        }
        repository_permission = {
            "schema_version": 2,
            "type": "github_repository_permission",
            "actor": event["dispatcher"],
            "permission": authorization.get("permission") if isinstance(authorization, dict) else None,
        }
        if (
            event_type != "start"
            or authorization not in (legacy_authorization, repository_permission)
            or (
                authorization == repository_permission
                and authorization["permission"] not in {"write", "push", "maintain", "admin"}
            )
        ):
            raise LoopMemoryError("dispatcher authorization is invalid")
    if "selection" in event:
        _validate_start_selection(event["selection"], event)
    _validate_sha(event.get("main_sha"))
    _validate_sha(event.get("prior_state_tip"))
    for field in ("initiative_id", "chunk_id"):
        value = event.get(field)
        if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
            raise LoopMemoryError(f"authority event {field} is invalid")
    if not event["chunk_id"].startswith(f"{event['initiative_id']}-"):
        raise LoopMemoryError("authority event chunk crosses initiative scope")
    return event_type


def _validate_cutover_event(event: Any, exemptions: Any, main_sha: Any) -> None:
    if not isinstance(event, dict) or set(event) != {
        "type", "main_sha", "legacy_exemptions"
    }:
        raise LoopMemoryError("cutover event has an invalid schema")
    if event.get("type") != "cutover" or event.get("main_sha") != main_sha:
        raise LoopMemoryError("cutover event is not bound to its merge")
    if event.get("legacy_exemptions") != exemptions:
        raise LoopMemoryError("cutover event exemptions do not match signed state")


def collect_authority_event(
    client: GitHubClient,
    repository: str,
    *,
    action: str,
    initiative_id: str,
    chunk_id: str,
    reason: str,
    run_id: int,
    dispatcher: str,
    main_sha: str,
    prior_state_tip: str,
    start_permissions: frozenset[str],
    selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect immutable GitHub authority evidence for a start/cancel event."""
    _validate_repository_and_sha(repository, main_sha)
    run = client.get_json(f"/repos/{repository}/actions/runs/{run_id}")
    if not isinstance(run, dict) or run.get("id") != run_id:
        raise LoopMemoryError("workflow run evidence does not match run_id")
    if run.get("run_attempt") != 1 or run.get("event") != "workflow_dispatch":
        raise LoopMemoryError("authority event must be a first-attempt dispatch")
    if run.get("head_branch") != "main" or run.get("head_sha") != main_sha:
        raise LoopMemoryError("authority event is not bound to expected main")
    if run.get("actor", {}).get("login") != dispatcher:
        raise LoopMemoryError("workflow dispatcher evidence does not match")
    permission = None
    if action == "start":
        permission_payload = client.get_json(
            f"/repos/{repository}/collaborators/{dispatcher}/permission"
        )
        permission = (
            permission_payload.get("permission")
            if isinstance(permission_payload, dict) else None
        )
        if permission not in start_permissions:
            raise LoopMemoryError("workflow dispatcher has no permitted repository write access")
    event = {
        "type": action,
        "event_id": f"github-actions:{run_id}:{action}",
        "run_id": run_id,
        "created_at": run.get("created_at"),
        "dispatcher": dispatcher,
        "reason": reason,
        "main_sha": main_sha,
        "prior_state_tip": prior_state_tip,
        "initiative_id": initiative_id,
        "chunk_id": chunk_id,
    }
    if action == "start":
        event["authorization"] = {
            "schema_version": 2,
            "type": "github_repository_permission",
            "actor": dispatcher,
            "permission": permission,
        }
        if selection is not None:
            event["selection"] = selection
    else:
        approvals = client.get_json(
            f"/repos/{repository}/actions/runs/{run_id}/approvals"
        )
        if not isinstance(approvals, list):
            raise LoopMemoryError("workflow approval history is invalid")
        approved = [
            item
            for item in approvals
            if isinstance(item, dict) and item.get("state") == "approved"
        ]
        if not approved or any(
            not isinstance(item.get("environments"), list)
            or len(item["environments"]) != 1
            or item["environments"][0].get("name") != "loop-memory-start"
            for item in approved
        ):
            raise LoopMemoryError(
                "approval history is not bound to loop-memory-start"
            )
        event["approvers"] = sorted(
            {
                item.get("user", {}).get("login")
                for item in approved
                if item.get("user", {}).get("login")
            }
        )
        if selection is not None:
            event["selection"] = selection
    _validate_event(event)
    return event


def load_start_permissions(repository_root: Path) -> frozenset[str]:
    """Load repository permissions eligible to dispatch a signed start."""
    policy = _load_json(repository_root / START_AUTHORITIES_PATH)
    if not isinstance(policy, dict) or set(policy) != {"schema_version", "permissions"}:
        raise LoopMemoryError("start-authority policy has an invalid schema")
    permissions = policy.get("permissions")
    if (
        policy.get("schema_version") != 2
        or permissions != ["admin", "maintain", "push", "write"]
    ):
        raise LoopMemoryError("start-authority policy has invalid permissions")
    return frozenset(permissions)


def _latest_merge_record(records: list[dict[str, Any]]) -> dict[str, Any]:
    for record in reversed(records):
        if _event_type(record) in {"merge", "cutover"}:
            return record
    raise LoopMemoryError("ledger has no merge record")


def render_state(
    state: dict[str, Any], records: list[dict[str, Any]] | None = None
) -> str:
    """Render the canonical JSON state as a concise human-readable view."""
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
    check_lines = []
    for name in REQUIRED_CHECKS:
        result = checks["required"][name]
        check_lines.append(f"  - `{name}`: `{result['conclusion'] or 'missing'}`")
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
    authority_lines: list[str] = []
    if _event_type(state) in {"start", "cancel"}:
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
            f"- Merge intent: `{source['intent_path']}` at blob `{source['intent_blob_sha']}`",
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
            f"Machine-readable state: `{STATE_PATH.as_posix()}`",
            f"Append-only merge ledger: `{LEDGER_PATH.as_posix()}`",
            "",
        ]
    )


def _latest_by_initiative(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return the latest authenticated merge record for each initiative."""
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        projected = record
        if _event_type(record) in {"start", "cancel"}:
            projected = json.loads(_canonical_json(record))
            projected.update(projected["authority_state"])
        initiative_id = projected["completed_chunk"]["initiative_id"]
        latest[initiative_id] = projected
    return latest


def render_work_queue(records: list[dict[str, Any]]) -> str:
    """Render deterministic signed lifecycle gates for every initiative."""
    lines = [
        "# Generated Workstream Work Queue",
        "",
        "> Signed merge/start/cancel projection. Unsigned chat or worktree starts are not represented.",
        "",
        "| Initiative | Latest completed chunk | Gate | Next chunk | Explicit start |",
        "|---|---|---|---|---|",
    ]
    for initiative_id, record in sorted(_latest_by_initiative(records).items()):
        completed = record["completed_chunk"]
        gate = record["gate"]
        next_chunk = gate["next_chunk_id"] or "none"
        explicit = "yes" if gate["next_requires_explicit_start"] else "no"
        lines.append(
            f"| `{initiative_id}` | `{completed['chunk_id']}` | "
            f"`{gate['status']}` | `{next_chunk}` | {explicit} |"
        )
    latest_merge = _latest_merge_record(records)
    lines.extend(["", f"Latest global merge: `{latest_merge['source']['main_sha']}`", ""])
    return "\n".join(lines)


def render_initiative_state(record: dict[str, Any]) -> str:
    """Render one deterministic signed-lifecycle initiative projection."""
    source = record["source"]
    completed = record["completed_chunk"]
    gate = record["gate"]
    next_chunk = gate["next_chunk_id"] or "none"
    planning_chunk = record["active"]["planning_chunk"] or "none"
    active_chunk = record["active"]["implementation_chunk"] or "none"
    return "\n".join(
        [
            "# Generated Merge/Start Projection",
            "",
            "> Signed merge/start/cancel state. Unsigned chat or worktree starts are not represented.",
            "",
            f"- Initiative: `{completed['initiative_id']}`",
            f"- Latest completed chunk: `{completed['chunk_id']}` - "
            f"{_markdown_text(completed['chunk_title'])}",
            f"- Gate: `{gate['status']}`",
            f"- Active planning chunk: `{planning_chunk}`",
            f"- Active implementation chunk: `{active_chunk}`",
            f"- Next chunk: `{next_chunk}`",
            f"- Separate explicit start required: "
            f"`{str(gate['next_requires_explicit_start']).lower()}`",
            f"- Source PR: [#{source['pr_number']}]({source['pr_url']})",
            f"- Source merge: `{source['main_sha']}`",
            f"- Source event time: `{source['merged_at']}`",
            "",
        ]
    )


def _canonical_json(value: Any, *, pretty: bool = False) -> str:
    """Return deterministic JSON text."""
    if pretty:
        return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _markdown_text(value: str) -> str:
    """Escape bounded metadata before rendering it into Markdown."""
    return (
        value.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _atomic_write(path: Path, content: str) -> None:
    """Write one generated file atomically within its directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _payload_paths(records: list[dict[str, Any]]) -> tuple[Path, ...]:
    """Return the ordered generated payload paths for the authenticated ledger."""
    initiative_paths = tuple(
        INITIATIVE_STATE_ROOT / f"{initiative_id}.md"
        for initiative_id in sorted(_latest_by_initiative(records))
    )
    return tuple(
        sorted(
            (
                STATE_PATH,
                LEDGER_PATH,
                RENDERED_PATH,
                WORK_QUEUE_PATH,
                *initiative_paths,
            ),
            key=lambda path: path.as_posix(),
        )
    )


def _write_projections(state_root: Path, records: list[dict[str, Any]]) -> None:
    """Write every deterministic projection and its ordered digest manifest."""
    latest = _latest_by_initiative(records)
    _atomic_write(state_root / WORK_QUEUE_PATH, render_work_queue(records))
    for initiative_id, record in sorted(latest.items()):
        _atomic_write(
            state_root / INITIATIVE_STATE_ROOT / f"{initiative_id}.md",
            render_initiative_state(record),
        )
    entries = []
    for relative_path in _payload_paths(records):
        content = (state_root / relative_path).read_bytes()
        entries.append(
            {
                "path": relative_path.as_posix(),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    _atomic_write(
        state_root / MANIFEST_PATH,
        _canonical_json(
            {"schema_version": SCHEMA_VERSION, "payloads": entries}, pretty=True
        ),
    )


def _load_json(path: Path) -> dict[str, Any] | None:
    """Load an optional JSON object."""
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LoopMemoryError(f"cannot read generated state at {path}") from exc
    if not isinstance(value, dict):
        raise LoopMemoryError("generated state must be a JSON object")
    return value


def _load_ledger(path: Path) -> list[dict[str, Any]]:
    """Load and validate the optional JSONL merge ledger."""
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise LoopMemoryError("merge ledger entries must be JSON objects")
                records.append(value)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LoopMemoryError(f"cannot read merge ledger at {path}") from exc
    return records


def _ledger_hash(previous_hash: str | None, record: dict[str, Any]) -> str:
    """Return the deterministic hash for one chained ledger entry."""
    payload = f"{previous_hash or ''}\n{_canonical_json(record)}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _ledger_entry(record: dict[str, Any], previous_hash: str | None) -> dict[str, Any]:
    """Wrap a merge record in one append-only hash-chain entry."""
    return {
        "schema_version": SCHEMA_VERSION,
        "previous_entry_hash": previous_hash,
        "record": record,
        "entry_hash": _ledger_hash(previous_hash, record),
    }


def _validate_record(record: dict[str, Any]) -> LoopMetadata:
    """Validate one complete schema-v2 live-state or ledger record."""
    event_type = _event_type(record)
    if event_type in {"start", "cancel"}:
        _validate_event(record.get("event"))
        event = record["event"]
        base = json.loads(_canonical_json(record))
        base.pop("event")
        authority = base.pop("authority_state", None)
        base["updated_at"] = base["source"]["merged_at"]
        _validate_record(base)
        if not isinstance(authority, dict) or set(authority) != {
            "source", "completed_chunk", "active", "gate"
        }:
            raise LoopMemoryError("authority lifecycle state has an invalid schema")
        lifecycle = json.loads(_canonical_json(base))
        lifecycle.update(authority)
        lifecycle["updated_at"] = lifecycle["source"]["merged_at"]
        metadata = parse_loop_metadata(_canonical_json(lifecycle["completed_chunk"]))
        lifecycle["active"] = {"planning_chunk": None, "implementation_chunk": None}
        lifecycle["gate"] = {
            "status": "stopped_after_merge",
            "next_chunk_id": metadata.next_chunk_id,
            "next_chunk_title": metadata.next_chunk_title,
            "next_requires_explicit_start": metadata.next_requires_explicit_start,
        }
        _validate_record(lifecycle)
        if metadata.initiative_id != event["initiative_id"]:
            raise LoopMemoryError("authority lifecycle initiative does not match event")
        selection = event.get("selection")
        if selection is None:
            if metadata.next_chunk_id != event["chunk_id"]:
                raise LoopMemoryError("authority event chunk is not the reviewed successor")
            selected_title = metadata.next_chunk_title
            selected_phase = "implementation"
        else:
            _validate_start_selection(selection, event)
            selected_title = selection["contract_title"]
            selected_phase = selection["phase"]
        if event["main_sha"] != base["source"]["main_sha"]:
            raise LoopMemoryError("authority event main does not match global state")
        if record.get("updated_at") != event["created_at"]:
            raise LoopMemoryError("authority state time does not match event time")
        expected_active = {
            "planning_chunk": (
                event["chunk_id"]
                if event_type == "start" and selected_phase == "planning" else None
            ),
            "implementation_chunk": (
                event["chunk_id"]
                if event_type == "start" and selected_phase == "implementation" else None
            ),
        }
        if authority.get("active") != expected_active:
            raise LoopMemoryError("authority event active state is inconsistent")
        expected_gate = {
            "status": "active" if event_type == "start" else "stopped_after_cancel",
            "next_chunk_id": event["chunk_id"],
            "next_chunk_title": selected_title,
            "next_requires_explicit_start": True,
        }
        if authority.get("gate") != expected_gate:
            raise LoopMemoryError("authority event gate is inconsistent")
        return metadata
    expected_record_keys = {
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
    allowed_record_keys = expected_record_keys | {"legacy_exemptions"}
    planning_record_keys = expected_record_keys | {"planning_intake"}
    planning_legacy_record_keys = planning_record_keys | {"legacy_exemptions"}
    cutover_record_keys = allowed_record_keys | {"event"}
    if frozenset(record) not in {
        frozenset(expected_record_keys),
        frozenset(allowed_record_keys),
        frozenset(planning_record_keys),
        frozenset(planning_legacy_record_keys),
        frozenset(cutover_record_keys),
    } or not _is_current_schema_version(
        record.get("schema_version")
    ):
        raise LoopMemoryError("loop-memory record has an invalid schema")
    exemptions = record.get("legacy_exemptions")
    if exemptions is not None:
        if not isinstance(exemptions, list):
            raise LoopMemoryError("legacy exemptions must be a list")
        identities = set()
        for exemption in exemptions:
            if not isinstance(exemption, dict) or set(exemption) != {
                "initiative_id", "chunk_id", "pr_number"
            }:
                raise LoopMemoryError("legacy exemption has an invalid schema")
            identity = (exemption["initiative_id"], exemption["chunk_id"])
            if (
                not _is_valid_exemption_id(*identity)
                or type(exemption["pr_number"]) is not int
                or exemption["pr_number"] <= 0
                or identity in identities
            ):
                raise LoopMemoryError("legacy exemption is invalid or duplicated")
            identities.add(identity)
    planning_intake = record.get("planning_intake")
    if planning_intake is not None:
        expected_intake_keys = {
            "schema_version",
            "initiative_directory",
            "base_tree_sha",
            "head_tree_sha",
            "first_parent_tree_sha",
            "merge_tree_sha",
            "delta_sha256",
            "changed_paths",
        }
        if (
            not isinstance(planning_intake, dict)
            or set(planning_intake) != expected_intake_keys
            or planning_intake.get("schema_version") != PLANNING_INTAKE_VERSION
        ):
            raise LoopMemoryError("planning intake evidence has an invalid schema")
        directory = planning_intake.get("initiative_directory")
        paths = planning_intake.get("changed_paths")
        if (
            not isinstance(directory, str)
            or not isinstance(paths, list)
            or not paths
            or paths != sorted(set(paths))
            or not all(isinstance(path, str) for path in paths)
        ):
            raise LoopMemoryError("planning intake path evidence is invalid")
        for field in (
            "base_tree_sha", "head_tree_sha", "first_parent_tree_sha", "merge_tree_sha"
        ):
            _validate_sha(planning_intake.get(field))
        if not isinstance(planning_intake.get("delta_sha256"), str) or not SHA256_PATTERN.fullmatch(
            planning_intake["delta_sha256"]
        ):
            raise LoopMemoryError("planning intake delta digest is invalid")
    if event_type == "cutover":
        _validate_cutover_event(
            record.get("event"), exemptions, record.get("source", {}).get("main_sha")
        )
    if record.get("state_branch") != STATE_BRANCH:
        raise LoopMemoryError("loop-memory record has an invalid state branch")

    source = record.get("source")
    expected_source_keys = {
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
    if not isinstance(source, dict) or set(source) != expected_source_keys:
        raise LoopMemoryError("loop-memory source has an invalid schema")
    repository = record.get("repository")
    _validate_repository_and_sha(repository, source.get("main_sha", ""))
    _validate_sha(source.get("first_parent_sha", ""))
    _validate_sha(source.get("head_sha", ""))
    _validate_sha(source.get("intent_blob_sha", ""))
    pr_number = source.get("pr_number")
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number <= 0:
        raise LoopMemoryError("loop-memory source has no positive PR number")
    if source.get("pr_url") != f"https://github.com/{repository}/pull/{pr_number}":
        raise LoopMemoryError("loop-memory source has an invalid PR URL")
    for field, maximum in (
        ("pr_title", 240),
        ("head_ref", 240),
        ("merged_by", 160),
    ):
        _bounded_text(source.get(field), field, maximum=maximum)
    merged_at = source.get("merged_at")
    _parse_timestamp(merged_at, "merged_at")
    if record.get("updated_at") != merged_at:
        raise LoopMemoryError("loop-memory updated_at does not match merged_at")

    completed = record.get("completed_chunk")
    if not isinstance(completed, dict):
        raise LoopMemoryError("completed_chunk must be a JSON object")
    metadata = parse_loop_metadata(_canonical_json(completed))
    if source.get("intent_path") != _intent_path(metadata):
        raise LoopMemoryError("loop-memory intent path does not match completed chunk")
    if planning_intake is not None:
        if (
            metadata.chunk_id != f"{metadata.initiative_id}-PLAN"
            or metadata.next_chunk_id is None
            or not metadata.next_requires_explicit_start
            or planning_intake["initiative_directory"]
            != _initiative_directory_from_path(
                f"{CHUNK_CONTRACT_ROOT}{planning_intake['initiative_directory']}/chunks/x.md",
                metadata.initiative_id,
            )
        ):
            raise LoopMemoryError("planning intake lifecycle identity is invalid")
        if not record.get("checks", {}).get("all_required_passed"):
            raise LoopMemoryError("planning intake required checks did not pass")

    active = record.get("active")
    if active != {"planning_chunk": None, "implementation_chunk": None}:
        raise LoopMemoryError("post-merge active chunk state must be empty")
    gate = record.get("gate")
    expected_gate = {
        "status": "stopped_after_merge",
        "next_chunk_id": metadata.next_chunk_id,
        "next_chunk_title": metadata.next_chunk_title,
        "next_requires_explicit_start": metadata.next_requires_explicit_start,
    }
    if gate != expected_gate:
        raise LoopMemoryError("next gate does not match completed chunk metadata")

    checks = record.get("checks")
    if not isinstance(checks, dict) or set(checks) != {
        "required",
        "all_required_passed",
    }:
        raise LoopMemoryError("loop-memory check evidence has an invalid schema")
    required = checks.get("required")
    if not isinstance(required, dict) or set(required) != set(REQUIRED_CHECKS):
        raise LoopMemoryError("loop-memory required-check evidence is incomplete")
    for name in REQUIRED_CHECKS:
        result = required[name]
        if not isinstance(result, dict) or set(result) != {
            "kind",
            "conclusion",
            "url",
        }:
            raise LoopMemoryError(f"loop-memory check evidence is invalid for {name}")
        if not isinstance(result.get("kind"), str):
            raise LoopMemoryError(f"loop-memory check kind is invalid for {name}")
        if result.get("conclusion") is not None and not isinstance(
            result.get("conclusion"), str
        ):
            raise LoopMemoryError(f"loop-memory check conclusion is invalid for {name}")
        if result.get("url") is not None and not isinstance(result.get("url"), str):
            raise LoopMemoryError(f"loop-memory check URL is invalid for {name}")
    all_passed = all(
        required[name].get("conclusion") == "success" for name in REQUIRED_CHECKS
    )
    if checks.get("all_required_passed") is not all_passed:
        raise LoopMemoryError("loop-memory aggregate check evidence is inconsistent")
    return metadata


def _is_valid_exemption_id(initiative_id: Any, chunk_id: Any) -> bool:
    return (
        isinstance(initiative_id, str)
        and isinstance(chunk_id, str)
        and bool(ID_PATTERN.fullmatch(initiative_id))
        and bool(ID_PATTERN.fullmatch(chunk_id))
        and chunk_id.startswith(f"{initiative_id}-")
    )


def _validate_legacy_exemptions(payload: Any) -> list[dict[str, Any]]:
    """Validate and canonicalize the closed legacy exemption inventory."""
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "exemptions",
    }:
        raise LoopMemoryError("legacy exemption inventory has an invalid schema")
    if payload.get("schema_version") != 1 or not isinstance(payload.get("exemptions"), list):
        raise LoopMemoryError("legacy exemption inventory is unsupported")
    result = json.loads(_canonical_json(payload["exemptions"]))
    for exemption in result:
        if not isinstance(exemption, dict) or set(exemption) != {"initiative_id", "chunk_id", "pr_number"}:
            raise LoopMemoryError("legacy exemption inventory entry is invalid")
        if not _is_valid_exemption_id(exemption["initiative_id"], exemption["chunk_id"]):
            raise LoopMemoryError("legacy exemption inventory identity is invalid")
        if type(exemption["pr_number"]) is not int or exemption["pr_number"] <= 0:
            raise LoopMemoryError("legacy exemption inventory PR is invalid")
    if result != sorted(result, key=lambda item: (item["initiative_id"], item["chunk_id"])):
        raise LoopMemoryError("legacy exemption inventory must be sorted")
    return result


def _validate_recovery_exemptions(payload: Any) -> list[dict[str, Any]]:
    """Validate a chronological ephemeral recovery plan without reordering it."""
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "exemptions"}
        or not isinstance(payload.get("exemptions"), list)
    ):
        raise LoopMemoryError("recovery exemption inventory has an invalid schema")
    version = payload.get("schema_version")
    if version not in {1, 2}:
        raise LoopMemoryError("recovery exemption inventory is unsupported")
    chronological = json.loads(_canonical_json(payload["exemptions"]))
    _validate_legacy_exemptions({
        "schema_version": 1,
        "exemptions": sorted(
            chronological,
            key=lambda item: (
                item.get("initiative_id", "") if isinstance(item, dict) else "",
                item.get("chunk_id", "") if isinstance(item, dict) else "",
            ),
        ),
    })
    identities = [
        (item["initiative_id"], item["chunk_id"], item["pr_number"])
        for item in chronological
    ]
    chunk_identities = [(item[0], item[1]) for item in identities]
    pr_numbers = [item[2] for item in identities]
    if (
        (version == 1 and len(chronological) > 2)
        or (version == 2 and len(chronological) != 3)
        or len(identities) != len(set(identities))
        or len(chunk_identities) != len(set(chunk_identities))
        or len(pr_numbers) != len(set(pr_numbers))
    ):
        raise LoopMemoryError("recovery exemption inventory is not unique and bounded")
    return chronological


def load_legacy_exemptions(repository_root: Path) -> list[dict[str, Any]]:
    """Load the reviewed inventory from the repository working tree."""
    return _validate_legacy_exemptions(
        _load_json(repository_root / LEGACY_EXEMPTIONS_PATH)
    )


def load_legacy_exemptions_at_commit(
    repository_root: Path, commit_sha: str
) -> list[dict[str, Any]]:
    """Load the inventory from its immutable cutover commit."""
    _validate_sha(commit_sha)
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository_root),
            "show",
            f"{commit_sha}:{LEGACY_EXEMPTIONS_PATH.as_posix()}",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0 or len(result.stdout) > 64 * 1024:
        raise LoopMemoryError(
            "cutover commit has no bounded legacy exemption inventory"
        )
    try:
        payload = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LoopMemoryError(
            "cutover commit legacy exemption inventory is invalid JSON"
        ) from exc
    return _validate_legacy_exemptions(payload)


def _load_json_at_commit(
    repository_root: Path, commit_sha: str, path: Path, label: str
) -> Any:
    """Load bounded JSON from an immutable repository commit."""
    _validate_sha(commit_sha)
    result = subprocess.run(
        ["git", "-C", str(repository_root), "show", f"{commit_sha}:{path}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0 or len(result.stdout) > 64 * 1024:
        raise LoopMemoryError(f"target commit has no bounded {label}")
    try:
        return json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LoopMemoryError(f"target commit {label} is invalid JSON") from exc


def _validate_recovery_policy(payload: Any) -> dict[str, Any]:
    """Validate the closed one-use recovery certificate."""
    if not isinstance(payload, dict):
        raise LoopMemoryError("recovery policy has an invalid schema")
    version = payload.get("schema_version")
    if version == 2 and "recovered_merge" in payload:
        raise LoopMemoryError("recovery policy is unsupported")
    expected = {
        1: {"schema_version", "activation", "recovered_merge"},
        2: {"schema_version", "activation", "mode"},
        3: {"schema_version", "activation", "recovered_merges"},
    }.get(version, set())
    if set(payload) != expected:
        raise LoopMemoryError("recovery policy has an invalid schema")
    activation = payload.get("activation")
    if version not in {1, 2, 3} or not isinstance(activation, dict):
        raise LoopMemoryError("recovery policy is unsupported")
    if set(activation) != {"initiative_id", "chunk_id"} or not _is_valid_exemption_id(
        activation.get("initiative_id"), activation.get("chunk_id")
    ):
        raise LoopMemoryError("recovery activation identity is invalid")
    if version == 2:
        if payload.get("mode") != "exact_single_target":
            raise LoopMemoryError("recovery policy mode is unsupported")
        return json.loads(_canonical_json(payload))
    if version == 3:
        recovered_merges = payload.get("recovered_merges")
        if not isinstance(recovered_merges, list) or not 1 <= len(recovered_merges) <= 2:
            raise LoopMemoryError("recovered merge inventory is invalid")
        chunk_identities: set[tuple[str, str]] = set()
        pr_numbers: set[int] = set()
        merge_shas: set[str] = set()
        for recovered in recovered_merges:
            if not isinstance(recovered, dict) or set(recovered) != {
                "initiative_id", "chunk_id", "pr_number", "merge_sha"
            }:
                raise LoopMemoryError("recovered merge identity is invalid")
            if (
                not _is_valid_exemption_id(
                    recovered.get("initiative_id"), recovered.get("chunk_id")
                )
                or type(recovered.get("pr_number")) is not int
                or recovered["pr_number"] <= 0
            ):
                raise LoopMemoryError("recovered merge identity is invalid")
            _validate_sha(recovered.get("merge_sha"))
            chunk_identity = (recovered["initiative_id"], recovered["chunk_id"])
            if (
                chunk_identity in chunk_identities
                or recovered["pr_number"] in pr_numbers
                or recovered["merge_sha"] in merge_shas
            ):
                raise LoopMemoryError("recovered merge inventory is not unique")
            if (
                recovered["initiative_id"] == activation["initiative_id"]
                and recovered["chunk_id"] == activation["chunk_id"]
            ):
                raise LoopMemoryError("recovery activation collides with recovered merge")
            chunk_identities.add(chunk_identity)
            pr_numbers.add(recovered["pr_number"])
            merge_shas.add(recovered["merge_sha"])
        return json.loads(_canonical_json(payload))
    recovered = payload.get("recovered_merge")
    if not isinstance(recovered, dict) or set(recovered) != {
        "initiative_id", "chunk_id", "pr_number", "merge_sha"
    }:
        raise LoopMemoryError("recovered merge identity is invalid")
    if not _is_valid_exemption_id(
        recovered.get("initiative_id"), recovered.get("chunk_id")
    ) or type(recovered.get("pr_number")) is not int or recovered["pr_number"] <= 0:
        raise LoopMemoryError("recovered merge identity is invalid")
    _validate_sha(recovered.get("merge_sha"))
    return json.loads(_canonical_json(payload))


def _record_exemption(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "initiative_id": record["completed_chunk"]["initiative_id"],
        "chunk_id": record["completed_chunk"]["chunk_id"],
        "pr_number": record["source"]["pr_number"],
    }


def prepare_recovery_exemptions(
    client: GitHubClient,
    repository: str,
    *,
    repository_root: Path,
    state_root: Path,
    target_sha: str,
    planned_shas: list[str],
) -> list[dict[str, Any]]:
    """Prepare exact exemptions before sequential recovery reconciliation."""
    _validate_repository_and_sha(repository, target_sha)
    state = _load_json(state_root / STATE_PATH)
    if not isinstance(state, dict):
        raise LoopMemoryError("recovery preparation requires canonical state")
    if not planned_shas and state.get("source", {}).get("main_sha") == target_sha:
        return []
    policy = _validate_recovery_policy(
        _load_json_at_commit(
            repository_root, target_sha, RECOVERY_POLICY_PATH, "recovery policy"
        )
    )
    target_record = collect_merge_record(client, repository, target_sha)
    activation = policy["activation"]
    target_identity = _record_exemption(target_record)
    if (
        target_identity["initiative_id"] != activation["initiative_id"]
        or target_identity["chunk_id"] != activation["chunk_id"]
    ):
        return []
    if policy["schema_version"] == 2:
        _validate_protected_actions_checks(
            client, repository, target_record["source"]["head_sha"]
        )
        if not target_record.get("checks", {}).get("all_required_passed"):
            raise LoopMemoryError("single-target recovery required checks did not pass")
        signed_main = (
            state.get("event", {}).get("main_sha")
            if _event_type(state) in {"start", "cancel"}
            else state.get("source", {}).get("main_sha")
        )
        if planned_shas != [target_sha]:
            raise LoopMemoryError("single-target recovery plan is not exact")
        if target_record.get("source", {}).get("first_parent_sha") != signed_main:
            raise LoopMemoryError("single-target recovery is not the signed first parent")
        exemption = target_identity
        existing = state.get("legacy_exemptions", [])
        if not isinstance(existing, list) or exemption in existing:
            raise LoopMemoryError("recovery exemption collides with signed state")
        return [exemption]
    if policy["schema_version"] == 3:
        recovered_policies = policy["recovered_merges"]
        expected_shas = [item["merge_sha"] for item in recovered_policies] + [target_sha]
        if planned_shas != expected_shas:
            raise LoopMemoryError("recovery plan is not the exact ordered sequence")
        recovered_records = [
            collect_merge_record(client, repository, item["merge_sha"])
            for item in recovered_policies
        ]
        for recovered_policy, recovered_record in zip(
            recovered_policies, recovered_records, strict=True
        ):
            if _record_exemption(recovered_record) != {
                "initiative_id": recovered_policy["initiative_id"],
                "chunk_id": recovered_policy["chunk_id"],
                "pr_number": recovered_policy["pr_number"],
            }:
                raise LoopMemoryError("recovered merge does not match its certificate")
        signed_main = (
            state.get("event", {}).get("main_sha")
            if _event_type(state) in {"start", "cancel"}
            else state.get("source", {}).get("main_sha")
        )
        records = [*recovered_records, target_record]
        expected_parent = signed_main
        for merge_sha, record in zip(planned_shas, records, strict=True):
            source = record.get("source", {})
            if (
                source.get("main_sha") != merge_sha
                or source.get("first_parent_sha") != expected_parent
            ):
                raise LoopMemoryError("recovery plan is not first-parent adjacent")
            expected_parent = merge_sha
            _validate_protected_actions_checks(
                client, repository, source.get("head_sha")
            )
            if not record.get("checks", {}).get("all_required_passed"):
                raise LoopMemoryError("recovery required checks did not pass")
        exemptions = [_record_exemption(record) for record in records]
        existing = state.get("legacy_exemptions", [])
        if not isinstance(existing, list) or any(item in existing for item in exemptions):
            raise LoopMemoryError("recovery exemption collides with signed state")
        return exemptions
    recovered = policy["recovered_merge"]
    if planned_shas != [recovered["merge_sha"], target_sha]:
        raise LoopMemoryError("recovery plan is not the exact two-merge sequence")
    recovered_record = collect_merge_record(client, repository, recovered["merge_sha"])
    if _record_exemption(recovered_record) != {
        "initiative_id": recovered["initiative_id"],
        "chunk_id": recovered["chunk_id"],
        "pr_number": recovered["pr_number"],
    }:
        raise LoopMemoryError("recovered merge does not match its certificate")
    _validate_protected_actions_checks(
        client, repository, target_record["source"]["head_sha"]
    )
    if (
        not recovered_record.get("checks", {}).get("all_required_passed")
        or not target_record.get("checks", {}).get("all_required_passed")
    ):
        raise LoopMemoryError("two-merge recovery required checks did not pass")
    exemptions = [_record_exemption(recovered_record), target_identity]
    existing = state.get("legacy_exemptions", [])
    if not isinstance(existing, list) or any(item in existing for item in exemptions):
        raise LoopMemoryError("recovery exemption collides with signed state")
    return exemptions


def assert_recovery_consumed(
    state_root: Path, target_sha: str, exemptions: list[dict[str, Any]]
) -> None:
    """Require exact target state with no surviving recovery identity."""
    _validate_sha(target_sha)
    state = _load_json(state_root / STATE_PATH)
    if not isinstance(state, dict) or state.get("source", {}).get("main_sha") != target_sha:
        raise LoopMemoryError("recovery did not reach the exact target")
    remaining = state.get("legacy_exemptions", [])
    if not isinstance(remaining, list) or any(item in remaining for item in exemptions):
        raise LoopMemoryError("recovery exemption was not fully consumed")
    records = _validate_ledger_entries(_load_ledger(state_root / LEDGER_PATH))
    if any(
        exemption in record.get("legacy_exemptions", [])
        for record in records
        for exemption in exemptions
    ):
        raise LoopMemoryError("recovery exemption leaked into signed history")


def _validate_ledger_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate the full ledger hash and first-parent chains."""
    records: list[dict[str, Any]] = []
    previous_hash: str | None = None
    previous_main_sha: str | None = None
    expected_keys = {
        "schema_version",
        "previous_entry_hash",
        "record",
        "entry_hash",
    }
    for entry in entries:
        if set(entry) != expected_keys or not _is_current_schema_version(
            entry.get("schema_version")
        ):
            raise LoopMemoryError("merge ledger entry has an invalid schema")
        record = entry.get("record")
        if not isinstance(record, dict):
            raise LoopMemoryError("merge ledger entry record must be a JSON object")
        _validate_record(record)
        _validate_authority_transition(record, records)
        if entry.get("previous_entry_hash") != previous_hash:
            raise LoopMemoryError("merge ledger previous hash chain is invalid")
        expected_hash = _ledger_hash(previous_hash, record)
        if entry.get("entry_hash") != expected_hash:
            raise LoopMemoryError("merge ledger entry hash is invalid")
        source = record.get("source", {})
        if (
            _event_type(record) in {"merge", "cutover"}
            and
            previous_main_sha is not None
            and source.get("first_parent_sha") != previous_main_sha
        ):
            raise LoopMemoryError("merge ledger first-parent chain is invalid")
        main_sha = source.get("main_sha")
        if not isinstance(main_sha, str) or not SHA_PATTERN.fullmatch(main_sha):
            raise LoopMemoryError("merge ledger record has no canonical main SHA")
        records.append(record)
        previous_hash = expected_hash
        previous_main_sha = (
            record["event"]["main_sha"]
            if _event_type(record) in {"start", "cancel"}
            else main_sha
        )
    return records


def _validate_authority_transition(
    record: dict[str, Any], prior_records: list[dict[str, Any]]
) -> None:
    """Bind an authority event to the exact preceding initiative lifecycle."""
    event_type = _event_type(record)
    if event_type not in {"start", "cancel"}:
        return
    event = record["event"]
    authority = record["authority_state"]
    if authority["completed_chunk"]["initiative_id"] != event["initiative_id"]:
        raise LoopMemoryError("authority lifecycle initiative does not match event")
    basis = _latest_by_initiative(prior_records).get(event["initiative_id"])
    if basis is None:
        raise LoopMemoryError("authority event has no preceding initiative basis")
    if authority["source"] != basis["source"] or authority["completed_chunk"] != basis["completed_chunk"]:
        raise LoopMemoryError("authority lifecycle does not copy its signed basis")
    if event_type == "start":
        if any(
            _event_type(item) in {"merge", "cutover"}
            and item["completed_chunk"]["initiative_id"] == event["initiative_id"]
            and item["completed_chunk"]["chunk_id"] == event["chunk_id"]
            for item in prior_records
        ):
            raise LoopMemoryError("authority start selects an already-completed chunk")
        selection = event.get("selection")
        if basis["active"]["implementation_chunk"] is not None or basis["active"]["planning_chunk"] is not None:
            raise LoopMemoryError("authority start follows an already-active basis")
        if selection is None and basis["gate"]["next_chunk_id"] != event["chunk_id"]:
            raise LoopMemoryError("authority start is not the basis successor")
        if selection is not None:
            _validate_start_selection(selection, event)
            expected_mode = (
                "declared_successor"
                if basis["gate"]["next_chunk_id"] == event["chunk_id"]
                else "writer_directed"
            )
            if selection["mode"] != expected_mode:
                raise LoopMemoryError("start selection mode does not match signed basis")
    elif basis["active"]["implementation_chunk"] != event["chunk_id"]:
        if basis["active"]["planning_chunk"] != event["chunk_id"]:
            raise LoopMemoryError("authority cancel does not match the basis active chunk")
    if event_type == "cancel" and event.get("selection") != basis.get("event", {}).get("selection"):
        raise LoopMemoryError("authority cancel selection does not match active start")


def apply_authority_event(
    state_root: Path,
    event: dict[str, Any],
    *,
    repository_root: Path,
    branch_root: Path | None = None,
) -> bool:
    """Apply one authenticated start/cancel event to canonical state."""
    event_type = _validate_event(event)
    state = _load_json(state_root / STATE_PATH)
    if state is None:
        raise LoopMemoryError("authority event requires existing signed state")
    ledger = _load_ledger(state_root / LEDGER_PATH)
    records = _validate_ledger_entries(ledger)
    if not records or _canonical_json(records[-1]) != _canonical_json(state):
        raise LoopMemoryError("canonical state does not match the ledger tail")
    duplicate = [
        record
        for record in records
        if isinstance(record.get("event"), dict)
        and record["event"].get("event_id") == event["event_id"]
    ]
    if duplicate:
        if len(duplicate) == 1 and duplicate[0].get("event") == event:
            return False
        raise LoopMemoryError("authority event ID already exists with different bytes")
    if any(
        isinstance(record.get("event"), dict)
        and record["event"].get("run_id") == event["run_id"]
        for record in records
    ):
        raise LoopMemoryError("workflow run ID already recorded")
    current_main_sha = (
        state["event"]["main_sha"]
        if _event_type(state) in {"start", "cancel"}
        else state["source"]["main_sha"]
    )
    if event["main_sha"] != current_main_sha:
        raise LoopMemoryError("authority event main is stale")
    actual_tip = _state_branch_tip(branch_root or state_root)
    if event["prior_state_tip"] != actual_tip:
        raise LoopMemoryError("authority event prior state tip is stale")
    latest = _latest_by_initiative(records)
    basis = latest.get(event["initiative_id"])
    if basis is None:
        raise LoopMemoryError("authority event initiative has no signed gate")
    if event_type == "start":
        if any(
            _event_type(item) in {"merge", "cutover"}
            and item["completed_chunk"]["initiative_id"] == event["initiative_id"]
            and item["completed_chunk"]["chunk_id"] == event["chunk_id"]
            for item in records
        ):
            raise LoopMemoryError("cannot start an already-completed chunk")
        if basis["active"]["implementation_chunk"] is not None or basis["active"]["planning_chunk"] is not None:
            raise LoopMemoryError("initiative already has an active chunk")
        selection = event.get("selection")
        if selection is None:
            if basis["gate"]["next_chunk_id"] != event["chunk_id"]:
                raise LoopMemoryError("start chunk is not the reviewed successor")
            selected_title = basis["gate"]["next_chunk_title"]
            selected_phase = "implementation"
        else:
            expected = resolve_start_selection(
                repository_root,
                initiative_id=event["initiative_id"],
                chunk_id=event["chunk_id"],
                phase=selection["phase"],
                main_sha=event["main_sha"],
                declared_successor=(basis["gate"]["next_chunk_id"] == event["chunk_id"]),
            )
            if selection != expected:
                raise LoopMemoryError("signed start selection does not match current main")
            selected_title = selection["contract_title"]
            selected_phase = selection["phase"]
    else:
        if event.get("selection") != basis.get("event", {}).get("selection"):
            raise LoopMemoryError("cancel selection does not match active start")
        if event.get("selection") is not None:
            selected_title = event["selection"]["contract_title"]
            selected_phase = event["selection"]["phase"]
        else:
            selected_title = basis["gate"]["next_chunk_title"]
            selected_phase = "implementation"
        if event["chunk_id"] not in basis["active"].values():
            raise LoopMemoryError("cancel chunk is not the active chunk")
    updated = json.loads(_canonical_json(_latest_merge_record(records)))
    if "legacy_exemptions" in state:
        updated["legacy_exemptions"] = json.loads(
            _canonical_json(state["legacy_exemptions"])
        )
    updated["updated_at"] = event["created_at"]
    updated["event"] = event
    updated["authority_state"] = {
        "source": basis["source"],
        "completed_chunk": basis["completed_chunk"],
        "active": {
            "planning_chunk": event["chunk_id"] if event_type == "start" and selected_phase == "planning" else None,
            "implementation_chunk": event["chunk_id"] if event_type == "start" and selected_phase == "implementation" else None,
        },
        "gate": {
            "status": "active" if event_type == "start" else "stopped_after_cancel",
            "next_chunk_id": event["chunk_id"],
            "next_chunk_title": selected_title,
            "next_requires_explicit_start": True,
        },
    }
    _validate_record(updated)
    previous_hash = ledger[-1]["entry_hash"]
    ledger.append(_ledger_entry(updated, previous_hash))
    _atomic_write(state_root / STATE_PATH, _canonical_json(updated, pretty=True))
    _atomic_write(state_root / RENDERED_PATH, render_state(updated, records + [updated]))
    _atomic_write(
        state_root / LEDGER_PATH,
        "".join(f"{_canonical_json(entry)}\n" for entry in ledger),
    )
    _write_projections(state_root, records + [updated])
    return True


def _state_branch_tip(branch_root: Path) -> str:
    """Resolve the authenticated state branch tip used by an authority event."""
    result = subprocess.run(
        ["git", "-C", str(branch_root), "rev-parse", "HEAD"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    tip = result.stdout.strip()
    if result.returncode != 0 or not SHA_PATTERN.fullmatch(tip):
        raise LoopMemoryError("cannot resolve authenticated state branch tip")
    return tip


def apply_merge_record(
    state_root: Path,
    record: dict[str, Any],
    recovery_exemptions: list[dict[str, Any]] | None = None,
) -> bool:
    """Apply one monotonic, idempotent merge record to a state directory."""
    _validate_record(record)
    state_path = state_root / STATE_PATH
    ledger_path = state_root / LEDGER_PATH
    rendered_path = state_root / RENDERED_PATH
    existing = _load_json(state_path)
    ledger = _load_ledger(ledger_path)
    records = _validate_ledger_entries(ledger)
    merge_sha = record["source"]["main_sha"]

    if existing is not None and (
        not records or _canonical_json(records[-1]) != _canonical_json(existing)
    ):
        raise LoopMemoryError("canonical state does not match the merge ledger tail")

    duplicate = next(
        (
            entry
            for entry in records
            if entry.get("source", {}).get("main_sha") == merge_sha
        ),
        None,
    )
    if duplicate is not None:
        same_identity = (
            duplicate.get("source") == record.get("source")
            and duplicate.get("completed_chunk") == record.get("completed_chunk")
            and duplicate.get("gate") == record.get("gate")
        )
        if not same_identity:
            raise LoopMemoryError("merge SHA already exists with different state")
        return False

    if existing is not None:
        initiative_id = record["completed_chunk"]["initiative_id"]
        initiative_state = _latest_by_initiative(records).get(initiative_id)
        planning_intake = record.get("planning_intake")
        if planning_intake is not None and initiative_state is not None:
            raise LoopMemoryError("planning intake initiative already exists in signed history")
        active_values = initiative_state.get("active", {}) if initiative_state else {}
        active_chunks = [
            value
            for value in (
                active_values.get("planning_chunk"),
                active_values.get("implementation_chunk"),
            )
            if value is not None
        ]
        if len(active_chunks) > 1:
            raise LoopMemoryError("initiative has multiple active chunks")
        active_chunk = active_chunks[0] if active_chunks else None
        remaining_exemptions = existing.get("legacy_exemptions")
        if recovery_exemptions:
            recovery_match = [
                item for item in recovery_exemptions
                if item == _record_exemption(record)
            ]
            if len(recovery_match) != 1:
                raise LoopMemoryError("merge has no unique exact recovery exemption")
            current = remaining_exemptions or []
            if any(item in current for item in recovery_exemptions):
                raise LoopMemoryError("recovery exemption collides with signed state")
            remaining_exemptions = json.loads(
                _canonical_json(current + recovery_match)
            )
        if remaining_exemptions is not None:
            remaining_exemptions = json.loads(_canonical_json(remaining_exemptions))
            match = next(
                (
                    exemption
                    for exemption in remaining_exemptions
                    if exemption["initiative_id"] == initiative_id
                    and exemption["chunk_id"] == record["completed_chunk"]["chunk_id"]
                    and exemption["pr_number"] == record["source"]["pr_number"]
                ),
                None,
            )
            if active_chunk is None:
                if match is None and planning_intake is None:
                    raise LoopMemoryError(
                        "post-cutover merge has no signed start or exemption"
                    )
            if match is not None:
                remaining_exemptions.remove(match)
            record["legacy_exemptions"] = remaining_exemptions
            _validate_record(record)
        if active_chunk is not None and record["completed_chunk"]["chunk_id"] != active_chunk:
            raise LoopMemoryError("merged chunk does not match active signed chunk")
        current_main_sha = (
            existing["event"]["main_sha"]
            if _event_type(existing) in {"start", "cancel"}
            else existing["source"]["main_sha"]
        )
        if record.get("source", {}).get("first_parent_sha") != current_main_sha:
            raise LoopMemoryError(
                "merge record is not the direct first-parent successor"
            )

    previous_hash = ledger[-1]["entry_hash"] if ledger else None
    ledger.append(_ledger_entry(record, previous_hash))
    _atomic_write(state_path, _canonical_json(record, pretty=True))
    _atomic_write(rendered_path, render_state(record, records + [record]))
    _atomic_write(
        ledger_path, "".join(f"{_canonical_json(entry)}\n" for entry in ledger)
    )
    _write_projections(state_root, records + [record])
    return True


def _load_validated_semantic_state(
    state_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load validated semantic state with a complete ledger and exact tail."""
    state = _load_json(state_root / STATE_PATH)
    if state is None:
        raise LoopMemoryError("generated state file is missing")
    _validate_record(state)
    ledger = _load_ledger(state_root / LEDGER_PATH)
    records = _validate_ledger_entries(ledger)
    if not records or _canonical_json(records[-1]) != _canonical_json(state):
        raise LoopMemoryError("merge ledger tail does not match canonical state")
    return state, records


def _validate_signed_payload_structure(
    state_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate signed semantic state and its closed manifest without rendering."""
    state, records = _load_validated_semantic_state(state_root)
    manifest = _load_json(state_root / MANIFEST_PATH)
    expected_entries = []
    for relative_path in _payload_paths(records):
        path = state_root / relative_path
        if not path.is_file() or path.is_symlink():
            raise LoopMemoryError("generated manifest payload is missing or unsafe")
        expected_entries.append(
            {
                "path": relative_path.as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    expected_manifest = {"schema_version": SCHEMA_VERSION, "payloads": expected_entries}
    if manifest != expected_manifest:
        raise LoopMemoryError("generated manifest does not match payloads")
    expected_tree = {item["path"] for item in expected_entries} | {
        MANIFEST_PATH.as_posix(),
    }
    signature_path = state_root / SIGNATURE_PATH
    if signature_path.exists() or signature_path.is_symlink():
        expected_tree.add(SIGNATURE_PATH.as_posix())
    agent_loop = state_root / ".agent-loop"
    actual_tree = {
        path.relative_to(state_root).as_posix()
        for path in agent_loop.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual_tree != expected_tree:
        raise LoopMemoryError("generated state tree does not match closed manifest")
    return state, records


def validate_generated_state(state_root: Path) -> None:
    """Validate semantic state, current rendered projections, and manifest."""
    state, records = _load_validated_semantic_state(state_root)
    rendered_path = state_root / RENDERED_PATH
    if not rendered_path.exists() or rendered_path.read_text(
        encoding="utf-8"
    ) != render_state(state, records):
        raise LoopMemoryError("rendered loop state does not match canonical JSON")
    if not (state_root / WORK_QUEUE_PATH).is_file() or (
        state_root / WORK_QUEUE_PATH
    ).read_text(encoding="utf-8") != render_work_queue(records):
        raise LoopMemoryError("generated work queue does not match merge ledger")
    latest = _latest_by_initiative(records)
    for initiative_id, record in latest.items():
        path = state_root / INITIATIVE_STATE_ROOT / f"{initiative_id}.md"
        if not path.is_file() or path.read_text(
            encoding="utf-8"
        ) != render_initiative_state(record):
            raise LoopMemoryError(
                "generated initiative state does not match merge ledger"
            )
    _validate_signed_payload_structure(state_root)


def _signature_payload(state_root: Path) -> bytes:
    """Return an unambiguous payload covering every canonical generated file."""
    payload = bytearray(b"workstream-loop-memory-signature-v2-projections\0")
    manifest_bytes = (state_root / MANIFEST_PATH).read_bytes()
    payload.extend(len(manifest_bytes).to_bytes(8, "big"))
    payload.extend(manifest_bytes)
    manifest = _load_json(state_root / MANIFEST_PATH)
    if manifest is None:
        raise LoopMemoryError("generated manifest is missing")
    for item in manifest["payloads"]:
        relative_path = Path(item["path"])
        path_bytes = relative_path.as_posix().encode("ascii")
        content = (state_root / relative_path).read_bytes()
        payload.extend(len(path_bytes).to_bytes(4, "big"))
        payload.extend(path_bytes)
        payload.extend(len(content).to_bytes(8, "big"))
        payload.extend(content)
    return bytes(payload)


def _legacy_signature_payload(state_root: Path) -> bytes:
    """Return the pre-04A schema-v2 signature payload for one-time migration."""
    payload = bytearray(b"workstream-loop-memory-signature-v2\0")
    for relative_path in (STATE_PATH, RENDERED_PATH, LEDGER_PATH):
        path_bytes = relative_path.as_posix().encode("ascii")
        content = (state_root / relative_path).read_bytes()
        payload.extend(len(path_bytes).to_bytes(4, "big"))
        payload.extend(path_bytes)
        payload.extend(len(content).to_bytes(8, "big"))
        payload.extend(content)
    return bytes(payload)


def sign_generated_state(state_root: Path, private_key: Path) -> None:
    """Sign validated generated state with the Actions-only Ed25519 key."""
    validate_generated_state(state_root)
    with tempfile.NamedTemporaryFile() as payload_file:
        payload_file.write(_signature_payload(state_root))
        payload_file.flush()
        result = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                str(private_key),
                "-in",
                payload_file.name,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    if result.returncode != 0 or len(result.stdout) != 64:
        raise LoopMemoryError("cannot sign generated loop memory")
    _atomic_write(
        state_root / SIGNATURE_PATH,
        base64.b64encode(result.stdout).decode("ascii") + "\n",
    )


def _verify_generated_state_signature_bytes(
    state_root: Path,
    public_key: Path,
    expected_main_sha: str | None = None,
) -> None:
    """Verify the signature over already validated generated bytes."""
    legacy = not (state_root / MANIFEST_PATH).exists()
    try:
        encoded_signature = (state_root / SIGNATURE_PATH).read_text(encoding="ascii")
        signature = base64.b64decode(encoded_signature.strip(), validate=True)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise LoopMemoryError("generated loop-memory signature is unreadable") from exc
    if len(signature) != 64:
        raise LoopMemoryError("generated loop-memory signature has an invalid length")
    with (
        tempfile.NamedTemporaryFile() as signature_file,
        tempfile.NamedTemporaryFile() as payload_file,
    ):
        signature_file.write(signature)
        signature_file.flush()
        payload_file.write(
            _legacy_signature_payload(state_root)
            if legacy
            else _signature_payload(state_root)
        )
        payload_file.flush()
        result = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-rawin",
                "-pubin",
                "-inkey",
                str(public_key),
                "-sigfile",
                signature_file.name,
                "-in",
                payload_file.name,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    if result.returncode != 0:
        raise LoopMemoryError("generated loop-memory signature verification failed")
    if expected_main_sha is not None:
        _validate_sha(expected_main_sha)
        state = _load_json(state_root / STATE_PATH)
        current_main_sha = (
            state.get("event", {}).get("main_sha")
            if isinstance(state, dict) and isinstance(state.get("event"), dict)
            else state.get("source", {}).get("main_sha") if isinstance(state, dict) else None
        )
        if (
            state is None
            or current_main_sha != expected_main_sha
        ):
            raise LoopMemoryError(
                "generated loop memory is not current for protected main"
            )


def verify_generated_state_signature(
    state_root: Path,
    public_key: Path,
    expected_main_sha: str | None = None,
) -> None:
    """Verify current canonical projections, signature, and main freshness."""
    legacy = not (state_root / MANIFEST_PATH).exists()
    if legacy:
        state = _load_json(state_root / STATE_PATH)
        ledger = _load_ledger(state_root / LEDGER_PATH)
        records = _validate_ledger_entries(ledger)
        if (
            state is None
            or not records
            or _canonical_json(records[-1]) != _canonical_json(state)
        ):
            raise LoopMemoryError("legacy generated state is inconsistent")
        if (state_root / RENDERED_PATH).read_text(encoding="utf-8") != render_state(
            state, records
        ):
            raise LoopMemoryError("legacy rendered state is inconsistent")
    else:
        validate_generated_state(state_root)
    _verify_generated_state_signature_bytes(
        state_root, public_key, expected_main_sha
    )


def verify_generated_state_rebuild_source(
    state_root: Path, public_key: Path
) -> None:
    """Authenticate signed manifest bytes while allowing renderer-version drift."""
    if not (state_root / MANIFEST_PATH).exists():
        verify_generated_state_signature(state_root, public_key)
        return
    _validate_signed_payload_structure(state_root)
    _verify_generated_state_signature_bytes(state_root, public_key)


def _remove_path(path: Path) -> None:
    """Remove one fixed generated path without following symbolic links."""
    if path.is_symlink() or not path.is_dir():
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path)


def prepare_generated_state_root(state_root: Path, public_key: Path) -> bool:
    """Authenticate existing state or clear fixed paths for bootstrap rebuild."""
    agent_loop = state_root / STATE_PATH.parent
    if agent_loop.is_symlink() or (agent_loop.exists() and not agent_loop.is_dir()):
        _remove_path(agent_loop)
        agent_loop.mkdir(parents=True)
        return False
    agent_loop.mkdir(parents=True, exist_ok=True)

    generated_paths = tuple(
        state_root / path
        for path in (
            STATE_PATH,
            RENDERED_PATH,
            LEDGER_PATH,
            WORK_QUEUE_PATH,
            MANIFEST_PATH,
            INITIATIVE_STATE_ROOT,
            SIGNATURE_PATH,
        )
    )
    if not any(path.exists() or path.is_symlink() for path in generated_paths):
        return False
    try:
        verify_generated_state_rebuild_source(state_root, public_key)
    except (
        LoopMemoryError,
        OSError,
        UnicodeError,
        AttributeError,
        TypeError,
        KeyError,
        IndexError,
        ValueError,
        RecursionError,
    ):
        for path in generated_paths:
            _remove_path(path)
        return False
    return True


def prepare_generated_output(
    source_root: Path, output_root: Path, public_key: Path
) -> bool:
    """Authenticate prior state and copy only canonical inputs to a fresh root."""
    if output_root.exists():
        raise LoopMemoryError("generated output root must not already exist")
    output_root.mkdir(parents=True)
    authenticated = prepare_generated_state_root(source_root, public_key)
    if not authenticated:
        return False
    source_paths = [STATE_PATH, LEDGER_PATH]
    for relative_path in source_paths:
        source = source_root / relative_path
        if source.is_symlink() or not source.is_file():
            raise LoopMemoryError("authenticated canonical input is unsafe")
        target = output_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    records = _validate_ledger_entries(_load_ledger(output_root / LEDGER_PATH))
    if not records:
        raise LoopMemoryError("authenticated canonical input has no ledger records")
    _atomic_write(
        output_root / RENDERED_PATH,
        render_state(records[-1], records),
    )
    _write_projections(output_root, records)
    validate_generated_state(output_root)
    return True


def validate_generated_git_tree(
    repository_root: Path, tree_sha: str, output_root: Path
) -> None:
    """Verify one staged Git tree exactly preserves signed generated bytes."""
    _validate_sha(tree_sha)
    validate_generated_state(output_root)
    result = subprocess.run(
        ["git", "-C", str(repository_root), "ls-tree", "-r", "-z", tree_sha],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise LoopMemoryError("cannot inspect generated Git tree")
    entries: dict[str, tuple[str, str]] = {}
    for raw_entry in result.stdout.split(b"\0"):
        if not raw_entry:
            continue
        try:
            metadata, raw_path = raw_entry.split(b"\t", 1)
            mode, object_type, object_sha = metadata.decode("ascii").split()
            relative_path = raw_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise LoopMemoryError("generated Git tree entry is malformed") from exc
        if mode != "100644" or object_type != "blob":
            raise LoopMemoryError("generated Git tree contains an unsafe file mode")
        entries[relative_path] = (object_sha, mode)
    expected_paths = {
        path.relative_to(output_root).as_posix()
        for path in (output_root / ".agent-loop").rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if set(entries) != expected_paths:
        raise LoopMemoryError(
            "generated Git tree path set does not match signed output"
        )
    for relative_path, (object_sha, _mode) in entries.items():
        blob = subprocess.run(
            ["git", "-C", str(repository_root), "cat-file", "blob", object_sha],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if (
            blob.returncode != 0
            or blob.stdout != (output_root / relative_path).read_bytes()
        ):
            raise LoopMemoryError("generated Git tree blob differs from signed output")


def _assert_state_branch(state_root: Path) -> None:
    """Refuse to write generated memory outside its dedicated branch."""
    result = subprocess.run(
        ["git", "-C", str(state_root), "branch", "--show-current"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0 or result.stdout.strip() != STATE_BRANCH:
        raise LoopMemoryError(f"state root must be checked out on {STATE_BRANCH}")


def publish_generated_state(
    branch_root: Path,
    output_root: Path,
    *,
    expected_prior_tip: str,
    message: str,
) -> str | None:
    """Build and fast-forward publish one exact signed tree from the state tip."""
    _assert_state_branch(branch_root)
    if expected_prior_tip:
        _validate_sha(expected_prior_tip)
        if _state_branch_tip(branch_root) != expected_prior_tip:
            raise LoopMemoryError("state branch moved before publication")
    _bounded_text(message, "publication message", maximum=240)
    validate_generated_state(output_root)
    descriptor, index_name = tempfile.mkstemp(prefix="loop-memory-index-")
    os.close(descriptor)
    index_path = Path(index_name)
    try:
        env = {**os.environ, "GIT_INDEX_FILE": str(index_path)}
        subprocess.run(["git", "-C", str(branch_root), "read-tree", "--empty"], env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", f"--git-dir={branch_root / '.git'}", f"--work-tree={output_root}", "add", "-f", "--", ".agent-loop"], env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        tree = subprocess.run(["git", "-C", str(branch_root), "write-tree"], env=env, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()
        validate_generated_git_tree(branch_root, tree, output_root)
        if expected_prior_tip:
            parent_tree = subprocess.run(["git", "-C", str(branch_root), "rev-parse", "HEAD^{tree}"], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()
            if tree == parent_tree:
                return None
        commit_args = ["git", "-C", str(branch_root), "commit-tree", tree]
        if expected_prior_tip:
            commit_args.extend(["-p", expected_prior_tip])
        commit = subprocess.run(commit_args, input=f"{message}\n", check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()
        subprocess.run(["git", "-C", str(branch_root), "push", "origin", f"{commit}:refs/heads/{STATE_BRANCH}"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return commit
    except subprocess.CalledProcessError as exc:
        raise LoopMemoryError("cannot publish generated state by fast-forward") from exc
    finally:
        index_path.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_intent = subparsers.add_parser("validate-merge-intent")
    validate_intent.add_argument("--repository-root", type=Path, default=Path("."))
    validate_intent.add_argument("--base-ref", required=True)

    plan_commits = subparsers.add_parser("plan-commits")
    plan_commits.add_argument("--repository-root", type=Path, default=Path("."))
    plan_commits.add_argument("--target-sha", required=True)
    plan_commits.add_argument("--current-sha")

    resolve_target = subparsers.add_parser("resolve-target")
    resolve_target.add_argument("--repository-root", type=Path, default=Path("."))
    resolve_target.add_argument(
        "--event-name", choices=("push", "repository_dispatch"), required=True
    )
    resolve_target.add_argument("--event-sha", required=True)
    resolve_target.add_argument("--current-main-sha", required=True)

    update = subparsers.add_parser("update")
    update.add_argument("--repository", required=True)
    update.add_argument("--repository-root", type=Path, default=Path("."))
    update.add_argument("--merge-sha", required=True)
    update.add_argument("--state-root", type=Path, required=True)
    update.add_argument("--branch-root", type=Path)
    update.add_argument("--token-env", default="GITHUB_TOKEN")
    update.add_argument("--api-url", default="https://api.github.com")
    update.add_argument(
        "--cutover-chunk-id",
        help="Explicitly apply the reviewed legacy exemption inventory at this chunk",
    )
    update.add_argument("--recovery-file", type=Path)

    prepare_recovery = subparsers.add_parser("prepare-recovery")
    prepare_recovery.add_argument("--repository", required=True)
    prepare_recovery.add_argument("--repository-root", type=Path, default=Path("."))
    prepare_recovery.add_argument("--state-root", type=Path, required=True)
    prepare_recovery.add_argument("--target-sha", required=True)
    prepare_recovery.add_argument("--plan-file", type=Path, required=True)
    prepare_recovery.add_argument("--token-env", default="GITHUB_TOKEN")
    prepare_recovery.add_argument("--api-url", default="https://api.github.com")

    assert_recovery = subparsers.add_parser("assert-recovery-consumed")
    assert_recovery.add_argument("--state-root", type=Path, required=True)
    assert_recovery.add_argument("--target-sha", required=True)
    assert_recovery.add_argument("--recovery-file", type=Path, required=True)

    authority = subparsers.add_parser("apply-event")
    authority.add_argument("--repository", required=True)
    authority.add_argument("--repository-root", type=Path, default=Path("."))
    authority.add_argument("--state-root", type=Path, required=True)
    authority.add_argument("--branch-root", type=Path, required=True)
    authority.add_argument("--action", choices=("start", "cancel"), required=True)
    authority.add_argument(
        "--phase", choices=("planning", "implementation"), default="implementation"
    )
    authority.add_argument("--initiative-id", required=True)
    authority.add_argument("--chunk-id", required=True)
    authority.add_argument("--reason", required=True)
    authority.add_argument("--run-id", type=int, required=True)
    authority.add_argument("--dispatcher", required=True)
    authority.add_argument("--main-sha", required=True)
    authority.add_argument("--prior-state-tip", required=True)
    authority.add_argument("--token-env", default="GITHUB_TOKEN")
    authority.add_argument("--api-url", default="https://api.github.com")

    validate_state = subparsers.add_parser("validate-state")
    validate_state.add_argument("--state-root", type=Path, required=True)

    sign_state = subparsers.add_parser("sign-state")
    sign_state.add_argument("--state-root", type=Path, required=True)
    sign_state.add_argument("--private-key", type=Path, required=True)

    verify_state = subparsers.add_parser("verify-state")
    verify_state.add_argument("--state-root", type=Path, required=True)
    verify_state.add_argument("--public-key", type=Path, required=True)
    verify_state.add_argument("--expected-main-sha")

    prepare_state = subparsers.add_parser("prepare-state")
    prepare_state.add_argument("--state-root", type=Path, required=True)
    prepare_state.add_argument("--public-key", type=Path, required=True)

    prepare_output = subparsers.add_parser("prepare-output")
    prepare_output.add_argument("--source-root", type=Path, required=True)
    prepare_output.add_argument("--output-root", type=Path, required=True)
    prepare_output.add_argument("--public-key", type=Path, required=True)

    validate_tree = subparsers.add_parser("validate-tree")
    validate_tree.add_argument("--repository-root", type=Path, required=True)
    validate_tree.add_argument("--tree-sha", required=True)
    validate_tree.add_argument("--output-root", type=Path, required=True)

    publish = subparsers.add_parser("publish")
    publish.add_argument("--branch-root", type=Path, required=True)
    publish.add_argument("--output-root", type=Path, required=True)
    publish.add_argument("--expected-prior-tip", default="")
    publish.add_argument("--message", required=True)

    show = subparsers.add_parser("show")
    show.add_argument("--state-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run metadata validation, state update, validation, or display."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-merge-intent":
            metadata = validate_local_merge_intent(
                args.repository_root,
                args.base_ref,
            )
            print(f"Merge intent passed for {metadata.chunk_id}.")
        elif args.command == "plan-commits":
            for merge_sha in plan_reconciliation_commits(
                args.repository_root,
                args.target_sha,
                args.current_sha,
            ):
                print(merge_sha)
        elif args.command == "resolve-target":
            print(
                resolve_reconciliation_target(
                    args.repository_root,
                    args.event_name,
                    args.event_sha,
                    args.current_main_sha,
                )
            )
        elif args.command == "update":
            _assert_state_branch(args.branch_root or args.state_root)
            token = os.environ.get(args.token_env, "")
            record = collect_merge_record(
                GitHubClient(token, args.api_url),
                args.repository,
                args.merge_sha,
            )
            if (
                args.cutover_chunk_id
                and record["completed_chunk"]["chunk_id"] == args.cutover_chunk_id
            ):
                record["legacy_exemptions"] = load_legacy_exemptions_at_commit(
                    args.repository_root,
                    record["source"]["main_sha"],
                )
                record["event"] = {
                    "type": "cutover",
                    "main_sha": record["source"]["main_sha"],
                    "legacy_exemptions": json.loads(
                        _canonical_json(record["legacy_exemptions"])
                    ),
                }
            recovery_exemptions = []
            if args.recovery_file:
                recovery_exemptions = _validate_recovery_exemptions(
                    _load_json(args.recovery_file)
                )
            if recovery_exemptions:
                changed = apply_merge_record(
                    args.state_root, record,
                    recovery_exemptions=recovery_exemptions,
                )
            else:
                changed = apply_merge_record(args.state_root, record)
            validate_generated_state(args.state_root)
            result = "updated" if changed else "already current"
            print(f"Loop memory {result} for PR #{record['source']['pr_number']}.")
        elif args.command == "prepare-recovery":
            token = os.environ.get(args.token_env, "")
            planned_shas = [
                line.strip()
                for line in args.plan_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            exemptions = prepare_recovery_exemptions(
                GitHubClient(token, args.api_url), args.repository,
                repository_root=args.repository_root, state_root=args.state_root,
                target_sha=args.target_sha, planned_shas=planned_shas,
            )
            transport_version = 2 if len(exemptions) == 3 else 1
            print(_canonical_json({
                "schema_version": transport_version, "exemptions": exemptions
            }))
        elif args.command == "assert-recovery-consumed":
            exemptions = _validate_recovery_exemptions(_load_json(args.recovery_file))
            assert_recovery_consumed(args.state_root, args.target_sha, exemptions)
            print("Loop-memory recovery inventory is fully consumed.")
        elif args.command == "apply-event":
            _assert_state_branch(args.branch_root)
            token = os.environ.get(args.token_env, "")
            state = _load_json(args.state_root / STATE_PATH)
            records = _validate_ledger_entries(_load_ledger(args.state_root / LEDGER_PATH))
            basis = _latest_by_initiative(records).get(args.initiative_id)
            if not isinstance(state, dict) or basis is None:
                raise LoopMemoryError("authority event has no signed initiative basis")
            if args.action == "start":
                selection = resolve_start_selection(
                    args.repository_root,
                    initiative_id=args.initiative_id,
                    chunk_id=args.chunk_id,
                    phase=args.phase,
                    main_sha=args.main_sha,
                    declared_successor=(
                        basis["gate"]["next_chunk_id"] == args.chunk_id
                    ),
                )
            else:
                selection = basis.get("event", {}).get("selection")
            event = collect_authority_event(
                GitHubClient(token, args.api_url),
                args.repository,
                action=args.action,
                initiative_id=args.initiative_id,
                chunk_id=args.chunk_id,
                reason=args.reason,
                run_id=args.run_id,
                dispatcher=args.dispatcher,
                main_sha=args.main_sha,
                prior_state_tip=args.prior_state_tip,
                start_permissions=(
                    load_start_permissions(args.repository_root)
                    if args.action == "start"
                    else frozenset()
                ),
                selection=selection,
            )
            changed = apply_authority_event(
                args.state_root,
                event,
                repository_root=args.repository_root,
                branch_root=args.branch_root,
            )
            validate_generated_state(args.state_root)
            result = "applied" if changed else "already recorded"
            print(f"Loop-memory {args.action} event {result}.")
        elif args.command == "validate-state":
            validate_generated_state(args.state_root)
            print("Generated loop memory state passed.")
        elif args.command == "sign-state":
            sign_generated_state(args.state_root, args.private_key)
            print("Generated loop memory state signed.")
        elif args.command == "verify-state":
            verify_generated_state_signature(
                args.state_root,
                args.public_key,
                args.expected_main_sha,
            )
            print("Generated loop memory state signature passed.")
        elif args.command == "prepare-state":
            authenticated = prepare_generated_state_root(
                args.state_root,
                args.public_key,
            )
            outcome = "authenticated" if authenticated else "ready for rebuild"
            print(f"Generated loop memory state is {outcome}.")
        elif args.command == "prepare-output":
            authenticated = prepare_generated_output(
                args.source_root, args.output_root, args.public_key
            )
            outcome = "authenticated" if authenticated else "ready for rebuild"
            print(f"Generated loop memory output is {outcome}.")
        elif args.command == "validate-tree":
            validate_generated_git_tree(
                args.repository_root, args.tree_sha, args.output_root
            )
            print("Generated Git tree matches signed output.")
        elif args.command == "publish":
            commit = publish_generated_state(
                args.branch_root,
                args.output_root,
                expected_prior_tip=args.expected_prior_tip,
                message=args.message,
            )
            outcome = f"published as {commit}" if commit else "already current"
            print(f"Generated state {outcome}.")
        elif args.command == "show":
            validate_generated_state(args.state_root)
            print((args.state_root / RENDERED_PATH).read_text(encoding="utf-8"), end="")
        else:  # pragma: no cover - argparse enforces the command set.
            raise LoopMemoryError("unsupported command")
    except (LoopMemoryError, OSError, UnicodeDecodeError) as exc:
        print(f"Post-merge memory failed closed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
