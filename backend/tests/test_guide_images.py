"""Focused proofs for bounded structural image metadata extraction."""

from __future__ import annotations

from io import BytesIO
import binascii
import json
import zlib

import pytest
from PIL import Image, PngImagePlugin

import app.modules.artifacts.guide_images as image_module
from app.modules.artifacts.guide_formats import GuideFormatDetector, GuideFormatLimits
from app.modules.artifacts.guide_images import (
    ImageExtractionFailure,
    ImageStructuralFacts,
    extract_image,
)


SENTINEL = "PRIVATE-GPS-SECRET-03B3B4"


def _image(format_name: str, *, mode: str = "RGB", size: tuple[int, int] = (3, 2)) -> bytes:
    output = BytesIO()
    image = Image.new(mode, size, 0)
    if format_name == "PNG":
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("private", SENTINEL)
        image.save(output, format=format_name, pnginfo=metadata, icc_profile=SENTINEL.encode())
    elif format_name == "JPEG":
        exif = Image.Exif()
        exif[0x010E] = SENTINEL
        image.save(output, format=format_name, exif=exif, comment=SENTINEL.encode())
    else:
        image.save(
            output,
            format=format_name,
            exif=b"Exif\x00\x00" + SENTINEL.encode(),
            xmp=SENTINEL.encode(),
            icc_profile=SENTINEL.encode(),
        )
    return output.getvalue()


@pytest.mark.parametrize(
    ("detected_format", "format_name", "mode", "color_model", "transparency"),
    [
        ("png", "PNG", "RGB", "rgb", False),
        ("png", "PNG", "RGBA", "rgba", True),
        ("png", "PNG", "L", "grayscale", False),
        ("jpeg", "JPEG", "RGB", "ycbcr", False),
        ("jpeg", "JPEG", "L", "grayscale", False),
        ("jpeg", "JPEG", "CMYK", "cmyk", False),
        ("webp", "WEBP", "RGB", "rgb", False),
        ("webp", "WEBP", "RGBA", "rgba", True),
    ],
)
def test_extracts_only_canonical_structural_metadata(
    detected_format: str,
    format_name: str,
    mode: str,
    color_model: str,
    transparency: bool,
) -> None:
    payload = _image(format_name, mode=mode)
    output = extract_image(payload, detected_format=detected_format)
    assert json.loads(output) == {
        "bit_depth": 8,
        "color_model": color_model,
        "detected_format": detected_format,
        "frame_count": 1,
        "height": 2,
        "transparency": transparency,
        "width": 3,
    }
    assert SENTINEL not in output


@pytest.mark.parametrize(
    ("detected_format", "format_name", "media_type"),
    [
        ("png", "PNG", "image/png"),
        ("jpeg", "JPEG", "image/jpeg"),
        ("webp", "WEBP", "image/webp"),
    ],
)
def test_classifier_and_extractor_agree_on_exact_image_identity(
    detected_format: str, format_name: str, media_type: str
) -> None:
    payload = _image(format_name)
    classification = GuideFormatDetector(GuideFormatLimits()).detect(
        BytesIO(payload), declared_media_type=media_type
    )
    extracted = json.loads(extract_image(payload, detected_format=detected_format))
    assert classification.status == "classified"
    assert classification.detected_format == detected_format
    assert classification.facts == {"width": 3, "height": 2}
    assert (extracted["width"], extracted["height"]) == (3, 2)


@pytest.mark.parametrize(
    ("payload", "detected_format", "code"),
    [
        (b"not-image", "png", "image_format_mismatch"),
        (b"not-image", "jpeg", "image_format_mismatch"),
        (b"not-image", "webp", "image_format_mismatch"),
        (
            b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR" + b"\0" * 17,
            "png",
            "image_invalid_header",
        ),
        (b"\x89PNG\r\n\x1a\n", "png", "image_truncated"),
        (b"\xff\xd8\xff\xd9", "jpeg", "image_invalid_header"),
        (_image("JPEG")[:-2], "jpeg", "image_truncated"),
        (b"RIFF\x10\x00\x00\x00WEBPUNKN\x04\x00\x00\x00bad!", "webp", "image_invalid_header"),
        (_image("WEBP")[:-1], "webp", "image_truncated"),
    ],
)
def test_malformed_and_truncated_images_fail_with_stable_codes(
    payload: bytes, detected_format: str, code: str
) -> None:
    with pytest.raises(ImageExtractionFailure) as raised:
        extract_image(payload, detected_format=detected_format)
    assert raised.value.status == "malformed"
    assert raised.value.code == code


