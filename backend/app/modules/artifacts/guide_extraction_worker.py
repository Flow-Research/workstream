"""Descriptor-only standard-library guide extraction child."""

from __future__ import annotations

import csv
import ctypes
from io import StringIO
import json
import math
import os
import resource
import sys
import unicodedata


_ALLOW = 0x7FFF0000
_ERRNO_EPERM = 0x00050001
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
            if number >= 0 and library.seccomp_rule_add(context, _ALLOW, number, 0) != 0:
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
    if any(
        unicodedata.category(character) == "Cc" and character not in "\t\n" for character in value
    ):
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


def _extract(payload: bytes, detected_format: str) -> str:
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


def main() -> int:
    """Apply resource/isolation controls and emit one bounded JSON result."""
    detected_format = sys.argv[1] if len(sys.argv) == 2 else ""
    try:
        _install_limits()
        _install_seccomp()
        payload = sys.stdin.buffer.read(32 * 1024 * 1024 + 1)
        if len(payload) > 32 * 1024 * 1024:
            raise ExtractionFailure("limit_exceeded", "input_limit")
        output = _extract(payload, detected_format)
        if len(output.encode("utf-8")) > 4 * 1024 * 1024:
            raise ExtractionFailure("limit_exceeded", "output_limit")
        result = {"status": "extracted", "error_code": None, "output": output}
    except ExtractionFailure as exc:
        result = {"status": exc.status, "error_code": exc.code, "output": None}
    except MemoryError:
        result = {"status": "limit_exceeded", "error_code": "memory_limit", "output": None}
    except BaseException:
        result = {"status": "parser_failure", "error_code": "parser_failure", "output": None}
    encoded = json.dumps(result, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    os.write(1, encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
