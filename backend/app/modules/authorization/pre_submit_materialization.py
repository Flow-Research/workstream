"""Prepared binding parser for pre-submit checker materialization."""

from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.resource_digest import authorization_resource_digest
from app.modules.authorization.runtime import PreSubmitCheckerInputPreparationContext
from app.modules.authorization.submission_consumption import parse_consumption_binding
from app.modules.authorization.submission_preparation import (
    parse_submission_preparation_or_invalid, submission_preparation_binding_fields,
)


def parse_materialization_binding(raw: dict, invalid_error) -> tuple[dict, str]:
    """Parse and digest exact checker-materialization preparation facts."""
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


def parse_prepared_artifact_bindings(action_id: ActionId, raw: dict, invalid_error) -> dict:
    """Bind only the exact artifact facts owned by the selected prepared action."""
    fields = {}
    if action_id is ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE:
        context, digest = parse_materialization_binding(raw, invalid_error)
        fields.update(exact_artifact_context=context, exact_artifact_resource_digest=digest)
    consumption = parse_consumption_binding(action_id, raw, invalid_error)
    if consumption is not None:
        fields.update(
            exact_artifact_context=consumption.model_dump(mode="json"),
            exact_artifact_resource_digest=authorization_resource_digest(consumption),
        )
    if action_id is ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE:
        fields.update(submission_preparation_binding_fields(
            parse_submission_preparation_or_invalid(raw, invalid_error),
        ))
    return fields


def parse_project_create_binding(raw: dict, invalid_error):
    """Parse and validate exact project-create operation selectors."""
    try:
        operation_id = UUID(str(raw["operation_id"]))
        project_id = UUID(str(raw["project_id"]))
        generation = raw["operation_generation"]
    except (KeyError, TypeError, ValueError) as exc:
        raise invalid_error("invalid prepared authorization handle") from exc
    if type(generation) is not int or generation < 1 or operation_id == project_id:
        raise invalid_error("invalid prepared authorization handle")
    return operation_id, project_id, generation