def _replace_png_ihdr_dimensions(payload: bytes, width: int, height: int) -> bytes:
    body = width.to_bytes(4, "big") + height.to_bytes(4, "big") + payload[24:29]
    crc = binascii.crc32(b"IHDR" + body).to_bytes(4, "big")
    return payload[:16] + body + crc + payload[33:]


def test_dimension_and_pixel_limits_run_before_decoder_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _image("PNG")
    decoder_called = False

    def decoder(_payload):
        nonlocal decoder_called
        decoder_called = True
        raise AssertionError("decoder must not run")

    monkeypatch.setattr(image_module.Image, "open", decoder)
    with pytest.raises(ImageExtractionFailure) as dimension:
        extract_image(_replace_png_ihdr_dimensions(payload, 16_385, 1), detected_format="png")
    assert (dimension.value.status, dimension.value.code) == (
        "limit_exceeded",
        "image_dimension_limit",
    )
    with pytest.raises(ImageExtractionFailure) as pixels:
        extract_image(_replace_png_ihdr_dimensions(payload, 3_015, 13_267), detected_format="png")
    assert (pixels.value.status, pixels.value.code) == (
        "limit_exceeded",
        "image_pixel_limit",
    )
    assert decoder_called is False


def test_exact_limit_constants_and_boundary_transitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        image_module.MAXIMUM_DIMENSION,
        image_module.MAXIMUM_PIXELS,
        image_module.MAXIMUM_FRAMES,
    ) == (16_384, 40_000_000, 1_000)
    image_module._enforce_limits(ImageStructuralFacts("png", 8_000, 5_000, 1_000, "rgb", 8, False))
    with pytest.raises(ImageExtractionFailure) as frame:
        image_module._enforce_limits(ImageStructuralFacts("png", 1, 1, 1_001, "rgb", 8, False))
    assert frame.value.code == "image_frame_limit"
    with pytest.raises(ImageExtractionFailure) as dimension:
        image_module._enforce_limits(ImageStructuralFacts("png", 16_385, 1, 1, "rgb", 8, False))
    assert dimension.value.code == "image_dimension_limit"
    monkeypatch.setattr(image_module, "MAXIMUM_PIXELS", 5)
    image_module._enforce_limits(ImageStructuralFacts("png", 5, 1, 1, "rgb", 8, False))
    with pytest.raises(ImageExtractionFailure) as one_over:
        image_module._enforce_limits(ImageStructuralFacts("png", 6, 1, 1, "rgb", 8, False))
    assert one_over.value.code == "image_pixel_limit"


@pytest.mark.parametrize(
    ("facts", "code"),
    [
        (ImageStructuralFacts("png", 0, 1, 1, "rgb", 8, False), "image_invalid_header"),
        (ImageStructuralFacts("png", 1, 1, 0, "rgb", 8, False), "image_invalid_header"),
    ],
)
def test_non_positive_structural_facts_fail_closed(facts: ImageStructuralFacts, code: str) -> None:
    with pytest.raises(ImageExtractionFailure) as raised:
        image_module._enforce_limits(facts)
    assert raised.value.code == code


def test_decoder_mismatch_and_rejection_are_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _image("PNG")

    class Mismatch:
        format = "PNG"
        size = (99, 99)
        mode = "RGB"
        n_frames = 1

        def close(self) -> None:
            pass

    monkeypatch.setattr(image_module.Image, "open", lambda _source: Mismatch())
    with pytest.raises(ImageExtractionFailure) as mismatch:
        extract_image(payload, detected_format="png")
    assert (mismatch.value.status, mismatch.value.code) == (
        "malformed",
        "image_decoder_mismatch",
    )

    monkeypatch.setattr(
        image_module.Image, "open", lambda _source: (_ for _ in ()).throw(OSError(SENTINEL))
    )
    with pytest.raises(ImageExtractionFailure) as rejected:
        extract_image(payload, detected_format="png")
    assert (rejected.value.status, rejected.value.code) == (
        "malformed",
        "image_decoder_rejected",
    )
    assert SENTINEL not in str(rejected.value)


