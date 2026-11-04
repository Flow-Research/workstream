"""Verify retained guide compilation evidence without reviving its executor."""

from types import SimpleNamespace
from uuid import UUID

from app.core.hashing import canonical_json_hash

from .contracts import AcceptedCompilationResult


_RETAINED_RESULT = "project_guide_compilation_result.v1"
_RETAINED_COMPONENTS = frozenset(
    {
        "sufficiency_hash",
        "artifact_policy_hash",
        "requirement_inventory_hash",
        "pre_submit_hash",
        "post_submit_hash",
        "capability_suggestions_hash",
        "setup_notes_hash",
    }
)
_RETAINED_TARGET_KEYS = frozenset(
    {
        "project_id",
        "guide_id",
        "compilation_id",
        "guide_version",
        "source_snapshot_id",
        "source_snapshot_hash",
        "setup_run_id",
        "setup_generation",
        "finalization_id",
        "finalization_facts_digest",
        "result_hash",
        "component_hashes",
        "pre_catalogue_id",
        "pre_catalogue_version",
        "pre_catalogue_schema_version",
        "pre_catalogue_manifest_hash",
        "post_catalogue_id",
        "post_catalogue_version",
        "post_catalogue_schema_version",
        "post_catalogue_manifest_hash",
        "artifact_policy_id",
        "artifact_policy_hash",
        "artifact_projection_operation_id",
        "artifact_projection_output_digest",
    }
)


def retained_target(raw: dict) -> SimpleNamespace:
    """Read the exact old target as evidence, never as an approval command."""
    if not isinstance(raw, dict) or set(raw) != _RETAINED_TARGET_KEYS:
        raise ValueError("retained approval target shape mismatch")
    if (
        not isinstance(raw["component_hashes"], dict)
        or set(raw["component_hashes"]) != _RETAINED_COMPONENTS
    ):
        raise ValueError("retained approval component shape mismatch")
    values = dict(raw)
    for name in (
        "project_id",
        "guide_id",
        "compilation_id",
        "source_snapshot_id",
        "setup_run_id",
        "finalization_id",
        "artifact_policy_id",
        "artifact_projection_operation_id",
    ):
        values[name] = UUID(values[name]) if values[name] is not None else None
    values["component_hashes"] = SimpleNamespace(**raw["component_hashes"])
    values["digest"] = canonical_json_hash(raw)
    return SimpleNamespace(**values)


def verified_compilation_result(compilation) -> dict:
    """Check stored content against its own exact component commitments.

    The old shape is a read-only evidence format. It is never parsed as a
    current agent result or returned to a provider for another attempt.
    """
    body = compilation.canonical_result
    hashes = compilation.component_hashes
    if compilation.result_schema_version is not None:
        if compilation.result_schema_version != "project_guide_check_specification.v1":
            raise ValueError("unknown compilation result schema")
        accepted = AcceptedCompilationResult(
            canonical_result=body,
            result_hash=compilation.result_hash,
            component_hashes=hashes,
        )
        return accepted.canonical_result
    if (
        not isinstance(body, dict)
        or body.get("schema_version") != _RETAINED_RESULT
        or not isinstance(hashes, dict)
        or set(hashes) != _RETAINED_COMPONENTS
        or canonical_json_hash(body) != compilation.result_hash
    ):
        raise ValueError("retained compilation result mismatch")
    try:
        requirements = body["requirements"]
        pre_bindings = body["pre_submit_bindings"]
        post_bindings = body["post_submit_bindings"]
        suggestions = body["capability_suggestions"]
        notes = body["setup_notes"]
        expected = {
            "sufficiency_hash": canonical_json_hash(
                {"status": body["status"], "findings": body["findings"]}
            ),
            "artifact_policy_hash": canonical_json_hash(body["submission_artifact_policy"]),
            "requirement_inventory_hash": canonical_json_hash({"requirements": requirements}),
            "pre_submit_hash": canonical_json_hash({"pre_submit_bindings": pre_bindings}),
            "post_submit_hash": canonical_json_hash({"post_submit_bindings": post_bindings}),
            "capability_suggestions_hash": canonical_json_hash(
                {"capability_suggestions": suggestions}
            ),
            "setup_notes_hash": canonical_json_hash({"setup_notes": notes}),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("retained compilation result shape mismatch") from exc
    if hashes != expected:
        raise ValueError("retained compilation component mismatch")
    return body
