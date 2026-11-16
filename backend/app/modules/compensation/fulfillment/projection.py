"""Rebuild fulfillment status from immutable, root-serialized evidence."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.compensation.api.fulfillment_evidence import (
    CompensationStatusProjection, FulfillmentEvidenceUnavailable,
)
from app.modules.compensation.fulfillment.models import (
    CompensationFulfillmentException, CompensationFulfillmentReceipt,
)
from app.modules.compensation.fulfillment.models import CompensationFulfillmentRoot


class CompensationStatusReader:
    """Read under the caller's authorized root custody; never mutate earning facts."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def read(self, root: CompensationFulfillmentRoot) -> CompensationStatusProjection:
        status, _, _, _ = await self.read_evidence(root)
        return status

    async def read_evidence(self, root: CompensationFulfillmentRoot):
        """Use bounded owner queries and actual append order for every latest value."""
        receipts = select(CompensationFulfillmentReceipt).where(
            CompensationFulfillmentReceipt.fulfillment_root_id == root.id,
        )
        latest = await self._session.scalar(receipts.order_by(
            CompensationFulfillmentReceipt.evidence_ordinal.desc(),
        ).limit(1).execution_options(populate_existing=True))
        fulfilled = await self._session.scalar(receipts.where(
            CompensationFulfillmentReceipt.reported_status == "fulfilled",
        ).execution_options(populate_existing=True))
        failed = await self._session.scalar(receipts.where(
            CompensationFulfillmentReceipt.reported_status == "failed",
        ).order_by(CompensationFulfillmentReceipt.evidence_ordinal.desc()).limit(1)
          .execution_options(populate_existing=True))
        exception = await self._session.scalar(select(CompensationFulfillmentException).where(
            CompensationFulfillmentException.fulfillment_root_id == root.id,
        ).order_by(CompensationFulfillmentException.evidence_ordinal.desc()).limit(1)
          .execution_options(populate_existing=True))
        if exception is not None and (
            fulfilled is None or exception.original_receipt_id != fulfilled.id
        ):
            raise FulfillmentEvidenceUnavailable("fulfillment_source_unavailable")
        latest_evidence = max(
            (value for value in (latest, exception) if value is not None),
            key=lambda value: value.evidence_ordinal, default=None,
        )
        status = CompensationStatusProjection(
            delivery_status=("acknowledged_by_adapter" if latest is not None else "pending_delivery"),
            fulfillment_status=("fulfilled" if fulfilled is not None else
                                "failed" if failed is not None else "pending"),
            fulfillment_attention_required=exception is not None,
            latest_receipt_id=latest.id if latest is not None else None,
            latest_exception_id=exception.id if exception is not None else None,
            last_failure_code=failed.report_body["failure_code"] if failed is not None else None,
            updated_at=latest_evidence.received_at if latest_evidence is not None else root.created_at,
        )
        return status, latest, fulfilled, exception
