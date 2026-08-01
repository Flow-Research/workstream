"""Focused contract proofs for deterministic bounded XLSX extraction."""

from __future__ import annotations

from io import BytesIO
import json
import zipfile

import pytest

import app.modules.artifacts.guide_xlsx as xlsx
from app.modules.artifacts.guide_xlsx import XlsxExtractionFailure, extract_xlsx


TRANSITIONAL_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
TRANSITIONAL_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
STRICT_MAIN = "http://purl.oclc.org/ooxml/spreadsheetml/main"
STRICT_R = "http://purl.oclc.org/ooxml/officeDocument/relationships"
PACKAGE_R = "http://schemas.openxmlformats.org/package/2006/relationships"


def _package(
    *,
    main: str = TRANSITIONAL_MAIN,
    relationship_ns: str = TRANSITIONAL_R,
    workbook_body: str | None = None,
    relationships_body: str | None = None,
    worksheet: str | None = None,
    shared_strings: str | None = None,
    additions: dict[str, str] | None = None,
) -> bytes:
    workbook_body = workbook_body or (
        '<sheets><sheet name="Guide" sheetId="1" r:id="rId1"/></sheets>'
    )
    relationships_body = relationships_body or (
        f'<Relationship Id="rId1" Type="{relationship_ns}/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
    )
    worksheet = worksheet or (
        '<sheetData><row r="2"><c r="b2"><v>2</v></c></row>'
        '<row r="1"><c r="A1" t="inlineStr"><is><r><t>A</t></r>'
        "<rPh><t>phonetic</t></rPh><r><t>B</t></r></is></c></row></sheetData>"
    )
    members = {
        "[Content_Types].xml": "<Types/>",
        "_rels/.rels": "<Relationships/>",
        "xl/workbook.xml": (
            f'<workbook xmlns="{main}" xmlns:r="{relationship_ns}">{workbook_body}</workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            f'<Relationships xmlns="{PACKAGE_R}">{relationships_body}</Relationships>'
        ),
        "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{main}">{worksheet}</worksheet>',
        **(additions or {}),
    }
    if shared_strings is not None:
        members["xl/sharedStrings.xml"] = f'<sst xmlns="{main}">{shared_strings}</sst>'
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    return output.getvalue()


def _extract(payload: bytes):
    return extract_xlsx(payload, validate_ooxml=lambda _payload: object())


def _replace(payload: bytes, name: str, body: str | None) -> bytes:
    source = zipfile.ZipFile(BytesIO(payload))
    output = BytesIO()
    with source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            if info.filename != name:
                target.writestr(info, source.read(info))
        if body is not None:
            target.writestr(name, body)
    return output.getvalue()


def _failure(payload: bytes) -> tuple[str, str]:
    with pytest.raises(XlsxExtractionFailure) as raised:
        _extract(payload)
    return raised.value.status, raised.value.code


def test_strict_workbook_normalizes_order_coordinates_and_visibility() -> None:
    result = _extract(
        _package(
            main=STRICT_MAIN,
            relationship_ns=STRICT_R,
            workbook_body=(
                '<sheets><sheet name="Guide" sheetId="1" state="veryHidden" r:id="rId1"/></sheets>'
            ),
        )
    )
    worksheet = json.loads(result.canonical_output)["worksheets"][0]
    assert worksheet["visibility"] == "very_hidden"
    assert [cell["coordinate"] for cell in worksheet["cells"]] == ["A1", "B2"]
    assert worksheet["cells"][0]["value"] == {"type": "text", "value": "AB"}
    assert result.omission_facts["hidden_metadata"] is True


@pytest.mark.parametrize(
    ("workbook_body", "code"),
    [
        ("<sheets><wrong/></sheets>", "xlsx_invalid_workbook_xml"),
        ('<sheets><sheet name="" sheetId="1" r:id="rId1"/></sheets>', "xlsx_invalid_workbook_xml"),
        (
            '<sheets><sheet name="A" sheetId="1" r:id="rId1"/>'
            '<sheet name="B" sheetId="1" r:id="rId2"/></sheets>',
            "xlsx_invalid_workbook_xml",
        ),
        (
            '<sheets><sheet name="A" sheetId="1" state="invalid" r:id="rId1"/></sheets>',
            "xlsx_invalid_workbook_xml",
        ),
    ],
)
def test_invalid_workbook_metadata_uses_exact_code(workbook_body: str, code: str) -> None:
    assert _failure(_package(workbook_body=workbook_body)) == ("malformed", code)


