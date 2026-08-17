"""PROJECT-owned composition adapters."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.api import (
    ProjectContributionPolicyEligibilityPort,
    ProjectLockedPolicyContextPort,
)
from app.modules.projects.contribution_policy import ProjectContributionPolicyEligibility
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository


def project_locked_policy_context_port(
    session: AsyncSession,
) -> ProjectLockedPolicyContextPort:
    """Bind the public PROJECT locked-policy port to its repository."""
    return ProjectLockedPolicyRepository(session)


def project_contribution_policy_eligibility_port(
    session: AsyncSession,
) -> ProjectContributionPolicyEligibilityPort:
    """Construct the PROJECTS-owned policy eligibility port."""
    return ProjectContributionPolicyEligibility(session)
