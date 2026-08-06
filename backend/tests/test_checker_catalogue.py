"""Proof for the single pre-submission catalogue and effective plan compiler."""

from __future__ import annotations

from dataclasses import replace
import json
from uuid import uuid4

import pytest

from app.core.hashing import canonical_json_hash
from app.core.config import Settings
from app.main import create_app
from app.modules.checkers.catalogue import (
    PRE_SUBMISSION_CATALOGUE_ID,
    PRE_SUBMISSION_CATALOGUE_SCHEMA_VERSION,
    PreSubmissionCatalogueError,
    PreSubmissionCheckerCatalogue,
    PreSubmissionDisabledBehavior,
    PreSubmissionCheckerPhase,
    PreSubmissionCheckerState,
    build_pre_submission_checker_catalogue,
    parse_disabled_pre_submission_checker_ids,
)
from app.modules.checkers.compiler import (
    compile_effective_project_submission_artifact_policy,
)
from app.modules.checkers.effective_plan import (
    EffectivePreSubmissionPlanError,
    EffectivePreSubmissionPlanLineage,
    PreSubmissionInfrastructureUnavailableError,
    compile_effective_pre_submission_execution_plan,
)


def _effective_policy() -> dict[str, object]:
    default_policy = {
        "required_packet_fields": ["summary", "worker_attestation"],
        "forbidden_artifacts": [{"pattern": ".env"}, {"pattern": ".git/**"}],
        "attestation_terms": ["rights_confirmed"],
    }
    return {
        "workstream_default_policy": default_policy,
        "project_policy": {},
        "required_packet_fields": default_policy["required_packet_fields"],
        "required_artifacts": [
            {"key": "task.toml", "path": "task.toml", "required": True}
        ],
        "required_evidence": [{"key": "results", "required": True}],
        "forbidden_artifacts": default_policy["forbidden_artifacts"],
        "attestation_terms": default_policy["attestation_terms"],
        "manifest_required": True,
        "artifact_hash_required": True,
        "artifact_hash_algorithm": "sha256",
        "allowed_storage_schemes": ["s3"],
        "maximum_file_size_bytes": 1_000_000,
        "maximum_package_size_bytes": 5_000_000,
        "packaging": {"package_required": True, "allowed_package_formats": ["zip"]},
    }


def _compiled_and_lineage() -> tuple[dict[str, object], EffectivePreSubmissionPlanLineage]:
    effective_policy_hash = canonical_json_hash(_effective_policy())
    compiled = compile_effective_project_submission_artifact_policy(
        _effective_policy(), effective_policy_hash
    )
    lineage = EffectivePreSubmissionPlanLineage(
        project_id=uuid4(),
        guide_id=uuid4(),
        guide_version=3,
        source_snapshot_id=uuid4(),
        source_snapshot_hash="sha256:" + "2" * 64,
        effective_policy_id=uuid4(),
        effective_policy_hash=effective_policy_hash,
        pre_submit_policy_id=uuid4(),
        pre_submit_policy_bundle_hash=compiled.compiled_bundle_hash,
    )
    return compiled.compiled_bundle, lineage


def test_catalogue_is_single_canonical_closed_namespace() -> None:
    catalogue = build_pre_submission_checker_catalogue()
    ids = [entry.stable_id for entry in catalogue.entries]

    assert catalogue.catalogue_id == PRE_SUBMISSION_CATALOGUE_ID
    assert catalogue.schema_version == PRE_SUBMISSION_CATALOGUE_SCHEMA_VERSION
    assert len(ids) == len(set(ids)) == 26
    assert ids == [
        entry.stable_id
        for entry in sorted(
            catalogue.entries,
            key=lambda entry: (
                list(PreSubmissionCheckerPhase).index(entry.phase),
                entry.order,
                entry.stable_id,
            ),
        )
    ]
    assert catalogue.manifest_sha256 == canonical_json_hash(dict(catalogue.manifest))

    expected = {
        "enforce_storage_scheme": ("policy.storage_scheme.enforce", "check_evidence_integrity"),
        "require_manifest_field": ("policy.manifest_field.require", "check_evidence_integrity"),
        "limit_file_size": ("policy.file_size.limit", "check_evidence_integrity"),
        "limit_package_size": ("policy.package_size.limit", "check_evidence_integrity"),
    }
    for primitive, (stable_id, public_name) in expected.items():
        definition = catalogue.primitive_definition(primitive)
        assert (definition.stable_id, definition.public_name) == (stable_id, public_name)


