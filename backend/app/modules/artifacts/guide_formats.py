"""Deterministic syntactic guide-format detection over verified scratch bytes."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
import stat
from typing import BinaryIO
import zipfile
from xml.etree import ElementTree


DETECTOR_NAME = "workstream.guide_format"
DETECTOR_VERSION = "1"
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


@dataclass(frozen=True, slots=True)
class GuideFormatLimits:
    """Fixed startup-owned limits for structural guide inspection."""

    maximum_entries: int = 2_000
    maximum_central_directory_bytes: int = 8 * 1024 * 1024
    maximum_decompressed_bytes: int = 128 * 1024 * 1024
    maximum_nesting_depth: int = 8
    maximum_compression_ratio: int = 100
    maximum_image_pixels: int = 40_000_000
    maximum_image_dimension: int = 16_384

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
        image = self._image_dimensions(header)
        if image is not None:
            image_format, width, height = image
            if (
                width > self._limits.maximum_image_dimension
                or height > self._limits.maximum_image_dimension
                or width * height > self._limits.maximum_image_pixels
            ):
                return GuideFormatResult(
                    detected_format=image_format,
                    status="limit_exceeded",
                    facts={"width": width, "height": height},
                )
            return GuideFormatResult(
                detected_format=image_format,
                status="classified",
                facts={"width": width, "height": height},
            )
        if self._is_audio_video_signature(header):
            return GuideFormatResult("audio_video", "unsupported", {})
        if header.startswith(b"PK\x03\x04") or header.startswith(b"PK\x05\x06"):
            return self._inspect_zip(reader)
        media_type = declared_media_type.split(";", 1)[0].strip().lower()
        declared = {
            "application/json": "json",
            "text/csv": "csv",
            "text/markdown": "markdown",
            "text/plain": "plain_text",
        }.get(media_type)
        if declared is None:
            declared = {
                "csv": "csv",
                "json": "json",
                "markdown": "markdown",
                "text": "plain_text",
                "plain_text": "plain_text",
            }.get((ingestion_adapter or "").strip().lower())
        if declared is not None:
            try:
                header.decode("utf-8")
            except UnicodeDecodeError:
                return GuideFormatResult(declared, "malformed", {})
            return self._classified(declared)
        if media_type.startswith("audio/") or media_type.startswith("video/"):
            return GuideFormatResult("audio_video", "unsupported", {})
        try:
            decoded = header.decode("utf-8")
        except UnicodeDecodeError:
            return GuideFormatResult("opaque", "unsupported", {})
        if "\x00" in decoded:
            return GuideFormatResult("opaque", "unsupported", {})
        return self._classified("plain_text")

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
        markers = {
            "docx": {"[Content_Types].xml", "_rels/.rels", "word/document.xml"},
            "pptx": {"[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml"},
            "xlsx": {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml"},
        }
        matches = [name for name, required in markers.items() if required <= names]
        facts = self._bounded_zip_facts(state)
        if len(matches) > 1:
            return GuideFormatResult("zip", "ambiguous", facts)
        if not matches:
            return GuideFormatResult("zip", "unsupported", facts)
        return GuideFormatResult(matches[0], "classified", facts)

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
        entry_count, central_directory_bytes = self._zip_directory_facts(source)
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
                        relationships = ElementTree.fromstring(relationship)
                    except ElementTree.ParseError:
                        return "malformed"
                    if any(
                        str(element.attrib.get("TargetMode", "")).strip().casefold()
                        == "external"
                        for element in relationships.iter()
                    ):
                        return "malformed"
                if lower.endswith(".zip"):
                    nested = archive.read(info)
                    nested_result = self._inspect_archive(
                        BytesIO(nested), state=state, depth=depth + 1
                    )
                    if nested_result is not None:
                        return nested_result
        return None

    @staticmethod
    def _zip_directory_facts(source: BinaryIO | BytesIO) -> tuple[int, int]:
        """Read the bounded EOCD before ZipFile allocates its entry inventory."""
        source.seek(0, 2)
        size = source.tell()
        source.seek(max(0, size - 65_557))
        tail = source.read(65_557)
        marker = tail.rfind(b"PK\x05\x06")
        if marker < 0 or len(tail) - marker < 22:
            raise zipfile.BadZipFile("missing end of central directory")
        if tail[marker + 4 : marker + 8] != b"\x00\x00\x00\x00":
            raise zipfile.BadZipFile("multi-disk archive")
        entry_count = int.from_bytes(tail[marker + 10 : marker + 12], "little")
        central_directory_bytes = int.from_bytes(tail[marker + 12 : marker + 16], "little")
        if entry_count == 0xFFFF or central_directory_bytes == 0xFFFFFFFF:
            raise zipfile.BadZipFile("zip64 archive is unsupported")
        return entry_count, central_directory_bytes

    @staticmethod
    def _is_audio_video_signature(header: bytes) -> bool:
        return (
            header.startswith((b"ID3", b"fLaC", b"OggS"))
            or (header.startswith(b"RIFF") and header[8:12] in {b"WAVE", b"AVI "})
            or (len(header) >= 12 and header[4:8] == b"ftyp")
        )

    @staticmethod
    def _image_dimensions(header: bytes) -> tuple[str, int, int] | None:
        if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
            return "png", int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
        if header.startswith(b"RIFF") and header[8:12] == b"WEBP" and len(header) >= 30:
            if header[12:16] == b"VP8X":
                return (
                    "webp",
                    1 + int.from_bytes(header[24:27], "little"),
                    1 + int.from_bytes(header[27:30], "little"),
                )
            if header[12:16] == b"VP8 " and header[23:26] == b"\x9d\x01\x2a":
                return (
                    "webp",
                    int.from_bytes(header[26:28], "little") & 0x3FFF,
                    int.from_bytes(header[28:30], "little") & 0x3FFF,
                )
            if header[12:16] == b"VP8L" and header[20] == 0x2F:
                return (
                    "webp",
                    1 + header[21] + ((header[22] & 0x3F) << 8),
                    1
                    + (header[22] >> 6)
                    + (header[23] << 2)
                    + ((header[24] & 0x0F) << 10),
                )
        if header.startswith(b"\xff\xd8"):
            offset = 2
            while offset + 9 <= len(header):
                if header[offset] != 0xFF:
                    offset += 1
                    continue
                marker = header[offset + 1]
                length = int.from_bytes(header[offset + 2 : offset + 4], "big")
                if marker in {
                    0xC0,
                    0xC1,
                    0xC2,
                    0xC3,
                    0xC5,
                    0xC6,
                    0xC7,
                    0xC9,
                    0xCA,
                    0xCB,
                    0xCD,
                    0xCE,
                    0xCF,
                }:
                    return (
                        "jpeg",
                        int.from_bytes(header[offset + 7 : offset + 9], "big"),
                        int.from_bytes(header[offset + 5 : offset + 7], "big"),
                    )
                if length < 2:
                    break
                offset += 2 + length
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
