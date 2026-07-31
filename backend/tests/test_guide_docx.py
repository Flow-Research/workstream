"""Focused proofs for deterministic bounded DOCX extraction."""

from __future__ import annotations

from io import BytesIO
import json
import zipfile

import pytest

from app.modules.artifacts.guide_docx import (
    DocxExtraction,
    DocxExtractionFailure,
    extract_docx as _extract_docx,
)
from app.modules.artifacts.guide_extraction import GuideExtractionRunner
from app.modules.artifacts.guide_ooxml import OoxmlSecurityFailure, validate_ooxml


_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx(
    document: bytes,
    *,
    document_name: str = "word/document.xml",
    additions: dict[str, bytes] | None = None,
) -> bytes:
    members = {
        "[Content_Types].xml": b"<Types/>",
        "_rels/.rels": b"<Relationships/>",
        document_name: document,
        **(additions or {}),
    }
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    return output.getvalue()


def _document(body: str) -> bytes:
    return f'<w:document xmlns:w="{_W}"><w:body>{body}</w:body></w:document>'.encode()


def extract_docx(
    payload: bytes,
    *,
    maximum_output_bytes: int = 4 * 1024 * 1024,
) -> DocxExtraction:
    def bounded_validate(exact_payload: bytes) -> object:
        try:
            return validate_ooxml(exact_payload, detected_format="docx")
        except OoxmlSecurityFailure as exc:
            raise DocxExtractionFailure(exc.status, exc.code) from exc

    return _extract_docx(
        payload,
        validate_ooxml=bounded_validate,
        maximum_output_bytes=maximum_output_bytes,
    )


def test_extracts_paragraphs_tables_and_nested_tables_deterministically() -> None:
    payload = _docx(
        _document(
            """
            <w:p><w:r><w:t>Hello </w:t><w:tab/><w:t>world</w:t><w:br/><w:t>again</w:t></w:r></w:p>
            <w:tbl><w:tr>
              <w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc>
              <w:tc><w:p><w:hyperlink><w:r><w:t>B</w:t></w:r></w:hyperlink></w:p>
                <w:tbl><w:tr><w:tc><w:p><w:r><w:t>nested</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
                <w:p><w:r><w:t>tail</w:t></w:r></w:p>
              </w:tc>
            </w:tr><w:tr><w:tc/><w:tc><w:p/></w:tc></w:tr></w:tbl>
            <w:p/>
            """
        )
    )

    result = extract_docx(payload)

    assert result.canonical_output == (
        '{"blocks":[{"text":"Hello \\tworld\\nagain","type":"paragraph"},'
        '{"text":"A\\tB\\nnested\\ntail\\n\\t","type":"table"},'
        '{"text":"","type":"paragraph"}]}'
    )
    assert result.omission_facts == {
        "truncated": False,
        "omitted": False,
        "headers": False,
        "footers": False,
        "comments": False,
        "tracked_deletions": False,
        "embedded_objects": False,
        "hidden_text": False,
        "field_instructions": False,
    }
    assert extract_docx(payload) == result


def test_records_every_docx_omission_without_exposing_omitted_text() -> None:
    payload = _docx(
        _document(
            """
            <w:p>
              <w:r><w:t>visible</w:t></w:r>
              <w:del><w:r><w:delText>deleted-secret</w:delText></w:r></w:del>
              <w:r><w:rPr><w:vanish/></w:rPr><w:t>hidden-secret</w:t></w:r>
              <w:r><w:instrText>field-secret</w:instrText><w:t>field result</w:t></w:r>
              <w:commentReference w:id="1"/><w:drawing/>
            </w:p>
            """
        ),
        additions={
            "word/header1.xml": b"<header/>",
            "word/footer1.xml": b"<footer/>",
            "word/comments.xml": b"<comments/>",
        },
    )

    result = extract_docx(payload)

    assert json.loads(result.canonical_output) == {
        "blocks": [{"type": "paragraph", "text": "visiblefield result"}]
    }
    assert result.omission_facts == {
        "truncated": False,
        "omitted": True,
        "headers": True,
        "footers": True,
        "comments": True,
        "tracked_deletions": True,
        "embedded_objects": True,
        "hidden_text": True,
        "field_instructions": True,
    }
    assert "secret" not in result.canonical_output


