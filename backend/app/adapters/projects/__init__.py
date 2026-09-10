"""PROJECT-owned composition adapters."""

from app.modules.projects.api.guide_documents import ProjectGuideDocumentScopePort
from collections.abc import Callable
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.modules.projects.api.guide_documents import GuideDocumentManifestPort, GuideDocumentAccessFactory
from app.interfaces.project_agents import ProjectGuideAgentRuntime
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.modules.checkers.api.pre_submit_catalogue import PreSubmissionCapabilityProjection
from app.modules.checkers.api.post_submit_catalogue import PostSubmitCatalogue
from app.modules.authorization.api import (
    GuideSufficiencyProjectionAuthorizationPort,
    ArtifactPolicyProjectionAuthorizationPort,
    SetupFinalizationAuthorizationPort,
)
from app.modules.projects.guide_compilation.live import RequestAuthority
from app.modules.projects.guide_compilation.orchestrator import GuideCompilationAuthorizationContext
from app.modules.projects.api.guide_compilation import ProjectGuideCompilationDeliveryPort
from app.modules.projects.guide_compilation.live import LiveGuideCompilationCoordinator
from app.modules.projects.guide_compilation.orchestrator import (
    project_guide_compilation_execution_port,
)
from app.modules.projects.guide_compilation.projections import GuideCompilationProjectionService

from app.modules.projects.api import (
    ProjectContributionPolicyEligibilityPort,
    ProjectLockedPolicyContextPort,
)
from app.modules.projects.contribution_policy import ProjectContributionPolicyEligibility
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository


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


def project_guide_compilation_delivery_port(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    material_factory: Callable[[AsyncSession], GuideDocumentManifestPort],
    document_access_factory: GuideDocumentAccessFactory,
    pre_capabilities: PreSubmissionCapabilityProjection,
    post_capabilities: PostSubmitCatalogue,
    request_authority: RequestAuthority,
    execution_authority: GuideCompilationAuthorizationContext,
    configuration_factory: Callable[[], ProjectGuideRuntimeConfiguration],
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
        pre_capabilities=pre_capabilities,
        post_capabilities=post_capabilities,
        request_authority=request_authority,
        configuration_factory=configuration_factory,
        execution=project_guide_compilation_execution_port(
            session_factory,
            material_factory=material_factory,
            pre_submission_capabilities=pre_capabilities,
            post_submission_capabilities=post_capabilities,
            authorization_context=execution_authority,
            runtime_factory=runtime_factory,
            document_access_factory=document_access_factory,
        ),
        projections=GuideCompilationProjectionService(
            session_factory,
            material_factory=material_factory,
            sufficiency_authorization_factory=sufficiency_authorization_factory,
            policy_authorization_factory=policy_authorization_factory,
        ),
        finalization_authorization_factory=finalization_authorization_factory,
    )


async def cleanup_project_guide_runtime_resources(session_factory, *, runtime_factory):
    """Compose exact retained cleanup scopes without source grants or inference admission."""
    from app.modules.projects.guide_compilation.runtime_resources import (
        SqlAlchemyGuideRuntimeCleanupCustody, pending_runtime_resource_cleanup,
    )

    async with session_factory() as session:
        candidates = await pending_runtime_resource_cleanup(session)
    completed = 0
    for attempt_id, manifest_sha256, configuration in candidates:
        runtime = None
        try:
            runtime = runtime_factory(configuration)
            if runtime.identity != configuration.adapter_identity:
                raise ValueError("cleanup runtime identity mismatch")
            custody = SqlAlchemyGuideRuntimeCleanupCustody(
                session_factory, attempt_id, manifest_sha256, configuration.runtime_key,
            )
            completed += bool(await runtime.cleanup_resources(custody))
        except Exception:
            # Keep exact-ID custody for the next bounded scan; never re-enter inference.
            continue
        finally:
            if runtime is not None:
                await runtime.aclose()
    return {"selected": len(candidates), "completed": completed}


def project_guide_document_scope_port(session: AsyncSession) -> ProjectGuideDocumentScopePort:
    """Bind PROJECTS current document scope independently from ART storage."""
    from app.modules.projects.guide_compilation.document_scope import SqlAlchemyProjectGuideDocumentScope
    return SqlAlchemyProjectGuideDocumentScope(session)
