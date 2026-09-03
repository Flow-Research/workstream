"""Exact replay validation for prepared guide-compilation projections."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.modules.authorization.catalogue import ACTION_BY_ID, ActionId
from app.modules.authorization.domain.guide_compilation_projections import (
    ProjectGuideProjectionResourceContext,
    parse_projection_prepare,
    projection_prepare_matches,
    projection_replay_event_matches,
)
from app.modules.authorization.domain.prepared_compilation import parse_prepared_compilation
from app.modules.authorization.domain.prepared_service import project_setup_resource_matches
from app.modules.authorization.runtime import (
    AuthorizationDenialCode,
    AuthorizationResourceContext,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
)


def parse_projection_bindings(action_id: ActionId, request_value: dict) -> tuple[dict, dict]:
    """Return mutually exclusive projection and legacy compilation bindings."""
    try:
        projection = parse_projection_prepare(action_id, request_value)
    except ValueError as exc:
        raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle") from exc
    legacy = {} if projection else parse_prepared_compilation(action_id, request_value)
    return projection, legacy


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
    if not isinstance(resource, ProjectGuideProjectionResourceContext) or not (
        projection_prepare_matches(issuance.binding.guide_projection_prepare_context, resource)
    ):
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
    if not projection_replay_event_matches(
        event,
        actor_profile_id=owner._context.actor_profile_id,
        action_id=expected_action_id,
        permission_id=action.permission_id.value,
        request_id=owner._context.request_id,
        correlation_id=owner._context.correlation_id,
        resource=resource,
    ):
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.RESOURCE_GUARD_DENIED)
