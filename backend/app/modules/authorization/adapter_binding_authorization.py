"""AUTH-owned adapter-binding authorization implementation."""

from __future__ import annotations

from uuid import UUID

from app.modules.authorization.api import (
    AdapterBindingCreateFacts,
    AdapterBindingMutationAuthorityFacts,
    AdapterBindingReadFacts,
    AdapterBindingResumeFacts,
    AdapterBindingSuspendFacts,
    AuthorizationDenied as BoundaryAuthorizationDenied,
    PreparedAuthorizationInvalid,
    action_id as public_action_id,
    adapter_binding_resource_digest,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.adapter_bindings import (
    ADAPTER_BINDING_MUTATION_ACTIONS,
    AdapterBindingMutationResourceContext,
    AdapterBindingReadResourceContext,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import (
    PreparedAuthorizationHandle,
    PreparedAuthorizationService,
)
from app.modules.authorization.runtime import (
    AuthorizationDenied,
    HumanAuthorizationContext,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)

class AdapterBindingAuthorizationAdapter:
    """Bind public adapter-binding facts to the kernel and existing PREP service."""

    def __init__(
        self,
        authorization: AuthorizationService,
        prepared: PreparedAuthorizationService,
    ) -> None:
        """Require the query kernel and PREP service to share one composition."""
        if prepared._authorization is not authorization:
            raise TypeError("adapter-binding authorization requires one composition")
        self._authorization = authorization
        self._prepared = prepared

    def _assert_human_actor(self, actor_profile_id: UUID) -> None:
        """Reject non-human or mismatched authenticated actor contexts."""
        context = self._authorization._context
        if (
            not isinstance(context, HumanAuthorizationContext)
            or context.actor_profile_id != actor_profile_id
        ):
            raise BoundaryAuthorizationDenied("adapter-binding authority denied")

    @staticmethod
    def _action(raw: str) -> ActionId:
        """Resolve a public action value within the closed mutation action set."""
        try:
            action = ActionId(raw)
        except ValueError as exc:
            raise BoundaryAuthorizationDenied("adapter-binding authority denied") from exc
        if action not in ADAPTER_BINDING_MUTATION_ACTIONS:
            raise BoundaryAuthorizationDenied("adapter-binding authority denied")
        return action

    @staticmethod
    def _resource_facts(facts: AdapterBindingMutationAuthorityFacts):
        """Build the action-specific immutable facts used by the resource digest."""
        action = str(facts.action_id)
        if action == ActionId.COMPENSATION_ADAPTER_BINDING_CREATE.value:
            return AdapterBindingCreateFacts(
                project_id=facts.project_id,
                adapter_binding_id=facts.adapter_binding_id,
                instrument_type=facts.instrument_type,
                adapter_actor_id=facts.adapter_actor_id,
                route_key=facts.route_key,
            )
        if action == ActionId.COMPENSATION_ADAPTER_BINDING_SUSPEND.value:
            return AdapterBindingSuspendFacts(
                project_id=facts.project_id,
                adapter_binding_id=facts.adapter_binding_id,
                expected_lifecycle_version=facts.expected_lifecycle_version,
                expected_status=facts.expected_status,
            )
        return AdapterBindingResumeFacts(
            project_id=facts.project_id,
            adapter_binding_id=facts.adapter_binding_id,
            expected_lifecycle_version=facts.expected_lifecycle_version,
            expected_status=facts.expected_status,
        )

    def _mutation_context(
        self, facts: AdapterBindingMutationAuthorityFacts
    ) -> tuple[ActionId, AdapterBindingMutationResourceContext]:
        """Bind mutation facts to the authenticated actor and canonical resource."""
        self._assert_human_actor(facts.actor_profile_id)
        action = self._action(str(facts.action_id))
        resource_facts = self._resource_facts(facts)
        return action, AdapterBindingMutationResourceContext(
            resource_type="compensation_adapter_binding",
            resource_id=facts.adapter_binding_id,
            scope_project_id=facts.project_id,
            operation_id=facts.operation_id,
            request_digest=facts.request_digest,
            instrument_type=facts.instrument_type,
            adapter_actor_id=facts.adapter_actor_id,
            route_key=facts.route_key,
            expected_status=facts.expected_status,
            expected_lifecycle_version=facts.expected_lifecycle_version,
            resource_facts_digest=adapter_binding_resource_digest(facts.action_id, resource_facts),
        )

    @staticmethod
    async def _invoke(operation):
        """Translate private PREP failures into the stable public AUTH boundary."""
        try:
            return await operation
        except PreparedAuthorizationHandleInvalid as exc:
            raise PreparedAuthorizationInvalid(
                "prepared adapter-binding authority is invalid"
            ) from exc
        except (PreparedAuthorizationUnsupported, AuthorizationDenied) as exc:
            raise BoundaryAuthorizationDenied("adapter-binding authority denied") from exc

    async def authorize_read(
        self, *, actor_profile_id: UUID, facts: AdapterBindingReadFacts
    ) -> None:
        """Authorize a fresh read of one exact project-owned adapter binding."""
        self._assert_human_actor(actor_profile_id)
        resource = AdapterBindingReadResourceContext(
            resource_type="compensation_adapter_binding",
            resource_id=facts.adapter_binding_id,
            scope_project_id=facts.project_id,
            resource_facts_digest=adapter_binding_resource_digest(
                public_action_id("compensation.adapter_binding.read"),
                facts,
            ),
        )
        try:
            await self._authorization.require(ActionId.COMPENSATION_ADAPTER_BINDING_READ, resource)
        except AuthorizationDenied as exc:
            raise BoundaryAuthorizationDenied("adapter-binding authority denied") from exc

    async def prepare_mutation(
        self, facts: AdapterBindingMutationAuthorityFacts
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
        self, prepared: object, facts: AdapterBindingMutationAuthorityFacts
    ) -> UUID:
        """Consume exact prepared authority and return the authenticated actor."""
        if type(prepared) is not PreparedAuthorizationHandle:
            raise PreparedAuthorizationInvalid("prepared adapter-binding authority is invalid")
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
            raise PreparedAuthorizationInvalid("prepared adapter-binding authority is invalid")
        try:
            self._prepared.close_handle(prepared)
        except PreparedAuthorizationHandleInvalid as exc:
            raise PreparedAuthorizationInvalid(
                "prepared adapter-binding authority is invalid"
            ) from exc
