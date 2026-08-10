"""Prepared-capability parsing and equality for guide compilation."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.guide_compilation import (
    CompilationResourceContext,
    ProjectGuideCompilationExecuteResourceContext,
    ProjectGuideCompilationRequestResourceContext,
)
from app.modules.authorization.runtime import authorization_resource_digest
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid

_CONTEXT_BY_ACTION = {
    ActionId.PROJECT_GUIDE_COMPILATION_REQUEST: ProjectGuideCompilationRequestResourceContext,
    ActionId.PROJECT_GUIDE_COMPILATION_EXECUTE: ProjectGuideCompilationExecuteResourceContext,
}
_UUID_FIELDS = (
    "resource_id",
    "scope_project_id",
    "guide_id",
    "source_snapshot_id",
    "setup_run_id",
    "operation_id",
    "request_id",
    "idempotency_key",
    "attempt_id",
    "provider_idempotency_key",
)


def parse_prepared_compilation(
    action_id: ActionId, request_value: Mapping[str, object]
) -> dict[str, object]:
    """Parse exact compilation facts when the action belongs to this capability."""
    context_type = _CONTEXT_BY_ACTION.get(action_id)
    if context_type is None:
        return {}
    try:
        value = dict(request_value)
        for field in _UUID_FIELDS:
            if field in value:
                value[field] = UUID(str(value[field]))
        resource = context_type.model_validate(value)
    except (TypeError, ValueError) as exc:
        raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle") from exc
    return {
        "guide_compilation_context": resource.model_dump(mode="json"),
        "guide_compilation_resource_digest": authorization_resource_digest(resource),
    }


def prepared_compilation_matches(
    context: dict | None,
    digest: str | None,
    resource: CompilationResourceContext,
) -> bool:
    """Require exact final facts and digest equality."""
    return context == resource.model_dump(mode="json") and (
        digest == authorization_resource_digest(resource)
    )
