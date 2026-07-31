"""Focused proofs for the shared bounded OOXML security boundary."""

from __future__ import annotations

from io import BytesIO
import stat
import zipfile

import pytest

import app.modules.artifacts.guide_ooxml as ooxml_module
from app.modules.artifacts.guide_formats import GuideFormatLimits, OOXML_REQUIRED_MARKERS
from app.modules.artifacts.guide_ooxml import OoxmlSecurityFailure, validate_ooxml


def _package(
    *,
    detected_format: str = "docx",
    additions: dict[str, bytes] | None = None,
    external: bool = False,
) -> bytes:
    marker = {"docx": "word/document.xml", "pptx": "ppt/presentation.xml", "xlsx": "xl/workbook.xml"}[detected_format]
    relationships = (
        b'<Relationships><Relationship TargetMode="External"/></Relationships>'
        if external
        else b"<Relationships/>"
    )
    members = {
        "[Content_Types].xml": b"<Types/>",
        "_rels/.rels": relationships,
        marker: b"<root/>",
        **(additions or {}),
    }
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    return output.getvalue()


def _failure(payload: bytes, *, detected_format: str = "docx") -> tuple[str, str]:
    with pytest.raises(OoxmlSecurityFailure) as raised:
        validate_ooxml(payload, detected_format=detected_format)
    return raised.value.status, raised.value.code


def test_ooxml_validator_inherits_classifier_markers_and_limits() -> None:
    limits = GuideFormatLimits()
    assert ooxml_module._REQUIRED is OOXML_REQUIRED_MARKERS
    assert ooxml_module.MAXIMUM_ENTRIES == limits.maximum_entries
    assert (
        ooxml_module.MAXIMUM_CENTRAL_DIRECTORY_BYTES
        == limits.maximum_central_directory_bytes
    )
    assert ooxml_module.MAXIMUM_DECOMPRESSED_BYTES == limits.maximum_decompressed_bytes
    assert ooxml_module.MAXIMUM_COMPRESSION_RATIO == limits.maximum_compression_ratio


@pytest.mark.parametrize("detected_format", ["docx", "pptx", "xlsx"])
def test_valid_exact_classified_packages_pass_without_extraction(detected_format: str) -> None:
    result = validate_ooxml(_package(detected_format=detected_format), detected_format=detected_format)
    assert result.detected_format == detected_format
    assert result.entry_count == 3


@pytest.mark.parametrize(
    ("additions", "status", "code"),
    [
        ({"../escape.xml": b"<x/>"}, "malformed", "ooxml_invalid_path"),
        ({"unknown/data.xml": b"<x/>"}, "malformed", "ooxml_unknown_package_part"),
        ({"word/embeddings/object.bin": b"x"}, "malformed", "ooxml_active_content"),
        ({"word/nested.zip": b"PK\x05\x06" + b"\0" * 18}, "malformed", "ooxml_active_content"),
        ({"word/bad.xml": b"<!DOCTYPE x [<!ENTITY e 'x'>]><x>&e;</x>"}, "malformed", "ooxml_unsafe_xml"),
        ({"word/bare_dtd.xml": b"<!DOCTYPE x><x/>"}, "malformed", "ooxml_unsafe_xml"),
    ],
)
def test_rejects_unsafe_members(additions, status: str, code: str) -> None:
    with pytest.raises(OoxmlSecurityFailure) as raised:
        validate_ooxml(_package(additions=additions), detected_format="docx")
    assert (raised.value.status, raised.value.code) == (status, code)


def test_rejects_external_relationships() -> None:
    with pytest.raises(OoxmlSecurityFailure) as raised:
        validate_ooxml(_package(external=True), detected_format="docx")
    assert raised.value.code == "ooxml_external_relationship"


