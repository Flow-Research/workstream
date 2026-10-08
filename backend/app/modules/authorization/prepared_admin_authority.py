"""Lock human administration authority before the kernel takes product custody."""

from app.modules.authorization.artifact_project_authority import lock_project_role_mutation_principals
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain import adapter_bindings, contribution_policies
from app.modules.authorization.domain.action_groups import PROJECT_SCOPED_ADMIN_MUTATIONS
from app.modules.authorization.runtime import (
    AuthorizationDenialCode, HumanAuthorizationContext, PreparedAuthorizationUnsupported,
    PreparedAuthorityScopeKind,
)
from app.modules.authorization.schemas import AdminRole


async def lock_admin_mutation_authority(repository, context, scope, action_id, permission_id, locked_context):
    """Preserve control, principal and grant order for the kernel's admin mutations."""
    if not isinstance(context, HumanAuthorizationContext):
        raise PreparedAuthorizationUnsupported(
            AuthorizationDenialCode.PERMISSION_NOT_GRANTED
        )
    if scope.kind not in {PreparedAuthorityScopeKind.SYSTEM, PreparedAuthorityScopeKind.PROJECT}:
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED)
    if scope.kind is PreparedAuthorityScopeKind.PROJECT and action_id not in PROJECT_SCOPED_ADMIN_MUTATIONS:
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED)
    await repository.lock_control()
    if action_id in {ActionId.PROJECT_ROLE_GRANT_ISSUE, ActionId.PROJECT_ROLE_GRANT_REVOKE}:
        locked = await lock_project_role_mutation_principals(
            repository, context, scope, action_id,
        )
    else:
        locked = await repository.lock_request_actor(
            context.identity_link_id, context.actor_profile_id,
            **({"preserve_foreign_key_reads": True}
               if action_id is ActionId.REVIEW_LIFECYCLE_ACTIVATION_MANAGE else {}),
        )
    context = locked_context(locked, context)
    if action_id is ActionId.PROJECT_ROLE_GRANT_REVOKE and scope.grant_id is None:
        raise PreparedAuthorizationUnsupported(
            AuthorizationDenialCode.RESOURCE_GUARD_DENIED
        )
    grant = await repository.find_effective_grant(
        context.actor_profile_id,
        permission_id,
        scope_project_id=scope.project_id,
        system_scope_only=scope.project_id is None,
        for_update=True,
        **({"allowed_roles": (AdminRole.OPERATOR,)} if action_id is ActionId.REVIEW_LIFECYCLE_ACTIVATION_MANAGE else {}),
        **adapter_bindings.finance_authority_grant_filters(action_id),
        **contribution_policies.policy_finance_grant_filters(action_id),
    )
    if grant is None:
        raise PreparedAuthorizationUnsupported(
            AuthorizationDenialCode.PERMISSION_NOT_GRANTED
        )
    return context, grant
