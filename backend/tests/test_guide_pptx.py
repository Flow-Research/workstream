"""Focused proofs for deterministic bounded PPTX extraction."""

from __future__ import annotations

from io import BytesIO
import json
import subprocess
import zipfile

import pytest

from app.modules.artifacts.guide_extraction import GuideExtractionRunner
from app.modules.artifacts.guide_ooxml import OoxmlSecurityFailure, validate_ooxml
from app.modules.artifacts.guide_pptx import (
    PptxExtraction,
    PptxExtractionFailure,
    extract_pptx as _extract_pptx,
)


_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_TRANSITIONAL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_STRICT = "http://purl.oclc.org/ooxml/officeDocument/relationships"


def _presentation(ids: list[str], *, family: str = _TRANSITIONAL) -> bytes:
    slides = "".join(f'<p:sldId id="{256 + index}" r:id="{rid}"/>' for index, rid in enumerate(ids))
    relationship_namespace = _R if family == _TRANSITIONAL else _STRICT
    return (
        f'<p:presentation xmlns:p="{_P}" xmlns:r="{relationship_namespace}">'
        f"<p:sldIdLst>{slides}</p:sldIdLst></p:presentation>"
    ).encode()


def _relationships(rows: list[tuple[str, str, str]]) -> bytes:
    values = "".join(
        f'<Relationship Id="{rid}" Type="{relationship_type}" Target="{target}"/>'
        for rid, relationship_type, target in rows
    )
    return f'<Relationships xmlns="{_REL}">{values}</Relationships>'.encode()


def _slide(body: str = "") -> bytes:
    return f'<p:sld xmlns:p="{_P}" xmlns:a="{_A}"><p:cSld><p:spTree>{body}</p:spTree></p:cSld></p:sld>'.encode()


def _notes(body: str = "") -> bytes:
    return f'<p:notes xmlns:p="{_P}" xmlns:a="{_A}"><p:cSld><p:spTree>{body}</p:spTree></p:cSld></p:notes>'.encode()


def _text_shape(paragraphs: list[str], *, placeholder: str | None = None, alt: str = "") -> str:
    placeholder_xml = f'<p:ph type="{placeholder}"/>' if placeholder else ""
    content = "".join(f"<a:p>{paragraph}</a:p>" for paragraph in paragraphs)
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="1" name="shape"{alt}/>'
        f"<p:nvPr>{placeholder_xml}</p:nvPr></p:nvSpPr>"
        f"<p:txBody>{content}</p:txBody></p:sp>"
    )


def _package(
    slides: list[bytes],
    *,
    notes: dict[int, bytes] | None = None,
    family: str = _TRANSITIONAL,
    additions: dict[str, bytes] | None = None,
    presentation_name: str = "ppt/presentation.xml",
) -> bytes:
    notes = notes or {}
    slide_rows = [
        (f"rId{index}", f"{family}/slide", f"slides/slide{index}.xml")
        for index in range(1, len(slides) + 1)
    ]
    members: dict[str, bytes] = {
        "[Content_Types].xml": b"<Types/>",
        "_rels/.rels": b"<Relationships/>",
        presentation_name: _presentation([row[0] for row in slide_rows], family=family),
        "ppt/_rels/presentation.xml.rels": _relationships(slide_rows),
    }
    for index, slide in enumerate(slides, 1):
        members[f"ppt/slides/slide{index}.xml"] = slide
        if index in notes:
            members[f"ppt/notesSlides/notesSlide{index}.xml"] = notes[index]
            members[f"ppt/slides/_rels/slide{index}.xml.rels"] = _relationships(
                [
                    (
                        "rIdNotes",
                        f"{family}/notesSlide",
                        f"../notesSlides/notesSlide{index}.xml",
                    )
                ]
            )
    members.update(additions or {})
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    return output.getvalue()


def _replace_member(payload: bytes, name: str, body: bytes) -> bytes:
    with zipfile.ZipFile(BytesIO(payload)) as source:
        members = {info.filename: source.read(info) for info in source.infolist()}
    members[name] = body
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for member_name, member_body in members.items():
            archive.writestr(member_name, member_body)
    return output.getvalue()


def extract_pptx(
    payload: bytes,
    *,
    maximum_output_bytes: int = 4 * 1024 * 1024,
) -> PptxExtraction:
    def bounded_validate(exact_payload: bytes) -> object:
        try:
            return validate_ooxml(exact_payload, detected_format="pptx")
        except OoxmlSecurityFailure as exc:
            raise PptxExtractionFailure(exc.status, exc.code) from exc

    return _extract_pptx(
        payload,
        validate_ooxml=bounded_validate,
        maximum_output_bytes=maximum_output_bytes,
    )


