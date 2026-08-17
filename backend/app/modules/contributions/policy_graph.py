"""Canonical server-owned ContributionPolicy publication graph facts."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.contributions.models import ContributionPolicyVersion


def publication_graph_facts(version: ContributionPolicyVersion) -> tuple[str, tuple[UUID, ...]]:
    """Return the canonical graph digest and sorted unique adapter bindings."""
    rules = []
    binding_ids: set[UUID] = set()
    for rule in sorted(version.rules, key=lambda value: (value.contribution_type, str(value.id))):
        definitions = []
        for item in sorted(
            rule.award_definitions,
            key=lambda value: (
                value.instrument_type,
                value.unit_code,
                str(value.adapter_binding_id),
                str(value.id),
            ),
        ):
            binding_ids.add(item.adapter_binding_id)
            definitions.append(
                {
                    "adapter_binding_id": str(item.adapter_binding_id),
                    "definition_id": str(item.id),
                    "instrument_type": item.instrument_type,
                    "quantity": _canonical_quantity(item.quantity),
                    "unit_code": item.unit_code,
                }
            )
        rules.append(
            {
                "compensation_mode": rule.compensation_mode,
                "contribution_type": rule.contribution_type,
                "definitions": definitions,
                "rule_id": str(rule.id),
            }
        )
    return canonical_json_hash({"rules": rules}), tuple(sorted(binding_ids, key=str))


def _canonical_quantity(value: Decimal) -> str:
    """Render an exact stored decimal without exponent or redundant zeros."""
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered
