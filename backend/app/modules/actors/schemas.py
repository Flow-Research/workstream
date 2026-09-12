"""Strict schemas for canonical actor self-service and legacy eligibility."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.actors.service_identities import ServiceIdentity
from app.modules.authorization.catalogue import ActionId


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
        if "\x00" in value:
            raise ValueError("profile field contains an unsupported character")
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


class ActorAuthorizationContextResponse(BaseModel):
    """Self-only effective authority projected onto one canonical project."""

    model_config = ConfigDict(extra="forbid")

    actor_profile_id: UUID
    status: Literal["active", "suspended", "deactivated"]
    project_id: UUID
    admin_roles: tuple[str, ...]
    project_roles: tuple[Literal["submitter", "reviewer"], ...]
    effective_action_ids: tuple[ActionId, ...]


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
    reactivated_at: datetime | None
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
