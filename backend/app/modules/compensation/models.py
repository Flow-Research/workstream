"""SQLAlchemy persistence for compensation adapter-binding identity."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProjectCompensationAdapterBinding(Base):
    """Project-scoped non-secret adapter-binding identity and lifecycle state."""

    __tablename__ = "project_compensation_adapter_bindings"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "project_id",
            "instrument_type",
            name="uq_compensation_binding_ownership",
        ),
        CheckConstraint(
            "instrument_type in ('money','project_points')",
            name="instrument_type",
        ),
        CheckConstraint(
            "route_key ~ '^[A-Za-z][A-Za-z0-9._:-]{0,119}$'",
            name="route_key",
        ),
        CheckConstraint("route_key not like '%..%'", name="route_key_no_traversal"),
        CheckConstraint(
            "status in ('active','suspended','retired')",
            name="status",
        ),
        CheckConstraint(
            "binding_lifecycle_version > 0",
            name="lifecycle_version_positive",
        ),
        CheckConstraint(
            "(status='active' and suspended_by is null and suspended_at is null "
            "and retired_by is null and retired_at is null) or "
            "(status='suspended' and suspended_by is not null and suspended_at is not null "
            "and retired_by is null and retired_at is null) or "
            "(status='retired' and retired_by is not null and retired_at is not null "
            "and ((suspended_by is null and suspended_at is null) or "
            "(suspended_by is not null and suspended_at is not null)))",
            name="lifecycle_shape",
        ),
        CheckConstraint(
            "(suspended_at is null or suspended_at >= created_at) and "
            "(retired_at is null or retired_at >= created_at) and "
            "(retired_at is null or suspended_at is null or retired_at >= suspended_at)",
            name="lifecycle_timestamps",
        ),
        Index(
            "uq_compensation_binding_active_project_instrument",
            "project_id",
            "instrument_type",
            unique=True,
            postgresql_where=text("status='active'"),
        ),
        Index(
            "ix_compensation_binding_adapter_actor",
            "adapter_actor_id",
            "status",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", name="fk_compensation_binding_project"), nullable=False
    )
    instrument_type: Mapped[str] = mapped_column(String(32), nullable=False)
    adapter_actor_id: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_compensation_binding_adapter_actor"),
        nullable=False,
    )
    route_key: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    binding_lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    created_by: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_compensation_binding_created_by"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("statement_timestamp()")
    )
    suspended_by: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_compensation_binding_suspended_by")
    )
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_by: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_compensation_binding_retired_by")
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
