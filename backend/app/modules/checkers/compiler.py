"""Trusted compiler for project pre-submit checker bundles."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from collections.abc import Callable
from typing import Any

from app.core.hashing import canonical_json_hash
from app.modules.checkers.catalogue import (
    PreSubmissionCatalogueError,
    PreSubmissionCheckerCatalogue,
    build_pre_submission_checker_catalogue,
)
from app.modules.checkers.pre_submit_defaults import is_canonical_relative_path

PRE_SUBMIT_COMPILER_VERSION = "workstream-pre-submit-compiler-v0.1"
PRE_SUBMIT_BUNDLE_SCHEMA_VERSION = "pre_submit_checker_bundle.v1"
PRE_SUBMIT_SPEC_SCHEMA_VERSION = "pre_submit_checker_spec.v1"
PRIMITIVES_VERSION = "workstream-pre-submit-primitives.v1"

BLOCKING_SEVERITY = "blocking"
WARNING_SEVERITY = "warning"


class PreSubmitCheckerCompilerError(ValueError):
    """Raised when checker specification compilation fails closed."""


@dataclass(frozen=True)
class CompiledPreSubmitCheckerPolicy:
    """Compiled bundle plus index projections persisted on policy rows."""

    compiler_version: str
    compiled_bundle: dict[str, Any]
    compiled_bundle_hash: str
    checker_names: list[str]
    checker_configs: dict[str, Any]


@lru_cache(maxsize=1)
def _compiler_catalogue() -> PreSubmissionCheckerCatalogue:
    """Return the immutable base catalogue used for policy compilation."""
    return build_pre_submission_checker_catalogue()


def build_project_pre_submit_checker_spec(
    effective_policy: dict[str, Any],
    effective_policy_hash: str,
) -> dict[str, Any]:
    """Build the default checker specification from an effective project policy."""
    rules = [
        _rule(
            "validate_submission_packet",
            ["required_packet_fields"],
            {"fields": effective_policy.get("required_packet_fields", [])},
        ),
        _rule(
            "enforce_storage_scheme",
            ["allowed_storage_schemes"],
            {"schemes": effective_policy.get("allowed_storage_schemes", [])},
        ),
    ]
    if effective_policy.get("manifest_required"):
        rules.append(_rule("require_manifest_field", ["manifest_required"], {}))
    if effective_policy.get("artifact_hash_required"):
        rules.append(
            _rule(
                "verify_hash",
                ["artifact_hash_required", "artifact_hash_algorithm"],
                {"algorithm": effective_policy.get("artifact_hash_algorithm")},
            )
        )
    required_artifacts = [
        artifact
        for artifact in effective_policy.get("required_artifacts", [])
        if artifact.get("required", True)
    ]
    if required_artifacts:
        artifact_paths = _project_unique_paths(
            required_artifacts,
            projector=_required_artifact_path,
            field="required_artifacts",
        )
        rules.append(
            _rule(
                "require_file",
                ["required_artifacts"],
                {
                    "artifact_paths": artifact_paths
                },
            )
        )
    required_evidence = [
        evidence
        for evidence in effective_policy.get("required_evidence", [])
        if evidence.get("required", True)
    ]
    if required_evidence:
        evidence_paths = _project_unique_paths(
            required_evidence,
            projector=_required_evidence_path,
            field="required_evidence",
        )
        rules.append(
            _rule(
                "require_minimum_evidence",
                ["required_evidence"],
                {
                    "evidence_paths": evidence_paths
                },
            )
        )
    forbidden_artifacts = effective_policy.get("forbidden_artifacts", [])
    if forbidden_artifacts:
        rules.append(
            _rule(
                "forbid_artifact",
                ["forbidden_artifacts"],
                {"patterns": [artifact["pattern"] for artifact in forbidden_artifacts]},
            )
        )
    attestation_terms = effective_policy.get("attestation_terms", [])
    if attestation_terms:
        rules.append(
            _rule(
                "require_attestation",
                ["attestation_terms"],
                {"terms": attestation_terms},
            )
        )
    if effective_policy.get("maximum_file_size_bytes") is not None:
        rules.append(
            _rule(
                "limit_file_size",
                ["maximum_file_size_bytes"],
                {"maximum_file_size_bytes": effective_policy["maximum_file_size_bytes"]},
            )
        )
    if effective_policy.get("maximum_package_size_bytes") is not None:
        rules.append(
            _rule(
                "limit_package_size",
                ["maximum_package_size_bytes"],
                {"maximum_package_size_bytes": effective_policy["maximum_package_size_bytes"]},
            )
        )
    packaging = effective_policy.get("packaging", {})
    if packaging.get("package_required") or packaging.get("allowed_package_formats"):
        rules.append(_rule("require_packaging", ["packaging"], packaging))
    rules.append(
        _rule(
            "warn_low_quality_generated_artifact",
            ["workstream_default_policy"],
            {},
            severity=WARNING_SEVERITY,
        )
    )
    return {
        "schema_version": PRE_SUBMIT_SPEC_SCHEMA_VERSION,
        "effective_policy_hash": effective_policy_hash,
        "rules": sorted(rules, key=lambda rule: rule["primitive"]),
    }


def compile_effective_project_submission_artifact_policy(
    effective_policy: dict[str, Any],
    effective_policy_hash: str,
    *,
    compiler_version: str = PRE_SUBMIT_COMPILER_VERSION,
) -> CompiledPreSubmitCheckerPolicy:
    """Compile the default project pre-submit checker bundle."""
    spec = build_project_pre_submit_checker_spec(effective_policy, effective_policy_hash)
    return compile_project_pre_submit_checker_spec(
        effective_policy,
        effective_policy_hash,
        spec,
        compiler_version=compiler_version,
    )


def compile_project_pre_submit_checker_spec(
    effective_policy: dict[str, Any],
    effective_policy_hash: str,
    spec: dict[str, Any],
    *,
    compiler_version: str = PRE_SUBMIT_COMPILER_VERSION,
) -> CompiledPreSubmitCheckerPolicy:
    """Validate and compile a project pre-submit checker specification."""
    _validate_spec_shape(spec, effective_policy_hash)
    rules = [_canonical_rule(rule) for rule in spec["rules"]]
    _validate_rule_coverage(effective_policy, rules)
    bundle = {
        "schema_version": PRE_SUBMIT_BUNDLE_SCHEMA_VERSION,
        "compiler_version": compiler_version,
        "primitives_version": PRIMITIVES_VERSION,
        "effective_policy_hash": effective_policy_hash,
        "rules": rules,
    }
    checker_names = _checker_names_for_rules(rules)
    return CompiledPreSubmitCheckerPolicy(
        compiler_version=compiler_version,
        compiled_bundle=bundle,
        compiled_bundle_hash=canonical_json_hash(bundle),
        checker_names=checker_names,
        checker_configs={
            rule["primitive"]: rule["config"]
            for rule in rules
        },
    )


def validate_compiled_pre_submit_checker_bundle(
    effective_policy: dict[str, Any],
    effective_policy_hash: str,
    compiled_bundle: dict[str, Any],
    *,
    compiler_version: str | None = None,
) -> list[str]:
    """Validate a persisted compiled bundle against its effective policy.

    Args:
        effective_policy: Effective project submission artifact policy body.
        effective_policy_hash: Canonical hash locked by the task/submission.
        compiled_bundle: Persisted compiled checker bundle to validate.
        compiler_version: Optional compiler version expected by the row.

    Returns:
        Stable checker-name projection derived from the compiled rules.

    Raises:
        PreSubmitCheckerCompilerError: If the compiled bundle cannot fully
            enforce the effective policy.
    """
    if compiled_bundle.get("schema_version") != PRE_SUBMIT_BUNDLE_SCHEMA_VERSION:
        raise PreSubmitCheckerCompilerError("compiled checker bundle schema version is invalid")
    if compiler_version is not None and compiled_bundle.get("compiler_version") != compiler_version:
        raise PreSubmitCheckerCompilerError("compiled checker bundle compiler version mismatch")
    if compiled_bundle.get("primitives_version") != PRIMITIVES_VERSION:
        raise PreSubmitCheckerCompilerError("compiled checker bundle primitives version is invalid")
    if compiled_bundle.get("effective_policy_hash") != effective_policy_hash:
        raise PreSubmitCheckerCompilerError(
            "compiled checker bundle effective project submission artifact policy hash mismatch"
        )
    rules = compiled_bundle.get("rules")
    if not isinstance(rules, list) or not rules:
        raise PreSubmitCheckerCompilerError("compiled checker bundle requires rules")
    canonical_rules = [_canonical_rule(rule) for rule in rules]
    if canonical_rules != rules:
        raise PreSubmitCheckerCompilerError("compiled checker bundle rules are not canonical")
    _validate_rule_coverage(effective_policy, canonical_rules)
    checker_names = _checker_names_for_rules(canonical_rules)
    return checker_names


def _rule(
    primitive: str,
    policy_fields: list[str],
    config: dict[str, Any],
    *,
    severity: str = BLOCKING_SEVERITY,
) -> dict[str, Any]:
    """Build one canonical checker-spec rule."""
    return {
        "primitive": primitive,
        "severity": severity,
        "policy_fields": sorted(policy_fields),
        "config": _canonical_value(config),
    }


def _validate_spec_shape(spec: dict[str, Any], effective_policy_hash: str) -> None:
    """Validate the top-level checker-spec envelope."""
    if spec.get("schema_version") != PRE_SUBMIT_SPEC_SCHEMA_VERSION:
        raise PreSubmitCheckerCompilerError("checker spec schema version is invalid")
    if spec.get("effective_policy_hash") != effective_policy_hash:
        raise PreSubmitCheckerCompilerError(
            "checker spec effective project submission artifact policy hash mismatch"
        )
    rules = spec.get("rules")
    if not isinstance(rules, list) or not rules:
        raise PreSubmitCheckerCompilerError("checker spec requires rules")


def _canonical_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one checker-spec rule."""
    primitive = rule.get("primitive")
    if not isinstance(primitive, str):
        raise PreSubmitCheckerCompilerError("checker spec contains unknown primitive")
    try:
        definition = _compiler_catalogue().primitive_definition(primitive)
    except PreSubmissionCatalogueError as exc:
        raise PreSubmitCheckerCompilerError("checker spec contains unknown primitive") from exc
    severity = rule.get("severity")
    if severity not in {BLOCKING_SEVERITY, WARNING_SEVERITY}:
        raise PreSubmitCheckerCompilerError("checker spec contains invalid severity")
    expected_severity = (
        BLOCKING_SEVERITY if definition.classification.mandatory else WARNING_SEVERITY
    )
    if severity != expected_severity:
        message = (
            "checker spec weakens severity"
            if definition.classification.mandatory
            else "checker spec escalates warning-only rule"
        )
        raise PreSubmitCheckerCompilerError(message)
    policy_fields = rule.get("policy_fields")
    if not isinstance(policy_fields, list) or not policy_fields:
        raise PreSubmitCheckerCompilerError("checker spec rule lacks policy trace fields")
    if not all(isinstance(field, str) and field for field in policy_fields):
        raise PreSubmitCheckerCompilerError("checker spec rule contains invalid policy trace field")
    actual_policy_fields = set(policy_fields)
    expected_policy_fields = set(definition.policy_fields)
    if actual_policy_fields != expected_policy_fields:
        raise PreSubmitCheckerCompilerError(
            f"checker spec rule has untraceable policy fields for {primitive}"
        )
    config = rule.get("config", {})
    if not isinstance(config, dict):
        raise PreSubmitCheckerCompilerError("checker spec rule config must be an object")
    return {
        "primitive": primitive,
        "severity": severity,
        "policy_fields": sorted(set(policy_fields)),
        "config": _canonical_value(config),
    }


