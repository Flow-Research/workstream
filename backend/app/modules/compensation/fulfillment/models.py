"""Immutable Workstream custody for one original earned award."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CompensationFulfillmentRoot(Base):
    __tablename__ = "compensation_fulfillment_roots"
    __table_args__ = (
        CheckConstraint("(get_byte(uuid_send(id),6)>>4)=7 and (get_byte(uuid_send(id),8)&192)=128", name="id_uuid7"),
        CheckConstraint("(get_byte(uuid_send(source_instance_id),6)>>4)=7 and (get_byte(uuid_send(source_instance_id),8)&192)=128", name="source_uuid7"),
        CheckConstraint("ordinal>0 and admission_generation>0", name="positive_custody"),
        CheckConstraint("source_award_digest ~ '^sha256:[0-9a-f]{64}$' and obligation_digest ~ '^sha256:[0-9a-f]{64}$'", name="digests"),
        CheckConstraint("jsonb_typeof(obligation_body)='object'", name="obligation_object"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    award_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("compensation_awards.id"), unique=True, nullable=False)
    project_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("projects.id"), nullable=False)
    ordinal: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    admission_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_instance_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    adapter_binding_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("project_compensation_adapter_bindings.id"), nullable=False)
    route_key: Mapped[str] = mapped_column(String(120), nullable=False)
    source_final_acceptance_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("final_acceptances.id"), nullable=False)
    source_authorization_decision_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("audit_events.id"), nullable=False)
    source_routing_manifest_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("task_post_submit_routing_manifests.id"), nullable=False)
    source_award_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    obligation_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    obligation_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    initial_outbox_event_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("outbox_events.event_id"), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()"))
