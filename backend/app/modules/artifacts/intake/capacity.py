"""Physical source-byte reservations, separate from SHA-deduplicated ART charges."""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.api.submission_intake import SubmissionSourceCapacityLimits
from app.modules.artifacts.intake.models import (
    SubmissionIntakeOperation, SubmissionSourceCapacityProfile, SubmissionSourceCharge,
)


class SubmissionSourceCapacityConflict(RuntimeError):
    """Stable allocation conflict; never a checker verdict or storage permission."""


class SubmissionSourceCapacity:
    """Flush-only capacity owner; caller holds TASK and operation custody first."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise SubmissionSourceCapacityConflict("source_capacity_requires_root_transaction")

    async def _profile(
        self, operation: SubmissionIntakeOperation, limits: SubmissionSourceCapacityLimits | None,
    ) -> SubmissionSourceCapacityProfile:
        self._require_transaction()
        if limits is not None:
            limits = SubmissionSourceCapacityLimits.model_validate(limits)
            await self._session.execute(insert(SubmissionSourceCapacityProfile).values(
                namespace_id=operation.namespace_id,
                namespace_fingerprint=operation.namespace_fingerprint,
                configuration_sha256=limits.configuration_sha256(),
                **limits.model_dump(),
            ).on_conflict_do_nothing(index_elements=["namespace_id"]))
        profile = await self._session.scalar(select(SubmissionSourceCapacityProfile).where(
            SubmissionSourceCapacityProfile.namespace_id == operation.namespace_id,
        ).with_for_update().execution_options(populate_existing=True))
        if (profile is None or profile.namespace_fingerprint != operation.namespace_fingerprint
                or (limits is not None and profile.configuration_sha256 != limits.configuration_sha256())):
            raise SubmissionSourceCapacityConflict("source_capacity_configuration_mismatch")
        return profile

    async def reserve(
        self, operation: SubmissionIntakeOperation, *, limits: SubmissionSourceCapacityLimits,
        declared_raw_bytes: int | None,
    ) -> SubmissionSourceCharge:
        """Reserve declared bytes or the raw ceiling before any provider write."""
        if declared_raw_bytes is not None and (
            type(declared_raw_bytes) is not int or not 1 <= declared_raw_bytes <= operation.maximum_raw_bytes
        ):
            raise SubmissionSourceCapacityConflict("source_declared_size_invalid")
        profile = await self._profile(operation, limits)
        reserved = declared_raw_bytes if declared_raw_bytes is not None else operation.maximum_raw_bytes
        existing = await self._session.get(SubmissionSourceCharge, operation.id)
        if existing is not None:
            if existing.declared_raw_bytes != declared_raw_bytes or existing.reserved_bytes != reserved:
                raise SubmissionSourceCapacityConflict("source_reservation_replay_mismatch")
            return existing
        charge, parent = SubmissionSourceCharge, SubmissionIntakeOperation
        totals = (await self._session.execute(select(
            func.coalesce(func.sum(charge.accounted_bytes), 0),
            func.coalesce(func.sum(charge.accounted_bytes).filter(parent.project_id == operation.project_id), 0),
            func.coalesce(func.sum(charge.accounted_bytes).filter(parent.actor_profile_id == operation.actor_profile_id), 0),
            func.coalesce(func.sum(charge.accounted_bytes).filter(parent.task_id == operation.task_id), 0),
        ).join(parent, parent.id == charge.operation_id).where(
            parent.namespace_id == operation.namespace_id,
            parent.namespace_fingerprint == operation.namespace_fingerprint,
        ))).one()
        ceilings = (profile.maximum_total_bytes, profile.maximum_project_bytes,
                    profile.maximum_producer_bytes, profile.maximum_task_bytes)
        if any(limit is not None and used + reserved > limit for used, limit in zip(totals, ceilings, strict=True)):
            raise SubmissionSourceCapacityConflict("source_capacity_exhausted")
        row = SubmissionSourceCharge(
            operation_id=operation.id, declared_raw_bytes=declared_raw_bytes,
            reserved_bytes=reserved, accounted_bytes=reserved, state="reserved",
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def seal(self, operation: SubmissionIntakeOperation) -> None:
        """Convert only unused allowance; terminal failures never reclaim bytes."""
        await self._profile(operation, None)
        charge = await self._session.scalar(select(SubmissionSourceCharge).where(
            SubmissionSourceCharge.operation_id == operation.id,
        ).with_for_update().execution_options(populate_existing=True))
        if (charge is None or operation.provider_generation is None or operation.raw_byte_count is None
                or operation.raw_byte_count > charge.reserved_bytes
                or (charge.declared_raw_bytes is not None and charge.declared_raw_bytes != operation.raw_byte_count)):
            raise SubmissionSourceCapacityConflict("source_sealed_charge_mismatch")
        if charge.state == "sealed":
            if charge.accounted_bytes != operation.raw_byte_count:
                raise SubmissionSourceCapacityConflict("source_sealed_charge_mismatch")
            return
        charge.state, charge.accounted_bytes = "sealed", operation.raw_byte_count
        charge.sealed_at = func.clock_timestamp()
        await self._session.flush()
