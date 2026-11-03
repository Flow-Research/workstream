"""Canonical post-policy projection and decisions over complete PostgreSQL custody."""

from tests.projects.guide_activation.source_fixtures import source_case

from app.adapters.contributions import published_contribution_policy_port
from app.adapters.projects.contribution_validation import GuideContributionPolicyDiscovery

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api.guide_proposals import GuideProposalApproval, GuideProposalSelection
from app.modules.projects.api.post_policy import PostPolicyApproval, PostPolicyDerive, PostPolicySelection
from app.modules.projects.post_policy.service import PostPolicyService
from app.modules.projects.post_policy.compiler import compile_saved_post_policy
from app.modules.checkers.api.external_policy import validate_stored_external_checker_policies
from tests.checkers.external.support import post_registry_spec
from tests.projects.guide_compilation.helpers import service_actor
from tests.projects.guide_compilation.proposals.pg_support import read_package
from tests.projects.guide_compilation.proposals.test_postgresql import approve
from .pg_support import PostAuthority


async def test_post_policy_operation_preserves_finalization_without_provider_or_evaluator_calls(clean_postgres_database, monkeypatch):
    async with source_case(clean_postgres_database, post_submit_registry_spec=post_registry_spec()) as (values, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        upstream = await approve(factory, command, actor, grant,
                                 GuideProposalApproval(
                                     target=package.target,
                                     pre_submit_attachments=values["pre_submit_attachments"],
                                     post_submit_attachments=values["post_submit_attachments"],
                                     idempotency_key=uuid4(),
                                 ))
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
        from app.modules.checkers.execution import PostSubmissionExecutor
        monkeypatch.setattr(PostSubmissionExecutor, 'evaluate_post_submission', forbidden)
        original = await stored_state(factory, command)
        receipts = []
        for _ in range(2):
            async with factory() as session, session.begin():
                service = PostPolicyService(session, PostAuthority(session, service_actor(values), command.project_id))
                receipts.append(await service.derive(payload, actor=service_actor(values), request_id=uuid4()))
        assert receipts[0] == receipts[1]
        target = receipts[0].target
        async with factory() as session, session.begin():
            service = PostPolicyService(session, PostAuthority(session, actor, command.project_id, grant))
            draft = await service.review_package(PostPolicySelection(**payload.selection.model_dump(), policy_id=target.policy_id), actor=actor, request_id=uuid4(), contribution=GuideContributionPolicyDiscovery(published_contribution_policy_port(session)))
        assert draft.current and draft.lifecycle_status == 'compiled'
        assert draft.policy.policy_sha256 == target.policy_hash
        async with factory() as session:
            approved_plan = await session.scalar(text(
                "SELECT effective_pre_submit_plan FROM project_guide_proposal_approvals WHERE operation_id=:id"
            ), {"id": upstream.operation_id})
        policies = validate_stored_external_checker_policies(approved_plan)
        assert draft.policy == policies.post_submit
        assert len(draft.policy.entries) == 1
        assert draft.policy.entries[0].registry.capability_id == post_registry_spec().capability_id
        assert compile_saved_post_policy(policies=policies) == draft.policy
        changed_plan = policies.model_dump(mode="json")
        changed_plan["post_submit"]["entries"][0]["requirement_id"] = "substituted_member"
        with pytest.raises(ValueError, match="digest mismatch"):
            validate_stored_external_checker_policies(changed_plan)
        assert draft.proposal.target == package.target
        approval = PostPolicyApproval(target=target, idempotency_key=uuid4())
        approved = []
        for _ in range(2):
            async with factory() as session, session.begin():
                service = PostPolicyService(session, PostAuthority(session, actor, command.project_id, grant))
                approved.append(await service.approve(approval, actor=actor, request_id=uuid4()))
        assert approved[0] == approved[1]
        async with factory() as session:
            assert await session.scalar(text('SELECT count(*) FROM project_post_policy_operations')) == 2
            assert await session.scalar(text("SELECT lifecycle_status FROM checker_policies WHERE id=:id"), dict(id=str(target.policy_id))) == 'approved'

        assert (await stored_state(factory, command))[:2] == original[:2]