def _validate_rule_coverage(effective_policy: dict[str, Any], rules: list[dict[str, Any]]) -> None:
    """Reject checker specs that do not fully enforce the effective policy."""
    primitives = [rule["primitive"] for rule in rules]
    if len(primitives) != len(set(primitives)):
        raise PreSubmitCheckerCompilerError("checker spec contains duplicate primitive rules")
    expected_primitives = _expected_primitives(effective_policy)
    extra_primitives = sorted(set(primitives).difference(expected_primitives))
    if extra_primitives:
        raise PreSubmitCheckerCompilerError(
            f"checker spec contains untraceable primitive rules: {', '.join(extra_primitives)}"
        )
    omitted_primitives = sorted(expected_primitives.difference(primitives))
    if omitted_primitives:
        raise PreSubmitCheckerCompilerError(
            f"checker spec omits required primitive rules: {', '.join(omitted_primitives)}"
        )
    by_primitive = {rule["primitive"]: rule for rule in rules}
    _require_warning_rule(by_primitive, "warn_low_quality_generated_artifact")
    _require_blocking_rule(by_primitive, "validate_submission_packet")
    _require_config_values(
        by_primitive["validate_submission_packet"],
        "fields",
        effective_policy.get("required_packet_fields", []),
        "required packet fields",
    )
    if effective_policy.get("manifest_required"):
        _require_blocking_rule(by_primitive, "require_manifest_field")
    if effective_policy.get("artifact_hash_required"):
        _require_blocking_rule(by_primitive, "verify_hash")
        if by_primitive["verify_hash"]["config"].get("algorithm") != "sha256":
            raise PreSubmitCheckerCompilerError("checker spec weakens artifact hash algorithm")
    _require_blocking_rule(by_primitive, "enforce_storage_scheme")
    _require_config_values(
        by_primitive["enforce_storage_scheme"],
        "schemes",
        effective_policy.get("allowed_storage_schemes", []),
        "allowed storage schemes",
    )

    required_artifact_paths = _project_unique_paths(
        [
            artifact
            for artifact in effective_policy.get("required_artifacts", [])
            if artifact.get("required", True)
        ],
        projector=_required_artifact_path,
        field="required_artifacts",
    )
    if required_artifact_paths:
        _require_blocking_rule(by_primitive, "require_file")
        _require_config_values(
            by_primitive["require_file"],
            "artifact_paths",
            required_artifact_paths,
            "required artifacts",
        )
    required_evidence_paths = _project_unique_paths(
        [
            evidence
            for evidence in effective_policy.get("required_evidence", [])
            if evidence.get("required", True)
        ],
        projector=_required_evidence_path,
        field="required_evidence",
    )
    if required_evidence_paths:
        _require_blocking_rule(by_primitive, "require_minimum_evidence")
        _require_config_values(
            by_primitive["require_minimum_evidence"],
            "evidence_paths",
            required_evidence_paths,
            "required evidence",
        )
    forbidden_patterns = [
        artifact["pattern"]
        for artifact in effective_policy.get("forbidden_artifacts", [])
    ]
    if forbidden_patterns:
        _require_blocking_rule(by_primitive, "forbid_artifact")
        _require_config_values(
            by_primitive["forbid_artifact"],
            "patterns",
            forbidden_patterns,
            "forbidden artifacts",
        )
    attestation_terms = effective_policy.get("attestation_terms", [])
    if attestation_terms:
        _require_blocking_rule(by_primitive, "require_attestation")
        _require_config_values(
            by_primitive["require_attestation"],
            "terms",
            attestation_terms,
            "attestation terms",
        )
    if effective_policy.get("maximum_file_size_bytes") is not None:
        _require_blocking_rule(by_primitive, "limit_file_size")
        if (
            by_primitive["limit_file_size"]["config"].get("maximum_file_size_bytes")
            != effective_policy["maximum_file_size_bytes"]
        ):
            raise PreSubmitCheckerCompilerError("checker spec weakens file size limit")
    if effective_policy.get("maximum_package_size_bytes") is not None:
        _require_blocking_rule(by_primitive, "limit_package_size")
        if (
            by_primitive["limit_package_size"]["config"].get("maximum_package_size_bytes")
            != effective_policy["maximum_package_size_bytes"]
        ):
            raise PreSubmitCheckerCompilerError("checker spec weakens package size limit")
    packaging = effective_policy.get("packaging", {})
    if packaging.get("package_required") or packaging.get("allowed_package_formats"):
        _require_blocking_rule(by_primitive, "require_packaging")
        if by_primitive["require_packaging"]["config"] != _canonical_value(packaging):
            raise PreSubmitCheckerCompilerError("checker spec weakens packaging requirements")

    default_policy = effective_policy.get("workstream_default_policy")
    if not isinstance(default_policy, dict):
        raise PreSubmitCheckerCompilerError("effective policy lacks Workstream defaults")
    _require_config_contains(
        by_primitive["validate_submission_packet"],
        "fields",
        default_policy.get("required_packet_fields", []),
        "Workstream default packet fields",
    )
    _require_config_contains(
        by_primitive["forbid_artifact"],
        "patterns",
        [artifact["pattern"] for artifact in default_policy.get("forbidden_artifacts", [])],
        "Workstream default forbidden artifacts",
    )
    _require_config_contains(
        by_primitive["require_attestation"],
        "terms",
        default_policy.get("attestation_terms", []),
        "Workstream default attestation terms",
    )


def _require_blocking_rule(by_primitive: dict[str, dict[str, Any]], primitive: str) -> None:
    """Require one blocking primitive rule."""
    rule = by_primitive.get(primitive)
    if rule is None:
        raise PreSubmitCheckerCompilerError(f"checker spec omits {primitive}")
    if rule["severity"] != BLOCKING_SEVERITY:
        raise PreSubmitCheckerCompilerError(f"checker spec weakens severity for {primitive}")


def _require_warning_rule(by_primitive: dict[str, dict[str, Any]], primitive: str) -> None:
    """Require one warning-only primitive rule."""
    rule = by_primitive.get(primitive)
    if rule is None:
        raise PreSubmitCheckerCompilerError(f"checker spec omits {primitive}")
    if rule["severity"] != WARNING_SEVERITY:
        raise PreSubmitCheckerCompilerError(f"checker spec escalates warning-only rule for {primitive}")
    if rule["config"] != {}:
        raise PreSubmitCheckerCompilerError(f"checker spec adds config for warning-only rule {primitive}")


def _require_config_values(
    rule: dict[str, Any],
    config_key: str,
    expected_values: list[Any],
    label: str,
) -> None:
    """Require a rule config list to exactly match expected values."""
    actual_values = set(rule["config"].get(config_key, []))
    expected_value_set = set(expected_values)
    missing_values = sorted(expected_value_set.difference(actual_values))
    if missing_values:
        raise PreSubmitCheckerCompilerError(
            f"checker spec omits {label}: {', '.join(str(value) for value in missing_values)}"
        )
    extra_values = sorted(actual_values.difference(expected_value_set))
    if extra_values:
        raise PreSubmitCheckerCompilerError(
            f"checker spec adds untraceable {label}: {', '.join(str(value) for value in extra_values)}"
        )


def _require_config_contains(
    rule: dict[str, Any],
    config_key: str,
    expected_values: list[Any],
    label: str,
) -> None:
    """Require a rule config list to include platform-default values."""
    actual_values = set(rule["config"].get(config_key, []))
    missing_values = sorted(set(expected_values).difference(actual_values))
    if missing_values:
        raise PreSubmitCheckerCompilerError(
            f"checker spec omits {label}: {', '.join(str(value) for value in missing_values)}"
        )


def _expected_primitives(effective_policy: dict[str, Any]) -> set[str]:
    """Return primitive rules required to enforce one effective policy."""
    expected = {
        "enforce_storage_scheme",
        "validate_submission_packet",
        "warn_low_quality_generated_artifact",
    }
    if effective_policy.get("manifest_required"):
        expected.add("require_manifest_field")
    if effective_policy.get("artifact_hash_required"):
        expected.add("verify_hash")
    required_artifacts = _policy_object_list(effective_policy, "required_artifacts")
    if [artifact["key"] for artifact in required_artifacts if artifact.get("required", True)]:
        expected.add("require_file")
    required_evidence = _policy_object_list(effective_policy, "required_evidence")
    if [evidence["key"] for evidence in required_evidence if evidence.get("required", True)]:
        expected.add("require_minimum_evidence")
    if effective_policy.get("forbidden_artifacts", []):
        expected.add("forbid_artifact")
    if effective_policy.get("attestation_terms", []):
        expected.add("require_attestation")
    if effective_policy.get("maximum_file_size_bytes") is not None:
        expected.add("limit_file_size")
    if effective_policy.get("maximum_package_size_bytes") is not None:
        expected.add("limit_package_size")
    packaging = effective_policy.get("packaging", {})
    if not isinstance(packaging, dict):
        raise PreSubmitCheckerCompilerError(
            "effective project submission artifact policy packaging must be an object"
        )
    if packaging.get("package_required") or packaging.get("allowed_package_formats"):
        expected.add("require_packaging")
    return expected


