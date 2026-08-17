"""COMPENSATION-owned composition adapters."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.compensation.api import PolicyAdapterBindingPort
from app.modules.compensation.policy_binding_service import PolicyAdapterBindingLookup


def policy_adapter_binding_port(session: AsyncSession) -> PolicyAdapterBindingPort:
    """Construct the public locked policy-binding lookup."""
    return PolicyAdapterBindingLookup(session)