def test_extracts_slides_tables_groups_and_notes_in_exact_order() -> None:
    slide = _slide(
        _text_shape(
            [
                "<a:r><a:t>one</a:t></a:r><a:tab/><a:r><a:t>two</a:t></a:r>",
                "<a:r><a:t>three</a:t></a:r><a:br/><a:r><a:t>four</a:t></a:r>",
            ]
        )
        + "<p:grpSp><p:sp><p:txBody><a:p><a:r><a:t>grouped</a:t></a:r></a:p></p:txBody></p:sp></p:grpSp>"
        + "<p:graphicFrame><a:graphic><a:graphicData><a:tbl><a:tr><a:tc><a:txBody>"
        + "<a:p><a:r><a:t>cell-a</a:t></a:r></a:p></a:txBody></a:tc><a:tc><a:txBody>"
        + "<a:p/><a:p><a:r><a:t>cell-b</a:t></a:r></a:p></a:txBody></a:tc>"
        + "</a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>"
    )
    notes = _notes(
        _text_shape(["<a:r><a:t>ignored footer</a:t></a:r>"], placeholder="ftr")
        + _text_shape(["<a:r><a:t>speaker note</a:t></a:r>"], placeholder="body")
    )

    result = extract_pptx(_package([slide, _slide()], notes={1: notes}))

    assert result.canonical_output == (
        '{"slides":[{"notes":["speaker note"],"number":1,'
        '"text":["one\\ttwo","three\\nfour","grouped","cell-a","","cell-b"]},'
        '{"notes":[],"number":2,"text":[]}]}'
    )
    assert result.omission_facts == {
        "truncated": False,
        "omitted": True,
        "masters": False,
        "comments": False,
        "hidden_metadata": True,
        "non_text_objects": False,
        "embedded_objects": False,
    }
    assert extract_pptx(_package([slide, _slide()], notes={1: notes})) == result


def test_records_every_pptx_omission_without_exposing_metadata() -> None:
    slide = _slide(
        _text_shape(["<a:r><a:t>visible</a:t></a:r>"], alt=' descr="secret alt"')
        + "<p:pic><a:p><a:r><a:t>picture secret</a:t></a:r></a:p></p:pic>"
        + "<p:oleObj><a:p><a:r><a:t>object secret</a:t></a:r></a:p></p:oleObj>"
        + "<p:graphicFrame><a:p><a:r><a:t>chart secret</a:t></a:r></a:p>"
        + "</p:graphicFrame>"
    )
    payload = _package(
        [slide],
        additions={
            "ppt/slideMasters/slideMaster1.xml": b"<master/>",
            "ppt/comments/comment1.xml": b"<comments/>",
            "docProps/core.xml": b"<properties/>",
        },
    )

    result = extract_pptx(payload)

    assert json.loads(result.canonical_output) == {
        "slides": [{"notes": [], "number": 1, "text": ["visible"]}]
    }
    assert result.omission_facts == {
        "truncated": False,
        "omitted": True,
        "masters": True,
        "comments": True,
        "hidden_metadata": True,
        "non_text_objects": True,
        "embedded_objects": True,
    }
    assert "secret" not in result.canonical_output


