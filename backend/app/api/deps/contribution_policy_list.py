"""Compose the Finance list of every ContributionPolicy version through the shared project read runner."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.project_management_reads import ProjectManagementReadRunner, ProjectManagementReads
from app.db.session import get_db_session
from app.modules.authorization.api.management_reads import ProjectManagementReadGrant
from app.modules.contributions.api.policies import ContributionPolicyVersionListPort, ContributionPolicyVersionPage


class ContributionPolicyListRead:
    """D1: every stored version of the project's policies, oldest first, under a Finance grant."""

    def __init__(self, runner: ProjectManagementReadRunner, policies: ContributionPolicyVersionListPort):
        """Compose the read runner with the CON policy owner."""
        self._runner, self._policies = runner, policies

    async def list(self, *, project_id: UUID, limit: int, cursor: str | None) -> ContributionPolicyVersionPage:
        """Authorize ``contribution.policy.list``, then read one page of versions."""
        request = self._runner.request("contribution.policy.list", project_id, {
            "limit": limit, "order": "created_at_id_asc",
        }, cursor=cursor)

        async def read(grant: ProjectManagementReadGrant):
            items, more = await self._policies.read_versions(
                grant.project_id, after=self._runner.position(grant), limit=limit,
            )
            last = items[-1] if items else None
            return ContributionPolicyVersionPage(items=items, next_cursor=self._runner.next_cursor(
                request, more, last.created_at if last else None,
                last.contribution_policy_version_id if last else None,
            ))

        return await self._runner.run(request, read)


async def get_contribution_policy_list(
    runner: ProjectManagementReads, session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ContributionPolicyListRead:
    """Build the policy version list from request-scoped owner adapters."""
    from app.adapters.contributions import contribution_policy_version_list

    return ContributionPolicyListRead(runner, contribution_policy_version_list(session))
