"""Project compensation unit identities and their immutable creation evidence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint, Uuid, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Iso4217CurrencyCode(Base):
    """Migration-seeded immutable ISO 4217 List One alphabetic code."""

    __tablename__ = "iso_4217_currency_codes"
    __table_args__ = (CheckConstraint("code ~ '^[A-Z]{3}$'", name="code"),)

    code: Mapped[str] = mapped_column(String(3), primary_key=True)

class ProjectCompensationUnit(Base):
    """Project-enabled money or project-scoped points unit identity."""

    __tablename__ = "project_compensation_units"
    __table_args__ = (
        ForeignKeyConstraint(
            ["iso_currency_code"],
            ["iso_4217_currency_codes.code"],
            name="fk_project_compensation_unit_iso_currency",
        ),
        CheckConstraint("instrument_type in ('money','project_points')", name="instrument_type"),
        CheckConstraint("status in ('active','retired')", name="status"),
        CheckConstraint(
            "(instrument_type='money' and iso_currency_code is not null "
            "and unit_code=iso_currency_code) or "
            "(instrument_type='project_points' and iso_currency_code is null "
            "and unit_code ~ '^[A-Za-z][A-Za-z0-9._:-]{0,31}$')",
            name="unit_identity",
        ),
        CheckConstraint(
            "(status='active' and retired_by is null and retired_at is null) or "
            "(status='retired' and retired_by is not null and retired_at is not null)",
            name="lifecycle_shape",
        ),
        CheckConstraint("retired_at is null or retired_at >= created_at", name="retirement_time"),
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", name="fk_project_compensation_unit_project"),
        primary_key=True,
    )
    instrument_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    unit_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    iso_currency_code: Mapped[str | None] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    created_by: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_project_compensation_unit_created_by"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("statement_timestamp()")
    )
    retired_by: Mapped[str | None] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_project_compensation_unit_retired_by")
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectCompensationUnitCreationEvent(Base):
    """Immutable recoverable truth for the one creation of a project unit."""

    __tablename__ = "project_compensation_unit_creation_events"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128", name="id_uuid7"),
        ForeignKeyConstraint(
            ["project_id", "instrument_type", "unit_code"],
            [
                "project_compensation_units.project_id",
                "project_compensation_units.instrument_type",
                "project_compensation_units.unit_code",
            ],
            name="fk_project_compensation_unit_creation_unit",
        ),
        UniqueConstraint("operation_id", name="uq_project_compensation_unit_creation_operation"),
        UniqueConstraint(
            "project_id", "instrument_type", "unit_code",
            name="uq_project_compensation_unit_creation_unit",
        ),
        CheckConstraint("request_digest ~ '^sha256:[0-9a-f]{64}$'", name="request_digest"),
        CheckConstraint("instrument_type = 'project_points'", name="instrument_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    actor_profile_id: Mapped[str] = mapped_column(
        ForeignKey("actor_profiles.id", name="fk_project_compensation_unit_creation_actor"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", name="fk_project_compensation_unit_creation_project"),
        nullable=False,
    )
    instrument_type: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("statement_timestamp()")
    )
