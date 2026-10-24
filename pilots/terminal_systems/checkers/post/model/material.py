"""Bounded, complete views of verified Terminal Systems package material."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat

from rubric import Rubric


class MaterialError(RuntimeError):
    """Material cannot be represented completely and safely for assessment."""


@dataclass(frozen=True, slots=True)
class MaterialLimits:
    maximum_entries: int
    maximum_file_bytes: int
    maximum_total_bytes: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value <= 0
            for value in (
                self.maximum_entries,
                self.maximum_file_bytes,
                self.maximum_total_bytes,
            )
        ):
            raise ValueError("material limits must be positive integers")


@dataclass(frozen=True, slots=True)
class MaterialEvidence:
    evidence_id: str
    path: str | None
    kind: str
    byte_count: int | None
    sha256: str
    content_utf8: str | None
    line_count: int | None

    def prompt_value(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "path": self.path,
            "kind": self.kind,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
            "content_utf8": self.content_utf8,
            "line_count": self.line_count,
        }


@dataclass(frozen=True, slots=True)
class MaterialSnapshot:
    digest: str
    evidence: tuple[MaterialEvidence, ...]

    @property
    def by_id(self) -> dict[str, MaterialEvidence]:
        return {item.evidence_id: item for item in self.evidence}

    def prompt_value(self) -> dict[str, object]:
        return {
            "material_digest": self.digest,
            "evidence": [item.prompt_value() for item in self.evidence],
        }


def _hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _safe_relative(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and not path.is_absolute()
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _selected_roots(rubric: Rubric) -> tuple[str, ...]:
    if any(item.get("kind") == "package" for item in rubric.inputs):
        return ("",)
    roots = []
    for item in rubric.inputs:
        kind = item.get("kind")
        path = item.get("relative_path")
        if kind not in {"relative_file", "relative_directory"}:
            raise MaterialError("material_unavailable")
        if type(path) is not str or not _safe_relative(path):
            raise MaterialError("material_unavailable")
        roots.append(path)
    return tuple(dict.fromkeys(roots))


def _inventory(root: Path, selected: tuple[str, ...], maximum_entries: int):
    entries: dict[str, tuple[str, Path]] = {}

    def visit(path: Path, relative: str) -> None:
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise MaterialError("material_unavailable") from exc
        if stat.S_ISLNK(metadata.st_mode) or not (
            stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)
        ):
            raise MaterialError("material_unavailable")
        if relative:
            entries[relative] = (
                "file" if stat.S_ISREG(metadata.st_mode) else "directory",
                path,
            )
            if len(entries) > maximum_entries:
                raise MaterialError("capacity_exceeded")
        if stat.S_ISDIR(metadata.st_mode):
            try:
                children = sorted(os.scandir(path), key=lambda item: item.name)
            except OSError as exc:
                raise MaterialError("material_unavailable") from exc
            for child in children:
                child_relative = f"{relative}/{child.name}" if relative else child.name
                if not _safe_relative(child_relative):
                    raise MaterialError("material_unavailable")
                visit(Path(child.path), child_relative)

    for value in selected:
        selected_path = (
            root if value == "" else root.joinpath(*PurePosixPath(value).parts)
        )
        visit(selected_path, value)
    return tuple((path, *entries[path]) for path in sorted(entries))


def _read_regular(path: Path, maximum_bytes: int) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise MaterialError("material_unavailable")
            value = handle.read(maximum_bytes + 1)
    except MaterialError:
        raise
    except OSError as exc:
        raise MaterialError("material_unavailable") from exc
    if len(value) > maximum_bytes:
        raise MaterialError("capacity_exceeded")
    return value


def collect_material(
    root: Path, rubric: Rubric, limits: MaterialLimits
) -> MaterialSnapshot:
    """Represent every selected entry; never truncate and call coverage complete."""
    try:
        root_metadata = root.lstat()
    except OSError as exc:
        raise MaterialError("material_unavailable") from exc
    if not stat.S_ISDIR(root_metadata.st_mode) or stat.S_ISLNK(root_metadata.st_mode):
        raise MaterialError("material_unavailable")
    rows = _inventory(root, _selected_roots(rubric), limits.maximum_entries)
    total = 0
    projected = []
    files: list[MaterialEvidence] = []
    for relative, kind, path in rows:
        if kind == "directory":
            projected.append({"path": relative, "kind": kind})
            continue
        raw = _read_regular(path, limits.maximum_file_bytes)
        total += len(raw)
        if total > limits.maximum_total_bytes:
            raise MaterialError("capacity_exceeded")
        digest = _hash(raw)
        projected.append(
            {"path": relative, "kind": kind, "byte_count": len(raw), "sha256": digest}
        )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        files.append(
            MaterialEvidence(
                evidence_id=f"file-{len(files) + 1}",
                path=relative,
                kind="file",
                byte_count=len(raw),
                sha256=digest,
                content_utf8=text,
                line_count=(len(text.splitlines()) if text is not None else None),
            )
        )
    inventory_bytes = _canonical(projected)
    inventory = MaterialEvidence(
        evidence_id="inventory",
        path=None,
        kind="inventory",
        byte_count=None,
        sha256=_hash(inventory_bytes),
        content_utf8=inventory_bytes.decode("utf-8"),
        line_count=None,
    )
    evidence = (inventory, *files)
    digest = _hash(_canonical([item.prompt_value() for item in evidence]))
    return MaterialSnapshot(digest=digest, evidence=evidence)


__all__ = (
    "MaterialError",
    "MaterialEvidence",
    "MaterialLimits",
    "MaterialSnapshot",
    "collect_material",
)
