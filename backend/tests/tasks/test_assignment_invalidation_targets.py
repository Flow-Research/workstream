"""Exact scalar target selection and absence of TASK locks during authority loss."""

from datetime import timedelta
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import func, select, text

from app.modules.tasks.api.assignment_invalidation import AssignmentInvalidationTargetsRequest
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.models import TaskAssignment, WorkstreamTask
from tests.test_tasks import task_client as task_client, task_database_env as task_database_env
from tests.tasks.invalidation_support import setup_assignment


@pytest.mark.parametrize("started", [False, True], ids=["claimed", "in_progress"])
async def test_target_projection_exact_membership(task_client, monkeypatch, started):
    s = await setup_assignment(task_client, monkeypatch, started=started)
    async with s.sessions() as session:
        assert await session.scalar(select(WorkstreamTask.status).where(
            WorkstreamTask.id == s.task["id"],
        )) == ("in_progress" if started else "claimed")
        assigned_at = await session.scalar(select(TaskAssignment.assigned_at).where(
            TaskAssignment.id == s.assignment["id"],
        ))
        request = AssignmentInvalidationTargetsRequest(
            contributor_id=UUID(s.grant["actor_profile_id"]), project_id=UUID(s.project["id"]),
            invalidation_event_id=new_record_id(), invalidated_at=assigned_at,
        )
        reader = TaskRepository(session)
        page = await reader.read_assignment_invalidation_targets_page(request)
        assert [item.assignment_id for item in page.items] == [UUID(s.assignment["id"])]
        assert page.next_after is None
        for changes in (
            {"contributor_id": new_record_id()}, {"project_id": new_record_id()},
            {"invalidated_at": assigned_at - timedelta(microseconds=1)},
            {"after": UUID(s.assignment["id"])},
        ):
            assert (await reader.read_assignment_invalidation_targets_page(
                request.model_copy(update=changes),
            )).items == ()
        all_projects = await reader.read_assignment_invalidation_targets_page(
            request.model_copy(update={"project_id": None}),
        )
        assert all_projects.items == page.items


async def test_target_projection_is_nonlocking(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    async with s.sessions() as locked, locked.begin(), s.sessions() as reader, reader.begin():
        await locked.execute(text("select id from workstream_tasks where id=:id for update"),
                             {"id": s.task["id"]})
        await locked.execute(text("select id from task_assignments where id=:id for update"),
                             {"id": s.assignment["id"]})
        await reader.execute(text("set local lock_timeout='200ms'"))
        request = AssignmentInvalidationTargetsRequest(
            contributor_id=UUID(s.grant["actor_profile_id"]), project_id=UUID(s.project["id"]),
            invalidation_event_id=new_record_id(), invalidated_at=await reader.scalar(select(func.clock_timestamp())),
        )
        page = await TaskRepository(reader).read_assignment_invalidation_targets_page(request)
        assert [item.assignment_id for item in page.items] == [UUID(s.assignment["id"])]


@pytest.mark.parametrize("field,value", [("contributor_id", "bad"), ("invalidated_at", "2026-01-01")])
def test_target_projection_request_rejects_untyped_values(field, value):
    from datetime import datetime, UTC
    from pydantic import ValidationError
    fields = dict(contributor_id=new_record_id(), project_id=None, invalidation_event_id=new_record_id(),
                  invalidated_at=datetime.now(UTC))
    with pytest.raises(ValidationError):
        AssignmentInvalidationTargetsRequest(**(fields | {field: value}))


async def test_target_projection_independent_state_predicates(task_client, monkeypatch):
    """Each excluded state reaches the reader, with a valid control restored between cases."""
    from sqlalchemy import update
    from app.modules.tasks.models import WorkstreamTask

    s = await setup_assignment(task_client, monkeypatch)
    async with s.sessions() as session, session.begin():
        request = AssignmentInvalidationTargetsRequest(
            contributor_id=UUID(s.grant["actor_profile_id"]), project_id=UUID(s.project["id"]),
            invalidation_event_id=new_record_id(), invalidated_at=await session.scalar(select(func.clock_timestamp())),
        )
        reader = TaskRepository(session)
        mutations = (
            update(TaskAssignment).where(TaskAssignment.id == s.assignment["id"]).values(status="completed"),
            update(TaskAssignment).where(TaskAssignment.id == s.assignment["id"]).values(released_at=func.clock_timestamp()),
            update(WorkstreamTask).where(WorkstreamTask.id == s.task["id"]).values(status="screening"),
            update(WorkstreamTask).where(WorkstreamTask.id == s.task["id"]).values(assigned_to=None),
        )
        for mutation in mutations:
            assert len((await reader.read_assignment_invalidation_targets_page(request)).items) == 1
            nested = await session.begin_nested()
            try:
                await session.execute(mutation)
                assert (await reader.read_assignment_invalidation_targets_page(request)).items == ()
            finally:
                await nested.rollback()


async def test_target_projection_excludes_retained_submission(task_client, monkeypatch):
    from sqlalchemy import update
    from app.modules.tasks.models import WorkstreamTask
    from app.modules.tasks.service import TaskService
    from tests.submission_fixtures import seed_retained_submission
    from tests.test_tasks import complete_submission_payload

    s = await setup_assignment(task_client, monkeypatch, started=True)
    async def hold_dispatch(*_args, **_kwargs):
        pass
    monkeypatch.setattr(TaskService, "_enqueue_pre_review_gate_after_commit", hold_dispatch)
    await seed_retained_submission(s.task["id"], complete_submission_payload())
    async with s.sessions() as session, session.begin():
        # Isolate retained evidence from the separate task-state exclusion.
        await session.execute(update(WorkstreamTask).where(WorkstreamTask.id == s.task["id"]).values(status="in_progress"))
        request = AssignmentInvalidationTargetsRequest(contributor_id=UUID(s.grant["actor_profile_id"]),
            project_id=UUID(s.project["id"]), invalidation_event_id=new_record_id(),
            invalidated_at=await session.scalar(select(func.clock_timestamp())))
        assert (await TaskRepository(session).read_assignment_invalidation_targets_page(request)).items == ()
