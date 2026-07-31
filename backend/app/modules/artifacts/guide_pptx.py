"""Deterministic bounded PPTX extraction after shared OOXML validation."""

from __future__ import annotations

from collections.abc import Callable
import codecs
from dataclasses import dataclass
from io import BytesIO
import json
import posixpath
from pathlib import PurePosixPath
from xml.etree import ElementTree
import zipfile


# Preload the ZIP filename codec before the isolated child installs seccomp.
codecs.lookup("cp437")
MAXIMUM_OUTPUT_BYTES = 4 * 1024 * 1024
MAXIMUM_SLIDES = 300
MAXIMUM_NESTING_DEPTH = 64
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_STRICT_R_NS = "http://purl.oclc.org/ooxml/officeDocument/relationships"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_PRESENTATION_TAG = f"{{{_P_NS}}}presentation"
_SLIDE_TAG = f"{{{_P_NS}}}sld"
_NOTES_TAG = f"{{{_P_NS}}}notes"
_SLIDE_ID_LIST_TAG = f"{{{_P_NS}}}sldIdLst"
_SLIDE_ID_TAG = f"{{{_P_NS}}}sldId"
_RELATIONSHIP_ID_ATTRIBUTE = f"{{{_R_NS}}}id"
_STRICT_RELATIONSHIP_ID_ATTRIBUTE = f"{{{_STRICT_R_NS}}}id"
_RELATIONSHIP_TAG = f"{{{_REL_NS}}}Relationship"
_RELATIONSHIPS_TAG = f"{{{_REL_NS}}}Relationships"
_PARAGRAPH_TAG = f"{{{_A_NS}}}p"
_TEXT_TAG = f"{{{_A_NS}}}t"
_TAB_TAG = f"{{{_A_NS}}}tab"
_BREAK_TAG = f"{{{_A_NS}}}br"
_SHAPE_TAG = f"{{{_P_NS}}}sp"
_NON_VISUAL_SHAPE_PROPERTIES_TAG = f"{{{_P_NS}}}nvSpPr"
_NON_VISUAL_PROPERTIES_TAG = f"{{{_P_NS}}}nvPr"
_COMMON_SLIDE_DATA_TAG = f"{{{_P_NS}}}cSld"
_SHAPE_TREE_TAG = f"{{{_P_NS}}}spTree"
_TEXT_BODY_TAG = f"{{{_P_NS}}}txBody"
_PLACEHOLDER_TAG = f"{{{_P_NS}}}ph"
_NON_TEXT_TAGS = frozenset(
    {
        f"{{{_P_NS}}}pic",
        f"{{{_P_NS}}}contentPart",
        f"{{{_P_NS}}}media",
        f"{{{_P_NS}}}video",
        f"{{{_P_NS}}}audio",
    }
)
_EMBEDDED_TAGS = frozenset({f"{{{_P_NS}}}oleObj", f"{{{_P_NS}}}externalData"})
_GRAPHIC_FRAME_TAG = f"{{{_P_NS}}}graphicFrame"
_TABLE_TAG = f"{{{_A_NS}}}tbl"
_NON_CONTENT_NOTE_PLACEHOLDERS = frozenset({"hdr", "ftr", "dt", "sldnum", "sldimg"})
_TRANSITIONAL_BASE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_STRICT_BASE = "http://purl.oclc.org/ooxml/officeDocument/relationships"
_RELATIONSHIP_FAMILIES = {
    _TRANSITIONAL_BASE: {
        "slide": f"{_TRANSITIONAL_BASE}/slide",
        "notesSlide": f"{_TRANSITIONAL_BASE}/notesSlide",
    },
    _STRICT_BASE: {
        "slide": f"{_STRICT_BASE}/slide",
        "notesSlide": f"{_STRICT_BASE}/notesSlide",
    },
}
_PPTX_OMISSION_KEYS = (
    "masters",
    "comments",
    "hidden_metadata",
    "non_text_objects",
    "embedded_objects",
)


@dataclass(frozen=True, slots=True)
class PptxExtraction:
    """One canonical PPTX result and its fixed bounded omission facts."""

    canonical_output: str
    omission_facts: dict[str, bool]


