"""Deterministic bounded DOCX extraction after shared OOXML validation."""

from __future__ import annotations

import codecs
from dataclasses import dataclass
from io import BytesIO
import json
from xml.etree import ElementTree
import zipfile
from collections.abc import Callable


# Preload the ZIP filename codec before the isolated worker installs seccomp.
codecs.lookup("cp437")
MAXIMUM_OUTPUT_BYTES = 4 * 1024 * 1024
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_BODY_TAG = f"{{{_WORD_NS}}}body"
_PARAGRAPH_TAG = f"{{{_WORD_NS}}}p"
_TABLE_TAG = f"{{{_WORD_NS}}}tbl"
_ROW_TAG = f"{{{_WORD_NS}}}tr"
_CELL_TAG = f"{{{_WORD_NS}}}tc"
_RUN_TAG = f"{{{_WORD_NS}}}r"
_RUN_PROPERTIES_TAG = f"{{{_WORD_NS}}}rPr"
_RUN_STYLE_TAG = f"{{{_WORD_NS}}}rStyle"
_PARAGRAPH_PROPERTIES_TAG = f"{{{_WORD_NS}}}pPr"
_PARAGRAPH_STYLE_TAG = f"{{{_WORD_NS}}}pStyle"
_STYLE_TAG = f"{{{_WORD_NS}}}style"
_BASED_ON_TAG = f"{{{_WORD_NS}}}basedOn"
_VALUE_ATTRIBUTE = f"{{{_WORD_NS}}}val"
_STYLE_ID_ATTRIBUTE = f"{{{_WORD_NS}}}styleId"
_STYLE_TYPE_ATTRIBUTE = f"{{{_WORD_NS}}}type"
_DOC_DEFAULTS_TAG = f"{{{_WORD_NS}}}docDefaults"
_RUN_PROPERTIES_DEFAULT_TAG = f"{{{_WORD_NS}}}rPrDefault"
_VANISH_TAG = f"{{{_WORD_NS}}}vanish"
_TEXT_TAG = f"{{{_WORD_NS}}}t"
_DELETION_TEXT_TAG = f"{{{_WORD_NS}}}delText"
_DELETION_TAG = f"{{{_WORD_NS}}}del"
_DELETION_CONTAINER_TAGS = frozenset({_DELETION_TAG, f"{{{_WORD_NS}}}moveFrom"})
_TAB_TAG = f"{{{_WORD_NS}}}tab"
_BREAK_TAGS = frozenset({f"{{{_WORD_NS}}}br", f"{{{_WORD_NS}}}cr"})
_FIELD_INSTRUCTION_TAG = f"{{{_WORD_NS}}}instrText"
_SIMPLE_FIELD_TAG = f"{{{_WORD_NS}}}fldSimple"
_FIELD_INSTRUCTION_ATTRIBUTE = f"{{{_WORD_NS}}}instr"
_COMMENT_TAGS = frozenset(
    {
        f"{{{_WORD_NS}}}commentRangeStart",
        f"{{{_WORD_NS}}}commentRangeEnd",
        f"{{{_WORD_NS}}}commentReference",
    }
)
_EMBEDDED_BODY_TAGS = frozenset(
    {
        f"{{{_WORD_NS}}}drawing",
        f"{{{_WORD_NS}}}object",
        f"{{{_WORD_NS}}}pict",
    }
)
_DOCX_OMISSION_KEYS = (
    "headers",
    "footers",
    "comments",
    "tracked_deletions",
    "embedded_objects",
    "hidden_text",
    "field_instructions",
)


@dataclass(frozen=True, slots=True)
class DocxExtraction:
    """One canonical DOCX result and its fixed bounded omission facts."""

    canonical_output: str
    omission_facts: dict[str, bool]


@dataclass(frozen=True, slots=True)
class _HiddenStyleFacts:
    default_hidden: bool
    run_styles: frozenset[str]
    paragraph_styles: frozenset[str]


