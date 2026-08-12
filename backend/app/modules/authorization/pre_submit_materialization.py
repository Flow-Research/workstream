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


def parse_submission_binding(raw: dict, invalid_error, parser) -> tuple:
    return parser(raw, invalid_error)


def parse_project_create_binding(raw: dict, invalid_error):
    try:
        operation_id = UUID(str(raw["operation_id"]))
        project_id = UUID(str(raw["project_id"]))
        generation = raw["operation_generation"]
    except (KeyError, TypeError, ValueError) as exc:
        raise invalid_error("invalid prepared authorization handle") from exc
    if type(generation) is not int or generation < 1 or operation_id == project_id:
        raise invalid_error("invalid prepared authorization handle")
    return operation_id, project_id, generation