def test_relationship_conflicts_and_orphans_fail_closed() -> None:
    orphan = _package([_slide()], additions={"ppt/slides/slide2.xml": _slide()})
    with pytest.raises(PptxExtractionFailure) as orphaned:
        extract_pptx(orphan)
    assert (orphaned.value.status, orphaned.value.code) == (
        "malformed",
        "pptx_relationship_conflict",
    )

    mixed = _package(
        [_slide()],
        notes={1: _notes()},
        family=_TRANSITIONAL,
    )
    with zipfile.ZipFile(BytesIO(mixed)) as source:
        members = {info.filename: source.read(info) for info in source.infolist()}
    members["ppt/slides/_rels/slide1.xml.rels"] = _relationships(
        [("rIdNotes", f"{_STRICT}/notesSlide", "../notesSlides/notesSlide1.xml")]
    )
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    with pytest.raises(PptxExtractionFailure) as namespace:
        extract_pptx(output.getvalue())
    assert (namespace.value.status, namespace.value.code) == (
        "malformed",
        "pptx_relationship_conflict",
    )

    wrong_type = _package([_slide()])
    with zipfile.ZipFile(BytesIO(wrong_type)) as source:
        members = {info.filename: source.read(info) for info in source.infolist()}
    members["ppt/_rels/presentation.xml.rels"] = _relationships(
        [("rIdSlide1", f"{_TRANSITIONAL}/slideLayout", "slides/slide1.xml")]
    )
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    with pytest.raises(PptxExtractionFailure) as relationship_type:
        extract_pptx(output.getvalue())
    assert (relationship_type.value.status, relationship_type.value.code) == (
        "malformed",
        "pptx_relationship_conflict",
    )

    members["ppt/_rels/presentation.xml.rels"] = (
        b'<NotRelationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        b'relationships"><Relationship Id="rIdSlide1" Type="http://schemas.'
        b'openxmlformats.org/officeDocument/2006/relationships/slide" '
        b'Target="slides/slide1.xml"/></NotRelationships>'
    )
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    with pytest.raises(PptxExtractionFailure) as relationship_root:
        extract_pptx(output.getvalue())
    assert (relationship_root.value.status, relationship_root.value.code) == (
        "malformed",
        "pptx_relationship_conflict",
    )

    duplicate_slide_ids = _replace_member(
        _package([_slide(), _slide()]),
        "ppt/presentation.xml",
        _presentation(["rId1", "rId2"]).replace(b'id="257"', b'id="256"'),
    )
    with pytest.raises(PptxExtractionFailure) as duplicate_id:
        extract_pptx(duplicate_slide_ids)
    assert (duplicate_id.value.status, duplicate_id.value.code) == (
        "malformed",
        "pptx_relationship_conflict",
    )


def test_complete_relationship_identity_and_ownership_matrix_fails_closed() -> None:
    base = _package([_slide()])
    dangling = _replace_member(
        base,
        "ppt/_rels/presentation.xml.rels",
        _relationships([("rId1", f"{_TRANSITIONAL}/slide", "slides/slide2.xml")]),
    )
    duplicate_relationship = _replace_member(
        base,
        "ppt/_rels/presentation.xml.rels",
        _relationships(
            [
                ("rId1", f"{_TRANSITIONAL}/slide", "slides/slide1.xml"),
                ("rId1", f"{_TRANSITIONAL}/slide", "slides/slide1.xml"),
            ]
        ),
    )
    duplicate_reference = _replace_member(
        _package([_slide(), _slide()]),
        "ppt/presentation.xml",
        _presentation(["rId1", "rId1"]),
    )
    cross_root = _replace_member(
        base,
        "ppt/_rels/presentation.xml.rels",
        _relationships([("rId1", f"{_TRANSITIONAL}/slide", "../word/document.xml")]),
    )
    orphan_notes = _package([_slide()], additions={"ppt/notesSlides/notesSlide1.xml": _notes()})
    shared_notes = _package([_slide(), _slide()], notes={1: _notes(), 2: _notes()})
    shared_notes = _replace_member(
        shared_notes,
        "ppt/slides/_rels/slide2.xml.rels",
        _relationships(
            [("rIdNotes", f"{_TRANSITIONAL}/notesSlide", "../notesSlides/notesSlide1.xml")]
        ),
    )

    for payload in (
        dangling,
        duplicate_relationship,
        duplicate_reference,
        cross_root,
        orphan_notes,
        shared_notes,
    ):
        with pytest.raises(PptxExtractionFailure) as conflict:
            extract_pptx(payload)
        assert (conflict.value.status, conflict.value.code) == (
            "malformed",
            "pptx_relationship_conflict",
        )


def test_hidden_slide_visibility_is_recorded_without_discarding_text() -> None:
    payload = _replace_member(
        _package([_slide(_text_shape(["<a:r><a:t>visible text</a:t></a:r>"]))]),
        "ppt/presentation.xml",
        _presentation(["rId1"]).replace(b'id="256"', b'id="256" show="0"'),
    )
    result = extract_pptx(payload)
    assert result.canonical_output == (
        '{"slides":[{"notes":[],"number":1,"text":["visible text"]}]}'
    )
    assert result.omission_facts["hidden_metadata"] is True
    assert result.omission_facts["omitted"] is True


def test_slide_limit_is_checked_before_slide_extraction() -> None:
    accepted = extract_pptx(_package([_slide()] * 300))
    assert len(json.loads(accepted.canonical_output)["slides"]) == 300

    with pytest.raises(PptxExtractionFailure) as excessive:
        extract_pptx(_package([_slide()] * 301))
    assert (excessive.value.status, excessive.value.code) == (
        "limit_exceeded",
        "pptx_slide_limit",
    )


