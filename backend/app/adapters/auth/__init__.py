"""Authorization application adapters and same-owner composition."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth.adapter_bindings import CompensationAdapterBindingAuthorization
from app.modules.authorization.adapter_binding_authorization import (
    AdapterBindingAuthorizationAdapter,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import AuthorizationContext


def compensation_adapter_binding_authorization(
    session: AsyncSession,
    context: AuthorizationContext,
) -> CompensationAdapterBindingAuthorization:
    """Compose one request-local AUTH adapter through the public CON port."""
    repository = AdminAuthorizationRepository(session)
    kernel = AuthorizationService(session, context, admin_repository=repository)
    prepared = PreparedAuthorizationService(session, context, kernel, repository)
    return CompensationAdapterBindingAuthorization(
        AdapterBindingAuthorizationAdapter(kernel, prepared)
    )


__all__ = (
    "CompensationAdapterBindingAuthorization",
    "compensation_adapter_binding_authorization",
)
