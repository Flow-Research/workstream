"""Public locked adapter-binding facts for contribution policies."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.compensation.api.instruments import CompensationInstrumentType


class PolicyAdapterBindingUnavailable(RuntimeError):
    """Conceal an absent, inactive, or foreign adapter binding."""


@dataclass(frozen=True, slots=True, kw_only=True)
class LockedPolicyAdapterBindingFacts:
    """Exact active binding retained under a COMPENSATION-owned row lock."""

    project_id: UUID
    adapter_binding_id: UUID
    instrument_type: CompensationInstrumentType
    binding_lifecycle_version: int


class PolicyAdapterBindingPort(Protocol):
    """Lock one exact active same-project adapter binding."""

    async def lock_policy_adapter_binding(
        self,
        *,
        project_id: UUID,
        adapter_binding_id: UUID,
        instrument_type: CompensationInstrumentType,
    ) -> LockedPolicyAdapterBindingFacts:
        """Retain the binding fence through the caller-owned transaction."""
