"""Disjoint AUTH resources for original-bound fulfillment evidence."""

import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, UUID7, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.authorization.catalogue import ActionId
from app.modules.compensation.api.fulfillment_evidence import (
    FulfillmentEvidenceAuthorityFacts, FulfillmentExceptionAuthorityFacts,
    FulfillmentReportAuthorityFacts, FulfillmentReportLookupAuthorityFacts,
    FulfillmentSourceReadAuthorityFacts,
)


class _Resource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")
    resource_id: UUID7
    scope_project_id: UUID7


def _exact_target(resource, project_id, resource_id):
    if resource.scope_project_id != project_id or resource.resource_id != resource_id:
        raise ValueError("fulfillment resource target differs from source facts")
    return resource


class FulfillmentReportResourceContext(_Resource):
    resource_type: Literal["compensation_fulfillment_report"] = "compensation_fulfillment_report"
    facts: FulfillmentReportAuthorityFacts

    @model_validator(mode="after")
    def exact_target(self):
        return _exact_target(self, self.facts.project_id, self.facts.external_event_id)


class FulfillmentExceptionResourceContext(_Resource):
    resource_type: Literal["compensation_fulfillment_exception"] = "compensation_fulfillment_exception"
    facts: FulfillmentExceptionAuthorityFacts

    @model_validator(mode="after")
    def exact_target(self):
        return _exact_target(self, self.facts.project_id, self.facts.exception_event_id)


class FulfillmentSourceReadResourceContext(_Resource):
    resource_type: Literal["compensation_fulfillment_evidence"] = "compensation_fulfillment_evidence"
    facts: FulfillmentSourceReadAuthorityFacts

    @model_validator(mode="after")
    def exact_target(self):
        return _exact_target(self, self.facts.project_id, self.facts.award_id)


class FulfillmentReportLookupResourceContext(_Resource):
    resource_type: Literal["compensation_fulfillment_report_lookup"] = "compensation_fulfillment_report_lookup"
    facts: FulfillmentReportLookupAuthorityFacts

    @model_validator(mode="after")
    def exact_target(self):
        return _exact_target(self, self.facts.project_id, self.facts.external_event_id)


FulfillmentEvidenceResourceContext = (
    FulfillmentReportResourceContext | FulfillmentExceptionResourceContext
    | FulfillmentSourceReadResourceContext | FulfillmentReportLookupResourceContext
)
_RESOURCE_TYPES = (
    FulfillmentReportResourceContext, FulfillmentExceptionResourceContext,
    FulfillmentSourceReadResourceContext, FulfillmentReportLookupResourceContext,
)


def fulfillment_evidence_resource(facts: FulfillmentEvidenceAuthorityFacts) -> FulfillmentEvidenceResourceContext:
    """Construct only one of the four closed resource identities from exact facts."""
    if type(facts) is FulfillmentReportAuthorityFacts:
        return FulfillmentReportResourceContext(
            resource_id=facts.external_event_id, scope_project_id=facts.project_id, facts=facts,
        )
    if type(facts) is FulfillmentExceptionAuthorityFacts:
        return FulfillmentExceptionResourceContext(
            resource_id=facts.exception_event_id, scope_project_id=facts.project_id, facts=facts,
        )
    if type(facts) is FulfillmentSourceReadAuthorityFacts:
        return FulfillmentSourceReadResourceContext(
            resource_id=facts.award_id, scope_project_id=facts.project_id, facts=facts,
        )
    if type(facts) is FulfillmentReportLookupAuthorityFacts:
        return FulfillmentReportLookupResourceContext(
            resource_id=facts.external_event_id, scope_project_id=facts.project_id, facts=facts,
        )
    raise ValueError("unsupported fulfillment evidence facts")


def fulfillment_evidence_resource_digest(resource: FulfillmentEvidenceResourceContext) -> str:
    """Bind type, project, target, original source and exact reporter/event facts."""
    if type(resource) not in _RESOURCE_TYPES:
        raise ValueError("unsupported fulfillment evidence resource")
    checked = type(resource).model_validate(resource.model_dump())
    return canonical_json_hash({
        "domain": "workstream.authorization.compensation_fulfillment.v0.1",
        "resource": checked.model_dump(mode="json"),
    })


def fulfillment_evidence_principal_matches(
    resource: FulfillmentEvidenceResourceContext, actor_profile_id: UUID, identity_link_id: UUID,
) -> bool:
    """Detached source fields never substitute for the actual request principal."""
    return type(resource) in _RESOURCE_TYPES and (
        resource.facts.reporter_actor_id == actor_profile_id
        and resource.facts.binding_actor_id == actor_profile_id
        and resource.facts.reporter_identity_link_id == identity_link_id
    )


FULFILLMENT_EVIDENCE_RESOURCES_BY_ACTION = {
    ActionId.COMPENSATION_FULFILLMENT_REPORT: (FulfillmentReportResourceContext,),
    ActionId.COMPENSATION_FULFILLMENT_EXCEPTION_REPORT: (FulfillmentExceptionResourceContext,),
    ActionId.COMPENSATION_FULFILLMENT_SOURCE_READ: (
        FulfillmentSourceReadResourceContext, FulfillmentReportLookupResourceContext,
    ),
}
FULFILLMENT_EVIDENCE_ACTIONS = frozenset(FULFILLMENT_EVIDENCE_RESOURCES_BY_ACTION)


def parse_fulfillment_evidence_binding(action, request, invalid_error):
    """Parse exact closed resource JSON only for the three fulfillment actions."""
    expected = FULFILLMENT_EVIDENCE_RESOURCES_BY_ACTION.get(action)
    if expected is None:
        return None
    try:
        value = dict(request)
        resource_type = value.get("resource_type")
        for resource in expected:
            if resource.model_fields["resource_type"].default == resource_type:
                return resource.model_validate_json(json.dumps(value))
    except (TypeError, ValueError):
        pass
    raise invalid_error("invalid fulfillment evidence authority") from None


def fulfillment_evidence_action_matches(action, resource, project_id, actor_id, link_id):
    """Require exact action family, project and actual request principal."""
    return (
        type(resource) in FULFILLMENT_EVIDENCE_RESOURCES_BY_ACTION.get(action, ())
        and resource.scope_project_id == project_id
        and fulfillment_evidence_principal_matches(resource, actor_id, link_id)
    )
