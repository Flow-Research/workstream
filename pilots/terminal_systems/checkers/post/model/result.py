"""Normalized external-checker results from validated project assessments."""

from __future__ import annotations

import hashlib
import json

from assessment import ValidatedFinding


INFRASTRUCTURE_FAILURES = frozenset(
    {
        "capacity_exceeded",
        "deadline_exceeded",
        "material_unavailable",
        "implementation_unavailable",
        "invalid_output",
    }
)


class ResultError(ValueError):
    """The external request cannot safely identify a project result."""


def canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _identity(request: dict) -> dict[str, str]:
    try:
        if (
            type(request) is not dict
            or request["identity"]["phase"] != "post_submit"
            or type(request["request_digest"]) is not str
            or type(request["registry"]["registry_entry_id"]) is not str
            or type(request["registry"]["entry_digest"]) is not str
        ):
            raise ResultError("request_invalid")
        return {
            "request_digest": request["request_digest"],
            "registry_entry_id": request["registry"]["registry_entry_id"],
            "registry_entry_digest": request["registry"]["entry_digest"],
        }
    except (KeyError, TypeError) as exc:
        raise ResultError("request_invalid") from exc


def _finish(body: dict) -> dict:
    return {
        **body,
        "result_digest": "sha256:"
        + hashlib.sha256(canonical(body).encode("utf-8")).hexdigest(),
    }


def completed_result(
    request: dict, requirement_id: str, findings: tuple[ValidatedFinding, ...]
) -> dict:
    """Use fixed rubric prose and evidence locations, never free-form model text."""
    if type(requirement_id) is not str or not requirement_id:
        raise ResultError("request_invalid")
    projected = []
    for item in findings:
        if type(item) is not ValidatedFinding:
            raise ResultError("assessment_invalid")
        projected.append(
            {
                "check_id": requirement_id,
                "code": item.code,
                "level": "error",
                "message": item.message,
                "path": item.evidence.path,
                "line": item.line,
            }
        )
    body = {
        "schema_version": "external_checker_result.v1",
        **_identity(request),
        "phase": "post_submit",
        "outcome": "completed",
        "verdict": "failed" if projected else "passed",
        "findings": projected,
        "infrastructure_failure_code": None,
    }
    return _finish(body)


def infrastructure_result(request: dict, code: str) -> dict:
    """Keep runtime/material failure distinct from submitted-work findings."""
    if code not in INFRASTRUCTURE_FAILURES:
        raise ResultError("infrastructure_failure_invalid")
    body = {
        "schema_version": "external_checker_result.v1",
        **_identity(request),
        "phase": "post_submit",
        "outcome": "infrastructure_failed",
        "verdict": None,
        "findings": [],
        "infrastructure_failure_code": code,
    }
    return _finish(body)


__all__ = (
    "ResultError",
    "canonical",
    "completed_result",
    "infrastructure_result",
)
