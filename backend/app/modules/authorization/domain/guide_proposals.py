"""Exact unified proposal resources and request-local preparation selectors."""

from types import MappingProxyType
from dataclasses import fields
import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.modules.authorization.api.guide_proposal_review import (
    GuideProposalAuthorizationFacts,
    GuideProposalAuthorizationLocator,
)
from app.modules.authorization.catalogue import ActionId, GUIDE_PROPOSAL_ACTION_IDS

_RESOURCE_KINDS = {
    ActionId.PROJECT_GUIDE_COMPILATION_REVIEW_PACKAGE_READ: "project_guide_compilation_review_package",
    ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_APPROVE: "project_submission_artifact_policy_mutation",
    ActionId.PROJECT_GUIDE_COMPILATION_CORRECTION_REQUEST: "project_guide_compilation_correction",
}
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")


def validate_locator(locator):
    """Require parsed selectors for one closed action, never a lookalike object."""
    if type(locator) is not GuideProposalAuthorizationLocator:
        raise ValueError("invalid proposal locator")
    for field in fields(locator):
        value = getattr(locator, field.name)
        if field.name == "action_id":
            if value not in GUIDE_PROPOSAL_ACTION_IDS:
                raise ValueError("invalid proposal action")
        elif not isinstance(value, UUID):
            raise ValueError("invalid proposal selector")
    return locator


def proposal_selectors(locator):
    """Serialize the exact narrow preparation binding."""
    validate_locator(locator)
    return {field.name: str(getattr(locator, field.name)) for field in fields(locator)}


class GuideProposalResourceContext(BaseModel):
    """Locked product commitments; AUTH validates custody, not policy content."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    resource_type: str
    resource_id: UUID
    scope_project_id: UUID
    facts: GuideProposalAuthorizationFacts

    @model_validator(mode="after")
    def validate_identity(self):
        """Reject partial tuples, noncanonical hashes and sibling resource identities."""
        f = self.facts
        if type(f) is not GuideProposalAuthorizationFacts:
            raise ValueError("invalid proposal facts")
        locator = validate_locator(f.locator)
        for name in ("finalization_id", "setup_run_id"):
            if not isinstance(getattr(f, name), UUID):
                raise ValueError("invalid proposal identity")
        for name in ("artifact_policy_id", "current_approval_operation_id"):
            if getattr(f, name) is not None and not isinstance(getattr(f, name), UUID):
                raise ValueError("invalid proposal identity")
        if type(f.setup_generation) is not int or f.setup_generation < 1:
            raise ValueError("invalid proposal generation")
        for name in (
            "target_digest",
            "request_digest",
            "output_digest",
            "current_approval_output_digest",
        ):
            value = getattr(f, name)
            if name == "current_approval_output_digest" and value is None:
                continue
            if not isinstance(value, str) or not _HASH.fullmatch(value):
                raise ValueError("invalid proposal digest")
        if (f.current_approval_operation_id is None) != (f.current_approval_output_digest is None):
            raise ValueError("partial proposal predecessor")
        action = ActionId(locator.action_id)
        expected_id = (
            f.artifact_policy_id
            if action is ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_APPROVE
            else locator.compilation_id
            if action is ActionId.PROJECT_GUIDE_COMPILATION_REVIEW_PACKAGE_READ
            else locator.operation_id
        )
        if (
            expected_id is None
            or self.resource_id != expected_id
            or self.scope_project_id != locator.project_id
            or self.resource_type != _RESOURCE_KINDS[action]
        ):
            raise ValueError("proposal resource identity mismatch")
        return self


GUIDE_PROPOSAL_RESOURCE_BY_ACTION = MappingProxyType(
    dict.fromkeys(GUIDE_PROPOSAL_ACTION_IDS, GuideProposalResourceContext)
)


def proposal_resource(facts):
    """Build the canonical exact resource from public owner-locked commitments."""
    locator = validate_locator(facts.locator)
    action = ActionId(locator.action_id)
    resource_id = (
        facts.artifact_policy_id
        if action is ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_APPROVE
        else locator.compilation_id
        if action is ActionId.PROJECT_GUIDE_COMPILATION_REVIEW_PACKAGE_READ
        else locator.operation_id
    )
    return GuideProposalResourceContext(
        resource_type=_RESOURCE_KINDS[action],
        resource_id=resource_id,
        scope_project_id=locator.project_id,
        facts=facts,
    )


def parse_proposal_prepare(action, caller_input, scope, context):
    """Bind actual authenticated request and private PREP selectors before product locks."""
    if action not in GUIDE_PROPOSAL_ACTION_IDS:
        return None
    value = dict(caller_input.request_value)
    parsed = {name: (raw if name == "action_id" else UUID(str(raw))) for name, raw in value.items()}
    locator = GuideProposalAuthorizationLocator(**parsed)
    validate_locator(locator)
    if (
        locator.action_id != action
        or locator.actor_profile_id != context.actor_profile_id
        or locator.identity_link_id != context.identity_link_id
        or locator.request_id != context.request_id
        or locator.operation_id != context.correlation_id
        or locator.project_id != scope.project_id
        or locator.operation_id != caller_input.idempotency_key
    ):
        raise ValueError("proposal preparation differs from custody")
    return proposal_selectors(locator)


def proposal_matches(binding, resource):
    """Reject missing bindings and sibling contexts in both substitution directions."""
    exact = type(resource) is GuideProposalResourceContext
    if exact != (binding is not None):
        return False
    if not exact:
        return True
    try:
        resource.validate_identity()
        return binding == proposal_selectors(resource.facts.locator)
    except (TypeError, ValueError):
        return False
