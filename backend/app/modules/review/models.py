"""SQLAlchemy models for review decisions and findings."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

REVIEW_DECISION_ACCEPT = "accept"
REVIEW_DECISION_NEEDS_REVISION = "needs_revision"
REVIEW_DECISION_REJECT = "reject"
REVIEW_DECISIONS = (
    REVIEW_DECISION_ACCEPT,
    REVIEW_DECISION_NEEDS_REVISION,
    REVIEW_DECISION_REJECT,
)
REVIEW_FINDING_SEVERITIES = ("low", "medium", "high", "critical")


class Review(Base):
    """Auditable human review decision for one immutable submission."""

    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint(
            "decision in ('accept', 'needs_revision', 'reject')",
            name="ck_reviews_decision",
        ),
        Index("ix_reviews_submission_created", "submission_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id"),
        nullable=False,
        index=True,
    )
    reviewer_actor_id: Mapped[str] = mapped_column(
        ForeignKey("actor_identities.actor_id"),
        nullable=False,
        index=True,
    )
    decision: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    acceptance_evidence_refs: Mapped[list[str]] = mapped_column(
        "acceptance_evidence_refs",
        nullable=False,
        default=list,
    )
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    findings: Mapped[list[ReviewFinding]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
    )


class ReviewFinding(Base):
    """Structured reviewer finding attached to a review decision."""

    __tablename__ = "review_findings"
    __table_args__ = (
        CheckConstraint(
            "severity in ('low', 'medium', 'high', 'critical')",
            name="ck_review_findings_severity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id"), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    area: Mapped[str] = mapped_column(String(100), nullable=False)
    issue: Mapped[str] = mapped_column(Text, nullable=False)
    required_fix: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    review: Mapped[Review] = relationship(back_populates="findings")
