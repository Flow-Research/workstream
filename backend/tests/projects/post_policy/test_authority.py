"""Real foreign principals and an exact separately authorized disclosure boundary."""

from tests.projects.guide_activation.source_fixtures import source_case

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import text
from app.core.identifiers import new_record_id

from app.modules.authorization.api import AuthorizationDenied
from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.api.post_policy import PostPolicyApproval, PostPolicyCorrection, PostPolicySelection
from tests.projects.guide_compilation.helpers import service_actor
from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor, revoke_review_grant
from .pg_support import PreparedPostPolicy, prepare_post_policy, operate


async def foreign_manager(factory, owner):
    from project_create_fixtures import seed_historical_project

    project = new_record_id()
    async with factory() as session, session.begin():
        await seed_historical_project(session, project_id=str(project), name='Foreign owner', slug=f'foreign-{project}')
    actor, grant = await seed_review_actor(factory, project)
    _, crossed_grant = await seed_review_actor(factory, project, actor=owner)
    return project, actor, grant, crossed_grant


async def state(factory):
    async with factory() as session:
        return tuple([await session.scalar(text(
            f"SELECT coalesce(jsonb_agg(to_jsonb(stored) ORDER BY to_jsonb(stored)::text), '[]'::jsonb) FROM {table} stored"
        )) for table in (
            'project_post_policy_operations', 'project_guide_proposal_corrections',
            'project_setup_runs', 'audit_events', 'checker_policies')])


async def test_stored_foreign_authority_cannot_mutate_replay_or_read_policy(clean_postgres_database):
    async with source_case(clean_postgres_database) as (values, factory, command, owner, grant):
        derive, projected = await prepare_post_policy(factory, command, owner, grant, service_actor(values), values)
        foreign_project, foreign, foreign_grant, crossed_grant = await foreign_manager(factory, owner)
        approval = PostPolicyApproval(target=projected.target, idempotency_key=uuid4())
        approved = await operate(factory, owner, command.project_id, grant, 'approve', approval)
        selection = PostPolicySelection(**derive.selection.model_dump(), policy_id=projected.target.policy_id)
        before = await state(factory)
        for actor, candidate_grant in (
            (foreign, foreign_grant), (owner, crossed_grant),
            (replace(owner, identity_link_id=foreign.identity_link_id), grant),
        ):
            for operation, payload in (
                ('derive', derive), ('approve', approval), ('review_package', selection),
                ('request_correction', PostPolicyCorrection(target=projected.target,
                    idempotency_key=uuid4(), reason='Foreign correction attempt')),
            ):
                with pytest.raises(GuideProposalError, match='authority_unavailable'):
                    await operate(factory, actor, command.project_id, candidate_grant, operation, payload)
        # Current authority for A reaches the repository, which must not resolve B's guide/policy.
        with pytest.raises(GuideProposalError, match='proposal_unavailable'):
            await operate(factory, foreign, foreign_project, foreign_grant, 'review_package',
                selection.model_copy(update={'project_id': foreign_project}))
        with pytest.raises(GuideProposalError, match='proposal_unavailable'):
            await operate(factory, service_actor(values), foreign_project, None, 'derive',
                derive.model_copy(update={'selection': derive.selection.model_copy(update={'project_id': foreign_project})}))
        assert await state(factory) == before
        assert await operate(factory, owner, command.project_id, grant, 'approve', approval) == approved


async def test_exact_draft_is_not_disclosed_when_read_decision_denies(clean_postgres_database, monkeypatch):
    async with source_case(clean_postgres_database) as (values, factory, command, actor, grant):
        derive, projected = await prepare_post_policy(factory, command, actor, grant, service_actor(values), values)
        selection = PostPolicySelection(**derive.selection.model_dump(), policy_id=projected.target.policy_id)
        before = await state(factory)
        original = PreparedPostPolicy.authorize_read
        seen = []

        async def deny(prepared, facts):
            await original(prepared, facts)
            seen.append(facts.policy_id)
            raise AuthorizationDenied('exact read decision denied')

        with monkeypatch.context() as patch:
            patch.setattr(PreparedPostPolicy, 'authorize_read', deny)
            with pytest.raises(GuideProposalError, match='authority_unavailable'):
                await operate(factory, actor, command.project_id, grant, 'review_package', selection)
        assert seen == [projected.target.policy_id]
        assert await state(factory) == before
        assert (await operate(factory, actor, command.project_id, grant, 'review_package', selection)).target == projected.target
        await revoke_review_grant(factory, actor, grant)
        revoked_state = await state(factory)
        with pytest.raises(GuideProposalError, match='authority_unavailable'):
            await operate(factory, actor, command.project_id, grant, 'review_package', selection)
        assert await state(factory) == revoked_state
