"""Real AUTH mutation and claim interleavings retain exact atomic publication."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from app.adapters.auth.assignment_invalidation_publication import AssignmentInvalidationPublication
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.api import TaskAuthorityDenied
from auth_concurrency_support import wait_for_named_database_lock
from tests.authorization.task_authority.test_lifecycle_races import _run_task_contributor_write
from tests.tasks.invalidation_support import setup_assignment
from tests.test_tasks import (
    task_client as task_client, task_database_env as task_database_env,
    create_ready_task, set_dev_actor, auth_headers,
)


@pytest.mark.parametrize("first", ["claim", "loss"])
async def test_claim_and_loss_publish_only_committed_original_assignments(
    task_client, task_database_env, monkeypatch, first,
):
    s = await setup_assignment(task_client, monkeypatch)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    task = await create_ready_task(task_client, s.project["id"])
    actor = s.grant["actor_profile_id"]
    token = uuid4().hex
    loss_name, claim_name = f"loss-{token}", f"claim-{token}"
    held, release, entered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_prepare = PreparedTaskAuthorization.prepare
    original_publish = AssignmentInvalidationPublication.publish
    original_lock = AdminAuthorizationRepository.lock_actor_lifecycle_target

    async def named_lock(repo, *args, **kwargs):
        if asyncio.current_task().get_name() == loss_name:
            await repo._session.execute(text("select set_config('application_name', :name, true)"), {"name": loss_name})
        return await original_lock(repo, *args, **kwargs)

    async def prepare(owner, facts):
        result = await original_prepare(owner, facts)
        if first == "claim":
            held.set()
            await asyncio.wait_for(release.wait(), 20)
        return result

    async def publish(owner, facts):
        if first == "loss":
            held.set()
            await asyncio.wait_for(release.wait(), 20)
        return await original_publish(owner, facts)

    monkeypatch.setattr(AdminAuthorizationRepository, "lock_actor_lifecycle_target", named_lock)
    monkeypatch.setattr(PreparedTaskAuthorization, "prepare", prepare)
    monkeypatch.setattr(AssignmentInvalidationPublication, "publish", publish)
    set_dev_actor(monkeypatch, roles="viewer", issuer=s.admin_identity[0], subject=s.admin_identity[1])

    def claim():
        return asyncio.create_task(_run_task_contributor_write(task_database_env,
            actor=actor, task_id=task["id"], operation="claim", application_name=claim_name,
            entered=entered), name=claim_name)

    def loss():
        return asyncio.create_task(task_client.post(
            f"/api/v1/actors/{s.grant['actor_profile_id']}/suspend",
            headers=auth_headers(), json={"reason": "Real claim loss race"}), name=loss_name)

    running = []
    try:
        running.append(claim() if first == "claim" else loss())
        await asyncio.wait_for(held.wait(), 20)
        running.append(loss() if first == "claim" else claim())
        await asyncio.wait_for(wait_for_named_database_lock(
            task_database_env, loss_name if first == "claim" else claim_name,
        ), 10)
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*running, return_exceptions=True), 20)
    finally:
        release.set()
        for pending in running:
            if not pending.done():
                pending.cancel()
        await asyncio.gather(*running, return_exceptions=True)
    claimed, response = results if first == "claim" else results[::-1]
    assert not isinstance(response, BaseException), repr(response)
    assert response.status_code == 200, response.text
    async with s.sessions() as session:
        events = (await session.scalars(select(OutboxEvent))).all()
    expected = {UUID(s.assignment["id"])}
    if first == "claim":
        assert not isinstance(claimed, BaseException), repr(claimed)
        expected.add(UUID(claimed.assignment.id))
    else:
        assert isinstance(claimed, TaskAuthorityDenied), repr(claimed)
    assert {event.aggregate_id for event in events} == expected
