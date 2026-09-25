"""Real project/task setup and distinct signed read audiences."""
from uuid import UUID, uuid4

from tests.authorization.task_queues.support import project_fixture
from tests.authorization.task_authority.test_postgresql import project_manager
from tests.test_tasks import complete_task_payload

READS = {
    "contributor_detail": ("/api/v1/tasks/{task}", "task.read"),
    "contributor_requirements": ("/api/v1/tasks/{task}/submission-requirements", "task.submission_requirements.read"),
    "management_detail": ("/api/v1/projects/{project}/tasks/{task}", "project.task.read"),
    "management_requirements": ("/api/v1/projects/{project}/tasks/{task}/submission-requirements", "project.task.submission_requirements.read"),
}


async def task_case(access, *, ready=True):
    project = await project_fixture()
    manager = await project_manager(access, project)
    task = await create_task(access, project, manager, ready=ready)
    return project, manager, task


async def create_task(access, project, manager, *, ready=True):
    client = access.signed.client
    response = await client.post(f"/api/v1/projects/{project}/tasks", headers=manager.headers | {"Idempotency-Key": str(uuid4())}, json=complete_task_payload())
    assert response.status_code == 201, response.text
    task = UUID(response.json()["id"])
    if ready:
        for command in ("screen", "release"):
            response = await client.post(f"/api/v1/tasks/{task}/{command}", headers=manager.headers | {"Idempotency-Key": str(uuid4())}, json={"reason": "Prepare governed task"})
            assert response.status_code == 200, response.text
    return task


def path(kind, project, task):
    return READS[kind][0].format(project=project, task=task)