def _policy_object_list(effective_policy: dict[str, Any], field: str) -> list[dict[str, Any]]:
    """Return a policy list that must contain object entries with keys."""
    values = effective_policy.get(field, [])
    if not isinstance(values, list):
        raise PreSubmitCheckerCompilerError(
            f"effective project submission artifact policy {field} must be a list"
        )
    keys: set[str] = set()
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get("key"), str):
            raise PreSubmitCheckerCompilerError(
                f"effective project submission artifact policy {field} entries are invalid"
            )
        key = value["key"]
        if not key or key in keys:
            raise PreSubmitCheckerCompilerError(
                f"effective project submission artifact policy {field} keys are invalid"
            )
        keys.add(key)
    return values


def _required_artifact_path(item: dict[str, Any]) -> str:
    """Require the explicit server-approved path attached to an artifact key."""
    value = item.get("path")
    if not isinstance(value, str) or not is_canonical_relative_path(value):
        raise PreSubmitCheckerCompilerError(
            "effective project submission artifact policy path is invalid"
        )
    return value


def _project_unique_paths(
    items: list[dict[str, Any]],
    *,
    projector: Callable[[dict[str, Any]], str],
    field: str,
) -> list[str]:
    """Project policy identities into unique canonical server-owned paths."""
    paths = [projector(item) for item in items]
    if len(paths) != len(set(paths)):
        raise PreSubmitCheckerCompilerError(
            f"effective project submission artifact policy {field} paths are ambiguous"
        )
    return paths


def _required_evidence_path(item: dict[str, Any]) -> str:
    """Project an evidence identity into Workstream's closed evidence namespace."""
    key = item.get("key")
    if (
        not isinstance(key, str)
        or not key
        or any(
            not (character.isascii() and (character.isalnum() or character in "._-"))
            for character in key
        )
    ):
        raise PreSubmitCheckerCompilerError(
            "effective project submission evidence key is unmappable"
        )
    path = f"evidence/{key}"
    if not is_canonical_relative_path(path):
        raise PreSubmitCheckerCompilerError(
            "effective project submission evidence key is unmappable"
        )
    return path


def _checker_names_for_rules(rules: list[dict[str, Any]]) -> list[str]:
    """Build stable checker-name projections from compiled primitive rules."""
    catalogue = _compiler_catalogue()
    names: list[str] = []
    for rule in rules:
        try:
            name = catalogue.primitive_definition(rule["primitive"]).public_name
        except PreSubmissionCatalogueError as exc:
            raise PreSubmitCheckerCompilerError(
                "compiled checker bundle references unknown catalogue definitions"
            ) from exc
        if name not in names:
            names.append(name)
    return names


def _canonical_value(value: Any) -> Any:
    """Recursively canonicalize JSON-like values."""
    if isinstance(value, dict):
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    return value
