"""Helpers for durable post-submit checker policy identity."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from app.core.hashing import canonical_json_hash
from app.modules.checkers.runner import (
    UnknownChecker,
    default_checker_registry,
)

POST_SUBMIT_COMPILER_VERSION = "workstream-post-submit-compiler-v0.1"
POST_SUBMIT_CHECKER_POLICY_SCHEMA_VERSION = "post_submit_checker_policy.v1"
POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION = "post_submit_checker_policy_spec.v1"
POST_SUBMIT_CHECKER_POLICY_BODY_KEYS = {
    "schema_version",
    "compiler_version",
    "project_id",
    "guide_version",
    "default_checkers",
    "required_checkers",
    "warning_checkers",
    "execution_checkers",
    "blocking_severities",
}
POST_SUBMIT_CHECKER_POLICY_SPEC_KEYS = {
    "schema_version",
    "project_id",
    "guide_version",
    "required_checkers",
    "warning_checkers",
    "blocking_severities",
}
POST_SUBMIT_V01_DEFAULT_CHECKERS = (
    "check_submission_packet",
    "check_policy_context_present",
    "check_evidence_present",
    "check_evidence_integrity",
    "check_required_files",
    "check_forbidden_files",
    "check_confidentiality_attestation",
    "check_low_quality_generated_artifacts",
)
DEFAULT_DURABLE_CHECKERS = list(POST_SUBMIT_V01_DEFAULT_CHECKERS)
POST_SUBMIT_DEFAULT_CHECKERS_BY_COMPILER_VERSION = MappingProxyType(
    {
        POST_SUBMIT_COMPILER_VERSION: POST_SUBMIT_V01_DEFAULT_CHECKERS,
    }
)
SUPPORTED_POST_SUBMIT_COMPILER_VERSIONS = frozenset(
    POST_SUBMIT_DEFAULT_CHECKERS_BY_COMPILER_VERSION
)
POST_SUBMIT_SEVERITY_ORDER = (
    "critical",
    "high",
    "medium",
    "low",
    "info",
)
PLATFORM_BLOCKING_SEVERITIES = ("critical", "high")
PLATFORM_BLOCKING_SEVERITY_SET = frozenset(PLATFORM_BLOCKING_SEVERITIES)


class PostSubmitCheckerCompilerError(ValueError):
    """Raised when post-submit checker policy compilation fails closed."""


@dataclass(frozen=True)
class LockedPostSubmitCheckerPolicy:
    """Validated locked post-submit checker policy body."""

    compiler_version: str
    default_checkers: list[str]
    required_checkers: list[str]
    warning_checkers: list[str]
    execution_checkers: list[str]
    blocking_severities: list[str]


@dataclass(frozen=True)
class CompiledPostSubmitCheckerPolicy:
    """Compiled post-submit policy body plus its canonical identity."""

    compiler_version: str
    policy_body: dict[str, Any]
    policy_hash: str
    required_checkers: list[str]
    warning_checkers: list[str]
    execution_checkers: list[str]
    blocking_severities: list[str]


def build_project_post_submit_checker_spec(
    *,
    project_id: str,
    guide_version: str,
    required_checkers: list[str] | None = None,
    warning_checkers: list[str] | None = None,
    blocking_severities: list[str] | None = None,
) -> dict[str, Any]:
    """Build a constrained post-submit checker specification.

    Args:
        project_id: Project that owns the guide version.
        guide_version: Guide version the policy belongs to.
        required_checkers: Project-specific checkers that must block review on
            failure. May include a default checker to tighten project routing.
        warning_checkers: Project-specific non-blocking checker names.
        blocking_severities: Additional severities that should block review.

    Returns:
        Canonical JSON-compatible checker specification.
    """
    canonical_required = _canonical_checker_names(required_checkers or [])
    canonical_warning = _canonical_checker_names(warning_checkers or [])
    _validate_checker_classifications(
        canonical_required,
        canonical_warning,
        platform_default_checkers=_default_checkers_for_compiler_version(
            POST_SUBMIT_COMPILER_VERSION
        ),
    )
    return {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION,
        "project_id": project_id,
        "guide_version": guide_version,
        "required_checkers": canonical_required,
        "warning_checkers": canonical_warning,
        "blocking_severities": (
            list(PLATFORM_BLOCKING_SEVERITIES)
            if blocking_severities is None
            else _canonical_blocking_severities(blocking_severities)
        ),
    }


def compile_project_post_submit_checker_spec(
    *,
    project_id: str,
    guide_version: str,
    spec: dict[str, Any],
    compiler_version: str = POST_SUBMIT_COMPILER_VERSION,
) -> CompiledPostSubmitCheckerPolicy:
    """Compile a constrained post-submit checker spec into a policy body.

    Args:
        project_id: Project that owns the guide version.
        guide_version: Guide version the policy belongs to.
        spec: Constrained checker specification from setup-time derivation or
            the current v0.1 manual bootstrap path.
        compiler_version: Server-owned compiler identity.

    Returns:
        Compiled policy body and canonical hash.

    Raises:
        PostSubmitCheckerCompilerError: If the spec is malformed or weakens
            platform defaults.
    """
    _validate_spec_shape(spec, project_id, guide_version)
    default_checkers = _default_checkers_for_compiler_version(compiler_version)
    required_checkers = _canonical_checker_names(spec["required_checkers"])
    warning_checkers = _canonical_checker_names(spec["warning_checkers"])
    blocking_severities = _canonical_blocking_severities(spec["blocking_severities"])
    _validate_checker_classifications(
        required_checkers,
        warning_checkers,
        platform_default_checkers=default_checkers,
    )
    policy_body = post_submit_checker_policy_body(
        project_id=project_id,
        guide_version=guide_version,
        required_checkers=required_checkers,
        warning_checkers=warning_checkers,
        blocking_severities=blocking_severities,
        compiler_version=compiler_version,
    )
    try:
        default_checker_registry().require_registered(set(policy_body["execution_checkers"]))
    except UnknownChecker as exc:
        raise PostSubmitCheckerCompilerError(str(exc)) from exc
    policy_hash = canonical_json_hash(policy_body)
    return CompiledPostSubmitCheckerPolicy(
        compiler_version=compiler_version,
        policy_body=policy_body,
        policy_hash=policy_hash,
        required_checkers=list(required_checkers),
        warning_checkers=list(warning_checkers),
        execution_checkers=list(policy_body["execution_checkers"]),
        blocking_severities=list(blocking_severities),
    )


def post_submit_checker_policy_body(
    *,
    project_id: str,
    guide_version: str,
    required_checkers: list[str],
    warning_checkers: list[str],
    blocking_severities: list[str],
    compiler_version: str = POST_SUBMIT_COMPILER_VERSION,
) -> dict[str, Any]:
    """Build the canonical body for a post-submit checker policy.

    Args:
        project_id: Project that owns the guide version.
        guide_version: Guide version the policy belongs to.
        required_checkers: Checker names that can block review on failure.
        warning_checkers: Checker names that produce non-blocking findings.
        blocking_severities: Severities that force a failed checker to block review.
        compiler_version: Versioned compiler contract that owns default checkers.

    Returns:
        Canonical JSON-compatible policy body.
    """
    default_checkers = _default_checkers_for_compiler_version(compiler_version)
    canonical_required_checkers = _canonical_checker_names(required_checkers)
    canonical_warning_checkers = _canonical_checker_names(warning_checkers)
    return {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SCHEMA_VERSION,
        "compiler_version": compiler_version,
        "project_id": project_id,
        "guide_version": guide_version,
        "default_checkers": list(default_checkers),
        "required_checkers": canonical_required_checkers,
        "warning_checkers": canonical_warning_checkers,
        "execution_checkers": list(
            dict.fromkeys(
                [
                    *default_checkers,
                    *canonical_required_checkers,
                    *canonical_warning_checkers,
                ]
            )
        ),
        "blocking_severities": _canonical_blocking_severities(blocking_severities),
    }


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
    compiler_version = body.get("compiler_version")
    required_checkers = body.get("required_checkers")
    warning_checkers = body.get("warning_checkers")
    default_checkers = body.get("default_checkers")
    execution_checkers = body.get("execution_checkers")
    blocking_severities = body.get("blocking_severities")
    if (
        set(body) != POST_SUBMIT_CHECKER_POLICY_BODY_KEYS
        or body.get("schema_version") != POST_SUBMIT_CHECKER_POLICY_SCHEMA_VERSION
        or not isinstance(compiler_version, str)
        or compiler_version not in SUPPORTED_POST_SUBMIT_COMPILER_VERSIONS
        or body.get("project_id") != project_id
        or body.get("guide_version") != guide_version
        or not _valid_unique_string_list(default_checkers)
        or not _valid_canonical_checker_list(required_checkers)
        or not _valid_canonical_checker_list(warning_checkers)
        or not _valid_unique_string_list(execution_checkers)
        or not _valid_canonical_blocking_severities(blocking_severities)
        or execution_checkers
        != list(dict.fromkeys([*default_checkers, *required_checkers, *warning_checkers]))
    ):
        raise ValueError("locked post-submit checker policy body is invalid")
    expected_default_checkers = _default_checkers_for_compiler_version(compiler_version)
    if default_checkers != expected_default_checkers:
        raise ValueError("locked post-submit checker policy body is invalid")
    try:
        _validate_checker_classifications(
            required_checkers,
            warning_checkers,
            platform_default_checkers=expected_default_checkers,
        )
    except PostSubmitCheckerCompilerError as exc:
        raise ValueError("locked post-submit checker policy body is invalid") from exc
    if canonical_json_hash(body) != policy_hash:
        raise ValueError("locked post-submit checker policy hash is invalid")
    return LockedPostSubmitCheckerPolicy(
        compiler_version=compiler_version,
        default_checkers=list(default_checkers),
        required_checkers=list(required_checkers),
        warning_checkers=list(warning_checkers),
        execution_checkers=list(execution_checkers),
        blocking_severities=list(blocking_severities),
    )


def _validate_spec_shape(
    spec: dict[str, Any],
    project_id: str,
    guide_version: str,
) -> None:
    """Validate the constrained post-submit spec envelope."""
    if not isinstance(spec, dict):
        raise PostSubmitCheckerCompilerError("post-submit checker spec shape is invalid")
    if set(spec) != POST_SUBMIT_CHECKER_POLICY_SPEC_KEYS:
        raise PostSubmitCheckerCompilerError("post-submit checker spec shape is invalid")
    if spec.get("schema_version") != POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION:
        raise PostSubmitCheckerCompilerError("post-submit checker spec schema version is invalid")
    if spec.get("project_id") != project_id or spec.get("guide_version") != guide_version:
        raise PostSubmitCheckerCompilerError("post-submit checker spec guide context mismatch")
    for field_name in ("required_checkers", "warning_checkers", "blocking_severities"):
        if not _string_list(spec.get(field_name)):
            raise PostSubmitCheckerCompilerError(f"post-submit checker spec {field_name} is invalid")


def _validate_checker_classifications(
    required_checkers: list[str],
    warning_checkers: list[str],
    *,
    platform_default_checkers: list[str],
) -> None:
    """Reject duplicate, contradictory, or weakening checker classifications."""
    duplicate_required = _duplicates(required_checkers)
    duplicate_warning = _duplicates(warning_checkers)
    if duplicate_required or duplicate_warning:
        raise PostSubmitCheckerCompilerError(
            "post-submit checker spec contains duplicate checker names"
        )
    conflicting = set(required_checkers).intersection(warning_checkers)
    if conflicting:
        raise PostSubmitCheckerCompilerError(
            "post-submit checker spec contains conflicting checker classifications"
        )
    weakened_defaults = sorted(set(warning_checkers).intersection(platform_default_checkers))
    if weakened_defaults:
        raise PostSubmitCheckerCompilerError(
            "post-submit checker spec cannot mark default checkers as warning-only"
        )


def _default_checkers_for_compiler_version(compiler_version: str) -> list[str]:
    """Return the frozen default-checker snapshot for a compiler version."""
    default_checkers = POST_SUBMIT_DEFAULT_CHECKERS_BY_COMPILER_VERSION.get(compiler_version)
    if default_checkers is None:
        raise PostSubmitCheckerCompilerError("post-submit checker compiler version is unsupported")
    return list(default_checkers)


def _canonical_checker_names(checker_names: list[str]) -> list[str]:
    """Return stable checker names while rejecting malformed values."""
    if not _string_list(checker_names):
        raise PostSubmitCheckerCompilerError("post-submit checker names must be strings")
    for checker_name in checker_names:
        if checker_name.strip() != checker_name or not checker_name:
            raise PostSubmitCheckerCompilerError("post-submit checker names must be canonical")
    return sorted(checker_names)


def _canonical_blocking_severities(severities: list[str]) -> list[str]:
    """Return canonical blocking severities without weakening platform defaults."""
    if not _string_list(severities):
        raise PostSubmitCheckerCompilerError("post-submit blocking severities must be strings")
    unknown = sorted(set(severities).difference(POST_SUBMIT_SEVERITY_ORDER))
    if unknown:
        raise PostSubmitCheckerCompilerError("post-submit checker spec contains unknown severities")
    if not PLATFORM_BLOCKING_SEVERITY_SET.issubset(severities):
        raise PostSubmitCheckerCompilerError(
            "post-submit checker spec weakens platform blocking severities"
        )
    return [severity for severity in POST_SUBMIT_SEVERITY_ORDER if severity in set(severities)]


def _valid_canonical_checker_list(value: Any) -> bool:
    """Return whether a checker-name list is sorted and duplicate-free."""
    if not _string_list(value):
        return False
    return list(value) == sorted(value) and len(value) == len(set(value))


def _valid_canonical_blocking_severities(value: Any) -> bool:
    """Return whether severity names use the canonical severity order."""
    if not _valid_unique_string_list(value):
        return False
    if not PLATFORM_BLOCKING_SEVERITY_SET.issubset(value):
        return False
    return list(value) == [
        severity for severity in POST_SUBMIT_SEVERITY_ORDER if severity in set(value)
    ]


def _valid_unique_string_list(value: Any) -> bool:
    """Return whether a value is a duplicate-free string list."""
    return _string_list(value) and len(value) == len(set(value))


def _string_list(value: Any) -> bool:
    """Return whether a value is a JSON-list-shaped string list."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _duplicates(values: list[str]) -> set[str]:
    """Return duplicate values from a sequence."""
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates
