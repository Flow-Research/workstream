"""Project ContributionPolicy ORM graphs into immutable public policy facts."""

from typing import cast
from uuid import UUID

from app.modules.compensation.api import CompensationInstrumentType
from app.modules.contributions.api import ContributionPolicyView, PolicyDefinitionView, PolicyRuleView
from app.modules.contributions.api.policies import ContributionPolicyVersionListItem
from app.modules.contributions.models import ContributionPolicy, ContributionPolicyVersion


def _rule_views(version: ContributionPolicyVersion) -> tuple[PolicyRuleView, ...]:
    """The version's rules and award definitions in their canonical public order."""
    return tuple(
        PolicyRuleView(
            rule_id=rule.id,
            contribution_type=cast(object, rule.contribution_type),  # type: ignore[arg-type]
            compensation_mode=cast(object, rule.compensation_mode),  # type: ignore[arg-type]
            definitions=tuple(
                PolicyDefinitionView(
                    definition_id=item.id,
                    instrument_type=CompensationInstrumentType(item.instrument_type),
                    unit_code=item.unit_code,
                    quantity=format(item.quantity, "f"),
                    adapter_binding_id=item.adapter_binding_id,
                )
                for item in sorted(rule.award_definitions, key=lambda value: value.instrument_type)
            ),
        )
        for rule in sorted(version.rules, key=lambda value: value.contribution_type)
    )


def _view_fields(policy: ContributionPolicy, version: ContributionPolicyVersion) -> dict:
    """The fields shared by the exact-version view and the version list item."""
    return {
        "project_id": UUID(policy.project_id),
        "contribution_policy_id": policy.id,
        "name": policy.name,
        "policy_status": policy.status,
        "contribution_policy_version_id": version.id,
        "version_number": version.version_number,
        "version_status": version.status,
        "rules": _rule_views(version),
    }


def policy_view(policy: ContributionPolicy, version: ContributionPolicyVersion) -> ContributionPolicyView:
    """The exact-version public policy facts."""
    return ContributionPolicyView(**_view_fields(policy, version))


def policy_version_list_item(
    policy: ContributionPolicy, version: ContributionPolicyVersion,
) -> ContributionPolicyVersionListItem:
    """The exact-version facts plus the version's lifecycle instants."""
    return ContributionPolicyVersionListItem(
        **_view_fields(policy, version), created_at=version.created_at,
        published_at=version.published_at, retired_at=version.retired_at,
    )
