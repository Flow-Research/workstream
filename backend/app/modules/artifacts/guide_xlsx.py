"""Deterministic bounded XLSX extraction after shared OOXML validation."""

from __future__ import annotations

from collections.abc import Callable
import codecs
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
import json
import posixpath
import re
from xml.etree import ElementTree
import zipfile


codecs.lookup("cp437")
MAXIMUM_WORKSHEETS = 100
MAXIMUM_ROWS = 100_000
MAXIMUM_CELLS = 1_000_000
MAXIMUM_CELL_CHARACTERS = 32_768
MAXIMUM_NESTING_DEPTH = 64
MAXIMUM_OUTPUT_BYTES = 4 * 1024 * 1024
_TRANSITIONAL_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_STRICT_MAIN = "http://purl.oclc.org/ooxml/spreadsheetml/main"
_TRANSITIONAL_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_STRICT_R = "http://purl.oclc.org/ooxml/officeDocument/relationships"
_PACKAGE_R = "http://schemas.openxmlformats.org/package/2006/relationships"
_FAMILIES = {
    _TRANSITIONAL_MAIN: _TRANSITIONAL_R,
    _STRICT_MAIN: _STRICT_R,
}
_NUMBER = re.compile(r"-?[0-9]+(?:\.[0-9]+)?(?:[Ee][+-]?[0-9]+)?\Z")
_DECIMAL = re.compile(r"[0-9]+\Z")
_CELL = re.compile(r"([A-Za-z]+)([1-9][0-9]*)\Z")
_DATE = re.compile(
    r"(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|"
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2}))\Z"
)


@dataclass(frozen=True, slots=True)
class XlsxExtraction:
    canonical_output: str
    omission_facts: dict[str, bool]


