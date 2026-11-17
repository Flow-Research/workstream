"""Real command/database races, with barriers only at observed owner boundaries."""

from app.adapters.artifacts import task_guide_documents_port
from app.core.config import get_settings

from app.adapters.tasks import task_service

import asyncio
from types import SimpleNamespace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from auth_concurrency_support import wait_for_named_database_lock
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db import session as db_session
from app.db.session import get_db_session
from app.adapters.audit import task_transition_audit
from app.modules.actors.models import ActorIdentityLink, ActorProfile
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
                session,
                authorization=PreparedTaskAuthorization(session, context),
                audit=task_transition_audit(session),
                actor_profile_id=context.actor_profile_id,
                contexts=task_service(session, settings=get_settings()),
                guide_documents=task_guide_documents_port(session, get_settings()),
            ).claim(UUID(task["id"]), "Competing claim", idempotency_key=uuid4())

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
        assert stored_task.status == "in_progress" and stored_task.assigned_to == winner.assignment.contributor_id
        assert assignments[0].submitter_task_size == stored_task.task_size
        assert assignments[0].submitter_award_definition_id == stored_task.locked_submission_award_definition_id
        assert assignments[0].submitter_contribution_policy_version_id == stored_task.locked_contribution_policy_version_id
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
                session,
                authorization=PreparedTaskAuthorization(session, context),
                audit=task_transition_audit(session),
                actor_profile_id=context.actor_profile_id,
                contexts=task_service(session, settings=get_settings()),
                guide_documents=task_guide_documents_port(session, get_settings()),
            ).claim(UUID(task["id"]), "Claim racing with authority revocation", idempotency_key=uuid4())

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
            assert stored_task.status == "in_progress"
            assert stored_task.assigned_to == grant["actor_profile_id"]
            assert len(assignments) == 1
            assert assignments[0].id == claim_result.assignment.id


@pytest.mark.parametrize("case", ["active", "suspended", "revoked_link", "missing", "foreign", "unauthorized"])
async def test_role_revocation_target_fence_preserves_authority_and_replay(task_client, monkeypatch, case):
    """Stored target discovery must not widen access or require target eligibility."""
    project = await create_active_project(task_client)
    granted = await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "revocation-target",
    )
    target_id = granted["actor_profile_id"]
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    selected_project = project["id"]
    selected_grant = granted["grant_id"]
    if case == "foreign":
        selected_project = (await create_active_project(task_client, slug="foreign-revoke"))["id"]
    elif case == "missing":
        selected_grant = str(uuid4())
    elif case == "unauthorized":
        set_dev_actor(monkeypatch, roles="worker", subject="revocation-target")
    async with db_session.get_session_factory()() as session:
        if case == "suspended":
            target = await session.get(ActorProfile, target_id)
            target.status = "suspended"
            target.suspended_by = target_id
            target.suspended_at = datetime.now(UTC)
            target.suspension_reason = "Revocation target fixture"
        elif case == "revoked_link":
            link = await session.scalar(select(ActorIdentityLink).where(
                ActorIdentityLink.actor_profile_id == target_id,
            ))
            link.status = "revoked"
            link.revoked_by = target_id
            link.revoked_at = datetime.now(UTC)
            link.revoked_reason = "Revocation target fixture"
        await session.commit()
        before = (await session.execute(select(ProjectRoleGrant.__table__).where(
            ProjectRoleGrant.id == UUID(granted["grant_id"]),
        ))).mappings().one()
    locked_targets = []
    original_principals = AdminAuthorizationRepository.lock_project_role_principals

    async def observe_target(repository, **kwargs):
        locked_targets.append(kwargs["target_actor_profile_id"])
        return await original_principals(repository, **kwargs)

    monkeypatch.setattr(AdminAuthorizationRepository, "lock_project_role_principals", observe_target)
    headers = auth_headers() | {"Idempotency-Key": str(uuid4())}
    url = f"/api/v1/projects/{selected_project}/role-grants/{selected_grant}/revoke"
    response = await task_client.post(url, headers=headers, json={"reason": "Revoke target authority"})
    allowed = case in {"active", "suspended", "revoked_link"}
    assert response.status_code == (200 if allowed else 404), response.text
    assert locked_targets == ([] if case in {"missing", "foreign"} else [UUID(target_id)])
    async with db_session.get_session_factory()() as session:
        after = (await session.execute(select(ProjectRoleGrant.__table__).where(
            ProjectRoleGrant.id == UUID(granted["grant_id"]),
        ))).mappings().one()
        if allowed:
            assert after["status"] == "revoked"
            assert after["actor_profile_id"] == before["actor_profile_id"]
        else:
            assert after == before
    if allowed:
        replay = await task_client.post(url, headers=headers, json={"reason": "Revoke target authority"})
        assert replay.status_code == 200, replay.text
        assert replay.json() == response.json()


@pytest.mark.asyncio
async def test_project_role_issue_crossed_principals_use_one_lexical_lock_order() -> None:
    low = UUID("00000000-0000-0000-0000-000000000001")
    high = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    low_link, high_link = uuid4(), uuid4()

    class RecordingSession:
        def __init__(self) -> None:
            self.calls: list[tuple[str, UUID]] = []

        async def scalar(self, statement):
            entity = statement.column_descriptions[0]["entity"]
            values = set(statement.compile().params.values())
            actor = low if str(low) in values else high
            if entity is ActorProfile:
                self.calls.append(("profile", actor))
                return SimpleNamespace(id=str(actor), actor_kind="human", status="active")
            self.calls.append(("link", actor))
            link_id = low_link if actor == low else high_link
            return SimpleNamespace(id=str(link_id), actor_profile_id=str(actor))

    expected = [
        ("profile", low),
        ("link", low),
        ("profile", high),
        ("link", high),
    ]
    for caller, caller_link, target in (
        (low, low_link, high),
        (high, high_link, low),
    ):
        session = RecordingSession()
        repository = AdminAuthorizationRepository(session)  # type: ignore[arg-type]
        locked_caller, target_eligible = await repository.lock_project_role_principals(
            caller_actor_profile_id=caller,
            caller_identity_link_id=caller_link,
            target_actor_profile_id=target,
        )
        assert locked_caller is not None
        assert target_eligible is True
        assert session.calls == expected
