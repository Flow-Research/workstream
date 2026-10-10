"""Exact routing values for canonical PREP; construction grants no authority."""

import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.authorization.acceptance_source_contracts import routing_source_commitment
from app.modules.authorization.api.acceptance_source import acceptance_source_commitment_digest
from app.modules.authorization.catalogue import ActionId
from app.modules.outbox.api import OutboxClaim
from app.modules.tasks.api.accepted_effects import TaskAcceptedEffectsRequest
from app.modules.tasks.api.post_submit_routing import (
    TaskPostSubmitSourceProposal,
    TaskRoutingRequestFacts,
)

ROUTE = ActionId.TASK_POST_SUBMIT_ROUTE


class _RoutingValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")


class HumanAdmissionConsequence(_RoutingValue):
    """Bind TASK's transition; REV queue admission belongs to its later consumer."""

    kind: Literal["human_admission"] = "human_admission"
    expected_task_status: Literal["evaluation_pending"] = "evaluation_pending"
    target_task_status: Literal["review_pending"] = "review_pending"


class AutomatedAcceptanceConsequence(_RoutingValue):
    """Bind the exact shared acceptance effects and original authorized generation."""

    kind: Literal["final_acceptance"] = "final_acceptance"
    task_effects: TaskAcceptedEffectsRequest
    authorized_lifecycle_generation: int = Field(gt=0, le=9_223_372_036_854_775_807)


class PostSubmitRoutingResourceContext(_RoutingValue):
    """Closed, detached facts awaiting owner verification in one transaction."""

    resource_type: Literal["task_post_submit_routing_manifest"] = "task_post_submit_routing_manifest"
    resource_id: UUID
    scope_project_id: UUID
    router_actor_id: UUID
    router_identity_link_id: UUID
    request: TaskRoutingRequestFacts
    source: TaskPostSubmitSourceProposal
    claim: OutboxClaim
    consequence: Annotated[HumanAdmissionConsequence | AutomatedAcceptanceConsequence, Field(discriminator="kind")]

    @model_validator(mode="after")
    def validate_identity(self):
        # Reconstruct nested owner values: model_copy/model_construct cannot bypass
        # their validators merely by supplying an existing instance.
        request = TaskRoutingRequestFacts.model_validate(self.request.model_dump())
        source = TaskPostSubmitSourceProposal.model_validate(self.source.model_dump())
        claim = OutboxClaim.model_validate(self.claim.model_dump())
        if not (
            self.resource_type == "task_post_submit_routing_manifest"
            and self.resource_id == request.routing_manifest_id == source.id
            and self.scope_project_id == request.project_id == source.project_id == claim.project_id
            and claim.event_id == request.completion_event_id == source.completion_event_id
            and request.evaluation_request_digest == source.request_digest
        ):
            raise ValueError("routing resource identity differs")
        for field in (
            "task_id", "submission_id", "submission_version", "checker_run_id",
            "evaluation_request_id", "evaluation_generation", "result_id", "result_digest",
            "routing_recommendation",
        ):
            if getattr(request, field) != getattr(source, field):
                raise ValueError("routing request source differs")
        if source.human_review_required:
            if type(self.consequence) is not HumanAdmissionConsequence:
                raise ValueError("routing consequence differs from review policy")
            HumanAdmissionConsequence.model_validate(self.consequence.model_dump())
        else:
            if type(self.consequence) is not AutomatedAcceptanceConsequence:
                raise ValueError("routing consequence differs from review policy")
            consequence = AutomatedAcceptanceConsequence.model_validate(self.consequence.model_dump())
            effects = TaskAcceptedEffectsRequest.model_validate(consequence.task_effects.model_dump())
            if effects.final_acceptance_id.version != 7:
                raise ValueError("routing acceptance requires UUIDv7 identity")
            if effects.expected_task_status != "evaluation_pending":
                raise ValueError("routing acceptance source state differs")
            for field in (
                "project_id", "task_id", "assignment_id", "submission_id", "submission_version",
                "contributor_id", "contribution_policy_version_id", "content_id", "content_sha256",
            ):
                if getattr(effects, field) != getattr(source, field):
                    raise ValueError("routing acceptance identity differs")
        return self


def post_submit_routing_prepare_values(request: TaskRoutingRequestFacts) -> dict:
    """Bind the complete reserved request, including its retained database time."""
    checked = TaskRoutingRequestFacts.model_validate(request.model_dump())
    return {"routing_request": checked.model_dump(mode="json")}


def parse_post_submit_routing_prepare(action, values, invalid_error):
    """Parse this action's one request field without introducing another DTO."""
    if action is not ROUTE:
        return None
    try:
        if set(values) != {"routing_request"}:
            raise ValueError("invalid fields")
        return TaskRoutingRequestFacts.model_validate_json(json.dumps(values["routing_request"]))
    except (ValueError, TypeError, KeyError) as error:
        raise invalid_error("invalid prepared routing request") from error


def post_submit_routing_prepare_matches(prepared, resource) -> bool:
    """Match every reserved selector and operation before canonical consumption."""
    if type(resource) is not PostSubmitRoutingResourceContext:
        return False
    resource.validate_identity()
    return prepared == resource.request


def post_submit_routing_resource_digest(resource: PostSubmitRoutingResourceContext) -> str:
    """Commit exact source, claim and consequence without asserting stored custody."""
    resource.validate_identity()
    source = routing_source_commitment(
        resource.source, route_operation_id=resource.request.route_operation_id,
        route_request_digest=resource.request.route_request_digest,
    )
    return canonical_json_hash(
        {
            "domain": "workstream.authorization.task_post_submit_route.v0.1",
            "resource_type": resource.resource_type,
            "resource_id": str(resource.resource_id),
            "project_id": str(resource.scope_project_id),
            "router_actor_id": str(resource.router_actor_id),
            "router_identity_link_id": str(resource.router_identity_link_id),
            "request": post_submit_routing_prepare_values(resource.request),
            "source_commitment_digest": acceptance_source_commitment_digest(source),
            "claim": resource.claim.model_dump(mode="json"),
            "consequence": resource.consequence.model_dump(mode="json"),
        }
    )
