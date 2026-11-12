"""Canonical server-owned ContributionPolicy publication graph facts."""

from __future__ import annotations

from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.contributions.api.quantities import format_award_quantity
from app.modules.contributions.models import ContributionPolicyVersion


def publication_graph_facts(version: ContributionPolicyVersion) -> tuple[str, tuple[UUID, ...]]:
    """Return the canonical graph digest and sorted unique adapter bindings."""
    size_order = {None: 0, "small": 0, "medium": 1, "large": 2}
    rules = []
    binding_ids: set[UUID] = set()
    for rule in sorted(version.rules, key=lambda value: (value.contribution_type, str(value.id))):
        definitions = []
        for item in sorted(
            rule.award_definitions,
            key=lambda value: (
                size_order[value.task_size],
                value.instrument_type,
                value.unit_code,
                str(value.adapter_binding_id),
                str(value.id),
            ),
        ):
            binding_ids.add(item.adapter_binding_id)
            definition = {
                "adapter_binding_id": str(item.adapter_binding_id),
                "definition_id": str(item.id),
                "instrument_type": item.instrument_type,
                "quantity": format_award_quantity(item.quantity),
                "unit_code": item.unit_code,
            }
            definition["task_size"] = item.task_size
            definitions.append(definition)
        rules.append(
            {
                "compensation_mode": rule.compensation_mode,
                "contribution_type": rule.contribution_type,
                "definitions": definitions,
                "rule_id": str(rule.id),
            }
        )
    graph = {
        "rules": rules,
        "instrument_type": version.instrument_type,
        "unit_code": version.unit_code,
        "adapter_binding_id": str(version.adapter_binding_id) if version.adapter_binding_id else None,
    }
    return canonical_json_hash(graph), tuple(sorted(binding_ids, key=str))
