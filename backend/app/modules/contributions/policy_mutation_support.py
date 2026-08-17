"""Shared fail-closed helpers for ContributionPolicy mutations."""

from uuid import UUID

from app.modules.contributions.api import (
    ContributionPolicyAuthorizationFacts,
    ContributionPolicyMutationAuthorizationPort,
    ContributionPolicyUnavailable,
)


async def consume_and_close_policy_authority(
    authorization: ContributionPolicyMutationAuthorizationPort,
    facts: ContributionPolicyAuthorizationFacts,
) -> UUID:
    """Consume exact opaque authority and invalidate it before product effects."""
    prepared = await authorization.prepare_contribution_policy_mutation(facts)
    try:
        actor = await authorization.consume_contribution_policy_mutation(prepared, facts)
    finally:
        authorization.close_contribution_policy_mutation(prepared)
    if type(actor) is not UUID or actor != facts.actor_profile_id:
        raise ContributionPolicyUnavailable("contribution_policy_unavailable")
    return actor
