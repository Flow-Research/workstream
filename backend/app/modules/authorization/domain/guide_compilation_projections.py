"""Exact AUTH resource custody for compilation-derived projections."""

from __future__ import annotations

from dataclasses import asdict, fields
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.authorization.api.project_guide_projections import (
    ArtifactPolicyProjectionFacts,
    GuideSufficiencyProjectionFacts,
    ProjectGuideProjectionIdentity,
    ProjectGuideProjectionLocator,
    artifact_policy_projection_facts_digest,
    guide_sufficiency_projection_facts_digest,
    projection_authority_digest,
)
from app.modules.authorization.catalogue import ActionId

ProjectionComponent = Literal["guide_sufficiency", "submission_artifact_policy"]
ProjectionResourceType = Literal[
    "project_guide_sufficiency_projection",
    "project_submission_artifact_policy_projection",
]

_STRICT = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProjectGuideProjectionPrepareContext(BaseModel):
    """Immutable locator and identity bound when projection authority is prepared."""

    model_config = _STRICT

    binding_kind: Literal["project_guide_projection"] = "project_guide_projection"
    component: ProjectionComponent
    resource_type: ProjectionResourceType
    project_id: UUID
    attempt_id: UUID
    operation_id: UUID
    correlation_id: UUID
    output_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    service_identity: Literal["workstream.project.setup"]


class ProjectGuideProjectionResourceContext(BaseModel):
    """Complete final facts for one exact deterministic projection."""

    model_config = _STRICT

    resource_type: ProjectionResourceType
    resource_id: UUID
    scope_project_id: UUID
    component: ProjectionComponent
    operation_id: UUID
    correlation_id: UUID
    output_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    service_identity: Literal["workstream.project.setup"]
    facts_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    projection_facts: dict[str, object]

    @model_validator(mode="after")
    def require_component_identity(self):
        """Keep component, resource, operation, and final fact identities exact."""
        expected_resource = (
            "project_guide_sufficiency_projection"
            if self.component == "guide_sufficiency"
            else "project_submission_artifact_policy_projection"
        )
        if self.resource_type != expected_resource or self.resource_id != self.operation_id:
            raise ValueError("projection resource identity is inconsistent")
        facts_type = (
            GuideSufficiencyProjectionFacts
            if self.component == "guide_sufficiency"
            else ArtifactPolicyProjectionFacts
        )
        expected_keys = {item.name for item in fields(facts_type)}
        if set(self.projection_facts) != expected_keys:
            raise ValueError("projection facts are incomplete")
        typed_facts = facts_type(
            **{
                key: UUID(str(value))
                if key.endswith("_id") or key == "provider_idempotency_key"
                else value
                for key, value in self.projection_facts.items()
            }
        )
        expected_digest = (
            guide_sufficiency_projection_facts_digest(typed_facts)
            if self.component == "guide_sufficiency"
            else artifact_policy_projection_facts_digest(typed_facts)
        )
        if self.facts_digest != expected_digest:
            raise ValueError("projection facts digest is inconsistent")
        output_field = "report_id" if self.component == "guide_sufficiency" else "policy_id"
        if self.projection_facts[output_field] != str(self.output_id):
            raise ValueError("projection output identity is inconsistent")
        if self.projection_facts.get("project_id") != str(self.scope_project_id):
            raise ValueError("projection project identity is inconsistent")
        return self


def projection_action(component: ProjectionComponent) -> ActionId:
    """Return the sole existing action for a projection component."""
    return (
        ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN
        if component == "guide_sufficiency"
        else ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE
    )


def projection_prepare_context(
    component: ProjectionComponent,
    locator: ProjectGuideProjectionLocator,
    identity: ProjectGuideProjectionIdentity,
) -> ProjectGuideProjectionPrepareContext:
    """Build the exact preparation binding for one locator and fixed identity."""
    return ProjectGuideProjectionPrepareContext(
        component=component,
        resource_type=(
            "project_guide_sufficiency_projection"
            if component == "guide_sufficiency"
            else "project_submission_artifact_policy_projection"
        ),
        project_id=locator.project_id,
        attempt_id=locator.attempt_id,
        operation_id=identity.operation_id,
        correlation_id=identity.correlation_id,
        output_id=identity.output_id,
        actor_profile_id=identity.actor_profile_id,
        identity_link_id=identity.identity_link_id,
        service_identity=identity.service_identity,
    )


def projection_resource_context(
    component: ProjectionComponent,
    identity: ProjectGuideProjectionIdentity,
    facts: GuideSufficiencyProjectionFacts | ArtifactPolicyProjectionFacts,
) -> ProjectGuideProjectionResourceContext:
    """Build and validate the complete final resource context."""
    expected_type = (
        GuideSufficiencyProjectionFacts
        if component == "guide_sufficiency"
        else ArtifactPolicyProjectionFacts
    )
    if type(facts) is not expected_type:
        raise ValueError("projection facts do not match component")
    facts_digest = (
        guide_sufficiency_projection_facts_digest(facts)
        if component == "guide_sufficiency"
        else artifact_policy_projection_facts_digest(facts)
    )
    return ProjectGuideProjectionResourceContext(
        resource_type=(
            "project_guide_sufficiency_projection"
            if component == "guide_sufficiency"
            else "project_submission_artifact_policy_projection"
        ),
        resource_id=identity.operation_id,
        scope_project_id=facts.project_id,
        component=component,
        operation_id=identity.operation_id,
        correlation_id=identity.correlation_id,
        output_id=identity.output_id,
        actor_profile_id=identity.actor_profile_id,
        identity_link_id=identity.identity_link_id,
        service_identity=identity.service_identity,
        facts_digest=facts_digest,
        projection_facts={
            key: str(value) if isinstance(value, UUID) else value
            for key, value in asdict(facts).items()
        },
    )


def projection_resource_digest(resource: ProjectGuideProjectionResourceContext) -> str:
    """Return the public authority digest for exact evidence parity."""
    return projection_authority_digest(
        component=resource.component,
        identity=ProjectGuideProjectionIdentity(
            operation_id=resource.operation_id,
            correlation_id=resource.correlation_id,
            output_id=resource.output_id,
            actor_profile_id=resource.actor_profile_id,
            identity_link_id=resource.identity_link_id,
            service_identity=resource.service_identity,
        ),
        project_id=resource.scope_project_id,
        facts_digest=resource.facts_digest,
    )


def projection_prepare_matches(
    prepared: dict | None,
    resource: ProjectGuideProjectionResourceContext,
) -> bool:
    """Require final resource identity to match every prepared locator fact."""
    return prepared == ProjectGuideProjectionPrepareContext(
        component=resource.component,
        resource_type=resource.resource_type,
        project_id=resource.scope_project_id,
        attempt_id=UUID(str(resource.projection_facts["attempt_id"])),
        operation_id=resource.operation_id,
        correlation_id=resource.correlation_id,
        output_id=resource.output_id,
        actor_profile_id=resource.actor_profile_id,
        identity_link_id=resource.identity_link_id,
        service_identity=resource.service_identity,
    ).model_dump(mode="json")


def parse_projection_prepare(
    action: ActionId, request_value: dict[str, object]
) -> dict[str, object]:
    """Parse only the closed projection preparation shape for reused actions."""
    if request_value.get("binding_kind") != "project_guide_projection":
        return {}
    try:
        context = ProjectGuideProjectionPrepareContext.model_validate_json(
            json.dumps(request_value)
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid projection preparation") from exc
    if projection_action(context.component) is not action:
        raise ValueError("projection action does not match component")
    return {"guide_projection_prepare_context": context.model_dump(mode="json")}