@pytest.mark.parametrize(
    "relationships_body",
    [
        f'<Relationship Id="rId1" Type="{TRANSITIONAL_R}/worksheet" Target="/bad.xml"/>',
        f'<Relationship Id="rId1" Type="{TRANSITIONAL_R}/worksheet" Target="../bad.xml"/>',
        f'<Relationship Id="rId1" Type="{TRANSITIONAL_R}/worksheet" Target="worksheets/sheet1.xml"/>'
        f'<Relationship Id="rId2" Type="{TRANSITIONAL_R}/styles" Target="worksheets/sheet1.xml"/>',
        f'<Relationship Id="rId1" Type="{TRANSITIONAL_R}/chartsheet" Target="worksheets/sheet1.xml"/>',
    ],
)
def test_relationship_conflicts_fail_closed(relationships_body: str) -> None:
    assert _failure(_package(relationships_body=relationships_body)) == (
        "malformed",
        "xlsx_relationship_conflict",
    )


def test_mixed_relationship_namespace_fails_exactly() -> None:
    assert _failure(
        _package(
            relationships_body=(
                f'<Relationship Id="rId1" Type="{STRICT_R}/worksheet" '
                'Target="worksheets/sheet1.xml"/>'
            )
        )
    ) == ("malformed", "xlsx_namespace_conflict")


def test_mixed_worksheet_and_rid_namespaces_fail_as_namespace_conflict() -> None:
    strict_worksheet = f'<worksheet xmlns="{STRICT_MAIN}"><sheetData/></worksheet>'
    assert _failure(_replace(_package(), "xl/worksheets/sheet1.xml", strict_worksheet)) == (
        "malformed",
        "xlsx_namespace_conflict",
    )
    strict_workbook_with_transitional_rid = _package(
        main=STRICT_MAIN,
        relationship_ns=STRICT_R,
    )
    workbook = (
        f'<workbook xmlns="{STRICT_MAIN}" xmlns:r="{TRANSITIONAL_R}"><sheets>'
        '<sheet name="Guide" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    assert _failure(
        _replace(strict_workbook_with_transitional_rid, "xl/workbook.xml", workbook)
    ) == ("malformed", "xlsx_namespace_conflict")
    dual_rid_workbook = (
        f'<workbook xmlns="{STRICT_MAIN}" xmlns:r="{STRICT_R}" '
        f'xmlns:t="{TRANSITIONAL_R}"><sheets><sheet name="Guide" sheetId="1" '
        'r:id="rId1" t:id="rId1"/></sheets></workbook>'
    )
    assert _failure(
        _replace(strict_workbook_with_transitional_rid, "xl/workbook.xml", dual_rid_workbook)
    ) == ("malformed", "xlsx_namespace_conflict")


@pytest.mark.parametrize(
    ("worksheet", "code"),
    [
        ('<sheetData><row r="0"/></sheetData>', "xlsx_invalid_cell"),
        ('<sheetData><row r="1"/><row r="1"/></sheetData>', "xlsx_invalid_cell"),
        ('<sheetData><row r="1"><c r="XFE1"><v>1</v></c></row></sheetData>', "xlsx_invalid_cell"),
        ('<sheetData><row r="1"><c r="A2"><v>1</v></c></row></sheetData>', "xlsx_invalid_cell"),
        ('<sheetData><row r="1"><c r="A1"/><c r="a1"/></row></sheetData>', "xlsx_invalid_cell"),
        ('<sheetData/><mergeCells><mergeCell ref="B2:A1"/></mergeCells>', "xlsx_invalid_cell"),
        (
            '<sheetData/><mergeCells><mergeCell ref="A1:B2"/><mergeCell ref="B2:C3"/></mergeCells>',
            "xlsx_invalid_cell",
        ),
        (
            '<sheetData><row r="1"><c r="A1"><f t="array">1</f></c></row></sheetData>',
            "xlsx_formula_unsupported",
        ),
    ],
)
def test_worksheet_semantic_failures_are_stable(worksheet: str, code: str) -> None:
    status = "unsupported" if code == "xlsx_formula_unsupported" else "malformed"
    assert _failure(_package(worksheet=worksheet)) == (status, code)


