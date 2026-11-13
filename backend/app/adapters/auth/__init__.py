"""Authorization application adapters and same-owner composition."""

import json
from contextlib import asynccontextmanager
from uuid import UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth.adapter_bindings import CompensationAdapterBindingAuthorization
from app.adapters.auth.assignment_invalidation_publication import (
    assignment_invalidation_publication,
)
from app.adapters.auth.contribution_policies import ContributionPolicyAuthorization
from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.adapter_binding_authorization import (
    AdapterBindingAuthorizationAdapter,
)
from app.modules.authorization.api import (
    ActorIdentityFacts,
    ActorKind,
    AuthorizationDenied,
    ProjectGuideCompilationAuthorizationPort,
)
from app.modules.authorization.api.guide_proposal_review import GuideProposalAuthorizationPort
from app.modules.authorization.api.outbox_dispatch import OutboxDispatchAuthorizationPort
from app.modules.authorization.api.post_policy import PostPolicyAuthorizationPort
from app.modules.authorization.artifact_operator_authorization import (
    ArtifactOperatorReadAuthorization,
    ArtifactOperatorRetryAuthorization,
)
from app.modules.authorization.contribution_policy_authorization import (
    ContributionPolicyAuthorizationAdapter,
)
from app.modules.authorization.domain.post_submit_routing import (
    AutomatedAcceptanceConsequence,
    CheckerExhaustionConsequence,
    CheckerRemediationConsequence,
    HumanAdmissionConsequence,
    PostSubmitRoutingResourceContext,
)
from app.modules.authorization.guide_compilation import ProjectGuideCompilationAuthorizationAdapter
from app.modules.authorization.guide_compilation_projections import (
    ArtifactPolicyProjectionAuthorization,
    GuideSufficiencyProjectionAuthorization,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.post_submit_routing_authorization import (
    PostSubmitRoutingAuthorization,
)
from app.modules.authorization.prepared import (
    PreparedAuthorizationService,
    fixed_service_prepared_authorization,
)
from app.modules.authorization.project_setup_finalization import SetupFinalizationAuthorization
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    AuthorizationContext,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationUnsupported,
    ServiceAuthorizationContext,
)
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.authorization.task_import_sources import PreparedTaskImportSourceAuthorization
from app.modules.projects.api.guide_activation import GuideActivationAuthorizationPort
from app.modules.tasks.api.routing_outcome import RoutingAuthorityFacts


def artifact_operator_read_authorization(
    session: AsyncSession, context: AuthorizationContext,
) -> ArtifactOperatorReadAuthorization:
    """Compose exact ART read decisions in the caller's transaction."""
    return ArtifactOperatorReadAuthorization(
        AuthorizationService(session, context, admin_repository=AdminAuthorizationRepository(session))
    )


def artifact_operator_retry_authorization(
    session: AsyncSession, context: AuthorizationContext,
) -> ArtifactOperatorRetryAuthorization:
    """Compose independent ART retry authority in ART's transaction."""
    return ArtifactOperatorRetryAuthorization(
        AuthorizationService(session, context, admin_repository=AdminAuthorizationRepository(session))
    )


def setup_finalization_authorization(session: AsyncSession) -> SetupFinalizationAuthorization:
    """Compose explicit hidden finalization authority in the caller session."""
    return SetupFinalizationAuthorization(session)


def task_authorization(
    session: AsyncSession, context: AuthorizationContext,
) -> PreparedTaskAuthorization:
    """Compose exact task authority in AUTH's registered composition root."""
    return PreparedTaskAuthorization(session, context)


def task_import_source_authorization(
    session: AsyncSession, context: AuthorizationContext,
) -> PreparedTaskImportSourceAuthorization:
    """Compose exact source authority in AUTH's registered owner root."""
    return PreparedTaskImportSourceAuthorization(session, context)


def checker_retry_authorization(session: AsyncSession, context: AuthorizationContext):
    """Compose one hidden retry through canonical prepared Operator authority."""
    from app.modules.authorization.checker_retry_authorization import (
        PreparedCheckerRetryAuthorization,
    )
    return PreparedCheckerRetryAuthorization(session, context)


