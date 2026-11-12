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
    ContributionPolicyConflict,
)
from app.modules.contributions.models import (
    ContributionAwardDefinition,
    ContributionPolicyVersion,
    ContributionRule,
)
from app.modules.contributions.api.quantities import canonical_award_quantity

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
        version.reward_model_version not in {1, 2}
        or len(rules) != 2
        or {rule.contribution_type for rule in rules} != {"accepted_submission", "completed_review"}
    ):
        conflict()
    header = (version.instrument_type, version.unit_code, version.adapter_binding_id)
    if version.reward_model_version == 1:
        if any(value is not None for value in header):
            conflict()
    elif any(rule.compensation_mode == "compensated" for rule in rules):
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
            if version.reward_model_version == 1:
                if not 1 <= len(items) <= 2 or len({item.instrument_type for item in items}) != len(
                    items
                ):
                    conflict()
            elif rule.contribution_type == "accepted_submission":
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
                or item.reward_model_version != version.reward_model_version
            ):
                conflict()
            if version.reward_model_version == 1:
                if item.task_size is not None:
                    conflict()
            elif (item.instrument_type, item.unit_code, item.adapter_binding_id) != header:
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
