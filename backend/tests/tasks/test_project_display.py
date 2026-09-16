"""Exact detached PROJECTS display and existing TASK HTTP behavior."""

import asyncio
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.db import session as db_session
from app.modules.projects.api import ProjectDisplayFacts, GuideDisplayFacts
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
from app.modules.projects.models import Project, ProjectGuide
from app.modules.tasks.models import AuditEvent, WorkstreamTask
from tests.projects.locked_policy_fixtures import activated_context, frozen_request
from tests.test_tasks import (
    task_database_env as task_database_env,
    task_client as task_client,
    auth_headers, set_dev_actor, complete_task_payload, complete_guide_payload,
    create_active_project, create_started_task, create_policy_bundle_for_guide,
    seed_active_guide_for_downstream_test, task_artifact_proposal,
)


@pytest.mark.parametrize("field", ("id", "name", "slug", "description"))
def test_project_display_rejects_non_scalar_values(field):
    facts = ProjectDisplayFacts(uuid4(), "Project", "project", None)
    with pytest.raises(ValueError, match="project display facts are invalid"):
        replace(facts, **{field: []})


@pytest.mark.parametrize("field", ("id", "project_id", "version", "change_summary", "effective_at"))
def test_guide_display_rejects_non_scalar_values(field):
    facts = GuideDisplayFacts(uuid4(), uuid4(), "guide", None, datetime.now(UTC))
    with pytest.raises(ValueError, match="guide display facts are invalid"):
        replace(facts, **{field: []})


async def test_context_display_identity_and_immutability(clean_postgres_database):
    async with activated_context(clean_postgres_database) as (factory, receipt, *_):
        async with factory() as session, session.begin():
            facts = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(
                frozen_request(receipt)
            )
            project = await session.get(Project, str(facts.project_id))
            guide = await session.get(ProjectGuide, str(facts.guide_id))
            assert facts.project == ProjectDisplayFacts(
                UUID(project.id), project.name, project.slug, project.description,
            )
            assert facts.guide == GuideDisplayFacts(
                UUID(guide.id), UUID(guide.project_id), guide.version,
                guide.change_summary, guide.effective_at,
            )
        assert replace(facts) == facts
        replacements = [dict(project=replace(facts.project, id=uuid4()))]
        for field, value in (
            ("project_id", uuid4()), ("id", uuid4()), ("version", "foreign-guide"),
            ("effective_at", facts.guide.effective_at + timedelta(seconds=1)),
        ):
            replacements.append(dict(guide=replace(facts.guide, **{field: value})))
        replacements.extend((dict(project=project), dict(guide=guide)))
        for replacement in replacements:
            with pytest.raises(ValueError, match="display facts differ from locked context"):
                replace(facts, **replacement)
        for value, field in ((facts.project, "name"), (facts.guide, "change_summary")):
            with pytest.raises(FrozenInstanceError):
                setattr(value, field, "altered")
            assert not hasattr(value, "_sa_instance_state")
        old_name = facts.project.name
        project.name = "detached ORM changed"
        assert facts.project.name == old_name