def test_catalogue_exact_v01_contract_is_locked() -> None:
    catalogue = build_pre_submission_checker_catalogue()
    actual = {
        "|".join(
            (
                entry.stable_id,
                entry.version,
                entry.public_name,
                entry.classification.value,
                entry.phase.value,
                str(entry.order),
                entry.dispatch_kind.value,
                entry.dispatch_capability,
                entry.primitive or "-",
                entry.disabled_behavior.value,
                ",".join(f"{name}={value}" for name, value in entry.resource_budget),
            )
        )
        for entry in catalogue.entries
    }
    expected = {
        "artifact.outer_zip.valid|v1|artifact.outer_zip.valid|mandatory_security|custody|10|platform_capability|submission_archive.outer_zip_valid|-|infrastructure_unavailable|maximum_results=1",
        "artifact.archive.paths_safe|v1|artifact.archive.paths_safe|mandatory_security|custody|20|platform_capability|submission_archive.paths_safe|-|infrastructure_unavailable|maximum_results=1",
        "artifact.archive.entries_safe|v1|artifact.archive.entries_safe|mandatory_security|custody|30|platform_capability|submission_archive.entries_safe|-|infrastructure_unavailable|maximum_results=1",
        "artifact.archive.resources_bounded|v1|artifact.archive.resources_bounded|mandatory_security|custody|40|platform_capability|submission_archive.resources_bounded|-|infrastructure_unavailable|maximum_results=1",
        "artifact.archive.integrity_verified|v1|artifact.archive.integrity_verified|mandatory_integrity|custody|50|platform_capability|submission_archive.integrity_verified|-|infrastructure_unavailable|maximum_results=1",
        "artifact.archive.identity_computed|v1|artifact.archive.identity_computed|mandatory_integrity|identity|10|platform_capability|artifact_commitment.identity|-|infrastructure_unavailable|maximum_results=1",
        "artifact.manifest.semantic_identity_computed|v1|artifact.manifest.semantic_identity_computed|mandatory_integrity|identity|20|platform_capability|submission_manifest.semantic_identity|-|infrastructure_unavailable|maximum_results=1",
        "artifact.manifest.executable_normalized|v1|artifact.manifest.executable_normalized|mandatory_integrity|identity|30|platform_capability|submission_manifest.executable_normalized|-|infrastructure_unavailable|maximum_results=1",
        "artifact.revision.content_changed|v1|artifact.revision.content_changed|mandatory_integrity|identity|40|platform_capability|submission_change.changed|-|infrastructure_unavailable|maximum_results=1",
        "artifact.scratch.sealed_tree_verified|v1|artifact.scratch.sealed_tree_verified|mandatory_integrity|materialization|10|platform_capability|submission_materialization.sealed_tree_verified|-|infrastructure_unavailable|maximum_results=1",
        "submission.packet.required_fields|v1|check_submission_packet|mandatory_accountability|default_policy|10|platform_capability|validate_submission_packet|-|infrastructure_unavailable|maximum_results=1",
        "submission.attestation.required_topics|v1|check_confidentiality_attestation|mandatory_accountability|default_policy|20|platform_capability|require_attestation|-|infrastructure_unavailable|maximum_results=1",
        "artifact.sensitive_paths.high_confidence|v1|check_forbidden_files|mandatory_security|default_policy|30|platform_capability|forbid_high_confidence_sensitive_path|-|infrastructure_unavailable|maximum_results=1",
        "artifact.quality.placeholder_signal|v1|check_low_quality_generated_artifacts|advisory|default_policy|40|platform_capability|warn_low_quality_generated_artifact|-|record_disabled_and_continue|maximum_results=1",
        "policy.submission_packet.validate|v1|check_submission_packet|mandatory_accountability|project_policy|10|policy_primitive|validate_submission_packet|validate_submission_packet|infrastructure_unavailable|maximum_results=1",
        "policy.storage_scheme.enforce|v1|check_evidence_integrity|mandatory_integrity|project_policy|20|policy_primitive|enforce_storage_scheme|enforce_storage_scheme|infrastructure_unavailable|maximum_results=1",
        "policy.manifest_field.require|v1|check_evidence_integrity|mandatory_integrity|project_policy|30|policy_primitive|require_manifest_field|require_manifest_field|infrastructure_unavailable|maximum_results=1",
        "policy.hash.verify|v1|check_evidence_integrity|mandatory_integrity|project_policy|40|policy_primitive|verify_hash|verify_hash|infrastructure_unavailable|maximum_results=1",
        "policy.file.require|v1|check_required_files|mandatory_accountability|project_policy|50|policy_primitive|require_file|require_file|infrastructure_unavailable|maximum_results=1",
        "policy.evidence.minimum|v1|check_evidence_present|mandatory_accountability|project_policy|60|policy_primitive|require_minimum_evidence|require_minimum_evidence|infrastructure_unavailable|maximum_results=1",
        "policy.artifact.forbid|v1|check_forbidden_files|mandatory_security|project_policy|70|policy_primitive|forbid_artifact|forbid_artifact|infrastructure_unavailable|maximum_results=1",
        "policy.attestation.require|v1|check_confidentiality_attestation|mandatory_accountability|project_policy|80|policy_primitive|require_attestation|require_attestation|infrastructure_unavailable|maximum_results=1",
        "policy.file_size.limit|v1|check_evidence_integrity|mandatory_integrity|project_policy|90|policy_primitive|limit_file_size|limit_file_size|infrastructure_unavailable|maximum_results=1",
        "policy.package_size.limit|v1|check_evidence_integrity|mandatory_integrity|project_policy|100|policy_primitive|limit_package_size|limit_package_size|infrastructure_unavailable|maximum_results=1",
        "policy.packaging.require|v1|check_submission_packet|mandatory_accountability|project_policy|110|policy_primitive|require_packaging|require_packaging|infrastructure_unavailable|maximum_results=1",
        "policy.generated_quality.warn|v1|check_low_quality_generated_artifacts|advisory|project_policy|120|policy_primitive|warn_low_quality_generated_artifact|warn_low_quality_generated_artifact|record_disabled_and_continue|maximum_results=1",
    }

    assert actual == expected


