"""PROJECT-owned composition adapters."""

from collections.abc import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.interfaces.external_services import ExternalServiceAdapterFactory
from app.interfaces.project_agents import ProjectGuideAgentRuntime
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.modules.authorization.api import (
    ActorIdentityFacts,
    ArtifactPolicyProjectionAuthorizationPort,
    GuideSufficiencyProjectionAuthorizationPort,
    ProjectGuideCompilationAuthorizationPort,
    SetupFinalizationAuthorizationPort,
)
from app.modules.authorization.api.guide_proposal_review import GuideProposalAuthorizationPort
from app.modules.authorization.api.post_policy import PostPolicyAuthorizationPort
from app.modules.projects.api import (
    ProjectContributionPolicyEligibilityPort,
    ProjectLockedPolicyContextPort,
)
from app.modules.projects.api.guide_activation import (
    GuideActivationAuthorizationPort,
    GuideActivationPort,
    GuideActivationReadinessPort,
    GuideContributionPolicyPort,
)
from app.modules.projects.api.guide_compilation import ProjectGuideCompilationDeliveryPort
from app.modules.projects.api.guide_documents import (
    GuideDocumentAccessFactory,
    GuideDocumentManifestPort,
    GuideDocumentToolsFactory,
    GuideRuntimeResourceCleanupAdapter,
    ProjectGuideDocumentScopePort,
)
from app.modules.projects.api.guide_proposals import (
    GuideCorrectionDispatchPort,
    GuideProposalOperationsPort,
)
from app.modules.projects.api.guide_reads import ProjectGuideReadPort
from app.modules.projects.api.post_policy import PostPolicyDeliveryPort, PostPolicyOperationsPort
from app.modules.projects.contribution_policy import ProjectContributionPolicyEligibility
from app.modules.projects.guide_compilation.live import (
    LiveGuideCompilationCoordinator,
    RequestAuthority,
)
from app.modules.projects.guide_compilation.orchestrator import (
    GuideCompilationAuthorizationContext,
    project_guide_compilation_execution_port,
)
from app.modules.projects.guide_compilation.projections import GuideCompilationProjectionService
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
from app.modules.projects.post_policy.delivery import PostPolicyServiceAuthority


def project_locked_policy_context_port(
    session: AsyncSession,
) -> ProjectLockedPolicyContextPort:
    """Bind the public PROJECT locked-policy port to its repository."""
    return ProjectLockedPolicyRepository(session)


def project_contribution_policy_eligibility_port(
    session: AsyncSession,
) -> ProjectContributionPolicyEligibilityPort:
    """Construct the PROJECTS-owned policy eligibility port."""
    return ProjectContributionPolicyEligibility(session)


def setup_model_usage_owner(session: AsyncSession):
    """Expose PROJECTS setup currentness only through the shared typed owner port."""
    from app.modules.projects.guide_compilation.model_usage import SetupModelUsageCurrent

    return SetupModelUsageCurrent(session)


def project_guide_compilation_delivery_port(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    material_factory: Callable[[AsyncSession], GuideDocumentManifestPort],
    document_tools_factory: GuideDocumentToolsFactory,
    model_session_factory,
    request_authority: RequestAuthority,
    execution_authority: GuideCompilationAuthorizationContext,
    configuration_factory: Callable[[], ProjectGuideRuntimeConfiguration],
    model_profiles,
    runtime_factory: Callable[[ProjectGuideRuntimeConfiguration], ProjectGuideAgentRuntime],
    sufficiency_authorization_factory: Callable[
        [AsyncSession], GuideSufficiencyProjectionAuthorizationPort
    ],
    policy_authorization_factory: Callable[
        [AsyncSession], ArtifactPolicyProjectionAuthorizationPort
    ],
    finalization_authorization_factory: Callable[
        [AsyncSession], SetupFinalizationAuthorizationPort
    ],
) -> ProjectGuideCompilationDeliveryPort:
    """Compose the existing PROJECTS owners from explicit external capability ports."""
    return LiveGuideCompilationCoordinator(
        session_factory,
        material_factory=material_factory,
        request_authority=request_authority,
        configuration_factory=configuration_factory,
        model_profiles=model_profiles,
        execution=project_guide_compilation_execution_port(
            session_factory,
            material_factory=material_factory,
            authorization_context=execution_authority,
            runtime_factory=runtime_factory,
            document_tools_factory=document_tools_factory,
            model_session_factory=model_session_factory,
        ),
        projections=GuideCompilationProjectionService(
            session_factory,
            material_factory=material_factory,
            sufficiency_authorization_factory=sufficiency_authorization_factory,
            policy_authorization_factory=policy_authorization_factory,
        ),
        finalization_authorization_factory=finalization_authorization_factory,
    )


async def cleanup_project_guide_runtime_resources(
    session_factory,
    *,
    retained_runtime_key,
    cleanup_adapter_factory: ExternalServiceAdapterFactory[
        GuideRuntimeResourceCleanupAdapter
    ],
):
    """Select a cleanup-only adapter from each immutable retained runtime identity."""
    from app.modules.projects.guide_compilation.runtime_resources import (
        SqlAlchemyGuideRuntimeCleanupCustody,
        pending_runtime_resource_cleanup,
    )

    async with session_factory() as session:
        candidates = await pending_runtime_resource_cleanup(
            session, retained_runtime_key=retained_runtime_key
        )
    completed = 0
    for candidate in candidates:
        try:
            cleanup_adapter = cleanup_adapter_factory.create(candidate.runtime_key)
            custody = SqlAlchemyGuideRuntimeCleanupCustody(
                session_factory,
                candidate.attempt_id,
                candidate.manifest_sha256,
                candidate.runtime_key,
            )
            completed += bool(await cleanup_adapter.cleanup(custody))
        except Exception:
            # Keep exact-ID custody for the next bounded scan; never re-enter inference.
            continue
    return {"selected": len(candidates), "completed": completed}


