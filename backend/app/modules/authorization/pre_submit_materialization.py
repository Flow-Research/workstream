"""Prepared binding parser for pre-submit checker materialization."""

from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.authorization.runtime import PreSubmitCheckerInputPreparationContext


def parse_materialization_binding(raw: dict, invalid_error) -> tuple[dict, str]:
    try:
        value = dict(raw)
        for field in (
            "resource_id", "task_id", "assignment_id", "project_id", "guide_id",
            "source_snapshot_id", "submission_artifact_policy_id", "checker_policy_id",
            "prepared_generation_id",
        ):
            value[field] = UUID(str(value[field]))
        resource = PreSubmitCheckerInputPreparationContext.model_validate(value)
    except (KeyError, TypeError, ValueError) as exc:
        raise invalid_error("invalid prepared authorization handle") from exc
    context = resource.model_dump(mode="json")
    return context, canonical_json_hash({"pre_submit_checker_input_preparation": context})


def initialize_artifact_bindings() -> tuple[None, None, None, None, None, None]:
    return None, None, None, None, None, None
