"""Public PROJECTS eligibility contract for ContributionPolicy mutation."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class ProjectContributionPolicyUnavailable(RuntimeError):
    """Conceal an absent or ineligible policy-owning project."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectContributionPolicyEligibilityFacts:
    """Exact eligible project retained under a PROJECTS-owned lock."""

    project_id: UUID


class ProjectContributionPolicyEligibilityPort(Protocol):
    """Lock and validate one project for policy mutation."""

    async def lock_contribution_policy_project(
        self, project_id: UUID
    ) -> ProjectContributionPolicyEligibilityFacts:
        """Retain the project eligibility fence through mutation."""
