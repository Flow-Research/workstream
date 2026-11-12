"""Exact project resource audit selectors, without raw product facts."""

from uuid import UUID
from app.modules.authorization.domain.submission_intake import IntakeReservationResourceContext, IntakeReservationPreflightResourceContext
from app.modules.authorization.domain.contributor_reads import ContributorWorkReadResourceContext

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.lifecycle import ReviewLifecycleActivationContract
from app.modules.authorization.domain.post_submit_routing import PostSubmitRoutingResourceContext
from app.modules.authorization.domain.post_submit import PostSubmitResourceContext
from app.modules.authorization.domain.pre_submit import PreSubmitResourceContext
from app.modules.authorization.domain.assignment_invalidation import AssignmentInvalidationResourceContext
from app.modules.authorization.domain.revision_expiry import RevisionExpiryResourceContext
from app.modules.authorization.domain.outbox_dispatch import OutboxDispatchResourceContext
from app.modules.authorization.domain.guide_proposals import GuideProposalResourceContext
from app.modules.authorization.domain.post_policy import PostPolicyResourceContext
from app.modules.authorization.domain.action_groups import (
    GUIDE_BOUND_PROJECT_MANAGER_ACTIONS, SUBMISSION_POLICY_MUTATIONS,
)
from app.modules.authorization.domain.project_create import ProjectCreateResourceContext
from app.modules.authorization.domain.task_authority import TaskAuthorityResourceContext, TaskImportBatchResourceContext
from app.modules.authorization.domain.task_queues import QueueReadResourceContext
from app.modules.authorization.domain.submission_history import HistoryReadResourceContext


def _checker_retry_read_target(resource):
    project_id = str(resource.scope_project_id)
    return (
        project_id,
        "project",
        project_id,
        "project",
        project_id,
    )


def _post_submit_delivery_target(resource):
    from app.modules.authorization.domain.post_submit_deliveries import (
        PostSubmitDeliveryReadResourceContext,
        PostSubmitDeliveryResourceContext,
    )

    if type(resource) not in {
        PostSubmitDeliveryReadResourceContext,
        PostSubmitDeliveryResourceContext,
    }:
        return None
    project_id = str(resource.scope_project_id)
    return (
        project_id,
        resource.resource_type,
        str(resource.resource_id),
        "project",
        project_id,
    )


def _compensation_unit_target(resource):
    """A unit has no record identifier, so its audit target is the owning project."""
    from app.modules.authorization.domain.contribution_policies import (
        ProjectCompensationUnitCreateResourceContext,
    )

    if type(resource) is not ProjectCompensationUnitCreateResourceContext:
        return None
    project_id = str(resource.scope_project_id)
    return project_id, "project", project_id, "project", project_id


def _model_administration_target(resource):
    """Audit project model administration against its exact owning project."""
    from app.modules.authorization.domain.model_usage import (
        ProjectModelAdministrationResourceContext,
    )

    if type(resource) is not ProjectModelAdministrationResourceContext:
        return None
    project_id = str(resource.project_id)
    return project_id, "project", project_id, "project", project_id


def _submission_operation_target(resource):
    if type(resource) in {IntakeReservationResourceContext, IntakeReservationPreflightResourceContext} or (
        type(resource) is ContributorWorkReadResourceContext
        and resource.resource_type == "submission_operation_read"
    ):
        return (str(resource.scope_project_id), "submission_operation", str(resource.resource_id),
                "submission_operation", str(resource.resource_id))
    return None


def _special_authority_target(resource):
    return (_submission_operation_target(resource) or _post_submit_delivery_target(resource)
            or _compensation_unit_target(resource) or _model_administration_target(resource))


def project_authority_audit_target(
    resource: object, action_id: ActionId,
    *, matched_scope_project_id: UUID | None = None,
) -> tuple[str | None, str | None, str | None, str, str] | None:
    """Project-scoped exact contexts share bounded audit selectors, never raw facts."""
    from app.modules.authorization.domain.contribution_policies import (
        ContributionPolicyReadResourceContext, ContributionPolicyMutationResourceContext,
        ContributionPolicyMutationScopeDenialResourceContext,
    )
    from app.modules.authorization.domain.contribution_reads import ContributionProjectReadResourceContext
    from app.modules.authorization.domain.adapter_bindings import (
        AdapterBindingReadResourceContext,
        AdapterBindingMutationResourceContext,
    )
    from app.modules.authorization.domain.checker_registry import ExternalCheckerRegistryResourceContext
    from app.modules.authorization.domain.checker_retry import CheckerRetryPrepareDenialResourceContext, CheckerRetryResourceContext
    from app.modules.authorization.domain.checker_retry_reads import CheckerRetrySourceReadResourceContext
    from app.modules.authorization.domain.guide_compilation import (
        ProjectGuideCompilationRequestResourceContext,
        ProjectGuideCompilationExecuteResourceContext,
    )
    from app.modules.authorization.domain.guide_compilation_projections import ProjectGuideProjectionResourceContext
    from app.modules.authorization.domain.project_setup_finalization import (
        ProjectSetupFinalizationResourceContext,
    )
    from app.modules.authorization.runtime import (
        PreSubmitCheckerInputResourceContext, ProjectSubmissionArtifactPolicyMutationResourceContext,
        SubmissionCreationResourceContext, SubmissionBindingResourceContext,
        ProjectGuideActivationResourceContext,
    )

    if type(resource) is ReviewLifecycleActivationContract:
        return None, resource.resource_type, str(resource.resource_id), "joint_lifecycle_control", str(resource.resource_id)
    if type(resource) is TaskImportBatchResourceContext:
        project_id, resource_id = str(resource.scope_project_id), str(resource.resource_id)
        return project_id, resource.resource_type, resource_id, resource.resource_type, resource_id
    if type(resource) is ContributionProjectReadResourceContext:
        if matched_scope_project_id != resource.scope_project_id:
            return None
        project_id = str(resource.scope_project_id)
        return project_id, "project", project_id, "project", project_id
    if type(resource) is ContributionPolicyMutationScopeDenialResourceContext:
        project_id = str(resource.scope_project_id)
        if resource.project_exists:
            return project_id, "project", project_id, "project", project_id
        return None, None, None, "project", project_id
    if action_id is ActionId.PROJECT_GUIDE_ACTIVATE and isinstance(resource, ProjectGuideActivationResourceContext):
        project_id = str(resource.scope_project_id)
        return project_id, resource.resource_type, str(resource.resource_id), "project", project_id
    if type(resource) is AssignmentInvalidationResourceContext:
        project_id = str(resource.scope_project_id)
        return project_id, "task", str(resource.resource_id), "project", project_id
    if type(resource) is RevisionExpiryResourceContext:
        project_id = str(resource.scope_project_id)
        return project_id, "task", str(resource.resource_id), "project", project_id
    if isinstance(resource, (TaskAuthorityResourceContext, QueueReadResourceContext, HistoryReadResourceContext)):
        project_id = str(resource.scope_project_id)
        return project_id, "project", project_id, "project", project_id
    if isinstance(resource, ProjectCreateResourceContext):
        return None, "project_create_operation", str(resource.resource_id), "project", str(resource.requested_project_id)
    if isinstance(resource, ExternalCheckerRegistryResourceContext):
        entry_id = str(resource.resource_id)
        return None, resource.resource_type, entry_id, resource.resource_type, entry_id
    if type(resource) in {
        CheckerRetryPrepareDenialResourceContext,
        CheckerRetryResourceContext,
    }:
        project_id = str(resource.project_id)
        return project_id, "checker_run", str(resource.resource_id), "project", project_id
    if type(resource) is CheckerRetrySourceReadResourceContext:
        return _checker_retry_read_target(resource)
    if target := _special_authority_target(resource):
        return target
    if action_id in SUBMISSION_POLICY_MUTATIONS and isinstance(
        resource, ProjectSubmissionArtifactPolicyMutationResourceContext,
    ):
        project_id = str(resource.scope_project_id)
        return project_id, resource.resource_type, str(resource.resource_id), "project", project_id
    if isinstance(
        resource,
        (
            PreSubmitCheckerInputResourceContext,
            SubmissionCreationResourceContext, SubmissionBindingResourceContext,            ProjectGuideCompilationRequestResourceContext,
            ProjectGuideCompilationExecuteResourceContext,
            ContributionPolicyReadResourceContext, ContributionPolicyMutationResourceContext,
            AdapterBindingReadResourceContext,
            AdapterBindingMutationResourceContext,
            ProjectGuideProjectionResourceContext,
            ProjectSetupFinalizationResourceContext,
            GuideProposalResourceContext, PostPolicyResourceContext, OutboxDispatchResourceContext, PreSubmitResourceContext, PostSubmitResourceContext, PostSubmitRoutingResourceContext,
        ),
    ):
        project_id = str(getattr(resource, "project_id", None) or resource.scope_project_id)
        return project_id, resource.resource_type, str(resource.resource_id), "project", project_id
    if action_id in GUIDE_BOUND_PROJECT_MANAGER_ACTIONS:
        scope_project_id = getattr(resource, "scope_project_id", None)
        if scope_project_id is not None:
            project_id = str(scope_project_id)
            return project_id, "project", project_id, "project", project_id
    return None
