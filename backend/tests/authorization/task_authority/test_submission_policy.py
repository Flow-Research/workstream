"""Locked-policy rejection through public raw-ZIP intake before source custody."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from app.db import models as db_models
from app.modules.projects.models import (
    PostSubmitCheckerPolicy,
)
from app.modules.tasks.api import TaskSubmissionContextUnavailable
from app.modules.projects.api.locked_policy import ProjectLockedPolicyContextUnavailable
from app.modules.tasks.models import AuditEvent, Submission, TaskAssignment, WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from tests.projects.policy_read_faults import corrupt_locked_policy_reads
from tests import test_tasks as task_fixtures
from tests.test_tasks import (
    auth_headers,
    create_active_project,
    create_started_task,
)


task_database_env = task_fixtures.task_database_env
task_client = task_fixtures.task_client


async def _reject_public_submission(client, task_id, tmp_path, monkeypatch, expected):
    """Keep exact owner refusal observable while exercising the real HTTP mapping."""
    from app.modules.artifacts.intake.foreground_admission import ForegroundIntakeAdmission
    from tests.artifacts.test_submission_foreground_command import configure_source_http
    factory = db_session.get_session_factory()
    _, _, errors, calls = await configure_source_http(
        factory, client, tmp_path, monkeypatch, b"unused", "completed")
    tables = ("submission_intake_operations", "submission_source_charges", "submissions",
              "checker_runs", "checker_results", "audit_events", "outbox_events")
    async def snapshot():
        async with factory() as session:
            return {table: list(await session.scalars(text(
                f"SELECT to_jsonb(r)::text FROM public.{table} r ORDER BY to_jsonb(r)::text"
            ))) for table in tables}
    before = await snapshot()
    async with factory() as session:
        assignment = await session.scalar(select(TaskAssignment).where(
            TaskAssignment.task_id == task_id, TaskAssignment.status == "active"))
        assignment_id = assignment.id
    failures = []
    validate = ForegroundIntakeAdmission._validate_context
    async def observe(owner, *args):
        try:
            return await validate(owner, *args)
        except expected as exc:
            failures.append(exc)
            raise
    async def forbidden_body():
        pytest.fail("invalid locked policy read the request body")
        yield b"never"
    with monkeypatch.context() as patch:
        patch.setattr(ForegroundIntakeAdmission, "_validate_context", observe)
        response = await client.post(f"/api/v1/tasks/{task_id}/submissions",
            headers=auth_headers() | {"Content-Type": "application/zip",
                "X-Task-Assignment-Id": assignment_id}, content=forbidden_body())
    assert len(failures) == 1
    expected_code = ("task_submission_context_invalid" if expected is TaskSubmissionContextUnavailable
                     else "project_locked_policy_context_changed")
    assert failures[0].code == expected_code
    assert response.status_code == (404 if expected is TaskSubmissionContextUnavailable else 503), response.text
    assert response.json()["error"]["code"] == (
        "submission_unavailable" if expected is TaskSubmissionContextUnavailable
        else "submission_infrastructure_unavailable")
    assert await snapshot() == before
    assert calls == [] and errors == []


@pytest.mark.parametrize("field", [
    "locked_post_submit_checker_policy_body",
    "locked_review_policy_hash",
    "locked_revision_policy_hash",
])
async def test_invalid_locked_policy_never_reaches_art_or_submission(
    task_client, monkeypatch, field,
):
    project = await create_active_project(task_client)
    task_response = await create_started_task(task_client, project["id"], monkeypatch)
    async with db_session.get_session_factory()() as session:
        with pytest.raises(IntegrityError, match="task revision context lacks current preparation"):
            async with session.begin():
                task = await session.get(WorkstreamTask, task_response["id"])
                original = getattr(task, field)
                # A released TASK can change these locks only through its
                # authorized current revision preparation. This BEFORE UPDATE
                # guard precedes policy FK checks and any ART participation.
                setattr(task, field, {} if field.endswith("body") else "sha256:" + "f" * 64)
                await session.flush()
        assert await session.scalar(select(Submission).where(
            Submission.task_id == task_response["id"],
        )) is None
        restored = await session.get(WorkstreamTask, task_response["id"])
        assert getattr(restored, field) == original
        assert restored.status == "in_progress"


async def test_submission_pre_submit_rejects_mutated_effective_policy_body(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    await corrupt_locked_policy_reads(monkeypatch, started_task["id"], "stale_effective")

    await _reject_public_submission(task_client, started_task["id"], tmp_path, monkeypatch,
                                    ProjectLockedPolicyContextUnavailable)

    async with db_session.get_session_factory()() as session:
        submissions = (
            (
                await session.execute(
                    select(Submission).where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
    assert submissions == []
    assert checker_runs == []


async def test_submission_rejects_malformed_locked_post_submit_policy_body_without_side_effects(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        corrupted_body = dict(task.locked_post_submit_checker_policy_body or {})
        corrupted_body["required_checkers"] = [
            "check_policy_context_present",
            "check_evidence_present",
        ]
        original_body = dict(task.locked_post_submit_checker_policy_body)

    original_get = TaskRepository.get_task

    async def corrupt_task_read(repository, task_id, **kwargs):
        task = await original_get(repository, task_id, **kwargs)
        if task is not None and task.id == started_task["id"]:
            # A detached storage fault exercises the read guard without editing
            # the locked row or disabling its current preparation guard.
            repository._session.expunge(task)
            task.locked_post_submit_checker_policy_body = dict(corrupted_body)
        return task

    monkeypatch.setattr(TaskRepository, "get_task", corrupt_task_read)

    await _reject_public_submission(task_client, started_task["id"], tmp_path, monkeypatch,
                                    TaskSubmissionContextUnavailable)
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        submissions = (
            (
                await session.execute(
                    select(Submission).where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
        runs = (
            (
                await session.execute(
                    select(db_models.CheckerRun)
                    .join(Submission, db_models.CheckerRun.submission_id == Submission.id)
                    .where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
        results = (
            (
                await session.execute(
                    select(db_models.CheckerResult)
                    .join(Submission, db_models.CheckerResult.submission_id == Submission.id)
                    .where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
        audit_events = (
            (
                await session.execute(
                    select(AuditEvent).where(AuditEvent.entity_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )

    assert task is not None
    assert task.status == "in_progress"
    assert task.locked_post_submit_checker_policy_body == original_body
    assert submissions == []
    assert runs == []
    assert results == []
    assert "submission_created" not in {event.event_type for event in audit_events}
    assert "submission_finalized" not in {event.event_type for event in audit_events}
    assert "checker_run_triggered" not in {event.event_type for event in audit_events}


async def test_submission_pre_submit_rejects_mutated_compiled_checker_bundle(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    await corrupt_locked_policy_reads(monkeypatch, started_task["id"], "stale_bundle")

    await _reject_public_submission(task_client, started_task["id"], tmp_path, monkeypatch,
                                    ProjectLockedPolicyContextUnavailable)

    async with db_session.get_session_factory()() as session:
        submissions = (
            (
                await session.execute(
                    select(Submission).where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
    assert submissions == []
    assert checker_runs == []


async def test_submission_rejects_crossed_post_submit_policy_sidecar(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        locked_body = dict(task.locked_post_submit_checker_policy_body or {})
        post_submit_policy = await session.get(
            PostSubmitCheckerPolicy,
            task.locked_post_submit_checker_policy_id,
        )
        assert post_submit_policy is not None
        policy_id = post_submit_policy.id
        audit_ids = sorted(await session.scalars(select(AuditEvent.id)))
        await session.commit()

    from tests.projects.post_submit_fixtures import crossed_post_policy_read

    with crossed_post_policy_read(policy_id) as seen:
        await _reject_public_submission(task_client, started_task["id"], tmp_path, monkeypatch,
                                        ProjectLockedPolicyContextUnavailable)
    assert seen


    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        submissions = (
            (
                await session.execute(
                    select(Submission).where(Submission.task_id == started_task["id"])
                )
            )
            .scalars()
            .all()
        )
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
        assert sorted(await session.scalars(select(AuditEvent.id))) == audit_ids
    assert task is not None
    assert task.status == "in_progress"
    assert submissions == []
    assert task.locked_post_submit_checker_policy_body == locked_body

    assert checker_runs == []