def test_style_hidden_text_is_omitted_and_simple_field_records_instructions() -> None:
    payload = _docx(
        _document(
            """
            <w:p>
              <w:r><w:rPr><w:rStyle w:val="InheritedHidden"/></w:rPr><w:t>hidden-by-style</w:t></w:r>
              <w:fldSimple w:instr="DATE"><w:r><w:t>visible-result</w:t></w:r></w:fldSimple>
            </w:p>
            """
        ),
        additions={
            "word/styles.xml": f"""
              <w:styles xmlns:w="{_W}">
                <w:style w:type="character" w:styleId="HiddenBase"><w:rPr><w:vanish/></w:rPr></w:style>
                <w:style w:type="character" w:styleId="InheritedHidden"><w:basedOn w:val="HiddenBase"/></w:style>
              </w:styles>
            """.encode()
        },
    )

    result = extract_docx(payload)

    assert result.canonical_output == ('{"blocks":[{"text":"visible-result","type":"paragraph"}]}')
    assert result.omission_facts["hidden_text"] is True
    assert result.omission_facts["field_instructions"] is True
    assert result.omission_facts["omitted"] is True
    assert "hidden-by-style" not in result.canonical_output


def test_validated_part_names_are_resolved_case_insensitively() -> None:
    payload = _docx(
        _document(
            '<w:p><w:r><w:rPr><w:rStyle w:val="Hidden"/></w:rPr><w:t>hidden</w:t></w:r></w:p>'
        ),
        document_name="word/Document.xml",
        additions={
            "word/Styles.xml": f"""
              <w:styles xmlns:w="{_W}">
                <w:style w:type="character" w:styleId="Hidden"><w:rPr><w:vanish/></w:rPr></w:style>
              </w:styles>
            """.encode()
        },
    )

    result = extract_docx(payload)

    assert result.canonical_output == ('{"blocks":[{"text":"","type":"paragraph"}]}')
    assert result.omission_facts["hidden_text"] is True


def test_default_and_inherited_paragraph_style_hidden_text_is_omitted() -> None:
    paragraph_style_payload = _docx(
        _document(
            """
            <w:p><w:pPr><w:pStyle w:val="InheritedHiddenParagraph"/></w:pPr>
              <w:r><w:t>hidden-paragraph</w:t></w:r></w:p>
            """
        ),
        additions={
            "word/styles.xml": f"""
              <w:styles xmlns:w="{_W}">
                <w:style w:type="paragraph" w:styleId="HiddenParagraph"><w:rPr><w:vanish/></w:rPr></w:style>
                <w:style w:type="paragraph" w:styleId="InheritedHiddenParagraph"><w:basedOn w:val="HiddenParagraph"/></w:style>
              </w:styles>
            """.encode()
        },
    )
    default_payload = _docx(
        _document("<w:p><w:r><w:t>hidden-by-default</w:t></w:r></w:p>"),
        additions={
            "word/styles.xml": f"""
              <w:styles xmlns:w="{_W}">
                <w:docDefaults><w:rPrDefault><w:rPr><w:vanish/></w:rPr></w:rPrDefault></w:docDefaults>
              </w:styles>
            """.encode()
        },
    )

    paragraph_result = extract_docx(paragraph_style_payload)
    default_result = extract_docx(default_payload)

    assert paragraph_result.canonical_output == ('{"blocks":[{"text":"","type":"paragraph"}]}')
    assert default_result.canonical_output == paragraph_result.canonical_output
    for result in (paragraph_result, default_result):
        assert result.omission_facts["hidden_text"] is True
        assert result.omission_facts["omitted"] is True
        assert "hidden-" not in result.canonical_output


