"""CONTRIBUTIONS-owned composition adapters."""

from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.contributions.api.published_selection import PublishedContributionPolicyPort

from app.adapters.compensation import policy_adapter_binding_port
from app.adapters.projects import project_contribution_policy_eligibility_port
from app.modules.contributions.api import (
    ContributionPolicyOperationsPort,
    ContributionPolicyMutationAuthorizationPort,
    ContributionPolicyReadAuthorizationPort,
    ContributionPolicyValidationPort,
    LockedCompensationTermsPort,
)
from app.modules.contributions.service import ContributionPolicyService
from app.modules.contributions.selected_policy_validation import (
    SelectedContributionPolicyValidation,
)


def contribution_policy_service(
    session: AsyncSession,
    *,
    read_authorization: ContributionPolicyReadAuthorizationPort | None = None,
    mutation_authorization: ContributionPolicyMutationAuthorizationPort | None = None,
) -> ContributionPolicyOperationsPort:
    """Compose policy behavior exclusively through public owner ports."""
    return ContributionPolicyService(
        session,
        read_authorization=read_authorization,
        mutation_authorization=mutation_authorization,
        projects=project_contribution_policy_eligibility_port(session),
        bindings=policy_adapter_binding_port(session),
    )


def contribution_policy_validation_port(
    session: AsyncSession,
) -> ContributionPolicyValidationPort:
    """Compose exact validation with owner locks in the caller transaction."""
    return SelectedContributionPolicyValidation(
        session,
        projects=project_contribution_policy_eligibility_port(session),
        bindings=policy_adapter_binding_port(session),
    )


def published_contribution_policy_port(session: AsyncSession) -> PublishedContributionPolicyPort:
    """Compose the bounded internal selector read; callers own disclosure authority."""
    from app.modules.contributions.repository import ContributionPolicyRepository
    return ContributionPolicyRepository(session)


def locked_compensation_terms_port(session: AsyncSession) -> LockedCompensationTermsPort:
    """Compose the contributor-safe locked-version projection at the CON owner."""
    from app.modules.contributions.repository import ContributionPolicyRepository
    return ContributionPolicyRepository(session)


def submitter_contribution_participant(session, fence):
    """Construct CON's atomic contribution and complete award participant."""
    from app.modules.contributions.records.participant import SubmitterContributionParticipant
    from app.adapters.compensation import compensation_award_participant

    return SubmitterContributionParticipant(
        session, fence=fence, awards=compensation_award_participant(session)
    )
