"""Persistence operations for hidden compensation adapter-binding behavior."""

from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.compensation.models import (
    CompensationAdapterBindingLifecycleEvent,
    ProjectCompensationAdapterBinding,
)


def operation_advisory_lock_key(operation_id: UUID) -> int:
    """Derive the contract-fixed signed PostgreSQL advisory key."""
    raw = int.from_bytes(hashlib.sha256(operation_id.bytes).digest()[:8], "big")
    return raw - (1 << 64) if raw >= (1 << 63) else raw


class AdapterBindingRepository:
    """Flush-only repository for one caller-owned root transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind persistence to the caller-owned root transaction."""
        self._session = session

    async def lock_operation(self, operation_id: UUID) -> None:
        """Acquire the transaction-scoped operation fence."""
        await self._session.execute(
            text("select pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": operation_advisory_lock_key(operation_id)},
        )

    async def get_event_by_operation(
        self, operation_id: UUID
    ) -> CompensationAdapterBindingLifecycleEvent | None:
        """Load immutable recovery evidence for one operation."""
        return await self._session.scalar(
            select(CompensationAdapterBindingLifecycleEvent).where(
                CompensationAdapterBindingLifecycleEvent.operation_id == operation_id
            )
        )

    async def get_binding(
        self, project_id: UUID, adapter_binding_id: UUID, *, for_update: bool = False
    ) -> ProjectCompensationAdapterBinding | None:
        """Load one tenant-scoped binding, optionally for update."""
        query = select(ProjectCompensationAdapterBinding).where(
            ProjectCompensationAdapterBinding.project_id == str(project_id),
            ProjectCompensationAdapterBinding.id == adapter_binding_id,
        )
        if for_update:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def lock_creation_scope(self, project_id: UUID, instrument_type: str) -> None:
        """Serialize active binding changes for a project instrument."""
        key = f"compensation-adapter-binding:{project_id}:{instrument_type}"
        await self._session.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": key},
        )

    async def get_active_binding(
        self, project_id: UUID, instrument_type: str
    ) -> ProjectCompensationAdapterBinding | None:
        """Lock and return the current active project binding."""
        return await self._session.scalar(
            select(ProjectCompensationAdapterBinding)
            .where(
                ProjectCompensationAdapterBinding.project_id == str(project_id),
                ProjectCompensationAdapterBinding.instrument_type == instrument_type,
                ProjectCompensationAdapterBinding.status == "active",
            )
            .with_for_update()
        )

    async def get_prior_suspension_event(
        self, adapter_binding_id: UUID, lifecycle_version: int
    ) -> CompensationAdapterBindingLifecycleEvent | None:
        """Load the immediately preceding suspension event."""
        return await self._session.scalar(
            select(CompensationAdapterBindingLifecycleEvent).where(
                CompensationAdapterBindingLifecycleEvent.adapter_binding_id
                == adapter_binding_id,
                CompensationAdapterBindingLifecycleEvent.to_lifecycle_version
                == lifecycle_version,
                CompensationAdapterBindingLifecycleEvent.event_type == "suspended",
            )
        )

    async def add_binding_and_event(
        self,
        binding: ProjectCompensationAdapterBinding,
        event: CompensationAdapterBindingLifecycleEvent,
    ) -> None:
        """Flush a binding and its mandatory created event together."""
        self._session.add_all((binding, event))
        await self._session.flush()
        await self._session.refresh(binding)
        await self._session.refresh(event)

    async def flush_event(
        self, event: CompensationAdapterBindingLifecycleEvent
    ) -> None:
        """Flush an event with the pending binding transition."""
        self._session.add(event)
        await self._session.flush()
        await self._session.refresh(event)
