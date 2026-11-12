"""Exact reservation commitment; existing project Submitter authority decides."""
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.authorization.catalogue import ActionId


class _IntakeReservationSelectors(BaseModel):
    """A source-custody reservation, never a prepared artifact or Submission."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")
    resource_id: UUID
    scope_project_id: UUID
    task_id: UUID
    assignment_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    idempotency_key: UUID
    metadata_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @field_validator("resource_id")
    @classmethod
    def operation_record(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("intake operation must be a generated UUIDv7 record")
        return value



class IntakeReservationPreflightResourceContext(_IntakeReservationSelectors):
    """Selector-only preflight; cannot become a prepared reservation handle."""
    resource_type: Literal["submission_intake_preflight"] = "submission_intake_preflight"


class IntakeReservationResourceContext(_IntakeReservationSelectors):
    """Complete locked reservation facts used only for prepare and consume."""
    resource_type: Literal["submission_intake_reservation"] = "submission_intake_reservation"
    locked_context_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    task_status: Literal["in_progress", "needs_revision"]


def intake_preflight_matches(caller_input, resource, scope) -> bool:
    """Match strict partial selectors and exact project/key without issuing custody."""
    from app.modules.authorization.runtime import PreparedAuthorityScopeKind
    if type(resource) is not IntakeReservationPreflightResourceContext:
        return False
    try:
        parsed = IntakeReservationPreflightResourceContext.model_validate_json(
            json.dumps(dict(caller_input.request_value)))
        return (parsed == resource and caller_input.idempotency_key == parsed.idempotency_key
                and scope.kind is PreparedAuthorityScopeKind.PROJECT
                and scope.project_id == parsed.scope_project_id)
    except (TypeError, ValueError):
        return False


def parse_intake_binding(action, request, key, invalid_error):
    """Bind every supplied field and caller key using the strict reservation schema."""
    if action is not ActionId.SUBMISSION_INTAKE_RESERVE:
        return None
    try:
        resource = IntakeReservationResourceContext.model_validate_json(json.dumps(dict(request)))
        if resource.idempotency_key != key:
            raise ValueError("intake key differs from prepared binding")
        return resource
    except (TypeError, ValueError) as exc:
        raise invalid_error("invalid prepared intake authorization") from exc