class PptxExtractionFailure(Exception):
    """Carry one bounded PPTX extraction outcome."""

    def __init__(self, status: str, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


@dataclass(frozen=True, slots=True)
class _Relationship:
    relationship_type: str
    target: str


def _new_omissions(names: frozenset[str]) -> dict[str, bool]:
    return {
        "truncated": False,
        "omitted": False,
        "masters": any(
            name.startswith(("ppt/slidemasters/", "ppt/notesmasters/", "ppt/handoutmasters/"))
            for name in names
        ),
        "comments": any(name.startswith(("ppt/comments/", "ppt/commentauthors")) for name in names),
        "hidden_metadata": any(name.startswith(("docprops/", "customxml/")) for name in names),
        "non_text_objects": False,
        "embedded_objects": False,
    }


def _xml(payload: bytes, *, code: str, root_tag: str) -> ElementTree.Element:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise PptxExtractionFailure("malformed", code) from exc
    if root.tag != root_tag:
        raise PptxExtractionFailure("malformed", code)
    return root


def _relationship_family(relationship_type: str, kind: str) -> str | None:
    for family, types in _RELATIONSHIP_FAMILIES.items():
        if relationship_type == types[kind]:
            return family
    return None


def _source_for_relationship_part(name: str) -> str:
    path = PurePosixPath(name)
    if len(path.parts) < 3 or path.parts[-2] != "_rels" or not path.name.endswith(".rels"):
        raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
    return (path.parent.parent / path.name.removesuffix(".rels")).as_posix()


def _relationship_target(part_name: str, target: str) -> str:
    if not target or target.startswith(("/", "\\")) or "\\" in target:
        raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
    source = _source_for_relationship_part(part_name)
    normalized = posixpath.normpath(posixpath.join(posixpath.dirname(source), target))
    if normalized.startswith("../") or not normalized.startswith("ppt/"):
        raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
    return normalized.casefold()


def _relationships(payload: bytes, *, part_name: str) -> dict[str, _Relationship]:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise PptxExtractionFailure("malformed", "pptx_relationship_conflict") from exc
    if root.tag != _RELATIONSHIPS_TAG:
        raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
    relationships: dict[str, _Relationship] = {}
    for element in root:
        if element.tag != _RELATIONSHIP_TAG:
            raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
        relationship_id = element.get("Id")
        relationship_type = element.get("Type")
        target = element.get("Target")
        if (
            not relationship_id
            or not relationship_type
            or not target
            or relationship_id in relationships
        ):
            raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
        relationships[relationship_id] = _Relationship(
            relationship_type=relationship_type,
            target=_relationship_target(part_name, target),
        )
    return relationships


def _paragraph_text(paragraph: ElementTree.Element, depth: int) -> str:
    values: list[str] = []

    def walk(element: ElementTree.Element, depth: int) -> None:
        if depth > MAXIMUM_NESTING_DEPTH:
            raise PptxExtractionFailure("malformed", "pptx_nesting_limit")
        if element.tag == _TEXT_TAG:
            values.append(element.text or "")
            return
        if element.tag == _TAB_TAG:
            values.append("\t")
            return
        if element.tag == _BREAK_TAG:
            values.append("\n")
            return
        for child in element:
            walk(child, depth + 1)

    walk(paragraph, depth)
    return "".join(values)


def _paragraphs(
    root: ElementTree.Element,
    omissions: dict[str, bool],
    *,
    notes: bool,
) -> list[str]:
    paragraphs: list[str] = []

    shape_tree = root.find(f"./{_COMMON_SLIDE_DATA_TAG}/{_SHAPE_TREE_TAG}")
    if shape_tree is None:
        return paragraphs

    def record_metadata(element: ElementTree.Element) -> None:
        if any(key in element.attrib for key in ("descr", "title")) or str(
            element.get("show", "1")
        ).casefold() in {"0", "false", "off", "no"}:
            omissions["hidden_metadata"] = True

    def scan_omissions(element: ElementTree.Element, depth: int) -> None:
        if depth > MAXIMUM_NESTING_DEPTH:
            raise PptxExtractionFailure("malformed", "pptx_nesting_limit")
        record_metadata(element)
        if element.tag in _NON_TEXT_TAGS:
            omissions["non_text_objects"] = True
        elif element.tag in _EMBEDDED_TAGS:
            omissions["embedded_objects"] = True
        for child in element:
            scan_omissions(child, depth + 1)

    def walk_graphic_frame(element: ElementTree.Element, depth: int) -> bool:
        if depth > MAXIMUM_NESTING_DEPTH:
            raise PptxExtractionFailure("malformed", "pptx_nesting_limit")
        record_metadata(element)
        if element.tag == _TABLE_TAG:
            walk(element, depth, text_allowed=True)
            return True
        found_table = False
        for child in element:
            found_table = walk_graphic_frame(child, depth + 1) or found_table
        return found_table

    def walk(element: ElementTree.Element, depth: int, *, text_allowed: bool = False) -> None:
        if depth > MAXIMUM_NESTING_DEPTH:
            raise PptxExtractionFailure("malformed", "pptx_nesting_limit")
        record_metadata(element)
        if element.tag in _NON_TEXT_TAGS:
            omissions["non_text_objects"] = True
            scan_omissions(element, depth)
            return
        if element.tag in _EMBEDDED_TAGS:
            omissions["embedded_objects"] = True
            scan_omissions(element, depth)
            return
        if element.tag == _SHAPE_TAG and notes:
            placeholder = element.find(
                f"./{_NON_VISUAL_SHAPE_PROPERTIES_TAG}/"
                f"{_NON_VISUAL_PROPERTIES_TAG}/{_PLACEHOLDER_TAG}"
            )
            placeholder_type = (
                str(placeholder.get("type", "body")).casefold()
                if placeholder is not None
                else "body"
            )
            if placeholder_type in _NON_CONTENT_NOTE_PLACEHOLDERS:
                omissions["hidden_metadata"] = True
                scan_omissions(element, depth)
                return
        if element.tag == _GRAPHIC_FRAME_TAG:
            if not walk_graphic_frame(element, depth):
                omissions["non_text_objects"] = True
            return
        if element.tag == _TEXT_BODY_TAG:
            text_allowed = True
        if element.tag == _PARAGRAPH_TAG and text_allowed:
            paragraphs.append(_paragraph_text(element, depth))
            return
        for child in element:
            walk(child, depth + 1, text_allowed=text_allowed)

    walk(shape_tree, 0)
    return paragraphs


def _part_names(names: frozenset[str], prefix: str) -> frozenset[str]:
    return frozenset(
        name
        for name in names
        if name.startswith(prefix) and name.endswith(".xml") and "/_rels/" not in name
    )


def _ordered_parts(
    archive: zipfile.ZipFile,
    stored: dict[str, str],
    presentation: ElementTree.Element,
    *,
    names: frozenset[str],
    omissions: dict[str, bool],
) -> tuple[list[tuple[str, str | None]], str]:
    relationship_name = "ppt/_rels/presentation.xml.rels"
    try:
        presentation_relationships = _relationships(
            archive.read(stored[relationship_name]),
            part_name=relationship_name,
        )
    except KeyError as exc:
        raise PptxExtractionFailure("malformed", "pptx_relationship_conflict") from exc
    slide_list = presentation.find(_SLIDE_ID_LIST_TAG)
    slide_ids = [] if slide_list is None else list(slide_list.findall(_SLIDE_ID_TAG))
    if len(slide_ids) > MAXIMUM_SLIDES:
        raise PptxExtractionFailure("limit_exceeded", "pptx_slide_limit")
    ordered_slides: list[str] = []
    family: str | None = None
    seen_ids: set[str] = set()
    seen_slide_ids: set[str] = set()
    for slide_id in slide_ids:
        canonical_slide_id = slide_id.get("id")
        if not canonical_slide_id or canonical_slide_id in seen_slide_ids:
            raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
        seen_slide_ids.add(canonical_slide_id)
        relationship_ids = tuple(
            value
            for attribute in (_RELATIONSHIP_ID_ATTRIBUTE, _STRICT_RELATIONSHIP_ID_ATTRIBUTE)
            if (value := slide_id.get(attribute)) is not None
        )
        if len(relationship_ids) != 1:
            raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
        relationship_id = relationship_ids[0]
        if not relationship_id or relationship_id in seen_ids:
            raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
        seen_ids.add(relationship_id)
        relationship = presentation_relationships.get(relationship_id)
        if relationship is None:
            raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
        current_family = _relationship_family(relationship.relationship_type, "slide")
        if current_family is None or (family is not None and family != current_family):
            raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
        family = current_family
        if relationship.target in ordered_slides or relationship.target not in stored:
            raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
        ordered_slides.append(relationship.target)
    if frozenset(ordered_slides) != _part_names(names, "ppt/slides/"):
        raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
    resolved: list[tuple[str, str | None]] = []
    owned_notes: set[str] = set()
    for slide_name in ordered_slides:
        path = PurePosixPath(slide_name)
        rel_name = (path.parent / "_rels" / f"{path.name}.rels").as_posix()
        notes_name = None
        if rel_name in stored:
            slide_relationships = _relationships(
                archive.read(stored[rel_name]),
                part_name=rel_name,
            )
            notes = [
                relationship
                for relationship in slide_relationships.values()
                if _relationship_family(relationship.relationship_type, "notesSlide") is not None
            ]
            if len(notes) > 1:
                raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
            if notes:
                notes_relationship = notes[0]
                notes_family = _relationship_family(
                    notes_relationship.relationship_type, "notesSlide"
                )
                if notes_family != family:
                    raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
                notes_name = notes_relationship.target
                if notes_name not in stored or notes_name in owned_notes:
                    raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
                owned_notes.add(notes_name)
        resolved.append((slide_name, notes_name))
    if frozenset(owned_notes) != _part_names(names, "ppt/notesslides/"):
        raise PptxExtractionFailure("malformed", "pptx_relationship_conflict")
    return resolved, family or _TRANSITIONAL_BASE


def _canonical_slides(
    archive: zipfile.ZipFile,
    stored: dict[str, str],
    parts: list[tuple[str, str | None]],
    omissions: dict[str, bool],
    *,
    maximum_output_bytes: int,
) -> str:
    serialized: list[str] = []
    byte_count = len(b'{"slides":[]}')
    for number, (slide_name, notes_name) in enumerate(parts, 1):
        slide = _xml(
            archive.read(stored[slide_name]),
            code="pptx_invalid_slide_xml",
            root_tag=_SLIDE_TAG,
        )
        if str(slide.get("show", "1")).casefold() in {"0", "false", "off", "no"}:
            omissions["hidden_metadata"] = True
        notes: list[str] = []
        if notes_name is not None:
            notes_root = _xml(
                archive.read(stored[notes_name]),
                code="pptx_invalid_notes_xml",
                root_tag=_NOTES_TAG,
            )
            notes = _paragraphs(notes_root, omissions, notes=True)
        entry = {
            "notes": notes,
            "number": number,
            "text": _paragraphs(slide, omissions, notes=False),
        }
        encoded = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        projected = byte_count + len(encoded.encode("utf-8")) + (1 if serialized else 0)
        if projected > maximum_output_bytes:
            raise PptxExtractionFailure("limit_exceeded", "output_limit")
        serialized.append(encoded)
        byte_count = projected
    return '{"slides":[' + ",".join(serialized) + "]}"


def extract_pptx(
    payload: bytes,
    *,
    validate_ooxml: Callable[[bytes], object],
    maximum_output_bytes: int = MAXIMUM_OUTPUT_BYTES,
) -> PptxExtraction:
    """Validate and extract one exact PPTX package without partial output."""
    try:
        validate_ooxml(payload)
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            stored = {info.filename.casefold(): info.filename for info in archive.infolist()}
            names = frozenset(stored)
            presentation = _xml(
                archive.read(stored["ppt/presentation.xml"]),
                code="pptx_invalid_presentation_xml",
                root_tag=_PRESENTATION_TAG,
            )
            omissions = _new_omissions(names)
            parts, _family = _ordered_parts(
                archive,
                stored,
                presentation,
                names=names,
                omissions=omissions,
            )
            output = _canonical_slides(
                archive,
                stored,
                parts,
                omissions,
                maximum_output_bytes=maximum_output_bytes,
            )
    except PptxExtractionFailure:
        raise
    except KeyError as exc:
        raise PptxExtractionFailure("malformed", "pptx_presentation_unavailable") from exc
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        raise PptxExtractionFailure("malformed", "pptx_presentation_unavailable") from exc
    omissions["omitted"] = any(omissions[key] for key in _PPTX_OMISSION_KEYS)
    return PptxExtraction(canonical_output=output, omission_facts=omissions)
