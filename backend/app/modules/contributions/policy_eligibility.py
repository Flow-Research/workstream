"""Shared locked policy graph and resource eligibility for publication and binding."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.modules.compensation.api import (
    CompensationInstrumentType,
    PolicyAdapterBindingPort,
    PolicyAdapterBindingUnavailable,
)
from app.modules.contributions.api import (
    ContributionPolicyConflict, ContributionPolicyUnavailable, RewardSelectionFacts, RewardSelectionRequest,
)
from app.modules.contributions.models import (
    ContributionAwardDefinition,
    ContributionPolicyVersion,
    ContributionRule,
)
from app.modules.contributions.api.quantities import canonical_award_quantity
from app.core.financial_wire import format_award_quantity

if TYPE_CHECKING:
    from app.modules.contributions.repository import ContributionPolicyRepository


def require_complete_policy_graph(
    version: ContributionPolicyVersion,
    rules: list[ContributionRule],
    definitions: list[ContributionAwardDefinition],
) -> None:
    """Check complete canonical rules and every child's exact persisted ownership."""

    def conflict():
        raise ContributionPolicyConflict("contribution_policy_conflict")

    if (
        len(rules) != 2
        or {rule.contribution_type for rule in rules} != {"accepted_submission", "completed_review"}
    ):
        conflict()
    header = (version.instrument_type, version.unit_code, version.adapter_binding_id)
    if any(rule.compensation_mode == "compensated" for rule in rules):
        if any(value is None for value in header):
            conflict()
    elif any(value is not None for value in header):
        conflict()
    attached = []
    for rule in rules:
        if (
            rule.project_id != version.project_id
            or rule.contribution_policy_version_id != version.id
        ):
            conflict()
        items = rule.award_definitions
        if rule.compensation_mode == "unpaid":
            if items:
                conflict()
        elif rule.compensation_mode == "compensated":
            if rule.contribution_type == "accepted_submission":
                if len(items) != 3 or {item.task_size for item in items} != {
                    "small",
                    "medium",
                    "large",
                }:
                    conflict()
            elif len(items) != 1 or items[0].task_size is not None:
                conflict()
        else:
            conflict()
        for item in items:
            if (
                item.project_id != version.project_id
                or item.contribution_policy_version_id != version.id
                or item.contribution_rule_id != rule.id
                or item.contribution_type != rule.contribution_type
            ):
                conflict()
            if (item.instrument_type, item.unit_code, item.adapter_binding_id) != header:
                conflict()
            try:
                canonical_award_quantity(
                    format(item.quantity, "f"), CompensationInstrumentType(item.instrument_type)
                )
            except (ValueError, TypeError):
                conflict()
            attached.append(item.id)
    if len(set(attached)) != len(attached) or sorted(attached) != sorted(
        item.id for item in definitions
    ):
        conflict()


async def lock_policy_resources(
    repository: ContributionPolicyRepository,
    bindings: PolicyAdapterBindingPort,
    project_id: UUID,
    definitions: list[ContributionAwardDefinition],
) -> None:
    """Lock sorted units then sorted binding owners and validate current eligibility."""
    units = sorted({(item.instrument_type, item.unit_code) for item in definitions})
    for instrument, unit_code in units:
        unit = await repository.lock_unit(project_id, instrument, unit_code)
        if unit is None or unit.status != "active":
            raise ContributionPolicyConflict("contribution_policy_not_found")
    by_binding = {item.adapter_binding_id: item for item in definitions}
    if any(
        by_binding[item.adapter_binding_id].instrument_type != item.instrument_type
        for item in definitions
    ):
        raise ContributionPolicyConflict("contribution_policy_conflict")
    for item in (by_binding[key] for key in sorted(by_binding, key=str)):
        try:
            binding = await bindings.lock_policy_adapter_binding(
                project_id=project_id,
                adapter_binding_id=item.adapter_binding_id,
                instrument_type=CompensationInstrumentType(item.instrument_type),
            )
        except (PolicyAdapterBindingUnavailable, ValueError) as exc:
            raise ContributionPolicyConflict("contribution_policy_not_found") from exc
        if (
            binding.project_id != project_id
            or binding.adapter_binding_id != item.adapter_binding_id
            or binding.instrument_type.value != item.instrument_type
        ):
            raise ContributionPolicyConflict("contribution_policy_not_found")


def reward_selection_facts(version, checked: RewardSelectionRequest) -> RewardSelectionFacts:
    """Validate one complete policy graph and select the exact requested size."""
    if version is None:
        raise ContributionPolicyUnavailable("reward_selection_unavailable")
    rules = list(version.rules)
    definitions = [definition for rule in rules for definition in rule.award_definitions]
    try:
        require_complete_policy_graph(version, rules, definitions)
    except ContributionPolicyConflict as exc:
        raise ContributionPolicyUnavailable("reward_selection_unavailable") from exc
    rule = next(rule for rule in rules if rule.contribution_type == "accepted_submission")
    common = dict(
        policy_version_id=version.id,
        task_size=checked.task_size,
        compensation_mode=rule.compensation_mode,
    )
    if rule.compensation_mode == "unpaid":
        return RewardSelectionFacts(
            **common,
            award_definition_id=None,
            instrument_type=None,
            unit_code=None,
            quantity=None,
            adapter_binding_id=None,
        )
    selected = next(
        item for item in rule.award_definitions if item.task_size == checked.task_size
    )
    return RewardSelectionFacts(
        **common,
        award_definition_id=selected.id,
        instrument_type=CompensationInstrumentType(selected.instrument_type),
        unit_code=selected.unit_code,
        quantity=format_award_quantity(selected.quantity),
        adapter_binding_id=selected.adapter_binding_id,
    )
