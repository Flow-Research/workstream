"""Focused security and boundary proofs for isolated PDF extraction."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
)

from app.modules.artifacts.guide_extraction import GuideExtractionRunner
from app.modules.artifacts.guide_pdf import PdfExtractionFailure, extract_pdf


def _pdf(
    *,
    pages: int = 1,
    active_key: str | None = None,
    active_type: tuple[str, str] | None = None,
    annotation_action: str | None = None,
    probe_action: str | None = None,
    encrypted: bool = False,
    text: str | None = None,
) -> bytes:
    writer = PdfWriter()
    created_pages = [writer.add_blank_page(width=72, height=72) for _ in range(pages)]
    if text is not None:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        created_pages[0][NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET".encode("ascii"))
        created_pages[0][NameObject("/Contents")] = writer._add_object(content)
    if active_key is not None:
        writer.root_object[NameObject(active_key)] = DictionaryObject(
            {NameObject("/S"): NameObject("/Launch")}
        )
    if active_type is not None:
        key, value = active_type
        writer.root_object[NameObject(key)] = NameObject(value)
    if annotation_action is not None:
        annotation = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Link"),
                NameObject("/Rect"): ArrayObject([FloatObject(0)] * 4),
                NameObject("/A"): DictionaryObject(
                    {
                        NameObject("/S"): NameObject(annotation_action),
                        NameObject("/N"): NameObject("/Print"),
                    }
                ),
            }
        )
        created_pages[0][NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])
    if probe_action is not None:
        writer.root_object[NameObject("/ActionProbe")] = DictionaryObject(
            {NameObject("/S"): NameObject(probe_action)}
        )
    if encrypted:
        writer.encrypt("secret")
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def test_pdf_extraction_is_deterministic_and_page_separated() -> None:
    payload = _pdf(pages=2, text="Guide content")

    first = extract_pdf(payload)
    second = extract_pdf(payload)

    assert first == second == '{"pages":["Guide content",""]}'


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        (b"%PDF-1.7\nnot-a-pdf", "malformed", "invalid_pdf"),
        (_pdf(encrypted=True), "malformed", "pdf_encrypted"),
        *[
            (_pdf(active_key=key), "malformed", "pdf_active_content")
            for key in (
                "/OpenAction",
                "/AA",
                "/AcroForm",
                "/XFA",
                "/EmbeddedFiles",
                "/AF",
                "/Launch",
                "/JavaScript",
                "/JS",
                "/SubmitForm",
                "/ImportData",
                "/URI",
            )
        ],
    ],
)
def test_pdf_rejects_malformed_encrypted_interactive_and_embedded_content(
    payload: bytes, status: str, code: str
) -> None:
    with pytest.raises(PdfExtractionFailure) as raised:
        extract_pdf(payload)

    assert (raised.value.status, raised.value.code) == (status, code)


@pytest.mark.parametrize(
    ("key", "value"),
    [("/Subtype", "/FileAttachment"), ("/Subtype", "/Widget"), ("/Type", "/Filespec")],
)
def test_pdf_rejects_attachment_form_and_external_file_object_types(key: str, value: str) -> None:
    with pytest.raises(PdfExtractionFailure) as raised:
        extract_pdf(_pdf(active_type=(key, value)))

    assert (raised.value.status, raised.value.code) == ("malformed", "pdf_active_content")


@pytest.mark.parametrize(
    "action",
    ["/Named", "/GoToR", "/GoToE", "/URI", "/JavaScript", "/Launch", "/SubmitForm", "/ImportData"],
)
def test_pdf_rejects_real_page_annotation_actions(action: str, tmp_path: Path) -> None:
    result = GuideExtractionRunner().extract(
        BytesIO(_pdf(annotation_action=action)), detected_format="pdf", workspace=tmp_path
    )

    assert (result.status, result.error_code) == ("malformed", "pdf_active_content")


@pytest.mark.parametrize(
    "action",
    ["/GoToE", "/GoToR", "/ImportData", "/JavaScript", "/Launch", "/SubmitForm", "/URI"],
)
def test_pdf_rejects_each_forbidden_action_value_independently(action: str) -> None:
    with pytest.raises(PdfExtractionFailure) as raised:
        extract_pdf(_pdf(probe_action=action))

    assert (raised.value.status, raised.value.code) == ("malformed", "pdf_active_content")


def test_pdf_page_limit_accepts_500_and_rejects_501() -> None:
    assert len(json.loads(extract_pdf(_pdf(pages=500)))["pages"]) == 500

    with pytest.raises(PdfExtractionFailure) as raised:
        extract_pdf(_pdf(pages=501))

    assert (raised.value.status, raised.value.code) == (
        "limit_exceeded",
        "pdf_page_limit",
    )


def test_pdf_runs_through_the_isolated_runner(tmp_path: Path) -> None:
    result = GuideExtractionRunner().extract(
        BytesIO(_pdf()), detected_format="pdf", workspace=tmp_path
    )

    assert result.status == "extracted"
    assert result.error_code is None
    assert result.canonical_output == '{"pages":[""]}'
    assert result.output_sha256 is not None
    assert list(tmp_path.iterdir()) == []


def test_pdf_runner_bounds_active_content_and_malformed_input(tmp_path: Path) -> None:
    active = GuideExtractionRunner().extract(
        BytesIO(_pdf(active_key="/OpenAction")), detected_format="pdf", workspace=tmp_path
    )
    malformed = GuideExtractionRunner().extract(
        BytesIO(b"%PDF-1.7\ninvalid"), detected_format="pdf", workspace=tmp_path
    )

    assert (active.status, active.error_code) == ("malformed", "pdf_active_content")
    assert (malformed.status, malformed.error_code) == ("malformed", "invalid_pdf")
