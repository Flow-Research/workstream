"""Compile and validate the single current post-submit policy contract."""

from __future__ import annotations
import json
from typing import Any
from uuid import UUID
from app.modules.checkers.api.post_submit_catalogue import (
    CompiledPostSubmitPolicy,
    EmptyPostSubmitConfiguration,
    PostSubmitPolicyEntry,
    current_post_submit_catalogue,
)

POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION = "post_submit_checker_policy_spec"
POST_SUBMIT_CHECKER_POLICY_SPEC_KEYS = {
    "schema_version",
    "project_id",
    "guide_version",
    "required_checkers",
    "warning_checkers",
    "blocking_severities",
}
DEFAULT_DURABLE_CHECKERS = [
    item.capability_id
    for item in current_post_submit_catalogue().definitions
    if item.platform_default
]
POST_SUBMIT_SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")
PLATFORM_BLOCKING_SEVERITIES = ("critical", "high")
PLATFORM_BLOCKING_SEVERITY_SET = frozenset(PLATFORM_BLOCKING_SEVERITIES)


class PostSubmitCheckerCompilerError(ValueError):
    """The supplied policy cannot compile into the current contract."""


def build_project_post_submit_checker_spec(
    *,
    project_id: str,
    guide_version: str,
    required_checkers: list[str] | None = None,
    warning_checkers: list[str] | None = None,
    blocking_severities: list[str] | None = None,
) -> dict[str, Any]:
    """Build constrained project additions without reclassifying platform defaults."""
    required = _canonical_checker_names(required_checkers if required_checkers is not None else [])
    warning = _canonical_checker_names(warning_checkers if warning_checkers is not None else [])
    _validate_checker_classifications(
        required, warning, platform_default_checkers=DEFAULT_DURABLE_CHECKERS
    )
    return {
        "schema_version": POST_SUBMIT_CHECKER_POLICY_SPEC_SCHEMA_VERSION,
        "project_id": project_id,
        "guide_version": guide_version,
        "required_checkers": required,
        "warning_checkers": warning,
        "blocking_severities": _canonical_blocking_severities(
            list(PLATFORM_BLOCKING_SEVERITIES)
            if blocking_severities is None
            else blocking_severities
        ),
    }


def compile_project_post_submit_checker_spec(
    *,
    project_id: str,
    guide_version: str,
    spec: dict[str, Any],
) -> CompiledPostSubmitPolicy:
    """Compile project selections into the one canonical ordered policy body."""
    _validate_spec_shape(spec, project_id, guide_version)
    required = _canonical_checker_names(spec["required_checkers"])
    warning = _canonical_checker_names(spec["warning_checkers"])
    severities = _canonical_blocking_severities(spec["blocking_severities"])
    _validate_checker_classifications(
        required, warning, platform_default_checkers=DEFAULT_DURABLE_CHECKERS
    )
    catalogue = current_post_submit_catalogue()
    requested = set(required + warning)
    selectable = {item.capability_id for item in catalogue.definitions if item.selectable}
    if not requested.issubset(selectable):
        raise PostSubmitCheckerCompilerError("post-submit project selection is unavailable")
    entries = tuple(
        PostSubmitPolicyEntry(
            checker_id=item.capability_id,
            definition_version=item.capability_version,
            implementation_version=item.implementation_version,
            classification=(
                "platform_default"
                if item.platform_default
                else "project_required"
                if item.capability_id in required
                else "project_warning"
            ),
            configuration=item.validate_configuration(EmptyPostSubmitConfiguration()),
        )
        for item in catalogue.definitions
        if item.platform_default or item.capability_id in requested
    )
    try:
        policy = CompiledPostSubmitPolicy(
            project_id=UUID(project_id),
            guide_version=guide_version,
            catalogue_manifest_sha256=catalogue.manifest_sha256,
            entries=entries,
            blocking_severities=tuple(severities),
        )
        policy.validate_catalogue(catalogue)
    except ValueError as exc:
        raise PostSubmitCheckerCompilerError(str(exc)) from exc
    return policy


def parse_locked_post_submit_checker_policy_body(
    body: Any,
    *,
    project_id: str,
    guide_version: str,
    policy_hash: str,
) -> CompiledPostSubmitPolicy:
    """Reject unsupported bodies and validate exact current policy identity."""
    if not isinstance(body, dict):
        raise ValueError("locked post-submit checker policy body is missing")
    policy = CompiledPostSubmitPolicy.model_validate_json(json.dumps(body))
    if str(policy.project_id) != project_id or policy.guide_version != guide_version:
        raise ValueError("locked post-submit checker policy guide context mismatch")
    if policy.policy_hash != policy_hash:
        raise ValueError("locked post-submit checker policy hash is invalid")
    policy.validate_catalogue(current_post_submit_catalogue())
    return policy


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
            raise PostSubmitCheckerCompilerError(
                f"post-submit checker spec {field_name} is invalid"
            )


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
