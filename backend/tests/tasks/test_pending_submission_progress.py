"""Task display separates accepted pending work from retained submission history."""

from unittest.mock import patch

import pytest
from sqlalchemy import text

from tests.retained_material_fixtures import finalize_retained_intake
from tests.submission_fixtures import seed_retained_submission, route_retained_checker_remediation
from tests.test_tasks import (
    task_client, task_database_env,  # noqa: F401 -- pytest fixtures
    create_active_project, create_started_task, complete_submission_payload,
    set_dev_actor, auth_headers, admit_and_grant_project_submitter,
)


@pytest.mark.parametrize("revision", [False, True])
async def test_pending_task_progress_is_authorized_and_clears_after_finalization(
    task_client, monkeypatch, revision,  # noqa: F811
):
    project = await create_active_project(task_client)
    task = await create_started_task(task_client, project["id"], monkeypatch)
    predecessor = None
    if revision:
        predecessor = await seed_retained_submission(task["id"], complete_submission_payload())
        await route_retained_checker_remediation(predecessor)
    await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], "other-reader")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    observed = []

    async def read_details(management=False):
        prefix = f"/api/v1/projects/{project['id']}" if management else "/api/v1"
        values = []
        for suffix in ("", "/work-context"):
            response = await task_client.get(f"{prefix}/tasks/{task['id']}{suffix}", headers=auth_headers())
            assert response.status_code == 200, response.text
            body = response.json()
            values.append(body["task"] if suffix else body)
        return values

    async def inspect_pending(factory, intake):
        expected = {"operation_id": str(intake.operation_id), "processing_stage": "finalization_pending"}
        with patch("app.adapters.artifacts.create_artifact_store_bootstrap", side_effect=AssertionError("progress opened provider")):
            for manager in (False, True):
                set_dev_actor(monkeypatch, roles="project_manager" if manager else "worker",
                              subject="project-manager-subject" if manager else "worker-one")
                for detail in await read_details(manager):
                    assert detail["pending_submission_operation"] == expected
                    assert detail["status"] == "evaluation_pending"
            set_dev_actor(monkeypatch, roles="viewer", subject="other-reader")
            for suffix in ("", "/work-context"):
                concealed = await task_client.get(f"/api/v1/tasks/{task['id']}{suffix}", headers=auth_headers())
                assert concealed.status_code == 404, concealed.text
                assert str(intake.operation_id) not in concealed.text
            set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
            history = await task_client.get(f"/api/v1/tasks/{task['id']}/submissions", headers=auth_headers())
            if revision:
                assert history.status_code == 200, history.text
                assert [item["id"] for item in history.json()["items"]] == [predecessor]
            else:
                assert history.status_code == 404, history.text
                async with factory() as session:
                    assert await session.scalar(text("SELECT count(*) FROM submissions WHERE task_id=:id"), {"id": task["id"]}) == 0
        observed.append(intake.operation_id)
        return await finalize_retained_intake(factory, intake)

    with patch("tests.submission_fixtures.finalize_retained_intake", inspect_pending):
        result = await seed_retained_submission(
            task["id"], complete_submission_payload(), predecessor_id=predecessor,
        )
    assert result != predecessor and len(observed) == 1
    for manager in (False, True):
        set_dev_actor(monkeypatch, roles="project_manager" if manager else "worker",
                      subject="project-manager-subject" if manager else "worker-one")
        for detail in await read_details(manager):
            assert detail["pending_submission_operation"] is None
