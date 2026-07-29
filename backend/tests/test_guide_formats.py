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

    assert (result.status, result.detected_format) == ("classified", expected)


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


@pytest.mark.parametrize(
    ("payload", "media_type", "expected"),
    [
        (b"%PDF-1.7\n", "application/octet-stream", "pdf"),
        (b'{"answer": 42}', "application/json", "json"),
        (b"a,b\n1,2\n", "text/csv", "csv"),
        (b"# Guide\n", "text/markdown", "markdown"),
        (b"Guide text\n", "text/plain", "plain_text"),
    ],
)
def test_classifies_non_container_formats(
    detector: GuideFormatDetector,
    payload: bytes,
    media_type: str,
    expected: str,
) -> None:
    result = detector.detect(BytesIO(payload), declared_media_type=media_type)

    assert (result.status, result.detected_format) == ("classified", expected)


def test_declared_text_with_invalid_utf8_is_malformed(detector: GuideFormatDetector) -> None:
    result = detector.detect(BytesIO(b"\xff\xfe"), declared_media_type="text/plain")

    assert (result.status, result.detected_format) == ("malformed", "plain_text")


def test_approved_text_adapter_classifies_octet_stream(detector: GuideFormatDetector) -> None:
    result = detector.detect(
        BytesIO(b'{"guide": true}'),
        declared_media_type="application/octet-stream",
        ingestion_adapter="json",
    )

    assert (result.status, result.detected_format) == ("classified", "json")


def test_audio_video_and_opaque_binary_are_unsupported(detector: GuideFormatDetector) -> None:
    audio = detector.detect(BytesIO(b"ID3\x00"), declared_media_type="audio/mpeg")
    signed_audio = detector.detect(
        BytesIO(b"OggS" + b"\x00" * 20), declared_media_type="application/octet-stream"
    )
    declared_video = detector.detect(BytesIO(b"video"), declared_media_type="video/mp4")
    signed_video = detector.detect(
        BytesIO(b"\x00\x00\x00\x18ftypisom"),
        declared_media_type="application/octet-stream",
    )
    opaque = detector.detect(
        BytesIO(b"\x00\xff\x00"), declared_media_type="application/octet-stream"
    )

    assert (audio.status, audio.detected_format) == ("unsupported", "audio_video")
    assert (signed_audio.status, signed_audio.detected_format) == ("unsupported", "audio_video")
    assert (declared_video.status, declared_video.detected_format) == (
        "unsupported",
        "audio_video",
    )
    assert (signed_video.status, signed_video.detected_format) == ("unsupported", "audio_video")
    assert (opaque.status, opaque.detected_format) == ("unsupported", "opaque")


def test_image_dimension_limit_is_enforced(detector: GuideFormatDetector) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (20_000).to_bytes(4, "big") + (2).to_bytes(4, "big")

    result = detector.detect(BytesIO(png), declared_media_type="image/png")

    assert result.status == "limit_exceeded"
    assert result.facts == {"width": 20_000, "height": 2}


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


def test_image_pixel_boundary_is_exact() -> None:
    def png(width: int, height: int) -> bytes:
        return (
            b"\x89PNG\r\n\x1a\n"
            + b"\x00" * 8
            + width.to_bytes(4, "big")
            + height.to_bytes(4, "big")
        )

    detector = GuideFormatDetector(
        GuideFormatLimits(maximum_image_pixels=100, maximum_image_dimension=100)
    )

    assert (
        detector.detect(BytesIO(png(10, 10)), declared_media_type="image/png").status
        == "classified"
    )
    assert (
        detector.detect(BytesIO(png(10, 11)), declared_media_type="image/png").status
        == "limit_exceeded"
    )


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


def test_fixed_image_boundaries_are_exact() -> None:
    def png(width: int, height: int) -> BytesIO:
        return BytesIO(
            b"\x89PNG\r\n\x1a\n"
            + b"\x00" * 8
            + width.to_bytes(4, "big")
            + height.to_bytes(4, "big")
        )

    detector = GuideFormatDetector(GuideFormatLimits())

    assert detector.detect(png(16_384, 1), declared_media_type="image/png").status == "classified"
    assert detector.detect(png(16_385, 1), declared_media_type="image/png").status == "limit_exceeded"
    assert detector.detect(png(8_000, 5_000), declared_media_type="image/png").status == "classified"
    assert detector.detect(png(8_000, 5_001), declared_media_type="image/png").status == "limit_exceeded"


@pytest.mark.parametrize(
    "payload",
    [
        b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 7 + b"\x9d\x01\x2a\x02\x00\x03\x00",
        b"RIFF\x00\x00\x00\x00WEBPVP8L" + b"\x00" * 4 + b"\x2f\x01\x08\x00\x00" + b"\x00" * 5,
    ],
)
def test_common_webp_variants_expose_dimensions(
    detector: GuideFormatDetector, payload: bytes
) -> None:
    result = detector.detect(BytesIO(payload), declared_media_type="image/webp")

    assert result.detected_format == "webp"
    assert result.status == "classified"


def test_jpeg_dimensions_classify_and_enforce_limit() -> None:
    def jpeg(width: int, height: int, *, standalone_marker: bytes = b"") -> BytesIO:
        return BytesIO(
            b"\xff\xd8"
            + standalone_marker
            + b"\xff\xc0\x00\x0b\x08"
            + height.to_bytes(2, "big")
            + width.to_bytes(2, "big")
            + b"\x00" * 8
        )

    detector = GuideFormatDetector(
        GuideFormatLimits(maximum_image_pixels=100, maximum_image_dimension=100)
    )

    classified = detector.detect(jpeg(10, 10), declared_media_type="image/jpeg")
    with_restart_marker = detector.detect(
        jpeg(10, 10, standalone_marker=b"\xff\xd0"),
        declared_media_type="image/jpeg",
    )
    over_limit = detector.detect(jpeg(10, 11), declared_media_type="image/jpeg")

    assert (classified.status, classified.detected_format, classified.facts) == (
        "classified",
        "jpeg",
        {"width": 10, "height": 10},
    )
    assert with_restart_marker.facts == {"width": 10, "height": 10}
    assert over_limit.status == "limit_exceeded"
