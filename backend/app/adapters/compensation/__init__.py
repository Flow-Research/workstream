"""COMPENSATION-owned composition adapters."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.compensation.api import PolicyAdapterBindingPort
from app.modules.compensation.policy_binding_service import PolicyAdapterBindingLookup


def policy_adapter_binding_port(session: AsyncSession) -> PolicyAdapterBindingPort:
    """Construct the public locked policy-binding lookup."""
    return PolicyAdapterBindingLookup(session)


def compensation_award_participant(session):
    """Construct the existing complete immutable award-set writer."""
    from app.modules.compensation.awards.participant import CompensationAwardParticipant

    return CompensationAwardParticipant(session)


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
