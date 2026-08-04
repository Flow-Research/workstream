"""Pure compiler for one locked effective pre-submission execution plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.checkers.catalogue import (
    PreSubmissionCheckerCatalogue,
    PreSubmissionCheckerDefinition,
    PreSubmissionCheckerState,
)
from app.modules.checkers.compiler import (
    PRE_SUBMIT_BUNDLE_SCHEMA_VERSION,
    PRE_SUBMIT_COMPILER_VERSION,
    PRIMITIVES_VERSION,
)


EFFECTIVE_PRE_SUBMISSION_PLAN_SCHEMA_VERSION = "effective_pre_submission_plan.v1"
EFFECTIVE_PRE_SUBMISSION_PLAN_HASH_DOMAIN = "workstream.effective_pre_submission_plan.v1"


class EffectivePreSubmissionPlanError(ValueError):
    """Reject a stale, ambiguous, or unavailable effective plan."""


class PreSubmissionInfrastructureUnavailableError(EffectivePreSubmissionPlanError):
    """Fail preparation closed when mandatory deployment capability is disabled."""


@dataclass(frozen=True, slots=True)
class EffectivePreSubmissionPlanLineage:
    """Exact server-locked lineage for one future preparation request."""

    project_id: UUID
    guide_id: UUID
    guide_version: int
    source_snapshot_id: UUID
    source_snapshot_hash: str
    effective_policy_id: UUID
    effective_policy_hash: str
    pre_submit_policy_id: UUID
    pre_submit_policy_bundle_hash: str

    def __post_init__(self) -> None:
        if any(
            type(value) is not UUID
            for value in (
                self.project_id,
                self.guide_id,
                self.source_snapshot_id,
                self.effective_policy_id,
                self.pre_submit_policy_id,
            )
        ):
            raise EffectivePreSubmissionPlanError("effective plan lineage id is invalid")
        if type(self.guide_version) is not int or self.guide_version <= 0:
            raise EffectivePreSubmissionPlanError("effective plan guide version is invalid")
        for value in (
            self.source_snapshot_hash,
            self.effective_policy_hash,
            self.pre_submit_policy_bundle_hash,
        ):
            _validate_sha256(value)

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": str(self.project_id),
            "guide_id": str(self.guide_id),
            "guide_version": self.guide_version,
            "source_snapshot_id": str(self.source_snapshot_id),
            "source_snapshot_hash": self.source_snapshot_hash,
            "effective_policy_id": str(self.effective_policy_id),
            "effective_policy_hash": self.effective_policy_hash,
            "pre_submit_policy_id": str(self.pre_submit_policy_id),
            "pre_submit_policy_bundle_hash": self.pre_submit_policy_bundle_hash,
        }


@dataclass(frozen=True, slots=True)
class EffectivePreSubmissionPlanEntry:
    """One ordered definition or deterministic locked-policy rule instance."""

    definition_id: str
    definition_version: str
    public_name: str
    phase: str
    order: int
    dependencies: tuple[str, ...]
    classification: str
    state: str
    disabled_behavior: str
    dispatch_kind: str
    dispatch_capability: str
    typed_inputs: tuple[str, ...]
    result_schema: str
    failure_code: str
    resource_budget: tuple[tuple[str, int], ...]
    policy_trace_source: str
    rule_instance_id: str | None
    configuration: dict[str, Any]
    configuration_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "definition_id": self.definition_id,
            "definition_version": self.definition_version,
            "public_name": self.public_name,
            "phase": self.phase,
            "order": self.order,
            "dependencies": list(self.dependencies),
            "classification": self.classification,
            "state": self.state,
            "disabled_behavior": self.disabled_behavior,
            "dispatch_kind": self.dispatch_kind,
            "dispatch_capability": self.dispatch_capability,
            "typed_inputs": list(self.typed_inputs),
            "result_schema": self.result_schema,
            "failure_code": self.failure_code,
            "resource_budget": dict(self.resource_budget),
            "policy_trace_source": self.policy_trace_source,
            "rule_instance_id": self.rule_instance_id,
            "configuration": self.configuration,
            "configuration_sha256": self.configuration_sha256,
        }


@dataclass(frozen=True, slots=True)
class EffectivePreSubmissionExecutionPlan:
    """Canonical side-effect-free plan consumed by later execution chunks."""

    lineage: EffectivePreSubmissionPlanLineage
    catalogue_id: str
    catalogue_version: str
    catalogue_schema_version: str
    catalogue_manifest_sha256: str
    entries: tuple[EffectivePreSubmissionPlanEntry, ...]
    plan_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return _plan_body(
            self.lineage,
            self.catalogue_id,
            self.catalogue_version,
            self.catalogue_schema_version,
            self.catalogue_manifest_sha256,
            self.entries,
        )


def compile_effective_pre_submission_execution_plan(
    *,
    lineage: EffectivePreSubmissionPlanLineage,
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
    rules = compiled_bundle.get("rules")
    if not isinstance(rules, list) or not rules:
        raise EffectivePreSubmissionPlanError("compiled checker bundle rules are invalid")

    entries = [
        _entry_from_definition(definition, configuration={}, rule_instance_id=None)
        for definition in catalogue.entries
        if definition.primitive is None
    ]
    seen_primitives: set[str] = set()
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
    body = _plan_body(
        lineage,
        catalogue.catalogue_id,
        catalogue.version,
        catalogue.schema_version,
        catalogue.manifest_sha256,
        ordered_entries,
    )
    return EffectivePreSubmissionExecutionPlan(
        lineage=lineage,
        catalogue_id=catalogue.catalogue_id,
        catalogue_version=catalogue.version,
        catalogue_schema_version=catalogue.schema_version,
        catalogue_manifest_sha256=catalogue.manifest_sha256,
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
    return EffectivePreSubmissionPlanEntry(
        definition_id=definition.stable_id,
        definition_version=definition.version,
        public_name=definition.public_name,
        phase=definition.phase.value,
        order=definition.order,
        dependencies=definition.dependencies,
        classification=definition.classification.value,
        state=definition.state.value,
        disabled_behavior=definition.disabled_behavior.value,
        dispatch_kind=definition.dispatch_kind.value,
        dispatch_capability=definition.dispatch_capability,
        typed_inputs=definition.typed_inputs,
        result_schema=definition.result_schema,
        failure_code=definition.failure_code,
        resource_budget=definition.resource_budget,
        policy_trace_source=definition.policy_trace_source,
        rule_instance_id=rule_instance_id,
        configuration=configuration,
        configuration_sha256=configuration_sha256,
    )


def _plan_body(
    lineage: EffectivePreSubmissionPlanLineage,
    catalogue_id: str,
    catalogue_version: str,
    catalogue_schema_version: str,
    catalogue_manifest_sha256: str,
    entries: tuple[EffectivePreSubmissionPlanEntry, ...],
) -> dict[str, Any]:
    return {
        "domain": EFFECTIVE_PRE_SUBMISSION_PLAN_HASH_DOMAIN,
        "schema_version": EFFECTIVE_PRE_SUBMISSION_PLAN_SCHEMA_VERSION,
        "lineage": lineage.as_dict(),
        "catalogue": {
            "id": catalogue_id,
            "version": catalogue_version,
            "schema_version": catalogue_schema_version,
            "manifest_sha256": catalogue_manifest_sha256,
        },
        "entries": [entry.as_dict() for entry in entries],
    }


def _phase_order(phase: str) -> int:
    return {
        "custody": 0,
        "identity": 1,
        "materialization": 2,
        "default_policy": 3,
        "project_policy": 4,
    }[phase]


def _validate_sha256(value: str) -> None:
    if (
        type(value) is not str
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise EffectivePreSubmissionPlanError("effective plan lineage hash is invalid")
