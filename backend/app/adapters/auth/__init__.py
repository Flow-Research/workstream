"""Authorization application adapters and same-owner composition."""

from contextlib import asynccontextmanager
from uuid import uuid5
from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.api import ActorIdentityFacts, ActorKind, AuthorizationDenied
from app.modules.authorization.guide_compilation import ProjectGuideCompilationAuthorizationAdapter
from app.modules.authorization.prepared import fixed_service_prepared_authorization
from app.modules.authorization.runtime import PreparedAuthorizationUnsupported

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth.contribution_policies import ContributionPolicyAuthorization
from app.modules.authorization.contribution_policy_authorization import (
    ContributionPolicyAuthorizationAdapter,
)

from app.adapters.auth.adapter_bindings import CompensationAdapterBindingAuthorization
from app.modules.authorization.adapter_binding_authorization import (
    AdapterBindingAuthorizationAdapter,
)
from app.modules.authorization.project_setup_finalization import SetupFinalizationAuthorization
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import AuthorizationContext
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.authorization.guide_compilation_projections import (
    ArtifactPolicyProjectionAuthorization,
    GuideSufficiencyProjectionAuthorization,
)


def setup_finalization_authorization(session: AsyncSession) -> SetupFinalizationAuthorization:
    """Compose explicit hidden finalization authority in the caller session."""
    return SetupFinalizationAuthorization(session)


def task_authorization(
    session: AsyncSession, context: AuthorizationContext,
) -> PreparedTaskAuthorization:
    """Compose exact task authority in AUTH's registered composition root."""
    return PreparedTaskAuthorization(session, context)


def guide_sufficiency_projection_authorization(
    session: AsyncSession,
) -> GuideSufficiencyProjectionAuthorization:
    """Compose request-local fixed-service sufficiency projection authority."""
    return GuideSufficiencyProjectionAuthorization(session)


def artifact_policy_projection_authorization(
    session: AsyncSession,
) -> ArtifactPolicyProjectionAuthorization:
    """Compose request-local fixed-service artifact-policy projection authority."""
    return ArtifactPolicyProjectionAuthorization(session)


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


def contribution_policy_authorization(
    session: AsyncSession, context: AuthorizationContext
) -> ContributionPolicyAuthorization:
    """Compose exact Finance Authority policy permissions in the caller session."""
    repository = AdminAuthorizationRepository(session)
    kernel = AuthorizationService(session, context, admin_repository=repository)
    prepared = PreparedAuthorizationService(session, context, kernel, repository)
    return ContributionPolicyAuthorization(ContributionPolicyAuthorizationAdapter(kernel, prepared))


__all__ = (
    "task_authorization",
    "guide_compilation_request_authority",
    "guide_compilation_execution_authority",
    "ContributionPolicyAuthorization",
    "contribution_policy_authorization",
    "CompensationAdapterBindingAuthorization",
    "compensation_adapter_binding_authorization",
    "artifact_policy_projection_authorization",
    "guide_sufficiency_projection_authorization",
    "setup_finalization_authorization",
)


@asynccontextmanager
async def guide_compilation_request_authority(session, operation_id):
    """Compose fresh fixed-service AUTH without constructing a human actor."""
    try:
        async with fixed_service_prepared_authorization(
            session,
            service_identity=ServiceIdentity.PROJECT_SETUP,
            request_id=operation_id,
            correlation_id=uuid5(operation_id, "compilation"),
        ) as authority:
            # Identity resolution is read-only. Each command below owns a fresh
            # root transaction and revalidates authority at consumption.
            await session.rollback()
            yield (
                ProjectGuideCompilationAuthorizationAdapter.from_prepared(authority.service),
                ActorIdentityFacts(
                    actor_profile_id=authority.actor_profile_id,
                    identity_link_id=authority.identity_link_id,
                    actor_kind=ActorKind.SERVICE,
                    service_identity=ServiceIdentity.PROJECT_SETUP.value,
                ),
            )
    except PreparedAuthorizationUnsupported:
        raise AuthorizationDenied("compilation service authority denied") from None


@asynccontextmanager
async def guide_compilation_execution_authority(session, state):
    """Reuse the same explicit service composition for an exact execution operation."""
    async with guide_compilation_request_authority(
        session, state.preflight_facts.operation_id
    ) as composed:
        yield composed
