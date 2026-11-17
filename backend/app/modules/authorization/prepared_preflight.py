"""Selector-only AUTH preflight without prepared handles or allow evidence."""
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.guide_compilation import ProjectGuideCompilationRequestResourceContext
from app.modules.authorization.domain.prepared_compilation import prepared_compilation_matches
from app.modules.authorization.domain.prepared_service import project_setup_resource_matches
from app.modules.authorization.domain.submission_intake import IntakeReservationPreflightResourceContext, intake_preflight_matches
from app.modules.authorization.submission_preparation import SubmissionBundlePreparationPreflightResourceContext
from app.modules.authorization.runtime import (
    AuthorizationDenialCode, PreparedAuthorizationHandleInvalid, PreparedAuthorizationUnsupported,
)


async def preflight_authority(service, action_id, caller_input, scope, resource):
    """Check exact selectors and current grant under the issuing service's root."""
    from app.modules.authorization.prepared import _submission_preparation_binding_matches
    service._root_transaction()
    if action_id is ActionId.SUBMISSION_INTAKE_RESERVE:
        scope_matches = True  # The strict intake matcher compares both scope and selectors.
        resource_matches = intake_preflight_matches(caller_input, resource, scope)
    else:
        binding = service._binding(action_id, caller_input, scope)
        scope_matches = service._scope_from_resource(action_id, resource) == scope
        if isinstance(resource, SubmissionBundlePreparationPreflightResourceContext):
            resource_matches = _submission_preparation_binding_matches(binding, resource)
        else:
            resource_matches = prepared_compilation_matches(
                binding.guide_compilation_context,
                binding.guide_compilation_resource_digest,
                resource,
            )
    if not scope_matches or not resource_matches:
        raise PreparedAuthorizationHandleInvalid("invalid prepared authorization preflight")
    authority = await service._authorization._prepare_prelocked(
        service._consumer_token, action_id, scope
    )
    try:
        setup_match = project_setup_resource_matches(
            action_id, resource, authority.scope_project_id
        )
        if setup_match is False or (
            setup_match is None
            and action_id is not ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE
            and not (action_id is ActionId.SUBMISSION_INTAKE_RESERVE
                     and type(resource) is IntakeReservationPreflightResourceContext)
            and not (
                action_id is ActionId.PROJECT_GUIDE_COMPILATION_REQUEST
                and isinstance(resource, ProjectGuideCompilationRequestResourceContext)
                and resource.trigger == "project_manager"
                and resource.scope_project_id == authority.scope_project_id
            )
        ):
            raise PreparedAuthorizationUnsupported(
                AuthorizationDenialCode.RESOURCE_GUARD_DENIED
            )
    finally:
        service._authorization._discard_prelocked(authority)

