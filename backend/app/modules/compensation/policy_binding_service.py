"""COMPENSATION-owned locked lookup for policy adapter bindings."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.compensation.api import (
    CompensationInstrumentType,
    LockedPolicyAdapterBindingFacts,
    PolicyAdapterBindingUnavailable,
)
from app.modules.compensation.models import ProjectCompensationAdapterBinding


class PolicyAdapterBindingLookup:
    """Retain one active same-project adapter-binding lock."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_policy_adapter_binding(
        self,
        *,
        project_id: UUID,
        adapter_binding_id: UUID,
        instrument_type: CompensationInstrumentType,
    ) -> LockedPolicyAdapterBindingFacts:
        """Return exact public facts while retaining the row fence."""
        binding = await self._session.scalar(
            select(ProjectCompensationAdapterBinding)
            .where(
                ProjectCompensationAdapterBinding.id == adapter_binding_id,
                ProjectCompensationAdapterBinding.project_id == str(project_id),
                ProjectCompensationAdapterBinding.instrument_type == instrument_type.value,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if binding is None or binding.status != "active":
            raise PolicyAdapterBindingUnavailable("contribution_policy_unavailable")
        return LockedPolicyAdapterBindingFacts(
            project_id=project_id,
            adapter_binding_id=UUID(str(binding.id)),
            instrument_type=instrument_type,
            binding_lifecycle_version=binding.binding_lifecycle_version,
        )