@pytest.mark.parametrize(
    ("attribute", "value", "code"),
    [
        ("format", "JPEG", "image_format_mismatch"),
        ("mode", "CMYK", "image_decoder_mismatch"),
        ("n_frames", 2, "image_decoder_mismatch"),
    ],
)
def test_decoder_identity_disagreement_fails_closed(
    monkeypatch: pytest.MonkeyPatch, attribute: str, value: object, code: str
) -> None:
    payload = _image("PNG")

    class Decoder:
        format = "PNG"
        size = (3, 2)
        mode = "RGB"
        n_frames = 1
        closed = False

        def close(self) -> None:
            self.closed = True

    decoder = Decoder()
    setattr(decoder, attribute, value)
    monkeypatch.setattr(image_module.Image, "open", lambda _source: decoder)
    with pytest.raises(ImageExtractionFailure) as raised:
        extract_image(payload, detected_format="png")
    assert raised.value.code == code
    assert decoder.closed is True


@pytest.mark.parametrize("format_name", ["PNG", "WEBP"])
def test_animated_images_report_exact_frame_count(format_name: str) -> None:
    output = BytesIO()
    frames = [
        Image.new("RGBA", (2, 2), (255, 0, 0, 255)),
        Image.new("RGBA", (2, 2), (0, 0, 255, 255)),
    ]
    frames[0].save(
        output,
        format=format_name,
        save_all=True,
        append_images=frames[1:],
        duration=10,
        loop=0,
    )
    detected_format = format_name.casefold()
    result = json.loads(extract_image(output.getvalue(), detected_format=detected_format))
    assert result["frame_count"] == 2


def test_lossless_webp_uses_structural_alpha_and_dimensions() -> None:
    output = BytesIO()
    Image.new("RGBA", (7, 5), (1, 2, 3, 4)).save(output, format="WEBP", lossless=True)
    result = json.loads(extract_image(output.getvalue(), detected_format="webp"))
    assert (result["width"], result["height"], result["transparency"]) == (7, 5, True)


def _png_chunk(kind: bytes, body: bytes) -> bytes:
    return (
        len(body).to_bytes(4, "big")
        + kind
        + body
        + (binascii.crc32(kind + body) & 0xFFFFFFFF).to_bytes(4, "big")
    )


def _png_with_chunks(*chunks: tuple[bytes, bytes]) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"".join(_png_chunk(*chunk) for chunk in chunks)


def _structural_apng(frame_count: int, *, declared_count: int | None = None) -> bytes:
    chunks: list[tuple[bytes, bytes]] = [
        (b"IHDR", b"\0\0\0\1\0\0\0\1\x08\x06\0\0\0"),
        (
            b"acTL",
            (declared_count if declared_count is not None else frame_count).to_bytes(4, "big")
            + b"\0" * 4,
        ),
    ]
    sequence = 0
    for frame_index in range(frame_count):
        frame_control = (
            sequence.to_bytes(4, "big") + b"\0\0\0\1\0\0\0\1" + b"\0" * 8 + b"\0\0\0\x01\0\0"
        )
        chunks.append((b"fcTL", frame_control))
        sequence += 1
        if frame_index == 0:
            chunks.append((b"IDAT", b"x"))
        else:
            chunks.append((b"fdAT", sequence.to_bytes(4, "big") + b"x"))
            sequence += 1
    if frame_count == 0:
        chunks.append((b"IDAT", b"x"))
    chunks.append((b"IEND", b""))
    return _png_with_chunks(*chunks)


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        (
            _png_with_chunks((b"IHDR", b"\0" * 13), (b"IEND", b"")),
            "malformed",
            "image_truncated",
        ),
        (
            _png_with_chunks(
                (b"IHDR", b"\0\0\0\1\0\0\0\1\x08\x05\0\0\0"),
                (b"IDAT", b"x"),
                (b"IEND", b""),
            ),
            "unsupported",
            "image_color_model",
        ),
        (
            _png_with_chunks(
                (b"IHDR", b"\0\0\0\1\0\0\0\1\x01\x02\0\0\0"),
                (b"IDAT", b"x"),
                (b"IEND", b""),
            ),
            "unsupported",
            "image_bit_depth",
        ),
        (
            _png_with_chunks(
                (b"IHDR", b"\0\0\0\1\0\0\0\1\x08\x02\0\0\0"),
                (b"acTL", (0).to_bytes(4, "big") + b"\0" * 4),
                (b"IDAT", b"x"),
                (b"IEND", b""),
            ),
            "malformed",
            "image_invalid_header",
        ),
    ],
)
def test_png_structural_failures_precede_decoder(payload: bytes, status: str, code: str) -> None:
    with pytest.raises(ImageExtractionFailure) as raised:
        extract_image(payload, detected_format="png")
    assert (raised.value.status, raised.value.code) == (status, code)


