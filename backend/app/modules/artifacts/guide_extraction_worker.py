"""Descriptor-only standard-library guide extraction child."""

from __future__ import annotations

import csv
import ctypes
from io import StringIO
import json
import math
import os
import re
import resource
import sys
from typing import Callable


_ALLOW = 0x7FFF0000
_ERRNO_EPERM = 0x00050001
_MAXIMUM_INPUT_BYTES = 32 * 1024 * 1024
_INVALID_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_ALLOWED_SYSCALLS = (
    "read",
    "write",
    "close",
    "fstat",
    "lseek",
    "mmap",
    "mprotect",
    "mremap",
    "munmap",
    "brk",
    "madvise",
    "futex",
    "clock_gettime",
    "rt_sigaction",
    "rt_sigprocmask",
    "rt_sigreturn",
    "sigaltstack",
    "getrandom",
    "exit",
    "exit_group",
)


class ExtractionFailure(Exception):
    """Carry one bounded child outcome."""

    def __init__(self, status: str, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


def _install_limits(*, cpu_soft_seconds: int = 29, cpu_hard_seconds: int = 30) -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_soft_seconds, cpu_hard_seconds))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    if hasattr(resource, "RLIMIT_NPROC"):
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))


def _install_seccomp() -> None:
    try:
        library = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    except OSError as exc:
        raise ExtractionFailure("parser_failure", "isolation_unavailable") from exc
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_rule_add.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    library.seccomp_rule_add.restype = ctypes.c_int
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_load.restype = ctypes.c_int
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    context = library.seccomp_init(_ERRNO_EPERM)
    if not context:
        raise ExtractionFailure("parser_failure", "isolation_unavailable")
    try:
        for name in _ALLOWED_SYSCALLS:
            number = library.seccomp_syscall_resolve_name(name.encode("ascii"))
            if number < 0 or library.seccomp_rule_add(context, _ALLOW, number, 0) != 0:
                raise ExtractionFailure("parser_failure", "isolation_unavailable")
        if library.seccomp_load(context) != 0:
            raise ExtractionFailure("parser_failure", "isolation_unavailable")
    finally:
        library.seccomp_release(context)


def _decode_text(payload: bytes) -> str:
    if payload.startswith(b"\xef\xbb\xbf"):
        payload = payload[3:]
    if b"\xef\xbb\xbf" in payload:
        raise ExtractionFailure("malformed", "invalid_encoding")
    try:
        value = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExtractionFailure("malformed", "invalid_encoding") from exc
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    if _INVALID_CONTROL.search(value):
        raise ExtractionFailure("malformed", "invalid_control_character")
    return value


def _reject_constant(_: str) -> None:
    raise ExtractionFailure("malformed", "invalid_json_number")


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ExtractionFailure("malformed", "duplicate_json_key")
        result[key] = value
    return result


