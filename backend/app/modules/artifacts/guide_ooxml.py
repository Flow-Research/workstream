"""Shared bounded OPC/OOXML container security for isolated guide adapters."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import posixpath
from pathlib import PurePosixPath
from urllib.parse import urlsplit
import stat
import unicodedata
import zipfile

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.modules.artifacts.guide_formats import (
    OOXML_REQUIRED_MARKERS,
    GuideFormatLimits,
    zip_directory_facts,
)


_GUIDE_FORMAT_LIMITS = GuideFormatLimits()
MAXIMUM_ENTRIES = _GUIDE_FORMAT_LIMITS.maximum_entries
MAXIMUM_CENTRAL_DIRECTORY_BYTES = _GUIDE_FORMAT_LIMITS.maximum_central_directory_bytes
MAXIMUM_DECOMPRESSED_BYTES = _GUIDE_FORMAT_LIMITS.maximum_decompressed_bytes
MAXIMUM_COMPRESSION_RATIO = _GUIDE_FORMAT_LIMITS.maximum_compression_ratio
MAXIMUM_RELATIONSHIP_BYTES = 1024 * 1024
_FORMAT_ROOT = {"docx": "word", "pptx": "ppt", "xlsx": "xl"}
_REQUIRED = OOXML_REQUIRED_MARKERS
_EXECUTABLE_SUFFIXES = (
    ".bat", ".bin", ".cmd", ".com", ".dll", ".exe", ".jar", ".js", ".msi",
    ".ps1", ".py", ".scr", ".sh", ".vbs", ".zip", ".docm", ".pptm", ".xlsm",
)
_PASSIVE_PART_SUFFIXES = frozenset(
    {".xml", ".rels", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".emf", ".wmf", ".odttf"}
)
_COMMON_PREFIXES = ("_rels/", "docprops/", "customxml/")
_ACTIVE_METADATA_TOKENS = (
    "activex", "attachedtemplate", "altchunk", "control", "embeddedpackage",
    "oleobject", "vbaproject", "vba", "macroenabled",
)
_PASSIVE_CONTENT_TYPE_PREFIXES = (
    "application/vnd.openxmlformats-officedocument.",
    "application/vnd.openxmlformats-package.",
)
_PASSIVE_CONTENT_TYPES = frozenset({"application/xml", "text/xml"})
_PASSIVE_IMAGE_CONTENT_TYPES = {
    "image/bmp": frozenset({".bmp"}),
    "image/gif": frozenset({".gif"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/png": frozenset({".png"}),
    "image/tiff": frozenset({".tif", ".tiff"}),
    "image/x-emf": frozenset({".emf"}),
    "image/x-wmf": frozenset({".wmf"}),
}
_COMMON_RELATIONSHIPS = frozenset(
    {
        "core-properties", "custom-properties", "customxml", "customxmlprops",
        "extended-properties", "image", "officeDocument", "thumbnail", "theme",
    }
)
_FORMAT_RELATIONSHIPS = {
    "docx": frozenset(
        {
            "chart", "comments", "commentsExtended", "commentsIds", "diagramColors",
            "diagramData", "diagramLayout", "diagramQuickStyle", "endnotes", "fontTable",
            "footer", "footnotes", "glossaryDocument", "header", "hyperlink", "numbering",
            "people", "settings", "styles", "stylesWithEffects", "themeOverride", "webSettings",
        }
    ),
    "pptx": frozenset(
        {
            "chart", "commentAuthors", "comments", "diagramColors", "diagramData",
            "diagramLayout", "diagramQuickStyle", "handoutMaster", "hyperlink", "notesMaster",
            "notesSlide", "presProps", "slide", "slideLayout", "slideMaster", "tableStyles",
            "tags", "themeOverride", "viewProps",
        }
    ),
    "xlsx": frozenset(
        {
            "calcChain", "chart", "chartsheet", "comments", "dialogsheet", "drawing",
            "hyperlink", "person", "pivotCacheDefinition", "pivotCacheRecords", "pivotTable",
            "sharedStrings", "styles", "table", "threadedComment", "worksheet",
        }
    ),
}


@dataclass(frozen=True, slots=True)
class OoxmlPackageFacts:
    """Bounded structural facts safe to pass to a later format adapter."""

    detected_format: str
    entry_count: int
    decompressed_bytes: int


class OoxmlSecurityFailure(Exception):
    """Carry one bounded container-security outcome."""

    def __init__(self, status: str, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


def _directory_facts(payload: bytes) -> tuple[int, int]:
    try:
        entries, directory_bytes = zip_directory_facts(BytesIO(payload))
    except zipfile.BadZipFile as exc:
        message = str(exc)
        code = "ooxml_invalid_directory"
        if message == "multi-disk archive":
            code = "ooxml_multidisk"
        elif message == "zip64 archive is unsupported":
            code = "ooxml_zip64"
        raise OoxmlSecurityFailure("malformed", code) from exc
    if entries > MAXIMUM_ENTRIES or directory_bytes > MAXIMUM_CENTRAL_DIRECTORY_BYTES:
        raise OoxmlSecurityFailure("limit_exceeded", "ooxml_directory_limit")
    return entries, directory_bytes


def _normalized_name(value: str) -> str:
    if "\\" in value:
        raise OoxmlSecurityFailure("malformed", "ooxml_invalid_path")
    normalized = unicodedata.normalize("NFC", value)
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or (path.parts and ":" in path.parts[0])
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise OoxmlSecurityFailure("malformed", "ooxml_invalid_path")
    return normalized.rstrip("/")


def _part_is_allowed(name: str, *, detected_format: str) -> bool:
    lower = name.casefold()
    if lower == "[content_types].xml":
        return True
    if not (
        lower.startswith(_COMMON_PREFIXES)
        or lower.startswith(f"{_FORMAT_ROOT[detected_format]}/")
    ):
        return False
    return any(lower.endswith(suffix) for suffix in _PASSIVE_PART_SUFFIXES)


def _directory_is_allowed(name: str, *, detected_format: str) -> bool:
    lower = f"{name.casefold().rstrip('/')}/"
    allowed_roots = (*_COMMON_PREFIXES, f"{_FORMAT_ROOT[detected_format]}/")
    return any(lower == root or lower.startswith(root) for root in allowed_roots)


def _has_active_metadata(value: str) -> bool:
    folded = value.casefold()
    return any(token in folded for token in _ACTIVE_METADATA_TOKENS)


def _relationship_target_is_external(value: str, *, relationship_part: str) -> bool:
    target = value.strip()
    if "\\" in target or "\x00" in target:
        return True
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith("/"):
        return True
    source_directory = (
        "" if relationship_part == "_rels/.rels" else relationship_part.rsplit("/_rels/", 1)[0]
    )
    resolved = posixpath.normpath(posixpath.join(source_directory, parsed.path))
    return resolved == ".." or resolved.startswith("../")


def _content_type_is_passive(
    value: str,
    *,
    part_name: str,
    extension: str,
) -> bool:
    folded = value.strip().casefold()
    if not folded or _has_active_metadata(folded):
        return False
    if folded in _PASSIVE_IMAGE_CONTENT_TYPES:
        declared_suffix = PurePosixPath(part_name.casefold()).suffix
        default_suffix = f".{extension.casefold().lstrip('.')}" if extension else ""
        suffix = declared_suffix or default_suffix
        return suffix in _PASSIVE_IMAGE_CONTENT_TYPES[folded]
    return folded in _PASSIVE_CONTENT_TYPES or folded.startswith(
        _PASSIVE_CONTENT_TYPE_PREFIXES
    )


def _relationship_type_is_passive(value: str, *, detected_format: str) -> bool:
    kind = value.rstrip("/").rsplit("/", 1)[-1]
    return kind in (_COMMON_RELATIONSHIPS | _FORMAT_RELATIONSHIPS[detected_format])


def validate_ooxml(payload: bytes, *, detected_format: str) -> OoxmlPackageFacts:
    """Validate one exact classified OOXML package without extracting content."""
    if detected_format not in _FORMAT_ROOT:
        raise OoxmlSecurityFailure("ambiguous", "ooxml_classification_conflict")
    expected_entries, _ = _directory_facts(payload)
    try:
        archive = zipfile.ZipFile(BytesIO(payload))
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise OoxmlSecurityFailure("malformed", "ooxml_invalid_directory") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) != expected_entries:
            raise OoxmlSecurityFailure("malformed", "ooxml_directory_conflict")
        names: dict[str, zipfile.ZipInfo] = {}
        decompressed = 0
        for info in infos:
            name = _normalized_name(info.filename)
            folded = name.casefold()
            if folded in names:
                raise OoxmlSecurityFailure("malformed", "ooxml_duplicate_path")
            names[folded] = info
            lower = name.casefold()
            mode = info.external_attr >> 16
            if info.flag_bits & 0x1:
                raise OoxmlSecurityFailure("malformed", "ooxml_encrypted_entry")
            if stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise OoxmlSecurityFailure("malformed", "ooxml_special_entry")
            if info.is_dir():
                # Directory records are optional OPC metadata and may not impersonate parts.
                if name.casefold() in {
                    marker.casefold() for markers in _REQUIRED.values() for marker in markers
                }:
                    raise OoxmlSecurityFailure("malformed", "ooxml_required_marker_missing")
                if not _directory_is_allowed(name, detected_format=detected_format):
                    raise OoxmlSecurityFailure("malformed", "ooxml_unknown_package_part")
                continue
            if (
                lower.endswith(_EXECUTABLE_SUFFIXES)
                or "vbaproject" in lower
                or "/embeddings/" in f"/{lower}"
            ):
                raise OoxmlSecurityFailure("malformed", "ooxml_active_content")
            root = lower.split("/", 1)[0]
            if root in set(_FORMAT_ROOT.values()) - {_FORMAT_ROOT[detected_format]}:
                raise OoxmlSecurityFailure("ambiguous", "ooxml_classification_conflict")
            if not _part_is_allowed(name, detected_format=detected_format):
                raise OoxmlSecurityFailure("malformed", "ooxml_unknown_package_part")
            decompressed += info.file_size
            if decompressed > MAXIMUM_DECOMPRESSED_BYTES:
                raise OoxmlSecurityFailure("limit_exceeded", "ooxml_decompressed_limit")
            if info.file_size and (
                info.compress_size == 0
                or info.file_size > info.compress_size * MAXIMUM_COMPRESSION_RATIO
            ):
                raise OoxmlSecurityFailure("limit_exceeded", "ooxml_compression_ratio")
        canonical_names = frozenset(names)
        required = frozenset(name.casefold() for name in _REQUIRED[detected_format])
        if not required <= canonical_names:
            raise OoxmlSecurityFailure("malformed", "ooxml_required_marker_missing")
        other_markers = {
            marker.casefold()
            for format_name, markers in _REQUIRED.items()
            if format_name != detected_format
            for marker in markers - {"[Content_Types].xml", "_rels/.rels"}
        }
        if canonical_names & other_markers:
            raise OoxmlSecurityFailure("ambiguous", "ooxml_classification_conflict")

        for name, info in names.items():
            if info.is_dir():
                continue
            try:
                body = archive.read(info)
            except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
                raise OoxmlSecurityFailure("malformed", "ooxml_entry_read_failed") from exc
            if zipfile.is_zipfile(BytesIO(body)):
                raise OoxmlSecurityFailure("malformed", "ooxml_nested_archive")
            if not (name.endswith(".xml") or name.endswith(".rels")):
                continue
            if name.endswith(".rels") and len(body) > MAXIMUM_RELATIONSHIP_BYTES:
                raise OoxmlSecurityFailure("limit_exceeded", "ooxml_relationship_limit")
            if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
                raise OoxmlSecurityFailure("malformed", "ooxml_unsafe_xml")
            try:
                root = ElementTree.fromstring(
                    body,
                    forbid_dtd=True,
                    forbid_entities=True,
                    forbid_external=True,
                )
            except (DefusedXmlException, ElementTree.ParseError) as exc:
                raise OoxmlSecurityFailure("malformed", "ooxml_unsafe_xml") from exc
            if name == "[content_types].xml":
                if any(
                    not _content_type_is_passive(
                        str(element.attrib["ContentType"]),
                        part_name=str(element.attrib.get("PartName", "")),
                        extension=str(element.attrib.get("Extension", "")),
                    )
                    for element in root.iter()
                    if "ContentType" in element.attrib
                ):
                    raise OoxmlSecurityFailure("malformed", "ooxml_active_content")
            if name.endswith(".rels"):
                for element in root.iter():
                    target_mode = str(element.attrib.get("TargetMode", "")).strip().casefold()
                    target = str(element.attrib.get("Target", ""))
                    relationship_type = str(element.attrib.get("Type", ""))
                    if target_mode == "external" or _relationship_target_is_external(
                        target,
                        relationship_part=name,
                    ):
                        raise OoxmlSecurityFailure("malformed", "ooxml_external_relationship")
                    if relationship_type and not _relationship_type_is_passive(
                        relationship_type,
                        detected_format=detected_format,
                    ):
                        raise OoxmlSecurityFailure("malformed", "ooxml_active_content")
    return OoxmlPackageFacts(detected_format, len(infos), decompressed)
