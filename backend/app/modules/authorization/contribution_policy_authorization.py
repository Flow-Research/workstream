"""AUTH-owned contribution-policy authorization implementation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.modules.authorization.api import (
    ContributionPolicyMutationAuthorityFacts,
    ContributionPolicyReadFacts,
    AuthorizationDenied as BoundaryAuthorizationDenied,
    AuthorizationUnavailable,
    PreparedAuthorizationInvalid,
    action_id as public_action_id,
    contribution_policy_resource_digest,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.contribution_policies import (
    CONTRIBUTION_POLICY_MUTATION_ACTIONS,
    CONTRIBUTION_POLICY_RESOURCE_BY_ACTION,
    ContributionPolicyReadResourceContext,
    ContributionPolicyMutationScopeDenialResourceContext,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import (
    PreparedAuthorizationHandle,
    PreparedAuthorizationService,
)
from app.modules.authorization.runtime import (
    AuthorizationDenied,
    AuthorizationEvidenceUnavailable,
    HumanAuthorizationContext,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)


class ContributionPolicyAuthorizationAdapter:
    """Bind public contribution-policy facts to the kernel and existing PREP service."""

    def __init__(
        self,
        authorization: AuthorizationService,
        prepared: PreparedAuthorizationService,
    ) -> None:
        """Require the query kernel and PREP service to share one composition."""
        if (
            prepared._authorization is not authorization
            or prepared._context != authorization._context
        ):
            raise TypeError("contribution-policy authorization requires one composition")
        self._authorization = authorization
        self._prepared = prepared

    def _assert_human_actor(self, actor_profile_id: UUID) -> None:
        """Reject non-human or mismatched authenticated actor contexts."""
        context = self._authorization._context
        if (
            not isinstance(context, HumanAuthorizationContext)
            or context.actor_profile_id != actor_profile_id
            or context != self._prepared._context
        ):
            raise BoundaryAuthorizationDenied("contribution-policy authority denied")

    @staticmethod
    def _action(raw: str) -> ActionId:
        """Resolve a public action value within the closed mutation action set."""
        try:
            action = ActionId(raw)
        except ValueError as exc:
            raise BoundaryAuthorizationDenied("contribution-policy authority denied") from exc
        if action not in CONTRIBUTION_POLICY_MUTATION_ACTIONS:
            raise BoundaryAuthorizationDenied("contribution-policy authority denied")
        return action

    def _mutation_context(self, facts: ContributionPolicyMutationAuthorityFacts):
        """Resolve only the exact action resource from validated public authority facts."""
        if type(facts) is not ContributionPolicyMutationAuthorityFacts:
            raise BoundaryAuthorizationDenied("contribution-policy authority denied")
        self._assert_human_actor(facts.actor_profile_id)
        action = self._action(str(facts.action_id))
        values = dict(
            resource_type="contribution_policy",
            resource_id=facts.contribution_policy_id,
            scope_project_id=facts.project_id,
            contribution_policy_version_id=facts.contribution_policy_version_id,
            operation_id=facts.operation_id,
            request_digest=facts.request_digest,
            expected_policy_status=facts.expected_policy_status,
            expected_version_status=facts.expected_version_status,
            resource_facts_digest=contribution_policy_resource_digest(
                facts.action_id, facts.resource_facts
            ),
        )
        if action is ActionId.CONTRIBUTION_POLICY_PUBLISH:
            values.update(
                rules_and_definitions_digest=facts.resource_facts.rules_and_definitions_digest,
                adapter_binding_ids=facts.resource_facts.adapter_binding_ids,
            )
        return action, CONTRIBUTION_POLICY_RESOURCE_BY_ACTION[action].model_validate(values)

    @staticmethod
    async def _invoke(operation):
        """Translate private PREP failures into the stable public AUTH boundary."""
        try:
            return await operation
        except PreparedAuthorizationHandleInvalid as exc:
            raise PreparedAuthorizationInvalid(
                "prepared contribution-policy authority is invalid"
            ) from exc
        except (PreparedAuthorizationUnsupported, AuthorizationDenied) as exc:
            raise BoundaryAuthorizationDenied("contribution-policy authority denied") from exc
        except AuthorizationEvidenceUnavailable as exc:
            raise AuthorizationUnavailable("contribution-policy authority unavailable") from exc

    async def authorize_read(
        self, *, actor_profile_id: UUID, facts: ContributionPolicyReadFacts
    ) -> None:
        """Authorize a fresh read of one exact project-owned policy."""
        self._assert_human_actor(actor_profile_id)
        resource = ContributionPolicyReadResourceContext(
            resource_type="contribution_policy",
            resource_id=facts.contribution_policy_id,
            scope_project_id=facts.project_id,
            contribution_policy_version_id=facts.contribution_policy_version_id,
            resource_facts_digest=contribution_policy_resource_digest(
                public_action_id("contribution.policy.read"),
                facts,
            ),
        )
        try:
            await self._authorization.require(ActionId.CONTRIBUTION_POLICY_READ, resource)
        except AuthorizationDenied as exc:
            raise BoundaryAuthorizationDenied("contribution-policy authority denied") from exc
        except AuthorizationEvidenceUnavailable as exc:
            raise AuthorizationUnavailable("contribution-policy authority unavailable") from exc

    async def lock_mutation_scope(
        self, *, action_id, actor_profile_id: UUID, project_id: UUID,
    ) -> None:
        """Fence current scoped authority before product locks without authorizing effects."""
        if not isinstance(actor_profile_id, UUID) or not isinstance(project_id, UUID):
            raise BoundaryAuthorizationDenied("invalid mutation scope")
        self._assert_human_actor(actor_profile_id)
        action = self._action(str(action_id))
        async def lock_scope():
            try:
                await self._prepared.lock_mutation_scope(
                    action,
                    PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.PROJECT, project_id=project_id),
                )
            except PreparedAuthorizationUnsupported as denial:
                try:
                    exists = await self._authorization._admin.project_exists(project_id)
                except SQLAlchemyError as exc:
                    raise AuthorizationUnavailable("contribution-policy authority unavailable") from exc
                resource = ContributionPolicyMutationScopeDenialResourceContext(
                    resource_type="project", resource_id=project_id,
                    scope_project_id=project_id, project_exists=exists,
                    requested_action=action,
                )
                await self._prepared.deny_unsupported(action, None, resource, denial)
        await self._invoke(lock_scope())

    async def prepare_mutation(
        self, facts: ContributionPolicyMutationAuthorityFacts
    ) -> PreparedAuthorizationHandle:
        """Prepare transaction-bound authority for one canonical mutation request."""
        action, resource = self._mutation_context(facts)
        return await self._invoke(
            self._prepared.prepare(
                action,
                PreparedAuthorizationInput(
                    idempotency_key=facts.operation_id,
                    request_value=resource.model_dump(mode="json"),
                ),
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT,
                    project_id=facts.project_id,
                ),
            )
        )

    async def consume_mutation(
        self, prepared: object, facts: ContributionPolicyMutationAuthorityFacts
    ) -> UUID:
        """Consume exact prepared authority and return the authenticated actor."""
        if type(prepared) is not PreparedAuthorizationHandle:
            raise PreparedAuthorizationInvalid("prepared contribution-policy authority is invalid")
        action, resource = self._mutation_context(facts)
        await self._invoke(
            self._prepared.consume(
                prepared,
                action,
                PreparedAuthorizationInput(
                    idempotency_key=facts.operation_id,
                    request_value=resource.model_dump(mode="json"),
                ),
                resource,
            )
        )
        return self._authorization._context.actor_profile_id

    def close_mutation(self, prepared: object) -> None:
        """Invalidate an exact prepared handle without exposing its internals."""
        if type(prepared) is not PreparedAuthorizationHandle:
            raise PreparedAuthorizationInvalid("prepared contribution-policy authority is invalid")
        try:
            self._prepared.close_handle(prepared)
        except PreparedAuthorizationHandleInvalid as exc:
            raise PreparedAuthorizationInvalid(
                "prepared contribution-policy authority is invalid"
            ) from exc
