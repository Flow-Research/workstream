"""Real locked-policy rejection before hidden Submission persistence or ART access."""

from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from app.db import models as db_models
from app.db.errors import integrity_constraint_name
from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.modules.projects.models import (
    PostSubmitCheckerPolicy,
)
from app.modules.authorization.prepared import PreparedSubmissionCreationAuthorization
from app.modules.tasks.api import SubmissionCreationRequest
from app.modules.tasks.models import AuditEvent, Submission, TaskAssignment, WorkstreamTask
from app.modules.tasks.service import TaskLockedContextInvalid
from app.modules.tasks.submission_composition import TaskSubmissionCreationService
from tests.authorization.task_authority.test_concurrency import actor_context
from tests.projects.policy_read_faults import corrupt_locked_policy_reads
from tests.test_tasks import (
    task_database_env as task_database_env,
    task_client as task_client,
    create_active_project,
    create_started_task,
)


async def _create_hidden_submission(task_id: str):
    """Exercise real TASK/AUTH composition; invalid policy must precede ART lookup.

    The deliberately nonexistent admission cannot produce successful creation.
    If policy validation regresses, admission denial is a different failure and
    does not satisfy these tests' precise locked-policy error assertions.
    """
    async with db_session.get_session_factory()() as session:
        assignment = await session.scalar(select(TaskAssignment).where(
            TaskAssignment.task_id == task_id, TaskAssignment.status == "active",
        ))
        assert assignment is not None
        assignment_id = UUID(assignment.id)
        contributor_id = UUID(assignment.contributor_id)
    context = await actor_context(str(contributor_id))
    async with db_session.get_session_factory()() as session:
        command = compose_hidden_submission_creation_command(
            session, context, request_id=context.request_id, correlation_id=context.correlation_id,
        )
        return await command.create(SubmissionCreationRequest(
            task_id=UUID(task_id), assignment_id=assignment_id,
            contributor_id=contributor_id, admission_id=uuid4(),
            predecessor_submission_id=None, summary="Completed work",
            contributor_attestation="This submission is my work.",
        ))


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
        assignment = await session.scalar(select(TaskAssignment).where(
            TaskAssignment.task_id == task_response["id"],
            TaskAssignment.status == "active",
        ))
        assignment_id = UUID(assignment.id)
        contributor_id = UUID(assignment.contributor_id)
    context = await actor_context(str(contributor_id))
    admissions = AsyncMock()
    admissions.consume.side_effect = AssertionError("invalid policy reached ART")

    async with db_session.get_session_factory()() as session:
        expected_error = (
            TaskLockedContextInvalid
            if field.endswith("body") else IntegrityError
        )
        with pytest.raises(expected_error) as rejected:
            async with session.begin():
                task = await session.get(WorkstreamTask, task_response["id"])
                original = getattr(task, field)
                # Policy hashes have composite FK custody. Body corruption is
                # rejected by the complete TASK policy validator instead.
                setattr(task, field, {} if field.endswith("body") else "sha256:" + "f" * 64)
                await session.flush()
                await TaskSubmissionCreationService(
                    session,
                    authorization=PreparedSubmissionCreationAuthorization(session, context),
                    admissions=admissions,
                ).create(SubmissionCreationRequest(
                    task_id=UUID(task.id), assignment_id=assignment_id,
                    contributor_id=contributor_id, admission_id=uuid4(),
                    predecessor_submission_id=None, summary="Completed work",
                    contributor_attestation="This submission is my work.",
                ))
        if expected_error is IntegrityError:
            policy = "review" if "review" in field else "revision"
            assert integrity_constraint_name(rejected.value) == (
                f"fk_workstream_tasks_locked_{policy}_policy"
            )
        admissions.consume.assert_not_awaited()
        assert await session.scalar(select(Submission).where(
            Submission.task_id == task_response["id"],
        )) is None
        restored = await session.get(WorkstreamTask, task_response["id"])
        assert getattr(restored, field) == original
        assert restored.status == "in_progress"


async def test_submission_pre_submit_rejects_mutated_effective_policy_body(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    await corrupt_locked_policy_reads(monkeypatch, started_task["id"], "stale_effective")

    with pytest.raises(TaskLockedContextInvalid) as rejected:
        await _create_hidden_submission(started_task["id"])
    assert rejected.value.status_code == 422
    assert rejected.value.code == "task_locked_context_invalid"
    assert rejected.value.details["field"] == "locked_effective_project_submission_artifact_policy_hash"

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


async def test_submission_pre_submit_checker_setup_error_is_controlled(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    await corrupt_locked_policy_reads(monkeypatch, started_task["id"], "checker_names")

    with pytest.raises(TaskLockedContextInvalid) as rejected:
        await _create_hidden_submission(started_task["id"])
    assert rejected.value.status_code == 422
    assert rejected.value.code == "task_locked_context_invalid"
    assert rejected.value.details["field"] == "locked_pre_submit_checker_policy_id"

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
    assert submissions == []


async def test_submission_rejects_malformed_locked_post_submit_policy_body_without_side_effects(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
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
        task.locked_post_submit_checker_policy_body = corrupted_body
        await session.commit()

    with pytest.raises(TaskLockedContextInvalid) as rejected:
        await _create_hidden_submission(started_task["id"])
    assert rejected.value.status_code == 422
    assert rejected.value.code == "task_locked_context_invalid"
    assert rejected.value.details["field"] == "locked_post_submit_checker_policy_body"
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
    assert submissions == []
    assert runs == []
    assert results == []
    assert "submission_created" not in {event.event_type for event in audit_events}
    assert "submission_finalized" not in {event.event_type for event in audit_events}
    assert "checker_run_triggered" not in {event.event_type for event in audit_events}


async def test_submission_pre_submit_rejects_mutated_compiled_checker_bundle(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    await corrupt_locked_policy_reads(monkeypatch, started_task["id"], "stale_bundle")

    with pytest.raises(TaskLockedContextInvalid) as rejected:
        await _create_hidden_submission(started_task["id"])
    assert rejected.value.status_code == 422
    assert rejected.value.code == "task_locked_context_invalid"
    assert rejected.value.details["field"] == "locked_pre_submit_checker_bundle_hash"

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
    monkeypatch: pytest.MonkeyPatch,
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
        post_submit_policy.required_checkers = [
            *post_submit_policy.required_checkers,
            "check_acceptance_criteria_present",
        ]
        audit_ids = sorted(await session.scalars(select(AuditEvent.id)))
        await session.commit()

    with pytest.raises(TaskLockedContextInvalid) as rejected:
        await _create_hidden_submission(started_task["id"])
    assert rejected.value.status_code == 422
    assert rejected.value.code == "task_locked_context_invalid"
    assert rejected.value.details["field"] == "locked_post_submit_checker_policy_body"

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
    assert "check_acceptance_criteria_present" not in [
        entry["checker_id"]
        for entry in locked_body["entries"]
        if entry["classification"] == "project_required"
    ]
    assert "check_acceptance_criteria_present" not in [
        entry["checker_id"] for entry in locked_body["entries"]
    ]
    assert "check_required_files" in [
        entry["checker_id"]
        for entry in locked_body["entries"]
        if entry["classification"] == "platform_default"
    ]
    assert "check_required_files" in [entry["checker_id"] for entry in locked_body["entries"]]
    assert checker_runs == []
