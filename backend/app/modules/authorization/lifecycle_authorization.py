"""Live system Operator preparation for the sole REV lifecycle controller."""

from contextlib import asynccontextmanager

from app.modules.authorization.api import AuthorizationDenied as BoundaryDenied
from app.modules.authorization.domain.lifecycle import ACTION, ReviewLifecycleActivationContract
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    HumanAuthorizationContext, PreparedAuthorizationInput,
    PreparedAuthorityScope, PreparedAuthorityScopeKind,
)
from app.modules.reviews.api.lifecycle import LifecycleAuthorityReceipt


class _PreparedLifecycle:
    def __init__(self, service, handle, caller_input):
        self._service, self._handle, self._input = service, handle, caller_input

    async def consume_new(self, facts):
        resource = ReviewLifecycleActivationContract(resource_id=facts.command.singleton_id, facts=facts)
        decision = await self._service.consume(self._handle, ACTION, self._input, resource)
        return LifecycleAuthorityReceipt(
            decision_event_id=decision.decision_id,
            resource_context_digest=decision.resource_context_digest,
        )

    async def validate_replay(self, facts, decision_id):
        resource = ReviewLifecycleActivationContract(resource_id=facts.command.singleton_id, facts=facts)
        await self._service.validate_replay(self._handle, ACTION, self._input, resource, decision_id)


class LifecycleAuthorizationAdapter:
    """Explicit request-local AUTH composition; command actor selectors are untrusted."""

    def __init__(self, session, context):
        self._session, self._context = session, context

    @asynccontextmanager
    async def lock_scope(self, command):
        context = self._context
        if (
            type(context) is not HumanAuthorizationContext
            or context.actor_profile_id != command.actor_profile_id
            or context.identity_link_id != command.identity_link_id
        ):
            raise BoundaryDenied("lifecycle authority denied")
        context = context.model_copy(update={"correlation_id": command.operation_id})
        repository = AdminAuthorizationRepository(self._session)
        kernel = AuthorizationService(self._session, context, admin_repository=repository)
        service = PreparedAuthorizationService(self._session, context, kernel, repository)
        caller_input = PreparedAuthorizationInput(
            idempotency_key=command.operation_id, request_value=command.model_dump(mode="json"),
        )
        try:
            handle = await service.prepare(
                ACTION, caller_input, PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM),
            )
            yield _PreparedLifecycle(service, handle, caller_input)
        finally:
            service.close()
