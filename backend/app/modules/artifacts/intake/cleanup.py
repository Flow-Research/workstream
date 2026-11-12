"""Private sealed-source cleanup custody; no provider I/O or service authority.

The composition root must authorize cleanup and act only on a committed claim.
This owner retains uncertain targets and releases charges only with both exact
object absence and settled upload-part obligations supplied by that coordinator.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, text

from app.modules.artifacts.api.submission_intake import SealedSubmissionSource
from app.modules.artifacts.intake.capacity import SubmissionSourceCapacity
from app.modules.artifacts.intake.models import SubmissionSourceCleanupClaim
from app.modules.artifacts.intake.repository import IntakeCustodyConflict, SubmissionIntakeRepository


@dataclass(frozen=True, slots=True)
class SealedSourceCleanupClaim:
    """Exact durable deletion target; a copied value grants no deletion authority."""

    claim_id: UUID
    generation: int
    source: SealedSubmissionSource
    lease_expires_at: datetime
    confirmed: bool


def _claim_value(row: SubmissionSourceCleanupClaim) -> SealedSourceCleanupClaim:
    """Recover typed source facts from persisted canonical JSON."""
    import json
    return SealedSourceCleanupClaim(
        UUID(row.claim_id), row.generation,
        SealedSubmissionSource.model_validate_json(json.dumps(row.source)),
        row.lease_expires_at, row.confirmed_at is not None,
    )


class SealedSourceCleanup:
    """Flush-only ownership: caller supplies current authority and root commits."""

    def __init__(self, session, tasks):
        self._session = session
        self._intake = SubmissionIntakeRepository(session, tasks)

    async def _locked(self, operation_id):
        operation = await self._intake._lock(operation_id)
        await self._session.execute(text(
            "SELECT public.require_sealed_source_cleanup(o) "
            "FROM public.submission_intake_operations o WHERE id=:id"
        ), {"id": operation.id})
        row = await self._session.scalar(select(SubmissionSourceCleanupClaim).where(
            SubmissionSourceCleanupClaim.operation_id == operation.id,
        ).with_for_update().execution_options(populate_existing=True))
        return operation, row

    async def claim(self, operation_id: UUID, claim_id: UUID, *, lease_duration: timedelta) -> SealedSourceCleanupClaim:
        """Claim only a stable eligible source; never resume foreground work."""
        if (type(claim_id) is not UUID or claim_id.version != 7
                or type(lease_duration) is not timedelta or lease_duration <= timedelta(0)):
            raise ValueError("source cleanup lease is invalid")
        operation, row = await self._locked(operation_id)
        now = await self._session.scalar(select(func.clock_timestamp()))
        if row is not None:
            if row.confirmed_at is not None:
                return _claim_value(row)
            if row.claim_id == str(claim_id):
                if row.lease_expires_at <= now:
                    raise IntakeCustodyConflict("source_cleanup_stale")
                return _claim_value(row)
            if row.lease_expires_at > now:
                raise IntakeCustodyConflict("source_cleanup_busy")
            row.claim_id, row.generation = str(claim_id), row.generation + 1
            row.claimed_at, row.lease_expires_at = now, now + lease_duration
        else:
            row = SubmissionSourceCleanupClaim(
                operation_id=operation.id, claim_id=str(claim_id), generation=1,
                source=self._intake._sealed_source(operation).model_dump(mode="json"),
                claimed_at=now, lease_expires_at=now + lease_duration,
            )
            self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _claim_value(row)

    async def confirm(self, claim: SealedSourceCleanupClaim, *, object_absent: bool,
                      writes_settled: bool, parts_absent: bool) -> None:
        """Commit exact absence and charge release together, never on an ACK."""
        if object_absent is not True or writes_settled is not True or parts_absent is not True:
            raise IntakeCustodyConflict("source_cleanup_unresolved")
        operation, row = await self._locked(claim.source.location.operation_id)
        if (row is None or row.claim_id != str(claim.claim_id) or row.generation != claim.generation
                or row.source != claim.source.model_dump(mode="json")):
            raise IntakeCustodyConflict("source_cleanup_stale")
        if row.confirmed_at is not None:
            return
        now = await self._session.scalar(select(func.clock_timestamp()))
        if row.lease_expires_at <= now:
            raise IntakeCustodyConflict("source_cleanup_stale")
        row.confirmed_at = now
        await self._session.flush()
        await SubmissionSourceCapacity(self._session).release_confirmed(operation)
