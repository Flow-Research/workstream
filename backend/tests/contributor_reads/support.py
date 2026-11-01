"""One real claimed, prepared and submitted task through the shared task harness."""

from tests.checkers.external.support import post_registry_spec
from tests.submission_fixtures import seed_retained_checker_run, seed_retained_submission
from tests.test_tasks import (
    admit_and_grant_project_submitter, auth_headers, complete_submission_payload,
    create_active_project, create_started_task, set_dev_actor,
)

OWNER, OTHER, MANAGER = "worker-one", "worker-two", "project-manager-subject"
ME = "/api/v1/actors/me"


async def submitted_case(client, monkeypatch, *, slug=None):
    """worker-one holds a started task with one real prepared Submission and checker run."""
    project = await create_active_project(
        client, post_submit_registry_spec=post_registry_spec(), **({"slug": slug} if slug else {}),
    )
    task = await create_started_task(client, project["id"], monkeypatch)
    submission = await seed_retained_submission(task["id"], complete_submission_payload())
    await seed_retained_checker_run(submission)
    return project["id"], task["id"], submission


async def as_actor(client, monkeypatch, subject, *, grant_project=None):
    """Switch the caller; optionally admit it with a Submitter grant first."""
    if grant_project is not None:
        await admit_and_grant_project_submitter(client, monkeypatch, grant_project, subject)
    set_dev_actor(monkeypatch, roles="", subject=subject)


async def get_ok(client, path, **params):
    response = await client.get(path, params=params, headers=auth_headers())
    assert response.status_code == 200, response.text
    return response.json()


async def status_of(client, path, **params):
    return (await client.get(path, params=params, headers=auth_headers())).status_code


def preparations_path(task):
    return f"/api/v1/tasks/{task}/submission-bundle-preparations"


async def start_another(client, monkeypatch, project, subject=OWNER):
    """Claim one more ready task for an already granted contributor."""
    from tests.test_tasks import create_ready_task

    set_dev_actor(monkeypatch, roles="project_manager", subject=MANAGER)
    task = await create_ready_task(client, project)
    set_dev_actor(monkeypatch, roles="", subject=subject)
    response = await client.post(f"/api/v1/tasks/{task['id']}/claim", headers=auth_headers(),
                                 json={"reason": "Claim another task"})
    assert response.status_code == 200, response.text
    assert response.json()["task"]["status"] == "in_progress"
    set_dev_actor(monkeypatch, roles="worker", subject=subject)
    return task["id"]
