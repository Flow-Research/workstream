"""Real command/database races, with barriers only at observed owner boundaries."""

import asyncio
from uuid import UUID, uuid4

import pytest
from auth_concurrency_support import wait_for_named_database_lock
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db import session as db_session
from app.db.session import get_db_session
from app.adapters.audit import task_transition_audit
from app.modules.actors.models import ActorIdentityLink
from app.modules.authorization.runtime import (
    ActorKind, ActorStatus, HumanAuthorizationContext, IdentityLinkStatus,
)
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.models import ProjectRoleGrant
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.models import AuditEvent, TaskAssignment, WorkstreamTask
from app.modules.tasks.schemas import TaskWithAssignmentResponse
from app.modules.tasks.api.authorization import TaskAuthorityDenied
from app.modules.tasks.repository import TaskRepository
from tests.test_tasks import (
    task_database_env as task_database_env,
    task_client as task_client,
    create_active_project, create_ready_task, admit_and_grant_project_submitter,
    set_dev_actor, auth_headers,
)


async def actor_context(actor_id):
    async with db_session.get_session_factory()() as session:
        link = await session.scalar(select(ActorIdentityLink).where(
            ActorIdentityLink.actor_profile_id == actor_id,
        ))
        return HumanAuthorizationContext(
            actor_profile_id=UUID(actor_id), actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus.ACTIVE, identity_link_id=UUID(link.id),
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=uuid4(), correlation_id=uuid4(),
        )


async def test_two_granted_claimants_have_one_atomic_winner(task_client, monkeypatch):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    actors = []
    for subject in ("first-claimant", "second-claimant"):
        granted = await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], subject)
        actors.append(await actor_context(granted["actor_profile_id"]))
    both_attempting_lock = asyncio.Barrier(2)
    original = TaskRepository.get_task

    async def align_before_task_lock(repository, task_id, *, for_update=False):
        if for_update:
            await both_attempting_lock.wait()
        return await original(repository, task_id, for_update=for_update)

    monkeypatch.setattr(TaskRepository, "get_task", align_before_task_lock)

    async def claim(context):
        async with db_session.get_session_factory()() as session:
            return await AuthorizedTaskCommands(
                session, authorization=PreparedTaskAuthorization(session, context),
                audit=task_transition_audit(session),
                actor_profile_id=context.actor_profile_id,
            ).claim(UUID(task["id"]), "Competing claim")

    results = await asyncio.wait_for(
        asyncio.gather(*(claim(actor) for actor in actors), return_exceptions=True), timeout=30,
    )
    winners = [result for result in results if isinstance(result, TaskWithAssignmentResponse)]
    losers = [result for result in results if isinstance(result, TaskAuthorityDenied)]
    assert len(winners) == len(losers) == 1, results
    winner = winners[0]
    async with db_session.get_session_factory()() as session:
        assignments = list(await session.scalars(select(TaskAssignment).where(TaskAssignment.task_id == task["id"])))
        assert len(assignments) == 1 and assignments[0].id == winner.assignment.id
        stored_task = await session.get(WorkstreamTask, task["id"])
        assert stored_task.status == "claimed" and stored_task.assigned_to == winner.assignment.contributor_id
        decisions = list(await session.scalars(select(AuditEvent).where(AuditEvent.action_id == "task.claim")))
        assert len(decisions) == 1 and decisions[0].after_facts["allowed"] is True
        events = list(await session.scalars(select(AuditEvent).where(
            AuditEvent.entity_id == task["id"], AuditEvent.event_type == "TaskClaimed",
        )))
        assert len(events) == 1
        assert events[0].event_payload["references"]["authorization_decision_id"] == decisions[0].id


