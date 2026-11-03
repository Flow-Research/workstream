"""The guide serialization fence yields one effect for concurrent exact retries."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api.post_policy import PostPolicyApproval, PostPolicyCorrection
from tests.projects.guide_compilation.helpers import service_actor
from tests.projects.guide_compilation.proposals.pg_support import proposal_case
from .pg_support import operate, prepare_upstream


@pytest.mark.parametrize('operation', ['derive', 'approve', 'request_correction'])
async def test_concurrent_exact_requests_have_one_effect(clean_postgres_database, operation):
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        derive = await prepare_upstream(factory, command, actor, grant, values)
        setup = service_actor(values)
        if operation == 'derive':
            identity, role, payload = setup, None, derive
        else:
            projected = await operate(factory, setup, command.project_id, None, 'derive', derive)
            identity, role = actor, grant
            payload = (PostPolicyApproval(target=projected.target, idempotency_key=uuid4()) if operation == 'approve'
                       else PostPolicyCorrection(target=projected.target, idempotency_key=uuid4(), reason='Reconsider this evaluation requirement'))
        first, second = await asyncio.wait_for(asyncio.gather(*(
            operate(factory, identity, command.project_id, role, operation, payload) for _ in range(2)
        )), timeout=30)
        assert first == second
        async with factory() as session:
            kind = 'correction' if operation == 'request_correction' else operation
            assert await session.scalar(text('SELECT count(*) FROM project_post_policy_operations WHERE kind=:kind'), dict(kind=kind)) == 1
            assert await session.scalar(text('SELECT count(*) FROM project_guide_compilations')) == 1
            assert await session.scalar(text('SELECT count(*) FROM project_guide_compilation_attempts')) == 1
            assert await session.scalar(text('SELECT count(*) FROM project_setup_runs')) == (2 if kind == 'correction' else 1)
