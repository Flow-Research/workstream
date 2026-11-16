"""Manager readiness through public HTTP, real authority and PostgreSQL custody."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.modules.tasks.models import AuditEvent, TaskCommandReceipt, WorkstreamTask
from tests.test_tasks import (
    task_database_env as task_database_env,
    task_client as task_client,
    auth_headers,
    complete_task_payload,
    create_active_project,
    create_draft_task,
    set_dev_actor,
)


async def test_create_draft_without_guide(task_client):
    project = await task_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={"name": "Draft only", "slug": f"draft-{uuid4().hex}"},
    )
    assert project.status_code == 201, project.text
    headers = auth_headers()
    path = f"/api/v1/projects/{project.json()['id']}/tasks"
    payload = complete_task_payload()
    created = await task_client.post(path, headers=headers, json=payload)
    assert created.status_code == 201, created.text
    assert {"base_amount", "currency", "payout_type", "locked_payment_policy_version"}.isdisjoint(created.json())
    replay = await task_client.post(path, headers=headers, json=payload)
    assert replay.status_code == 201, replay.text
    assert replay.json() == created.json()
    changed = await task_client.post(path, headers=headers, json=payload | {"title": "different"})
    assert changed.status_code == 409, changed.text
    task_id = created.json()["id"]
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, task_id)
        receipt = (
            await session.scalars(
                select(TaskCommandReceipt).where(TaskCommandReceipt.task_id == task_id)
            )
        ).one()
        event = (
            await session.scalars(select(AuditEvent).where(AuditEvent.entity_id == task_id))
        ).one()
        assert task.status == "draft" and task.locked_guide_version is None
        assert task.title == payload["title"] and task.created_by == receipt.actor_profile_id
        assert receipt.assignment_id is None and receipt.contributor_id is None
        assert event.event_type == "TaskCreated"
        assert {key: value for key, value in event.event_payload.items() if key not in {'manager_authority_facts', 'authorization_resource_digest'}} == {
            "source_type": payload["source_type"],
            "references": {
                "project_id": task.project_id,
                "task_id": task.id,
                "authorization_decision_id": event.event_payload["references"][
                    "authorization_decision_id"
                ],
            },
        }
        assert UUID(event.event_payload["references"]["authorization_decision_id"])


@pytest.mark.parametrize("phase", ["authorize", "stage"])
async def test_creation_preparation_cannot_move_to_a_later_root(task_client, phase):
    """Rolled-back preparation and ALLOW evidence cannot authorize another root."""
    from app.adapters.audit import task_transition_audit
    from app.adapters.tasks import task_commands
    from app.core.config import get_settings
    from app.modules.authorization.task_authorization import PreparedTaskAuthorization
    from app.modules.tasks.schemas import TaskCreate
    from tests.authorization.task_authority.test_concurrency import actor_context

    project = await task_client.post("/api/v1/projects", headers=auth_headers(),
                                     json={"name": "Preparation root", "slug": "create-root-" + uuid4().hex})
    assert project.status_code == 201, project.text
    async with db_session.get_session_factory()() as observer:
        from app.modules.actors.models import ActorIdentityLink
        actor_id = await observer.scalar(select(ActorIdentityLink.actor_profile_id).where(
            ActorIdentityLink.subject == "project-manager-subject",
        ))
    context = await actor_context(actor_id)
    async with db_session.get_session_factory()() as session:
        commands = task_commands(session, authorization=PreparedTaskAuthorization(session, context),
                                 audit=task_transition_audit(session), actor_profile_id=context.actor_profile_id,
                                 settings=get_settings())
        async with session.begin():
            prepared = await commands.prepare_creation(UUID(project.json()["id"]), TaskCreate(**complete_task_payload()),
                                                       idempotency_key=uuid4())
            decision = await commands.authorize_creation(prepared)
            receipt_id = prepared.receipt.id
            await session.rollback()
        async with session.begin():
            with pytest.raises(RuntimeError, match="original caller transaction"):
                if phase == "authorize":
                    await commands.authorize_creation(prepared)
                else:
                    await commands.stage_creation(prepared, decision)
        async with session.begin():
            assert await session.get(WorkstreamTask, str(prepared.task_id)) is None
            assert await session.get(TaskCommandReceipt, receipt_id) is None
            assert await session.get(AuditEvent, str(decision.decision_id)) is None


async def test_screen_and_release_lock_approved_context(task_client):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    responses = []
    for operation in ("screen", "release"):
        headers = auth_headers()
        path = f"/api/v1/tasks/{task['id']}/{operation}"
        response = await task_client.post(
            path, headers=headers, json={"reason": "Manager decision"}
        )
        assert response.status_code == 200, response.text
        assert {"base_amount", "currency", "payout_type", "locked_payment_policy_version"}.isdisjoint(response.json())
        replay = await task_client.post(path, headers=headers, json={"reason": "Manager decision"})
        assert replay.status_code == 200, replay.text
        assert replay.json() == response.json()
        different_key = await task_client.post(
            path, headers=auth_headers(), json={"reason": "Manager decision"}
        )
        assert different_key.status_code == 403, different_key.text
        responses.append(response.json())
    assert (
        responses[0]["locked_contribution_policy_version_id"]
        == responses[1]["locked_contribution_policy_version_id"]
    )
    async with db_session.get_session_factory()() as session:
        events = list(
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.entity_id == task["id"],
                    AuditEvent.event_type.in_(["TaskScreened", "TaskReleased"]),
                )
            )
        )
        assert len(events) == 2
        from app.modules.tasks.api.audit_evidence import AuditTaskEvidenceRequest
        from app.modules.tasks.repository import TaskRepository

        page = await TaskRepository(session).read_audit_task_evidence(
            AuditTaskEvidenceRequest(UUID(project["id"]), UUID(task["id"]))
        )
        assert [item.event_type for item in page.items] == [
            "TaskCreated",
            "TaskScreened",
            "TaskReleased",
        ]
        assert all(
            item.assignment_id is None and item.authorization_decision_id is not None
            for item in page.items
        )
        for event in events:
            assert "assignment_id" not in event.event_payload["references"]
            assert (
                event.event_payload["locked_contribution_policy_version_id"]
                == responses[0]["locked_contribution_policy_version_id"]
            )
            assert (
                event.event_payload["locked_guide_version"] == responses[0]["locked_guide_version"]
            )


@pytest.mark.parametrize("operation", ["create", "screen", "release"])
async def test_role_claim_without_project_grant_cannot_manage(task_client, monkeypatch, operation):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    set_dev_actor(monkeypatch, roles="project_manager", subject="ungranted-manager")
    path = (
        f"/api/v1/projects/{project['id']}/tasks"
        if operation == "create"
        else f"/api/v1/tasks/{task['id']}/{operation}"
    )
    response = await task_client.post(
        path, headers=auth_headers(), json=complete_task_payload() if operation == "create" else {}
    )
    assert response.status_code == 403, response.text


async def test_manager_mutations_reject_bad_keys(task_client):
    from app.api.deps.authorization import get_task_commands

    app = task_client._transport.app

    async def forbidden():
        raise AssertionError("actor/product resolution must not run")

    app.dependency_overrides[get_task_commands] = forbidden
    try:
        for operation in ("create", "screen", "release"):
            for header_values in ([], ["bad"], [str(uuid4()), str(uuid4())]):
                path = (
                    f"/api/v1/projects/{uuid4()}/tasks"
                    if operation == "create"
                    else f"/api/v1/tasks/{uuid4()}/{operation}"
                )
                headers = [("Authorization", "Bearer task-token")] + [
                    ("Idempotency-Key", value) for value in header_values
                ]
                response = await task_client.post(
                    path,
                    headers=headers,
                    json=complete_task_payload() if operation == "create" else {},
                )
                assert response.status_code == 422, response.text
    finally:
        app.dependency_overrides.pop(get_task_commands, None)


async def test_unknown_project_create_is_controlled(task_client):
    response = await task_client.post(
        f"/api/v1/projects/{uuid4()}/tasks", headers=auth_headers(), json=complete_task_payload()
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("operation", ["create", "screen", "release"])
async def test_manager_command_rolls_back_all_staged_success(task_client, monkeypatch, operation):
    from app.modules.tasks.command_replay import TaskCommandReplay

    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    if operation == "release":
        response = await task_client.post(
            f"/api/v1/tasks/{task['id']}/screen", headers=auth_headers()
        )
        assert response.status_code == 200, response.text
    path = (
        f"/api/v1/projects/{project['id']}/tasks"
        if operation == "create"
        else f"/api/v1/tasks/{task['id']}/{operation}"
    )
    payload = complete_task_payload() if operation == "create" else {"reason": "Release decision"}
    headers = auth_headers()
    original = TaskCommandReplay.complete
    async with db_session.get_session_factory()() as session:
        before_tasks = [
            (t.id, t.status)
            for t in await session.scalars(select(WorkstreamTask).order_by(WorkstreamTask.id))
        ]
        before_audit = list(await session.scalars(select(AuditEvent.id).order_by(AuditEvent.id)))
    reached = []

    def fail(*args, **kwargs):
        reached.append(True)
        raise RuntimeError("staged failure")

    monkeypatch.setattr(TaskCommandReplay, "complete", fail)
    failed = await task_client.post(path, headers=headers, json=payload)
    assert failed.status_code == 500, failed.text
    assert reached == [True]
    async with db_session.get_session_factory()() as session:
        assert [
            (t.id, t.status)
            for t in await session.scalars(select(WorkstreamTask).order_by(WorkstreamTask.id))
        ] == before_tasks
        assert (
            list(await session.scalars(select(AuditEvent.id).order_by(AuditEvent.id)))
            == before_audit
        )
        assert (
            await session.scalar(
                select(TaskCommandReceipt).where(
                    TaskCommandReceipt.idempotency_key == UUID(headers["Idempotency-Key"])
                )
            )
            is None
        )
    monkeypatch.setattr(TaskCommandReplay, "complete", staticmethod(original))
    retry = await task_client.post(path, headers=headers, json=payload)
    assert retry.status_code == (201 if operation == "create" else 200), retry.text


async def test_screen_replay_retains_original_result_after_guide_and_task_advance(task_client):
    from tests.test_tasks import (
        complete_guide_payload,
        create_policy_bundle_for_guide,
        seed_active_guide_for_downstream_test,
    )

    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    path = f"/api/v1/tasks/{task['id']}/screen"
    headers = auth_headers()
    first = await task_client.post(path, headers=headers)
    assert first.status_code == 200, first.text
    successor = await task_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=complete_guide_payload("v2"),
    )
    assert successor.status_code == 201, successor.text
    await create_policy_bundle_for_guide(task_client, project["id"], successor.json()["id"])
    await seed_active_guide_for_downstream_test(
        db_session.get_session_factory(), project_id=project["id"], guide_id=successor.json()["id"]
    )
    replay = await task_client.post(path, headers=headers)
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    released = await task_client.post(
        f"/api/v1/tasks/{task['id']}/release",
        headers=auth_headers(),
        json={"reason": "Release frozen rules"},
    )
    assert released.status_code == 200, released.text
    assert released.json()["locked_guide_version"] == first.json()["locked_guide_version"] == "v1"
    retained = await task_client.post(path, headers=headers)
    assert retained.status_code == 200, retained.text
    assert retained.json() == first.json()
    async with db_session.get_session_factory()() as session:
        events = list(
            await session.scalars(
                select(AuditEvent.event_type)
                .where(AuditEvent.entity_id == task["id"])
                .order_by(AuditEvent.created_at)
            )
        )
        assert events == ["TaskCreated", "TaskScreened", "TaskReleased"]
