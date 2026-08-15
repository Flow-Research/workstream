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
            "status in ('active','suspended')",
            name="status",
        ),
        CheckConstraint(
            "binding_lifecycle_version > 0",
            name="lifecycle_version_positive",
        ),
        CheckConstraint(
            "(status='active' and suspended_by is null and suspended_at is null "
            "and ((binding_lifecycle_version=1 and resumed_by is null and resumed_at is null) "
            "or (binding_lifecycle_version>1 and resumed_by is not null "
            "and resumed_at is not null)) and retired_by is null and retired_at is null) or "
            "(status='suspended' and binding_lifecycle_version > 1 "
            "and suspended_by is not null and suspended_at is not null "
            "and resumed_by is null and resumed_at is null "
            "and retired_by is null and retired_at is null)",
            name="lifecycle_shape",
        ),
        CheckConstraint(
            "(suspended_at is null or suspended_at >= created_at) and "
            "(resumed_at is null or resumed_at >= created_at) and "
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
    resumed_by: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_compensation_binding_resumed_by")
    )
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_by: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_compensation_binding_retired_by")
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CompensationAdapterBindingLifecycleEvent(Base):
    """Immutable lifecycle truth for one adapter-binding version transition."""

    __tablename__ = "compensation_adapter_binding_lifecycle_events"
    __table_args__ = (
        UniqueConstraint("operation_id", name="operation_id"),
        UniqueConstraint(
            "adapter_binding_id",
            "to_lifecycle_version",
            name="binding_version",
        ),
        CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="request_digest",
        ),
        CheckConstraint(
            "event_type in ('created','suspended','resumed')",
            name="event_type",
        ),
        CheckConstraint(
            "(event_type='created' and from_status is null and to_status='active' "
            "and from_lifecycle_version=0 and to_lifecycle_version=1 "
            "and prior_suspension_event_id is null) or "
            "(event_type='suspended' and from_status='active' and to_status='suspended' "
            "and from_lifecycle_version > 0 "
            "and to_lifecycle_version=from_lifecycle_version+1 "
            "and prior_suspension_event_id is null) or "
            "(event_type='resumed' and from_status='suspended' and to_status='active' "
            "and from_lifecycle_version > 0 "
            "and to_lifecycle_version=from_lifecycle_version+1 "
            "and prior_suspension_event_id is not null)",
            name="transition_shape",
        ),
        Index(
            "ix_compensation_binding_event_binding",
            "adapter_binding_id",
            "to_lifecycle_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", name="fk_compensation_binding_event_project"),
        nullable=False,
    )
    adapter_binding_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "project_compensation_adapter_bindings.id",
            name="fk_compensation_binding_event_binding",
        ),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_profile_id: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_compensation_binding_event_actor"),
        nullable=False,
    )
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    from_lifecycle_version: Mapped[int] = mapped_column(Integer, nullable=False)
    to_lifecycle_version: Mapped[int] = mapped_column(Integer, nullable=False)
    prior_suspension_event_id: Mapped[UUID | None] = mapped_column(
        Uuid(),
        ForeignKey(
            "compensation_adapter_binding_lifecycle_events.id",
            name="fk_compensation_binding_event_prior_suspension",
        ),
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