@pytest.mark.parametrize("target", ["../evil.xml", "../../evil.xml"])
def test_root_relationship_cannot_traverse_above_package(target: str) -> None:
    relationships = (
        f'<Relationships><Relationship Type="http://schemas.example/relationships/image" '
        f'Target="{target}"/></Relationships>'
    ).encode()
    assert _failure(_package(additions={"_rels/.rels": relationships})) == (
        "malformed",
        "ooxml_external_relationship",
    )


@pytest.mark.parametrize(
    ("relationship", "expected_code"),
    [
        (
            b'<Relationships><Relationship Target="https://example.test/payload"/></Relationships>',
            "ooxml_external_relationship",
        ),
        (
            b'<Relationships><Relationship Type="http://schemas.example/oleObject" Target="item.xml"/></Relationships>',
            "ooxml_active_content",
        ),
    ],
)
def test_rejects_implicit_external_and_active_relationship_metadata(
    relationship: bytes,
    expected_code: str,
) -> None:
    assert _failure(
        _package(additions={"word/_rels/document.xml.rels": relationship})
    ) == ("malformed", expected_code)


def test_rejects_active_content_type_under_a_passive_filename() -> None:
    content_types = (
        b'<Types><Override PartName="/word/payload.xml" '
        b'ContentType="application/vnd.ms-office.vbaProject"/></Types>'
    )
    assert _failure(
        _package(additions={"[Content_Types].xml": content_types, "word/payload.xml": b"<x/>"})
    ) == ("malformed", "ooxml_active_content")


def test_rejects_svg_content_type_disguised_as_an_xml_part() -> None:
    content_types = (
        b'<Types><Override PartName="/word/media/active.xml" '
        b'ContentType="image/svg+xml"/></Types>'
    )
    assert _failure(
        _package(
            additions={
                "[Content_Types].xml": content_types,
                "word/media/active.xml": b"<svg><script/></svg>",
            }
        )
    ) == ("malformed", "ooxml_active_content")


@pytest.mark.parametrize("kind", ["aFChunk", "package", "externalLink"])
def test_rejects_non_passive_relationship_types(kind: str) -> None:
    relationship = (
        f'<Relationships><Relationship Type="http://schemas.example/relationships/{kind}" '
        'Target="payload.xml"/></Relationships>'
    ).encode()
    assert _failure(
        _package(additions={"word/_rels/document.xml.rels": relationship})
    ) == ("malformed", "ooxml_active_content")


def test_utf16_dtd_is_rejected_by_parser_policy() -> None:
    body = '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE x><x/>'.encode("utf-16")
    assert _failure(_package(additions={"word/utf16.xml": body})) == (
        "malformed",
        "ooxml_unsafe_xml",
    )


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("/absolute.xml", "ooxml_invalid_path"),
        ("C:/drive.xml", "ooxml_invalid_path"),
        ("word\\backslash.xml", "ooxml_invalid_path"),
        ("word/vbaProject.bin", "ooxml_active_content"),
        ("word/run.js", "ooxml_active_content"),
        ("word/run.sh", "ooxml_active_content"),
        ("word/unknown.any", "ooxml_unknown_package_part"),
        ("word/media/active.svg", "ooxml_unknown_package_part"),
        ("ppt/slides/slide1.xml", "ooxml_classification_conflict"),
    ],
)
def test_rejects_path_and_executable_variants(name: str, code: str) -> None:
    expected_status = "ambiguous" if code == "ooxml_classification_conflict" else "malformed"
    assert _failure(_package(additions={name: b"<x/>"})) == (expected_status, code)


def test_rejects_case_collisions_and_special_entries() -> None:
    collision = _package(additions={"word/A.xml": b"<a/>", "word/a.XML": b"<b/>"})
    assert _failure(collision) == ("malformed", "ooxml_duplicate_path")

    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, body in {
            "[Content_Types].xml": b"<Types/>",
            "_rels/.rels": b"<Relationships/>",
            "word/document.xml": b"<root/>",
        }.items():
            archive.writestr(name, body)
        link = zipfile.ZipInfo("word/link.xml")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, b"target")
    assert _failure(output.getvalue()) == ("malformed", "ooxml_special_entry")


