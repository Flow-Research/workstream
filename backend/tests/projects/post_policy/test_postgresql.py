"""Canonical post-policy projection and decisions over complete PostgreSQL custody."""

from uuid import uuid4

from sqlalchemy import text

from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
from app.modules.projects.api.guide_proposals import GuideProposalApproval, GuideProposalSelection
from app.modules.projects.api.post_policy import PostPolicyApproval, PostPolicyDerive, PostPolicySelection
from app.modules.projects.post_policy.service import PostPolicyService
from tests.projects.guide_compilation.helpers import service_actor
from tests.projects.guide_compilation.proposals.pg_support import proposal_case, read_package
from tests.projects.guide_compilation.proposals.test_postgresql import approve
from .pg_support import PostAuthority


async def test_post_policy_operation_preserves_finalization_without_provider_or_evaluator_calls(clean_postgres_database, monkeypatch):
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        upstream = await approve(factory, command, actor, grant,
                                 GuideProposalApproval(target=package.target, idempotency_key=uuid4()))
        from app.core.hashing import canonical_json_hash
        payload = PostPolicyDerive(selection=GuideProposalSelection(
            project_id=command.project_id, guide_id=command.guide_id, compilation_id=command.compilation_id),
            upstream_approval_operation_id=upstream.operation_id,
            upstream_approval_output_digest=canonical_json_hash(upstream.model_dump(mode='json')))
        from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
        from app.modules.artifacts.guide_document_access import ScopedGuideDocumentGrant
        from tests.projects.guide_compilation.finalization.pg_support import stored_state

        async def forbidden(*args, **kwargs):
            raise AssertionError('post-policy operation accessed a runtime, document or evaluator')

        monkeypatch.setattr(OpenAIAgentSdkProjectGuideRuntime, 'compile_project_guide', forbidden)
        monkeypatch.setattr(ScopedGuideDocumentGrant, 'open', forbidden)
        from app.adapters.artifacts import CheckerPhaseService
        monkeypatch.setattr(CheckerPhaseService, 'evaluate_post_submission', forbidden)
        original = await stored_state(factory, command)
        receipts = []
        for _ in range(2):
            async with factory() as session, session.begin():
                service = PostPolicyService(session, PostAuthority(session, service_actor(values), command.project_id), current_post_submit_catalogue())
                receipts.append(await service.derive(payload, actor=service_actor(values), request_id=uuid4()))
        assert receipts[0] == receipts[1]
        target = receipts[0].target
        async with factory() as session, session.begin():
            service = PostPolicyService(session, PostAuthority(session, actor, command.project_id, grant), current_post_submit_catalogue())
            draft = await service.review_package(PostPolicySelection(**payload.selection.model_dump(), policy_id=target.policy_id), actor=actor, request_id=uuid4())
        assert draft.current and draft.lifecycle_status == 'compiled'
        assert draft.policy.policy_hash == target.policy_hash
        assert len(draft.policy.entries) == 8
        assert draft.proposal.target == package.target
        approval = PostPolicyApproval(target=target, idempotency_key=uuid4())
        approved = []
        for _ in range(2):
            async with factory() as session, session.begin():
                service = PostPolicyService(session, PostAuthority(session, actor, command.project_id, grant), current_post_submit_catalogue())
                approved.append(await service.approve(approval, actor=actor, request_id=uuid4()))
        assert approved[0] == approved[1]
        async with factory() as session:
            assert await session.scalar(text('SELECT count(*) FROM project_post_policy_operations')) == 2
            assert await session.scalar(text("SELECT lifecycle_status FROM checker_policies WHERE id=:id"), dict(id=str(target.policy_id))) == 'approved'

        assert (await stored_state(factory, command))[:2] == original[:2]
