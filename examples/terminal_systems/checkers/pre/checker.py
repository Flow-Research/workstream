"""Terminal Systems intake rules; no imports from Workstream or task execution."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tomllib

REQUIRED_FILES = ("instruction.md", "task.toml", "AUTHOR_NOTES.md")
REQUIRED_DIRECTORIES = ("environment", "workspace", "solution", "tests")
# Execution capacity, not a contributor size rule. Exceeding this is infra failure.
METADATA_READ_CAPACITY = 4 * 1024 * 1024
REQUEST_READ_CAPACITY = 2 * 1024 * 1024
RESOURCE_FIELDS = (
    "cpu_millis",
    "memory_bytes",
    "disk_bytes",
    "build_timeout_seconds",
    "reference_timeout_seconds",
    "verification_timeout_seconds",
)


class InfrastructureFailure(Exception):
    """A checker could not evaluate the work; no contributor verdict is valid."""


def finding(check: str, code: str, message: str, path: str | None = None) -> dict:
    """Use only fixed, guide-derived prose and known-safe locations in findings."""
    return {
        "check_id": check,
        "code": code,
        "level": "error",
        "message": message,
        "path": path,
        "line": None,
    }


def entry_type(root: Path, path: str) -> str | None:
    """Inspect the material without following links, including parent links."""
    current = root
    try:
        for part in path.split("/"):
            current = current / part
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode):
                return "other"
        if stat.S_ISREG(mode):
            return "file"
        if stat.S_ISDIR(mode):
            return "directory"
        return "other"
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as exc:
        raise InfrastructureFailure("material_unavailable") from exc


def layout(root: Path) -> list[dict]:
    """Enforce required root types, without restricting subjects or extra files."""
    findings = []
    for paths, expected in (
        (REQUIRED_FILES, "file"),
        (REQUIRED_DIRECTORIES, "directory"),
    ):
        for path in paths:
            actual = entry_type(root, path)
            if actual is None:
                findings.append(
                    finding(
                        "package_layout",
                        f"layout_missing_required_{expected}",
                        f"Add the required root {expected}: {path}.",
                        path,
                    )
                )
            elif actual != expected:
                findings.append(
                    finding(
                        "package_layout",
                        "layout_wrong_entry_type",
                        f"The root entry {path} must be a regular {expected}.",
                        path,
                    )
                )
    if findings:
        try:
            # Bounded wrapper detection: only exactly one root entry can be a wrapper.
            with os.scandir(root) as entries:
                first = next(entries, None)
                only = first if next(entries, None) is None else None
            if only is not None and only.is_dir(follow_symlinks=False):
                nested = root / only.name
                if all(entry_type(nested, p) == "file" for p in REQUIRED_FILES) and all(
                    entry_type(nested, p) == "directory" for p in REQUIRED_DIRECTORIES
                ):
                    findings.append(
                        finding(
                            "package_layout",
                            "layout_wrapped_archive",
                            "Place the required files and directories directly at the archive root.",
                        )
                    )
        except OSError as exc:
            raise InfrastructureFailure("material_unavailable") from exc
    return findings


def contained_path(root: Path, value: object, expected: str) -> bool:
    """Validate a declared POSIX package path and its actual material entry type."""
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        return False
    if value == ".":
        return expected == "directory"
    parts = value.split("/")
    if ":" in parts[0] or any(part in ("", ".", "..") for part in parts):
        return False
    return entry_type(root, value) == expected


def metadata(root: Path) -> list[dict]:
    """Parse the declared metadata contract; never execute its argument arrays."""

    def issue(code: str, message: str) -> dict:
        return finding("metadata_contract", code, message, "task.toml")

    if entry_type(root, "task.toml") != "file":
        return [
            issue(
                "metadata_invalid_format", "Provide task.toml as a regular root file."
            )
        ]
    try:
        descriptor = os.open(
            root / "task.toml", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        )
        with os.fdopen(descriptor, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise InfrastructureFailure("material_unavailable")
            raw = handle.read(METADATA_READ_CAPACITY + 1)
    except OSError as exc:
        raise InfrastructureFailure("material_unavailable") from exc
    if len(raw) > METADATA_READ_CAPACITY:
        raise InfrastructureFailure("capacity_exceeded")
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError):
        return [issue("metadata_invalid_format", "task.toml must be valid UTF-8 TOML.")]
    allowed = {
        "format_version",
        "id",
        "title",
        "environment",
        "reference",
        "verification",
        "resources",
        "extensions",
    }
    findings = []
    if set(data) - allowed or (
        "extensions" in data and not isinstance(data["extensions"], dict)
    ):
        findings.append(
            issue(
                "metadata_invalid_format",
                "Use the documented top-level fields; extensions must be a table.",
            )
        )

    def required(condition: bool, field: str) -> None:
        if not condition:
            findings.append(
                issue(
                    "metadata_missing_required_value",
                    f"Supply a valid {field} value as defined by the guide.",
                )
            )

    required(
        type(data.get("format_version")) is int and data["format_version"] == 1,
        "format_version",
    )
    identifier = data.get("id")
    required(
        isinstance(identifier, str)
        and re.fullmatch(r"[a-z][a-z0-9-]{0,79}", identifier) is not None,
        "id",
    )
    required(isinstance(data.get("title"), str) and bool(data["title"]), "title")

    tables = {}
    fields_by_table = {
        "environment": {"dockerfile", "context", "platform"},
        "reference": {"command", "working_directory"},
        "verification": {"command", "working_directory"},
        "resources": set(RESOURCE_FIELDS),
    }
    for name, fields in fields_by_table.items():
        value = data.get(name)
        required(isinstance(value, dict), name)
        tables[name] = value if isinstance(value, dict) else {}
        if set(tables[name]) - fields:
            findings.append(
                issue(
                    "metadata_invalid_format",
                    f"Use only documented fields in {name}; put supplementary metadata under extensions.",
                )
            )
    platform = tables["environment"].get("platform")
    required(
        isinstance(platform, str)
        and re.fullmatch(
            r"linux/[a-zA-Z0-9_][a-zA-Z0-9_.-]*(?:/[a-zA-Z0-9_.-]+)?", platform
        )
        is not None,
        "environment.platform",
    )
    for table, field, kind in (
        ("environment", "dockerfile", "file"),
        ("environment", "context", "directory"),
        ("reference", "working_directory", "directory"),
        ("verification", "working_directory", "directory"),
    ):
        if not contained_path(root, tables[table].get(field), kind):
            findings.append(
                issue(
                    "metadata_unsafe_path",
                    f"{table}.{field} must name a contained package {kind}.",
                )
            )
    for table in ("reference", "verification"):
        command = tables[table].get("command")
        if not (
            isinstance(command, list)
            and bool(command)
            and all(isinstance(arg, str) and "\x00" not in arg for arg in command)
            and bool(command[0])
        ):
            findings.append(
                issue(
                    "metadata_invalid_argument_array",
                    f"{table}.command must be a nonempty argument array with a program name.",
                )
            )
    for field in RESOURCE_FIELDS:
        value = tables["resources"].get(field)
        required(type(value) is int and value > 0, f"resources.{field}")
    return findings


def canonical(value: object) -> str:
    """Canonical wire encoding for this checker's string/integer result fields."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def result(request: dict, findings: list[dict], failure: str | None = None) -> dict:
    """Bind findings or infrastructure failure to the exact supplied invocation."""
    body = {
        "schema_version": "external_checker_result.v1",
        "request_digest": request["request_digest"],
        "registry_entry_id": request["registry"]["registry_entry_id"],
        "registry_entry_digest": request["registry"]["entry_digest"],
        "phase": request["identity"]["phase"],
        "outcome": "infrastructure_failed" if failure else "completed",
        "verdict": None if failure else ("failed" if findings else "passed"),
        "findings": [] if failure else findings,
        "infrastructure_failure_code": failure,
    }
    return {
        **body,
        "result_digest": "sha256:"
        + hashlib.sha256(canonical(body).encode()).hexdigest(),
    }


def evaluate(request: dict, root: Path) -> dict:
    """Run exactly one configured PRE rule against read-only verified material."""
    try:
        configuration = request["configuration"]
        if request["identity"]["phase"] != "pre_submit" or set(configuration) != {
            "check"
        }:
            raise InfrastructureFailure("implementation_unavailable")
        evaluator = {"package_layout": layout, "metadata_contract": metadata}.get(
            configuration["check"]
        )
        if evaluator is None:
            raise InfrastructureFailure("implementation_unavailable")
        if not root.is_dir():
            raise InfrastructureFailure("material_unavailable")
        return result(request, evaluator(root))
    except InfrastructureFailure as exc:
        return result(request, [], str(exc))
    except (OSError, MemoryError, RecursionError):
        return result(request, [], "capacity_exceeded")


def main() -> int:
    """Read one bounded request and emit one result, with no raw exception output."""
    try:
        raw = sys.stdin.buffer.read(REQUEST_READ_CAPACITY + 1)
        if len(raw) > REQUEST_READ_CAPACITY:
            return 1
        request = json.loads(raw)
        response = evaluate(request, Path("/work/input"))
        sys.stdout.write(canonical(response))
        return 0
    except (ValueError, KeyError, TypeError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
