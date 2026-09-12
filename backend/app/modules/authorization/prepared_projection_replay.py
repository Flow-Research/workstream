"""Exact replay validation for prepared guide-compilation projections."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.modules.authorization.catalogue import ACTION_BY_ID, ActionId
from app.modules.authorization.domain.guide_compilation_projections import (
    ProjectGuideProjectionResourceContext,
    parse_projection_prepare,
    projection_prepare_matches, projection_context_matches,
    projection_replay_event_matches,
)
from app.modules.authorization.domain.project_setup_finalization import (
    ProjectSetupFinalizationResourceContext, finalization_context_matches, finalization_replay_event_matches, parse_finalization_prepare,
)
from app.modules.authorization.domain.prepared_compilation import parse_prepared_compilation
from app.modules.authorization.domain.prepared_service import project_setup_resource_matches
from app.modules.authorization.runtime import (
    AuthorizationDenialCode,
    AuthorizationResourceContext, AuthorizationContext, PreparedAuthorityScope,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
)


def parse_setup_bindings(
    action_id: ActionId, caller_input: PreparedAuthorizationInput,
    scope: PreparedAuthorityScope, context: AuthorizationContext,
) -> dict:
    """Parse exact setup-family bindings, including compilation request custody."""
    request_value = caller_input.request_value
    if not isinstance(request_value, dict):
        raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
    try:
        projection = parse_projection_prepare(action_id, request_value)
        finalization = parse_finalization_prepare(
            action_id, request_value,
            actor_profile_id=context.actor_profile_id, identity_link_id=context.identity_link_id,
            service_identity=getattr(context, "service_identity", None),
            request_id=context.request_id, correlation_id=context.correlation_id,
            scope_project_id=scope.project_id, idempotency_key=caller_input.idempotency_key,
        )
    except (TypeError, ValueError) as exc:
        raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle") from exc
    compilation = {} if projection else parse_prepared_compilation(action_id, request_value)
    return {**projection, **compilation, "setup_finalization_prepare_context": finalization}


def setup_context_matches(binding: Any, resource: AuthorizationResourceContext) -> bool:
    """Require mutually exclusive exact preparation/resource kinds at consumption."""
    return projection_context_matches(binding.guide_projection_prepare_context, resource) and (
        finalization_context_matches(binding.setup_finalization_prepare_context, resource)
    )


async def validate_projection_replay(
    owner: Any,
    issuance: Any,
    expected_action_id: ActionId,
    caller_input: PreparedAuthorizationInput,
    resource: AuthorizationResourceContext,
    stored_decision_id: UUID,
) -> None:
    """Freshly validate one exact stored allow without new consumption."""
    invalid = PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
    if expected_action_id is not issuance.binding.action_id:
        raise invalid
    if owner._binding(expected_action_id, caller_input, issuance.binding.scope) != issuance.binding:
        raise invalid
    if owner._root_transaction() is not issuance.transaction:
        raise invalid
    if owner._scope_from_resource(expected_action_id, resource) != issuance.binding.scope:
        raise invalid
    if isinstance(resource, ProjectSetupFinalizationResourceContext):
        if not finalization_context_matches(issuance.binding.setup_finalization_prepare_context, resource):
            raise invalid
        replay_event_matches = finalization_replay_event_matches
    elif isinstance(resource, ProjectGuideProjectionResourceContext):
        if not projection_prepare_matches(issuance.binding.guide_projection_prepare_context, resource):
            raise invalid
        replay_event_matches = projection_replay_event_matches
    else:
        raise invalid
    if (
        project_setup_resource_matches(
            expected_action_id, resource, issuance.authority.scope_project_id
        )
        is not True
    ):
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.RESOURCE_GUARD_DENIED)
    event = await owner._authorization._audit.get_authority_event(stored_decision_id)
    action = ACTION_BY_ID[expected_action_id]
    if not replay_event_matches(
        event,
        actor_profile_id=owner._context.actor_profile_id,
        action_id=expected_action_id,
        permission_id=action.permission_id.value,
        request_id=owner._context.request_id,
        correlation_id=owner._context.correlation_id,
        resource=resource,
    ):
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.RESOURCE_GUARD_DENIED)