@pytest.mark.parametrize(
    ("name", "flag"),
    [
        ("xl/theme/theme1.xml", "formatting"),
        ("xl/comments1.xml", "comments"),
        ("xl/persons/person.xml", "comments"),
        ("xl/drawings/drawing1.xml", "drawings"),
        ("xl/charts/chart1.xml", "drawings"),
        ("docProps/core.xml", "hidden_metadata"),
        ("xl/calcChain.xml", "unsupported_objects"),
        ("xl/pivotcache/cache.xml", "unsupported_objects"),
        ("xl/chartsheets/sheet1.xml", "unsupported_objects"),
    ],
)
def test_each_stored_part_omission_trigger_is_exact(name: str, flag: str) -> None:
    result = _extract(_package(additions={name: "<passive/>"}))
    assert result.omission_facts[flag] is True
    assert result.omission_facts["omitted"] is True


def test_defined_names_and_shared_phonetics_record_hidden_metadata() -> None:
    relationships = (
        f'<Relationship Id="rId1" Type="{TRANSITIONAL_R}/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        f'<Relationship Id="rId2" Type="{TRANSITIONAL_R}/sharedStrings" '
        'Target="sharedStrings.xml"/>'
    )
    workbook = (
        '<definedNames><definedName name="hidden">Sheet1!A1</definedName></definedNames>'
        '<sheets><sheet name="Guide" sheetId="1" r:id="rId1"/></sheets>'
    )
    result = _extract(
        _package(
            workbook_body=workbook,
            relationships_body=relationships,
            worksheet='<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData>',
            shared_strings="<si><t>A</t><rPh><t>hidden</t></rPh></si>",
        )
    )
    assert result.omission_facts["hidden_metadata"] is True
    assert json.loads(result.canonical_output)["worksheets"][0]["cells"][0]["value"]["value"] == "A"


def test_adapter_enforces_output_limit_before_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(xlsx, "MAXIMUM_OUTPUT_BYTES", 20)
    assert _failure(_package()) == ("limit_exceeded", "output_limit")


def test_missing_and_invalid_workbook_fail_with_distinct_exact_codes() -> None:
    assert _failure(_replace(_package(), "xl/workbook.xml", None)) == (
        "malformed",
        "xlsx_workbook_unavailable",
    )
    assert _failure(_replace(_package(), "xl/workbook.xml", "<broken")) == (
        "malformed",
        "xlsx_invalid_workbook_xml",
    )
    assert _failure(b"not a zip") == ("malformed", "xlsx_relationship_conflict")


def test_invalid_shared_string_root_uses_exact_code() -> None:
    relationships = (
        f'<Relationship Id="rId1" Type="{TRANSITIONAL_R}/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        f'<Relationship Id="rId2" Type="{TRANSITIONAL_R}/sharedStrings" '
        'Target="sharedStrings.xml"/>'
    )
    assert _failure(
        _package(
            relationships_body=relationships,
            shared_strings="<wrong/>",
        )
    ) == ("malformed", "xlsx_invalid_shared_strings_xml")


def test_formula_duplicates_and_empty_merged_cells_fail_or_omit_exactly() -> None:
    assert _failure(
        _package(
            worksheet=('<sheetData><row r="1"><c r="A1"><f>1</f><f>2</f></c></row></sheetData>')
        )
    ) == ("malformed", "xlsx_invalid_cell")
    result = _extract(
        _package(
            worksheet=(
                '<sheetData><row r="1"><c r="B1"/></row></sheetData>'
                '<mergeCells><mergeCell ref="A1:B2"/></mergeCells>'
            )
        )
    )
    assert json.loads(result.canonical_output)["worksheets"][0]["cells"] == []


@pytest.mark.parametrize(
    ("covered", "code"),
    [
        ('<c r="B1"><f t="array">1</f></c>', "xlsx_merged_cell_conflict"),
        ('<c r="B1"><unknown/></c>', "xlsx_invalid_cell"),
        ('<c r="B1" t="unknown"/>', "xlsx_invalid_cell"),
    ],
)
def test_covered_merged_cells_fail_with_exact_precedence(covered: str, code: str) -> None:
    worksheet = (
        f'<sheetData><row r="1">{covered}</row></sheetData>'
        '<mergeCells><mergeCell ref="A1:B2"/></mergeCells>'
    )
    assert _failure(_package(worksheet=worksheet)) == ("malformed", code)