@pytest.mark.parametrize("ordering", ["revoke_first", "claim_first"])
async def test_project_grant_revocation_serializes_with_claim(
    task_client, task_database_env, monkeypatch, ordering,
):
    """Real revocation API and task command share the same grant-row fence."""
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    grant = await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "revocation-race-submitter",
    )
    context = await actor_context(grant["actor_profile_id"])
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    locked, release = asyncio.Event(), asyncio.Event()
    revoke_name = f"task-grant-revoke-{uuid4().hex}"
    claim_name = f"task-grant-claim-{uuid4().hex}"
    original_grant_lock = AdminAuthorizationRepository.lock_project_role_grant
    original_prepare = PreparedTaskAuthorization.prepare

    async def observe_revoke_lock(repository, *, project_id, grant_id):
        await repository._session.execute(
            text("select set_config('application_name', :name, true)"),
            {"name": revoke_name},
        )
        row = await original_grant_lock(repository, project_id=project_id, grant_id=grant_id)
        if ordering == "revoke_first":
            locked.set()
            await release.wait()
        return row

    async def observe_claim_lock(authority, facts):
        handle = await original_prepare(authority, facts)
        if ordering == "claim_first":
            locked.set()
            await release.wait()
        return handle

    monkeypatch.setattr(AdminAuthorizationRepository, "lock_project_role_grant", observe_revoke_lock)
    monkeypatch.setattr(PreparedTaskAuthorization, "prepare", observe_claim_lock)
    engine = create_async_engine(task_database_env, connect_args={
        "server_settings": {"application_name": claim_name},
    })
    revoke_engine = create_async_engine(task_database_env, connect_args={
        "server_settings": {"application_name": revoke_name},
    })
    app = task_client._transport.app
    previous_session_dependency = app.dependency_overrides.get(get_db_session)

    async def named_revoke_session():
        async with AsyncSession(revoke_engine, expire_on_commit=False) as session:
            yield session

    # Name the actual request session before any AUTH preparation can lock a
    # target row, not only after the router reaches its mutation repository.
    app.dependency_overrides[get_db_session] = named_revoke_session

    async def claim():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            return await AuthorizedTaskCommands(
                session, authorization=PreparedTaskAuthorization(session, context),
                audit=task_transition_audit(session), actor_profile_id=context.actor_profile_id,
            ).claim(UUID(task["id"]), "Claim racing with authority revocation")

    async def revoke():
        return await task_client.post(
            f"/api/v1/projects/{project['id']}/role-grants/{grant['grant_id']}/revoke",
            headers=auth_headers(), json={"reason": "Concurrent grant revocation"},
        )

    pending = []
    try:
        first = revoke if ordering == "revoke_first" else claim
        second = claim if ordering == "revoke_first" else revoke
        pending.append(asyncio.create_task(first()))
        await asyncio.wait_for(locked.wait(), timeout=30)
        pending.append(asyncio.create_task(second()))
        await asyncio.wait_for(wait_for_named_database_lock(
            task_database_env, claim_name if ordering == "revoke_first" else revoke_name,
        ), timeout=30)
        release.set()
        results = await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True), timeout=30,
        )
    finally:
        release.set()
        for running in pending:
            if not running.done():
                running.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await engine.dispose()
        await revoke_engine.dispose()
        if previous_session_dependency is None:
            app.dependency_overrides.pop(get_db_session, None)
        else:
            app.dependency_overrides[get_db_session] = previous_session_dependency
    revoke_result, claim_result = results if ordering == "revoke_first" else results[::-1]
    assert not isinstance(revoke_result, BaseException), revoke_result
    assert revoke_result.status_code == 200, revoke_result.text
    async with db_session.get_session_factory()() as session:
        stored_grant = await session.get(ProjectRoleGrant, UUID(grant["grant_id"]))
        assert stored_grant.status == "revoked"
        stored_task = await session.get(WorkstreamTask, task["id"])
        assignments = list(await session.scalars(select(TaskAssignment).where(
            TaskAssignment.task_id == task["id"],
        )))
        if ordering == "revoke_first":
            assert isinstance(claim_result, TaskAuthorityDenied), claim_result
            assert stored_task.status == "ready" and stored_task.assigned_to is None
            assert assignments == []
        else:
            assert isinstance(claim_result, TaskWithAssignmentResponse), claim_result
            assert stored_task.status == "claimed"
            assert stored_task.assigned_to == grant["actor_profile_id"]
            assert len(assignments) == 1
            assert assignments[0].id == claim_result.assignment.id