def test_apng_frame_declarations_are_independently_counted() -> None:
    assert image_module._png(_structural_apng(2)).frame_count == 2


@pytest.mark.parametrize("actual_frames", [0, 1])
def test_apng_conflicting_frame_declarations_fail_before_decoder(
    monkeypatch: pytest.MonkeyPatch, actual_frames: int
) -> None:
    decoder_called = False

    def decoder(_payload):
        nonlocal decoder_called
        decoder_called = True

    monkeypatch.setattr(image_module.Image, "open", decoder)
    with pytest.raises(ImageExtractionFailure) as raised:
        extract_image(_structural_apng(actual_frames, declared_count=2), detected_format="png")
    assert raised.value.code == "image_invalid_header"
    assert decoder_called is False


def test_apng_exact_frame_limit_and_one_over_precede_decoder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert image_module._png(_structural_apng(1_000)).frame_count == 1_000
    decoder_called = False

    def decoder(_payload):
        nonlocal decoder_called
        decoder_called = True

    monkeypatch.setattr(image_module.Image, "open", decoder)
    with pytest.raises(ImageExtractionFailure) as raised:
        extract_image(_structural_apng(1_001), detected_format="png")
    assert raised.value.code == "image_frame_limit"
    assert decoder_called is False


def test_png_crc_and_trailing_bytes_fail_closed() -> None:
    payload = bytearray(_image("PNG"))
    payload[29] ^= 1
    with pytest.raises(ImageExtractionFailure) as crc:
        extract_image(bytes(payload), detected_format="png")
    assert crc.value.code == "image_invalid_header"
    with pytest.raises(ImageExtractionFailure) as trailing:
        extract_image(_image("PNG") + b"secret", detected_format="png")
    assert trailing.value.code == "image_invalid_header"


@pytest.mark.parametrize(
    "payload",
    [
        b"\x89PNG\r\n\x1a\n" + b"\0" * 11,
        b"\x89PNG\r\n\x1a\n" + (100).to_bytes(4, "big") + b"IHDR" + b"short",
        _png_with_chunks((b"IDAT", b"x"), (b"IEND", b"")),
        _png_with_chunks(
            (b"IHDR", b"\0\0\0\1\0\0\0\1\x08\x02\0\0\0"),
            (b"IHDR", b"\0\0\0\1\0\0\0\1\x08\x02\0\0\0"),
            (b"IDAT", b"x"),
            (b"IEND", b""),
        ),
        _png_with_chunks(
            (b"IHDR", b"\0\0\0\1\0\0\0\1\x08\x02\0\0\0"),
            (b"acTL", b"\0\0\0\1" + b"\0" * 4),
            (b"acTL", b"\0\0\0\1" + b"\0" * 4),
            (b"IDAT", b"x"),
            (b"IEND", b""),
        ),
    ],
)
def test_png_chunk_structure_is_bounded(payload: bytes) -> None:
    with pytest.raises(ImageExtractionFailure):
        image_module._png(payload)


def test_png_transparency_marker_is_semantic() -> None:
    payload = _png_with_chunks(
        (b"IHDR", b"\0\0\0\1\0\0\0\1\x08\x02\0\0\0"),
        (b"tRNS", b"\0" * 6),
        (b"IDAT", b"x"),
        (b"IEND", b""),
    )
    assert image_module._png(payload).transparency is True


def test_sixteen_bit_grayscale_alpha_preserves_header_semantics() -> None:
    payload = _png_with_chunks(
        (b"IHDR", b"\0\0\0\1\0\0\0\1\x10\x04\0\0\0"),
        (b"IDAT", zlib.compress(b"\0\x80\0\xff\xff")),
        (b"IEND", b""),
    )
    assert json.loads(extract_image(payload, detected_format="png")) == {
        "bit_depth": 16,
        "color_model": "grayscale_alpha",
        "detected_format": "png",
        "frame_count": 1,
        "height": 1,
        "transparency": True,
        "width": 1,
    }


