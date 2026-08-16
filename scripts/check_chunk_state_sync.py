#!/usr/bin/env python3
"""Require one chunk PR to land its durable state projections atomically."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHUNK_PATH = re.compile(r"^\.agent-loop/initiatives/([^/]+)/chunks/([^/]+)\.md$")
OUTCOME = re.compile(r"^- Outcome on merge: `(planned|complete|cancelled|superseded)`\s*$")
MERGE_STATE_SECTION = re.compile(
    r"^## Merge state\s*$\n(?P<body>.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
CHUNK_ID = re.compile(r"^([A-Z]+-[A-Z]+-[0-9]+-[A-Z0-9]+)(?:-|$)")
IMPLEMENTATION_PREFIXES = (
    ".ci/",
    ".github/workflows/",
    "backend/",
    "frontend/src/",
    "scripts/",
)
OUTCOME_WORDS = {
    "planned": ("planned", "proposed"),
    "complete": ("complete", "merged"),
    "cancelled": ("cancelled",),
    "superseded": ("superseded",),
}
REVIEW_ONLY_WORDS = ("in review", "pending review", "ready for review")
TEMPORAL_PROJECTION = re.compile(r"\bon merge\b", re.IGNORECASE)


class ChunkStateError(RuntimeError):
    """Raised when a PR would merge stale or incomplete chunk state."""


def changed_paths(base_ref: str, head_ref: str = "HEAD") -> list[str]:
    """Return paths changed by the prospective merge."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _read(relative_path: str) -> str:
    try:
        return (ROOT / relative_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ChunkStateError(f"CHUNK_STATE_UNREADABLE: {relative_path}") from exc


def _chunk_row(chunk_map: str, chunk_id: str) -> str:
    rows = [line for line in chunk_map.splitlines() if f"`{chunk_id}`" in line]
    if len(rows) != 1:
        raise ChunkStateError(f"CHUNK_STATE_MAP_ROW_INVALID: {chunk_id}")
    return rows[0]


def _projection_lines(projection: str, chunk_id: str) -> list[str]:
    identifier = re.compile(rf"(?<![A-Z0-9-]){re.escape(chunk_id)}(?![A-Z0-9-])")
    return [line for line in projection.splitlines() if identifier.search(line)]


def _declared_outcome(contract: str, chunk_id: str) -> str:
    sections = list(MERGE_STATE_SECTION.finditer(contract))
    declarations = [
        match
        for line in contract.splitlines()
        if (match := OUTCOME.fullmatch(line)) is not None
    ]
    if len(sections) != 1 or len(declarations) != 1:
        raise ChunkStateError(f"CHUNK_STATE_OUTCOME_INVALID: {chunk_id}")
    section_declarations = [
        match
        for line in sections[0].group("body").splitlines()
        if (match := OUTCOME.fullmatch(line)) is not None
    ]
    if len(section_declarations) != 1:
        raise ChunkStateError(f"CHUNK_STATE_OUTCOME_INVALID: {chunk_id}")
    return section_declarations[0].group(1)


def _has_outcome(line: str, outcome: str) -> bool:
    """Return whether a line asserts, rather than merely contains, an outcome."""
    folded = line.casefold()
    for word in OUTCOME_WORDS[outcome]:
        token = re.compile(rf"(?<![a-z0-9_]){re.escape(word)}(?![a-z0-9_])")
        for match in token.finditer(folded):
            prefix = folded[max(0, match.start() - 32) : match.start()]
            if re.search(r"\b(?:not(?:\s+yet)?|never)\s+$", prefix):
                continue
            return True
    return False


def _requires_contract(paths: set[str]) -> bool:
    return any(path.startswith(IMPLEMENTATION_PREFIXES) for path in paths)


def _validate_chunk(chunk_path: str, changed: set[str]) -> str:
    """Validate one changed contract and return its declared merge outcome."""
    match = CHUNK_PATH.fullmatch(chunk_path)
    assert match is not None
    initiative_directory, chunk_filename = match.groups()
    chunk_id_match = CHUNK_ID.match(chunk_filename)
    if chunk_id_match is None:
        raise ChunkStateError(f"CHUNK_STATE_ID_INVALID: {chunk_filename}")
    chunk_id = chunk_id_match.group(1)
    contract = _read(chunk_path)
    outcome = _declared_outcome(contract, chunk_id)

    initiative_root = f".agent-loop/initiatives/{initiative_directory}"
    chunk_map_path = f"{initiative_root}/CHUNK_MAP.md"
    status_path = f"{initiative_root}/STATUS.md"
    current_state_path = ".agent-loop/CURRENT_STATE.md"
    required = {chunk_map_path, status_path, current_state_path}
    missing = sorted(required - changed)
    if missing:
        raise ChunkStateError("CHUNK_STATE_PROJECTION_MISSING: " + ", ".join(missing))

    chunk_map = _read(chunk_map_path)
    status = _read(status_path)
    current_state = _read(current_state_path)
    row = _chunk_row(chunk_map, chunk_id)
    if TEMPORAL_PROJECTION.search(row):
        raise ChunkStateError(f"CHUNK_STATE_TEMPORAL_PROJECTION: {chunk_id}")
    if not _has_outcome(row, outcome):
        raise ChunkStateError(f"CHUNK_STATE_MAP_OUTCOME_MISMATCH: {chunk_id}")
    if outcome == "complete" and any(word in row.casefold() for word in REVIEW_ONLY_WORDS):
        raise ChunkStateError(f"CHUNK_STATE_REVIEW_WORDING: {chunk_id}")
    for projection_path, projection in (
        (status_path, status),
        (current_state_path, current_state),
    ):
        lines = _projection_lines(projection, chunk_id)
        if not lines:
            raise ChunkStateError(f"CHUNK_STATE_ID_MISSING: {projection_path}: {chunk_id}")
        if not any(_has_outcome(line, outcome) for line in lines):
            raise ChunkStateError(f"CHUNK_STATE_OUTCOME_MISMATCH: {projection_path}: {chunk_id}")
        if any(TEMPORAL_PROJECTION.search(line) for line in lines):
            raise ChunkStateError(
                f"CHUNK_STATE_TEMPORAL_PROJECTION: {projection_path}: {chunk_id}"
            )
    return outcome


def validate(paths: list[str]) -> None:
    """Validate atomic state for planning contracts or one implementation chunk."""
    changed = set(paths)
    chunk_paths = sorted(path for path in changed if CHUNK_PATH.fullmatch(path))
    implementation = _requires_contract(changed)
    if implementation and not chunk_paths:
        raise ChunkStateError("CHUNK_STATE_CONTRACT_MISSING")
    if implementation and len(chunk_paths) > 1:
        raise ChunkStateError("CHUNK_STATE_MULTIPLE_CONTRACTS")
    outcomes = [_validate_chunk(chunk_path, changed) for chunk_path in chunk_paths]
    if len(outcomes) > 1 and any(outcome != "planned" for outcome in outcomes):
        raise ChunkStateError("CHUNK_STATE_MULTIPLE_FINAL_OUTCOMES")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", default="HEAD")
    args = parser.parse_args()
    try:
        validate(changed_paths(args.base_ref, args.head_ref))
    except (ChunkStateError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("Atomic chunk state check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