def test_output_and_nesting_limits_are_exact_and_never_partial() -> None:
    payload = _package([_slide(_text_shape(["<a:r><a:t>bounded</a:t></a:r>"]))])
    expected = extract_pptx(payload).canonical_output
    assert (
        extract_pptx(payload, maximum_output_bytes=len(expected.encode())).canonical_output
        == expected
    )
    with pytest.raises(PptxExtractionFailure) as output:
        extract_pptx(payload, maximum_output_bytes=len(expected.encode()) - 1)
    assert (output.value.status, output.value.code) == ("limit_exceeded", "output_limit")

    nested = "<a:p><a:r><a:t>deep</a:t></a:r></a:p>"
    for _ in range(65):
        nested = f"<a:ext>{nested}</a:ext>"
    with pytest.raises(PptxExtractionFailure) as nesting:
        extract_pptx(_package([_slide(_text_shape([nested]))]))
    assert (nesting.value.status, nesting.value.code) == (
        "malformed",
        "pptx_nesting_limit",
    )

    grouped = "<p:grpSp>" * 65 + _text_shape(["<a:r><a:t>deep</a:t></a:r>"]) + "</p:grpSp>" * 65
    with pytest.raises(PptxExtractionFailure) as grouped_nesting:
        extract_pptx(_package([_slide(grouped)]))
    assert (grouped_nesting.value.status, grouped_nesting.value.code) == (
        "malformed",
        "pptx_nesting_limit",
    )


def test_only_shape_tree_text_enters_canonical_output() -> None:
    slide = (
        f'<p:sld xmlns:p="{_P}" xmlns:a="{_A}"><p:cSld><p:spTree>'
        f"{_text_shape(['<a:r><a:t>visible</a:t></a:r>'])}"
        "</p:spTree></p:cSld><p:extLst><a:p><a:r><a:t>extension secret</a:t>"
        "</a:r></a:p></p:extLst></p:sld>"
    ).encode()
    result = extract_pptx(_package([slide]))
    assert result.canonical_output == ('{"slides":[{"notes":[],"number":1,"text":["visible"]}]}')


def test_skipped_non_text_subtrees_still_record_hidden_metadata() -> None:
    slide = _slide(
        '<p:pic><p:cNvPr descr="hidden description"/>'
        "<a:p><a:r><a:t>not content</a:t></a:r></a:p></p:pic>"
    )
    result = extract_pptx(_package([slide]))
    assert result.canonical_output == '{"slides":[{"notes":[],"number":1,"text":[]}]}'
    assert result.omission_facts["hidden_metadata"] is True
    assert result.omission_facts["non_text_objects"] is True


def test_graphic_frame_table_discovery_preserves_the_outer_depth_limit() -> None:
    nested_table = (
        "<p:graphicFrame>"
        + "<p:grpSp>" * 65
        + "<a:tbl><a:tr><a:tc><a:p><a:r><a:t>deep table</a:t></a:r></a:p>"
        + "</a:tc></a:tr></a:tbl>"
        + "</p:grpSp>" * 65
        + "</p:graphicFrame>"
    )
    with pytest.raises(PptxExtractionFailure) as nesting:
        extract_pptx(_package([_slide(nested_table)]))
    assert (nesting.value.status, nesting.value.code) == (
        "malformed",
        "pptx_nesting_limit",
    )


def test_deep_notes_placeholder_cannot_bypass_the_nesting_limit() -> None:
    nested_placeholder = (
        '<p:sp><p:nvSpPr><p:cNvPr id="1" name="notes"/><p:nvPr>'
        + "<p:grpSp>" * 65
        + '<p:ph type="ftr"/>'
        + "</p:grpSp>" * 65
        + "</p:nvPr></p:nvSpPr></p:sp>"
    )
    with pytest.raises(PptxExtractionFailure) as nesting:
        extract_pptx(_package([_slide()], notes={1: _notes(nested_placeholder)}))
    assert (nesting.value.status, nesting.value.code) == (
        "malformed",
        "pptx_nesting_limit",
    )

    deep_metadata_body = (
        '<p:sp><p:nvSpPr><p:cNvPr id="1" name="notes"/><p:nvPr>'
        '<p:ph type="ftr"/></p:nvPr></p:nvSpPr><p:txBody>'
        + "<p:grpSp>" * 65
        + "<a:p><a:r><a:t>footer</a:t></a:r></a:p>"
        + "</p:grpSp>" * 65
        + "</p:txBody></p:sp>"
    )
    with pytest.raises(PptxExtractionFailure) as metadata_nesting:
        extract_pptx(_package([_slide()], notes={1: _notes(deep_metadata_body)}))
    assert (metadata_nesting.value.status, metadata_nesting.value.code) == (
        "malformed",
        "pptx_nesting_limit",
    )


