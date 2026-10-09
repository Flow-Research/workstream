"""AUTH-owned exact preparation for ART's declared task-import source role."""

from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.modules.artifacts.api.task_import_source import (
    TaskImportSourceAction, TaskImportSourceAuthorityFacts, TaskImportSourceAuthorityDenied,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    AuthorizationContext, AuthorizationDenied, PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported, PreparedAuthorityScope, PreparedAuthorityScopeKind,
    TaskImportSourceResourceContext,
)


class PreparedTaskImportSourceAuthorization:
    """Reuse live actor/grant locks, exact handles and canonical decision custody."""

    def __init__(self, session: AsyncSession, context: AuthorizationContext):
        self._session, self._context = session, context
        self._repository = AdminAuthorizationRepository(session)
        self._kernel = AuthorizationService(session, context, admin_repository=self._repository)

    async def authorize(self, action: TaskImportSourceAction, facts: TaskImportSourceAuthorityFacts) -> UUID:
        if type(facts) is not TaskImportSourceAuthorityFacts or facts.actor_profile_id != self._context.actor_profile_id:
            raise TaskImportSourceAuthorityDenied("task-import source authority denied")
        resource = TaskImportSourceResourceContext(
            resource_id=facts.source_id, scope_project_id=facts.project_id,
            actor_profile_id=facts.actor_profile_id, identity_link_id=self._context.identity_link_id,
            sha256=facts.sha256, byte_count=facts.byte_count,
            operation_identity=facts.operation_identity, idempotency_key=facts.idempotency_key,
        )
        prepared = PreparedAuthorizationService(self._session, self._context, self._kernel, self._repository)
        caller_input = PreparedAuthorizationInput(idempotency_key=facts.idempotency_key,
                                                  request_value=resource.model_dump(mode="json"))
        try:
            try:
                handle = await prepared.prepare(ActionId(action.value), caller_input, PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT, project_id=facts.project_id,
                ))
            except PreparedAuthorizationUnsupported as exc:
                await prepared.deny_unsupported(ActionId(action.value), caller_input, resource, exc)
                raise
            decision = await prepared.consume(handle, ActionId(action.value), caller_input, resource)
            return decision.decision_id
        except AuthorizationDenied as exc:
            raise TaskImportSourceAuthorityDenied("task-import source authority denied") from exc
        finally:
            prepared.close()

    async def restage_denial(self, error: TaskImportSourceAuthorityDenied) -> None:
        if isinstance(error.__cause__, AuthorizationDenied):
            await self._kernel.restage_denial(error.__cause__.decision)