class DocxExtractionFailure(Exception):
    """Carry one bounded DOCX extraction outcome."""

    def __init__(self, status: str, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


def _new_omissions(names: frozenset[str]) -> dict[str, bool]:
    facts = {
        "truncated": False,
        "omitted": False,
        "headers": any(name.startswith("word/header") and name.endswith(".xml") for name in names),
        "footers": any(name.startswith("word/footer") and name.endswith(".xml") for name in names),
        "comments": "word/comments.xml" in names,
        "tracked_deletions": False,
        "embedded_objects": False,
        "hidden_text": False,
        "field_instructions": False,
    }
    return facts


def _hidden_styles(styles: bytes | None) -> _HiddenStyleFacts:
    if styles is None:
        return _HiddenStyleFacts(False, frozenset(), frozenset())
    try:
        root = ElementTree.fromstring(styles)
    except ElementTree.ParseError as exc:
        raise DocxExtractionFailure("malformed", "docx_invalid_styles_xml") from exc
    hidden_by_type: dict[str, set[str]] = {"character": set(), "paragraph": set()}
    parents_by_type: dict[str, dict[str, str]] = {"character": {}, "paragraph": {}}
    for style in root.findall(_STYLE_TAG):
        style_id = style.get(_STYLE_ID_ATTRIBUTE)
        style_type = style.get(_STYLE_TYPE_ATTRIBUTE)
        if not style_id or style_type not in hidden_by_type:
            continue
        properties = style.find(_RUN_PROPERTIES_TAG)
        if properties is not None and properties.find(_VANISH_TAG) is not None:
            hidden_by_type[style_type].add(style_id)
        based_on = style.find(_BASED_ON_TAG)
        parent_id = based_on.get(_VALUE_ATTRIBUTE) if based_on is not None else None
        if parent_id:
            parents_by_type[style_type][style_id] = parent_id
    for style_type, hidden in hidden_by_type.items():
        changed = True
        while changed:
            inherited = {
                style_id
                for style_id, parent in parents_by_type[style_type].items()
                if parent in hidden
            }
            changed = not inherited.issubset(hidden)
            hidden.update(inherited)
    defaults = root.find(_DOC_DEFAULTS_TAG)
    run_defaults = defaults.find(_RUN_PROPERTIES_DEFAULT_TAG) if defaults is not None else None
    default_properties = (
        run_defaults.find(_RUN_PROPERTIES_TAG) if run_defaults is not None else None
    )
    return _HiddenStyleFacts(
        default_hidden=(
            default_properties is not None and default_properties.find(_VANISH_TAG) is not None
        ),
        run_styles=frozenset(hidden_by_type["character"]),
        paragraph_styles=frozenset(hidden_by_type["paragraph"]),
    )


def _paragraph_text(
    paragraph: ElementTree.Element,
    omissions: dict[str, bool],
    hidden_styles: _HiddenStyleFacts,
) -> str:
    paragraph_properties = paragraph.find(_PARAGRAPH_PROPERTIES_TAG)
    paragraph_style = (
        paragraph_properties.find(_PARAGRAPH_STYLE_TAG)
        if paragraph_properties is not None
        else None
    )
    paragraph_style_id = (
        paragraph_style.get(_VALUE_ATTRIBUTE) if paragraph_style is not None else None
    )
    if paragraph_style_id in hidden_styles.paragraph_styles:
        omissions["hidden_text"] = True
        return ""
    values: list[str] = []

    def walk(element: ElementTree.Element) -> None:
        if element.tag in _DELETION_CONTAINER_TAGS:
            omissions["tracked_deletions"] = True
            return
        if element.tag == _RUN_TAG:
            properties = element.find(_RUN_PROPERTIES_TAG)
            if properties is not None:
                style = properties.find(_RUN_STYLE_TAG)
                style_id = style.get(_VALUE_ATTRIBUTE) if style is not None else None
                if (
                    properties.find(_VANISH_TAG) is not None
                    or style_id in hidden_styles.run_styles
                    or hidden_styles.default_hidden
                ):
                    omissions["hidden_text"] = True
                    return
            elif hidden_styles.default_hidden:
                omissions["hidden_text"] = True
                return
        if element.tag == _TEXT_TAG:
            values.append(element.text or "")
            return
        if element.tag == _DELETION_TEXT_TAG:
            omissions["tracked_deletions"] = True
            return
        if element.tag == _TAB_TAG:
            values.append("\t")
            return
        if element.tag in _BREAK_TAGS:
            values.append("\n")
            return
        if element.tag == _FIELD_INSTRUCTION_TAG:
            omissions["field_instructions"] = True
            return
        if element.tag == _SIMPLE_FIELD_TAG and element.get(_FIELD_INSTRUCTION_ATTRIBUTE):
            omissions["field_instructions"] = True
        if element.tag in _COMMENT_TAGS:
            omissions["comments"] = True
            return
        if element.tag in _EMBEDDED_BODY_TAGS:
            omissions["embedded_objects"] = True
            return
        for child in element:
            walk(child)

    walk(paragraph)
    return "".join(values)


def _contained_blocks(
    container: ElementTree.Element,
    omissions: dict[str, bool],
):
    for child in container:
        if child.tag in _DELETION_CONTAINER_TAGS:
            omissions["tracked_deletions"] = True
        elif child.tag in {_PARAGRAPH_TAG, _TABLE_TAG}:
            yield child
        elif child.tag in _EMBEDDED_BODY_TAGS:
            omissions["embedded_objects"] = True
        else:
            yield from _contained_blocks(child, omissions)


def _table_text(
    table: ElementTree.Element,
    omissions: dict[str, bool],
    hidden_styles: _HiddenStyleFacts,
) -> str:
    rows: list[str] = []
    for row in table.findall(_ROW_TAG):
        cells: list[str] = []
        for cell in row.findall(_CELL_TAG):
            cell_parts: list[str] = []
            for child in _contained_blocks(cell, omissions):
                if child.tag == _PARAGRAPH_TAG:
                    cell_parts.append(_paragraph_text(child, omissions, hidden_styles))
                elif child.tag == _TABLE_TAG:
                    cell_parts.append(_table_text(child, omissions, hidden_styles))
            cells.append("\n".join(cell_parts))
        rows.append("\t".join(cells))
    return "\n".join(rows)


def _canonical_blocks(
    body: ElementTree.Element,
    omissions: dict[str, bool],
    hidden_styles: _HiddenStyleFacts,
    *,
    maximum_output_bytes: int,
) -> str:
    serialized: list[str] = []
    byte_count = len(b'{"blocks":[]}')
    for child in _contained_blocks(body, omissions):
        block: dict[str, str] | None = None
        if child.tag == _PARAGRAPH_TAG:
            block = {
                "type": "paragraph",
                "text": _paragraph_text(child, omissions, hidden_styles),
            }
        elif child.tag == _TABLE_TAG:
            block = {"type": "table", "text": _table_text(child, omissions, hidden_styles)}
        if block is None:
            continue
        encoded = json.dumps(block, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        projected = byte_count + len(encoded.encode("utf-8")) + (1 if serialized else 0)
        if projected > maximum_output_bytes:
            raise DocxExtractionFailure("limit_exceeded", "output_limit")
        serialized.append(encoded)
        byte_count = projected
    return '{"blocks":[' + ",".join(serialized) + "]}"


def extract_docx(
    payload: bytes,
    *,
    validate_ooxml: Callable[[bytes], object],
    maximum_output_bytes: int = MAXIMUM_OUTPUT_BYTES,
) -> DocxExtraction:
    """Validate and extract one exact DOCX package without partial output."""
    try:
        validate_ooxml(payload)
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            names = frozenset(info.filename.casefold() for info in archive.infolist())
            document = archive.read("word/document.xml")
            styles = archive.read("word/styles.xml") if "word/styles.xml" in names else None
    except (KeyError, OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        raise DocxExtractionFailure("malformed", "docx_document_unavailable") from exc
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as exc:
        raise DocxExtractionFailure("malformed", "docx_invalid_document_xml") from exc
    body = root.find(_BODY_TAG)
    if body is None:
        raise DocxExtractionFailure("malformed", "docx_body_missing")
    omissions = _new_omissions(names)
    hidden_styles = _hidden_styles(styles)
    output = _canonical_blocks(
        body,
        omissions,
        hidden_styles,
        maximum_output_bytes=maximum_output_bytes,
    )
    omissions["omitted"] = any(omissions[key] for key in _DOCX_OMISSION_KEYS)
    return DocxExtraction(canonical_output=output, omission_facts=omissions)
