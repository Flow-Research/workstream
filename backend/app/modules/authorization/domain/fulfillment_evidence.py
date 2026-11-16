"""Disjoint AUTH resources for original-bound fulfillment evidence."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, UUID7, model_validator

from app.core.hashing import canonical_json_hash
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
