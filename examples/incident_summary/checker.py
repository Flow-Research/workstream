"""Standalone incident summary PRE/POST checker; never executes submitted material."""

from __future__ import annotations
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from uuid import UUID

MATERIAL = Path("/work/input")
FIXED = Path(__file__).with_name("events.jsonl")
MAX_REQUEST = 2 * 1024 * 1024
MAX_FILE = 16 * 1024
CHECKS = {
    "pre_submit": "incident_summary_layout",
    "post_submit": "incident_summary_counts",
}


class InvalidRequest(ValueError):
    pass


class MaterialUnavailable(Exception):
    pass


def invalid_constant(_value):
    raise ValueError("invalid JSON constant")


def valid_sha256(value):
    return (
        type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None
    )


def pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def decode(raw):
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=pairs,
        parse_constant=invalid_constant,
    )


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def validate_request(request):
    if type(request) is not dict:
        raise InvalidRequest("request")
    try:
        phase = request["identity"]["phase"]
        config = request["configuration"]
        digest = request["request_digest"]
        entry = request["registry"]
        if (
            phase not in CHECKS
            or type(config) is not dict
            or config != {"check": CHECKS[phase]}
        ):
            raise InvalidRequest("configuration")
        if not valid_sha256(digest):
            raise InvalidRequest("digest")
        if not valid_sha256(entry["entry_digest"]):
            raise InvalidRequest("registry digest")
        registry_id = entry["registry_entry_id"]
        if type(registry_id) is not str or str(UUID(registry_id)) != registry_id:
            raise InvalidRequest("registry")
        if (
            type(request["input"]) is not dict
            or request["input"]["requirement_id"]
            != "terminal."
            + ("pre" if phase == "pre_submit" else "post")
            + "."
            + CHECKS[phase]
        ):
            raise InvalidRequest("requirement")
        return phase
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidRequest("request") from exc


def finding(check, code, message, path):
    return {
        "check_id": check,
        "code": code,
        "level": "error",
        "message": message,
        "path": path,
        "line": None,
    }


def result(request, phase, findings=(), failure=None):
    body = {
        "schema_version": "external_checker_result.v1",
        "request_digest": request["request_digest"],
        "registry_entry_id": request["registry"]["registry_entry_id"],
        "registry_entry_digest": request["registry"]["entry_digest"],
        "phase": phase,
        "outcome": "infrastructure_failed" if failure else "completed",
        "verdict": None if failure else ("failed" if findings else "passed"),
        "findings": list(findings) if not failure else [],
        "infrastructure_failure_code": failure,
    }
    return {
        **body,
        "result_digest": "sha256:"
        + hashlib.sha256(canonical(body).encode()).hexdigest(),
    }


def regular_bytes(root, name):
    if not isinstance(root, Path) or root.is_symlink() or not root.is_dir():
        raise MaterialUnavailable("material_unavailable")
    try:
        fd = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise MaterialUnavailable("material_unavailable") from exc
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise MaterialUnavailable("material_unavailable")
        raw = f.read(MAX_FILE + 1)
    if len(raw) > MAX_FILE:
        raise MaterialUnavailable("capacity_exceeded")
    return raw


def events_shape(raw):
    try:
        lines = raw.splitlines()
        if not lines or len(lines) > 100:
            return False
        for line in lines:
            value = decode(line)
            if (
                type(value) is not dict
                or set(value) != {"service", "status"}
                or type(value["service"]) is not str
                or not value["service"]
                or value["status"] not in ("ok", "error")
            ):
                return False
        return True
    except (UnicodeError, ValueError, TypeError):
        return False


def summary_shape(raw):
    try:
        value = decode(raw)
        if (
            type(value) is not dict
            or set(value) != {"services"}
            or type(value["services"]) is not list
            or not value["services"]
        ):
            return None
        rows = value["services"]
        names = []
        for row in rows:
            if (
                type(row) is not dict
                or set(row) != {"service", "total", "errors"}
                or type(row["service"]) is not str
                or not row["service"]
                or type(row["total"]) is not int
                or type(row["errors"]) is not int
                or row["total"] < 0
                or row["errors"] < 0
                or row["errors"] > row["total"]
            ):
                return None
            names.append(row["service"])
        if names != sorted(set(names)):
            return None
        return value
    except (UnicodeError, ValueError, TypeError):
        return None


def expected_summary():
    raw = FIXED.read_bytes()
    if not events_shape(raw):
        raise MaterialUnavailable("implementation_unavailable")
    counts = {}
    for line in raw.splitlines():
        event = decode(line)
        row = counts.setdefault(
            event["service"], {"service": event["service"], "total": 0, "errors": 0}
        )
        row["total"] += 1
        row["errors"] += event["status"] == "error"
    return raw, {"services": [counts[name] for name in sorted(counts)]}


def evaluate(request, root=MATERIAL):
    phase = validate_request(request)
    check = CHECKS[phase]
    try:
        events = regular_bytes(root, "events.jsonl")
        summary = regular_bytes(root, "summary.json")
        findings = []
        if events is None:
            findings.append(
                finding(
                    check,
                    "events_missing",
                    "Add events.jsonl at the ZIP root.",
                    "events.jsonl",
                )
            )
        elif not events_shape(events):
            findings.append(
                finding(
                    check,
                    "events_invalid",
                    "events.jsonl must contain valid service/status event rows.",
                    "events.jsonl",
                )
            )
        if summary is None:
            findings.append(
                finding(
                    check,
                    "summary_missing",
                    "Add summary.json at the ZIP root.",
                    "summary.json",
                )
            )
        elif (actual := summary_shape(summary)) is None:
            findings.append(
                finding(
                    check,
                    "summary_invalid",
                    "summary.json must contain sorted unique service rows with nonnegative integer counts.",
                    "summary.json",
                )
            )
        if phase == "post_submit" and not findings:
            fixed, expected = expected_summary()
            if events != fixed:
                findings.append(
                    finding(
                        check,
                        "events_changed",
                        "Keep the supplied events.jsonl unchanged.",
                        "events.jsonl",
                    )
                )
            if actual != expected:
                findings.append(
                    finding(
                        check,
                        "counts_incorrect",
                        "Recount all events and error events for each service.",
                        "summary.json",
                    )
                )
        return result(request, phase, findings)
    except MaterialUnavailable as exc:
        return result(request, phase, failure=str(exc))
    except (OSError, MemoryError, RecursionError):
        return result(request, phase, failure="material_unavailable")


def main():
    raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
    if not raw or len(raw) > MAX_REQUEST:
        return 1
    try:
        response = evaluate(decode(raw))
        sys.stdout.write(canonical(response))
        return 0
    except (InvalidRequest, UnicodeError, ValueError, TypeError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
