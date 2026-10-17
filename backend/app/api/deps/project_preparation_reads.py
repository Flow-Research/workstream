"""Compose a project's ZIP preparation list through the shared project management read runner."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.project_management_reads import ProjectManagementReadRunner, ProjectManagementReads
from app.db.session import get_db_session
from app.modules.artifacts.api.submission_preparation import (
    PreparationOutcome, ProjectSubmissionBundlePreparationPage, SubmissionBundlePreparationReadPort,
)
from app.modules.authorization.api.management_reads import ProjectManagementReadGrant
from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitUnavailable


class ProjectPreparationReads:
    """C8: a project's ZIP preparations across contributors, newest first, with finding counts only."""

    def __init__(self, runner: ProjectManagementReadRunner, preparations: SubmissionBundlePreparationReadPort):
        """Compose the read runner with the ART preparation projection."""
        self._runner, self._preparations = runner, preparations

    async def list(
        self, *, project_id: UUID, outcome: PreparationOutcome | None, limit: int, cursor: str | None,
    ) -> ProjectSubmissionBundlePreparationPage:
        """List preparations, optionally of one intake outcome, under a Project Manager grant."""
        request = self._runner.request("project.submission_bundle_preparation.list", project_id, {
            "limit": limit, "order": "created_at_id_desc", "outcome": outcome,
        }, cursor=cursor)

        async def read(grant: ProjectManagementReadGrant):
            items, more = await self._preparations.read_project(
                project_id=grant.project_id, outcome=outcome, limit=limit, before=self._runner.position(grant),
            )
            last = items[-1] if items else None
            return ProjectSubmissionBundlePreparationPage(items=items, next_cursor=self._runner.next_cursor(
                request, more, last.created_at if last else None, last.preparation_id if last else None,
            ))

        return await self._runner.run(request, read, faults=(SelectedPreSubmitUnavailable,))


async def get_project_preparation_reads(
    runner: ProjectManagementReads, session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectPreparationReads:
    """Build the project preparation read from request-scoped owner adapters."""
    from app.adapters.artifacts import submission_bundle_preparation_reader

    return ProjectPreparationReads(runner, submission_bundle_preparation_reader(session))
