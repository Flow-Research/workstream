"""Deterministic bounded guide-format classification."""

from __future__ import annotations

from io import BytesIO
import stat
import zipfile

import pytest

from app.modules.artifacts.guide_formats import GuideFormatDetector, GuideFormatLimits


@pytest.fixture
def detector() -> GuideFormatDetector:
    return GuideFormatDetector(GuideFormatLimits())


def _zip(entries: dict[str, bytes], *, compression: int = zipfile.ZIP_STORED) -> BytesIO:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    output.seek(0)
    return output


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        (
            {
                "[Content_Types].xml": b"types",
                "_rels/.rels": b"<Relationships />",
                "word/document.xml": b"document",
            },
            "docx",
        ),
        (
            {
                "[Content_Types].xml": b"types",
                "_rels/.rels": b"<Relationships />",
                "ppt/presentation.xml": b"presentation",
            },
            "pptx",
        ),
        (
            {
                "[Content_Types].xml": b"types",
                "_rels/.rels": b"<Relationships />",
                "xl/workbook.xml": b"workbook",
            },
            "xlsx",
        ),
    ],
)
def test_classifies_exact_ooxml_markers(
    detector: GuideFormatDetector,
    entries: dict[str, bytes],
    expected: str,
) -> None:
    result = detector.detect(_zip(entries), declared_media_type="application/octet-stream")

    assert (result.status, result.detected_format) == (
        "unsupported" if expected == "xlsx" else "classified", expected
    )


def test_ordinary_zip_is_unsupported_not_docx(detector: GuideFormatDetector) -> None:
    result = detector.detect(
        _zip({"document.txt": b"hello"}), declared_media_type="application/zip"
    )

    assert (result.status, result.detected_format) == ("unsupported", "zip")


def test_ambiguous_ooxml_markers_are_not_classified(detector: GuideFormatDetector) -> None:
    result = detector.detect(
        _zip(
            {
                "[Content_Types].xml": b"types",
                "_rels/.rels": b"<Relationships />",
                "word/document.xml": b"document",
                "xl/workbook.xml": b"workbook",
            }
        ),
        declared_media_type="application/octet-stream",
    )

    assert (result.status, result.detected_format) == ("ambiguous", "zip")


def test_malformed_central_directory_is_rejected(detector: GuideFormatDetector) -> None:
    result = detector.detect(BytesIO(b"PK\x03\x04truncated"), declared_media_type="application/zip")

    assert (result.status, result.detected_format) == ("malformed", "zip")


@pytest.mark.parametrize(
    "entries",
    [
        {"../escape.txt": b"no"},
        {"word/vbaProject.bin": b"macro"},
        {"_rels/.rels": b'<Relationship TargetMode="External" />'},
        {"_rels/.rels": b'<Relationship\n TargetMode = "External" />'},
        {"word/embeddings/object.bin": b"embedded"},
        {"payload.exe": b"executable"},
    ],
)
def test_dangerous_container_is_malformed(
    detector: GuideFormatDetector, entries: dict[str, bytes]
) -> None:
    result = detector.detect(_zip(entries), declared_media_type="application/zip")

    assert (result.status, result.detected_format) == ("malformed", "zip")


def test_compression_bomb_ratio_is_bounded(detector: GuideFormatDetector) -> None:
    result = detector.detect(
        _zip({"large.txt": b"x" * 100_000}, compression=zipfile.ZIP_DEFLATED),
        declared_media_type="application/zip",
    )

    assert result.status == "limit_exceeded"


def test_nested_zip_is_inspected(detector: GuideFormatDetector) -> None:
    nested = _zip({"../escape.txt": b"no"}).getvalue()
    result = detector.detect(_zip({"nested.zip": nested}), declared_media_type="application/zip")

    assert result.status == "malformed"