async def _draft_project(client):
    response = await client.post(
        "/api/v1/projects", headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json={"name": "Before guide", "slug": "before-guide-" + uuid4().hex},
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "draft"
    return response.json()


async def test_project_display_lookup_preserves_draft_and_transaction(task_client):
    project = await _draft_project(task_client)
    factory = db_session.get_session_factory()
    async with factory() as session:
        owner = ProjectLockedPolicyRepository(session)
        assert not session.in_transaction()
        expected = await owner.read_project_display(UUID(project["id"]))
        assert expected.id == UUID(project["id"]) and expected.name == project["name"]
        assert await owner.read_project_display(uuid4()) is None
        assert await session.scalar(select(func.count()).select_from(ProjectGuide)) == 0
        pending = Project(id=str(uuid4()), slug="invalid-without-required-name")
        session.add(pending)
        assert await owner.read_project_display(UUID(project["id"])) == expected
        assert pending in session.new and session.in_transaction()
        await session.rollback()
    async with factory() as session:
        marker = await session.get(Project, project["id"])
        marker.description = "flushed but uncommitted"
        await session.flush()
        display = await ProjectLockedPolicyRepository(session).read_project_display(UUID(project["id"]))
        assert display.description == "flushed but uncommitted" and session.in_transaction()
        await session.rollback()
    async with factory() as observer:
        assert (await observer.get(Project, project["id"])).description is None
        assert await observer.get(Project, pending.id) is None


async def test_project_display_lookup_does_not_wait_for_project_lock(task_client):
    project = await _draft_project(task_client)
    factory = db_session.get_session_factory()
    async with factory() as writer, factory() as reader:
        locked = await writer.scalar(
            select(Project).where(Project.id == project["id"]).with_for_update()
        )
        assert locked.id == project["id"] and writer.in_transaction()
        display = await asyncio.wait_for(
            ProjectLockedPolicyRepository(reader).read_project_display(UUID(project["id"])), 5,
        )
        assert display.name == project["name"] and writer.in_transaction()
        await writer.rollback()
        await reader.rollback()


async def _task_audit_counts():
    async with db_session.get_session_factory()() as session:
        return tuple([
            await session.scalar(select(func.count()).select_from(model))
            for model in (WorkstreamTask, AuditEvent)
        ])


async def test_task_creation_before_guide_and_missing_project_atomicity(task_client, monkeypatch):
    project = await _draft_project(task_client)
    response = await task_client.post(
        f"/api/v1/projects/{project['id']}/tasks", headers=auth_headers(),
        json=complete_task_payload(),
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "draft"
    before = await _task_audit_counts()
    for missing in (str(uuid4()), "malformed-project", project["id"].replace("-", "")):
        response = await task_client.post(
            f"/api/v1/projects/{missing}/tasks", headers=auth_headers(),
            json=complete_task_payload(),
        )
        assert response.status_code == 422, response.text
        assert response.json()["detail"] == "project not found"
        assert await _task_audit_counts() == before
    set_dev_actor(monkeypatch, roles="worker", subject="draft-denial")
    # Resolve the actor before measuring product/audit writes for the denial.
    await task_client.get("/api/v1/actors/me", headers=auth_headers())
    before = await _task_audit_counts()
    denied = await task_client.post(
        "/api/v1/projects/malformed-project/tasks", headers=auth_headers(),
        json=complete_task_payload(),
    )
    assert denied.status_code == 403, denied.text
    assert await _task_audit_counts() == before


async def test_task_display_survives_guide_successor_for_contributor_and_manager(
    task_client, monkeypatch,
):
    project = await create_active_project(task_client)
    task = await create_started_task(task_client, project["id"], monkeypatch)
    url = f"/api/v1/tasks/{task['id']}/work-context"
    original = await task_client.get(url, headers=auth_headers())
    assert original.status_code == 200, original.text
    original = original.json()
    requirements_url = f"/api/v1/tasks/{task['id']}/submission-requirements"
    first_requirements = await task_client.get(requirements_url, headers=auth_headers())
    assert first_requirements.status_code == 200, first_requirements.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    successor = await task_client.post(
        f"/api/v1/projects/{project['id']}/guides", headers=auth_headers(),
        json={**complete_guide_payload("v2"), "change_summary": "Different successor summary"},
    )
    assert successor.status_code == 201, successor.text
    await create_policy_bundle_for_guide(
        task_client, project["id"], successor.json()["id"],
        task_artifact_proposal().model_copy(update={"required_artifacts": ("v2-answer.md",)}),
    )
    await seed_active_guide_for_downstream_test(
        db_session.get_session_factory(), project_id=project["id"], guide_id=successor.json()["id"],
    )
    manager = await task_client.get(
        f"/api/v1/projects/{project['id']}/tasks/{task['id']}/work-context", headers=auth_headers(),
    )
    assert manager.status_code == 200, manager.text
    foreign = await task_client.get(
        f"/api/v1/projects/{uuid4()}/tasks/{task['id']}/work-context", headers=auth_headers(),
    )
    assert foreign.status_code == 404, foreign.text
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    contributor = await task_client.get(url, headers=auth_headers())
    assert contributor.status_code == 200, contributor.text
    for response in (manager.json(), contributor.json()):
        assert set(response) == set(original)
        assert response["guide"] == original["guide"]
        assert set(response["guide"]) == {"id", "version", "change_summary", "effective_at"}
        assert response["project"] == original["project"]
        assert set(response["task"]) == set(original["task"])
        assert response["guide"]["id"] != successor.json()["id"]
    requirements = await task_client.get(requirements_url, headers=auth_headers())
    assert requirements.status_code == 200, requirements.text
    assert requirements.json()["guide_version"] == "v1"
    assert requirements.json()["required_artifacts"] == first_requirements.json()["required_artifacts"]
    assert requirements.json()["required_artifacts"][0]["path"] == "answer.md"
