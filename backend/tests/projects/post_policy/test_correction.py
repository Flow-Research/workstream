"""Dual-authority correction preserves immutable finalization and one successor."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.api.post_policy import PostPolicyCorrection, PostPolicySelection
from tests.projects.guide_compilation.helpers import service_actor
from tests.projects.guide_activation.source_fixtures import source_case
from .pg_support import prepare_post_policy, operate


async def test_correction_replays_one_existing_unified_successor_and_read_recovers_it(clean_postgres_database):
    async with source_case(clean_postgres_database) as (values, factory, command, actor, grant):
        _, projected = await prepare_post_policy(factory, command, actor, grant, service_actor(values), values)
        correction = PostPolicyCorrection(target=projected.target, idempotency_key=uuid4(), reason='Reconsider the task evaluation requirements')
        first = await operate(factory, actor, command.project_id, grant, 'request_correction', correction)
        second = await operate(factory, actor, command.project_id, grant, 'request_correction', correction)
        assert first == second
        selection = PostPolicySelection(project_id=command.project_id, guide_id=command.guide_id,
                                        compilation_id=command.compilation_id, policy_id=projected.target.policy_id)
        read = await operate(factory, actor, command.project_id, grant, 'review_package', selection)
        assert read.correction == first.correction
        assert not read.current and read.lifecycle_status == 'superseded'
        async with factory() as session:
            assert await session.scalar(text('SELECT count(*) FROM project_guide_proposal_corrections')) == 1
            assert await session.scalar(text('SELECT count(*) FROM project_post_policy_operations')) == 2
            assert await session.scalar(text('SELECT count(*) FROM project_setup_runs')) == 2
            assert await session.scalar(text('SELECT count(*) FROM project_guide_setup_finalizations')) == 1


@pytest.mark.parametrize('which', ['post', 'guide'])
async def test_either_prepared_close_failure_rolls_back_both_operations(clean_postgres_database, which):
    async with source_case(clean_postgres_database) as (values, factory, command, actor, grant):
        _, projected = await prepare_post_policy(factory, command, actor, grant, service_actor(values), values)
        correction = PostPolicyCorrection(target=projected.target, idempotency_key=uuid4(), reason='Reconsider the task evaluation requirements')
        with pytest.raises(GuideProposalError, match='authority_unavailable'):
            await operate(factory, actor, command.project_id, grant, 'request_correction', correction,
                          close_error=which == 'post', guide_close_error=which == 'guide')
        async with factory() as session:
            assert await session.scalar(text('SELECT count(*) FROM project_guide_proposal_corrections')) == 0
            assert await session.scalar(text('SELECT count(*) FROM project_post_policy_operations')) == 1
            assert await session.scalar(text('SELECT count(*) FROM project_setup_runs')) == 1
            assert await session.scalar(text("SELECT count(*) FROM checker_policies WHERE lifecycle_status='compiled'")) == 1
        # The same complete command must work when only close rejection is removed.
        recovered = await operate(factory, actor, command.project_id, grant, 'request_correction', correction)
        assert recovered.correction.successor_setup_generation == 2