def _validate_json(value: object, depth: int = 0) -> None:
    if isinstance(value, (dict, list)):
        if depth > 64:
            raise ExtractionFailure("limit_exceeded", "json_nesting_limit")
        values = value.values() if isinstance(value, dict) else value
        for child in values:
            _validate_json(child, depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ExtractionFailure("malformed", "invalid_json_number")


def _extract(
    payload: bytes,
    detected_format: str,
    pdf_extractor: Callable[[bytes], str] | None = None,
    docx_extractor: Callable[[bytes], tuple[str, dict[str, bool]]] | None = None,
    pptx_extractor: Callable[[bytes], tuple[str, dict[str, bool]]] | None = None,
    xlsx_extractor: Callable[[bytes], tuple[str, dict[str, bool]]] | None = None,
    image_extractor: Callable[[bytes], str] | None = None,
) -> str | tuple[str, dict[str, bool]]:
    if detected_format == "pdf":
        if pdf_extractor is None:
            raise ExtractionFailure("parser_failure", "parser_unavailable")
        return pdf_extractor(payload)
    if detected_format == "docx":
        if docx_extractor is None:
            raise ExtractionFailure("parser_failure", "parser_unavailable")
        return docx_extractor(payload)
    if detected_format == "pptx":
        if pptx_extractor is None:
            raise ExtractionFailure("parser_failure", "parser_unavailable")
        return pptx_extractor(payload)
    if detected_format == "xlsx":
        if xlsx_extractor is None:
            raise ExtractionFailure("parser_failure", "parser_unavailable")
        return xlsx_extractor(payload)
    if detected_format in {"png", "jpeg", "webp"}:
        if image_extractor is None:
            raise ExtractionFailure("parser_failure", "parser_unavailable")
        return image_extractor(payload)
    text = _decode_text(payload)
    if detected_format in {"plain_text", "markdown"}:
        return text
    if detected_format == "json":
        try:
            value = json.loads(text, object_pairs_hook=_object, parse_constant=_reject_constant)
        except ExtractionFailure:
            raise
        except (json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise ExtractionFailure("malformed", "invalid_json") from exc
        _validate_json(value, 1)
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if detected_format == "csv":
        rows: list[list[str]] = []
        cells = 0
        try:
            csv.field_size_limit(_MAXIMUM_INPUT_BYTES + 1)
            reader = csv.reader(StringIO(text, newline=""), dialect="excel", strict=True)
            for row in reader:
                if len(rows) >= 100_000:
                    raise ExtractionFailure("limit_exceeded", "csv_row_limit")
                cells += len(row)
                if cells > 1_000_000:
                    raise ExtractionFailure("limit_exceeded", "csv_cell_limit")
                if any(len(cell) > 32_768 for cell in row):
                    raise ExtractionFailure("limit_exceeded", "csv_cell_size_limit")
                rows.append(row)
        except csv.Error as exc:
            raise ExtractionFailure("malformed", "invalid_csv") from exc
        return json.dumps(rows, separators=(",", ":"), ensure_ascii=False)
    raise ExtractionFailure("unsupported", "unsupported_format")


def _load_pdf_extractor() -> Callable[[bytes], str]:
    """Load the approved adapter after limits but before descriptor-only seccomp."""
    from app.modules.artifacts.guide_pdf import PdfExtractionFailure, extract_pdf

    def bounded_extract(payload: bytes) -> str:
        try:
            return extract_pdf(payload)
        except PdfExtractionFailure as exc:
            raise ExtractionFailure(exc.status, exc.code) from exc

    return bounded_extract


def _load_ooxml_security() -> Callable[[bytes, str], object]:
    """Load the approved shared OOXML validator for later format adapters."""
    from app.modules.artifacts.guide_ooxml import OoxmlSecurityFailure, validate_ooxml

    def bounded_validate(payload: bytes, detected_format: str) -> object:
        try:
            return validate_ooxml(payload, detected_format=detected_format)
        except OoxmlSecurityFailure as exc:
            raise ExtractionFailure(exc.status, exc.code) from exc

    return bounded_validate


def _load_docx_extractor(
    validate_ooxml: Callable[[bytes, str], object],
) -> Callable[[bytes], tuple[str, dict[str, bool]]]:
    """Load the DOCX adapter after limits but before descriptor-only seccomp."""
    from app.modules.artifacts.guide_docx import DocxExtractionFailure, extract_docx

    def bounded_extract(payload: bytes) -> tuple[str, dict[str, bool]]:
        try:
            extracted = extract_docx(
                payload,
                validate_ooxml=lambda exact_payload: validate_ooxml(exact_payload, "docx"),
            )
        except DocxExtractionFailure as exc:
            raise ExtractionFailure(exc.status, exc.code) from exc
        return extracted.canonical_output, extracted.omission_facts

    return bounded_extract


def _load_pptx_extractor(
    validate_ooxml: Callable[[bytes, str], object],
) -> Callable[[bytes], tuple[str, dict[str, bool]]]:
    """Load the PPTX adapter after limits but before descriptor-only seccomp."""
    from app.modules.artifacts.guide_pptx import PptxExtractionFailure, extract_pptx

    def bounded_extract(payload: bytes) -> tuple[str, dict[str, bool]]:
        try:
            extracted = extract_pptx(
                payload,
                validate_ooxml=lambda exact_payload: validate_ooxml(exact_payload, "pptx"),
            )
        except PptxExtractionFailure as exc:
            raise ExtractionFailure(exc.status, exc.code) from exc
        return extracted.canonical_output, extracted.omission_facts

    return bounded_extract


def _load_xlsx_extractor(
    validate_ooxml: Callable[[bytes, str], object],
) -> Callable[[bytes], tuple[str, dict[str, bool]]]:
    """Load the XLSX adapter after limits but before descriptor-only seccomp."""
    from app.modules.artifacts.guide_xlsx import XlsxExtractionFailure, extract_xlsx

    def bounded_extract(payload: bytes) -> tuple[str, dict[str, bool]]:
        try:
            extracted = extract_xlsx(
                payload,
                validate_ooxml=lambda exact_payload: validate_ooxml(exact_payload, "xlsx"),
            )
        except XlsxExtractionFailure as exc:
            raise ExtractionFailure(exc.status, exc.code) from exc
        return extracted.canonical_output, extracted.omission_facts

    return bounded_extract


def _load_image_extractor(detected_format: str) -> Callable[[bytes], str]:
    """Load approved native image plugins before descriptor-only seccomp."""
    from PIL import Image

    from app.modules.artifacts.guide_images import ImageExtractionFailure, extract_image

    Image.init()

    def bounded_extract(payload: bytes) -> str:
        try:
            return extract_image(payload, detected_format=detected_format)
        except ImageExtractionFailure as exc:
            raise ExtractionFailure(exc.status, exc.code) from exc

    return bounded_extract


def main() -> int:
    """Apply resource/isolation controls and emit one bounded JSON result."""
    detected_format = sys.argv[1] if len(sys.argv) == 2 else ""
    try:
        _install_limits()
        pdf_extractor = None
        docx_extractor = None
        pptx_extractor = None
        xlsx_extractor = None
        image_extractor = None
        if detected_format == "pdf":
            pdf_extractor = _load_pdf_extractor()
        elif detected_format == "docx":
            docx_extractor = _load_docx_extractor(_load_ooxml_security())
        elif detected_format == "pptx":
            pptx_extractor = _load_pptx_extractor(_load_ooxml_security())
        elif detected_format == "xlsx":
            xlsx_extractor = _load_xlsx_extractor(_load_ooxml_security())
        elif detected_format in {"png", "jpeg", "webp"}:
            image_extractor = _load_image_extractor(detected_format)
        _install_seccomp()
        payload = sys.stdin.buffer.read(_MAXIMUM_INPUT_BYTES + 1)
        if len(payload) > _MAXIMUM_INPUT_BYTES:
            raise ExtractionFailure("limit_exceeded", "input_limit")
        extracted = _extract(
            payload,
            detected_format,
            pdf_extractor,
            docx_extractor,
            pptx_extractor,
            xlsx_extractor,
            image_extractor,
        )
        if isinstance(extracted, tuple):
            output, omission_facts = extracted
        else:
            output = extracted
            omission_facts = {"truncated": False, "omitted": False}
        if len(output.encode("utf-8")) > 4 * 1024 * 1024:
            raise ExtractionFailure("limit_exceeded", "output_limit")
        result = {
            "status": "extracted",
            "error_code": None,
            "output": output,
            "omission_facts": omission_facts,
        }
    except ExtractionFailure as exc:
        result = {
            "status": exc.status,
            "error_code": exc.code,
            "output": None,
            "omission_facts": {"truncated": False, "omitted": False},
        }
    except MemoryError:
        result = {
            "status": "limit_exceeded",
            "error_code": "memory_limit",
            "output": None,
            "omission_facts": {"truncated": False, "omitted": False},
        }
    except BaseException:
        result = {
            "status": "parser_failure",
            "error_code": "parser_failure",
            "output": None,
            "omission_facts": {"truncated": False, "omitted": False},
        }
    encoded = json.dumps(result, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    view = memoryview(encoded)
    while view:
        written = os.write(1, view)
        if written <= 0:
            raise OSError("guide extraction result write made no progress")
        view = view[written:]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