def test_block_level_deleted_and_moved_content_never_enters_output() -> None:
    payload = _docx(
        _document(
            """
            <w:del><w:p><w:r><w:t>deleted-block</w:t></w:r></w:p></w:del>
            <w:tbl><w:tr><w:tc>
              <w:moveFrom><w:p><w:r><w:t>moved-block</w:t></w:r></w:p></w:moveFrom>
            </w:tc></w:tr></w:tbl>
            <w:sdt><w:sdtContent><w:p><w:r><w:t>visible-control</w:t></w:r></w:p></w:sdtContent></w:sdt>
            """
        )
    )
    result = extract_docx(payload)
    assert result.canonical_output == (
        '{"blocks":[{"text":"","type":"table"},{"text":"visible-control","type":"paragraph"}]}'
    )
    assert result.omission_facts["tracked_deletions"] is True
    assert result.omission_facts["omitted"] is True
    assert "deleted-block" not in result.canonical_output
    assert "moved-block" not in result.canonical_output


def test_table_rows_and_cells_inside_content_controls_preserve_order() -> None:
    payload = _docx(
        _document(
            """
            <w:tbl><w:sdt><w:sdtContent><w:tr>
              <w:sdt><w:sdtContent><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc></w:sdtContent></w:sdt>
              <w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc>
            </w:tr></w:sdtContent></w:sdt></w:tbl>
            """
        )
    )

    result = extract_docx(payload)

    assert result.canonical_output == ('{"blocks":[{"text":"A\\tB","type":"table"}]}')
    assert result.omission_facts["omitted"] is False


def test_active_content_and_missing_body_fail_with_bounded_codes() -> None:
    with pytest.raises(DocxExtractionFailure) as active:
        extract_docx(
            _docx(
                _document("<w:p/>"),
                additions={"word/embeddings/object.bin": b"unsafe"},
            )
        )
    assert (active.value.status, active.value.code) == (
        "malformed",
        "ooxml_active_content",
    )

    missing_body = _docx(f'<w:document xmlns:w="{_W}"/>'.encode())
    with pytest.raises(DocxExtractionFailure) as missing:
        extract_docx(missing_body)
    assert (missing.value.status, missing.value.code) == (
        "malformed",
        "docx_body_missing",
    )


def test_output_limit_is_exact_and_never_returns_partial_content() -> None:
    payload = _docx(_document("<w:p><w:r><w:t>bounded</w:t></w:r></w:p>"))
    expected = extract_docx(payload).canonical_output
    assert (
        extract_docx(payload, maximum_output_bytes=len(expected.encode())).canonical_output
        == expected
    )
    with pytest.raises(DocxExtractionFailure) as over:
        extract_docx(payload, maximum_output_bytes=len(expected.encode()) - 1)
    assert (over.value.status, over.value.code) == ("limit_exceeded", "output_limit")


def test_excessive_wrapper_nesting_has_one_deterministic_malformed_outcome() -> None:
    nested = "<w:p><w:r><w:t>deep</w:t></w:r></w:p>"
    for _ in range(65):
        nested = f"<w:sdt><w:sdtContent>{nested}</w:sdtContent></w:sdt>"

    with pytest.raises(DocxExtractionFailure) as excessive:
        extract_docx(_docx(_document(nested)))

    assert (excessive.value.status, excessive.value.code) == (
        "malformed",
        "docx_nesting_limit",
    )


def test_malformed_document_xml_is_bounded_by_shared_security() -> None:
    with pytest.raises(DocxExtractionFailure) as malformed:
        extract_docx(_docx(b"<w:document"))
    assert (malformed.value.status, malformed.value.code) == (
        "malformed",
        "ooxml_unsafe_xml",
    )


def test_real_isolated_runner_uses_docx_v3_and_preserves_omissions(tmp_path) -> None:
    payload = _docx(
        _document(
            "<w:p><w:r><w:t>visible</w:t></w:r>"
            "<w:del><w:r><w:delText>deleted</w:delText></w:r></w:del></w:p>"
        )
    )
    result = GuideExtractionRunner().extract(
        BytesIO(payload), detected_format="docx", workspace=tmp_path
    )
    assert (result.status, result.policy_version) == ("extracted", "guide-extraction-v3")
    assert result.canonical_output == ('{"blocks":[{"text":"visible","type":"paragraph"}]}')
    assert result.omission_facts == {
        "truncated": False,
        "omitted": True,
        "headers": False,
        "footers": False,
        "comments": False,
        "tracked_deletions": True,
        "embedded_objects": False,
        "hidden_text": False,
        "field_instructions": False,
    }
    assert list(tmp_path.iterdir()) == []