def test_rejects_missing_and_conflicting_markers() -> None:
    missing = _package()
    with zipfile.ZipFile(BytesIO(missing), "r") as source:
        members = {info.filename: source.read(info) for info in source.infolist()}
    members.pop("word/document.xml")
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    assert _failure(output.getvalue()) == ("malformed", "ooxml_required_marker_missing")
    conflict = _package(additions={"ppt/presentation.xml": b"<root/>"})
    assert _failure(conflict) == ("ambiguous", "ooxml_classification_conflict")
    assert _failure(_package(), detected_format="opaque") == (
        "ambiguous",
        "ooxml_classification_conflict",
    )


def test_directory_cannot_impersonate_required_file_marker() -> None:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("_rels/.rels", b"<Relationships/>")
        archive.writestr("word/document.xml/", b"")
    assert _failure(output.getvalue()) == ("malformed", "ooxml_required_marker_missing")


@pytest.mark.parametrize("directory", ["unknown/", "ppt/"])
def test_unknown_and_cross_format_directory_roots_fail_closed(directory: str) -> None:
    assert _failure(_package(additions={directory: b""})) == (
        "malformed",
        "ooxml_unknown_package_part",
    )


@pytest.mark.parametrize("name", ["_rels/foo.rels", "_rels/nested/"])
def test_noncanonical_root_relationship_parts_fail_closed(name: str) -> None:
    assert _failure(_package(additions={name: b"<Relationships/>"})) == (
        "malformed",
        "ooxml_unknown_package_part",
    )


def test_rejects_nested_archive_magic_without_archive_suffix() -> None:
    nested = _package(additions={"word/inner.xml": b"<x/>"})
    sfx = _package(additions={"word/media/blob.xml": b"MZstub" + nested})
    assert _failure(sfx) == ("malformed", "ooxml_nested_archive")


def test_rejects_bounded_size_ratio_and_relationship_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ooxml_module, "MAXIMUM_DECOMPRESSED_BYTES", 8)
    assert _failure(_package()) == ("limit_exceeded", "ooxml_decompressed_limit")
    monkeypatch.setattr(ooxml_module, "MAXIMUM_DECOMPRESSED_BYTES", 128 * 1024 * 1024)
    monkeypatch.setattr(ooxml_module, "MAXIMUM_COMPRESSION_RATIO", 1)
    assert _failure(_package(additions={"word/large.xml": b"x" * 1_000})) == (
        "limit_exceeded",
        "ooxml_compression_ratio",
    )
    monkeypatch.setattr(ooxml_module, "MAXIMUM_COMPRESSION_RATIO", 100)
    monkeypatch.setattr(ooxml_module, "MAXIMUM_RELATIONSHIP_BYTES", 4)
    assert _failure(_package()) == ("limit_exceeded", "ooxml_relationship_limit")


def test_rejects_invalid_directory_multidisk_and_zip64() -> None:
    assert _failure(b"not-a-zip") == ("malformed", "ooxml_invalid_directory")
    payload = bytearray(_package())
    marker = payload.rfind(b"PK\x05\x06")
    payload[marker + 4 : marker + 8] = b"\x01\x00\x00\x00"
    assert _failure(bytes(payload)) == ("malformed", "ooxml_multidisk")
    payload = bytearray(_package())
    marker = payload.rfind(b"PK\x05\x06")
    payload[marker + 10 : marker + 12] = b"\xff\xff"
    assert _failure(bytes(payload)) == ("malformed", "ooxml_zip64")


def test_entry_boundary_is_exact_2000_and_2001() -> None:
    accepted = {f"word/items/{index}.xml": b"<x/>" for index in range(1_997)}
    result = validate_ooxml(_package(additions=accepted), detected_format="docx")
    assert result.entry_count == 2_000
    rejected = {**accepted, "word/items/over.xml": b"<x/>"}
    assert _failure(_package(additions=rejected)) == (
        "limit_exceeded",
        "ooxml_directory_limit",
    )


