"""Auth actor schemas used by API dependencies and responses."""

from __future__ import annotations

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field


SubjectKind = Literal["human", "service", "agent", "space"]
MAX_VERIFIED_IDENTITY_ANCHOR_CHARACTERS = 200


class VerifiedIssuerToken(BaseModel):
    """Canonical identity and coarse-access claims from a verified issuer token."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issuer: str = Field(min_length=1, max_length=MAX_VERIFIED_IDENTITY_ANCHOR_CHARACTERS)
    subject: str = Field(min_length=1, max_length=MAX_VERIFIED_IDENTITY_ANCHOR_CHARACTERS)
    audience: tuple[str, ...]
    expires_at: int
    issued_at: int
    not_before: int | None = None
    token_id: str
    subject_kind: SubjectKind
    scopes: frozenset[str]


class AuthVerificationResult(BaseModel):
    """Canonical verified identity; product authority is resolved by AUTH."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    token: VerifiedIssuerToken


def actor_id_from_external_identity(issuer: str, subject: str) -> str:
    """Build the historical stable actor identifier from issuer and subject."""
    return str(uuid5(NAMESPACE_URL, f"{issuer}:{subject}"))
