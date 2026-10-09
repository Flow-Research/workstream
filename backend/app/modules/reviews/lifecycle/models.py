"""Shared lifecycle controller and immutable authorized transition history."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


class JointLifecycleReleaseControl(Base):
    """One preserved singleton; each phase change requires exact authorized history."""

    __tablename__ = "joint_lifecycle_release_control"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        CheckConstraint("singleton", name="singleton_true"),
        UniqueConstraint("singleton"),
        CheckConstraint("phase in ('disabled','shadow','live','draining')", name="phase"),
        CheckConstraint("generation >= 0", name="generation_nonnegative"),
        CheckConstraint("generation <> 0 or phase='disabled'", name="genesis_disabled"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    singleton: Mapped[bool] = mapped_column(Boolean, nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    transition_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("joint_lifecycle_transitions.id", name="fk_joint_lifecycle_release_control_transition_id", deferrable=True, initially="DEFERRED"),
    )


class JointLifecycleTransition(Base):
    """One immutable operation and AUTH event for each controller generation."""

    __tablename__ = "joint_lifecycle_transitions"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        UniqueConstraint("operation_id"),
        UniqueConstraint("singleton_id", "generation"),
        UniqueConstraint("authorization_decision_event_id"),
        CheckConstraint("generation > 0", name="generation_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    singleton_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("joint_lifecycle_release_control.id"), nullable=False,
    )
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    previous_phase: Mapped[str] = mapped_column(String(16), nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    facts_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    resource_context_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    authorization_decision_event_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("audit_events.id"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()"),
    )