def test_catalogue_manifest_does_not_install_broad_generic_path_heuristics() -> None:
    manifest = json.dumps(dict(build_pre_submission_checker_catalogue().manifest), sort_keys=True)
    for forbidden_heuristic in ("token*", "secret*", "credential*", "node_modules"):
        assert forbidden_heuristic not in manifest


def test_catalogue_rejects_unknown_duplicate_and_unsafe_dependency_configuration() -> None:
    with pytest.raises(PreSubmissionCatalogueError, match="unknown"):
        build_pre_submission_checker_catalogue(disabled_entry_ids=frozenset({"unknown"}))
    with pytest.raises(PreSubmissionCatalogueError, match="duplicates"):
        parse_disabled_pre_submission_checker_ids(
            "artifact.outer_zip.valid,artifact.outer_zip.valid"
        )

    valid = build_pre_submission_checker_catalogue()
    first = valid.entries[0]
    duplicate = tuple(
        sorted(
            (*valid.entries, first), key=lambda entry: (entry.phase, entry.order, entry.stable_id)
        )
    )
    with pytest.raises(PreSubmissionCatalogueError, match="duplicate stable IDs"):
        PreSubmissionCheckerCatalogue(
            valid.catalogue_id, valid.version, valid.schema_version, duplicate
        )

    version_alias = tuple(
        sorted(
            (*valid.entries, replace(first, version="v2")),
            key=lambda entry: (entry.phase, entry.order, entry.stable_id),
        )
    )
    with pytest.raises(PreSubmissionCatalogueError, match="duplicate stable IDs"):
        PreSubmissionCheckerCatalogue(
            valid.catalogue_id, valid.version, valid.schema_version, version_alias
        )

    broken = (replace(first, dependencies=("missing.definition",)), *valid.entries[1:])
    with pytest.raises(PreSubmissionCatalogueError, match="dependency is missing"):
        PreSubmissionCheckerCatalogue(
            valid.catalogue_id, valid.version, valid.schema_version, broken
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"stable_id": ""}, "identity"),
        ({"order": -1}, "order"),
        (
            {"dependencies": ("artifact.outer_zip.valid", "artifact.outer_zip.valid")},
            "duplicate dependencies",
        ),
        ({"typed_inputs": ()}, "typed inputs"),
        ({"resource_budget": (("maximum_results", -1),)}, "resource budget"),
        (
            {"disabled_behavior": PreSubmissionDisabledBehavior.RECORD_DISABLED_AND_CONTINUE},
            "mandatory catalogue definition may not skip",
        ),
        ({"dispatch_capability": "unknown.capability"}, "capability is unknown"),
    ],
)
def test_catalogue_definition_validation_fails_closed(
    mutation: dict[str, object], message: str
) -> None:
    definition = build_pre_submission_checker_catalogue().entries[0]
    with pytest.raises(PreSubmissionCatalogueError, match=message):
        replace(definition, **mutation)