@pytest.mark.parametrize(
    "color_type,bit_depth,transparency_body,after_image_data",
    [
        (4, 8, b"\0\0", False),
        (6, 8, b"\0" * 6, False),
        (0, 8, b"\0", False),
        (2, 8, b"\0" * 2, False),
        (3, 1, b"\0" * 3, False),
        (2, 8, b"\0" * 6, True),
    ],
)
def test_png_invalid_transparency_markers_fail_closed(
    color_type: int,
    bit_depth: int,
    transparency_body: bytes,
    after_image_data: bool,
) -> None:
    ihdr = b"\0\0\0\1\0\0\0\1" + bytes([bit_depth, color_type]) + b"\0\0\0"
    trns = (b"tRNS", transparency_body)
    idat = (b"IDAT", b"x")
    middle = (idat, trns) if after_image_data else (trns, idat)
    payload = _png_with_chunks((b"IHDR", ihdr), *middle, (b"IEND", b""))
    with pytest.raises(ImageExtractionFailure) as raised:
        image_module._png(payload)
    assert raised.value.code == "image_invalid_header"


@pytest.mark.parametrize(
    ("precision", "components", "status", "code"),
    [
        (12, 3, "unsupported", "image_bit_depth"),
        (8, 2, "unsupported", "image_color_model"),
    ],
)
def test_jpeg_structural_modes_are_closed(
    precision: int, components: int, status: str, code: str
) -> None:
    sof_body = bytes([precision]) + b"\0\x01\0\x01" + bytes([components]) + b"\0" * (components * 3)
    segment = b"\xff\xc0" + (len(sof_body) + 2).to_bytes(2, "big") + sof_body
    payload = b"\xff\xd8" + segment + b"\xff\xd9"
    with pytest.raises(ImageExtractionFailure) as raised:
        extract_image(payload, detected_format="jpeg")
    assert (raised.value.status, raised.value.code) == (status, code)


@pytest.mark.parametrize(
    "payload",
    [
        b"wrong",
        b"\xff\xd8truncated",
        b"\xff\xd8x\xff\xd9",
        b"\xff\xd8\xff\xe0\x00\xff\xff\xd9",
        b"\xff\xd8\xff\xe0\x00\x01\xff\xd9",
        b"\xff\xd8\xff\xc0\x00\x07" + b"\0" * 5 + b"\xff\xd9",
    ],
)
def test_jpeg_marker_structure_is_bounded(payload: bytes) -> None:
    with pytest.raises(ImageExtractionFailure):
        image_module._jpeg(payload)


@pytest.mark.parametrize(
    "payload",
    [
        b"RIFF\x10\x00\x00\x00WEBPVP8X\x04\x00\x00\x00bad!",
        b"RIFF\x10\x00\x00\x00WEBPUNKN\x04\x00\x00\x00bad!",
    ],
)
def test_webp_invalid_primary_chunks_fail_closed(payload: bytes) -> None:
    with pytest.raises(ImageExtractionFailure) as raised:
        extract_image(payload, detected_format="webp")
    assert raised.value.code == "image_invalid_header"


@pytest.mark.parametrize(
    "payload",
    [
        b"RIFF\x0c\x00\x00\x00WEBPshort!!!",
        b"RIFF\x0c\x00\x00\x00WEBPVP8 \x08\x00\x00\x00bad!",
        b"RIFF\x0c\x00\x00\x00WEBP",
    ],
)
def test_webp_chunk_structure_is_bounded(payload: bytes) -> None:
    with pytest.raises(ImageExtractionFailure):
        image_module._webp(payload)


def test_unknown_detected_format_fails_closed() -> None:
    with pytest.raises(ImageExtractionFailure) as raised:
        extract_image(_image("PNG"), detected_format="gif")
    assert raised.value.code == "image_format_mismatch"


def test_decoder_bomb_outcomes_are_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _image("PNG")
    for failure in (
        Image.DecompressionBombError("private"),
        Image.DecompressionBombWarning("private"),
    ):
        monkeypatch.setattr(
            image_module.Image,
            "open",
            lambda _source, failure=failure: (_ for _ in ()).throw(failure),
        )
        with pytest.raises(ImageExtractionFailure) as raised:
            extract_image(payload, detected_format="png")
        assert (raised.value.status, raised.value.code) == (
            "limit_exceeded",
            "image_decompression_bomb",
        )