def test_entry_and_decompressed_byte_boundaries_are_exact() -> None:
    entries = {f"item-{index}.txt": b"x" for index in range(3)}
    at_entry_limit = GuideFormatDetector(GuideFormatLimits(maximum_entries=3)).detect(
        _zip(entries), declared_media_type="application/zip"
    )
    over_entry_limit = GuideFormatDetector(GuideFormatLimits(maximum_entries=2)).detect(
        _zip(entries), declared_media_type="application/zip"
    )
    at_byte_limit = GuideFormatDetector(GuideFormatLimits(maximum_decompressed_bytes=3)).detect(
        _zip(entries), declared_media_type="application/zip"
    )
    over_byte_limit = GuideFormatDetector(GuideFormatLimits(maximum_decompressed_bytes=2)).detect(
        _zip(entries), declared_media_type="application/zip"
    )

    assert at_entry_limit.status == "unsupported"
    assert at_byte_limit.status == "unsupported"
    assert over_entry_limit.status == "limit_exceeded"
    assert over_byte_limit.status == "limit_exceeded"


def test_nested_depth_boundary_is_exact() -> None:
    inner = _zip({"guide.txt": b"guide"}).getvalue()
    outer = _zip({"nested.zip": inner})

    at_limit = GuideFormatDetector(GuideFormatLimits(maximum_nesting_depth=1)).detect(
        outer, declared_media_type="application/zip"
    )
    outer.seek(0)
    over_limit = GuideFormatDetector(GuideFormatLimits(maximum_nesting_depth=0)).detect(
        outer, declared_media_type="application/zip"
    )

    assert at_limit.status == "unsupported"
    assert over_limit.status == "limit_exceeded"


def test_nested_archive_member_byte_boundary_is_exact() -> None:
    inner = _zip({"guide.txt": b"guide"}).getvalue()

    at_limit = GuideFormatDetector(
        GuideFormatLimits(maximum_nested_archive_bytes=len(inner))
    ).detect(_zip({"nested.zip": inner}), declared_media_type="application/zip")
    over_limit = GuideFormatDetector(
        GuideFormatLimits(maximum_nested_archive_bytes=len(inner) - 1)
    ).detect(_zip({"nested.zip": inner}), declared_media_type="application/zip")

    assert at_limit.status == "unsupported"
    assert over_limit.status == "limit_exceeded"


def test_symlink_entry_is_rejected(detector: GuideFormatDetector) -> None:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "target")
    output.seek(0)

    result = detector.detect(output, declared_media_type="application/zip")

    assert result.status == "malformed"




def test_fixed_v01_limits_accept_exact_values_and_reject_one_over() -> None:
    limits = GuideFormatLimits()

    assert not limits.archive_totals_exceeded(
        entry_count=2_000,
        decompressed_bytes=128 * 1024 * 1024,
    )
    assert limits.archive_totals_exceeded(
        entry_count=2_001,
        decompressed_bytes=128 * 1024 * 1024,
    )
    assert limits.archive_totals_exceeded(
        entry_count=2_000,
        decompressed_bytes=128 * 1024 * 1024 + 1,
    )
    assert not limits.compression_ratio_exceeded(file_size=10_000, compressed_size=100)
    assert limits.compression_ratio_exceeded(file_size=10_001, compressed_size=100)








@pytest.mark.parametrize("payload,media_type,adapter", [
    (b'{"answer":42}', "application/json", "json"),
    (b"a,b\n1,2\n", "text/csv", "csv"),
    (b"# Guide", "text/markdown", "manual_import"),
    (b"Guide", "text/plain", "upload"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "upload"),
    (b"ID3\x00", "audio/mpeg", "upload"),
    (b"\xff\xfe", "text/plain", "upload"),
])
def test_unsupported_formats_and_removed_adapters_never_activate_text_fallback(detector, payload, media_type, adapter):
    result = detector.detect(BytesIO(payload), declared_media_type=media_type, ingestion_adapter=adapter)
    assert (result.status, result.detected_format, result.facts) == ("unsupported", "opaque", {})


def test_pdf_signature_is_classified_without_extracting_text(detector):
    result = detector.detect(BytesIO(b"%PDF-1.7\n"), declared_media_type="application/pdf")
    assert (result.status, result.detected_format) == ("classified", "pdf")


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-32"])
def test_ooxml_relationship_dtd_is_rejected_in_each_encoding(detector, encoding):
    xml = '<?xml version="1.0"?><!DOCTYPE Relationships [<!ENTITY value "expanded">]><Relationships>&value;</Relationships>'
    result = detector.detect(_zip({"_rels/.rels": xml.encode(encoding)}), declared_media_type="application/zip")
    assert result.status == "malformed"