def test_xml_depth_limit_is_applied_inside_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(xlsx, "MAXIMUM_NESTING_DEPTH", 1)
    assert _failure(_package()) == ("malformed", "xlsx_nesting_limit")


def test_exact_policy_constants_and_counter_boundaries() -> None:
    assert (
        xlsx.MAXIMUM_WORKSHEETS,
        xlsx.MAXIMUM_ROWS,
        xlsx.MAXIMUM_CELLS,
        xlsx.MAXIMUM_CELL_CHARACTERS,
        xlsx.MAXIMUM_OUTPUT_BYTES,
    ) == (100, 100_000, 1_000_000, 32_768, 4 * 1024 * 1024)
    namespace = TRANSITIONAL_MAIN
    one_row = (
        f'<worksheet xmlns="{namespace}"><sheetData><row r="1"><c r="A1"><v>1</v>'
        "</c></row></sheetData></worksheet>"
    ).encode()
    counters = {"rows": 99_999, "cells": 999_999}
    cells, _, _ = xlsx._worksheet(one_row, namespace, None, counters, xlsx._CanonicalBudget())
    assert counters == {"rows": 100_000, "cells": 1_000_000}
    assert cells[0]["coordinate"] == "A1"
    with pytest.raises(XlsxExtractionFailure) as row_failure:
        xlsx._worksheet(
            one_row,
            namespace,
            None,
            {"rows": 100_000, "cells": 0},
            xlsx._CanonicalBudget(),
        )
    assert (row_failure.value.status, row_failure.value.code) == (
        "limit_exceeded",
        "xlsx_row_limit",
    )
    with pytest.raises(XlsxExtractionFailure) as cell_failure:
        xlsx._worksheet(
            one_row,
            namespace,
            None,
            {"rows": 0, "cells": 1_000_000},
            xlsx._CanonicalBudget(),
        )
    assert (cell_failure.value.status, cell_failure.value.code) == (
        "limit_exceeded",
        "xlsx_cell_limit",
    )


def test_exact_character_boundary() -> None:
    accepted = _extract(
        _package(
            worksheet=(
                '<sheetData><row r="1"><c r="A1" t="str"><v>'
                + ("a" * 32_768)
                + "</v></c></row></sheetData>"
            )
        )
    )
    assert (
        len(json.loads(accepted.canonical_output)["worksheets"][0]["cells"][0]["value"]["value"])
        == 32_768
    )
    assert _failure(
        _package(
            worksheet=(
                '<sheetData><row r="1"><c r="A1" t="str"><v>'
                + ("a" * 32_769)
                + "</v></c></row></sheetData>"
            )
        )
    ) == ("limit_exceeded", "xlsx_cell_character_limit")


def _many_sheet_package(count: int) -> bytes:
    sheets = "".join(
        f'<sheet name="S{number}" sheetId="{number}" r:id="rId{number}"/>'
        for number in range(1, count + 1)
    )
    relationships = "".join(
        f'<Relationship Id="rId{number}" Type="{TRANSITIONAL_R}/worksheet" '
        f'Target="worksheets/sheet{number}.xml"/>'
        for number in range(1, count + 1)
    )
    empty = f'<worksheet xmlns="{TRANSITIONAL_MAIN}"><sheetData/></worksheet>'
    additions = {f"xl/worksheets/sheet{number}.xml": empty for number in range(2, count + 1)}
    return _package(
        workbook_body=f"<sheets>{sheets}</sheets>",
        relationships_body=relationships,
        worksheet="<sheetData/>",
        additions=additions,
    )


def test_exact_sheet_count_boundary() -> None:
    accepted = _extract(_many_sheet_package(100))
    assert len(json.loads(accepted.canonical_output)["worksheets"]) == 100
    assert _failure(_many_sheet_package(101)) == (
        "limit_exceeded",
        "xlsx_sheet_limit",
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [("A1", ("A1", 1, 1)), ("xfd1048576", ("XFD1048576", 1_048_576, 16_384))],
)
def test_coordinate_grid_edges(value: str, expected: tuple[str, int, int]) -> None:
    assert xlsx._coordinate(value) == expected


@pytest.mark.parametrize("target", ["", "\\bad", "/bad", "../../bad"])
def test_relationship_target_rejects_unsafe_paths(target: str) -> None:
    with pytest.raises(XlsxExtractionFailure) as raised:
        xlsx._relationship_target(target)
    assert raised.value.code == "xlsx_relationship_conflict"
