"""Contributor visibility retains every existing owned-assignment state."""
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.tasks.lifecycle import ALLOWED_TASK_TRANSITIONS
from app.modules.tasks.models import TaskAssignment, WorkstreamTask
from tests.authorization.task_queues.support import grant_queue_role
from tests.authorization.task_reads.support import create_task, path, task_case


@pytest.mark.parametrize("kind", ("contributor_detail", "contributor_requirements"))
async def test_task_read_contributor_visibility(admin_access, kind):
    project, manager, task = await task_case(admin_access)
    await grant_queue_role(admin_access, project, "submitter")
    client, actor = admin_access.signed.client, admin_access.target
    async def request(target=task):
        return await client.get(path(kind, project, target), headers=actor.headers)
    assert (await request()).status_code == 200
    claimed = await client.post(f"/api/v1/tasks/{task}/claim", headers=actor.headers | {"Idempotency-Key": str(uuid4())})
    assert claimed.status_code == 200, claimed.text
    factory = db_session.get_session_factory()
    states = {state for transition in ALLOWED_TASK_TRANSITIONS for state in transition}
    assert len(states) == 9
    for state in states:
        async with factory() as session, session.begin():
            row = await session.get(WorkstreamTask, str(task))
            row.status = state
        response = await request()
        assert response.status_code == 200, (state, response.text)
    other = await admin_access.signed.actor("other-owner")
    cases = {
        "wrong_contributor": ("claimed", str(actor.id), str(other.id), "active"),
        "wrong_assignee": ("claimed", str(other.id), str(actor.id), "active"),
        "active_only": ("ready", None, str(actor.id), "active"),
        "unrelated": ("claimed", str(actor.id), None, None),
        "released": ("claimed", str(actor.id), str(actor.id), "released"),
        "assignee_only": ("ready", str(actor.id), None, None),
        "draft": ("draft", None, None, None),
    }
    for name,(status,assignee,contributor,assignment_status) in cases.items():
        target = await create_task(admin_access, project, manager)
        async with factory() as session, session.begin():
            row = await session.get(WorkstreamTask, str(target))
            row.status, row.assigned_to = status, assignee
            if contributor:
                session.add(TaskAssignment(id=str(new_record_id()), task_id=row.id, project_id=row.project_id,
                    contributor_id=contributor, assigned_by=str(actor.id), status=assignment_status,
                    submitter_contribution_policy_version_id=row.locked_contribution_policy_version_id))
        async with factory() as session:
            row = await session.get(WorkstreamTask, str(target))
            assignment = await session.scalar(select(TaskAssignment).where(TaskAssignment.task_id == row.id))
            assert (row.status,row.assigned_to,assignment.contributor_id if assignment else None,assignment.status if assignment else None) == cases[name]
        denied = await request(target)
        assert denied.status_code == 404, (name,denied.text)
