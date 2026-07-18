"""Strict public schemas for controlled service actor provisioning."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.modules.actors.service_identities import ServiceIdentity

_STRICT = ConfigDict(extra="forbid", hide_input_in_errors=True)


def _bounded_subject(value: str) -> str:
    if not value.strip() or value != value.strip() or len(value.encode("utf-8")) > 200:
        raise ValueError("subject must contain 1 to 200 UTF-8 bytes")
    return value


def _bounded_reason(value: str) -> str:
    if not 1 <= len(value.encode("utf-8")) <= 500:
        raise ValueError("reason must contain 1 to 500 UTF-8 bytes")
    return value


OpaqueSubject = Annotated[str, Field(min_length=1), AfterValidator(_bounded_subject)]
ProvisionReason = Annotated[str, Field(min_length=1), AfterValidator(_bounded_reason)]


class ServiceActorProvisionBody(BaseModel):
    """One fixed service identity and opaque external subject binding."""

    model_config = _STRICT
    service_identity: ServiceIdentity
    subject: OpaqueSubject
    reason: ProvisionReason


class ServiceActorProvisionResponse(BaseModel):
    """Privacy-bounded immutable service actor creation facts."""

    model_config = _STRICT
    actor_profile_id: UUID
    service_identity: ServiceIdentity
    actor_status: Literal["active"]
    identity_link_status: Literal["active"]
    provisioning_method: Literal["manual_service_provisioning"]
    created_at: datetime
    linked_at: datetime
