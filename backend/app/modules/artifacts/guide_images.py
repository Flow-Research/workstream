"""Bounded structural PNG, JPEG, and WebP metadata extraction."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import binascii
import json
from typing import NoReturn
import warnings

from PIL import Image, UnidentifiedImageError


MAXIMUM_DIMENSION = 16_384
MAXIMUM_PIXELS = 40_000_000
MAXIMUM_FRAMES = 1_000
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SOF = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)
_PNG_COLOR_MODELS = {
    0: "grayscale",
    2: "rgb",
    3: "indexed",
    4: "grayscale_alpha",
    6: "rgba",
}
_PNG_BIT_DEPTHS = {
    0: frozenset({1, 2, 4, 8, 16}),
    2: frozenset({8, 16}),
    3: frozenset({1, 2, 4, 8}),
    4: frozenset({8, 16}),
    6: frozenset({8, 16}),
}


@dataclass(frozen=True, slots=True)
class ImageStructuralFacts:
    detected_format: str
    width: int
    height: int
    frame_count: int
    color_model: str
    bit_depth: int
    transparency: bool


class ImageExtractionFailure(Exception):
    """Carry one stable bounded image extraction outcome."""

    def __init__(self, status: str, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


def _fail(status: str, code: str) -> NoReturn:
    raise ImageExtractionFailure(status, code)


def _enforce_limits(facts: ImageStructuralFacts) -> None:
    if facts.width < 1 or facts.height < 1:
        _fail("malformed", "image_invalid_header")
    if facts.width > MAXIMUM_DIMENSION or facts.height > MAXIMUM_DIMENSION:
        _fail("limit_exceeded", "image_dimension_limit")
    if facts.width * facts.height > MAXIMUM_PIXELS:
        _fail("limit_exceeded", "image_pixel_limit")
    if facts.frame_count < 1:
        _fail("malformed", "image_invalid_header")
    if facts.frame_count > MAXIMUM_FRAMES:
        _fail("limit_exceeded", "image_frame_limit")


def _png(payload: bytes) -> ImageStructuralFacts:
    if not payload.startswith(_PNG_SIGNATURE):
        _fail("malformed", "image_format_mismatch")
    offset = len(_PNG_SIGNATURE)
    ihdr: bytes | None = None
    transparency_length: int | None = None
    frame_count = 1
    animation_control = False
    animation_sequence = 0
    frame_controls = 0
    frame_data_pending = False
    frame_uses_idat = False
    image_data = False
    ended = False
    while offset < len(payload):
        if offset + 12 > len(payload):
            _fail("malformed", "image_truncated")
        length = int.from_bytes(payload[offset : offset + 4], "big")
        kind = payload[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(payload):
            _fail("malformed", "image_truncated")
        body = payload[offset + 8 : offset + 8 + length]
        expected_crc = int.from_bytes(payload[offset + 8 + length : end], "big")
        if binascii.crc32(kind + body) & 0xFFFFFFFF != expected_crc:
            _fail("malformed", "image_invalid_header")
        if ihdr is None:
            if kind != b"IHDR" or length != 13:
                _fail("malformed", "image_invalid_header")
            ihdr = body
        elif kind == b"IHDR":
            _fail("malformed", "image_invalid_header")
        if kind == b"IDAT":
            if frame_controls and not frame_uses_idat:
                _fail("malformed", "image_invalid_header")
            if frame_data_pending and frame_uses_idat:
                frame_data_pending = False
            image_data = True
        elif kind == b"tRNS":
            if image_data or transparency_length is not None:
                _fail("malformed", "image_invalid_header")
            transparency_length = length
        elif kind == b"acTL":
            if animation_control or image_data or length != 8:
                _fail("malformed", "image_invalid_header")
            animation_control = True
            frame_count = int.from_bytes(body[:4], "big")
        elif kind == b"fcTL":
            if not animation_control or length != 26 or frame_data_pending:
                _fail("malformed", "image_invalid_header")
            sequence = int.from_bytes(body[:4], "big")
            frame_width = int.from_bytes(body[4:8], "big")
            frame_height = int.from_bytes(body[8:12], "big")
            x = int.from_bytes(body[12:16], "big")
            y = int.from_bytes(body[16:20], "big")
            canvas_width = int.from_bytes(ihdr[:4], "big")
            canvas_height = int.from_bytes(ihdr[4:8], "big")
            if (
                sequence != animation_sequence
                or frame_width < 1
                or frame_height < 1
                or x + frame_width > canvas_width
                or y + frame_height > canvas_height
                or body[24] > 2
                or body[25] > 1
            ):
                _fail("malformed", "image_invalid_header")
            animation_sequence += 1
            frame_controls += 1
            frame_data_pending = True
            frame_uses_idat = not image_data
        elif kind == b"fdAT":
            if (
                not animation_control
                or not image_data
                or frame_controls < 1
                or frame_uses_idat
                or length < 5
                or int.from_bytes(body[:4], "big") != animation_sequence
            ):
                _fail("malformed", "image_invalid_header")
            animation_sequence += 1
            frame_data_pending = False
        elif kind == b"IEND":
            if length != 0 or end != len(payload):
                _fail("malformed", "image_invalid_header")
            ended = True
            break
        offset = end
    if ihdr is None or not image_data or not ended:
        _fail("malformed", "image_truncated")
    if animation_control and (frame_controls != frame_count or frame_data_pending):
        _fail("malformed", "image_invalid_header")
    width = int.from_bytes(ihdr[:4], "big")
    height = int.from_bytes(ihdr[4:8], "big")
    bit_depth = ihdr[8]
    color_type = ihdr[9]
    if ihdr[10:] != b"\x00\x00\x00" or color_type not in _PNG_COLOR_MODELS:
        _fail("unsupported", "image_color_model")
    if bit_depth not in _PNG_BIT_DEPTHS[color_type]:
        _fail("unsupported", "image_bit_depth")
    if transparency_length is not None:
        valid_transparency = (
            (color_type == 0 and transparency_length == 2)
            or (color_type == 2 and transparency_length == 6)
            or (color_type == 3 and 1 <= transparency_length <= 2**bit_depth)
        )
        if not valid_transparency:
            _fail("malformed", "image_invalid_header")
    facts = ImageStructuralFacts(
        "png",
        width,
        height,
        frame_count,
        _PNG_COLOR_MODELS[color_type],
        bit_depth,
        transparency_length is not None or color_type in {4, 6},
    )
    _enforce_limits(facts)
    return facts


def _jpeg(payload: bytes) -> ImageStructuralFacts:
    if not payload.startswith(b"\xff\xd8"):
        _fail("malformed", "image_format_mismatch")
    if not payload.endswith(b"\xff\xd9"):
        _fail("malformed", "image_truncated")
    offset = 2
    width = height = precision = components = 0
    while offset + 1 < len(payload) - 2:
        if payload[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(payload) and payload[offset] == 0xFF:
            offset += 1
        if offset >= len(payload):
            _fail("malformed", "image_truncated")
        marker = payload[offset]
        offset += 1
        if marker == 0x00 or marker == 0xD9:
            continue
        if marker == 0xDA:
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:
            continue
        if offset + 2 > len(payload):
            _fail("malformed", "image_truncated")
        length = int.from_bytes(payload[offset : offset + 2], "big")
        if length < 2 or offset + length > len(payload):
            _fail("malformed", "image_truncated")
        if marker in _JPEG_SOF:
            if length < 8 or width:
                _fail("malformed", "image_invalid_header")
            precision = payload[offset + 2]
            height = int.from_bytes(payload[offset + 3 : offset + 5], "big")
            width = int.from_bytes(payload[offset + 5 : offset + 7], "big")
            components = payload[offset + 7]
        offset += length
    if not width or not height or not components:
        _fail("malformed", "image_invalid_header")
    if precision != 8:
        _fail("unsupported", "image_bit_depth")
    color_model = {1: "grayscale", 3: "ycbcr", 4: "cmyk"}.get(components)
    if color_model is None:
        _fail("unsupported", "image_color_model")
    facts = ImageStructuralFacts("jpeg", width, height, 1, color_model, 8, False)
    _enforce_limits(facts)
    return facts


def _webp(payload: bytes) -> ImageStructuralFacts:
    if len(payload) < 20 or payload[:4] != b"RIFF" or payload[8:12] != b"WEBP":
        _fail("malformed", "image_format_mismatch")
    declared = int.from_bytes(payload[4:8], "little") + 8
    if declared != len(payload):
        _fail("malformed", "image_truncated")
    offset = 12
    chunks: list[tuple[bytes, bytes]] = []
    while offset < len(payload):
        if offset + 8 > len(payload):
            _fail("malformed", "image_truncated")
        kind = payload[offset : offset + 4]
        length = int.from_bytes(payload[offset + 4 : offset + 8], "little")
        end = offset + 8 + length
        padded_end = end + (length & 1)
        if end > len(payload) or padded_end > len(payload):
            _fail("malformed", "image_truncated")
        chunks.append((kind, payload[offset + 8 : end]))
        offset = padded_end
    if not chunks:
        _fail("malformed", "image_invalid_header")
    first_kind, first = chunks[0]
    frame_count = 1
    transparency = False
    if first_kind == b"VP8X":
        if len(first) != 10 or first[0] & 0xC1 or first[1:4] != b"\x00\x00\x00":
            _fail("malformed", "image_invalid_header")
        flags = first[0]
        transparency = bool(flags & 0x10)
        animated = bool(flags & 0x02)
        width = 1 + int.from_bytes(first[4:7], "little")
        height = 1 + int.from_bytes(first[7:10], "little")
        animation_headers = [body for kind, body in chunks if kind == b"ANIM"]
        animation_frames = [body for kind, body in chunks if kind == b"ANMF"]
        if animated:
            if len(animation_headers) != 1 or len(animation_headers[0]) != 6:
                _fail("malformed", "image_invalid_header")
            for frame in animation_frames:
                if len(frame) < 16 or frame[15] & 0xFC:
                    _fail("malformed", "image_invalid_header")
                x = 2 * int.from_bytes(frame[:3], "little")
                y = 2 * int.from_bytes(frame[3:6], "little")
                frame_width = 1 + int.from_bytes(frame[6:9], "little")
                frame_height = 1 + int.from_bytes(frame[9:12], "little")
                if x + frame_width > width or y + frame_height > height:
                    _fail("malformed", "image_invalid_header")
            frame_count = len(animation_frames)
        elif animation_headers or animation_frames:
            _fail("malformed", "image_invalid_header")
    elif first_kind == b"VP8 ":
        if len(first) < 10 or first[3:6] != b"\x9d\x01\x2a":
            _fail("malformed", "image_invalid_header")
        width = int.from_bytes(first[6:8], "little") & 0x3FFF
        height = int.from_bytes(first[8:10], "little") & 0x3FFF
    elif first_kind == b"VP8L":
        if len(first) < 5 or first[0] != 0x2F or first[4] & 0xE0:
            _fail("malformed", "image_invalid_header")
        width = 1 + first[1] + ((first[2] & 0x3F) << 8)
        height = 1 + (first[2] >> 6) + (first[3] << 2) + ((first[4] & 0x0F) << 10)
        transparency = bool(first[4] & 0x10)
    else:
        _fail("malformed", "image_invalid_header")
    facts = ImageStructuralFacts(
        "webp", width, height, frame_count, "rgba" if transparency else "rgb", 8, transparency
    )
    _enforce_limits(facts)
    return facts


def _header_facts(payload: bytes, detected_format: str) -> ImageStructuralFacts:
    parser = {"png": _png, "jpeg": _jpeg, "webp": _webp}.get(detected_format)
    if parser is None:
        _fail("malformed", "image_format_mismatch")
    return parser(payload)


def _expected_modes(facts: ImageStructuralFacts) -> frozenset[str]:
    if facts.detected_format == "jpeg":
        return {
            "grayscale": frozenset({"L"}),
            "ycbcr": frozenset({"RGB", "YCbCr"}),
            "cmyk": frozenset({"CMYK"}),
        }[facts.color_model]
    if facts.detected_format == "webp":
        return frozenset({"RGBA"}) if facts.transparency else frozenset({"RGB"})
    return {
        "grayscale": frozenset({"1", "L", "I", "I;16", "I;16B"}),
        "grayscale_alpha": frozenset({"LA", "RGBA"}),
        "indexed": frozenset({"P"}),
        "rgb": frozenset({"RGB"}),
        "rgba": frozenset({"RGBA"}),
    }[facts.color_model]


def extract_image(payload: bytes, *, detected_format: str) -> str:
    """Return only canonical structural metadata for one exact image format."""
    facts = _header_facts(payload, detected_format)
    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAXIMUM_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image: Image.Image | None = None
            try:
                image = Image.open(BytesIO(payload))
                if image.format is None or image.format.casefold() != detected_format:
                    _fail("malformed", "image_format_mismatch")
                if image.size != (facts.width, facts.height):
                    _fail("malformed", "image_decoder_mismatch")
                if image.mode not in _expected_modes(facts):
                    _fail("malformed", "image_decoder_mismatch")
                if int(getattr(image, "n_frames", 1)) != facts.frame_count:
                    _fail("malformed", "image_decoder_mismatch")
            except Image.DecompressionBombError as exc:
                raise ImageExtractionFailure("limit_exceeded", "image_decompression_bomb") from exc
            except Image.DecompressionBombWarning as exc:
                raise ImageExtractionFailure("limit_exceeded", "image_decompression_bomb") from exc
            except (OSError, SyntaxError, UnidentifiedImageError, ValueError) as exc:
                raise ImageExtractionFailure("malformed", "image_decoder_rejected") from exc
            finally:
                if image is not None:
                    image.close()
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit
    return json.dumps(
        {
            "bit_depth": facts.bit_depth,
            "color_model": facts.color_model,
            "detected_format": facts.detected_format,
            "frame_count": facts.frame_count,
            "height": facts.height,
            "transparency": facts.transparency,
            "width": facts.width,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
