"""Helpers for durable post-submit checker policy identity."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.core.hashing import canonical_json_hash

POST_SUBMIT_CHECKER_POLICY_SCHEMA_VERSION = "post_submit_checker_policy.v1"
POST_SUBMIT_CHECKER_POLICY_BODY_KEYS = {
    "schema_version",
    "project_id",
    "guide_version",
    "default_checkers",
    "required_checkers",
    "warning_checkers",
    "execution_checkers",
    "blocking_severities",
}
DEFAULT_DURABLE_CHECKERS = [
    "check_submission_packet",
    "check_policy_context_present",
    "check_evidence_present",
    "check_evidence_integrity",
    "check_required_files",
    "check_forbidden_files",
    "check_confidentiality_attestation",
    "check_low_quality_generated_artifacts",
]


@dataclass(frozen=True)
class LockedPostSubmitCheckerPolicy:
    """Validated locked post-submit checker policy body."""

    default_checkers: list[str]
    required_checkers: list[str]
    warning_checkers: list[str]
    execution_checkers: list[str]
    blocking_severities: list[str]


def post_submit_checker_policy_body(
    *,
    project_id: str,
    guide_version: str,
    required_checkers: Sequence[str],
    warning_checkers: Sequence[str],
    blocking_severities: Sequence[str],
) -> dict[str, Any]:
    """Build the canonical body for a post-submit checker policy.

    Args:
        project_id: Project that owns the guide version.
        guide_version: Guide version the policy belongs to.
        required_checkers: Checker names that can block review on failure.
        warning_checkers: Checker names that produce non-blocking findings.
        blocking_severities: Severities that force a failed checker to block review.

    Returns:
        Canonical JSON-compatible policy body.
    """
    return {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SCHEMA_VERSION,
        "project_id": project_id,
        "guide_version": guide_version,
        "default_checkers": list(DEFAULT_DURABLE_CHECKERS),
        "required_checkers": list(required_checkers),
        "warning_checkers": list(warning_checkers),
        "execution_checkers": list(
            dict.fromkeys(
                [
                    *DEFAULT_DURABLE_CHECKERS,
                    *required_checkers,
                    *warning_checkers,
                ]
            )
        ),
        "blocking_severities": list(blocking_severities),
    }


def post_submit_checker_policy_hash(
    *,
    project_id: str,
    guide_version: str,
    required_checkers: Sequence[str],
    warning_checkers: Sequence[str],
    blocking_severities: Sequence[str],
) -> str:
    """Return the server-owned hash for a post-submit checker policy.

    Args:
        project_id: Project that owns the guide version.
        guide_version: Guide version the policy belongs to.
        required_checkers: Checker names that can block review on failure.
        warning_checkers: Checker names that produce non-blocking findings.
        blocking_severities: Severities that force a failed checker to block review.

    Returns:
        Canonical SHA-256 hash for the durable policy contract.
    """
    return canonical_json_hash(
        post_submit_checker_policy_body(
            project_id=project_id,
            guide_version=guide_version,
            required_checkers=required_checkers,
            warning_checkers=warning_checkers,
            blocking_severities=blocking_severities,
        )
    )


def parse_locked_post_submit_checker_policy_body(
    body: Any,
    *,
    project_id: str,
    guide_version: str,
    policy_hash: str,
) -> LockedPostSubmitCheckerPolicy:
    """Validate and parse a locked post-submit checker policy body.

    Args:
        body: JSON body stamped when the task locked project context.
        project_id: Expected project id from the locked task.
        guide_version: Expected guide version from the locked task.
        policy_hash: Expected hash stamped with the locked body.

    Returns:
        Parsed checker policy lists.

    Raises:
        ValueError: If the body is malformed or does not match the locked hash.
    """
    if not isinstance(body, dict):
        raise ValueError("locked post-submit checker policy body is missing")
    required_checkers = body.get("required_checkers")
    warning_checkers = body.get("warning_checkers")
    default_checkers = body.get("default_checkers")
    execution_checkers = body.get("execution_checkers")
    blocking_severities = body.get("blocking_severities")
    if (
        set(body) != POST_SUBMIT_CHECKER_POLICY_BODY_KEYS
        or body.get("schema_version") != POST_SUBMIT_CHECKER_POLICY_SCHEMA_VERSION
        or body.get("project_id") != project_id
        or body.get("guide_version") != guide_version
        or not _string_list(default_checkers)
        or not _string_list(required_checkers)
        or not _string_list(warning_checkers)
        or not _string_list(execution_checkers)
        or not _string_list(blocking_severities)
        or not required_checkers
        or execution_checkers
        != list(dict.fromkeys([*default_checkers, *required_checkers, *warning_checkers]))
    ):
        raise ValueError("locked post-submit checker policy body is invalid")
    if canonical_json_hash(body) != policy_hash:
        raise ValueError("locked post-submit checker policy hash is invalid")
    return LockedPostSubmitCheckerPolicy(
        default_checkers=list(default_checkers),
        required_checkers=list(required_checkers),
        warning_checkers=list(warning_checkers),
        execution_checkers=list(execution_checkers),
        blocking_severities=list(blocking_severities),
    )


def _string_list(value: Any) -> bool:
    """Return whether a value is a list containing only strings."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)