def test_catalogue_rejects_noncanonical_order_and_dependency_order() -> None:
    catalogue = build_pre_submission_checker_catalogue()
    with pytest.raises(PreSubmissionCatalogueError, match="not canonical"):
        PreSubmissionCheckerCatalogue(
            catalogue.catalogue_id,
            catalogue.version,
            catalogue.schema_version,
            tuple(reversed(catalogue.entries)),
        )
    first, second, *rest = catalogue.entries
    broken_first = replace(first, dependencies=(second.stable_id,))
    broken = tuple(
        sorted(
            (broken_first, second, *rest),
            key=lambda entry: (
                list(PreSubmissionCheckerPhase).index(entry.phase),
                entry.order,
                entry.stable_id,
            ),
        )
    )
    with pytest.raises(PreSubmissionCatalogueError, match="dependency order"):
        PreSubmissionCheckerCatalogue(
            catalogue.catalogue_id,
            catalogue.version,
            catalogue.schema_version,
            broken,
        )


def test_mandatory_disabled_fails_closed_and_advisory_disabled_stays_visible() -> None:
    compiled_bundle, lineage = _compiled_and_lineage()
    mandatory_disabled = build_pre_submission_checker_catalogue(
        disabled_entry_ids=frozenset({"artifact.outer_zip.valid"})
    )
    assert mandatory_disabled.available is False
    with pytest.raises(
        PreSubmissionInfrastructureUnavailableError,
        match="pre_submission_infrastructure_unavailable",
    ):
        compile_effective_pre_submission_execution_plan(
            lineage=lineage,
            effective_policy=_effective_policy(),
            compiled_bundle=compiled_bundle,
            catalogue=mandatory_disabled,
        )

    advisory_disabled = build_pre_submission_checker_catalogue(
        disabled_entry_ids=frozenset({"artifact.quality.placeholder_signal"})
    )
    plan = compile_effective_pre_submission_execution_plan(
        lineage=lineage,
        effective_policy=_effective_policy(),
        compiled_bundle=compiled_bundle,
        catalogue=advisory_disabled,
    )
    entry = next(
        item for item in plan.entries if item.definition_id == "artifact.quality.placeholder_signal"
    )
    assert entry.state == PreSubmissionCheckerState.DISABLED.value
    assert entry.disabled_behavior == "record_disabled_and_continue"


