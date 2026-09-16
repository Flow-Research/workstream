"""Complete active or exact frozen guide context under the caller's transaction."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.api import (
    ProjectLockedPolicyContextFacts,
    ProjectLockedPolicyContextRequest,
    ProjectLockedPolicyContextUnavailable,
    ProjectGuideSetupFinalizationError,
    ProjectDisplayFacts,
)
from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.api.post_policy import PostPolicySelection
from app.modules.projects.guide_activation.custody import load_guide_activation
from app.modules.projects.guide_compilation.repository import GuideCompilationIntegrityError
from app.modules.projects.locked_policy_projection import complete_context
from app.modules.projects.models import Project, ProjectGuide
from app.modules.projects.post_policy.repository import PostPolicyRepository
from app.modules.projects.repository import ProjectRepository


class ProjectLockedPolicyRepository:
    """Resolve one complete graph without current CON or catalogue selection."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read_project_display(self, project_id: UUID) -> ProjectDisplayFacts | None:
        """Copy stored scalars without refreshing, flushing or locking caller-owned rows."""
        with self._session.no_autoflush:
            row = (await self._session.execute(
                select(Project.id, Project.name, Project.slug, Project.description)
                .where(Project.id == str(project_id))
            )).one_or_none()
        return None if row is None else ProjectDisplayFacts(
            id=UUID(row.id), name=row.name, slug=row.slug, description=row.description,
        )

    async def lock_active_policy_context(self, project_id: UUID) -> ProjectLockedPolicyContextFacts:
        """Select the sole active guide while retaining the Project fence."""
        return await self._resolve(project_id, None)

    async def lock_locked_policy_context(
        self, request: ProjectLockedPolicyContextRequest
    ) -> ProjectLockedPolicyContextFacts:
        """Resolve only the stored selectors, including a superseded guide."""
        return await self._resolve(request.project_id, request)

    async def _resolve(self, project_id, request):
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise ProjectLockedPolicyContextUnavailable("project_locked_policy_context_changed")
        try:
            # Reads must neither flush the caller's pending writes nor commit them.
            with self._session.no_autoflush:
                return await self._load(project_id, request)
        except (
            ValueError,
            TypeError,
            GuideProposalError,
            ProjectGuideSetupFinalizationError,
            GuideCompilationIntegrityError,
        ) as exc:
            raise ProjectLockedPolicyContextUnavailable(
                "project_locked_policy_context_changed"
            ) from exc

    async def _load(self, project_id, request):
        project = await self._session.scalar(
            select(Project)
            .where(
                Project.id == str(project_id),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if project is None or project.status != "active":
            raise ValueError("active project unavailable")
        selection = select(ProjectGuide).where(ProjectGuide.project_id == str(project_id))
        selection = selection.where(
            ProjectGuide.version == request.guide_version
            if request
            else ProjectGuide.status == "active"
        )
        # Do not take Guide before Attempt: finalization owns Attempt -> Guide.
        guide = (
            await self._session.scalars(selection.execution_options(populate_existing=True))
        ).one_or_none()
        if guide is None:
            raise ValueError("selected guide unavailable")
        receipt = await load_guide_activation(self._session, guide)
        target = receipt.command.target
        locked, post_policy, post_custody = await PostPolicyRepository(self._session).lock_policy(
            PostPolicySelection(
                project_id=project_id,
                guide_id=target.proposal.guide_id,
                compilation_id=target.proposal.compilation_id,
                policy_id=target.policy_id,
            ),
            allowed_guide_statuses=frozenset({"active", "superseded"}),
        )
        guide = locked.view.guide
        refreshed = await load_guide_activation(self._session, guide)
        if refreshed != receipt or (request is None and guide.status != "active"):
            raise ValueError("selected activation changed")
        projects = ProjectRepository(self._session)
        review = await projects.lock_review_policy(guide.project_id, guide.version)
        revision = await projects.lock_revision_policy(guide.project_id, guide.version)
        facts = complete_context(locked, post_policy, post_custody, refreshed, review, revision, project)
        if request is not None and request != ProjectLockedPolicyContextRequest(
            project_id=facts.project_id,
            guide_version=facts.guide_version,
            source_snapshot_id=facts.source_snapshot_id,
            source_snapshot_hash=facts.source_snapshot_hash,
            effective_policy_id=facts.effective_policy_id,
            effective_policy_hash=facts.effective_policy_hash,
            pre_submit_policy_id=facts.pre_submit_policy_id,
            pre_submit_policy_bundle_hash=facts.pre_submit_policy_bundle_hash,
        ):
            raise ValueError("frozen context selectors differ")
        return facts
