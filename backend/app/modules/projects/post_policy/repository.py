"""Reuse finalized guide serialization for post-policy source and upstream custody."""

from uuid import UUID

from sqlalchemy import select

from app.modules.projects.api.guide_proposals import GuideProposalError, GuideProposalSelection
from app.modules.projects.guide_compilation.approval_custody import approved_projection_digest
from app.modules.projects.guide_compilation.proposal_repository import GuideProposalRepository
from app.modules.projects.models import PostSubmitCheckerPolicy

from .custody import load_post_policy_custody
from .models import PostPolicyOperation


class PostPolicyRepository:
    """Resolve exact targets only after the caller prepares all required authority."""

    def __init__(self, session):
        self.session = session
        self.proposals = GuideProposalRepository(session)

    async def lock_proposal(self, selection, *, allowed_guide_statuses=frozenset({"draft"})):
        return await self.proposals.lock(GuideProposalSelection(
            project_id=selection.project_id, guide_id=selection.guide_id,
            compilation_id=selection.compilation_id,
        ), allowed_guide_statuses=allowed_guide_statuses)

    async def require_current_upstream(self, locked):
        """A finalized draft alone is insufficient; require the approved chain tip."""
        custody = locked.view.approval_custody
        if not locked.current or custody is None or custody.successor is not None:
            raise GuideProposalError("proposal_stale")
        approved_projection_digest(locked.view)
        current = await self.proposals.current_approval(locked.target.guide_id)
        if (
            current is None or current.operation_id != custody.operation.operation_id
            or current.compilation_id != locked.target.compilation_id
            or current.target_digest != locked.target.digest
        ):
            raise GuideProposalError("proposal_stale")
        return custody.operation

    async def latest_policy(self, guide_id):
        return (await self.session.scalars(select(PostSubmitCheckerPolicy)
        .join(PostPolicyOperation, PostPolicyOperation.operation_id == PostSubmitCheckerPolicy.projection_operation_id)
        .where(PostSubmitCheckerPolicy.guide_id == str(guide_id))
        .order_by(PostPolicyOperation.target_json["proposal"]["setup_generation"].as_integer().desc())
        .limit(1).with_for_update().execution_options(populate_existing=True))).one_or_none()

    async def lock_policy(self, selection, *, allowed_guide_statuses=frozenset({"draft"})):
        locked = await self.lock_proposal(selection, allowed_guide_statuses=allowed_guide_statuses)
        policy = await self.session.scalar(select(PostSubmitCheckerPolicy).where(
            PostSubmitCheckerPolicy.id == str(selection.policy_id),
            PostSubmitCheckerPolicy.project_id == str(selection.project_id),
            PostSubmitCheckerPolicy.guide_id == str(selection.guide_id),
        ).with_for_update().execution_options(populate_existing=True))
        if policy is None:
            raise GuideProposalError("proposal_unavailable")
        custody = await load_post_policy_custody(self.session, policy)
        upstream = locked.view.approval_custody
        if (
            custody.target.proposal != locked.target or upstream is None
            or custody.target.upstream.operation_id != upstream.operation.operation_id
            or custody.target.upstream_output_digest != upstream.operation.output_digest
            or custody.target.upstream.model_dump(mode="json") != upstream.operation.receipt_json
        ):
            raise GuideProposalError("proposal_unavailable")
        return locked, policy, custody

    async def operation(self, operation_id: UUID):
        return await self.session.scalar(select(PostPolicyOperation).where(
            PostPolicyOperation.operation_id == operation_id,
        ).with_for_update())