def test_effective_plan_is_deterministic_and_commits_to_lineage_catalogue_and_config() -> None:
    compiled_bundle, lineage = _compiled_and_lineage()
    first = compile_effective_pre_submission_execution_plan(
        lineage=lineage,
        effective_policy=_effective_policy(),
        compiled_bundle=compiled_bundle,
        catalogue=build_pre_submission_checker_catalogue(),
    )
    second = compile_effective_pre_submission_execution_plan(
        lineage=lineage,
        effective_policy=_effective_policy(),
        compiled_bundle=compiled_bundle,
        catalogue=build_pre_submission_checker_catalogue(),
    )
    assert first == second
    assert first.plan_sha256 == canonical_json_hash(first.as_dict())
    assert (
        first.catalogue_manifest_sha256 == build_pre_submission_checker_catalogue().manifest_sha256
    )
    assert {entry.definition_id for entry in first.entries}.issuperset(
        {
            "artifact.outer_zip.valid",
            "artifact.manifest.semantic_identity_computed",
            "submission.packet.required_fields",
            "policy.file.require",
        }
    )
    assert all(entry.configuration_sha256 for entry in first.entries)
    required_file = next(
        entry for entry in first.entries if entry.definition_id == "policy.file.require"
    )
    exported = required_file.as_dict()
    exported["configuration"]["artifact_paths"].append("mutated-after-hash")
    assert required_file.as_dict()["configuration"]["artifact_paths"] == ["task.toml"]
    assert hash(required_file)
    assert first.plan_sha256 == canonical_json_hash(first.as_dict())

    changed_lineage = replace(lineage, project_id=uuid4())
    changed = compile_effective_pre_submission_execution_plan(
        lineage=changed_lineage,
        effective_policy=_effective_policy(),
        compiled_bundle=compiled_bundle,
        catalogue=build_pre_submission_checker_catalogue(),
    )
    assert changed.plan_sha256 != first.plan_sha256

    advisory_disabled = build_pre_submission_checker_catalogue(
        disabled_entry_ids=frozenset({"artifact.quality.placeholder_signal"})
    )
    state_changed = compile_effective_pre_submission_execution_plan(
        lineage=lineage,
        effective_policy=_effective_policy(),
        compiled_bundle=compiled_bundle,
        catalogue=advisory_disabled,
    )
    assert state_changed.plan_sha256 != first.plan_sha256
    first_rule_ids = {
        entry.definition_id: entry.rule_instance_id
        for entry in first.entries
        if entry.rule_instance_id is not None
    }
    state_changed_rule_ids = {
        entry.definition_id: entry.rule_instance_id
        for entry in state_changed.entries
        if entry.rule_instance_id is not None
    }
    assert state_changed_rule_ids.keys() == first_rule_ids.keys()
    assert all(
        state_changed_rule_ids[definition_id] != rule_instance_id
        for definition_id, rule_instance_id in first_rule_ids.items()
    )


def test_effective_plan_rejects_stale_or_non_catalogue_bundle_facts() -> None:
    compiled_bundle, lineage = _compiled_and_lineage()
    with pytest.raises(EffectivePreSubmissionPlanError, match="hash mismatch"):
        compile_effective_pre_submission_execution_plan(
            lineage=replace(
                lineage,
                pre_submit_policy_bundle_hash="sha256:" + "9" * 64,
            ),
            effective_policy=_effective_policy(),
            compiled_bundle=compiled_bundle,
            catalogue=build_pre_submission_checker_catalogue(),
        )

    altered = {**compiled_bundle, "rules": [dict(rule) for rule in compiled_bundle["rules"]]}
    altered["rules"][0]["primitive"] = "legacy_alias"
    altered_lineage = replace(
        lineage,
        pre_submit_policy_bundle_hash=canonical_json_hash(altered),
    )
    with pytest.raises(EffectivePreSubmissionPlanError, match="unknown"):
        compile_effective_pre_submission_execution_plan(
            lineage=altered_lineage,
            effective_policy=_effective_policy(),
            compiled_bundle=altered,
            catalogue=build_pre_submission_checker_catalogue(),
        )

    stale_envelope = {**compiled_bundle, "compiler_version": "obsolete"}
    with pytest.raises(EffectivePreSubmissionPlanError, match="envelope"):
        compile_effective_pre_submission_execution_plan(
            lineage=replace(
                lineage,
                pre_submit_policy_bundle_hash=canonical_json_hash(stale_envelope),
            ),
            effective_policy=_effective_policy(),
            compiled_bundle=stale_envelope,
            catalogue=build_pre_submission_checker_catalogue(),
        )


