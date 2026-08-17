"""Shared fail-closed authorization and recovery for policy mutations."""

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from app.modules.contributions.api import (
    ContributionPolicyAuthorizationFacts,
    ContributionPolicyConflict,
    ContributionPolicyMutationResult,
    ContributionPolicyMutationAuthorizationPort,
    ContributionPolicyReadAuthorizationPort,
    ContributionPolicyReadRequest,
    ContributionPolicyUnavailable,
)
from app.modules.contributions.models import ContributionPolicyLifecycleEvent


class PolicyRecoveryRepository(Protocol):
    """Minimal persistence surface required by shared operation recovery."""

    async def lock_operation(self, operation_id: UUID) -> None: ...

    async def get_event_by_operation(
        self, operation_id: UUID
    ) -> ContributionPolicyLifecycleEvent | None: ...


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


async def begin_and_recover_policy_mutation(
    *,
    repository: PolicyRecoveryRepository,
    read_authorization: ContributionPolicyReadAuthorizationPort,
    request: object,
    request_digest: str,
    expected_event_type: str,
    result_factory: Callable[[ContributionPolicyLifecycleEvent], ContributionPolicyMutationResult],
) -> ContributionPolicyMutationResult | None:
    """Fence an operation and recover only immutable currently-readable truth."""
    operation_id = getattr(request, "operation_id")
    await repository.lock_operation(operation_id)
    event = await repository.get_event_by_operation(operation_id)
    if event is None:
        return None
    if (
        event.event_type != expected_event_type
        or event.request_digest != request_digest
        or event.actor_profile_id != str(getattr(request, "actor_profile_id"))
        or event.project_id != str(getattr(request, "project_id"))
    ):
        raise ContributionPolicyConflict("contribution_policy_conflict")
    try:
        await read_authorization.authorize_contribution_policy_read(
            ContributionPolicyReadRequest(
                actor_profile_id=UUID(event.actor_profile_id),
                project_id=UUID(event.project_id),
                contribution_policy_id=event.contribution_policy_id,
                contribution_policy_version_id=event.contribution_policy_version_id,
            )
        )
    except (ContributionPolicyUnavailable, ContributionPolicyConflict) as exc:
        raise ContributionPolicyConflict("contribution_policy_conflict") from exc
    return result_factory(event)
