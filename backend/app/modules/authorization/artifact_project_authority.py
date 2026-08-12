"""Narrow kernel rules for human project-scoped ART actions."""

from __future__ import annotations

from app.modules.authorization.catalogue import ActionAvailability
from app.modules.authorization.runtime import (
    AuthorizationDenialCode,
    HumanAuthorizationContext,
    MatchedAuthorityKind,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScopeKind,
    SubmissionBundlePreparationResourceContext,
)


async def lock_guide_ingest_authority(repository, context, scope, permission_id, locked_context):
    """Lock the exact human identity and project-scoped guide-ingest grant."""
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
        for_update=True,
    )
    if grant is None:
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.PERMISSION_NOT_GRANTED)
    return context, grant


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
    elif denial is None and not isinstance(resource, SubmissionBundlePreparationResourceContext):
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
