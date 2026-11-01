"""Exact TASK-owned facts bound by the existing fixed-service PREP kernel."""

import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.modules.authorization.catalogue import ActionId
from app.modules.tasks.api.assignment_invalidation import AssignmentInvalidationAuthorityFacts


class AssignmentInvalidationResourceContext(BaseModel):
    """Separate service effect facts from human claim authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["task_authority"] = "task_authority"
    resource_id: UUID
    scope_project_id: UUID
    facts: AssignmentInvalidationAuthorityFacts

    @model_validator(mode="after")
    def validate_identity(self):
        facts = AssignmentInvalidationAuthorityFacts.model_validate(self.facts.model_dump())
        if (
            self.resource_id != facts.target.task_id
            or self.scope_project_id != facts.target.project_id
            or facts.task_status != "in_progress"
        ):
            raise ValueError("invalid assignment reconciliation facts")
        return self


def assignment_invalidation_resource(facts):
    """Revalidate constructed or copied owner values before accepting authority."""
    facts = AssignmentInvalidationAuthorityFacts.model_validate(facts.model_dump())
    return AssignmentInvalidationResourceContext(
        resource_id=facts.target.task_id, scope_project_id=facts.target.project_id, facts=facts,
    )


def parse_assignment_invalidation_binding(action, request, invalid_error):
    """Preserve every exact fact in the canonical transaction-bound handle."""
    if action is not ActionId.TASK_ASSIGNMENT_AUTHORITY_RECONCILE:
        return None
    try:
        return AssignmentInvalidationResourceContext.model_validate_json(json.dumps(dict(request)))
    except (TypeError, ValueError) as exc:
        raise invalid_error("invalid assignment reconciliation authority") from exc
