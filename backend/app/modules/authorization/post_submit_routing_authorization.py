"""Fixed router preparation through AUTH/PREP; the action remains unavailable."""

from contextlib import asynccontextmanager

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.acceptance_source_contracts import routing_source_commitment
from app.modules.authorization.api.acceptance_source import (
    AcceptanceSourceReceiptFacts, acceptance_source_commitment_digest,
)
from app.modules.authorization.catalogue import PermissionId
from app.modules.authorization.domain.audit import MatchedAuthorityKind
from app.modules.authorization.domain.post_submit_routing import (
    ROUTE, PostSubmitRoutingResourceContext, post_submit_routing_prepare_values,
    post_submit_routing_resource_digest,
)
from app.modules.authorization.prepared import fixed_service_prepared_authorization
from app.modules.authorization.runtime import (
    PreparedAuthorizationHandleInvalid, PreparedAuthorizationInput,
    PreparedAuthorityScope, PreparedAuthorityScopeKind,
)
from app.modules.tasks.api.post_submit_routing import TaskRoutingRequestFacts


class _PreparedRouting:
    """A private participant; only canonical PREP owns capability lifetime."""

    def __init__(self, authority, handle, caller_input):
        self._authority = authority
        self._handle = handle
        self._input = caller_input

    async def consume(self, resource: PostSubmitRoutingResourceContext) -> AcceptanceSourceReceiptFacts:
        decision = await self._authority.service.consume(self._handle, ROUTE, self._input, resource)
        return self._receipt(decision, resource)

    def _receipt(self, decision, resource):
        """Project only the returned decision; detached values remain untrusted."""
        resource.validate_identity()
        operation_id = resource.request.route_operation_id
        digest = post_submit_routing_resource_digest(resource)
        if not (
            decision.allowed and decision.revalidated
            and decision.denial_code is None
            and decision.matched_authority_kind is MatchedAuthorityKind.FIXED_SERVICE
            and decision.matched_grant_id is None and decision.matched_scope_project_id is None
            and decision.action_id is ROUTE and decision.permission_id is PermissionId.TASK_POST_SUBMIT_ROUTE
            and decision.resource_type == resource.resource_type
            and decision.resource_id == resource.resource_id
            and decision.resource_context_digest == digest
            and decision.request_id == decision.correlation_id == self._input.idempotency_key == operation_id
            and self._input.request_value == post_submit_routing_prepare_values(resource.request)
        ):
            raise PreparedAuthorizationHandleInvalid("invalid routing authorization receipt")
        source = routing_source_commitment(
            resource.source, route_operation_id=operation_id,
            route_request_digest=resource.request.route_request_digest,
        )
        return AcceptanceSourceReceiptFacts(
            authorization_decision_event_id=decision.decision_id,
            action_id=ROUTE.value, permission_id=PermissionId.TASK_POST_SUBMIT_ROUTE.value,
            actor_profile_id=self._authority.actor_profile_id,
            actor_identity_link_id=self._authority.identity_link_id,
            service_identity=ServiceIdentity.TASK_POST_SUBMIT_ROUTER.value,
            matched_grant_id=None, project_id=resource.scope_project_id,
            resource_type=resource.resource_type, resource_id=resource.resource_id,
            request_id=operation_id, correlation_id=operation_id, idempotency_reference=operation_id,
            resource_context_digest=digest, source=source,
            source_commitment_digest=acceptance_source_commitment_digest(source),
        )


class PostSubmitRoutingAuthorization:
    """Prepare only the fixed router; callers cannot choose a service principal."""

    def __init__(self, session):
        self._session = session

    @asynccontextmanager
    async def prepare(self, request: TaskRoutingRequestFacts):
        checked = TaskRoutingRequestFacts.model_validate(request.model_dump())
        async with fixed_service_prepared_authorization(
            self._session, service_identity=ServiceIdentity.TASK_POST_SUBMIT_ROUTER,
            request_id=checked.route_operation_id, correlation_id=checked.route_operation_id,
        ) as authority:
            caller_input = PreparedAuthorizationInput(
                idempotency_key=checked.route_operation_id,
                request_value=post_submit_routing_prepare_values(checked),
            )
            handle = await authority.service.prepare(ROUTE, caller_input, PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT, project_id=checked.project_id,
            ))
            yield _PreparedRouting(authority, handle, caller_input)
