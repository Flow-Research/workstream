"""Real AUTH role issuance and TASK claim share one consistent lock order."""

from app.core.config import get_settings

import asyncio
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.adapters.audit import task_transition_audit
from app.adapters.tasks import task_commands
from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.authorization.project_role_schemas import ProjectRoleGrantIssueBody
from app.modules.tasks.api.authorization import TaskAuthorityDenied
from app.modules.tasks.models import TaskAssignment, WorkstreamTask
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.authorization.task_authority.test_concurrency import actor_context
from tests.project_role_issue_fixtures import issue_body, issue_role, issue_runtime
from tests.test_tasks import (
    task_database_env as task_database_env,
    task_client as task_client,
    create_active_project,
    create_ready_task,
    seed_task_test_actor,
)


@pytest.mark.parametrize("ordering", ["issue_first", "claim_first"])
async def test_role_issuance_and_claim_linearize_at_real_authority(
    task_client,
    task_database_env,
    monkeypatch,
    ordering,
):
    project = await create_active_project(task_client)
    ready = await create_ready_task(task_client, project["id"])
    contributor = await seed_task_test_actor("cp08-ungranted-contributor")
    context = await actor_context(contributor)
    async with db_session.get_session_factory()() as session:
        manager_link = await session.scalar(
            select(ActorIdentityLink).where(
                ActorIdentityLink.issuer == "flow-test",
                ActorIdentityLink.subject == "project-manager-subject",
            )
        )
        manager_id, link_id = UUID(manager_link.actor_profile_id), UUID(manager_link.id)
    body = ProjectRoleGrantIssueBody.model_validate(
        issue_body(UUID(contributor)).model_dump(mode="json") | {"role": "submitter"},
    )
    entered, release = asyncio.Event(), asyncio.Event()
    names = {side: f"cp08_{side}_{new_record_id().hex}" for side in ("claim", "issue")}
    engines = {
        side: create_async_engine(
            task_database_env,
            connect_args={
                "server_settings": {"application_name": name, "statement_timeout": "30000"},
            },
        )
        for side, name in names.items()
    }
    original_project = AdminAuthorizationRepository.lock_project
    original_prepare = PreparedTaskAuthorization.prepare

    async def observe_project(repository, project_id):
        result = await original_project(repository, project_id)
        if repository._session.info.get("cp08_issue") and ordering == "issue_first":
            entered.set()
            await release.wait()
        return result

    async def observe_denial(authority, facts):
        try:
            return await original_prepare(authority, facts)
        except TaskAuthorityDenied:
            if ordering == "claim_first":
                entered.set()
                await release.wait()
            raise

    monkeypatch.setattr(AdminAuthorizationRepository, "lock_project", observe_project)
    monkeypatch.setattr(PreparedTaskAuthorization, "prepare", observe_denial)

    async def issue():
        async with AsyncSession(engines["issue"], expire_on_commit=False) as session:
            session.info["cp08_issue"] = True
            prepared, resolved = await issue_runtime(session, manager_id, link_id)
            return await issue_role(
                session, UUID(project["id"]), body, new_record_id(), resolved, prepared
            )

    async def claim():
        async with AsyncSession(engines["claim"], expire_on_commit=False) as session:
            return await task_commands(
                session,
                authorization=PreparedTaskAuthorization(session, context),
                audit=task_transition_audit(session),
                actor_profile_id=context.actor_profile_id,
                settings=get_settings(),
            ).claim(UUID(ready["id"]), "Concurrent initial claim", idempotency_key=new_record_id())

    pending = []
    try:
        first, second = (issue, claim) if ordering == "issue_first" else (claim, issue)
        pending.append(asyncio.create_task(first()))
        await asyncio.wait_for(entered.wait(), 30)
        pending.append(asyncio.create_task(second()))
        await asyncio.wait_for(
            wait_for_named_database_lock(
                task_database_env,
                names["claim" if ordering == "issue_first" else "issue"],
            ),
            30,
        )
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), 30)
        if ordering == "issue_first":
            assert all(not isinstance(result, BaseException) for result in results), results
        else:
            assert isinstance(results[0], TaskAuthorityDenied), results
            assert not isinstance(results[1], BaseException), results
        async with db_session.get_session_factory()() as session:
            task = await session.get(WorkstreamTask, ready["id"])
            assignments = list(
                await session.scalars(
                    select(TaskAssignment).where(TaskAssignment.task_id == task.id)
                )
            )
            assert task.locked_contribution_policy_version_id == UUID(
                ready["locked_contribution_policy_version_id"]
            )
            if ordering == "issue_first":
                assert len(assignments) == 1
                assert (
                    assignments[0].submitter_contribution_policy_version_id
                    == task.locked_contribution_policy_version_id
                )
                assert task.status == "in_progress"
            else:
                assert assignments == []
                assert task.status == "ready"
    finally:
        release.set()
        for pending_task in pending:
            if not pending_task.done():
                pending_task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for engine in engines.values():
            await engine.dispose()


