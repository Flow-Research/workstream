"""Shared locked policy graph and resource eligibility for publication and binding."""

from uuid import UUID

from app.modules.compensation.api import (
    CompensationInstrumentType,
    PolicyAdapterBindingPort,
    PolicyAdapterBindingUnavailable,
)
from app.modules.contributions.api import (
    ContributionPolicyConflict,
    PolicyDefinitionInput,
    PolicyRuleInput,
)
from app.modules.contributions.models import (
    ContributionAwardDefinition,
    ContributionPolicyVersion,
    ContributionRule,
)
from app.modules.contributions.policy_graph import _canonical_quantity
from app.modules.contributions.policy_validation import validate_policy_graph
from app.modules.contributions.repository import ContributionPolicyRepository


def require_complete_policy_graph(
    version: ContributionPolicyVersion,
    rules: list[ContributionRule],
    definitions: list[ContributionAwardDefinition],
) -> None:
    """Check complete canonical rules and every child's exact persisted ownership."""
    attached = []
    inputs = []
    for rule in rules:
        if (
            rule.project_id != version.project_id
            or rule.contribution_policy_version_id != version.id
        ):
            raise ContributionPolicyConflict("contribution_policy_conflict")
        items = []
        for item in rule.award_definitions:
            if (
                item.project_id != version.project_id
                or item.contribution_policy_version_id != version.id
                or item.contribution_rule_id != rule.id
                or item.contribution_type != rule.contribution_type
            ):
                raise ContributionPolicyConflict("contribution_policy_conflict")
            try:
                instrument = CompensationInstrumentType(item.instrument_type)
            except ValueError:
                raise ContributionPolicyConflict("contribution_policy_conflict") from None
            items.append(
                PolicyDefinitionInput(
                    instrument_type=instrument,
                    unit_code=item.unit_code,
                    quantity=_canonical_quantity(item.quantity),
                    adapter_binding_id=UUID(str(item.adapter_binding_id)),
                )
            )
            attached.append(item.id)
        inputs.append(
            PolicyRuleInput(
                contribution_type=rule.contribution_type,
                compensation_mode=rule.compensation_mode,
                definitions=tuple(items),
            )
        )
    if sorted(attached) != sorted(item.id for item in definitions):
        raise ContributionPolicyConflict("contribution_policy_conflict")
    validate_policy_graph(tuple(inputs))


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
