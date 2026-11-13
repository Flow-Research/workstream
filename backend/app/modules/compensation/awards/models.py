"""Fixed compensation facts copied from the exact frozen contribution rule."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CompensationAward(Base):
    """Immutable award metadata, with no mutable delivery or payment status."""

    __tablename__ = "compensation_awards"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        UniqueConstraint("contribution_record_id", name="uq_compensation_award_contribution"),
        ForeignKeyConstraint(
            ["contribution_policy_version_id", "project_id"],
            ["contribution_policy_versions.id", "contribution_policy_versions.project_id"],
            name="fk_compensation_award_policy_project",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("instrument_type in ('money','project_points')", name="instrument_type"),
        CheckConstraint(
            "quantity > 0 and quantity < 100000000000000000000 "
            "and scale(quantity) between 0 and 18",
            name="quantity_exact_bounds",
        ),
        CheckConstraint(
            "instrument_type <> 'project_points' or scale(quantity)=0", name="project_points_whole"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    contribution_record_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("contribution_records.id", ondelete="RESTRICT"), nullable=False
    )
    contributor_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("actor_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    contribution_policy_version_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("contribution_policy_versions.id", ondelete="RESTRICT"), nullable=False
    )
    award_definition_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("contribution_award_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    adapter_binding_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey("project_compensation_adapter_bindings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    instrument_type: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    correlation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
