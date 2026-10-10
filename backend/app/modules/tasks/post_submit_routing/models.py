"""Immutable TASK routing requests and authorized outcome custody."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.db.base import Base


class TaskPostSubmitRoutingManifest(Base):
    """One immutable exact source, consumed routing authority and outcome identity."""

    __tablename__ = "task_post_submit_routing_manifests"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        CheckConstraint("submission_version > 0", name="submission_version_positive"),
        CheckConstraint("evaluation_generation > 0", name="evaluation_generation_positive"),
        CheckConstraint("byte_count >= 0", name="byte_count_nonnegative"),
        CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "result_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "content_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "semantic_manifest_sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="sha256_shapes",
        ),
        ForeignKeyConstraint(
            ["task_id", "project_id"],
            ["workstream_tasks.id", "workstream_tasks.project_id"],
            name="fk_task_routing_manifest_task_project",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["submission_id", "task_id", "submission_version"],
            ["submissions.id", "submissions.task_id", "submissions.version"],
            name="fk_task_routing_manifest_submission_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["assignment_id", "task_id", "contributor_id"],
            ["task_assignments.id", "task_assignments.task_id", "task_assignments.contributor_id"],
            name="fk_task_routing_manifest_assignment_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["contribution_policy_version_id", "project_id"],
            ["contribution_policy_versions.id", "contribution_policy_versions.project_id"],
            name="fk_task_routing_manifest_contribution_project",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["checker_run_id", "task_id", "submission_id"],
            ["checker_runs.id", "checker_runs.task_id", "checker_runs.submission_id"],
            name="fk_task_routing_manifest_checker_source",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "submission_id",
            "checker_run_id",
            "result_digest",
            name="uq_task_routing_manifest_source",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    submission_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    submission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    assignment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    contributor_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    contribution_policy_version_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    checker_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    evaluation_request_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    evaluation_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    result_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    result_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    completion_event_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "outbox_events.event_id",
            name="fk_task_routing_manifest_completion_event",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    execute_evidence_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey(
            "audit_events.id",
            name="fk_task_routing_manifest_execute_evidence",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    finalize_evidence_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey(
            "audit_events.id",
            name="fk_task_routing_manifest_finalize_evidence",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    authorization_decision_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("audit_events.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    router_actor_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("actor_profiles.id"), nullable=False
    )
    router_identity_link_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("actor_identity_links.id"), nullable=False
    )
    authority_context: Mapped[dict] = mapped_column(JSONB, nullable=False)
    final_acceptance_id: Mapped[UUID | None] = mapped_column(
        Uuid(),
        ForeignKey("final_acceptances.id", deferrable=True, initially="DEFERRED"),
        unique=True,
    )
    authorized_lifecycle_generation: Mapped[int | None] = mapped_column(BigInteger)
    audit_event_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("audit_events.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
        unique=True,
    )
    outcome_event_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey("outbox_events.event_id", deferrable=True, initially="DEFERRED"),
        nullable=False,
        unique=True,
    )
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    replica_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey(
            "artifact_replicas.id",
            name="fk_task_routing_manifest_replica",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    content_sha256: Mapped[str] = mapped_column(String(71), nullable=False)
    byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    semantic_manifest_sha256: Mapped[str] = mapped_column(String(71), nullable=False)


class TaskRoutingRequest(Base):
    """Immutable coordination reservation; its allocated manifest is not yet published."""

    __tablename__ = "task_post_submit_routing_requests"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(route_operation_id), 6) >> 4) = 7 and "
            "(get_byte(uuid_send(route_operation_id), 8) & 192) = 128",
            name="route_operation_id_uuid7",
        ),
        CheckConstraint(
            "(get_byte(uuid_send(routing_manifest_id), 6) >> 4) = 7 and "
            "(get_byte(uuid_send(routing_manifest_id), 8) & 192) = 128",
            name="routing_manifest_id_uuid7",
        ),
        CheckConstraint(
            "route_operation_id <> routing_manifest_id and "
            "route_operation_id not in (evaluation_request_id, result_id, completion_event_id) and "
            "routing_manifest_id not in (evaluation_request_id, result_id, completion_event_id)",
            name="distinct_request_ids",
        ),
        CheckConstraint("submission_version > 0 and evaluation_generation > 0", name="positive_versions"),
        CheckConstraint("routing_recommendation = 'allow_review'", name="allow_review_only"),
        CheckConstraint(
            "evaluation_request_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "result_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "route_request_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "route_request_digest <> evaluation_request_digest", name="request_digests",
        ),
        ForeignKeyConstraint(
            ["task_id", "project_id"], ["workstream_tasks.id", "workstream_tasks.project_id"],
            name="fk_task_route_request_task_project", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["submission_id", "task_id", "submission_version"],
            ["submissions.id", "submissions.task_id", "submissions.version"],
            name="fk_task_route_request_submission", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["checker_run_id", "task_id", "submission_id"],
            ["checker_runs.id", "checker_runs.task_id", "checker_runs.submission_id"],
            name="fk_task_route_request_checker", ondelete="RESTRICT",
        ),
        UniqueConstraint("routing_manifest_id", name="uq_task_route_request_manifest"),
        UniqueConstraint("completion_event_id", name="uq_task_route_request_completion"),
        UniqueConstraint("submission_id", "checker_run_id", "result_digest", name="uq_task_route_request_source"),
    )

    route_operation_id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    routing_manifest_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    task_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    submission_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    submission_version: Mapped[int] = mapped_column(Integer, nullable=False)
    checker_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    evaluation_request_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    evaluation_request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    evaluation_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    result_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    result_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    completion_event_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("outbox_events.event_id", name="fk_task_route_request_event", ondelete="RESTRICT"),
        nullable=False,
    )
    routing_recommendation: Mapped[str] = mapped_column(String(30), nullable=False)
    route_request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )
