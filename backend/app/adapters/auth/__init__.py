"""Authorization application adapters and same-owner composition."""

from app.adapters.auth.assignment_invalidation_publication import assignment_invalidation_publication
from app.modules.projects.api.guide_activation import GuideActivationAuthorizationPort
from contextlib import asynccontextmanager
from uuid import UUID, uuid5
from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.api import (
    ActorIdentityFacts, ActorKind, AuthorizationDenied, ProjectGuideCompilationAuthorizationPort,
)
from app.modules.authorization.api.guide_proposal_review import GuideProposalAuthorizationPort
from app.modules.authorization.api.post_policy import PostPolicyAuthorizationPort
from app.modules.authorization.api.outbox_dispatch import OutboxDispatchAuthorizationPort
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
    "assignment_invalidation_publication",
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


def guide_proposal_authorization(
    session: AsyncSession, context: AuthorizationContext,
) -> GuideProposalAuthorizationPort:
    """Bind the public proposal authority port to the canonical request adapter."""
    from app.modules.authorization.guide_proposal_authorization import GuideProposalAuthorizationAdapter

    return GuideProposalAuthorizationAdapter(session, context)


def human_guide_compilation_authorization(
    prepared: PreparedAuthorizationService,
) -> ProjectGuideCompilationAuthorizationPort:
    """Bind the existing human request port to one shared PREP composition."""
    return ProjectGuideCompilationAuthorizationAdapter.from_prepared(prepared)


def post_policy_authorization(
    session: AsyncSession, context: AuthorizationContext,
) -> "PostPolicyAuthorizationPort":
    """Bind the post-policy port to shared request-local AUTH in the same session."""
    from app.modules.authorization.post_policy_authorization import PostPolicyAuthorizationAdapter

    return PostPolicyAuthorizationAdapter(session, context)


@asynccontextmanager
async def post_policy_service_authority(session: AsyncSession, request_id: UUID):
    """Resolve the provisioned setup principal for the existing post-policy port."""
    from app.modules.authorization.prepared import fixed_service_authorization_context

    try:
        context = await fixed_service_authorization_context(
            session, ServiceIdentity.PROJECT_SETUP, request_id,
            uuid5(request_id, "post-policy-authority"),
        )
        await session.rollback()
        yield post_policy_authorization(session, context), ActorIdentityFacts(
            actor_profile_id=context.actor_profile_id,
            identity_link_id=context.identity_link_id,
            actor_kind=ActorKind.SERVICE,
            service_identity=ServiceIdentity.PROJECT_SETUP.value,
        )
    except PreparedAuthorizationUnsupported:
        raise AuthorizationDenied("post-policy service authority denied") from None


def guide_activation_authorization(
    session: AsyncSession, context: AuthorizationContext,
) -> GuideActivationAuthorizationPort:
    """Compose live manager authority for the sole complete-guide operation."""
    from app.modules.authorization.guide_activation_authorization import GuideActivationAuthorizationAdapter

    return GuideActivationAuthorizationAdapter(session, context)


def outbox_dispatch_authorization(session: AsyncSession) -> "OutboxDispatchAuthorizationPort":
    """Compose the one fixed dispatcher through canonical AUTH/PREP."""
    from app.modules.authorization.outbox_dispatch_authorization import OutboxDispatchAuthorizationAdapter

    return OutboxDispatchAuthorizationAdapter(session)


def assignment_invalidation_authorization(session: AsyncSession):
    """Compose the exact reconciler through canonical fixed-service PREP."""
    from app.modules.authorization.assignment_invalidation_authorization import AssignmentInvalidationAuthorizationAdapter

    return AssignmentInvalidationAuthorizationAdapter(session)


def actor_lifecycle_service(session: AsyncSession):
    """Compose lifecycle evidence and exact assignment publication together."""
    from app.modules.authorization.lifecycle_service import ActorLifecycleService
    return ActorLifecycleService(session, publication=assignment_invalidation_publication(session))


def identity_link_lifecycle_service(session: AsyncSession):
    """Compose link loss with the same required transaction participant."""
    from app.modules.authorization.lifecycle_service import IdentityLinkLifecycleService
    return IdentityLinkLifecycleService(session, publication=assignment_invalidation_publication(session))


def project_role_mutation_service(session: AsyncSession):
    """Compose grant mutations; only Submitter loss publishes assignment targets."""
    from app.modules.authorization.project_role_service import ProjectRoleGrantMutationService
    return ProjectRoleGrantMutationService(session, publication=assignment_invalidation_publication(session))


def task_queue_authorization(kernel, secret):
    """Compose the canonical queue AUTH adapter without exporting private owners."""
    from app.modules.authorization.task_queue_read import TaskQueueReadAuthorization
    return TaskQueueReadAuthorization(kernel, secret)


def history_read_authorization(kernel):
    """Compose current AUTH decisions for owner-selected immutable history."""
    from app.modules.authorization.history_authorization import HistoryReadAuthorization
    return HistoryReadAuthorization(kernel)