def project_guide_document_tools_factory(
    session_factory,
    *,
    document_access_factory: GuideDocumentAccessFactory,
    parser_factory,
) -> GuideDocumentToolsFactory:
    """Compose ART, parser and PROJECTS custody behind the sole runtime tool port."""
    from app.adapters.projects.guide_document_tools import (
        trusted_guide_document_tools_factory,
    )
    from app.modules.projects.guide_compilation.runtime_resources import (
        SqlAlchemyGuideDocumentAccessCustody,
    )

    return trusted_guide_document_tools_factory(
        grant_factory=document_access_factory,
        parser_factory=parser_factory,
        custody_factory=lambda attempt_id, manifest, configuration: (
            SqlAlchemyGuideDocumentAccessCustody(
                session_factory,
                attempt_id,
                manifest,
                configuration.runtime_key,
            )
        ),
    )


def project_guide_document_scope_port(session: AsyncSession) -> ProjectGuideDocumentScopePort:
    """Bind PROJECTS current document scope independently from ART storage."""
    from app.modules.projects.guide_compilation.document_scope import (
        SqlAlchemyProjectGuideDocumentScope,
    )

    return SqlAlchemyProjectGuideDocumentScope(session)


def project_guide_proposal_service(
    session: AsyncSession,
    authorization: GuideProposalAuthorizationPort,
) -> GuideProposalOperationsPort[
    ActorIdentityFacts,
    GuideDocumentManifestPort,
]:
    """Compose the sole proposal owner with explicit authority."""
    from app.adapters.checkers import external_checker_registry_reader, model_profile_reader
    from app.modules.projects.guide_compilation.proposal_service import GuideProposalService

    return GuideProposalService(
        session,
        authorization,
        external_checker_registry_reader(session),
        model_profile_reader(session),
    )


def project_guide_correction_dispatch(
    session: AsyncSession,
    authorization: ProjectGuideCompilationAuthorizationPort,
    *,
    material: GuideDocumentManifestPort,
    configuration: ProjectGuideRuntimeConfiguration,
) -> GuideCorrectionDispatchPort[ActorIdentityFacts]:
    """Compose human correction admission and existing queue dispatch without inference."""
    from app.modules.projects.guide_compilation.correction_dispatch import (
        GuideCorrectionDispatchService,
    )
    from app.modules.projects.guide_compilation.request_inputs import CompilationRequestInputs

    from app.adapters.model_usage import model_profile_reader

    return GuideCorrectionDispatchService(
        session,
        authorization,
        CompilationRequestInputs(material, configuration),
        profiles=model_profile_reader(session),
    )


def project_post_policy_service(
    session: AsyncSession,
    authorization: PostPolicyAuthorizationPort,
) -> PostPolicyOperationsPort[ActorIdentityFacts, GuideProposalAuthorizationPort, object]:
    """Compose the canonical post-policy owner with explicitly supplied authority."""
    from app.modules.projects.post_policy.service import PostPolicyService

    return PostPolicyService(session, authorization)


def project_post_policy_delivery_port(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    authority: PostPolicyServiceAuthority,
) -> PostPolicyDeliveryPort:
    """Compose deterministic delivery without document or agent capabilities."""
    from app.modules.projects.post_policy.delivery import PostPolicyDeliveryService

    return PostPolicyDeliveryService(session_factory, authority=authority)


async def pending_post_policy_approvals(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    after: UUID | None,
    limit: int,
) -> list[UUID]:
    """Read only pending immutable approval identifiers for a bounded internal scan."""
    from app.modules.projects.post_policy.delivery import pending_approval_ids

    async with session_factory() as session:
        return await pending_approval_ids(session, after=after, limit=limit)


async def dispatch_post_policy_derivation_after_commit(approval_operation_id: UUID) -> bool:
    """Publish the committed approval; existing custody survives broker failure."""
    from app.modules.projects.post_policy.queue import dispatch_after_commit

    return await dispatch_after_commit(approval_operation_id)


def project_guide_activation_port(
    session: AsyncSession,
    *,
    contribution: GuideContributionPolicyPort,
    authorization: GuideActivationAuthorizationPort | None = None,
) -> GuideActivationPort[ActorIdentityFacts]:
    """Compose canonical activation with explicit CON validation and authority."""
    from app.adapters.checkers import external_checker_registry_reader, model_profile_reader
    from app.modules.projects.guide_activation.service import GuideActivationService

    return GuideActivationService(
        session,
        contribution=contribution,
        authorization=authorization,
        registry=external_checker_registry_reader(session),
        profiles=model_profile_reader(session),
    )


def project_guide_activation_readiness_port(
    session: AsyncSession,
    *,
    contribution: GuideContributionPolicyPort,
) -> GuideActivationReadinessPort:
    """Compose activation's own conditions for a dry run; no activation authority is bound."""
    from app.adapters.checkers import external_checker_registry_reader, model_profile_reader
    from app.modules.projects.guide_activation.service import GuideActivationService

    return GuideActivationService(
        session,
        contribution=contribution,
        registry=external_checker_registry_reader(session),
        profiles=model_profile_reader(session),
    )


def project_guide_reader(session: AsyncSession) -> ProjectGuideReadPort:
    """Read a project's guides, declared documents and selected policies for an authorized caller."""
    from app.modules.projects.guide_reads import ProjectGuideReader

    return ProjectGuideReader(session)


def project_summary_reader(session: AsyncSession):
    """Read minimal identity and active guide version for an authorized project set."""
    from app.modules.projects.project_summaries import ProjectSummaryReader

    return ProjectSummaryReader(session)
