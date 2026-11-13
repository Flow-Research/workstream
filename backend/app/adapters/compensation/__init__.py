"""COMPENSATION-owned composition adapters."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.compensation.api import PolicyAdapterBindingPort
from app.modules.compensation.policy_binding_service import PolicyAdapterBindingLookup
from app.modules.compensation.api.awards import CompensationAwardConflict
from app.modules.reviews.api.lifecycle import JointLifecycleUnavailable


class FulfillmentLifecycleFenceAdapter:
    """Translate custody errors while retaining the exact supplied REV fence."""

    def __init__(self, fence):
        self._fence = fence

    async def acquire(self, expected_generation):
        try:
            return await self._fence.acquire(expected_generation)
        except JointLifecycleUnavailable as exc:
            raise CompensationAwardConflict("compensation_fulfillment_unavailable") from exc


def policy_adapter_binding_port(session: AsyncSession) -> PolicyAdapterBindingPort:
    """Construct the public locked policy-binding lookup."""
    return PolicyAdapterBindingLookup(session)


def compensation_award_participant(session, fence):
    """Construct the existing complete immutable award-set writer."""
    from app.modules.compensation.awards.participant import CompensationAwardParticipant
    from app.modules.compensation.fulfillment.service import CompensationFulfillmentParticipant
    from app.adapters.outbox import outbox_append

    return CompensationAwardParticipant(session, fulfillment=CompensationFulfillmentParticipant(
        session, fence=FulfillmentLifecycleFenceAdapter(fence), outbox=outbox_append(session),
        source=compensation_fulfillment_readiness(session),
    ))


def compensation_fulfillment_readiness(session):
    """Resolve deployment identity through the existing settings owner."""
    from app.core.config import get_settings
    from app.modules.compensation.fulfillment.service import CompensationFulfillmentReadiness

    return CompensationFulfillmentReadiness(session, get_settings().source_instance_id)


def contribution_award_read_port(session):
    """Read selected immutable awards without bindings, fulfillment or a second session."""
    from app.modules.compensation.awards.read_repository import ContributionAwardReadRepository

    return ContributionAwardReadRepository(session)


def contributor_award_totals_port(session):
    """Sum a contributor's immutable awards in the caller's snapshot."""
    from app.modules.compensation.awards.read_repository import ContributionAwardReadRepository

    return ContributionAwardReadRepository(session)


def project_award_totals_port(session):
    """Sum one project's immutable awards in the caller's snapshot."""
    from app.modules.compensation.awards.read_repository import ContributionAwardReadRepository

    return ContributionAwardReadRepository(session)
