"""Parse content-free guide commitments for the shared prepared-authority owner."""

from collections.abc import Mapping
from uuid import UUID

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid


def parse_prepared_guide_mutation(action: ActionId, request: Mapping[str, object]) -> dict:
    """Bind existing guide selectors and require exact create-time example facts."""
    if action not in {
        ActionId.PROJECT_GUIDE_CREATE, ActionId.PROJECT_GUIDE_UPDATE,
        ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE,
    }:
        return {}
    try:
        project = UUID(str(request["project_id"]))
        guide = UUID(str(request["guide_id"]))
        target = UUID(str(request["target_resource_id"]))
        operation = UUID(str(request["operation_id"]))
        if (action is ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE) == (target == guide):
            raise ValueError("guide target shape mismatch")
        result = {
            "guide_mutation_project_id": project, "guide_mutation_guide_id": guide,
            "guide_mutation_target_resource_id": target, "guide_mutation_operation_id": operation,
        }
        if action is ActionId.PROJECT_GUIDE_CREATE:
            digest, examples_hash, count = (
                request["request_digest"], request["task_examples_hash"], request["task_examples_count"],
            )
            if not isinstance(digest, str) or not isinstance(examples_hash, str) or type(count) is not int or not 1 <= count <= 100:
                raise ValueError("invalid guide example commitment")
            result.update(
                guide_create_request_digest=digest, guide_create_task_examples_hash=examples_hash,
                guide_create_task_examples_count=count,
            )
        return result
    except (KeyError, TypeError, ValueError) as exc:
        raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle") from exc
