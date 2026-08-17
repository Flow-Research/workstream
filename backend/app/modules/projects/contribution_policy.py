"""PROJECTS-owned eligibility implementation for ContributionPolicy mutation."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.api import (
    ProjectContributionPolicyEligibilityFacts,
    ProjectContributionPolicyUnavailable,
)
from app.modules.projects.models import Project


class ProjectContributionPolicyEligibility:
    """Retain one eligible project lock in the caller transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind project eligibility checks to the caller transaction."""
        self._session = session

    async def lock_contribution_policy_project(
        self, project_id: UUID
    ) -> ProjectContributionPolicyEligibilityFacts:
        """Lock an exact non-retired project or conceal it."""
        project = await self._session.scalar(
            select(Project)
            .where(Project.id == str(project_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if project is None or project.status not in {"draft", "active"}:
            raise ProjectContributionPolicyUnavailable(
                "contribution_policy_unavailable"
            )
        return ProjectContributionPolicyEligibilityFacts(project_id=project_id)
