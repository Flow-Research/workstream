"""A distinct, fully prepared guide supersedes exactly the selected predecessor."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.api.post_policy import PostPolicyApproval
from app.modules.projects.guide_activation.custody import load_guide_activation
from app.modules.projects.models import ProjectGuide
from tests.projects.guide_compilation.helpers import ids, service_actor
from tests.projects.guide_compilation.proposals.pg_support import (
    seed_selected_review_revision_inputs,
)
from tests.projects.guide_compilation.proposals.public_support import proposal_client
from tests.projects.post_policy.pg_support import prepare_post_policy, operate
from .pg_support import activation_case, activation_command, activation_service
from .source_fixtures import create_compiled_guide


async def successor_command(factory, command, actor, grant, policy):
    values = {**ids(), "project": command.target.proposal.project_id}
    async with factory() as session:
        actor_id, link_id = (
            await session.execute(
                select(ActorProfile.id, ActorIdentityLink.id)
                .join(ActorIdentityLink, ActorIdentityLink.actor_profile_id == ActorProfile.id)
                .where(ActorProfile.service_identity == "workstream.project.setup")
            )
        ).one()
    values.update(actor=UUID(actor_id), link=UUID(link_id))
    values, finalization = await create_compiled_guide(factory, values, actor, version="v2")
    await seed_selected_review_revision_inputs(factory, finalization, actor)
    _, derived = await prepare_post_policy(
        factory, finalization, actor, grant, service_actor(values), values
    )
    approved = await operate(
        factory,
        actor,
        values["project"],
        grant,
        "approve",
        PostPolicyApproval(target=derived.target, idempotency_key=uuid4()),
    )
    return await activation_command(factory, approved, policy)


async def test_distinct_guide_supersession_and_historical_replay(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (
        factory,
        first,
        actor,
        grant,
        world,
        policy,
    ):
        async with factory() as session, session.begin():
            receipt = await activation_service(session, actor, first, grant).activate(
                first, actor=actor, request_id=uuid4()
            )
        next_command = await successor_command(factory, first, actor, grant, policy)
        assert next_command.target.proposal.guide_id != first.target.proposal.guide_id
        # A manager cannot accidentally replace a guide they did not explicitly select.
        with pytest.raises(GuideProposalError, match="proposal_stale"):
            async with factory() as session, session.begin():
                await activation_service(session, actor, next_command, grant).activate(
                    next_command, actor=actor, request_id=uuid4()
                )
        next_command = next_command.model_copy(
            update={
                "expected_previous_active_guide_id": first.target.proposal.guide_id,
                "expected_previous_active_guide_generation": receipt.activation_generation,
            }
        )
        async with factory() as session, session.begin():
            successor = await activation_service(session, actor, next_command, grant).activate(
                next_command, actor=actor, request_id=uuid4()
            )
        async with factory() as session:
            old = await session.get(ProjectGuide, str(first.target.proposal.guide_id))
            current = await session.get(ProjectGuide, str(next_command.target.proposal.guide_id))
            assert old.status == "superseded" and current.status == "active"
            assert old.superseded_at == current.effective_at == successor.effective_at
            assert await load_guide_activation(session, old) == receipt
            assert await load_guide_activation(session, current) == successor
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM project_guides WHERE status='active'")
                )
                == 1
            )
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'"
                    )
                )
                == 2
            )
        async with proposal_client(factory, actor) as client:
            response = await client.get(
                f"/api/v1/projects/{first.target.proposal.project_id}/active-guide"
            )
            assert response.status_code == 200, response.text
            assert response.json()["guide"]["id"] == str(next_command.target.proposal.guide_id)
        async with factory() as session, session.begin():
            await world.service(session).retire(world.request("retire", policy))
        for command, expected in ((first, receipt), (next_command, successor)):
            async with factory() as session, session.begin():
                assert (
                    await activation_service(session, actor, command, grant).activate(
                        command, actor=actor, request_id=uuid4()
                    )
                    == expected
                )


async def test_waiting_successor_refreshes_cached_project_status(clean_postgres_database):
    """A clean identity map cannot preserve draft after another activation commits."""
    import asyncio
    from app.modules.projects.models import Project
    from tests.auth_concurrency_support import wait_for_named_database_lock

    async with activation_case(clean_postgres_database) as (factory, first, actor, grant, _, policy):
        next_command = await successor_command(factory, first, actor, grant, policy)
        task = None
        try:
            async with factory() as waiting, waiting.begin():
                cached = await waiting.get(Project, str(first.target.proposal.project_id))
                assert cached.status == "draft"
                label = "cp07-cached-project-" + uuid4().hex
                await waiting.execute(text("select set_config('application_name',:name,true)"), dict(name=label))
                waiting_pid = await waiting.scalar(text("select pg_backend_pid()"))
                async with factory() as first_session, first_session.begin():
                    first_pid = await first_session.scalar(text("select pg_backend_pid()"))
                    first_receipt = await activation_service(first_session, actor, first, grant).activate(
                        first, actor=actor, request_id=uuid4()
                    )
                    next_command = next_command.model_copy(update={
                        "expected_previous_active_guide_id": first.target.proposal.guide_id,
                        "expected_previous_active_guide_generation": first_receipt.activation_generation,
                    })
                    task = asyncio.create_task(activation_service(waiting, actor, next_command, grant).activate(
                        next_command, actor=actor, request_id=uuid4()
                    ))
                    await asyncio.wait_for(wait_for_named_database_lock(
                        clean_postgres_database, label,
                        expected_waiter_pid=waiting_pid, expected_blocker_pid=first_pid,
                    ), 10)
                    assert not task.done()
                successor = await asyncio.wait_for(task, 20)
                assert first_receipt.prior_project_status == "draft"
                assert successor.prior_project_status == "active"
                assert cached.status == "active"
            async with factory() as session:
                guide = await session.get(ProjectGuide, str(next_command.target.proposal.guide_id))
                assert await load_guide_activation(session, guide) == successor
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


async def test_waiting_activation_denies_refreshed_unavailable_project_before_policy_reads(
    clean_postgres_database,
):
    """Current locked Project state controls admission before another owner is read."""
    import asyncio
    from unittest.mock import AsyncMock
    from app.modules.projects.models import Project
    from tests.auth_concurrency_support import wait_for_named_database_lock

    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        task = None
        try:
            async with factory() as waiting:
                await waiting.begin()
                cached = await waiting.get(Project, str(command.target.proposal.project_id))
                assert cached.status == "draft"
                label = "cp07-unavailable-project-" + uuid4().hex
                await waiting.execute(text("select set_config('application_name',:name,true)"), dict(name=label))
                waiting_pid = await waiting.scalar(text("select pg_backend_pid()"))
                service = activation_service(waiting, actor, command, grant)
                service.post.lock_policy = AsyncMock(side_effect=AssertionError(
                    "unavailable Project reached downstream policy reads"
                ))
                async with factory() as changer, changer.begin():
                    changer_pid = await changer.scalar(text("select pg_backend_pid()"))
                    await changer.execute(text("UPDATE projects SET status='archived' WHERE id=:id"),
                                          dict(id=str(command.target.proposal.project_id)))
                    task = asyncio.create_task(service.activate(command, actor=actor, request_id=uuid4()))
                    await asyncio.wait_for(wait_for_named_database_lock(
                        clean_postgres_database, label,
                        expected_waiter_pid=waiting_pid, expected_blocker_pid=changer_pid,
                    ), 10)
                    assert not task.done()
                with pytest.raises(GuideProposalError, match="approval_blocked"):
                    await asyncio.wait_for(task, 20)
                service.post.lock_policy.assert_not_awaited()
                assert cached.status == "archived"
                await waiting.rollback()
            async with factory() as session:
                assert (await session.get(ProjectGuide, str(command.target.proposal.guide_id))).status == "draft"
                assert await session.scalar(text(
                    "SELECT count(*) FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'"
                )) == 0
                assert await session.scalar(text(
                    "SELECT count(*) FROM audit_events WHERE action_id='project.guide.activate'"
                )) == 0
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
