"""Application adapter from CON's public policy port to AUTH's public port."""

from __future__ import annotations

from uuid import UUID

from app.modules.authorization.api import (
    ContributionPolicyAuthorizationPort,
    ContributionPolicyMutationAuthorityFacts,
    ContributionPolicyReadFacts,
    ContributionPolicyCreateDraftFacts,
    ContributionPolicyUpdateDraftFacts,
    ContributionPolicyPublishFacts,
    ContributionPolicyRetireFacts,
    AuthorizationBoundaryError, AuthorizationDenied,
    action_id,
)
from app.modules.contributions.api import (
    ContributionPolicyAuthorizationFacts,
    ContributionPolicyPublishAuthorizationFacts,
    ContributionPolicyRetireAuthorizationFacts,
    ContributionPolicyMutationAuthorizationFacts,
    ContributionPolicyReadRequest,
    ContributionPolicyUnavailable,
    ContributionPolicyAuthorizationDenied, ContributionPolicyAuthorizationUnavailable,
)


def _policy_authority_error(error: Exception) -> ContributionPolicyUnavailable:
    """Preserve denial versus unavailable without exposing AUTH diagnostics."""
    error_type = (ContributionPolicyAuthorizationDenied if isinstance(error, AuthorizationDenied)
                  else ContributionPolicyAuthorizationUnavailable)
    return error_type("contribution_policy_unavailable")


class ContributionPolicyAuthorization:
    """Translate immutable CON facts without importing either private domain."""

    def __init__(self, authorization: ContributionPolicyAuthorizationPort) -> None:
        """Bind the CON-facing adapter to AUTH's public authorization port."""
        self._authorization = authorization

    async def authorize_contribution_policy_read(
        self, request: ContributionPolicyReadRequest
    ) -> None:
        """Authorize one exact contribution-policy read or return a concealed denial."""
        try:
            await self._authorization.authorize_read(
                actor_profile_id=request.actor_profile_id,
                facts=ContributionPolicyReadFacts(
                    project_id=request.project_id,
                    contribution_policy_id=request.contribution_policy_id,
                    contribution_policy_version_id=request.contribution_policy_version_id,
                ),
            )
        except (AuthorizationBoundaryError, ValueError) as exc:
            raise _policy_authority_error(exc) from exc

    @staticmethod
    def _facts(
        facts: ContributionPolicyAuthorizationFacts,
    ) -> ContributionPolicyMutationAuthorityFacts:
        """Translate exact public CON facts without consulting private product owners."""
        if type(facts) not in {
            ContributionPolicyMutationAuthorizationFacts,
            ContributionPolicyPublishAuthorizationFacts,
            ContributionPolicyRetireAuthorizationFacts,
        }:
            raise ValueError("invalid policy authority facts")
        identity = dict(
            project_id=facts.project_id,
            contribution_policy_id=facts.contribution_policy_id,
            contribution_policy_version_id=facts.contribution_policy_version_id,
        )
        if type(facts) is ContributionPolicyPublishAuthorizationFacts:
            resource = ContributionPolicyPublishFacts(
                **identity,
                rules_and_definitions_digest=facts.rules_and_definitions_digest,
                adapter_binding_ids=facts.adapter_binding_ids,
                expected_status=facts.expected_version_status,
            )
        elif type(facts) is ContributionPolicyRetireAuthorizationFacts:
            resource = ContributionPolicyRetireFacts(
                **identity, expected_status=facts.expected_version_status
            )
        elif facts.action == "contribution.policy.create_draft":
            resource = ContributionPolicyCreateDraftFacts(project_id=facts.project_id)
        elif facts.action == "contribution.policy.update_draft":
            resource = ContributionPolicyUpdateDraftFacts(
                **identity, expected_status=facts.expected_version_status
            )
        else:
            raise ValueError("invalid policy authority action")
        return ContributionPolicyMutationAuthorityFacts(
            action_id=action_id(facts.action),
            actor_profile_id=facts.actor_profile_id,
            operation_id=facts.operation_id,
            request_digest=facts.request_digest,
            contribution_policy_id=facts.contribution_policy_id,
            contribution_policy_version_id=facts.contribution_policy_version_id,
            expected_policy_status=facts.expected_policy_status,
            expected_version_status=facts.expected_version_status,
            resource_facts=resource,
        )

    async def lock_contribution_policy_mutation_scope(
        self, *, action: str, actor_profile_id: UUID, project_id: UUID,
    ) -> None:
        """Acquire AUTH-owned scope locks before any product owner lock."""
        try:
            await self._authorization.lock_mutation_scope(
                action_id=action_id(action), actor_profile_id=actor_profile_id, project_id=project_id,
            )
        except (AuthorizationBoundaryError, ValueError) as exc:
            raise _policy_authority_error(exc) from exc

    async def prepare_contribution_policy_mutation(
        self, facts: ContributionPolicyAuthorizationFacts
    ) -> object:
        """Prepare opaque authority for one exact contribution-policy mutation."""
        try:
            return await self._authorization.prepare_mutation(self._facts(facts))
        except (AuthorizationBoundaryError, ValueError) as exc:
            raise _policy_authority_error(exc) from exc

    async def consume_contribution_policy_mutation(
        self, prepared: object, facts: ContributionPolicyAuthorizationFacts
    ) -> UUID:
        """Consume prepared mutation authority and return its authorized actor."""
        try:
            return await self._authorization.consume_mutation(prepared, self._facts(facts))
        except (AuthorizationBoundaryError, ValueError) as exc:
            raise _policy_authority_error(exc) from exc

    def close_contribution_policy_mutation(self, prepared: object) -> None:
        """Invalidate prepared mutation authority through AUTH's public port."""
        try:
            self._authorization.close_mutation(prepared)
        except (AuthorizationBoundaryError, ValueError) as exc:
            raise _policy_authority_error(exc) from exc
