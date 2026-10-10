"""Immutable shared acceptance source schema, awaiting exact AUTH custody."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FinalAcceptance(Base):
    """Storage foundation only; no runtime consumer may infer acceptance authority."""

    __tablename__ = "final_acceptances"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        CheckConstraint(
            "(acceptance_source='human_review' and source_review_id is not null "
            "and source_routing_manifest_id is null) or "
            "(acceptance_source='task_post_submit_route' and source_review_id is null "
            "and source_routing_manifest_id is not null)",
            name="source_shape",
        ),
        UniqueConstraint("task_id"),
        UniqueConstraint("submission_id"),
        UniqueConstraint("source_review_id"),
        UniqueConstraint("source_routing_manifest_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("workstream_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    submission_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("submissions.id", ondelete="RESTRICT"), nullable=False
    )
    acceptance_source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_review_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("reviews.id", ondelete="RESTRICT"), nullable=True
    )
    source_routing_manifest_id: Mapped[UUID | None] = mapped_column(
        Uuid(),
        ForeignKey("task_post_submit_routing_manifests.id", ondelete="RESTRICT"),
        nullable=True,
    )
    accepted_submitter_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("actor_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_by: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("actor_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    policy_context_ref: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("review_policies.id", ondelete="RESTRICT"), nullable=False
    )
    source_authorization_decision_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("audit_events.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
