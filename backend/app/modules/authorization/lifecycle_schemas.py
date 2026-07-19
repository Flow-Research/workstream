"""Strict public schemas for actor-profile lifecycle administration."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

_STRICT = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class ActorLifecycleBody(BaseModel):
    """One normalized bounded lifecycle reason."""

    model_config = _STRICT
    reason: str

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if "\x00" in normalized or not 1 <= len(normalized.encode("utf-8")) <= 500:
            raise ValueError("reason must contain 1 to 500 UTF-8 bytes")
        return normalized


class ActorLifecycleMutationResponse(BaseModel):
    """Stable privacy-bounded reference for one profile lifecycle result."""

    model_config = _STRICT
    resource_type: Literal["actor_profile"]
    resource_id: UUID
    version: None = None
    http_status: Literal[200]


class IdentityLinkLifecycleMutationResponse(BaseModel):
    """Stable privacy-bounded reference for one identity-link lifecycle result."""

    model_config = _STRICT
    resource_type: Literal["actor_identity_link"]
    resource_id: UUID
    version: None = None
    http_status: Literal[200]
