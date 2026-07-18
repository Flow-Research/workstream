"""SQLAlchemy models for authority mutation idempotency."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class AuthorityIdempotencyRecord(Base):
    """Internal reservation and typed replay reference for one authority mutation."""

    __tablename__ = "authority_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "actor_ref_kind",
            "actor_ref",
            "operation",
            "idempotency_key",
            name="replay_namespace",
        ),
        UniqueConstraint("id", "actor_ref_kind", "actor_ref", name="actor_reference"),
        CheckConstraint(
            "actor_ref_kind in ('legacy_actor', 'actor_profile', 'system_principal')",
            name="actor_kind",
        ),
        CheckConstraint(
            "((actor_ref_kind = 'system_principal' and actor_ref = "
            "'workstream:system:bootstrap') or (actor_ref_kind <> 'system_principal' and "
            "actor_ref ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'))",
            name="actor_reference",
        ),
        CheckConstraint(
            "operation in ('service_actor.create', 'admin_role_grant.issue', "
            "'admin_role_grant.revoke', 'project_role_grant.issue', "
            "'project_role_grant.revoke', 'actor_profile.suspend', "
            "'actor_profile.reactivate', 'actor_profile.deactivate', "
            "'actor_identity_link.revoke', 'actor_identity_link.reactivate')",
            name="operation",
        ),
        CheckConstraint("request_digest ~ '^sha256:[0-9a-f]{64}$'", name="request_digest"),
        CheckConstraint("status in ('pending', 'committed')", name="status"),
        CheckConstraint(
            "response_resource_version is null or response_resource_version > 0",
            name="response_version",
        ),
        CheckConstraint(
            "(status = 'pending' and response_resource_type is null and "
            "response_resource_id is null and response_resource_version is null and "
            "response_http_status is null and committed_at is null) or "
            "(status = 'committed' and response_resource_type is not null and "
            "response_resource_id is not null and response_http_status is not null and "
            "committed_at is not null)",
            name="state_shape",
        ),
        CheckConstraint(
            "response_http_status is null or ((operation in ('service_actor.create', "
            "'admin_role_grant.issue', 'project_role_grant.issue') and "
            "response_http_status = 201) or (operation not in ('service_actor.create', "
            "'admin_role_grant.issue', 'project_role_grant.issue') and "
            "response_http_status = 200))",
            name="response_status",
        ),
        CheckConstraint(
            "(operation = 'service_actor.create' and (response_resource_type is null or "
            "response_resource_type = 'actor_profile')) or "
            "(operation like 'admin_role_grant.%' and (response_resource_type is null or "
            "response_resource_type = 'admin_role_grant')) or "
            "(operation like 'project_role_grant.%' and (response_resource_type is null or "
            "response_resource_type = 'project_role_grant')) or "
            "(operation like 'actor_profile.%' and (response_resource_type is null or "
            "response_resource_type = 'actor_profile')) or "
            "(operation like 'actor_identity_link.%' and (response_resource_type is null or "
            "response_resource_type = 'actor_identity_link'))",
            name="response_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    actor_ref_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str] = mapped_column(String(48), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    response_resource_type: Mapped[str | None] = mapped_column(String(32))
    response_resource_id: Mapped[UUID | None] = mapped_column(Uuid())
    response_resource_version: Mapped[int | None] = mapped_column(BigInteger)
    response_http_status: Mapped[int | None] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminRoleGrant(Base):
    """Immutable administrative authority history."""

    __tablename__ = "admin_role_grants"
    __table_args__ = (
        CheckConstraint(
            "role in ('access_administrator','operator','project_manager',"
            "'finance_authority','audit_authority')",
            name="role",
        ),
        CheckConstraint("scope_type in ('system','project')", name="scope_type"),
        CheckConstraint(
            "(scope_type='system' and scope_project_id is null) or "
            "(scope_type='project' and scope_project_id is not null and "
            "role not in ('access_administrator','operator'))",
            name="role_scope",
        ),
        CheckConstraint(
            "(granted_by_system_principal='workstream:system:bootstrap' and "
            "granted_by_actor_profile_id is null and "
            "granted_by_admin_role_grant_id is null) or "
            "(granted_by_system_principal is null and "
            "granted_by_actor_profile_id is not null and "
            "granted_by_admin_role_grant_id is not null)",
            name="grant_attribution",
        ),
        CheckConstraint("octet_length(grant_reason) between 1 and 500", name="grant_reason"),
        CheckConstraint(
            "(status='active' and version=1 and revoked_by_actor_profile_id is null "
            "and revoked_by_admin_role_grant_id is null and revoked_reason is null "
            "and revoked_at is null) or (status='revoked' and version=2 and "
            "revoked_by_actor_profile_id is not null and "
            "revoked_by_admin_role_grant_id is not null and revoked_reason is not null "
            "and octet_length(revoked_reason) between 1 and 500 and revoked_at is not null)",
            name="lifecycle",
        ),
        Index(
            "uq_admin_role_grants_active_system",
            "target_actor_profile_id",
            "role",
            unique=True,
            postgresql_where=text("status='active' and scope_type='system'"),
        ),
        Index(
            "uq_admin_role_grants_active_project",
            "target_actor_profile_id",
            "role",
            "scope_project_id",
            unique=True,
            postgresql_where=text("status='active' and scope_type='project'"),
        ),
        Index(
            "ix_admin_role_grants_effective_candidate",
            "target_actor_profile_id",
            "status",
            "scope_type",
            "scope_project_id",
        ),
        Index(
            "ix_admin_role_grants_history",
            "target_actor_profile_id",
            "granted_at",
            "id",
        ),
        Index(
            "ix_admin_role_grants_final_access_admin",
            "role",
            "status",
            postgresql_where=text(
                "role='access_administrator' and status='active' and scope_type='system'"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    target_actor_profile_id: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    granted_by_actor_profile_id: Mapped[str | None] = mapped_column(ForeignKey("actor_profiles.id"))
    granted_by_system_principal: Mapped[str | None] = mapped_column(String(100))
    granted_by_admin_role_grant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admin_role_grants.id")
    )
    grant_reason: Mapped[str] = mapped_column(Text, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_by_actor_profile_id: Mapped[str | None] = mapped_column(ForeignKey("actor_profiles.id"))
    revoked_by_admin_role_grant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admin_role_grants.id")
    )
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthorityControl(Base):
    """Irreversible singleton governing bootstrap and final-admin mutation order."""

    __tablename__ = "authority_control"
    __table_args__ = (
        CheckConstraint("id=1", name="singleton"),
        CheckConstraint(
            "(bootstrap_completed=false and bootstrap_grant_id is null and version=0) or "
            "(bootstrap_completed=true and bootstrap_grant_id is not null and version=1)",
            name="bootstrap_state",
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    bootstrap_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bootstrap_grant_id: Mapped[UUID | None] = mapped_column(ForeignKey("admin_role_grants.id"))
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
