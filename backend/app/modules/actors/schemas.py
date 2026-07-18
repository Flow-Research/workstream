"""Strict schemas for canonical actor self-service and legacy eligibility."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.actors.service_identities import ServiceIdentity


def normalize_skill_tags(value: list[str]) -> list[str]:
    """Return stable deduplicated legacy workflow skill tags."""
    normalized_tags: list[str] = []
    seen_tags: set[str] = set()
    for raw_tag in value:
        tag = raw_tag.strip().lower()
        if not tag or len(tag) > 64:
            raise ValueError("invalid skill tag")
        if tag not in seen_tags:
            normalized_tags.append(tag)
            seen_tags.add(tag)
    return normalized_tags


class ActorProfileUpdateRequest(BaseModel):
    """Human-owned display fields accepted by the canonical self API."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)

    @field_validator("display_name", "contact_email")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Reject whitespace-only values while preserving opaque text."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("profile field must not be blank")
        return normalized

    @model_validator(mode="after")
    def require_update(self):
        """Reject an empty PATCH document."""
        if not self.model_fields_set:
            raise ValueError("at least one profile field is required")
        return self


class ActorProfileSelfResponse(BaseModel):
    """Privacy-bounded canonical profile returned to its human owner."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    actor_profile_id: str
    actor_kind: Literal["human"]
    status: Literal["active", "suspended", "deactivated"]
    domains: tuple[Literal["contributor"], ...] = ("contributor",)
    admin_roles: tuple[str, ...] = ()
    project_role_grants: tuple[str, ...] = ()
    display_name: str | None
    contact_email: str | None
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None


class ActorProfileAdminResponse(BaseModel):
    """Privacy-bounded administrative view of one canonical actor."""

    model_config = ConfigDict(extra="forbid")

    actor_profile_id: UUID
    actor_kind: Literal["human", "service"]
    status: Literal["active", "suspended", "deactivated"]
    provisioning_method: Literal[
        "automatic_first_access",
        "manual_service_provisioning",
    ]
    service_identity: ServiceIdentity | None
    display_name: str | None
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None
    suspended_at: datetime | None
    deactivated_at: datetime | None

    @model_validator(mode="after")
    def require_kind_identity_pair(self):
        """Bind the closed local service identity to service actors only."""
        if (self.actor_kind == "service") != (self.service_identity is not None):
            raise ValueError("actor kind and service identity are inconsistent")
        return self


class ActorIdentityLinkAdminResponse(BaseModel):
    """Privacy-bounded administrative view of one canonical identity link."""

    model_config = ConfigDict(extra="forbid")

    identity_link_id: UUID
    actor_profile_id: UUID
    subject_kind: Literal["human", "service"]
    status: Literal["active", "revoked"]
    linked_at: datetime
    last_verified_at: datetime | None
    revoked_at: datetime | None
    reactivated_at: datetime | None


class LegacyWorkflowEligibilityActivationRequest(BaseModel):
    """Temporary non-authoritative intake metadata for existing task workflows."""

    model_config = ConfigDict(extra="forbid")

    skill_tags: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("skill_tags")
    @classmethod
    def validate_skill_tags(cls, value: list[str]) -> list[str]:
        return normalize_skill_tags(value)


class LegacyWorkflowEligibilityResponse(BaseModel):
    """Temporary compatibility response that grants no product permission."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    actor_id: str
    profile_type: str
    status: str
    skill_tags: list[str]
    scope_type: str
    scope_id: str
    profile_metadata: dict
    external_subject: str
    external_issuer: str
    created_at: datetime
    updated_at: datetime
