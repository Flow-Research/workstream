"""AUTH-owned adapter for exact prepared task operations."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.api import TaskAuthorityDenied, TaskAuthorityFacts
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.task_authority import TaskAuthorityResourceContext
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationHandle, PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    AuthorizationContext,
    AuthorizationDenied,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)


class PreparedTaskAuthorization:
    """Reuse the kernel's locks, single-use handles and exact decision audit."""

    def __init__(self, session: AsyncSession, context: AuthorizationContext) -> None:
        self._context = context
        self._session = session
        self._repository = AdminAuthorizationRepository(session)
        self._kernel = AuthorizationService(session, context, admin_repository=self._repository)

    def _resource(self, facts: TaskAuthorityFacts) -> TaskAuthorityResourceContext:
        if facts.actor_profile_id != self._context.actor_profile_id:
            raise TaskAuthorityDenied("task authority denied")
        # Service actors reach the canonical fixed-service matrix denial so
        # their rejected request retains the same AUTH audit custody as humans.
        return TaskAuthorityResourceContext(
            resource_id=facts.task_id,
            scope_project_id=facts.project_id,
            actor_profile_id=facts.actor_profile_id,
            identity_link_id=self._context.identity_link_id,
            task_status=facts.task_status,
            assigned_to=facts.assigned_to,
            assignment_id=facts.assignment_id,
            assignment_contributor_id=facts.assignment_contributor_id,
            locked_context_hash=facts.locked_context_hash,
            reason=facts.reason,
        )

    async def prepare(self, facts: TaskAuthorityFacts) -> object:
        resource = self._resource(facts)
        service = PreparedAuthorizationService(
            self._session,
            self._context,
            self._kernel,
            self._repository,
        )
        caller_input = PreparedAuthorizationInput(
            idempotency_key=self._context.request_id,
            request_value=resource.model_dump(mode="json"),
        )
        try:
            handle = await service.prepare(
                ActionId(facts.operation.value),
                caller_input,
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT,
                    project_id=facts.project_id,
                ),
            )
            return _TaskPrepared(service, handle, caller_input)
        except PreparedAuthorizationUnsupported as exc:
            try:
                await service.deny_unsupported(
                    ActionId(facts.operation.value), caller_input, resource, exc
                )
            except AuthorizationDenied as denial:
                raise TaskAuthorityDenied("task authority denied") from denial
            finally:
                service.close()
        except (AuthorizationDenied, PreparedAuthorizationHandleInvalid) as exc:
            service.close()
            raise TaskAuthorityDenied("task authority denied") from exc
        except BaseException:
            service.close()
            raise

    async def consume(self, handle: object, facts: TaskAuthorityFacts) -> UUID:
        if not isinstance(handle, _TaskPrepared):
            raise TaskAuthorityDenied("task authority denied")
        try:
            decision = await handle.service.consume(
                handle.handle,
                ActionId(facts.operation.value),
                handle.caller_input,
                self._resource(facts),
            )
            return decision.decision_id
        except (
            AuthorizationDenied,
            PreparedAuthorizationHandleInvalid,
            PreparedAuthorizationUnsupported,
        ) as exc:
            raise TaskAuthorityDenied("task authority denied") from exc
        finally:
            handle.service.close()

    def close(self, handle: object) -> None:
        if isinstance(handle, _TaskPrepared):
            handle.service.close()

    async def restage_denial(self, error: TaskAuthorityDenied) -> bool:
        """Reuse the issuing kernel's exact pending evidence after rollback."""
        if isinstance(error.__cause__, AuthorizationDenied):
            await self._kernel.restage_denial(error.__cause__.decision)
            return True
        return False


class _TaskPrepared:
    __slots__ = ("service", "handle", "caller_input")

    def __init__(
        self, service: PreparedAuthorizationService, handle: PreparedAuthorizationHandle,
        caller_input: PreparedAuthorizationInput,
    ) -> None:
        self.service = service
        self.handle = handle
        self.caller_input = caller_input
