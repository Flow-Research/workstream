"""Compose a project's guide reads through the shared project management read runner."""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.project_management_reads import (
    READ_FAULTS, ProjectManagementReadRunner, ProjectManagementReads, project_read_unavailable,
)
from app.core.api_controls import StructuredHTTPException
from app.db.session import get_db_session
from app.modules.projects.api.guide_activation import GuideActivationReadiness, GuideActivationReadinessPort
from app.modules.projects.api.guide_activation_context import GuideContributionDiscoveryPort
from app.modules.projects.api.guide_documents import GuideDocumentUnavailable
from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.api.guide_reads import (
    GuideStatus, ProjectGuideDetail, ProjectGuideDocumentContentPort, ProjectGuidePage, ProjectGuideReadPort,
    ProjectGuideReadUnavailable, VerifiedGuideDocumentRead,
)

_FAULTS = (ProjectGuideReadUnavailable, GuideProposalError)


class ProjectGuideReadOperation:
    """C1–C3 and C9 over the shared runner; the owner proves the guide or document is in the project."""

    def __init__(
        self, runner: ProjectManagementReadRunner, *,
        guides: ProjectGuideReadPort, activation: GuideActivationReadinessPort,
        contribution: GuideContributionDiscoveryPort, documents: ProjectGuideDocumentContentPort,
    ) -> None:
        """Compose the read runner and the owner read ports for one request."""
        self._runner = runner
        self._guides, self._activation = guides, activation
        self._contribution, self._documents = contribution, documents

    async def guides(self, project_id: UUID, *, status: GuideStatus | None, limit: int, cursor: str | None):
        """C1: the project's guides by creation order, optionally by stored status."""
        request = self._runner.request("project.guide.list", project_id, {
            "limit": limit, "order": "created_at_id_asc", "status": status,
        }, cursor=cursor)

        async def read(grant):
            """One page of the project's guides after the verified position."""
            items, more = await self._guides.list_guides(
                project_id, status=status, after=self._runner.position(grant), limit=limit,
            )
            last = items[-1] if items else None
            return ProjectGuidePage(items=items, next_cursor=self._runner.next_cursor(
                request, more, last.created_at if last else None, last.guide_id if last else None,
            ))

        return await self._runner.run(request, read, faults=_FAULTS)

    async def guide(self, project_id: UUID, guide_id: UUID) -> ProjectGuideDetail:
        """C2: one guide of the project with documents, selected policies and setup lineage."""
        request = self._runner.request("project.guide.read", project_id, {}, resource_id=guide_id)

        async def read(grant):
            """The guide when it belongs to the project, else the concealed answer."""
            detail = await self._guides.read_guide(project_id, guide_id)
            if detail is None:
                raise await self._runner.conceal()
            return detail

        return await self._runner.run(request, read, faults=_FAULTS)

    async def activation_readiness(self, project_id: UUID, guide_id: UUID) -> GuideActivationReadiness:
        """C3: activation's own conditions over the current selections, with no write or authority use."""
        request = self._runner.request("project.guide.activation_readiness.read", project_id, {}, resource_id=guide_id)

        async def read(grant):
            """Readiness for a guide of the project, else the concealed answer."""
            if not await self._guides.guide_in_project(project_id, guide_id):
                raise await self._runner.conceal()
            return await self._activation.readiness(project_id, guide_id, contribution=self._contribution)

        return await self._runner.run(request, read, faults=_FAULTS)

    @asynccontextmanager
    async def document(
        self, project_id: UUID, guide_id: UUID, document_id: UUID,
    ) -> AsyncIterator[VerifiedGuideDocumentRead]:
        """C9: commit the decision only after the original is verified, then serve the staged bytes.

        The provider is opened only after AUTH allows the read and the owner
        proves the document belongs to a guide of the project.
        """
        request = self._runner.request("project.guide.document.read", project_id, {
            "guide_id": str(guide_id),
        }, resource_id=document_id)
        async with AsyncExitStack() as stack:
            try:
                await self._runner.snapshot()
                await self._runner.authorize(request)
                selection = await self._guides.select_document(project_id, guide_id, document_id)
                if selection is None:
                    raise await self._runner.conceal()
                if selection.original is None:
                    await self._runner.commit()
                    raise StructuredHTTPException(
                        status_code=409, detail="Guide document not uploaded",
                        error_code="guide_document_not_uploaded", error_message="Guide document not uploaded",
                    )
                read = await stack.enter_async_context(self._documents.open(project_id, selection.original))
                await self._runner.commit()
            except GuideDocumentUnavailable as exc:
                await self._runner.rollback()
                raise StructuredHTTPException(
                    status_code=503, detail="Guide document integrity unavailable",
                    error_code="guide_document_integrity_unavailable",
                    error_message="Guide document integrity unavailable", retryable=False,
                ) from exc
            except (*READ_FAULTS, *_FAULTS) as exc:
                await self._runner.rollback()
                raise project_read_unavailable() from exc
            yield read


async def get_project_guide_reads(
    request: Request, runner: ProjectManagementReads, session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectGuideReadOperation:
    """Build the guide read operation from request-scoped owner adapters."""
    from app.adapters.artifacts import project_guide_documents_port
    from app.adapters.contributions import contribution_policy_validation_port, published_contribution_policy_port
    from app.adapters.projects import project_guide_activation_readiness_port, project_guide_reader
    from app.adapters.projects.contribution_validation import (
        GuideContributionPolicyDiscovery, GuideContributionPolicyValidation,
    )

    return ProjectGuideReadOperation(
        runner, guides=project_guide_reader(session),
        activation=project_guide_activation_readiness_port(
            session, contribution=GuideContributionPolicyValidation(contribution_policy_validation_port(session)),
        ),
        contribution=GuideContributionPolicyDiscovery(published_contribution_policy_port(session)),
        documents=project_guide_documents_port(session, request.app.state.settings),
    )
