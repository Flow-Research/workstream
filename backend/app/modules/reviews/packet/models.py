"""Normalized immutable reviewer packets and their exact guide members."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReviewPacketManifest(Base):
    """One retained metadata packet per lease, with exactly one original ZIP."""

    __tablename__ = "review_packet_manifests"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        UniqueConstraint("review_lease_id", name="uq_review_packet_lease"),
        ForeignKeyConstraint(
            ["task_id", "project_id"],
            ["workstream_tasks.id", "workstream_tasks.project_id"],
            ondelete="RESTRICT",
            name="fk_review_packet_task",
        ),
        ForeignKeyConstraint(
            ["submission_id", "task_id", "submission_version"],
            ["submissions.id", "submissions.task_id", "submissions.version"],
            ondelete="RESTRICT",
            name="fk_review_packet_submission",
        ),
        ForeignKeyConstraint(
            ["checker_run_id", "task_id", "submission_id"],
            ["checker_runs.id", "checker_runs.task_id", "checker_runs.submission_id"],
            ondelete="RESTRICT",
            name="fk_review_packet_checker",
        ),
        ForeignKeyConstraint(
            ["source_snapshot_id", "project_id", "guide_id"],
            [
                "guide_source_snapshots.id",
                "guide_source_snapshots.project_id",
                "guide_source_snapshots.guide_id",
            ],
            ondelete="RESTRICT",
            name="fk_review_packet_snapshot",
        ),
        ForeignKeyConstraint(
            [
                "project_setup_run_id",
                "project_id",
                "guide_id",
                "source_snapshot_id",
                "setup_generation",
            ],
            [
                "project_setup_runs.id",
                "project_setup_runs.project_id",
                "project_setup_runs.guide_id",
                "project_setup_runs.source_snapshot_id",
                "project_setup_runs.setup_generation",
            ],
            ondelete="RESTRICT",
            name="fk_review_packet_setup",
        ),
        CheckConstraint(
            "submission_version > 0 and setup_generation > 0 and packet_manifest_generation > 0",
            name="positive_generations",
        ),
        CheckConstraint("length(btrim(guide_version)) > 0", name="guide_version_nonblank"),
        CheckConstraint("packet_manifest_digest ~ '^sha256:[0-9a-f]{64}$'", name="digest_shape"),
        CheckConstraint(
            "submission_logical_role='submission_bundle_original' and submission_media_type='application/zip'",
            name="original_zip",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    review_lease_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("review_leases.id", ondelete="RESTRICT"), nullable=False
    )
    review_queue_entry_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("review_queue_entries.id", ondelete="RESTRICT"), nullable=False
    )
    packet_manifest_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    packet_manifest_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    submission_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    submission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    checker_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    result_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("checker_runs.result_id", ondelete="RESTRICT"),
        nullable=False,
    )
    guide_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("project_guides.id", ondelete="RESTRICT"), nullable=False
    )
    guide_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_snapshot_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    project_setup_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    setup_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    submission_binding_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("artifact_bindings.id", ondelete="RESTRICT"), nullable=False
    )
    submission_logical_role: Mapped[str] = mapped_column(String(32), nullable=False)
    submission_media_type: Mapped[str] = mapped_column(String(100), nullable=False)


class ReviewPacketGuideItem(Base):
    """One normalized member of the exact declared guide document set."""

    __tablename__ = "review_packet_guide_items"
    __table_args__ = (
        UniqueConstraint("packet_id", "ingest_id", name="uq_review_packet_ingest"),
        UniqueConstraint("packet_id", "item_order", name="uq_review_packet_order"),
        CheckConstraint("item_order >= 0", name="order_nonnegative"),
        CheckConstraint("logical_role='guide_source_original'", name="original_guide"),
        CheckConstraint(
            "media_type in ('application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/vnd.openxmlformats-officedocument.presentationml.presentation','text/markdown')",
            name="guide_media",
        ),
    )

    packet_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("review_packet_manifests.id", ondelete="RESTRICT"), primary_key=True
    )
    source_item_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("guide_source_snapshot_items.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    ingest_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("guide_source_artifact_ingests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    item_order: Mapped[int] = mapped_column(Integer, nullable=False)
    logical_role: Mapped[str] = mapped_column(String(32), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
