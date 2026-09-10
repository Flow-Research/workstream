"""Bounded ingress inspection for supported original guide documents."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
import stat
from typing import BinaryIO
import zipfile
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.modules.artifacts.zip_safety import zip_directory_facts


_SAMPLE_BYTES = 64 * 1024
_MAXIMUM_RELATIONSHIP_BYTES = 1024 * 1024
_EXECUTABLE_SUFFIXES = {
    ".bat",
    ".cmd",
    ".com",
    ".dll",
    ".exe",
    ".jar",
    ".js",
    ".msi",
    ".ps1",
    ".scr",
}
OOXML_REQUIRED_MARKERS = {
    "docx": frozenset({"[Content_Types].xml", "_rels/.rels", "word/document.xml"}),
    "pptx": frozenset({"[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml"}),
    "xlsx": frozenset({"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml"}),
}


@dataclass(frozen=True, slots=True)
class GuideFormatLimits:
    """Fixed startup-owned limits for structural guide inspection."""

    maximum_entries: int = 2_000
    maximum_central_directory_bytes: int = 8 * 1024 * 1024
    maximum_decompressed_bytes: int = 128 * 1024 * 1024
    maximum_nested_archive_bytes: int = 16 * 1024 * 1024
    maximum_nesting_depth: int = 8
    maximum_compression_ratio: int = 100

    def archive_totals_exceeded(self, *, entry_count: int, decompressed_bytes: int) -> bool:
        return (
            entry_count > self.maximum_entries
            or decompressed_bytes > self.maximum_decompressed_bytes
        )

    def compression_ratio_exceeded(self, *, file_size: int, compressed_size: int) -> bool:
        return file_size > 0 and (
            compressed_size == 0
            or file_size > compressed_size * self.maximum_compression_ratio
        )


@dataclass(frozen=True, slots=True)
class GuideFormatResult:
    """Bounded classification facts containing no source-controlled names."""

    detected_format: str
    status: str
    facts: dict[str, int | str | bool]


@dataclass(frozen=True, slots=True)
class BoundGuideFormatInspector:
    """Bind approved item metadata to the one syntactic format detector."""

    detector: GuideFormatDetector
    declared_media_type: str
    ingestion_adapter: str

    def inspect(self, reader: BinaryIO) -> GuideFormatResult:
        return self.detector.detect(
            reader,
            declared_media_type=self.declared_media_type,
            ingestion_adapter=self.ingestion_adapter,
        )


class GuideFormatDetector:
    """Classify signatures and bounded containers without semantic extraction."""

    def __init__(self, limits: GuideFormatLimits) -> None:
        self._limits = limits

    def detect(
        self,
        reader: BinaryIO,
        *,
        declared_media_type: str,
        ingestion_adapter: str | None = None,
    ) -> GuideFormatResult:
        reader.seek(0)
        header = reader.read(_SAMPLE_BYTES)
        reader.seek(0)
        if header.startswith(b"%PDF-"):
            return self._classified("pdf")
        if header.startswith(b"PK\x03\x04") or header.startswith(b"PK\x05\x06"):
            return self._inspect_zip(reader)
        return GuideFormatResult("opaque", "unsupported", {})

    def _inspect_zip(self, reader: BinaryIO) -> GuideFormatResult:
        state = {"entries": 0, "decompressed": 0, "compressed": 0, "depth": 0}
        try:
            unsafe = self._inspect_archive(reader, state=state, depth=0)
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError):
            return GuideFormatResult("zip", "malformed", self._bounded_zip_facts(state))
        if unsafe is not None:
            return GuideFormatResult("zip", unsafe, self._bounded_zip_facts(state))
        reader.seek(0)
        with zipfile.ZipFile(reader) as archive:
            names = {info.filename for info in archive.infolist()}
        matches = [
            name for name, required in OOXML_REQUIRED_MARKERS.items() if required <= names
        ]
        facts = self._bounded_zip_facts(state)
        if len(matches) > 1:
            return GuideFormatResult("zip", "ambiguous", facts)
        if not matches:
            return GuideFormatResult("zip", "unsupported", facts)
        return GuideFormatResult(matches[0], "unsupported" if matches[0] == "xlsx" else "classified", facts)

    def _inspect_archive(
        self,
        source: BinaryIO | BytesIO,
        *,
        state: dict[str, int],
        depth: int,
    ) -> str | None:
        state["depth"] = max(state["depth"], depth)
        if depth > self._limits.maximum_nesting_depth:
            return "limit_exceeded"
        entry_count, central_directory_bytes = zip_directory_facts(source)
        if (
            state["entries"] + entry_count > self._limits.maximum_entries
            or central_directory_bytes > self._limits.maximum_central_directory_bytes
        ):
            return "limit_exceeded"
        source.seek(0)
        with zipfile.ZipFile(source) as archive:
            seen: set[str] = set()
            for info in archive.infolist():
                state["entries"] += 1
                state["decompressed"] += info.file_size
                state["compressed"] += info.compress_size
                if self._limits.archive_totals_exceeded(
                    entry_count=state["entries"],
                    decompressed_bytes=state["decompressed"],
                ) or self._limits.compression_ratio_exceeded(
                    file_size=info.file_size,
                    compressed_size=info.compress_size,
                ):
                    return "limit_exceeded"
                normalized = info.filename.replace("\\", "/")
                path = PurePosixPath(normalized)
                folded = normalized.casefold()
                if (
                    not normalized
                    or normalized.startswith("/")
                    or (path.parts and ":" in path.parts[0])
                    or ".." in path.parts
                    or folded in seen
                    or info.flag_bits & 0x1
                ):
                    return "malformed"
                seen.add(folded)
                mode = info.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    return "malformed"
                lower = normalized.lower()
                if (
                    lower.endswith("vbaproject.bin")
                    or any(lower.endswith(suffix) for suffix in _EXECUTABLE_SUFFIXES)
                    or "/embeddings/" in f"/{lower}"
                ):
                    return "malformed"
                if lower.endswith(".rels"):
                    if info.file_size > _MAXIMUM_RELATIONSHIP_BYTES:
                        return "limit_exceeded"
                    relationship = archive.read(info)
                    if b"<!DOCTYPE" in relationship.upper():
                        return "malformed"
                    try:
                        relationships = ElementTree.fromstring(relationship, forbid_dtd=True)
                    except (ElementTree.ParseError, DefusedXmlException):
                        return "malformed"
                    if any(
                        str(element.attrib.get("TargetMode", "")).strip().casefold()
                        == "external"
                        for element in relationships.iter()
                    ):
                        return "malformed"
                if lower.endswith(".zip"):
                    if info.file_size > self._limits.maximum_nested_archive_bytes:
                        return "limit_exceeded"
                    nested = archive.read(info)
                    nested_result = self._inspect_archive(
                        BytesIO(nested), state=state, depth=depth + 1
                    )
                    if nested_result is not None:
                        return nested_result
        return None

    @staticmethod
    def _classified(detected_format: str) -> GuideFormatResult:
        return GuideFormatResult(detected_format, "classified", {})

    @staticmethod
    def _bounded_zip_facts(state: dict[str, int]) -> dict[str, int]:
        return {
            "entry_count": state["entries"],
            "decompressed_bytes": state["decompressed"],
            "maximum_depth": state["depth"],
        }
