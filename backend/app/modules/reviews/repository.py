"""Caller-transaction persistence for review queue identity and admission replay."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reviews.models import (
    ReviewAdmissionIdempotencyRecord,
    ReviewLease,
    ReviewQueueEntry,
)
from app.modules.reviews.schemas import (
    ReviewAdmissionReservationInput,
    ReviewLeaseInput,
    ReviewQueueEntryInput,
)


class ReviewAdmissionIdempotencyConflict(RuntimeError):
    """A replay identity was reused for different immutable admission facts."""


@dataclass(frozen=True, slots=True)
class ReviewAdmissionReservation:
    """Locked reservation returned to a future caller-owned admission command."""

    created: bool
    record: ReviewAdmissionIdempotencyRecord


class ReviewQueueRepository:
    """Persist queue identities without authorizing or selecting review work."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_queue_entry(self, value: ReviewQueueEntryInput) -> ReviewQueueEntry:
        """Flush one database-validated queue identity without committing."""
        record = ReviewQueueEntry(
            id=value.id,
            project_id=value.project_id,
            task_id=value.task_id,
            submission_id=value.submission_id,
            submission_version=value.submission_version,
            admitting_checker_run_id=value.admitting_checker_run_id,
            queue_state="pending",
            routing_mode=value.routing_mode.value,
            routing_reason=value.routing_reason.value,
            preferred_reviewer_id=value.preferred_reviewer_id,
            preference_expires_at=value.preference_expires_at,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def add_lease(self, value: ReviewLeaseInput) -> ReviewLease:
        """Flush one active lease attempt without claiming or committing."""
        record = ReviewLease(
            id=value.id,
            review_queue_entry_id=value.review_queue_entry_id,
            project_id=value.project_id,
            task_id=value.task_id,
            submission_id=value.submission_id,
            submission_version=value.submission_version,
            reviewer_id=value.reviewer_id,
            reviewer_contribution_policy_version_id=(
                value.reviewer_contribution_policy_version_id
            ),
            attempt_generation=value.attempt_generation,
            status="active",
            expires_at=value.expires_at,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def reserve_admission(
        self,
        value: ReviewAdmissionReservationInput,
    ) -> ReviewAdmissionReservation:
        """Reserve one replay/checker identity and lock every possible conflict."""
        created_id = await self._session.scalar(
            insert(ReviewAdmissionIdempotencyRecord)
            .values(
                id=value.id,
                idempotency_key=value.idempotency_key,
                operation_id=value.operation_id,
                request_digest=value.request_digest,
                project_id=value.project_id,
                task_id=value.task_id,
                submission_id=value.submission_id,
                submission_version=value.submission_version,
                admitting_checker_run_id=value.admitting_checker_run_id,
            )
            .on_conflict_do_nothing()
            .returning(ReviewAdmissionIdempotencyRecord.id)
        )
        await self._session.flush()
        records = tuple(
            (
                await self._session.scalars(
                    select(ReviewAdmissionIdempotencyRecord)
                    .where(
                        or_(
                            ReviewAdmissionIdempotencyRecord.idempotency_key
                            == value.idempotency_key,
                            ReviewAdmissionIdempotencyRecord.operation_id
                            == value.operation_id,
                            ReviewAdmissionIdempotencyRecord.admitting_checker_run_id
                            == value.admitting_checker_run_id,
                        )
                    )
                    .order_by(ReviewAdmissionIdempotencyRecord.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        if len(records) != 1 or not self._matches_reservation(records[0], value):
            raise ReviewAdmissionIdempotencyConflict("review_admission_idempotency_conflict")
        return ReviewAdmissionReservation(created=created_id is not None, record=records[0])

    async def commit_admission(
        self,
        *,
        reservation_id: UUID,
        queue_entry_id: UUID,
    ) -> ReviewAdmissionIdempotencyRecord:
        """Bind a pending reservation to its exact queue row without committing."""
        record = await self._session.scalar(
            update(ReviewAdmissionIdempotencyRecord)
            .where(
                ReviewAdmissionIdempotencyRecord.id == reservation_id,
                ReviewAdmissionIdempotencyRecord.status == "pending",
            )
            .values(
                status="committed",
                review_queue_entry_id=queue_entry_id,
                committed_at=text("statement_timestamp()"),
            )
            .returning(ReviewAdmissionIdempotencyRecord)
        )
        if record is None:
            raise ReviewAdmissionIdempotencyConflict("review_admission_not_pending")
        await self._session.flush()
        return record

    @staticmethod
    def _matches_reservation(
        record: ReviewAdmissionIdempotencyRecord,
        value: ReviewAdmissionReservationInput,
    ) -> bool:
        return (
            record.idempotency_key == value.idempotency_key
            and record.operation_id == value.operation_id
            and record.request_digest == value.request_digest
            and record.project_id == value.project_id
            and record.task_id == value.task_id
            and record.submission_id == value.submission_id
            and record.submission_version == value.submission_version
            and record.admitting_checker_run_id == value.admitting_checker_run_id
        )
