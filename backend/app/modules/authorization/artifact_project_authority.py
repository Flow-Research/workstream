"""Shared project-authority locks and ART resource evaluation for the AUTH kernel."""

from __future__ import annotations

from app.modules.authorization.catalogue import ActionAvailability, ActionId
from app.modules.authorization.domain.task_authority import (
    TASK_ACTIONS, TASK_SUBMITTER_ACTIONS, evaluate_task_authority,
)
from app.modules.authorization.runtime import (
    AuthorizationDenialCode,
    HumanAuthorizationContext,
    MatchedAuthorityKind,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScopeKind,
    SubmissionBundlePreparationResourceContext,
    SubmissionCreationResourceContext,
)


PROJECT_SUBMITTER_ACTIONS = TASK_SUBMITTER_ACTIONS | {
    ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE, ActionId.SUBMISSION_CREATE,
}
PROJECT_AUTHORITY_ACTIONS = TASK_ACTIONS | PROJECT_SUBMITTER_ACTIONS | {
    ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
}


async def lock_project_authority(repository, context, scope, action, locked_context):
    """Dispatch the closed project-action set to its existing authority owner."""
    if action.action_id in PROJECT_SUBMITTER_ACTIONS:
        return await lock_submitter_authority(repository, context, scope, locked_context)
    if action.action_id not in PROJECT_AUTHORITY_ACTIONS:
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.ACTION_UNAVAILABLE)
    return await lock_project_admin_authority(
        repository, context, scope, action.permission_id, locked_context,
        system_scope_only=action.action_id is ActionId.OPERATIONS_TASK_START_OVERRIDE,
    )


async def lock_project_admin_authority(
    repository, context, scope, permission_id, locked_context, *, system_scope_only=False,
):
    """Lock a project-covering admin grant, or require a system grant for override."""
    if (
        not isinstance(context, HumanAuthorizationContext)
        or scope.kind is not PreparedAuthorityScopeKind.PROJECT
        or scope.project_id is None
    ):
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED)
    locked = await repository.lock_request_actor(context.identity_link_id, context.actor_profile_id)
    context = locked_context(locked, context)
    grant = await repository.find_effective_grant(
        context.actor_profile_id,
        permission_id,
        scope_project_id=scope.project_id,
        system_scope_only=system_scope_only,
        for_update=True,
    )
    if grant is None:
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.PERMISSION_NOT_GRANTED)
    return context, grant


def evaluate_project_authority(action, context, authority, resource, lifecycle_denial):
    """Keep each resource guard distinct while sharing the closed dispatch boundary."""
    if action.action_id in TASK_ACTIONS:
        return evaluate_task_authority(action, context, authority, resource, lifecycle_denial)
    if action.action_id is ActionId.ARTIFACT_GUIDE_SOURCE_INGEST:
        return evaluate_guide_ingest_authority(action, authority, resource, lifecycle_denial)
    if action.action_id in PROJECT_SUBMITTER_ACTIONS:
        return evaluate_submitter_authority(action, context, authority, resource, lifecycle_denial)
    return AuthorizationDenialCode.ACTION_UNAVAILABLE, None, None, None


def evaluate_guide_ingest_authority(action, authority, resource, lifecycle_denial):
    """Evaluate guide-ingest facts against the locked project authority."""
    from app.modules.authorization.runtime import GuideSourceIngestResourceContext

    denial = lifecycle_denial
    if denial is None and action.availability is not ActionAvailability.ACTIVE:
        denial = AuthorizationDenialCode.ACTION_UNAVAILABLE
    elif denial is None and not isinstance(resource, GuideSourceIngestResourceContext):
        denial = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    elif denial is None and resource.scope_project_id != authority.scope_project_id:
        denial = AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED
    elif denial is None and (
        authority.matched_grant_id is None or authority.matched_grant_status != "active"
    ):
        denial = AuthorizationDenialCode.PERMISSION_NOT_GRANTED
    if denial is not None:
        return denial, None, None, None
    return (
        None,
        MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        authority.matched_grant_id,
        authority.scope_project_id,
    )


async def lock_submitter_authority(repository, context, scope, locked_context):
    """Lock the exact human identity and active submitter grant."""
    if (
        not isinstance(context, HumanAuthorizationContext)
        or scope.kind is not PreparedAuthorityScopeKind.PROJECT
        or scope.project_id is None
    ):
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED)
    locked = await repository.lock_request_actor(context.identity_link_id, context.actor_profile_id)
    context = locked_context(locked, context)
    grant = await repository.find_active_project_role(
        project_id=scope.project_id,
        actor_profile_id=context.actor_profile_id,
        role="submitter",
        for_update=True,
    )
    if grant is None:
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.PERMISSION_NOT_GRANTED)
    return context, grant


def evaluate_submitter_authority(action, context, authority, resource, lifecycle_denial):
    """Evaluate the exact final facts against the locked submitter authority."""
    denial = lifecycle_denial
    if denial is None and action.availability is not ActionAvailability.ACTIVE:
        denial = AuthorizationDenialCode.ACTION_UNAVAILABLE
    elif denial is None and not isinstance(
        resource,
        (SubmissionBundlePreparationResourceContext, SubmissionCreationResourceContext),
    ):
        denial = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    elif denial is None and resource.scope_project_id != authority.scope_project_id:
        denial = AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED
    elif denial is None and (
        resource.actor_profile_id != context.actor_profile_id
        or resource.identity_link_id != context.identity_link_id
    ):
        denial = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    elif denial is None and (
        authority.matched_grant_id is None or authority.matched_grant_status != "active"
    ):
        denial = AuthorizationDenialCode.PERMISSION_NOT_GRANTED
    if denial is not None:
        return denial, None, None, None
    return (
        None,
        MatchedAuthorityKind.PROJECT_ROLE_GRANT,
        authority.matched_grant_id,
        authority.scope_project_id,
    )
