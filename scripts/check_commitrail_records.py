#!/usr/bin/env python3
"""Validate Workstream's small Commitrail record contract."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

try:
    from scripts.git_delta import GitCommandError, committed_changed_files, run_checked
except ModuleNotFoundError:  # Direct `python scripts/...` execution.
    from git_delta import GitCommandError, committed_changed_files, run_checked

ROOT = Path(__file__).resolve().parents[1]
DISPOSITIONS = {"Planned", "Complete", "Stopped", "Superseded"}
PRE_CUTOVER_MANIFEST_DIGESTS = {
    "7f7ec4e15bd85fe76d52f5f69c85308bd12b777d": "ce604b34e7d4c3a6b5a24841143a1213a640ba3aa30cada9e8418bc1a25f6cde",
}
RECORD_REQUIRED_PREFIXES = (
    ".agents/skills/",
    ".ci/",
    ".codex/agents/",
    ".commitrail/",
    ".github/workflows/",
    "backend/",
    "docs/engineering/",
    "frontend/src/",
    "scripts/",
)
RECORD_REQUIRED_FILES = {
    ".github/pull_request_template.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "README.md",
}
RECORD_PATH = re.compile(
    r"^\.commitrail/initiatives/(?P<initiative>[A-Z]+-[A-Z]+-[0-9]+)/"
    r"(?P<record>[A-Z]+-[A-Z]+-[0-9]+-[A-Z0-9]+)\.md$"
)
REQUIRED_HEADINGS = (
    "## Intent",
    "## Bounded change",
    "## Acceptance criteria",
    "## Risk and review routing",
    "## Evidence",
)
CHANGE_TEMPLATE_PATH = ".commitrail/CHANGE_TEMPLATE.md"
TRANSIENT_DECLARATION = re.compile(
    r"^\s*(?:[-*]\s*)?(?:status|review|ci|approval|merge)\s*:"
    r"\s*(?:in review|pending|passing|passed|approved|ready(?: to merge)?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
FENCE_OPEN = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>[^\r\n]*)$")
FENCE_CLOSE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})[ \t]*$")


class CommitrailError(RuntimeError):
    """Raised when the repository violates the Commitrail contract."""


def changed_paths(base_ref: str, head_ref: str = "HEAD") -> list[str]:
    return committed_changed_files(
        base_ref,
        head_ref,
        repository_root=ROOT,
    )


def tracked_legacy_paths(root: Path) -> list[str]:
    output = run_checked(
        ["git", "ls-files", ".agent-loop", ".agent-loop/**"],
        repository_root=root,
    )
    return output.splitlines()


def _read(root: Path, relative: str) -> str:
    try:
        return (root / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CommitrailError(f"COMMITRAIL_UNREADABLE: {relative}") from exc


def _masked_markdown_line(line: str) -> str:
    return "".join(character if character in "\r\n" else " " for character in line)


def _markdown_structure(text: str, source: str) -> str:
    """Mask fenced content while preserving offsets used to slice source Markdown."""
    masked: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    for line in text.splitlines(keepends=True):
        candidate = line.rstrip("\r\n")
        if fence_character is None:
            opening = FENCE_OPEN.fullmatch(candidate)
            if opening is None:
                masked.append(line)
                continue
            fence = opening.group("fence")
            if fence[0] == "`" and "`" in opening.group("info"):
                raise CommitrailError(f"COMMITRAIL_MARKDOWN_FENCE_INVALID: {source}")
            fence_character = fence[0]
            fence_length = len(fence)
            masked.append(_masked_markdown_line(line))
            continue

        masked.append(_masked_markdown_line(line))
        closing = FENCE_CLOSE.fullmatch(candidate)
        if closing is None:
            continue
        fence = closing.group("fence")
        if fence[0] == fence_character and len(fence) >= fence_length:
            fence_character = None
            fence_length = 0

    if fence_character is not None:
        raise CommitrailError(f"COMMITRAIL_MARKDOWN_FENCE_UNCLOSED: {source}")
    return "".join(masked)


def _disposition(text: str, label: str) -> str:
    match = re.search(rf"^- {re.escape(label)}: `?([^`\n]+)`?\s*$", text, re.MULTILINE)
    if match is None or match.group(1).strip() not in DISPOSITIONS:
        raise CommitrailError(f"COMMITRAIL_DISPOSITION_INVALID: {label}")
    return match.group(1).strip()


def _index_disposition(index: str, initiative: str) -> str:
    rows = []
    for line in index.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells:
            continue
        label = re.sub(r"^\[([^]]+)\]\([^)]*\)$", r"\1", cells[0])
        if label == initiative:
            rows.append(line)
    if len(rows) != 1:
        raise CommitrailError(f"COMMITRAIL_INDEX_ROW_INVALID: {initiative}")
    cells = [cell.strip() for cell in rows[0].strip("|").split("|")]
    if len(cells) < 3 or cells[1] not in DISPOSITIONS:
        raise CommitrailError(f"COMMITRAIL_INDEX_DISPOSITION_INVALID: {initiative}")
    return cells[1]


def _validate_index_dispositions(index: str) -> None:
    for line in index.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or cells[0] in {"Initiative", "---"}:
            continue
        if len(cells) < 3 or cells[1] not in DISPOSITIONS:
            raise CommitrailError(f"COMMITRAIL_INDEX_DISPOSITION_INVALID: {cells[0]}")


def _tree_blob_map(output: str) -> dict[str, str]:
    blobs: dict[str, str] = {}
    for line in output.splitlines():
        try:
            metadata, path = line.split("\t", 1)
            _mode, object_type, blob = metadata.split()
        except ValueError as exc:
            raise CommitrailError("COMMITRAIL_RELOCATION_BASE_INVALID") from exc
        if (
            object_type != "blob"
            or not re.fullmatch(r"[0-9a-f]{40}", blob)
            or path in blobs
        ):
            raise CommitrailError("COMMITRAIL_RELOCATION_BASE_INVALID")
        blobs[path] = blob
    return blobs


def _required_section_body(
    text: str,
    structure: str,
    heading: str,
    record_path: str,
) -> None:
    match = re.search(rf"^{re.escape(heading)}[ \t]*$", structure, re.MULTILINE)
    if match is None:
        raise CommitrailError(f"COMMITRAIL_FIELD_MISSING: {record_path}: {heading}")
    next_heading = re.search(r"^##\s+", structure[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading is not None else len(text)
    body = text[match.end() : end]
    substantive_lines = [
        line
        for line in body.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not substantive_lines:
        raise CommitrailError(f"COMMITRAIL_FIELD_EMPTY: {record_path}: {heading}")


def _template_markers(root: Path) -> tuple[str, ...]:
    template = _read(root, CHANGE_TEMPLATE_PATH)
    first_line = template.splitlines()[0] if template.splitlines() else ""
    markers = set(re.findall(r"`(<[^`\n]+>)`", template))
    markers.update(re.findall(r"<[^>\n]+>", first_line))
    return tuple(sorted(markers))


def _validate_relocation_inventory(
    root: Path,
    comparison_base_ref: str | None = None,
) -> None:
    relative = ".commitrail/initiatives/WS-ENG-009/RELOCATION_INVENTORY.md"
    path = root / relative
    if not path.is_file():
        cutover = root / ".commitrail/initiatives/WS-ENG-009/OVERVIEW.md"
        if cutover.is_file():
            raise CommitrailError("COMMITRAIL_RELOCATION_INVENTORY_MISSING")
        return
    text = _read(root, relative)
    match = re.search(r"^Base: `([0-9a-f]{40})`\.$", text, re.MULTILINE)
    if match is None:
        raise CommitrailError("COMMITRAIL_RELOCATION_BASE_INVALID")
    base = match.group(1)
    declared_tree = run_checked(
        ["git", "ls-tree", "-r", base, "--", ".agent-loop"],
        repository_root=root,
    )
    source_blobs = _tree_blob_map(declared_tree)
    expected = set(source_blobs)
    recorded = {
        line.split("\t", 1)[0]
        for line in text.splitlines()
        if line.startswith(".agent-loop/") and "\t" in line
    }
    if recorded != expected:
        raise CommitrailError("COMMITRAIL_RELOCATION_INVENTORY_INCOMPLETE")

    if comparison_base_ref is not None:
        comparison_tree = run_checked(
            ["git", "ls-tree", "-r", comparison_base_ref, "--", ".agent-loop"],
            repository_root=root,
        )
        # Before cutover merges, a rebased PR base that still carries legacy
        # records must match the declared archive source exactly. After
        # cutover, a trusted base correctly has no .agent-loop tree; permanent
        # manifest and destination checks below continue to protect custody.
        if comparison_tree and comparison_tree != declared_tree:
            raise CommitrailError("COMMITRAIL_RELOCATION_BASE_DRIFT")

    manifest_relative = ".commitrail/initiatives/WS-ENG-009/PRE_CUTOVER_MANIFEST.tsv"
    manifest_path = root / manifest_relative
    if not manifest_path.is_file():
        raise CommitrailError("COMMITRAIL_PRE_CUTOVER_MANIFEST_MISSING")
    expected_digest = PRE_CUTOVER_MANIFEST_DIGESTS.get(base)
    if expected_digest is None:
        raise CommitrailError("COMMITRAIL_RELOCATION_BASE_UNRECOGNIZED")
    try:
        manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise CommitrailError(f"COMMITRAIL_UNREADABLE: {manifest_relative}") from exc
    if manifest_digest != expected_digest:
        raise CommitrailError("COMMITRAIL_PRE_CUTOVER_MANIFEST_CHANGED")
    rows: dict[str, tuple[str, str]] = {}
    for line in _read(root, manifest_relative).splitlines():
        if not line or line == "source\tdestination\tbase_blob_sha":
            continue
        cells = line.split("\t")
        if len(cells) != 3 or cells[0] in rows:
            raise CommitrailError("COMMITRAIL_PRE_CUTOVER_MANIFEST_INVALID")
        source, destination, base_blob = cells
        if (
            source not in expected
            or not destination.startswith(".commitrail/initiatives/")
            or "/pre-cutover/" not in destination
            or not re.fullmatch(r"[0-9a-f]{40}", base_blob)
        ):
            raise CommitrailError("COMMITRAIL_PRE_CUTOVER_MANIFEST_INVALID")
        rows[source] = (destination, base_blob)

    destinations = {destination for destination, _ in rows.values()}
    if len(destinations) != len(rows):
        raise CommitrailError("COMMITRAIL_PRE_CUTOVER_MANIFEST_INVALID")
    actual_destinations = {
        path.relative_to(root).as_posix()
        for path in (root / ".commitrail" / "initiatives").glob("*/pre-cutover/**/*")
        if path.is_file()
    }
    if destinations != actual_destinations:
        raise CommitrailError("COMMITRAIL_PRE_CUTOVER_DESTINATIONS_INVALID")

    indexed_destinations: dict[str, tuple[str, str]] = {}
    index_output = run_checked(
        ["git", "ls-files", "--stage", "--", *sorted(destinations)],
        repository_root=root,
    )
    for line in index_output.splitlines():
        metadata, destination = line.split("\t", 1)
        mode, blob, stage = metadata.split()
        if stage != "0" or destination in indexed_destinations:
            raise CommitrailError("COMMITRAIL_PRE_CUTOVER_DESTINATIONS_INVALID")
        indexed_destinations[destination] = (mode, blob)
    if set(indexed_destinations) != destinations:
        raise CommitrailError("COMMITRAIL_PRE_CUTOVER_DESTINATIONS_INVALID")

    ordered_destinations = sorted(destinations)
    for destination in ordered_destinations:
        destination_path = root / destination
        destination_mode, _indexed_blob = indexed_destinations[destination]
        if destination_path.is_symlink() or destination_mode != "100644":
            raise CommitrailError(
                f"COMMITRAIL_PRE_CUTOVER_DESTINATION_NOT_REGULAR: {destination}"
            )

    destination_hashes = run_checked(
        ["git", "hash-object", "--", *ordered_destinations],
        repository_root=root,
    ).splitlines()
    if len(destination_hashes) != len(ordered_destinations) or any(
        not re.fullmatch(r"[0-9a-f]{40}", blob) for blob in destination_hashes
    ):
        raise CommitrailError("COMMITRAIL_PRE_CUTOVER_DESTINATIONS_INVALID")
    worktree_blobs = dict(zip(ordered_destinations, destination_hashes, strict=True))

    for source, (destination, declared_blob) in rows.items():
        _destination_mode, indexed_blob = indexed_destinations[destination]
        source_blob = source_blobs[source]
        destination_blob = worktree_blobs[destination]
        if (
            declared_blob != source_blob
            or indexed_blob != source_blob
            or destination_blob != source_blob
        ):
            raise CommitrailError(
                f"COMMITRAIL_PRE_CUTOVER_CONTENT_MISMATCH: {destination}"
            )


def validate(
    root: Path,
    paths: list[str],
    *,
    comparison_base_ref: str | None = None,
) -> None:
    legacy = tracked_legacy_paths(root)
    if legacy:
        raise CommitrailError("COMMITRAIL_LEGACY_PATH: " + ", ".join(legacy[:3]))

    changed = set(paths)
    implementation = any(
        path in RECORD_REQUIRED_FILES or path.startswith(RECORD_REQUIRED_PREFIXES)
        for path in changed
    )
    records = sorted(path for path in changed if RECORD_PATH.fullmatch(path))
    if implementation and len(records) != 1:
        raise CommitrailError("COMMITRAIL_CHANGE_RECORD_REQUIRED")
    if len(records) > 1:
        raise CommitrailError("COMMITRAIL_MULTIPLE_CHANGE_RECORDS")

    index_path = ".commitrail/INDEX.md"
    index = _read(root, index_path)
    index_structure = _markdown_structure(index, index_path)
    _validate_index_dispositions(index_structure)
    _validate_relocation_inventory(root, comparison_base_ref)
    if TRANSIENT_DECLARATION.search(index_structure):
        raise CommitrailError("COMMITRAIL_TRANSIENT_STATE: INDEX.md")

    overview_root = root / ".commitrail" / "initiatives"
    for overview_path in overview_root.glob("*/OVERVIEW.md"):
        relative = overview_path.relative_to(root).as_posix()
        overview = _read(root, relative)
        overview_structure = _markdown_structure(overview, relative)
        if TRANSIENT_DECLARATION.search(overview_structure):
            raise CommitrailError(f"COMMITRAIL_TRANSIENT_STATE: {relative}")
        initiative = overview_path.parent.name
        disposition = _disposition(overview_structure, "Disposition")
        if _index_disposition(index_structure, initiative) != disposition:
            raise CommitrailError(f"COMMITRAIL_INDEX_OVERVIEW_MISMATCH: {initiative}")

    for record_path in records:
        match = RECORD_PATH.fullmatch(record_path)
        assert match is not None
        record = _read(root, record_path)
        record_structure = _markdown_structure(record, record_path)
        _disposition(record_structure, "Durable disposition")
        for heading in REQUIRED_HEADINGS:
            _required_section_body(record, record_structure, heading, record_path)
        outcome = re.search(
            r"^- Intended merge outcome:[ \t]*(.*)$",
            record_structure,
            re.MULTILINE,
        )
        if outcome is None:
            raise CommitrailError(
                f"COMMITRAIL_FIELD_MISSING: {record_path}: Intended merge outcome"
            )
        if not outcome.group(1).strip():
            raise CommitrailError(
                f"COMMITRAIL_FIELD_EMPTY: {record_path}: Intended merge outcome"
            )
        for marker in _template_markers(root):
            if marker in record_structure:
                raise CommitrailError(
                    f"COMMITRAIL_TEMPLATE_MARKER: {record_path}: {marker}"
                )
        if TRANSIENT_DECLARATION.search(record_structure):
            raise CommitrailError(f"COMMITRAIL_TRANSIENT_STATE: {record_path}")
        initiative = match.group("initiative")
        if not match.group("record").startswith(f"{initiative}-"):
            raise CommitrailError(f"COMMITRAIL_RECORD_OWNER_MISMATCH: {record_path}")
        overview = f".commitrail/initiatives/{initiative}/OVERVIEW.md"
        if not (root / overview).is_file():
            raise CommitrailError(f"COMMITRAIL_OVERVIEW_MISSING: {initiative}")
        _index_disposition(index_structure, initiative)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", default="HEAD")
    args = parser.parse_args()
    try:
        validate(
            ROOT,
            changed_paths(args.base_ref, args.head_ref),
            comparison_base_ref=args.base_ref,
        )
    except (CommitrailError, GitCommandError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("Commitrail record check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
