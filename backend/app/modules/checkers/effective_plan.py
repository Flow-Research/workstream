"""Pure compiler for one locked effective pre-submission execution plan."""

from __future__ import annotations

from typing import Any

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api import (
    EffectivePreSubmissionExecutionPlan,
    EffectivePreSubmissionPlanEntry,
    EffectivePreSubmissionPlanError,
    EffectivePreSubmissionPlanLineage,
    FrozenJsonObject,
    PreSubmissionInfrastructureUnavailableError,
)
from app.modules.checkers.api.pre_submit import effective_plan_body, freeze_json
from app.modules.checkers.catalogue import (
    PreSubmissionCheckerCatalogue,
    PreSubmissionCheckerDefinition,
    PreSubmissionCheckerPhase,
    PreSubmissionCheckerState,
    pre_submission_phase_order,
)
from app.modules.checkers.compiler import (
    PRE_SUBMIT_BUNDLE_SCHEMA_VERSION,
    PRE_SUBMIT_COMPILER_VERSION,
    PRIMITIVES_VERSION,
    PreSubmitCheckerCompilerError,
    validate_compiled_pre_submit_checker_bundle,
)


def compile_effective_pre_submission_execution_plan(
    *,
    lineage: EffectivePreSubmissionPlanLineage,
    effective_policy: dict[str, Any],
    compiled_bundle: dict[str, Any],
    catalogue: PreSubmissionCheckerCatalogue,
) -> EffectivePreSubmissionExecutionPlan:
    """Compose platform definitions and locked project rules without execution."""
    if not catalogue.available:
        raise PreSubmissionInfrastructureUnavailableError(
            "pre_submission_infrastructure_unavailable"
        )
    if canonical_json_hash(compiled_bundle) != lineage.pre_submit_policy_bundle_hash:
        raise EffectivePreSubmissionPlanError("compiled checker bundle hash mismatch")
    if (
        compiled_bundle.get("schema_version") != PRE_SUBMIT_BUNDLE_SCHEMA_VERSION
        or compiled_bundle.get("compiler_version") != PRE_SUBMIT_COMPILER_VERSION
        or compiled_bundle.get("primitives_version") != PRIMITIVES_VERSION
    ):
        raise EffectivePreSubmissionPlanError("compiled checker bundle envelope is invalid")
    if compiled_bundle.get("effective_policy_hash") != lineage.effective_policy_hash:
        raise EffectivePreSubmissionPlanError("compiled checker effective policy mismatch")
    if canonical_json_hash(effective_policy) != lineage.effective_policy_hash:
        raise EffectivePreSubmissionPlanError(
            "locked effective project submission artifact policy hash mismatch"
        )
    try:
        validate_compiled_pre_submit_checker_bundle(
            effective_policy,
            lineage.effective_policy_hash,
            compiled_bundle,
            compiler_version=PRE_SUBMIT_COMPILER_VERSION,
        )
    except PreSubmitCheckerCompilerError as exc:
        raise EffectivePreSubmissionPlanError(
            f"compiled checker bundle does not enforce the locked effective policy: {exc}"
        ) from exc
    rules = compiled_bundle.get("rules")
    if not isinstance(rules, list) or not rules:
        raise EffectivePreSubmissionPlanError("compiled checker bundle rules are invalid")

    entries = [
        _entry_from_definition(definition, configuration={}, rule_instance_id=None)
        for definition in catalogue.entries
        if definition.primitive is None
    ]
    seen_primitives: set[str] = set()
    catalogue_manifest_sha256 = catalogue.manifest_sha256
    for rule in rules:
        if not isinstance(rule, dict):
            raise EffectivePreSubmissionPlanError("compiled checker rule is invalid")
        primitive = rule.get("primitive")
        if not isinstance(primitive, str) or primitive in seen_primitives:
            raise EffectivePreSubmissionPlanError("compiled checker primitive is invalid")
        seen_primitives.add(primitive)
        try:
            definition = catalogue.primitive_definition(primitive)
        except ValueError as exc:
            raise EffectivePreSubmissionPlanError("compiled checker primitive is unknown") from exc
        if definition.state is PreSubmissionCheckerState.DISABLED:
            if definition.classification.mandatory:
                raise PreSubmissionInfrastructureUnavailableError(
                    "pre_submission_infrastructure_unavailable"
                )
        configuration = rule.get("config")
        if not isinstance(configuration, dict):
            raise EffectivePreSubmissionPlanError("compiled checker configuration is invalid")
        if rule.get("policy_fields") != list(definition.policy_fields):
            raise EffectivePreSubmissionPlanError("compiled checker policy trace is invalid")
        expected_severity = "warning" if not definition.classification.mandatory else "blocking"
        if rule.get("severity") != expected_severity:
            raise EffectivePreSubmissionPlanError("compiled checker severity is invalid")
        rule_instance_id = canonical_json_hash(
            {
                "domain": "workstream.pre_submission_rule_instance.v1",
                "catalogue_id": catalogue.catalogue_id,
                "catalogue_version": catalogue.version,
                "catalogue_manifest_sha256": catalogue_manifest_sha256,
                "definition_id": definition.stable_id,
                "definition_version": definition.version,
                "effective_policy_id": str(lineage.effective_policy_id),
                "effective_policy_hash": lineage.effective_policy_hash,
                "pre_submit_policy_id": str(lineage.pre_submit_policy_id),
                "configuration": configuration,
            }
        )
        entries.append(
            _entry_from_definition(
                definition,
                configuration=configuration,
                rule_instance_id=rule_instance_id,
            )
        )
    ordered_entries = tuple(
        sorted(
            entries, key=lambda entry: (_phase_order(entry.phase), entry.order, entry.definition_id)
        )
    )
    body = effective_plan_body(
        lineage,
        catalogue.catalogue_id,
        catalogue.version,
        catalogue.schema_version,
        catalogue_manifest_sha256,
        ordered_entries,
    )
    return EffectivePreSubmissionExecutionPlan(
        lineage=lineage,
        catalogue_id=catalogue.catalogue_id,
        catalogue_version=catalogue.version,
        catalogue_schema_version=catalogue.schema_version,
        catalogue_manifest_sha256=catalogue_manifest_sha256,
        entries=ordered_entries,
        plan_sha256=canonical_json_hash(body),
    )


def _entry_from_definition(
    definition: PreSubmissionCheckerDefinition,
    *,
    configuration: dict[str, Any],
    rule_instance_id: str | None,
) -> EffectivePreSubmissionPlanEntry:
    configuration_sha256 = canonical_json_hash(configuration)
    frozen_configuration = FrozenJsonObject(
        tuple((key, freeze_json(value)) for key, value in sorted(configuration.items()))
    )
    return EffectivePreSubmissionPlanEntry(
        definition_id=definition.stable_id,
        definition_version=definition.version,
        public_name=definition.public_name,
        phase=definition.phase.value,
        order=definition.order,
        dependencies=definition.dependencies,
        classification=definition.classification.value,
        checker_definition_state=definition.state.value,
        disabled_behavior=definition.disabled_behavior.value,
        dispatch_kind=definition.dispatch_kind.value,
        dispatch_capability=definition.dispatch_capability,
        typed_inputs=definition.typed_inputs,
        result_schema=definition.result_schema,
        failure_code=definition.failure_code,
        resource_budget=definition.resource_budget,
        policy_trace_source=definition.policy_trace_source,
        rule_instance_id=rule_instance_id,
        configuration=frozen_configuration,
        configuration_sha256=configuration_sha256,
    )


def _phase_order(phase: str) -> int:
    return pre_submission_phase_order(PreSubmissionCheckerPhase(phase))