def post_submit_delivery_authorization(
    session: AsyncSession, context: AuthorizationContext,
):
    """Compose one exact public uncertain-delivery reconciliation decision."""
    from app.modules.authorization.post_submit_delivery_authorization import (
        PostSubmitDeliveryAuthorization,
    )

    repository = AdminAuthorizationRepository(session)
    kernel = AuthorizationService(session, context, admin_repository=repository)
    return PostSubmitDeliveryAuthorization(session, context, kernel)


def post_submit_delivery_cause_authorization(session: AsyncSession):
    """Validate the retained human decision as worker cause without new authority."""
    from app.modules.authorization.post_submit_delivery_authorization import (
        PostSubmitDeliveryAuthorization,
    )

    return PostSubmitDeliveryAuthorization(session, None, None)


def checker_registry_authorization(
    session: AsyncSession, context: AuthorizationContext,
):
    """Compose CHECKERS registry access through one canonical AUTH/PREP graph."""
    from app.modules.authorization.checker_registry_authorization import (
        ExternalCheckerRegistryAuthorizationAdapter,
    )

    repository = AdminAuthorizationRepository(session)
    kernel = AuthorizationService(session, context, admin_repository=repository)
    prepared = PreparedAuthorizationService(session, context, kernel, repository)
    return ExternalCheckerRegistryAuthorizationAdapter(kernel, prepared)


def checker_model_authorization(session: AsyncSession, context: AuthorizationContext):
    """Compose exact project-model authority using the existing AUTH/PREP graph."""
    from app.modules.authorization.model_usage_authorization import CheckerModelAuthorization

    repository = AdminAuthorizationRepository(session)
    revalidate = None
    if isinstance(context, ServiceAuthorizationContext):
        from app.modules.authorization.prepared import fixed_service_context_revalidator

        if context.service_identity not in {
            ServiceIdentity.CHECKER_POST_SUBMIT,
            ServiceIdentity.PROJECT_SETUP,
        }:
            raise TypeError("model usage service identity is unsupported")
        revalidate = fixed_service_context_revalidator(repository, context.service_identity)
    kernel = AuthorizationService(
        session, context, admin_repository=repository, revalidate_service=revalidate,
    )
    prepared = PreparedAuthorizationService(session, context, kernel, repository)
    return CheckerModelAuthorization(kernel, prepared)


async def checker_model_service_authorization(session: AsyncSession, request_id: UUID):
    """Resolve the fixed POST checker principal within the caller's transaction."""
    from app.modules.authorization.prepared import fixed_service_authorization_context

    context = await fixed_service_authorization_context(
        session, ServiceIdentity.CHECKER_POST_SUBMIT, request_id, request_id,
    )
    return checker_model_authorization(session, context)


async def setup_model_service_authorization(session: AsyncSession, request_id: UUID):
    """Resolve the fixed PROJECT_SETUP principal for one setup model effect."""
    from app.modules.authorization.prepared import fixed_service_authorization_context

    context = await fixed_service_authorization_context(
        session,
        ServiceIdentity.PROJECT_SETUP,
        request_id,
        uuid5(request_id, "setup-model-authority"),
    )
    return checker_model_authorization(session, context)


def checker_output_write_authorization(session: AsyncSession):
    """Compose private model-evidence admission and recovery authority."""
    from app.modules.authorization.checker_output_authorization import (
        PreparedCheckerOutputWriteAuthorization,
    )

    return PreparedCheckerOutputWriteAuthorization(session)


def checker_output_binding_authorization(session: AsyncSession):
    """Compose verified call-evidence publication authority."""
    from app.modules.authorization.checker_output_authorization import (
        PreparedCheckerOutputBindingAuthorization,
    )

    return PreparedCheckerOutputBindingAuthorization(session)


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


def contribution_read_authorization(session: AsyncSession, context: AuthorizationContext):
    """Compose fresh contribution evidence authority in the export transaction."""
    from app.modules.authorization.contribution_read import ContributionReadAuthorization

    return ContributionReadAuthorization(AuthorizationService(
        session, context, admin_repository=AdminAuthorizationRepository(session),
    ))


__all__ = (
    "CompensationAdapterBindingAuthorization",
    "ContributionPolicyAuthorization",
    "artifact_policy_projection_authorization",
    "assignment_invalidation_publication",
    "checker_registry_authorization",
    "compensation_adapter_binding_authorization",
    "contribution_policy_authorization",
    "guide_compilation_execution_authority",
    "guide_sufficiency_projection_authorization",
    "setup_finalization_authorization",
    "task_authorization",
    "task_import_source_authorization",
)