def test_effective_plan_rejects_bundle_that_omits_locked_required_rule() -> None:
    compiled_bundle, lineage = _compiled_and_lineage()
    altered = {
        **compiled_bundle,
        "rules": [
            dict(rule)
            for rule in compiled_bundle["rules"]
            if rule["primitive"] != "require_file"
        ],
    }
    altered_lineage = replace(
        lineage,
        pre_submit_policy_bundle_hash=canonical_json_hash(altered),
    )

    with pytest.raises(EffectivePreSubmissionPlanError, match="locked effective policy"):
        compile_effective_pre_submission_execution_plan(
            lineage=altered_lineage,
            effective_policy=_effective_policy(),
            compiled_bundle=altered,
            catalogue=build_pre_submission_checker_catalogue(),
        )


def test_effective_plan_rejects_policy_body_that_does_not_match_locked_hash() -> None:
    compiled_bundle, lineage = _compiled_and_lineage()
    weakened_policy = {
        **_effective_policy(),
        "required_artifacts": [],
    }

    with pytest.raises(EffectivePreSubmissionPlanError, match="policy hash mismatch"):
        compile_effective_pre_submission_execution_plan(
            lineage=lineage,
            effective_policy=weakened_policy,
            compiled_bundle=compiled_bundle,
            catalogue=build_pre_submission_checker_catalogue(),
        )


def test_effective_plan_lineage_rejects_ambiguous_identity_version_and_hash() -> None:
    _, lineage = _compiled_and_lineage()
    with pytest.raises(EffectivePreSubmissionPlanError, match="lineage id"):
        replace(lineage, project_id="not-a-uuid")
    with pytest.raises(EffectivePreSubmissionPlanError, match="guide version"):
        replace(lineage, guide_version=0)
    with pytest.raises(EffectivePreSubmissionPlanError, match="lineage hash"):
        replace(lineage, source_snapshot_hash="sha256:bad")


def test_compiler_uses_catalogue_without_durable_checker_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.checkers import runner

    monkeypatch.setattr(
        runner,
        "default_checker_registry",
        lambda: (_ for _ in ()).throw(AssertionError("durable registry used")),
    )
    compiled = compile_effective_project_submission_artifact_policy(
        _effective_policy(), "sha256:" + "3" * 64
    )
    assert "check_evidence_integrity" in compiled.checker_names
    assert "check_submission_packet" in compiled.checker_names


async def test_application_startup_installs_fixed_catalogue_configuration() -> None:
    app = create_app(
        Settings(
            environment="test",
            artifact_pre_submission_checker_disabled_ids="artifact.quality.placeholder_signal",
        )
    )
    async with app.router.lifespan_context(app):
        catalogue = app.state.pre_submission_checker_catalogue
        assert catalogue.definition("artifact.quality.placeholder_signal").state is (
            PreSubmissionCheckerState.DISABLED
        )


async def test_application_startup_rejects_unknown_catalogue_configuration() -> None:
    app = create_app(
        Settings(
            environment="test",
            artifact_pre_submission_checker_disabled_ids="unknown.definition",
        )
    )
    with pytest.raises(PreSubmissionCatalogueError, match="unknown"):
        async with app.router.lifespan_context(app):
            pass