async def test_claim_keeps_frozen_policy_while_successor_activation_waits(
    task_client,
    task_database_env,
    monkeypatch,
):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
    from tests.test_tasks import (
        auth_headers,
        complete_guide_payload,
        create_policy_bundle_for_guide,
        admit_and_grant_project_submitter,
    )
    from tests.project_create_fixtures import seed_active_guide_for_downstream_test

    project = await create_active_project(task_client)
    ready = await create_ready_task(task_client, project["id"])
    created = await task_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=complete_guide_payload("v2"),
    )
    assert created.status_code == 201, created.text
    successor = created.json()
    await create_policy_bundle_for_guide(task_client, project["id"], successor["id"])
    grant = await admit_and_grant_project_submitter(
        task_client,
        monkeypatch,
        project["id"],
        "cp08-guide-race-contributor",
    )
    contributor = grant["actor_profile_id"]
    context = await actor_context(contributor)
    name = f"cp08_activation_{new_record_id().hex}"
    engine = create_async_engine(
        task_database_env,
        connect_args={
            "server_settings": {"application_name": name, "statement_timeout": "30000"},
        },
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    entered, release = asyncio.Event(), asyncio.Event()
    original = ProjectLockedPolicyRepository.lock_locked_policy_context

    async def hold_context(repository, request):
        result = await original(repository, request)
        if repository._session.info.get("cp08_claim"):
            entered.set()
            await release.wait()
        return result

    monkeypatch.setattr(ProjectLockedPolicyRepository, "lock_locked_policy_context", hold_context)

    async def claim():
        async with db_session.get_session_factory()() as session:
            session.info["cp08_claim"] = True
            return await task_commands(
                session,
                authorization=PreparedTaskAuthorization(session, context),
                audit=task_transition_audit(session),
                actor_profile_id=context.actor_profile_id,
                settings=get_settings(),
            ).claim(UUID(ready["id"]), "Claim exact prior guide during successor activation", idempotency_key=new_record_id())

    pending = []
    try:
        pending.append(asyncio.create_task(claim()))
        await asyncio.wait_for(entered.wait(), 30)
        pending.append(
            asyncio.create_task(
                seed_active_guide_for_downstream_test(
                    factory,
                    project_id=project["id"],
                    guide_id=successor["id"],
                )
            )
        )
        await asyncio.wait_for(wait_for_named_database_lock(task_database_env, name), 30)
        release.set()
        await asyncio.wait_for(asyncio.gather(*pending), 30)
        from app.modules.projects.models import ProjectGuide

        async with factory() as session:
            task = await session.get(WorkstreamTask, ready["id"])
            assignment = (
                await session.scalars(
                    select(TaskAssignment).where(TaskAssignment.task_id == task.id)
                )
            ).one()
            guide = await session.get(ProjectGuide, successor["id"])
            assert guide.status == "active"
            assert (
                guide.contribution_policy_version_id != task.locked_contribution_policy_version_id
            )
            assert task.locked_guide_version == "v1"
            assert (
                assignment.submitter_contribution_policy_version_id
                == task.locked_contribution_policy_version_id
                == UUID(ready["locked_contribution_policy_version_id"])
            )
    finally:
        release.set()
        for task in pending:
            if not task.done():
                task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await engine.dispose()