@asynccontextmanager
async def _guide_compilation_execution_context(session, operation_id):
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
    async with _guide_compilation_execution_context(
        session, state.preflight_facts.operation_id
    ) as composed:
        yield composed


def guide_proposal_authorization(
    session: AsyncSession, context: AuthorizationContext,
) -> GuideProposalAuthorizationPort:
    """Bind the public proposal authority port to the canonical request adapter."""
    from app.modules.authorization.guide_proposal_authorization import (
        GuideProposalAuthorizationAdapter,
    )

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
    from app.modules.authorization.guide_activation_authorization import (
        GuideActivationAuthorizationAdapter,
    )

    return GuideActivationAuthorizationAdapter(session, context)


def outbox_dispatch_authorization(session: AsyncSession) -> "OutboxDispatchAuthorizationPort":
    """Compose the one fixed dispatcher through canonical AUTH/PREP."""
    from app.modules.authorization.outbox_dispatch_authorization import (
        OutboxDispatchAuthorizationAdapter,
    )

    return OutboxDispatchAuthorizationAdapter(session)


def assignment_invalidation_authorization(session: AsyncSession):
    """Compose the exact reconciler through canonical fixed-service PREP."""
    from app.modules.authorization.assignment_invalidation_authorization import (
        AssignmentInvalidationAuthorizationAdapter,
    )

    return AssignmentInvalidationAuthorizationAdapter(session)


def revision_expiry_authorization(session: AsyncSession):
    """Bind TASK's deadline effect to canonical fixed-service AUTH."""
    from app.modules.authorization.revision_expiry_authorization import (
        RevisionExpiryAuthorizationAdapter,
    )

    return RevisionExpiryAuthorizationAdapter(session)


def revision_recovery_authorization(session: AsyncSession):
    """Bind retained-window recovery to canonical fixed-service AUTH."""
    from app.modules.authorization.revision_recovery_authorization import (
        RevisionRecoveryAuthorizationAdapter,
    )

    return RevisionRecoveryAuthorizationAdapter(session)


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


def checker_retry_discovery_authorization(session, context, secret):
    """Compose exact Operator retry-source reads through the shared AUTH kernel."""
    from app.modules.authorization.checker_retry_read import (
        CheckerRetryDiscoveryAuthorization,
    )
    from app.modules.authorization.kernel import AuthorizationService

    repository = AdminAuthorizationRepository(session)
    return CheckerRetryDiscoveryAuthorization(
        AuthorizationService(
            session, context, admin_repository=repository,
        ),
        secret,
    )


def post_submit_delivery_read_authorization(session, context, secret):
    """Compose exact Operator uncertain-delivery reads through canonical AUTH."""
    from app.modules.authorization.post_submit_delivery_read import (
        PostSubmitDeliveryReadAuthorization,
    )

    repository = AdminAuthorizationRepository(session)
    return PostSubmitDeliveryReadAuthorization(
        AuthorizationService(session, context, admin_repository=repository),
        secret,
    )


def contributor_read_authorization(kernel, session: AsyncSession, secret):
    """Compose the caller's own-work AUTH adapter in the shared decision transaction."""
    from app.modules.authorization.contributor_read import ContributorReadAuthorization
    return ContributorReadAuthorization(kernel, AdminAuthorizationRepository(session), secret)


def project_catalogue_authorization(kernel, secret):
    """Compose the bounded system-project read through the request kernel."""
    from app.modules.authorization.project_catalogue import ProjectCatalogueAuthorization
    return ProjectCatalogueAuthorization(kernel, secret)


def project_management_read_authorization(kernel, secret):
    """Compose the project-wide Project Manager and Finance read adapter over the request kernel."""
    from app.modules.authorization.management_read import ProjectManagementReadAuthorization
    return ProjectManagementReadAuthorization(kernel, secret)


def history_read_authorization(kernel):
    """Compose current AUTH decisions for owner-selected immutable history."""
    from app.modules.authorization.history_authorization import HistoryReadAuthorization
    return HistoryReadAuthorization(kernel)


def post_submit_execution_authority(session):
    """Compose fixed checker execute/finalize authority over shared PREP."""
    from app.modules.authorization.post_submit_authorization import PostSubmitExecutionAuthorization
    return PostSubmitExecutionAuthorization(session)


