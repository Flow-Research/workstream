"""Auth actor schemas used by API dependencies and responses."""

from __future__ import annotations

from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field


SubjectKind = Literal["human", "service", "agent", "space"]
MAX_VERIFIED_IDENTITY_ANCHOR_CHARACTERS = 200


def normalize_legacy_roles(value: Any) -> tuple[str, ...]:
    """Normalize verified compatibility roles into a bounded tuple."""
    if isinstance(value, str):
        raw_roles = value.split(",")
    elif isinstance(value, list | tuple | set):
        raw_roles = value
    else:
        raw_roles = ()
    roles = tuple(
        role.strip() for role in raw_roles if isinstance(role, str) and 0 < len(role.strip()) <= 128
    )
    return roles[:32]


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


class LegacyAuthorizationCompatibilityContext(BaseModel):
    """Verified legacy roles for the bounded unmigrated dependency only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    roles: tuple[str, ...] = ()
    auth_source: Literal["flow", "dev_mock"]
    is_dev_auth: bool = False


class AuthVerificationResult(BaseModel):
    """One verification result containing canonical and bounded legacy views."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    token: VerifiedIssuerToken
    legacy: LegacyAuthorizationCompatibilityContext | None = None

    def legacy_actor(self) -> "ActorContext":
        """Build the temporary actor context for verified human callers only."""
        if self.token.subject_kind != "human" or self.legacy is None:
            raise ValueError("legacy authorization compatibility requires a human token")
        return ActorContext(
            actor_id=actor_id_from_external_identity(self.token.issuer, self.token.subject),
            external_subject=self.token.subject,
            external_issuer=self.token.issuer,
            roles=self.legacy.roles,
            claim_snapshot={"roles": self.legacy.roles},
            auth_source=self.legacy.auth_source,
            is_dev_auth=self.legacy.is_dev_auth,
        )


def actor_id_from_external_identity(issuer: str, subject: str) -> str:
    """Build the historical stable actor identifier from issuer and subject."""
    return str(uuid5(NAMESPACE_URL, f"{issuer}:{subject}"))


def normalized_relationship_profile_claims(claim_snapshot: dict[str, Any]) -> list[dict[str, str]]:
    """Return sanitized Workstream relationship profiles from trusted claims.

    Args:
        claim_snapshot: Trusted token claims produced by the auth verifier.

    Returns:
        Sanitized relationship profile records. Unsupported or malformed claim
        entries are dropped rather than stored.
    """
    relationship_profiles = claim_snapshot.get("workstream_relationship_profiles")
    if not isinstance(relationship_profiles, list):
        return []

    sanitized_relationships: list[dict[str, str]] = []
    for raw_profile in relationship_profiles:
        if not isinstance(raw_profile, dict):
            continue
        if raw_profile.get("profile_type") != "project_owner":
            continue
        scope_type = raw_profile.get("scope_type")
        scope_id = raw_profile.get("scope_id")
        if not isinstance(scope_type, str) or not isinstance(scope_id, str):
            continue
        scope_type = scope_type.strip()
        scope_id = scope_id.strip()
        if not scope_type or not scope_id:
            continue
        sanitized_relationships.append(
            {
                "profile_type": "project_owner",
                "scope_type": scope_type,
                "scope_id": scope_id,
            }
        )
    return sanitized_relationships


def sanitized_claim_snapshot(claim_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return the audit-safe claim snapshot allowed in Workstream storage.

    Args:
        claim_snapshot: Trusted token claims produced by the auth verifier.

    Returns:
        Claim snapshot with relationship claims reduced to scope identity only.
    """
    sanitized: dict[str, Any] = {}
    raw_roles = claim_snapshot.get("roles")
    if isinstance(raw_roles, list | tuple):
        roles = [role.strip() for role in raw_roles if isinstance(role, str) and role.strip()]
    elif isinstance(raw_roles, str):
        roles = [role.strip() for role in raw_roles.split(",") if role.strip()]
    else:
        roles = []
    if roles:
        sanitized["roles"] = roles

    sanitized_relationships = normalized_relationship_profile_claims(claim_snapshot)
    if not sanitized_relationships:
        return sanitized
    sanitized["workstream_relationship_profiles"] = sanitized_relationships
    return sanitized


class ActorAuditContext(BaseModel):
    """Stable actor claims stored with auditable Workstream actions."""

    actor_id: str
    external_subject: str
    external_issuer: str
    actor_roles: tuple[str, ...]
    claim_snapshot: dict[str, Any]
    auth_source: Literal["flow", "dev_mock", "workstream_system"]
    is_dev_auth: bool


class ActorContext(BaseModel):
    """Trusted actor context resolved from an external Flow token."""

    actor_id: str
    external_subject: str
    external_issuer: str
    email: str | None = None
    display_name: str | None = None
    roles: tuple[str, ...] = ()
    claim_snapshot: dict[str, Any] = Field(default_factory=dict)
    auth_source: Literal["flow", "dev_mock", "workstream_system"]
    is_dev_auth: bool = False

    def audit_context(self) -> ActorAuditContext:
        """Build the audit-safe actor snapshot for persisted records.

        Returns:
            Actor audit context derived from the trusted actor claims.
        """
        return ActorAuditContext(
            actor_id=self.actor_id,
            external_subject=self.external_subject,
            external_issuer=self.external_issuer,
            actor_roles=self.roles,
            claim_snapshot=sanitized_claim_snapshot(self.claim_snapshot),
            auth_source=self.auth_source,
            is_dev_auth=self.is_dev_auth,
        )


class ActorResponse(BaseModel):
    """Public response schema for the current actor endpoint."""

    actor_id: str
    external_subject: str
    external_issuer: str
    email: str | None = None
    display_name: str | None = None
    roles: tuple[str, ...]
    auth_source: Literal["flow", "dev_mock", "workstream_system"]
    is_dev_auth: bool
    audit_context: ActorAuditContext

    @classmethod
    def from_actor(cls, actor: ActorContext) -> "ActorResponse":
        """Build an actor response from the trusted actor context.

        Args:
            actor: Trusted actor resolved by authentication.

        Returns:
            Public actor response with audit context included.
        """
        return cls(
            actor_id=actor.actor_id,
            external_subject=actor.external_subject,
            external_issuer=actor.external_issuer,
            email=actor.email,
            display_name=actor.display_name,
            roles=actor.roles,
            auth_source=actor.auth_source,
            is_dev_auth=actor.is_dev_auth,
            audit_context=actor.audit_context(),
        )
