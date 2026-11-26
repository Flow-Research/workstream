"""Manager CLI reads through real HTTP/API/PostgreSQL authority and retained rows.

The existing fixture arranges approved policy, a started task and
manager/Submitter grants. The tested Submission is created by the public CLI;
this test makes no backend authority or checker decision on the CLI's behalf.
"""

import asyncio
from datetime import UTC, datetime
import json
import sys
from pathlib import Path
from uuid import UUID, uuid4
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from test_submission_public_api import socket_api

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND / "tests"))
from tests.conftest import (  # noqa: E402
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
    isolated_database_env as isolated_database_env,
)
from tests.tasks.test_submission_lineage import _submission_task  # noqa: E402
from tests.tasks.test_public_submission_intake import _client  # noqa: E402
from tests.project_create_fixtures import (  # noqa: E402
    grant_fixture_admin_role,
    seed_historical_project,
)
from app.core.identifiers import new_record_id  # noqa: E402
from app.modules.authorization.models import AdminRoleGrant  # noqa: E402


@pytest.mark.asyncio
async def test_manager_context_history_and_checker_authority(
    isolated_database_env,
    tmp_path,
    monkeypatch,
    cli,
):
    async with _submission_task(isolated_database_env, tmp_path) as h:
        async with _client(h, monkeypatch, isolated_database_env) as direct:
            from tests.artifacts.test_submission_foreground_command import (
                configure_source_http,
            )
            from tests.retained_material_fixtures import finalize_retained_intake

            _, settings, runtime_errors, runtime_calls = await configure_source_http(
                h.factory,
                direct,
                tmp_path,
                monkeypatch,
                h.archive_bytes,
                "completed",
            )
            archive = tmp_path / "manager-submission.zip"
            archive.write_bytes(h.archive_bytes)
            async with socket_api(direct._transport.app) as origin:
                project, task = str(h.project_id), str(h.task_id)

                async def call(*args, status=200):
                    result = await asyncio.to_thread(
                        cli,
                        origin,
                        "public-intake-token",
                        "-o",
                        "json",
                        *args,
                        process_timeout=90 if args[:2] == ("task", "submit") else 20,
                    )
                    if status != 200:
                        assert result.returncode == 1 and result.stdout == "", (
                            result.stderr
                        )
                        assert json.loads(result.stderr)["error"]["status"] == status
                        return None
                    assert result.returncode == 0 and result.stderr == "", result.stderr
                    return json.loads(result.stdout)

                paths = (await direct.get("/openapi.json")).json()["paths"]
                routes = (
                    (
                        "task-requirements",
                        f"/api/v1/projects/{project}/tasks/{task}/submission-requirements",
                        "project.task.submission_requirements.read",
                    ),
                    (
                        "task-locked-context",
                        f"/api/v1/projects/{project}/tasks/{task}/locked-context",
                        "project.task.locked_context.read",
                    ),
                    (
                        "task-context",
                        f"/api/v1/projects/{project}/tasks/{task}/work-context",
                        "project.task.work_context.read",
                    ),
                )
                for command, path, action in routes:
                    template = path.replace(project, "{project_id}").replace(
                        task, "{task_id}"
                    )
                    assert paths[template]["get"]["x-workstream-action-id"] == action
                    actual = await call("project", command, project, task)
                    expected = await direct.get(
                        path, headers={"Authorization": "Bearer public-intake-token"}
                    )
                    assert expected.status_code == 200, expected.text
                    assert actual == expected.json()
                assert "lifecycle" not in (
                    await call("project", "task-context", project, task)
                )

                receipt = await call(
                    "task",
                    "submit",
                    task,
                    "--assignment",
                    str(h.assignment_id),
                    "--file",
                    str(archive),
                    "--idempotency-key",
                    str(uuid4()),
                    "--feedback",
                    "Completed the required project work and included evidence.",
                )
                assert receipt["status"] == "accepted" and receipt["replayed"] is False
                assert len(runtime_calls) == 1 and not runtime_errors, runtime_errors
                submission = str(
                    await finalize_retained_intake(
                        h.factory,
                        SimpleNamespace(
                            operation_id=UUID(receipt["operation_id"]),
                            settings=settings,
                            store=h.store,
                            namespace=h.namespace,
                        ),
                    )
                )
                [item] = (
                    await call(
                        "project", "task-submissions", project, task, "--limit", "1"
                    )
                )["items"]
                assert item["id"] == submission and item["contributor_id"] == str(
                    h.context.actor_profile_id
                )
                assert item["locked_review_policy_generation"] > 0
                detail = await call("project", "submission", project, submission)
                assert detail == item
                run_page = await call(
                    "project", "checker-runs", project, submission, "--limit", "1"
                )
                [run] = run_page["items"]
                assert run["submission_id"] == submission and run["status"] == "queued"
                assert (
                    await call(
                        "project",
                        "checker-runs",
                        project,
                        submission,
                        "--run",
                        run["id"],
                    )
                    == run
                )
                assert (
                    "routing_recommendation" in run
                    and "routing_recommendation"
                    not in (await call("submission", "findings", submission))["items"][
                        0
                    ]
                )

                foreign_project = str(new_record_id())
                async with h.factory.begin() as session:
                    await seed_historical_project(
                        session,
                        project_id=foreign_project,
                        name="Manager evidence foreign project",
                        slug=f"manager-evidence-foreign-{foreign_project}",
                    )
                    foreign_grant = await grant_fixture_admin_role(
                        session,
                        h.context.actor_profile_id,
                        project_id=foreign_project,
                    )
                    assert foreign_grant.status == "active"
                assert (await call("project", "show", foreign_project))["id"] == (
                    foreign_project
                )
                for args in (
                    ("project", "task-requirements", foreign_project, task),
                    ("project", "task-locked-context", foreign_project, task),
                    ("project", "task-context", foreign_project, task),
                    ("project", "task-submissions", foreign_project, task),
                    ("project", "submission", foreign_project, submission),
                    ("project", "checker-runs", foreign_project, submission),
                    (
                        "project",
                        "checker-runs",
                        foreign_project,
                        submission,
                        "--run",
                        run["id"],
                    ),
                ):
                    await call(*args, status=404)

                for args in (
                    ("project", "task-requirements", str(uuid4()), task),
                    ("project", "task-submissions", str(uuid4()), task),
                    ("project", "submission", project, str(uuid4())),
                    (
                        "project",
                        "checker-runs",
                        project,
                        submission,
                        "--run",
                        str(uuid4()),
                    ),
                ):
                    await call(*args, status=404)

                async with h.factory.begin() as session:
                    grant = await session.scalar(
                        select(AdminRoleGrant).where(
                            AdminRoleGrant.target_actor_profile_id
                            == str(h.context.actor_profile_id),
                            AdminRoleGrant.role == "project_manager",
                            AdminRoleGrant.scope_project_id == project,
                            AdminRoleGrant.status == "active",
                        )
                    )
                    assert grant is not None
                    grant.status = "revoked"
                    grant.version = 2
                    grant.revoked_by_actor_profile_id = (
                        grant.granted_by_actor_profile_id
                    )
                    grant.revoked_by_admin_role_grant_id = (
                        grant.granted_by_admin_role_grant_id
                    )
                    grant.revoked_reason = "Manager read authority withdrawn in fixture"
                    grant.revoked_at = datetime.now(UTC)
                for args, denied in (
                    (("project", "task-context", project, task), 403),
                    (("project", "submission", project, submission), 404),
                    (("project", "checker-runs", project, submission), 404),
                ):
                    await call(*args, status=denied)