def selected_pre_submit_authority(session):
    """Compose fixed selected-PRE execute/finalize authority."""
    from app.modules.authorization.pre_submit_authorization import (
        SelectedPreSubmitAuthorization,
    )

    return SelectedPreSubmitAuthorization(session)


def post_submit_materialization_authority(session):
    """Compose the separate fixed ART materializer principal."""
    from app.modules.authorization.post_submit_authorization import (
        PostSubmitMaterializationAuthorization,
    )
    return PostSubmitMaterializationAuthorization(session)


def lifecycle_transition_authorization(session: AsyncSession, context):
    """Compose the existing system Operator action for the REV controller."""
    from app.modules.authorization.lifecycle_authorization import LifecycleAuthorizationAdapter

    return LifecycleAuthorizationAdapter(session, context)


def _routing_resource(
    source,
    claim,
    effects,
    authorized_generation,
    actor_id,
    link_id,
    *,
    reconciliation_claim=None,
):
    accepts = source.source.routing_recommendation == "allow_review" and not source.source.human_review_required
    if accepts != (effects is not None) or accepts != (authorized_generation is not None):
        raise PreparedAuthorizationHandleInvalid("routing consequence unavailable")
    consequence = (
        CheckerExhaustionConsequence(**source.exhaustion.model_dump())
        if source.exhaustion is not None
        else CheckerRemediationConsequence()
        if source.source.routing_recommendation == "needs_revision"
        else HumanAdmissionConsequence()
        if effects is None
        else AutomatedAcceptanceConsequence(
            task_effects=effects,
            authorized_lifecycle_generation=authorized_generation,
        )
    )
    return PostSubmitRoutingResourceContext(
        resource_id=source.source.id,
        scope_project_id=source.source.project_id,
        router_actor_id=actor_id,
        router_identity_link_id=link_id,
        request=source.request,
        source=source.source,
        claim=claim,
        reconciliation_claim=reconciliation_claim,
        consequence=consequence,
    )


def _routing_resource_values(resource):
    """Omit only the absent recovery claim; retain every established null fact."""
    values = resource.model_dump(mode="json")
    if values["reconciliation_claim"] is None:
        del values["reconciliation_claim"]
    return values


class _TaskRoutingAuthorizationAdapter:
    def __init__(self, session):
        self._authority = PostSubmitRoutingAuthorization(session)

    @asynccontextmanager
    async def prepare(self, request):
        async with self._authority.prepare(request) as prepared:
            yield _PreparedTaskRoutingAdapter(prepared)


class _PreparedTaskRoutingAdapter:
    def __init__(self, prepared):
        self._prepared = prepared

    async def consume(
        self,
        source,
        claim,
        effects,
        authorized_generation,
        *,
        reconciliation_claim=None,
    ):
        resource = _routing_resource(
            source,
            claim,
            effects,
            authorized_generation,
            self._prepared.actor_profile_id,
            self._prepared.identity_link_id,
            reconciliation_claim=reconciliation_claim,
        )
        receipt = await self._prepared.consume(resource)
        return RoutingAuthorityFacts(
            decision_id=receipt.authorization_decision_event_id,
            actor_id=receipt.actor_profile_id,
            identity_link_id=receipt.actor_identity_link_id,
            context_json=json.dumps(
                _routing_resource_values(resource), separators=(",", ":")
            ),
        )

    async def validate_replay(self, source, retained, effects, authorized_generation):
        original = PostSubmitRoutingResourceContext.model_validate_json(retained.context_json)
        expected = _routing_resource(
            source,
            original.claim,
            effects,
            authorized_generation,
            retained.actor_id,
            retained.identity_link_id,
            reconciliation_claim=original.reconciliation_claim,
        )
        if (
            original != expected
            or json.loads(retained.context_json) != _routing_resource_values(expected)
        ):
            raise PreparedAuthorizationHandleInvalid("routing receipt unavailable")
        await self._prepared.validate_replay(
            expected, retained.decision_id, retained.actor_id, retained.identity_link_id
        )


def task_routing_authorization(session):
    """Compose canonical router AUTH through the designated AUTH composition root."""
    return _TaskRoutingAuthorizationAdapter(session)