@pytest.mark.parametrize(
    ("replacement", "code"),
    [
        ({"ppt/presentation.xml": b"<broken"}, "ooxml_unsafe_xml"),
        ({"ppt/presentation.xml": b"<wrong/>"}, "pptx_invalid_presentation_xml"),
        ({"ppt/slides/slide1.xml": b"<wrong/>"}, "pptx_invalid_slide_xml"),
        (
            {"ppt/notesSlides/notesSlide1.xml": b"<wrong/>"},
            "pptx_invalid_notes_xml",
        ),
    ],
)
def test_invalid_xml_and_roots_have_stable_bounded_codes(
    replacement: dict[str, bytes], code: str
) -> None:
    payload = _package([_slide()], notes={1: _notes()}, additions=replacement)
    with pytest.raises(PptxExtractionFailure) as invalid:
        extract_pptx(payload)
    assert (invalid.value.status, invalid.value.code) == ("malformed", code)


def test_validated_part_names_resolve_case_insensitively() -> None:
    payload = _package(
        [_slide(_text_shape(["<a:r><a:t>visible</a:t></a:r>"]))],
        presentation_name="ppt/Presentation.xml",
    )
    result = extract_pptx(payload)
    assert result.canonical_output == ('{"slides":[{"notes":[],"number":1,"text":["visible"]}]}')


def test_strict_relationship_namespace_is_supported_without_mixing() -> None:
    result = extract_pptx(
        _package(
            [_slide(_text_shape(["<a:r><a:t>strict</a:t></a:r>"]))],
            family=_STRICT,
        )
    )
    assert result.canonical_output == ('{"slides":[{"notes":[],"number":1,"text":["strict"]}]}')


def test_missing_presentation_after_validation_has_stable_bounded_code() -> None:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")

    with pytest.raises(PptxExtractionFailure) as unavailable:
        _extract_pptx(output.getvalue(), validate_ooxml=lambda _: object())
    assert (unavailable.value.status, unavailable.value.code) == (
        "malformed",
        "pptx_presentation_unavailable",
    )

    with pytest.raises(PptxExtractionFailure) as invalid_container:
        _extract_pptx(b"not-a-zip", validate_ooxml=lambda _: object())
    assert (invalid_container.value.status, invalid_container.value.code) == (
        "malformed",
        "pptx_presentation_unavailable",
    )


def test_real_isolated_runner_uses_pptx_v4_and_complete_omissions(tmp_path) -> None:
    payload = _package([_slide("<p:pic/>")])
    result = GuideExtractionRunner().extract(
        BytesIO(payload), detected_format="pptx", workspace=tmp_path
    )
    assert (result.status, result.policy_version) == ("extracted", "guide-extraction-v4")
    assert result.canonical_output == '{"slides":[{"notes":[],"number":1,"text":[]}]}'
    assert result.omission_facts == {
        "truncated": False,
        "omitted": True,
        "masters": False,
        "comments": False,
        "hidden_metadata": False,
        "non_text_objects": True,
        "embedded_objects": False,
    }
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "omission_facts",
    [
        {"truncated": False, "omitted": False},
        {
            "truncated": False,
            "omitted": False,
            "masters": True,
            "comments": False,
            "hidden_metadata": False,
            "non_text_objects": False,
            "embedded_objects": False,
        },
    ],
)
def test_parent_rejects_incomplete_or_inconsistent_pptx_omission_facts(
    tmp_path, monkeypatch: pytest.MonkeyPatch, omission_facts: dict[str, bool]
) -> None:
    class CompletedProcess:
        returncode = 0
        pid = 123

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def communicate(self, _payload, timeout):
            del timeout
            return json.dumps(
                {
                    "status": "extracted",
                    "error_code": None,
                    "output": '{"slides":[]}',
                    "omission_facts": omission_facts,
                }
            ).encode(), b""

    monkeypatch.setattr(subprocess, "Popen", CompletedProcess)
    result = GuideExtractionRunner().extract(
        BytesIO(b"guide"), detected_format="pptx", workspace=tmp_path
    )
    assert (result.status, result.error_code) == (
        "parser_failure",
        "invalid_executor_output",
    )