def test_exact_and_one_over_decompressed_and_directory_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _package()
    baseline = validate_ooxml(payload, detected_format="docx")
    monkeypatch.setattr(ooxml_module, "MAXIMUM_DECOMPRESSED_BYTES", baseline.decompressed_bytes)
    assert validate_ooxml(payload, detected_format="docx") == baseline
    monkeypatch.setattr(
        ooxml_module, "MAXIMUM_DECOMPRESSED_BYTES", baseline.decompressed_bytes - 1
    )
    assert _failure(payload) == ("limit_exceeded", "ooxml_decompressed_limit")

    monkeypatch.setattr(ooxml_module, "MAXIMUM_DECOMPRESSED_BYTES", 128 * 1024 * 1024)
    marker = payload.rfind(b"PK\x05\x06")
    directory_bytes = int.from_bytes(payload[marker + 12 : marker + 16], "little")
    monkeypatch.setattr(ooxml_module, "MAXIMUM_CENTRAL_DIRECTORY_BYTES", directory_bytes)
    validate_ooxml(payload, detected_format="docx")
    monkeypatch.setattr(ooxml_module, "MAXIMUM_CENTRAL_DIRECTORY_BYTES", directory_bytes - 1)
    assert _failure(payload) == ("limit_exceeded", "ooxml_directory_limit")


def test_encrypted_central_directory_flag_rejects_before_body_read() -> None:
    payload = bytearray(_package())
    marker = payload.find(b"PK\x01\x02")
    flags = int.from_bytes(payload[marker + 8 : marker + 10], "little") | 0x1
    payload[marker + 8 : marker + 10] = flags.to_bytes(2, "little")
    assert _failure(bytes(payload)) == ("malformed", "ooxml_encrypted_entry")


def test_all_metadata_rejections_happen_before_any_body_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encrypted = bytearray(_package())
    marker = encrypted.find(b"PK\x01\x02")
    flags = int.from_bytes(encrypted[marker + 8 : marker + 10], "little") | 0x1
    encrypted[marker + 8 : marker + 10] = flags.to_bytes(2, "little")

    special = BytesIO()
    with zipfile.ZipFile(special, "w") as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("_rels/.rels", b"<Relationships/>")
        archive.writestr("word/document.xml", b"<root/>")
        link = zipfile.ZipInfo("word/link.xml")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, b"target")

    payloads = [
        bytes(encrypted),
        _package(additions={"word/A.xml": b"<a/>", "word/a.XML": b"<b/>"}),
        _package(additions={"../escape.xml": b"<x/>"}),
        _package(additions={"unknown/data.xml": b"<x/>"}),
        _package(additions={"ppt/presentation.xml": b"<root/>"}),
        special.getvalue(),
        _package(additions={"word/run.sh": b"echo unsafe"}),
    ]
    reads = 0
    original_read = zipfile.ZipFile.read

    def observed_read(self, *args, **kwargs):
        nonlocal reads
        reads += 1
        return original_read(self, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "read", observed_read)
    for payload in payloads:
        with pytest.raises(OoxmlSecurityFailure):
            validate_ooxml(payload, detected_format="docx")
    assert reads == 0


def test_directory_inventory_conflict_is_rejected() -> None:
    payload = bytearray(_package())
    marker = payload.rfind(b"PK\x05\x06")
    payload[marker + 10 : marker + 12] = (2).to_bytes(2, "little")
    assert _failure(bytes(payload)) == ("malformed", "ooxml_directory_conflict")


def test_corrupt_local_member_header_has_bounded_failure() -> None:
    payload = bytearray(_package())
    marker = payload.find(b"PK\x03\x04")
    name_length = int.from_bytes(payload[marker + 26 : marker + 28], "little")
    assert name_length > 0
    payload[marker + 30] ^= 1
    assert _failure(bytes(payload)) == ("malformed", "ooxml_entry_read_failed")