class XlsxExtractionFailure(Exception):
    def __init__(self, status: str, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


@dataclass(slots=True)
class _CanonicalBudget:
    """Bound semantic accumulation by bytes known to appear in canonical JSON."""

    used: int = 0

    def claim(self, value: object) -> None:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        self.used += len(encoded)
        if self.used > MAXIMUM_OUTPUT_BYTES:
            _fail("output_limit", "limit_exceeded")


def _fail(code: str, status: str = "malformed") -> None:
    raise XlsxExtractionFailure(status, code)


def _xml(
    payload: bytes,
    expected: str,
    code: str,
    *,
    spreadsheet_family: bool = False,
) -> ElementTree.Element:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise XlsxExtractionFailure("malformed", code) from exc
    if root.tag != expected:
        if spreadsheet_family and root.tag.startswith("{"):
            namespace, local = root.tag[1:].split("}", 1)
            expected_local = expected.rsplit("}", 1)[-1]
            if namespace in _FAMILIES and local == expected_local:
                _fail("xlsx_namespace_conflict")
        _fail(code)
    stack = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        if depth > MAXIMUM_NESTING_DEPTH:
            _fail("xlsx_nesting_limit")
        stack.extend((child, depth + 1) for child in element)
    return root


def _column_number(letters: str) -> int:
    result = 0
    for character in letters.upper():
        result = result * 26 + ord(character) - 64
    return result


def _coordinate(value: str) -> tuple[str, int, int]:
    match = _CELL.fullmatch(value)
    if match is None:
        _fail("xlsx_invalid_cell")
    column = _column_number(match.group(1))
    row = int(match.group(2))
    if column > 16_384 or row > 1_048_576:
        _fail("xlsx_invalid_cell")
    return f"{match.group(1).upper()}{row}", row, column


def _relationship_target(target: str) -> str:
    if not target or target.startswith(("/", "\\")) or "\\" in target:
        _fail("xlsx_relationship_conflict")
    resolved = posixpath.normpath(posixpath.join("xl", target))
    if resolved.startswith("../") or not resolved.startswith("xl/"):
        _fail("xlsx_relationship_conflict")
    return resolved.casefold()


def _relationships(payload: bytes) -> dict[str, tuple[str, str]]:
    root = _xml(payload, f"{{{_PACKAGE_R}}}Relationships", "xlsx_relationship_conflict")
    result: dict[str, tuple[str, str]] = {}
    targets: set[str] = set()
    for child in root:
        if child.tag != f"{{{_PACKAGE_R}}}Relationship":
            _fail("xlsx_relationship_conflict")
        identity, kind, target = child.get("Id"), child.get("Type"), child.get("Target")
        if (
            set(child.attrib) != {"Id", "Type", "Target"}
            or not identity
            or not kind
            or not target
            or identity in result
        ):
            _fail("xlsx_relationship_conflict")
        normalized_target = _relationship_target(target)
        if normalized_target in targets:
            _fail("xlsx_relationship_conflict")
        targets.add(normalized_target)
        result[identity] = (kind, normalized_target)
    return result


def _rich_text(element: ElementTree.Element, ns: str) -> str:
    phonetic = {f"{{{ns}}}rPh", f"{{{ns}}}phoneticPr"}
    values: list[str] = []

    def walk(candidate: ElementTree.Element) -> None:
        if candidate.tag in phonetic:
            return
        if candidate.tag == f"{{{ns}}}t":
            values.append(candidate.text or "")
        for child in candidate:
            walk(child)

    walk(element)
    return "".join(values)


def _shared_strings(payload: bytes, ns: str) -> tuple[list[str], bool]:
    root = _xml(
        payload,
        f"{{{ns}}}sst",
        "xlsx_invalid_shared_strings_xml",
        spreadsheet_family=True,
    )
    values: list[str] = []
    for child in root:
        if child.tag != f"{{{ns}}}si":
            _fail("xlsx_invalid_shared_strings_xml")
        values.append(_rich_text(child, ns))
    phonetic = any(
        element.tag in {f"{{{ns}}}rPh", f"{{{ns}}}phoneticPr"} for element in root.iter()
    )
    return values, phonetic


def _formula(cell: ElementTree.Element, ns: str) -> str | None:
    formulas = [child for child in cell if child.tag == f"{{{ns}}}f"]
    if len(formulas) > 1:
        _fail("xlsx_invalid_cell")
    if not formulas:
        return None
    formula = formulas[0]
    if list(formula) or set(formula.attrib) - {"t"}:
        _fail("xlsx_formula_unsupported", "unsupported")
    if formula.get("t") not in {None, "normal"} or not (formula.text or ""):
        _fail("xlsx_formula_unsupported", "unsupported")
    return formula.text


def _date_value(value: str) -> str:
    if not _DATE.fullmatch(value):
        _fail("xlsx_invalid_cell")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise XlsxExtractionFailure("malformed", "xlsx_invalid_cell") from exc
    return value


def _cell_value(
    cell: ElementTree.Element,
    ns: str,
    shared: list[str] | None,
    formula: str | None,
) -> dict[str, str] | None:
    children = list(cell)
    allowed = {f"{{{ns}}}f", f"{{{ns}}}v", f"{{{ns}}}is"}
    if any(child.tag not in allowed for child in children):
        _fail("xlsx_invalid_cell")
    values = [child for child in children if child.tag == f"{{{ns}}}v"]
    inline = [child for child in children if child.tag == f"{{{ns}}}is"]
    if len(values) > 1 or len(inline) > 1:
        _fail("xlsx_invalid_cell")
    value = values[0].text or "" if values else None
    cell_type = cell.get("t")
    if cell_type in {None, "n"}:
        if inline or (value is not None and not _NUMBER.fullmatch(value)):
            _fail("xlsx_invalid_cell")
        result = None if value is None else {"type": "number", "value": value}
    elif cell_type == "s":
        if (
            formula is not None
            or inline
            or value is None
            or _DECIMAL.fullmatch(value) is None
            or shared is None
        ):
            _fail("xlsx_invalid_cell")
        index = int(value)
        if index >= len(shared):
            _fail("xlsx_invalid_cell")
        result = {"type": "text", "value": shared[index]}
    elif cell_type == "inlineStr":
        if formula is not None or values or len(inline) != 1:
            _fail("xlsx_invalid_cell")
        result = {"type": "text", "value": _rich_text(inline[0], ns)}
    elif cell_type in {"str", "e", "d", "b"}:
        if inline or value is None:
            _fail("xlsx_invalid_cell")
        if cell_type == "b":
            if value not in {"0", "1", "false", "true"}:
                _fail("xlsx_invalid_cell")
            result = {"type": "boolean", "value": "true" if value in {"1", "true"} else "false"}
        elif cell_type == "d":
            result = {"type": "date", "value": _date_value(value)}
        else:
            if not value:
                _fail("xlsx_invalid_cell")
            result = {"type": "text" if cell_type == "str" else "error", "value": value}
    else:
        _fail("xlsx_invalid_cell")
    length = len(formula or "") + (len(result["value"]) if result else 0)
    if length > MAXIMUM_CELL_CHARACTERS:
        _fail("xlsx_cell_character_limit", "limit_exceeded")
    return result


def _merged_ranges(
    root: ElementTree.Element, ns: str, budget: _CanonicalBudget
) -> tuple[list[dict[str, str]], list[tuple[int, int, int, int]]]:
    ranges: list[tuple[tuple[int, int], tuple[int, int], str, str]] = []
    rectangles: list[tuple[int, int, int, int]] = []
    containers = root.findall(f"./{{{ns}}}mergeCells")
    if len(containers) > 1:
        _fail("xlsx_invalid_cell")
    for item in containers[0] if containers else ():
        if item.tag != f"{{{ns}}}mergeCell" or set(item.attrib) != {"ref"}:
            _fail("xlsx_invalid_cell")
        parts = item.get("ref", "").split(":")
        if len(parts) != 2:
            _fail("xlsx_invalid_cell")
        start, sr, sc = _coordinate(parts[0])
        end, er, ec = _coordinate(parts[1])
        if (sr, sc) > (er, ec) or (sr, sc) == (er, ec):
            _fail("xlsx_invalid_cell")
        if any(
            not (er < other_sr or sr > other_er or ec < other_sc or sc > other_ec)
            for other_sr, other_sc, other_er, other_ec in rectangles
        ):
            _fail("xlsx_invalid_cell")
        rectangles.append((sr, sc, er, ec))
        ranges.append(((sr, sc), (er, ec), start, end))
    ranges.sort(key=lambda item: (item[0], item[1]))
    canonical = [{"anchor": start, "range": f"{start}:{end}"} for _, _, start, end in ranges]
    for item in canonical:
        budget.claim(item)
    return canonical, rectangles


def _worksheet(
    payload: bytes,
    ns: str,
    shared: list[str] | None,
    counters: dict[str, int],
    budget: _CanonicalBudget,
) -> tuple[list[dict[str, object]], list[dict[str, str]], bool]:
    root = _xml(
        payload,
        f"{{{ns}}}worksheet",
        "xlsx_invalid_worksheet_xml",
        spreadsheet_family=True,
    )
    sheet_data = root.findall(f"./{{{ns}}}sheetData")
    if len(sheet_data) != 1:
        _fail("xlsx_invalid_cell")
    direct_rows = {id(row) for row in sheet_data[0]}
    if any(id(row) not in direct_rows for row in root.iter(f"{{{ns}}}row")):
        _fail("xlsx_invalid_cell")
    merges, merged_rectangles = _merged_ranges(root, ns, budget)
    cells: list[tuple[int, int, dict[str, object]]] = []
    seen_rows: set[int] = set()
    seen_cells: set[str] = set()
    validated_cell_ids: set[int] = set()
    for row in sheet_data[0]:
        if (
            row.tag != f"{{{ns}}}row"
            or row.get("r") is None
            or _DECIMAL.fullmatch(row.get("r", "")) is None
        ):
            _fail("xlsx_invalid_cell")
        row_number = int(row.get("r", "0"))
        if not 1 <= row_number <= 1_048_576 or row_number in seen_rows:
            _fail("xlsx_invalid_cell")
        seen_rows.add(row_number)
        counters["rows"] += 1
        if counters["rows"] > MAXIMUM_ROWS:
            _fail("xlsx_row_limit", "limit_exceeded")
        for cell in row:
            if cell.tag != f"{{{ns}}}c" or cell.get("r") is None:
                _fail("xlsx_invalid_cell")
            coordinate, actual_row, column = _coordinate(cell.get("r", ""))
            if actual_row != row_number or coordinate in seen_cells:
                _fail("xlsx_invalid_cell")
            seen_cells.add(coordinate)
            validated_cell_ids.add(id(cell))
            counters["cells"] += 1
            if counters["cells"] > MAXIMUM_CELLS:
                _fail("xlsx_cell_limit", "limit_exceeded")
            covered = any(
                sr <= actual_row <= er and sc <= column <= ec and (actual_row, column) != (sr, sc)
                for sr, sc, er, ec in merged_rectangles
            )
            if covered:
                if any(child.tag in {f"{{{ns}}}f", f"{{{ns}}}v", f"{{{ns}}}is"} for child in cell):
                    _fail("xlsx_merged_cell_conflict")
                if _cell_value(cell, ns, shared, None) is not None:
                    _fail("xlsx_merged_cell_conflict")
                continue
            formula = _formula(cell, ns)
            value = _cell_value(cell, ns, shared, formula)
            if formula is None and value is None:
                continue
            canonical_cell = {
                "coordinate": coordinate,
                "formula": formula,
                "value": value,
            }
            budget.claim(canonical_cell)
            cells.append((actual_row, column, canonical_cell))
    if any(id(cell) not in validated_cell_ids for cell in root.iter(f"{{{ns}}}c")):
        _fail("xlsx_invalid_cell")
    cells.sort(key=lambda item: (item[0], item[1]))
    phonetic = any(
        element.tag in {f"{{{ns}}}rPh", f"{{{ns}}}phoneticPr"} for element in root.iter()
    )
    return [item[2] for item in cells], merges, phonetic


def extract_xlsx(
    payload: bytes,
    *,
    validate_ooxml: Callable[[bytes], object],
) -> XlsxExtraction:
    validate_ooxml(payload)
    try:
        archive = zipfile.ZipFile(BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise XlsxExtractionFailure("malformed", "xlsx_relationship_conflict") from exc
    with archive:
        infos = {info.filename.casefold(): info for info in archive.infolist() if not info.is_dir()}

        def read(name: str, code: str = "xlsx_relationship_conflict") -> bytes:
            info = infos.get(name.casefold())
            if info is None:
                _fail(code)
            return archive.read(info)

        workbook_payload = read("xl/workbook.xml", "xlsx_workbook_unavailable")
        try:
            probe = ElementTree.fromstring(workbook_payload)
        except ElementTree.ParseError as exc:
            raise XlsxExtractionFailure("malformed", "xlsx_invalid_workbook_xml") from exc
        ns = probe.tag.removeprefix("{").split("}", 1)[0] if probe.tag.startswith("{") else ""
        if ns not in _FAMILIES:
            _fail("xlsx_namespace_conflict")
        relationship_ns = _FAMILIES[ns]
        workbook = _xml(workbook_payload, f"{{{ns}}}workbook", "xlsx_invalid_workbook_xml")
        relationships = _relationships(read("xl/_rels/workbook.xml.rels"))
        expected_base = relationship_ns
        worksheet_type = f"{expected_base}/worksheet"
        shared_type = f"{expected_base}/sharedStrings"
        for kind, _target in relationships.values():
            if (
                kind.startswith(f"{_TRANSITIONAL_R}/") or kind.startswith(f"{_STRICT_R}/")
            ) and not kind.startswith(f"{expected_base}/"):
                _fail("xlsx_namespace_conflict")
        sheets_element = workbook.find(f"./{{{ns}}}sheets")
        if sheets_element is None:
            _fail("xlsx_invalid_workbook_xml")
        sheets = list(sheets_element)
        if len(sheets) > MAXIMUM_WORKSHEETS:
            _fail("xlsx_sheet_limit", "limit_exceeded")
        shared_targets = [target for kind, target in relationships.values() if kind == shared_type]
        if len(shared_targets) > 1:
            _fail("xlsx_relationship_conflict")
        shared_result = _shared_strings(read(shared_targets[0]), ns) if shared_targets else None
        shared = shared_result[0] if shared_result else None
        phonetic_metadata = shared_result[1] if shared_result else False
        omissions = {
            "truncated": False,
            "omitted": False,
            "formatting": "xl/styles.xml" in infos
            or any(name.startswith("xl/theme/") for name in infos),
            "comments": any(
                name.startswith(("xl/comments", "xl/threadedcomments/", "xl/persons/"))
                for name in infos
            ),
            "drawings": any(name.startswith(("xl/drawings/", "xl/charts/")) for name in infos),
            "hidden_metadata": phonetic_metadata
            or workbook.find(f"./{{{ns}}}definedNames") is not None
            or any(name.startswith(("docprops/", "customxml/")) for name in infos),
            "unsupported_objects": any(
                name == "xl/calcchain.xml" or name.startswith(token)
                for name in infos
                for token in (
                    "xl/tables/",
                    "xl/pivottables/",
                    "xl/pivotcache/",
                    "xl/slicers/",
                    "xl/chartsheets/",
                    "xl/dialogsheets/",
                )
            ),
        }
        counters = {"rows": 0, "cells": 0}
        budget = _CanonicalBudget()
        canonical: list[dict[str, object]] = []
        used_targets: set[str] = set()
        seen_names: set[str] = set()
        seen_sheet_ids: set[int] = set()
        for position, sheet in enumerate(sheets, 1):
            if sheet.tag != f"{{{ns}}}sheet":
                _fail("xlsx_invalid_workbook_xml")
            name = sheet.get("name")
            rel_id = sheet.get(f"{{{relationship_ns}}}id")
            other_relationship_ns = (
                _STRICT_R if relationship_ns == _TRANSITIONAL_R else _TRANSITIONAL_R
            )
            if sheet.get(f"{{{other_relationship_ns}}}id") is not None:
                _fail("xlsx_namespace_conflict")
            state = sheet.get("state", "visible")
            sheet_id_text = sheet.get("sheetId")
            if (
                not name
                or name in seen_names
                or state not in {"visible", "hidden", "veryHidden"}
                or not rel_id
                or sheet_id_text is None
                or _DECIMAL.fullmatch(sheet_id_text) is None
            ):
                _fail("xlsx_invalid_workbook_xml")
            sheet_id = int(sheet_id_text)
            if sheet_id < 1 or sheet_id in seen_sheet_ids:
                _fail("xlsx_invalid_workbook_xml")
            seen_names.add(name)
            seen_sheet_ids.add(sheet_id)
            relationship = relationships.get(rel_id)
            if (
                relationship is None
                or relationship[0] != worksheet_type
                or relationship[1] in used_targets
            ):
                _fail("xlsx_relationship_conflict")
            target = relationship[1]
            used_targets.add(target)
            cells, merged, worksheet_phonetic = _worksheet(
                read(target), ns, shared, counters, budget
            )
            omissions["hidden_metadata"] = bool(omissions["hidden_metadata"] or worksheet_phonetic)
            worksheet_result = {
                "cells": cells,
                "merged_ranges": merged,
                "name": name,
                "position": position,
                "visibility": "very_hidden" if state == "veryHidden" else state,
            }
            budget.claim(
                {
                    "name": worksheet_result["name"],
                    "position": worksheet_result["position"],
                    "visibility": worksheet_result["visibility"],
                }
            )
            canonical.append(worksheet_result)
        stored_worksheets = {
            name for name in infos if name.startswith("xl/worksheets/") and name.endswith(".xml")
        }
        if stored_worksheets != used_targets:
            _fail("xlsx_relationship_conflict")
        stored_shared = {name for name in infos if name == "xl/sharedstrings.xml"}
        expected_shared = set(shared_targets)
        if stored_shared != expected_shared:
            _fail("xlsx_relationship_conflict")
        omissions["omitted"] = any(
            omissions[key] for key in omissions if key not in {"truncated", "omitted"}
        )
        chunks: list[str] = []
        output_bytes = 0
        encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for chunk in encoder.iterencode({"worksheets": canonical}):
            output_bytes += len(chunk.encode("utf-8"))
            if output_bytes > MAXIMUM_OUTPUT_BYTES:
                _fail("output_limit", "limit_exceeded")
            chunks.append(chunk)
        output = "".join(chunks)
        return XlsxExtraction(canonical_output=output, omission_facts=omissions)
