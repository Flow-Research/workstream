"""Canonical actor identity models and bounded legacy workflow metadata."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.modules.actors.service_identities import SERVICE_IDENTITY_VALUES

ACTOR_KINDS = ("human", "service")
ACTOR_PROFILE_STATUSES = ("active", "suspended", "deactivated")
ACTOR_PROVISIONING_METHODS = ("automatic_first_access", "manual_service_provisioning")
IDENTITY_LINK_STATUSES = ("active", "revoked")
LEGACY_PROFILE_TYPES = ("worker", "reviewer", "admin", "project_manager", "project_owner")
LEGACY_PROFILE_STATUSES = ("observed", "active", "disabled")
GLOBAL_PROFILE_SCOPE_TYPE = "global"
GLOBAL_PROFILE_SCOPE_ID = "global"


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class ActorProfile(Base):
    """Canonical Workstream actor root without implied product authority."""

    __tablename__ = "actor_profiles"
    __table_args__ = (
        CheckConstraint(f"actor_kind in ({_sql_values(ACTOR_KINDS)})", name="actor_kind"),
        CheckConstraint(
            f"status in ({_sql_values(ACTOR_PROFILE_STATUSES)})", name="status"
        ),
        CheckConstraint(
            f"provisioning_method in ({_sql_values(ACTOR_PROVISIONING_METHODS)})",
            name="provisioning_method",
        ),
        CheckConstraint(
            "(actor_kind = 'human' and provisioning_method = 'automatic_first_access') or "
            "(actor_kind = 'service' and provisioning_method = 'manual_service_provisioning')",
            name="kind_provisioning",
        ),
        CheckConstraint(
            "(actor_kind = 'human' and service_identity is null) or "
            f"(actor_kind = 'service' and service_identity in ({_sql_values(SERVICE_IDENTITY_VALUES)}))",
            name="kind_service_identity",
        ),
        CheckConstraint(
            "(status = 'active' and suspended_by is null and suspended_at is null and "
            "suspension_reason is null and deactivated_by is null and deactivated_at is null "
            "and deactivation_reason is null) or "
            "(status = 'suspended' and suspended_by is not null and suspended_at is not null "
            "and suspension_reason is not null and deactivated_by is null and "
            "deactivated_at is null and deactivation_reason is null) or "
            "(status = 'deactivated' and deactivated_by is not null and deactivated_at is not null "
            "and deactivation_reason is not null)",
            name="lifecycle_fields",
        ),
        Index("ix_actor_profiles_status_actor_kind", "status", "actor_kind"),
        Index("ix_actor_profiles_last_seen_at", "last_seen_at"),
        UniqueConstraint("service_identity", name="service_identity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    provisioning_method: Mapped[str] = mapped_column(String(32), nullable=False)
    service_identity: Mapped[str | None] = mapped_column(String(80))
    display_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_by: Mapped[str | None] = mapped_column(String(120))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspension_reason: Mapped[str | None] = mapped_column(String(500))
    deactivated_by: Mapped[str | None] = mapped_column(String(120))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deactivation_reason: Mapped[str | None] = mapped_column(String(500))

    identity_link: Mapped[ActorIdentityLink] = relationship(
        back_populates="actor_profile",
        uselist=False,
    )


class ActorIdentityLink(Base):
    """One stable external issuer subject linked to one canonical actor."""

    __tablename__ = "actor_identity_links"
    __table_args__ = (
        CheckConstraint(f"subject_kind in ({_sql_values(ACTOR_KINDS)})", name="subject_kind"),
        CheckConstraint(
            f"status in ({_sql_values(IDENTITY_LINK_STATUSES)})", name="status"
        ),
        CheckConstraint(
            "(status = 'active' and revoked_by is null and revoked_at is null and "
            "revoked_reason is null) or "
            "(status = 'revoked' and revoked_by is not null and revoked_at is not null and "
            "revoked_reason is not null)",
            name="revocation_fields",
        ),
        CheckConstraint(
            "subject_kind = 'service' or last_verified_at is not null",
            name="human_verified",
        ),
        UniqueConstraint("issuer", "subject", name="external_identity"),
        UniqueConstraint("actor_profile_id", name="actor_profile"),
        Index(
            "ix_actor_identity_links_issuer_subject_status",
            "issuer",
            "subject",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_profile_id: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id"), nullable=False
    )
    issuer: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    subject_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    linked_by: Mapped[str] = mapped_column(String(120), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(String(120))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(500))
    reactivated_by: Mapped[str | None] = mapped_column(String(120))
    reactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reactivation_reason: Mapped[str | None] = mapped_column(String(500))

    actor_profile: Mapped[ActorProfile] = relationship(back_populates="identity_link")


class LegacyActorIdentity(Base):
    """Non-authoritative token-observation row retained for intermediate workflows."""

    __tablename__ = "legacy_actor_identities"
    __table_args__ = (
        UniqueConstraint(
            "external_issuer",
            "external_subject",
            name="uq_legacy_actor_identities_external_identity",
        ),
    )

    actor_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    external_subject: Mapped[str] = mapped_column(String(200), nullable=False)
    external_issuer: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    last_seen_roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    last_claim_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    auth_source: Mapped[str] = mapped_column(String(50), nullable=False)
    is_dev_auth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workflow_eligibility: Mapped[list[LegacyWorkflowEligibility]] = relationship(
        back_populates="identity",
        cascade="all, delete-orphan",
    )


class LegacyWorkflowEligibility(Base):
    """Classified workflow metadata that grants no Workstream permission."""

    __tablename__ = "legacy_workflow_eligibility"
    __table_args__ = (
        CheckConstraint(
            f"profile_type in ({_sql_values(LEGACY_PROFILE_TYPES)})",
            name="profile_type",
        ),
        CheckConstraint(
            f"status in ({_sql_values(LEGACY_PROFILE_STATUSES)})",
            name="status",
        ),
        UniqueConstraint(
            "actor_id",
            "profile_type",
            "scope_type",
            "scope_id",
            name="actor_type_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_actor_identities.actor_id"), nullable=False, index=True
    )
    profile_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="observed", index=True)
    skill_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    scope_type: Mapped[str] = mapped_column(String(50), nullable=False, default=GLOBAL_PROFILE_SCOPE_TYPE)
    scope_id: Mapped[str] = mapped_column(String(100), nullable=False, default=GLOBAL_PROFILE_SCOPE_ID)
    profile_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    identity: Mapped[LegacyActorIdentity] = relationship(back_populates="workflow_eligibility")
