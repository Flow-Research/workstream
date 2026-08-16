"""PROJECTS-owned compensation-binding eligibility implementation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.api import (
    ProjectCompensationBindingEligibilityFacts,
    ProjectCompensationBindingUnavailable,
)
from app.modules.projects.models import Project


class ProjectCompensationBindingEligibility:
    """Retain one eligible project lock in the caller transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_compensation_binding_project(
        self, project_id: UUID
    ) -> ProjectCompensationBindingEligibilityFacts:
        """Lock the exact non-retired project or return one concealed denial."""
        project = await self._session.scalar(
            select(Project)
            .where(Project.id == str(project_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if project is None or project.status not in {"draft", "active"}:
            raise ProjectCompensationBindingUnavailable(
                "project_compensation_binding_unavailable"
            )
        return ProjectCompensationBindingEligibilityFacts(project_id=project_id)
