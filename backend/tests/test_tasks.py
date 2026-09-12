from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Iterator
from contextlib import suppress
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID, uuid4

import pytest  # type: ignore[import-not-found]
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (  # type: ignore[import-not-found]
    AsyncSession,
)
from sqlalchemy.schema import CreateIndex

from projects.guide_fixtures import complete_guide_payload
from tests.projects.policy_read_faults import corrupt_locked_policy_reads
from auth_concurrency_support import wait_for_named_database_lock
from tests.submission_fixtures import seed_finalized_submission_for_checker_test

from app.adapters.auth.dev import actor_id_from_external_identity
from app.core.config import get_settings
from app.core.hashing import canonical_json_hash
from app.core.permissions import PermissionDenied
from app.db import models as db_models
from app.db import session as db_session
from app.db.base import Base
from app.db.errors import integrity_constraint_name
from app.main import create_app
from app.modules.actors.models import (
    ActorIdentityLink,
    ActorProfile,
    LegacyActorIdentity,
    LegacyWorkflowEligibility,
)
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    GuideSourceSnapshot,
    PaymentPolicy,
    PostSubmitCheckerPolicy,
    PreSubmitCheckerPolicy,
    ProjectGuide,
)
from app.modules.tasks.lifecycle import InvalidTaskTransition, ensure_allowed_transition
from app.modules.tasks.api import (
    SubmissionPredecessorFacts,
    TaskLockedProjectContextReferences,
    TaskSubmissionContextFacts,
    TaskSubmissionContextRequest,
    TaskSubmissionContextUnavailable,
)
from app.modules.tasks.models import (
    AuditEvent,
    EvidenceItem,
    Submission,
    TaskAssignment,
    WorkstreamTask,
)
from project_create_fixtures import (
    seed_active_guide_for_downstream_test,
    grant_system_project_manager,
)
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.submission_composition import build_submission
from app.modules.tasks.schemas import TaskCreate
from app.modules.tasks.service import (
    TaskLockedContextInvalid,
    TaskService,
    TaskServiceError,
    TaskTransitionBlocked,
)
from app.schemas.auth import ActorContext


def _locked_task_context_references() -> TaskLockedProjectContextReferences:
    """Build complete immutable locked references for focused unit tests."""
    return TaskLockedProjectContextReferences(
        project_id=uuid4(),
        guide_version="v1",
        source_snapshot_id=uuid4(),
        source_snapshot_hash="sha256:" + "1" * 64,
        effective_policy_id=uuid4(),
        effective_policy_hash="sha256:" + "2" * 64,
        pre_submit_policy_id=uuid4(),
        pre_submit_policy_bundle_hash="sha256:" + "3" * 64,
    )


def test_task_submission_context_public_facts_are_immutable_and_consistent() -> None:
    """Reject mutation, invalid failures, and inconsistent lifecycle facts."""
    predecessor = SubmissionPredecessorFacts(submission_id=uuid4(), version=2)
    facts = TaskSubmissionContextFacts(
        task_id=uuid4(),
        assignment_id=uuid4(),
        contributor_id=uuid4(),
        status="needs_revision",
        kind="revision",
        predecessor=predecessor,
        locked_project_context=_locked_task_context_references(),
    )

    assert facts.predecessor is predecessor
    failure = TaskSubmissionContextUnavailable("task_submission_context_invalid")
    assert failure.code == "task_submission_context_invalid"
    with pytest.raises(ValueError, match="failure code is invalid"):
        TaskSubmissionContextUnavailable(cast(Any, "unbounded_failure"))
    with pytest.raises(FrozenInstanceError):
        facts.status = "in_progress"  # type: ignore[misc]
    with pytest.raises(ValueError, match="version is invalid"):
        SubmissionPredecessorFacts(submission_id=uuid4(), version=0)
    with pytest.raises(ValueError, match="reference is empty"):
        TaskLockedProjectContextReferences(
            project_id=uuid4(),
            guide_version=" ",
            source_snapshot_id=uuid4(),
            source_snapshot_hash="sha256:" + "1" * 64,
            effective_policy_id=uuid4(),
            effective_policy_hash="sha256:" + "2" * 64,
            pre_submit_policy_id=uuid4(),
            pre_submit_policy_bundle_hash="sha256:" + "3" * 64,
        )
    with pytest.raises(ValueError, match="predecessor is inconsistent"):
        TaskSubmissionContextFacts(
            task_id=uuid4(),
            assignment_id=uuid4(),
            contributor_id=uuid4(),
            status="in_progress",
            kind="initial",
            predecessor=predecessor,
            locked_project_context=_locked_task_context_references(),
        )
    with pytest.raises(ValueError, match="predecessor is inconsistent"):
        TaskSubmissionContextFacts(
            task_id=uuid4(),
            assignment_id=uuid4(),
            contributor_id=uuid4(),
            status="needs_revision",
            kind="initial",
            predecessor=None,
            locked_project_context=_locked_task_context_references(),
        )


@pytest.mark.asyncio
async def test_task_repository_locks_initial_and_revision_submission_context() -> None:
    """Project exact initial and revision facts through the owner-local port."""
    contributor_id = uuid4()
    task_id = uuid4()
    assignment_id = uuid4()
    predecessor_id = uuid4()
    references = _locked_task_context_references()
    task = MagicMock(
        project_id=str(references.project_id),
        assigned_to=str(contributor_id),
        status="in_progress",
        locked_guide_version=references.guide_version,
        locked_guide_source_snapshot_id=str(references.source_snapshot_id),
        locked_guide_source_snapshot_hash=references.source_snapshot_hash,
        locked_effective_project_submission_artifact_policy_id=str(references.effective_policy_id),
        locked_effective_project_submission_artifact_policy_hash=(references.effective_policy_hash),
        locked_pre_submit_checker_policy_id=str(references.pre_submit_policy_id),
        locked_pre_submit_checker_bundle_hash=references.pre_submit_policy_bundle_hash,
    )
    assignment = MagicMock(
        task_id=str(task_id),
        contributor_id=str(contributor_id),
        status="active",
    )
    session = MagicMock()
    session.scalar = AsyncMock(side_effect=[assignment, assignment])
    repository = TaskRepository(session)
    repository.get_task = AsyncMock(return_value=task)
    repository.get_latest_submission_for_task = AsyncMock(
        side_effect=[
            None,
            MagicMock(
                id=str(predecessor_id),
                version=1,
                contributor_id=str(contributor_id),
            ),
        ]
    )

    initial = await repository.lock_submission_context(
        TaskSubmissionContextRequest(
            task_id=task_id,
            assignment_id=assignment_id,
            contributor_id=contributor_id,
            predecessor_submission_id=None,
        )
    )
    assert initial == TaskSubmissionContextFacts(
        task_id=task_id,
        assignment_id=assignment_id,
        contributor_id=contributor_id,
        status="in_progress",
        kind="initial",
        predecessor=None,
        locked_project_context=references,
    )
    task.status = "needs_revision"
    revision = await repository.lock_submission_context(
        TaskSubmissionContextRequest(
            task_id=task_id,
            assignment_id=assignment_id,
            contributor_id=contributor_id,
            predecessor_submission_id=predecessor_id,
        )
    )
    assert revision == TaskSubmissionContextFacts(
        task_id=task_id,
        assignment_id=assignment_id,
        contributor_id=contributor_id,
        status="needs_revision",
        kind="revision",
        predecessor=SubmissionPredecessorFacts(
            submission_id=predecessor_id,
            version=1,
        ),
        locked_project_context=references,
    )
    assert repository.get_task.await_args_list == [
        call(str(task_id), for_update=True),
        call(str(task_id), for_update=True),
    ]
    assert repository.get_latest_submission_for_task.await_args_list == [
        call(str(task_id), for_update=True, populate_existing=True),
        call(str(task_id), for_update=True, populate_existing=True),
    ]
    assignment_statements = [args.args[0] for args in session.scalar.await_args_list]
    assert len(assignment_statements) == 2
    assert all("FOR UPDATE" in str(statement) for statement in assignment_statements)
    assert all(
        statement.get_execution_options().get("populate_existing") is True
        for statement in assignment_statements
    )


@pytest.mark.asyncio
async def test_task_repository_rejects_stale_submission_predecessor() -> None:
    """Reject a predecessor selector that is no longer the latest Submission."""
    task_id = uuid4()
    contributor_id = uuid4()
    assignment_id = uuid4()
    task = MagicMock(assigned_to=str(contributor_id), status="in_progress")
    assignment = MagicMock(
        task_id=str(task_id), contributor_id=str(contributor_id), status="active"
    )
    session = MagicMock()
    session.scalar = AsyncMock(return_value=assignment)
    repository = TaskRepository(session)
    repository.get_task = AsyncMock(return_value=task)
    repository.get_latest_submission_for_task = AsyncMock(
        return_value=MagicMock(id=str(uuid4()), version=1, contributor_id=str(contributor_id))
    )

    with pytest.raises(
        TaskSubmissionContextUnavailable,
        match="task_submission_predecessor_changed",
    ):
        await repository.lock_submission_context(
            TaskSubmissionContextRequest(
                task_id=task_id,
                assignment_id=assignment_id,
                contributor_id=contributor_id,
                predecessor_submission_id=uuid4(),
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("cross_contributor", (False, True))
async def test_task_repository_rejects_invalid_revision_lineage(
    cross_contributor: bool,
) -> None:
    """Reject crossed lifecycle state and cross-contributor predecessors."""
    task_id = uuid4()
    contributor_id = uuid4()
    assignment_id = uuid4()
    predecessor_id = uuid4()
    task = MagicMock(assigned_to=str(contributor_id), status="in_progress")
    assignment = MagicMock(
        task_id=str(task_id), contributor_id=str(contributor_id), status="active"
    )
    predecessor = MagicMock(
        id=str(predecessor_id),
        version=1,
        contributor_id=str(uuid4()) if cross_contributor else str(contributor_id),
    )
    session = MagicMock()
    session.scalar = AsyncMock(return_value=assignment)
    repository = TaskRepository(session)
    repository.get_task = AsyncMock(return_value=task)
    repository.get_latest_submission_for_task = AsyncMock(return_value=predecessor)
    if cross_contributor:
        task.status = "needs_revision"

    with pytest.raises(
        TaskSubmissionContextUnavailable,
        match="task_submission_context_invalid",
    ):
        await repository.lock_submission_context(
            TaskSubmissionContextRequest(
                task_id=task_id,
                assignment_id=assignment_id,
                contributor_id=contributor_id,
                predecessor_submission_id=predecessor_id,
            )
        )


async def test_task_repository_delegates_audit_persistence() -> None:
    """Keep legacy task audit methods as same-session shared-writer adapters."""
    session = MagicMock()
    repository = TaskRepository(session)
    event = MagicMock(spec=AuditEvent)
    persisted = MagicMock(spec=AuditEvent)
    listed = [persisted]
    repository._audit_repository.add_audit_event = AsyncMock(return_value=persisted)
    repository._audit_repository.list_audit_events = AsyncMock(return_value=listed)

    assert repository._audit_repository._session is session
    assert await repository.add_audit_event(event) is persisted
    assert await repository.list_audit_events("task", "task-1") is listed
    repository._audit_repository.add_audit_event.assert_awaited_once_with(event)
    repository._audit_repository.list_audit_events.assert_awaited_once_with("task", "task-1")




def task_service_actor(*roles: str) -> ActorContext:
    """Build a verified actor for direct task-service behavior tests."""
    return ActorContext(
        actor_id=actor_id("task-service-actor"),
        external_subject="task-service-actor",
        external_issuer="flow-test",
        roles=roles,
        claim_snapshot={},
        auth_source="dev_mock",
        is_dev_auth=True,
    )


async def test_task_service_create_persists_canonical_attribution_and_audit() -> None:
    actor = task_service_actor("project_manager")
    session = MagicMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    service = TaskService(session)
    service._project_repo.get_project = AsyncMock(return_value=MagicMock())
    service._repo.add_task = AsyncMock(side_effect=lambda task: task)
    service._write_task_audit = AsyncMock()
    response = MagicMock(name="task_response")
    service._task_response = MagicMock(return_value=response)
    payload = TaskCreate.model_validate(complete_task_payload())

    result = await service.create_task(actor, "project-1", payload)

    assert service._repo.add_task.await_args is not None
    task = service._repo.add_task.await_args.args[0]
    assert result is response
    assert isinstance(task, WorkstreamTask)
    assert task.project_id == "project-1"
    assert task.created_by == actor.actor_id
    assert task.status == "draft"
    assert task.title == payload.title
    service._write_task_audit.assert_awaited_once_with(
        actor,
        task,
        event_type="task_created",
        from_status=None,
        to_status="draft",
        reason=None,
        event_payload={"source_type": payload.source_type},
    )
    session.commit.assert_awaited_once_with()
    session.refresh.assert_awaited_once_with(task)
    service._task_response.assert_called_once_with(actor, task)


async def test_task_service_read_contexts_preserve_visibility_and_operator_scope() -> None:
    actor = task_service_actor("project_manager")
    session = MagicMock(spec=AsyncSession)
    service = TaskService(session)
    task = MagicMock(spec=WorkstreamTask)
    task.id = "task-1"
    task.created_by = actor.actor_id
    context = MagicMock(name="locked_context")
    task_response = MagicMock(name="task_response")
    requirements_response = MagicMock(name="requirements_response")
    locked_response = MagicMock(name="locked_response")
    service._get_task = AsyncMock(return_value=task)
    service._ensure_task_visible = AsyncMock()
    service._load_locked_task_context = AsyncMock(return_value=context)
    service._task_response = MagicMock(return_value=task_response)
    service._submission_requirements_response = MagicMock(return_value=requirements_response)
    service._locked_context_response = MagicMock(return_value=locked_response)

    assert await service.get_task(actor, task.id) is task_response
    assert await service.get_task_submission_requirements(actor, task.id) is requirements_response
    assert await service.get_task_locked_context(actor, task.id) is locked_response

    assert service._get_task.await_count == 3
    assert service._ensure_task_visible.await_count == 2
    assert service._load_locked_task_context.await_count == 2
    service._submission_requirements_response.assert_called_once_with(task, context)
    service._locked_context_response.assert_called_once_with(task, context)


async def test_task_service_screen_and_release_own_transaction_boundaries() -> None:
    actor = task_service_actor("project_manager")
    session = MagicMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    service = TaskService(session)
    draft_task = MagicMock(spec=WorkstreamTask)
    draft_task.id = "task-1"
    draft_task.project_id = "project-1"
    draft_task.status = "draft"
    screened_task = MagicMock(spec=WorkstreamTask)
    screened_task.id = draft_task.id
    screened_task.project_id = draft_task.project_id
    screened_task.status = "screening"
    active_context = tuple(MagicMock(name=f"policy_{index}") for index in range(8))
    screen_response = MagicMock(name="screen_response")
    release_response = MagicMock(name="release_response")
    service._get_task = AsyncMock(side_effect=(draft_task, screened_task))
    service._ensure_transition_allowed = MagicMock()
    service._load_active_policy_context = AsyncMock(return_value=active_context)
    service._validate_task_contract_fields = MagicMock()
    service._stamp_locked_context = MagicMock()
    service._change_task_status = AsyncMock()
    service._ensure_locked_context = MagicMock()
    service._load_locked_task_context = AsyncMock(return_value=MagicMock())
    service._task_response = MagicMock(side_effect=(screen_response, release_response))

    assert (
        await service.move_to_screening(actor, draft_task.id, "screening complete")
        is screen_response
    )
    assert (
        await service.release_to_ready(actor, screened_task.id, "release approved")
        is release_response
    )

    service._stamp_locked_context.assert_called_once_with(draft_task, *active_context)
    assert service._change_task_status.await_args_list[0].args == (
        actor,
        draft_task,
        "screening",
        "screening complete",
    )
    assert service._change_task_status.await_args_list[1].args == (
        actor,
        screened_task,
        "ready",
        "release approved",
    )
    service._ensure_locked_context.assert_called_once_with(screened_task)
    service._load_locked_task_context.assert_awaited_once_with(screened_task)
    assert session.commit.await_count == 2
    assert session.refresh.await_args_list[0].args == (draft_task,)
    assert session.refresh.await_args_list[1].args == (screened_task,)




async def test_task_service_finalize_requeues_locked_latest_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = task_service_actor("project_manager")
    session = MagicMock(spec=AsyncSession)
    service = TaskService(session)
    task = MagicMock(spec=WorkstreamTask)
    task.id = "task-1"
    task.created_by = actor.actor_id
    submission = MagicMock(spec=Submission)
    submission.id = "submission-1"
    submission.task_id = task.id
    submission.status = "submitted"
    submission.locked_at = datetime.now(UTC)
    persisted = MagicMock(spec=Submission)
    repair_snapshot = {"status": "failed", "repairable": True}
    requester_provenance = {"request_id": "request-1", "correlation_id": "correlation-1"}
    checker_service = MagicMock()
    checker_service.pre_review_gate_repair_snapshot = AsyncMock(return_value=repair_snapshot)
    monkeypatch.setattr(
        "app.modules.tasks.service.CheckerService",
        MagicMock(return_value=checker_service),
    )
    response = MagicMock(name="submission_response")
    service._get_submission = AsyncMock(return_value=submission)
    service._get_task = AsyncMock(return_value=task)
    service._ensure_submission_finalize_authorized = AsyncMock()
    service._repo.get_latest_submission_for_task = AsyncMock(return_value=submission)
    service._submission_finalization_requester_provenance = AsyncMock(
        return_value=requester_provenance
    )
    service._enqueue_pre_review_gate_after_commit = AsyncMock(return_value="queue-task-1")
    service._repo.get_submission = AsyncMock(return_value=persisted)
    service._submission_response = MagicMock(return_value=response)

    result = await service.finalize_submission(actor, submission.id)

    assert result is response
    service._ensure_submission_finalize_authorized.assert_awaited_once_with(actor, task)
    checker_service.pre_review_gate_repair_snapshot.assert_awaited_once_with(submission.id)
    service._submission_finalization_requester_provenance.assert_awaited_once_with(
        task,
        submission,
    )
    service._enqueue_pre_review_gate_after_commit.assert_awaited_once_with(
        actor,
        submission.id,
        requester_provenance=requester_provenance,
        repair_snapshot=repair_snapshot,
    )
    service._submission_response.assert_called_once_with(
        actor,
        persisted,
        has_operator_access=True,
    )


@pytest.mark.parametrize("task_status", ["submitted", "in_progress"])
async def test_task_service_dispatch_failure_records_bounded_repair_evidence(
    monkeypatch: pytest.MonkeyPatch,
    task_status: str,
) -> None:
    session = MagicMock(spec=AsyncSession)
    session.commit = AsyncMock()
    service = TaskService(session)
    submission = MagicMock(spec=Submission)
    submission.id = "submission-1"
    submission.task_id = "task-1"
    submission.version = 3
    task = MagicMock(spec=WorkstreamTask)
    task.id = submission.task_id
    task.status = task_status
    system_actor = task_service_actor("admin")
    monkeypatch.setattr(
        "app.modules.tasks.service.pre_review_gate_system_actor",
        MagicMock(return_value=system_actor),
    )
    service._get_submission = AsyncMock(return_value=submission)
    service._get_task = AsyncMock(return_value=task)
    service._change_task_status = AsyncMock()
    service._write_task_audit = AsyncMock()
    requester_payload = {"request_id": "request-1", "correlation_id": "correlation-1"}

    await service._mark_pre_review_gate_dispatch_failed(
        submission.id,
        "checker-run-1",
        "x" * 1200,
        requester_payload,
    )

    expected_payload = {
        "submission_id": submission.id,
        "submission_version": submission.version,
        "checker_run_id": "checker-run-1",
        "failure_code": "pre_review_gate_enqueue_failed",
        "failure_message": "x" * 1000,
        **requester_payload,
    }
    if task_status == "submitted":
        service._change_task_status.assert_awaited_once_with(
            system_actor,
            task,
            "evaluation_pending",
            reason="automatic pre-review gate dispatch failed; operator repair required",
            event_payload=expected_payload,
            event_type="pre_review_gate_dispatch_failed",
        )
        service._write_task_audit.assert_not_awaited()
    else:
        service._write_task_audit.assert_awaited_once_with(
            system_actor,
            task,
            event_type="pre_review_gate_dispatch_failed",
            from_status=task.status,
            to_status=task.status,
            reason="automatic pre-review gate dispatch failed; operator repair required",
            event_payload=expected_payload,
        )
        service._change_task_status.assert_not_awaited()
    session.commit.assert_awaited_once_with()


async def test_task_service_finalization_provenance_fails_closed_without_lock_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=AsyncSession)
    service = TaskService(session)
    task = MagicMock(spec=WorkstreamTask)
    task.id = "task-1"
    submission = MagicMock(spec=Submission)
    submission.id = "submission-1"
    events = [MagicMock(spec=AuditEvent)]
    service._repo.list_audit_events = AsyncMock(return_value=events)
    provenance = {"request_id": "request-1", "correlation_id": "correlation-1"}
    finder = MagicMock(side_effect=(provenance, None))
    monkeypatch.setattr(
        "app.modules.tasks.service.find_submission_requester_provenance",
        finder,
    )

    assert (
        await service._submission_finalization_requester_provenance(task, submission) == provenance
    )
    with pytest.raises(
        TaskTransitionBlocked,
        match="submission lock audit provenance is missing",
    ):
        await service._submission_finalization_requester_provenance(task, submission)

    assert service._repo.list_audit_events.await_count == 2
    assert finder.call_count == 2


async def test_task_service_submission_lock_conflict_recovers_only_persisted_lock() -> None:
    actor = task_service_actor("project_manager")
    session = MagicMock(spec=AsyncSession)
    service = TaskService(session)
    task = MagicMock(spec=WorkstreamTask)
    task.status = "submitted"
    submission = MagicMock(spec=Submission)
    submission.id = "submission-1"
    submission.locked_at = None
    persisted = MagicMock(spec=Submission)
    persisted.locked_at = datetime.now(UTC)
    service._repo.finalize_submission_if_unlocked = AsyncMock(return_value=False)
    service._repo.get_submission = AsyncMock(side_effect=(persisted, None))
    service._repo.lock_submission_evidence = AsyncMock()
    service._write_task_audit = AsyncMock()

    await service._finalize_submission_for_evaluation(actor, task, submission)

    assert submission.locked_at == persisted.locked_at
    service._repo.lock_submission_evidence.assert_not_awaited()
    service._write_task_audit.assert_not_awaited()

    submission.locked_at = None
    with pytest.raises(TaskTransitionBlocked, match="submission lock conflicted; retry"):
        await service._finalize_submission_for_evaluation(actor, task, submission)


@pytest.mark.parametrize(
    ("method_name", "args", "expected_field"),
    [
        ("_policy_list", ({"items": "not-a-list"}, "items"), "effective_policy.items"),
        ("_policy_string_list", ({"items": [1]}, "items"), "effective_policy.items"),
        ("_policy_bool", ({"flag": "true"}, "flag"), "effective_policy.flag"),
        ("_policy_object", ({"rules": []}, "rules"), "effective_policy.rules"),
        ("_optional_policy_text", ({"note": ""}, "note"), "effective_policy.note"),
        ("_optional_policy_non_negative_int", ({"limit": -1}, "limit"), "effective_policy.limit"),
        (
            "_required_packet_fields",
            ({"required_packet_fields": "summary"},),
            "effective_policy.required_packet_fields",
        ),
        (
            "_required_packet_fields",
            ({"required_packet_fields": [""]},),
            "effective_policy.required_packet_fields",
        ),
        ("_policy_rule_text", ([], "path", "files"), "effective_policy.files"),
        (
            "_policy_rule_text",
            ({}, "path", "files"),
            "effective_policy.files.path",
        ),
        ("_optional_policy_rule_text", ([], "note", "files"), "effective_policy.files"),
        (
            "_optional_policy_rule_text",
            ({"note": ""}, "note", "files"),
            "effective_policy.files.note",
        ),
        ("_policy_rule_bool", ([], "required", "files"), "effective_policy.files"),
        (
            "_policy_rule_bool",
            ({"required": "true"}, "required", "files"),
            "effective_policy.files.required",
        ),
    ],
)
def test_task_service_locked_policy_helpers_fail_closed_on_wrong_types(
    method_name: str,
    args: tuple[object, ...],
    expected_field: str,
) -> None:
    service = TaskService(MagicMock(spec=AsyncSession))

    with pytest.raises(TaskLockedContextInvalid) as failure:
        getattr(service, method_name)(*args)

    assert failure.value.details == {"field": expected_field}


def test_task_service_optional_locked_policy_helpers_preserve_absence() -> None:
    service = TaskService(MagicMock(spec=AsyncSession))

    assert service._optional_policy_text({}, "note") is None
    assert service._optional_policy_non_negative_int({}, "limit") is None


async def delete_audit_fixture_as_owner(session: AsyncSession, event_id: str) -> None:
    """Construct missing-evidence corruption under explicit test-owner custody."""
    await session.execute(text("lock table audit_events in access exclusive mode"))
    await session.execute(
        text("alter table audit_events disable trigger audit_events_reject_update_delete")
    )
    await session.execute(
        text("delete from audit_events where id = :event_id"),
        {"event_id": event_id},
    )
    await session.execute(
        text("alter table audit_events enable trigger audit_events_reject_update_delete")
    )
    await session.commit()


@pytest.fixture
def task_database_env(
    monkeypatch: pytest.MonkeyPatch,
    clean_postgres_database: str,
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    monkeypatch.setenv(
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET",
        "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
    )
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    get_settings.cache_clear()
    try:
        yield clean_postgres_database
    finally:
        get_settings.cache_clear()


@pytest.fixture
async def task_client(task_database_env: str) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        admission = await client.get("/api/v1/actors/me", headers=auth_headers())
        assert admission.status_code == 200, admission.text
        async with db_session.get_session_factory()() as session:
            await grant_system_project_manager(
                session,
                issuer="flow-test",
                subject="project-manager-subject",
            )
            await session.commit()
        yield client


def alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    return config


def auth_headers(token: str = "task-token") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": str(uuid4()),
    }


_DEFAULT_DEV_ACTOR_FIELD = object()


def set_dev_actor(
    monkeypatch: pytest.MonkeyPatch,
    *,
    roles: str,
    subject: str,
    token: str = "task-token",
    issuer: str = "flow-test",
    email: str | None | object = _DEFAULT_DEV_ACTOR_FIELD,
    display_name: str | None | object = _DEFAULT_DEV_ACTOR_FIELD,
) -> None:
    monkeypatch.setenv("WORKSTREAM_AUTH_PROVIDER", "dev")
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "test")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_TOKEN", token)
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", subject)
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ISSUER", issuer)
    if email is _DEFAULT_DEV_ACTOR_FIELD:
        monkeypatch.setenv("WORKSTREAM_DEV_AUTH_EMAIL", f"{subject}@example.test")
    elif email is None:
        monkeypatch.delenv("WORKSTREAM_DEV_AUTH_EMAIL", raising=False)
    else:
        monkeypatch.setenv("WORKSTREAM_DEV_AUTH_EMAIL", email)
    if display_name is _DEFAULT_DEV_ACTOR_FIELD:
        monkeypatch.setenv("WORKSTREAM_DEV_AUTH_DISPLAY_NAME", subject.replace("-", " ").title())
    elif display_name is None:
        monkeypatch.delenv("WORKSTREAM_DEV_AUTH_DISPLAY_NAME", raising=False)
    else:
        monkeypatch.setenv("WORKSTREAM_DEV_AUTH_DISPLAY_NAME", display_name)
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", roles)
    get_settings.cache_clear()


def actor_id(subject: str, issuer: str = "flow-test") -> str:
    return actor_id_from_external_identity(issuer, subject)




def sha256_hash(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


async def load_pre_submit_checker_policy(effective_policy: dict) -> dict:
    """Load the project pre-submit checker policy compiled during approval."""
    async with db_session.get_session_factory()() as session:
        pre_submit_checker_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == effective_policy["id"]
            )
        )
        assert pre_submit_checker_policy is not None
        assert pre_submit_checker_policy.lifecycle_status == "compiled"
        return {
            "id": pre_submit_checker_policy.id,
            "effective_policy_id": pre_submit_checker_policy.effective_policy_id,
            "effective_policy_hash": pre_submit_checker_policy.effective_policy_hash,
            "compiled_bundle": pre_submit_checker_policy.compiled_bundle,
            "compiled_bundle_hash": pre_submit_checker_policy.compiled_bundle_hash,
        }


async def load_post_submit_checker_policy(project_id: str, guide_version: str = "v1") -> dict:
    """Load the project post-submit checker policy attached to a guide version."""
    async with db_session.get_session_factory()() as session:
        policy = await session.scalar(
            select(PostSubmitCheckerPolicy).where(
                PostSubmitCheckerPolicy.project_id == project_id,
                PostSubmitCheckerPolicy.guide_version == guide_version,
            )
        )
        assert policy is not None
        assert policy.policy_hash is not None
        assert policy.policy_body is not None
        return {
            "id": policy.id,
            "guide_version": policy.guide_version,
            "policy_hash": policy.policy_hash,
            "policy_body": policy.policy_body,
        }


def task_artifact_proposal():
    from app.interfaces.project_agents import SubmissionArtifactPolicyProposal

    return SubmissionArtifactPolicyProposal(
        maximum_file_size_bytes=1_000_000,
        maximum_package_size_bytes=5_000_000,
        required_artifacts=("answer.md",),
        required_evidence=("checker_log",),
        attestation_terms=("task_test_originality",),
    )


async def create_policy_bundle_for_guide(
    client: AsyncClient,
    project_id: str,
    guide_id: str,
    artifact_proposal=None,
    *,
    post_submit_required_checkers: list[str] | None = None,
    post_submit_warning_checkers: list[str] | None = None,
    post_submit_blocking_severities: list[str] | None = None,
) -> dict:
    for kind, body in (
        (
            "review",
            {
                "review_preference_window_seconds": 3600,
                "review_lease_duration_seconds": 1800,
                "max_active_review_leases_per_reviewer": 1,
                "self_review_allowed": False,
                "reject_policy": "close_task",
                "finding_evidence_requirement": "optional",
                "requires_second_review": False,
                "allowed_decisions": ["accept", "needs_revision", "reject"],
                "minimum_finding_fields": ["issue", "required_fix"],
            },
        ),
        (
            "revision",
            {
                "max_revision_rounds": 7,
                "revision_deadline_hours": 48,
                "allowed_resubmission_states": ["needs_revision"],
                "reviewer_reassignment_rule": "same reviewer preferred",
            },
        ),
    ):
        response = await client.put(
            f"/api/v1/projects/{project_id}/guides/{guide_id}/{kind}-policy",
            headers=auth_headers() | {"If-Match": '"no-current-policy"'},
            json=body,
        )
        assert response.status_code == 200, response.text
    async with db_session.get_session_factory()() as session:
        guide = await session.get(ProjectGuide, guide_id)
        assert guide is not None
        session.add_all(
            [
                PaymentPolicy(
                    id=str(uuid4()),
                    project_id=project_id,
                    guide_version=guide.version,
                    base_amount="25.00",
                    currency="USD",
                    payout_type="fixed",
                    revision_payment_rule="none",
                    rejection_payment_rule="none",
                    accepted_payment_rule="pay base amount",
                ),
            ]
        )
        await session.flush()
        await session.commit()

    from projects.policy_bundle_fixtures import create_approved_policy_bundle
    from project_create_fixtures import grant_fixture_admin_role
    async with db_session.get_session_factory()() as session, session.begin():
        link = await session.scalar(select(ActorIdentityLink).where(
            ActorIdentityLink.issuer == "flow-test", ActorIdentityLink.subject == "project-manager-subject",
        ))
        assert link is not None
        await grant_fixture_admin_role(session, link.actor_profile_id, project_id=project_id)

    return await create_approved_policy_bundle(
        client, project_id, guide_id,
        artifact_proposal=artifact_proposal or task_artifact_proposal(),
        request_headers=auth_headers(),
        post_submit_required_checkers=post_submit_required_checkers,
        post_submit_warning_checkers=post_submit_warning_checkers,
        post_submit_blocking_severities=post_submit_blocking_severities,
    )


def complete_task_payload() -> dict:
    return {
        "title": "Evaluate proof",
        "description": "Check whether the proof satisfies the guide.",
        "task_type": "evaluation",
        "difficulty": "medium",
        "skill_tags": ["stem", "proofs"],
        "estimated_time_minutes": 45,
        "source_type": "manual",
        "source_ref": "local-ticket-1",
        "source_payload_hash": "hash-123",
        "acceptance_criteria": "Proof is correct and evidence is present.",
        "rejection_criteria": "Proof is unsupported.",
    }


def complete_submission_payload(package_hash: str = "sha256:package-v1") -> dict:
    return {
        "summary": "Completed the proof evaluation.",
        "package_uri": "local://submissions/proof-evaluation-v1.zip",
        "package_hash": package_hash,
        "artifact_hash_manifest": [
            {
                "artifact": "answer.md",
                "hash": "sha256:answer-v1",
                "size_bytes": 128,
                "notes": "main answer",
            }
        ],
        "worker_attestation": (
            "I attest this is original work with task test originality and contains no confidential client data, "
            "credentials, secrets, tokens, passwords, API keys, private source material, "
            "source code, copied platform artifacts, or copied platform content. I confirm credentials "
            "and secret exclusion and accept human accountability for agent assisted work."
        ),
        "evidence_items": [
            {
                "type": "log",
                "label": "checker dry run",
                "uri": "local://evidence/checker.log",
                "hash": "sha256:log-v1",
                "size_bytes": 256,
                "metadata": {"command": "pytest", "policy_key": "required-evidence-001"},
            }
        ],
    }


async def create_active_project(client: AsyncClient) -> dict:
    project_response = await client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json={
            "name": "Task Queue Project",
            "slug": "task-queue-project",
            "description": "Project for task queue tests",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()

    guide_response = await client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=complete_guide_payload(),
    )
    assert guide_response.status_code == 201, guide_response.text
    guide = guide_response.json()
    await create_policy_bundle_for_guide(client, project["id"], guide["id"])

    await seed_active_guide_for_downstream_test(
        db_session.get_session_factory(),
        project_id=project["id"],
        guide_id=guide["id"],
    )
    return project


async def create_draft_task(
    client: AsyncClient, project_id: str, payload: dict | None = None
) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers=auth_headers(),
        json=payload or complete_task_payload(),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_ready_task(
    client: AsyncClient,
    project_id: str,
    payload: dict | None = None,
) -> dict:
    task = await create_draft_task(client, project_id, payload)
    screen = await client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screening checklist passed"},
    )
    assert screen.status_code == 200, screen.text
    release = await client.post(
        f"/api/v1/tasks/{task['id']}/release",
        headers=auth_headers(),
        json={"reason": "release decision recorded"},
    )
    assert release.status_code == 200, release.text
    return release.json()


async def create_started_task(
    client: AsyncClient,
    project_id: str,
    monkeypatch: pytest.MonkeyPatch,
    subject: str = "worker-one",
    payload: dict | None = None,
) -> dict:
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    ready_task = await create_ready_task(client, project_id, payload)
    await admit_and_grant_project_submitter(client, monkeypatch, project_id, subject)
    claim = await client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "claim"},
    )
    assert claim.status_code == 200, claim.text
    start = await client.post(
        f"/api/v1/tasks/{ready_task['id']}/start",
        headers=auth_headers(),
        json={"reason": "start"},
    )
    assert start.status_code == 200, start.text
    # Claim/start above prove grant-only authority. Downstream retained
    # checker/detail routes still expect this token role until their cutover.
    set_dev_actor(monkeypatch, roles="worker", subject=subject)
    return start.json()


async def admit_and_grant_project_submitter(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, project_id: str, subject: str,
) -> dict:
    """Give a role-free contributor explicit authority for exactly one project."""
    set_dev_actor(monkeypatch, roles="viewer", subject=subject)
    admitted = await client.get("/api/v1/actors/me", headers=auth_headers())
    assert admitted.status_code == 200, admitted.text
    actor_profile_id = admitted.json()["actor_profile_id"]
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    response = await client.post(
        f"/api/v1/projects/{project_id}/role-grants",
        headers=auth_headers(),
        json={
            "target_actor_profile_id": actor_profile_id,
            "role": "submitter",
            "qualification": {
                "skills_snapshot": {"availability": "unavailable", "reference_ids": [], "unavailable_reason": "no_record"},
                "reputation_snapshot": {"availability": "unavailable", "reference_ids": [], "unavailable_reason": "no_record"},
                "prior_project_work_refs": [], "external_expertise_refs": [],
            },
            "reason": "Explicit project assignment for task behavior tests",
        },
    )
    assert response.status_code == 201, response.text
    set_dev_actor(monkeypatch, roles="viewer", subject=subject)
    return {"actor_profile_id": actor_profile_id, "grant_id": response.json()["id"]}


def expected_worker_requester_provenance(subject: str = "worker-one") -> dict[str, str]:
    """Return the queue-safe requester provenance for a seeded worker actor."""
    return {
        "requester_actor_id": actor_id(subject),
        "requester_external_subject": subject,
        "requester_external_issuer": "flow-test",
        "requester_auth_source": "dev_mock",
    }


def hold_pre_review_enqueue(*, checker_run_id: str, requester_provenance: dict) -> str:
    """Hold a pre-review gate enqueue while preserving the production call shape."""
    return f"held:{checker_run_id}"


async def seed_task_test_actor(subject: str, *, stored_role: str = "worker") -> str:
    """Seed identity facts for row/read tests; never seed eligibility or a grant."""
    worker_actor_id = actor_id(subject)
    async with db_session.get_session_factory()() as session:
        session.add_all(
            [
                ActorProfile(
                    id=worker_actor_id,
                    actor_kind="human",
                    status="active",
                    provisioning_method="automatic_first_access",
                    created_by=worker_actor_id,
                ),
                ActorIdentityLink(
                    id=str(uuid4()),
                    actor_profile_id=worker_actor_id,
                    issuer="flow-test",
                    subject=subject,
                    subject_kind="human",
                    status="active",
                    linked_by=worker_actor_id,
                    last_verified_at=datetime.now(UTC),
                ),
                LegacyActorIdentity(
                    actor_id=worker_actor_id,
                    external_subject=subject,
                    external_issuer="flow-test",
                    display_name=subject.replace("-", " ").title(),
                    email=f"{subject}@example.test",
                    last_seen_roles=[stored_role],
                    last_claim_snapshot={"seeded_for_task_test": True},
                    auth_source="dev_mock",
                    is_dev_auth=True,
                ),

            ]
        )
        await session.commit()
    return worker_actor_id


async def _submission_context_request_for_started_task(
    task_id: str,
    contributor_id: str,
    *,
    predecessor_submission_id: str | None = None,
) -> TaskSubmissionContextRequest:
    """Build a request from the canonical active assignment in PostgreSQL."""
    async with db_session.get_session_factory()() as session:
        assignment_id = await session.scalar(
            select(TaskAssignment.id).where(
                TaskAssignment.task_id == task_id,
                TaskAssignment.status == "active",
            )
        )
    assert assignment_id is not None
    return TaskSubmissionContextRequest(
        task_id=UUID(task_id),
        assignment_id=UUID(assignment_id),
        contributor_id=UUID(contributor_id),
        predecessor_submission_id=(
            UUID(predecessor_submission_id) if predecessor_submission_id is not None else None
        ),
    )


@pytest.mark.asyncio
async def test_task_repository_postgresql_submission_context_state_matrix(
    task_client: AsyncClient,
    task_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove TASK context facts and crossed-state failures against PostgreSQL."""
    project = await create_active_project(task_client)
    subject = "worker-submission-context"
    task = await create_started_task(task_client, project["id"], monkeypatch, subject)
    contributor_id = actor_id(subject)
    initial_request = await _submission_context_request_for_started_task(task["id"], contributor_id)

    async with db_session.get_session_factory()() as session:
        initial = await TaskRepository(session).lock_submission_context(initial_request)
        assert initial.kind == "initial"
        assert initial.status == "in_progress"
        assert initial.predecessor is None

    async with db_session.get_session_factory()() as session:
        await session.execute(
            update(WorkstreamTask)
            .where(WorkstreamTask.id == task["id"])
            .values(status="needs_revision")
        )
        await session.commit()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(
            TaskSubmissionContextUnavailable,
            match="task_submission_context_invalid",
        ):
            await TaskRepository(session).lock_submission_context(initial_request)

    async with db_session.get_session_factory()() as session:
        await session.execute(
            update(WorkstreamTask)
            .where(WorkstreamTask.id == task["id"])
            .values(status="in_progress")
        )
        await session.commit()
    monkeypatch.setattr(
        "app.modules.tasks.service.enqueue_pre_review_gate",
        hold_pre_review_enqueue,
    )
    set_dev_actor(monkeypatch, roles="worker", subject=subject)
    submission_id = await seed_finalized_submission_for_checker_test(
        task["id"], complete_submission_payload(),
    )
    submission_response = await task_client.get(
        f"/api/v1/submissions/{submission_id}", headers=auth_headers(),
    )
    assert submission_response.status_code == 200, submission_response.text
    predecessor = submission_response.json()

    async with db_session.get_session_factory()() as session:
        await session.execute(
            update(WorkstreamTask)
            .where(WorkstreamTask.id == task["id"])
            .values(status="needs_revision")
        )
        await session.commit()
    revision_request = await _submission_context_request_for_started_task(
        task["id"], contributor_id, predecessor_submission_id=predecessor["id"]
    )
    async with db_session.get_session_factory()() as session:
        revision = await TaskRepository(session).lock_submission_context(revision_request)
        assert revision.kind == "revision"
        assert revision.status == "needs_revision"
        assert revision.predecessor == SubmissionPredecessorFacts(
            submission_id=UUID(predecessor["id"]),
            version=predecessor["version"],
        )

    stale_request = TaskSubmissionContextRequest(
        task_id=revision_request.task_id,
        assignment_id=revision_request.assignment_id,
        contributor_id=revision_request.contributor_id,
        predecessor_submission_id=uuid4(),
    )
    async with db_session.get_session_factory()() as session:
        with pytest.raises(
            TaskSubmissionContextUnavailable,
            match="task_submission_predecessor_changed",
        ):
            await TaskRepository(session).lock_submission_context(stale_request)

    async with db_session.get_session_factory()() as session:
        await session.execute(
            update(WorkstreamTask)
            .where(WorkstreamTask.id == task["id"])
            .values(status="in_progress")
        )
        await session.commit()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(
            TaskSubmissionContextUnavailable,
            match="task_submission_context_invalid",
        ):
            await TaskRepository(session).lock_submission_context(revision_request)

    replacement_subject = "worker-submission-context-replacement"
    replacement_contributor_id = await seed_task_test_actor(replacement_subject)
    async with db_session.get_session_factory()() as session:
        await session.execute(
            update(TaskAssignment)
            .where(TaskAssignment.id == str(revision_request.assignment_id))
            .values(contributor_id=replacement_contributor_id)
        )
        await session.execute(
            update(WorkstreamTask)
            .where(WorkstreamTask.id == task["id"])
            .values(
                assigned_to=replacement_contributor_id,
                status="needs_revision",
            )
        )
        await session.commit()
    cross_contributor_request = TaskSubmissionContextRequest(
        task_id=revision_request.task_id,
        assignment_id=revision_request.assignment_id,
        contributor_id=UUID(replacement_contributor_id),
        predecessor_submission_id=revision_request.predecessor_submission_id,
    )
    async with db_session.get_session_factory()() as session:
        with pytest.raises(
            TaskSubmissionContextUnavailable,
            match="task_submission_context_invalid",
        ):
            await TaskRepository(session).lock_submission_context(cross_contributor_request)


@pytest.mark.asyncio
async def test_task_repository_postgresql_submission_context_lock_serializes_race(
    task_client: AsyncClient,
    task_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove the TASK row lock serializes concurrent context observation."""
    project = await create_active_project(task_client)
    subject = "worker-submission-context-race"
    task = await create_started_task(task_client, project["id"], monkeypatch, subject)
    request = await _submission_context_request_for_started_task(task["id"], actor_id(subject))
    contender_name = f"task-context-{uuid4()}"

    holder = db_session.get_session_factory()()
    contender = db_session.get_session_factory()()
    contender_call: asyncio.Task[TaskSubmissionContextFacts] | None = None
    try:
        held_facts = await TaskRepository(holder).lock_submission_context(request)
        assert held_facts.kind == "initial"
        await contender.execute(
            text("select set_config('application_name', :application_name, true)"),
            {"application_name": contender_name},
        )
        contender_call = asyncio.create_task(
            TaskRepository(contender).lock_submission_context(request)
        )
        await wait_for_named_database_lock(task_database_env, contender_name)
        assert not contender_call.done()
        await holder.rollback()
        contender_facts = await contender_call
        assert contender_facts == held_facts
    finally:
        if contender_call is not None:
            contender_call.cancel()
            with suppress(asyncio.CancelledError):
                await contender_call
        await holder.close()
        await contender.close()






def test_task_models_are_registered_for_alembic_metadata() -> None:
    expected_tables = {
        "actor_profiles",
        "actor_identity_links",
        "legacy_actor_identities",
        "legacy_workflow_eligibility",
        "workstream_tasks",
        "task_assignments",
        "submissions",
        "evidence_items",
        "audit_events",
    }

    assert expected_tables.issubset(Base.metadata.tables)
    assert "worker_profiles" not in Base.metadata.tables
    assert "reviewer_profiles" not in Base.metadata.tables
    assert db_models.ActorProfile is ActorProfile
    assert db_models.ActorIdentityLink is ActorIdentityLink
    assert db_models.LegacyActorIdentity is LegacyActorIdentity
    assert db_models.LegacyWorkflowEligibility is LegacyWorkflowEligibility
    assert not hasattr(db_models, "WorkerProfile")
    assert not hasattr(db_models, "ReviewerProfile")
    assert db_models.WorkstreamTask is WorkstreamTask
    assert db_models.TaskAssignment is TaskAssignment
    assert db_models.Submission is Submission
    assert db_models.EvidenceItem is EvidenceItem
    assert db_models.AuditEvent is AuditEvent


async def test_chunk4_migration_creates_expected_tables(task_database_env: str) -> None:
    async with db_session.get_engine().connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )

    assert {
        "actor_profiles",
        "actor_identity_links",
        "legacy_actor_identities",
        "legacy_workflow_eligibility",
        "workstream_tasks",
        "task_assignments",
        "submissions",
        "evidence_items",
        "audit_events",
    }.issubset(table_names)


def test_task_assignment_partial_unique_index_metadata_compiles() -> None:
    index = next(
        index
        for index in TaskAssignment.__table__.indexes
        if index.name == "uq_task_assignments_one_active_per_task"
    )

    postgres_compiled = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "status = 'active'" in postgres_compiled


@pytest.mark.parametrize("path", [
    "/api/v1/tasks/{task_id}/work-context",
    "/api/v1/projects/{project_id}/tasks/{task_id}/work-context",
])
def test_task_context_openapi_documents_locked_context_domain_error(path: str) -> None:
    schema = create_app().openapi()
    responses = schema["paths"][path]["get"]["responses"]
    response_422 = responses["422"]["content"]["application/json"]["schema"]

    assert {"$ref": "#/components/schemas/HTTPValidationError"} in response_422["oneOf"]
    domain_schema = next(option for option in response_422["oneOf"] if "properties" in option)
    assert domain_schema["properties"]["code"]["enum"] == ["task_locked_context_invalid"]
    assert "details" in domain_schema["properties"]
    assert set(domain_schema["required"]) == {"code", "details", "error"}
    assert domain_schema["additionalProperties"] is False


def test_task_locked_context_constraints_bind_task_submission_and_hashes() -> None:
    expected_task_constraints = {
        "fk_workstream_tasks_locked_source_snapshot_hash": [
            "locked_guide_source_snapshot_id",
            "locked_guide_source_snapshot_hash",
        ],
        "fk_workstream_tasks_locked_effective_policy_hash": [
            "locked_effective_project_submission_artifact_policy_id",
            "locked_effective_project_submission_artifact_policy_hash",
        ],
        "fk_workstream_tasks_locked_pre_submit_checker_hash": [
            "locked_pre_submit_checker_policy_id",
            "locked_pre_submit_checker_bundle_hash",
        ],
        "fk_workstream_tasks_locked_post_submit_policy_hash": [
            "locked_post_submit_checker_policy_id",
            "locked_post_submit_checker_policy_version",
            "locked_post_submit_checker_policy_hash",
        ],
    }
    for constraint_name, local_columns in expected_task_constraints.items():
        constraint = next(
            constraint
            for constraint in WorkstreamTask.__table__.foreign_key_constraints
            if constraint.name == constraint_name
        )
        assert [column.name for column in constraint.columns] == local_columns

    expected_submission_constraints = {
        "fk_submissions_task_locked_source_snapshot_hash": [
            "task_id",
            "locked_guide_source_snapshot_id",
            "locked_guide_source_snapshot_hash",
        ],
        "fk_submissions_task_locked_effective_policy_hash": [
            "task_id",
            "locked_effective_project_submission_artifact_policy_id",
            "locked_effective_project_submission_artifact_policy_hash",
        ],
        "fk_submissions_task_locked_pre_submit_checker_hash": [
            "task_id",
            "locked_pre_submit_checker_policy_id",
            "locked_pre_submit_checker_bundle_hash",
        ],
        "fk_submissions_locked_pre_submit_checker_hash": [
            "locked_pre_submit_checker_policy_id",
            "locked_pre_submit_checker_bundle_hash",
        ],
        "fk_submissions_task_locked_post_submit_policy_hash": [
            "task_id",
            "locked_post_submit_checker_policy_id",
            "locked_post_submit_checker_policy_version",
            "locked_post_submit_checker_policy_hash",
        ],
        "fk_submissions_locked_post_submit_policy_hash": [
            "locked_post_submit_checker_policy_id",
            "locked_post_submit_checker_policy_version",
            "locked_post_submit_checker_policy_hash",
        ],
    }
    for constraint_name, local_columns in expected_submission_constraints.items():
        constraint = next(
            constraint
            for constraint in Submission.__table__.foreign_key_constraints
            if constraint.name == constraint_name
        )
        assert [column.name for column in constraint.columns] == local_columns

    assert {
        "ix_workstream_tasks_locked_source_snapshot",
        "ix_workstream_tasks_locked_effective_policy_hash",
        "ix_workstream_tasks_locked_pre_submit_checker_hash",
        "ix_workstream_tasks_locked_post_submit_policy_hash",
    }.issubset({index.name for index in WorkstreamTask.__table__.indexes})
    assert {
        "ix_submissions_locked_source_snapshot",
        "ix_submissions_locked_effective_policy_hash",
        "ix_submissions_locked_pre_submit_checker_hash",
        "ix_submissions_locked_post_submit_policy_hash",
    }.issubset({index.name for index in Submission.__table__.indexes})
    assert "ck_workstream_tasks_post_submit_policy_lock_complete" in {
        constraint.name for constraint in WorkstreamTask.__table__.constraints
    }
    assert "ck_submissions_post_submit_policy_lock_complete" in {
        constraint.name for constraint in Submission.__table__.constraints
    }


async def test_task_router_service_errors_use_canonical_request_context(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_with_service_error(*_args, **_kwargs):
        raise TaskServiceError("bounded task failure")

    cases = [
        ("create_task", "POST", "/api/v1/projects/project-id/tasks", complete_task_payload()),
        ("get_task", "GET", "/api/v1/tasks/task-id", None),
        (
            "get_task_submission_requirements",
            "GET",
            "/api/v1/tasks/task-id/submission-requirements",
            None,
        ),
        ("get_task_locked_context", "GET", "/api/v1/tasks/task-id/locked-context", None),
        ("move_to_screening", "POST", "/api/v1/tasks/task-id/screen", None),
        ("release_to_ready", "POST", "/api/v1/tasks/task-id/release", None),
        ("list_task_submissions", "GET", "/api/v1/tasks/task-id/submissions", None),
        ("get_submission", "GET", "/api/v1/submissions/submission-id", None),
        ("finalize_submission", "POST", "/api/v1/submissions/submission-id/finalize", None),
        ("list_task_audit_events", "GET", "/api/v1/tasks/task-id/audit-events", None),
    ]

    for service_method, method, path, payload in cases:
        monkeypatch.setattr(TaskService, service_method, fail_with_service_error)
        response = await task_client.request(
            method,
            path,
            headers=auth_headers(),
            json=payload,
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "bounded task failure"
        assert response.json()["error"]["code"] == "invalid_request"
        assert response.json()["error"]["correlation_id"] == response.headers["x-correlation-id"]

    async def fail_with_permission_error(*_args, **_kwargs):
        raise PermissionDenied("bounded permission failure")

    monkeypatch.setattr(TaskService, "get_task", fail_with_permission_error)
    denied = await task_client.get("/api/v1/tasks/task-id", headers=auth_headers())

    assert denied.status_code == 403
    assert denied.json()["detail"] == "bounded permission failure"
    assert denied.json()["error"]["code"] == "permission_not_granted"





async def test_task_can_be_created_in_draft(task_client: AsyncClient) -> None:
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])

    assert task["status"] == "draft"
    assert "locked_guide_version" not in task
    assert task["skill_tags"] == ["stem", "proofs"]
    assert task["source_ref"] == "local-ticket-1"
    assert "required_files" not in task
    assert "required_evidence" not in task


async def test_task_create_rejects_task_owned_artifact_requirement_fields(
    task_client: AsyncClient,
) -> None:
    project = await create_active_project(task_client)
    payload = complete_task_payload()
    payload["required_files"] = ["answer.md"]
    payload["required_evidence"] = ["checker log"]

    response = await task_client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    error_text = response.text
    assert "required_files" in error_text
    assert "required_evidence" in error_text


async def test_task_create_and_transitions_reject_client_supplied_policy_context(
    task_client: AsyncClient,
) -> None:
    project = await create_active_project(task_client)
    locked_context_payload = {
        "locked_post_submit_checker_policy_id": "malicious",
        "locked_post_submit_checker_policy_version": "malicious",
        "locked_post_submit_checker_policy_hash": "sha256:" + "0" * 64,
        "locked_post_submit_checker_policy_body": {"required_checkers": []},
    }

    create_payload = complete_task_payload()
    create_payload.update(locked_context_payload)
    create_response = await task_client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        headers=auth_headers(),
        json=create_payload,
    )
    assert create_response.status_code == 422

    task = await create_draft_task(task_client, project["id"])
    screen_response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screen", **locked_context_payload},
    )
    assert screen_response.status_code == 422

    valid_screen = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screen"},
    )
    assert valid_screen.status_code == 200, valid_screen.text

    release_response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/release",
        headers=auth_headers(),
        json={"reason": "release", **locked_context_payload},
    )
    assert release_response.status_code == 422


async def test_screening_requires_active_guide_context(task_client: AsyncClient) -> None:
    project_response = await task_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(uuid4())},
        json={"name": "No Guide", "slug": "no-guide"},
    )
    assert project_response.status_code == 201, project_response.text
    task = await create_draft_task(task_client, project_response.json()["id"])

    response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screen"},
    )

    assert response.status_code == 422
    assert "active guide" in response.json()["detail"]


async def test_screening_maps_ambiguous_active_policy_context_to_controlled_error(
    task_client: AsyncClient,
) -> None:
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])

    from app.modules.projects.repository import ProjectRepository
    from types import SimpleNamespace
    with pytest.MonkeyPatch.context() as patch:
        async def ambiguous(repository, *args, **kwargs):
            return repository._resolve_current_append_only_row(
                [SimpleNamespace(id=str(uuid4()), predecessor=None) for _ in range(2)],
                "predecessor", "ambiguous approved policies",
            )
        patch.setattr(ProjectRepository, "get_current_approved_submission_artifact_policy", ambiguous)
        response = await task_client.post(
            f"/api/v1/tasks/{task['id']}/screen", headers=auth_headers(), json={"reason": "screen"},
        )
    assert response.status_code == 422
    assert "ambiguous" in response.json()["detail"]


async def test_screening_rejects_missing_task_contract_fields(task_client: AsyncClient) -> None:
    project = await create_active_project(task_client)
    payload = complete_task_payload()
    payload.pop("acceptance_criteria")
    task = await create_draft_task(task_client, project["id"], payload)

    response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screen"},
    )

    assert response.status_code == 422
    assert "acceptance_criteria" in response.json()["detail"]


async def test_screening_locks_guide_policy_context_and_payment_fields(
    task_client: AsyncClient,
) -> None:
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])

    response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screen"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "screening"
    assert body["locked_guide_version"] == "v1"
    assert body["locked_review_policy_id"]
    assert body["locked_review_policy_generation"] == 1
    assert body["locked_review_policy_hash"].startswith("sha256:")
    assert body["locked_revision_policy_id"]
    assert body["locked_revision_policy_generation"] == 1
    assert body["locked_revision_policy_hash"].startswith("sha256:")
    assert body["locked_payment_policy_version"] == "v1"
    assert body["locked_guide_source_snapshot_id"]
    assert body["locked_guide_source_snapshot_hash"].startswith("sha256:")
    assert body["locked_effective_project_submission_artifact_policy_id"]
    assert body["locked_effective_project_submission_artifact_policy_hash"].startswith("sha256:")
    assert body["locked_pre_submit_checker_policy_id"]
    assert body["locked_pre_submit_checker_bundle_hash"].startswith("sha256:")
    expected_post_submit_policy = await load_post_submit_checker_policy(project["id"])
    async with db_session.get_session_factory()() as session:
        persisted_task = await session.get(WorkstreamTask, task["id"])
        selected_guide = await session.scalar(
            select(ProjectGuide).where(
                ProjectGuide.project_id == project["id"], ProjectGuide.status == "active"
            )
        )
    assert persisted_task is not None
    assert selected_guide is not None
    assert (
        body["locked_review_policy_id"],
        body["locked_review_policy_generation"],
        body["locked_review_policy_hash"],
    ) == (
        selected_guide.selected_review_policy_id,
        selected_guide.selected_review_policy_generation,
        selected_guide.selected_review_policy_hash,
    )
    assert (
        body["locked_revision_policy_id"],
        body["locked_revision_policy_generation"],
        body["locked_revision_policy_hash"],
    ) == (
        selected_guide.selected_revision_policy_id,
        selected_guide.selected_revision_policy_generation,
        selected_guide.selected_revision_policy_hash,
    )
    assert persisted_task.locked_post_submit_checker_policy_id == expected_post_submit_policy["id"]
    assert persisted_task.locked_post_submit_checker_policy_version == "v1"
    assert (
        persisted_task.locked_post_submit_checker_policy_hash
        == expected_post_submit_policy["policy_hash"]
    )
    assert body["base_amount"] == "25.00"
    assert body["currency"] == "USD"
    assert body["payout_type"] == "fixed"


async def test_release_rejects_crossed_post_submit_policy_sidecar(
    task_client: AsyncClient,
) -> None:
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    screen = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screening checklist passed"},
    )
    assert screen.status_code == 200, screen.text
    async with db_session.get_session_factory()() as session:
        persisted_task = await session.get(WorkstreamTask, task["id"])
        assert persisted_task is not None
        locked_body = dict(persisted_task.locked_post_submit_checker_policy_body or {})
        post_submit_policy = await session.get(
            PostSubmitCheckerPolicy,
            persisted_task.locked_post_submit_checker_policy_id,
        )
        assert post_submit_policy is not None
        post_submit_policy.required_checkers = [
            *post_submit_policy.required_checkers,
            "check_acceptance_criteria_present",
        ]
        audit_ids = sorted(await session.scalars(select(AuditEvent.id)))
        await session.commit()

    release = await task_client.post(
        f"/api/v1/tasks/{task['id']}/release",
        headers=auth_headers(),
        json={"reason": "release decision recorded"},
    )

    assert release.status_code == 422, release.text
    assert release.json()["error"]["code"] == "task_locked_context_invalid"
    assert "summaries are invalid" in release.json()["detail"]
    async with db_session.get_session_factory()() as session:
        persisted_task = await session.get(WorkstreamTask, task["id"])
        assert sorted(await session.scalars(select(AuditEvent.id))) == audit_ids
        assert await session.scalar(select(func.count()).select_from(Submission)) == 0
        assert await session.scalar(select(func.count()).select_from(db_models.CheckerRun)) == 0
    assert persisted_task is not None
    assert persisted_task.status == "screening"
    assert persisted_task.locked_post_submit_checker_policy_body == locked_body
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


async def test_worker_task_response_redacts_locked_policy_hashes(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    payload = complete_task_payload()
    payload["import_batch_id"] = "private-import-batch"
    payload["external_task_id"] = "private-external-task"
    ready_task = await create_ready_task(task_client, project["id"], payload=payload)
    operator_response = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}",
        headers=auth_headers(),
    )

    assert operator_response.status_code == 200, operator_response.text

    await seed_task_test_actor("worker-one")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")

    response = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}",
        headers=auth_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    for internal_field in (
        "locked_guide_source_snapshot_id",
        "locked_guide_source_snapshot_hash",
        "locked_effective_project_submission_artifact_policy_id",
        "locked_effective_project_submission_artifact_policy_hash",
        "locked_pre_submit_checker_policy_id",
        "locked_pre_submit_checker_bundle_hash",
        "locked_post_submit_checker_policy_id",
        "locked_post_submit_checker_policy_version",
        "locked_post_submit_checker_policy_hash",
        "locked_post_submit_checker_policy_body",
        "source_ref",
        "source_payload_hash",
        "import_batch_id",
        "external_task_id",
        "created_by",
        "assigned_to",
    ):
        assert internal_field not in body


async def test_task_context_apis_return_worker_requirements_and_operator_provenance(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    payload = complete_task_payload()
    payload["import_batch_id"] = "private-import-batch"
    payload["external_task_id"] = "private-external-task"
    started_task = await create_started_task(
        task_client, project["id"], monkeypatch, payload=payload
    )

    work_context = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/work-context",
        headers=auth_headers(),
    )
    assert work_context.status_code == 200, work_context.text
    work_body = work_context.json()
    assert work_body["task"]["locked_guide_version"] == "v1"
    assert work_body["guide"]["version"] == "v1"
    assert work_body["guide"]["change_summary"] == "Initial v1"
    assert "content_markdown" not in work_body["guide"]
    assert work_body["payment_policy"]["base_amount"] == "25.00"
    assert work_body["lifecycle"]["can_submit"] is False
    assert work_body["lifecycle"]["can_run_pre_submit_check"] is False
    assert work_body["lifecycle"]["next_actions"] == []
    worker_context_json = json.dumps(work_body, sort_keys=True)
    for internal_field in (
        "locked_guide_source_snapshot_hash",
        "locked_effective_project_submission_artifact_policy_hash",
        "locked_pre_submit_checker_bundle_hash",
        "compiled_bundle",
        "checker_configs",
    ):
        assert internal_field not in worker_context_json
    for private_field in (
        "source_ref",
        "source_payload_hash",
        "import_batch_id",
        "external_task_id",
        "created_by",
        "assigned_to",
    ):
        assert private_field not in work_body["task"]

    requirements = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/submission-requirements",
        headers=auth_headers(),
    )
    assert requirements.status_code == 200, requirements.text
    requirements_body = requirements.json()
    assert requirements_body["guide_version"] == "v1"
    assert requirements_body["required_packet_fields"] == [
        "summary",
        "package_hash",
        "artifact_hash_manifest",
        "worker_attestation",
    ]
    assert requirements_body["required_artifacts"] == [
        {
            "key": "required-artifact-001",
            "path": "answer.md",
            "hash_required": True,
            "required": True,
        }
    ]
    assert requirements_body["required_evidence"] == [
        {
            "key": "required-evidence-001",
            "label": "checker_log",
            "hash_required": True,
            "required": True,
        }
    ]
    assert requirements_body["artifact_hash_algorithm"] == "sha256"
    assert set(requirements_body["allowed_storage_schemes"]) == {"local", "s3"}
    assert requirements_body["storage_reference_rules"]["credentials_allowed"] is False
    assert requirements_body["storage_reference_rules"]["query_strings_allowed"] is False
    requirements_json = json.dumps(requirements_body, sort_keys=True)
    for internal_field in (
        "source_snapshot_hash",
        "compiled_bundle",
        "checker_configs",
        "celery",
    ):
        assert internal_field not in requirements_json
    assert "source" not in requirements_body["forbidden_artifacts"][0]

    worker_locked_context = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/locked-context",
        headers=auth_headers(),
    )
    assert worker_locked_context.status_code == 403

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    locked_context = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/locked-context",
        headers=auth_headers(),
    )
    assert locked_context.status_code == 200, locked_context.text
    locked_body = locked_context.json()
    assert locked_body["locked_guide_version"] == "v1"
    assert locked_body["locked_guide_source_snapshot_hash"].startswith("sha256:")
    assert locked_body["locked_effective_project_submission_artifact_policy_hash"].startswith(
        "sha256:"
    )
    assert locked_body["locked_pre_submit_checker_bundle_hash"].startswith("sha256:")
    assert locked_body["locked_post_submit_checker_policy_hash"].startswith("sha256:")
    assert locked_body["locked_post_submit_checker_policy_body_summary"]["required_checkers"] == []


async def test_ready_worker_work_context_omits_private_task_source_fields(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    payload = complete_task_payload()
    payload["import_batch_id"] = "ready-private-import"
    payload["external_task_id"] = "ready-private-external"
    ready_task = await create_ready_task(task_client, project["id"], payload)
    await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "worker-one",
    )

    response = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}/work-context",
        headers=auth_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lifecycle"]["next_actions"] == ["claim"]
    for private_field in (
        "source_ref",
        "source_payload_hash",
        "import_batch_id",
        "external_task_id",
        "created_by",
        "assigned_to",
    ):
        assert private_field not in body["task"]


async def test_work_context_uses_stamped_policy_values_after_payment_policy_mutation(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    before_response = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/work-context",
        headers=auth_headers(),
    )
    assert before_response.status_code == 200, before_response.text
    before = before_response.json()

    async with db_session.get_session_factory()() as session:
        payment_policy = await session.scalar(
            select(PaymentPolicy).where(
                PaymentPolicy.project_id == project["id"],
                PaymentPolicy.guide_version == "v1",
            )
        )
        assert payment_policy is not None
        payment_policy.base_amount = Decimal("999.00")
        payment_policy.currency = "EUR"
        payment_policy.payout_type = "manual"
        await session.commit()

    after_response = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/work-context",
        headers=auth_headers(),
    )

    assert after_response.status_code == 200, after_response.text
    after = after_response.json()
    assert after["review_policy"] == before["review_policy"]
    assert after["revision_policy"] == before["revision_policy"]
    assert after["payment_policy"] == before["payment_policy"]
    assert after["payment_policy"]["base_amount"] == "25.00"
    assert after["payment_policy"]["currency"] == "USD"
    assert after["payment_policy"]["payout_type"] == "fixed"


async def test_task_context_apis_fail_closed_when_locked_context_is_missing(
    task_client: AsyncClient,
) -> None:
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])

    response = await task_client.get(
        f"/api/v1/tasks/{task['id']}/submission-requirements",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert set(response.json()) == {"code", "details", "error"}
    assert response.json()["code"] == "task_locked_context_invalid"
    assert response.json()["error"]["code"] == "task_locked_context_invalid"
    assert response.json()["error"]["details"] == response.json()["details"]
    assert "locked_guide_version" in response.json()["details"]["missing_fields"]


@pytest.mark.parametrize(
    "mutation",
    [
        "source_snapshot_manifest",
        "effective_policy_body",
        "pre_submit_bundle",
        "post_submit_body",
    ],
)
async def test_task_context_apis_fail_closed_on_stale_locked_context_rows(
    task_client: AsyncClient,
    mutation: str,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    # Use the manager's actual grant-backed route so AUTH cannot mask a
    # locked-policy validation defect with an earlier contributor denial.
    context_url = f"/api/v1/projects/{project['id']}/tasks/{ready_task['id']}/work-context"
    before = await task_client.get(context_url, headers=auth_headers())
    assert before.status_code == 200, before.text

    async with db_session.get_session_factory()() as session:
        persisted_task = await session.get(WorkstreamTask, ready_task["id"])
        assert persisted_task is not None
        if mutation == "source_snapshot_manifest":
            snapshot = await session.get(
                GuideSourceSnapshot,
                persisted_task.locked_guide_source_snapshot_id,
            )
            assert snapshot is not None
            snapshot.manifest_json = {**snapshot.manifest_json, "tampered": True}
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()
            return
        elif mutation == "effective_policy_body":
            effective_policy = await session.get(
                EffectiveProjectSubmissionArtifactPolicy,
                persisted_task.locked_effective_project_submission_artifact_policy_id,
            )
            assert effective_policy is not None
            effective_policy.effective_policy = {
                **effective_policy.effective_policy,
                "required_artifacts": [],
            }
        elif mutation == "pre_submit_bundle":
            pre_submit_policy = await session.get(
                PreSubmitCheckerPolicy,
                persisted_task.locked_pre_submit_checker_policy_id,
            )
            assert pre_submit_policy is not None
            pre_submit_policy.compiled_bundle = {
                **pre_submit_policy.compiled_bundle,
                "rules": [],
            }
        else:
            persisted_task.locked_post_submit_checker_policy_body = {
                **persisted_task.locked_post_submit_checker_policy_body,
                "blocking_severities": [],
            }
        if mutation in {"effective_policy_body", "pre_submit_bundle"}:
            with pytest.raises(IntegrityError, match="unified proposal content is immutable"):
                await session.commit()
            await session.rollback()
            return
        await session.commit()

    response = await task_client.get(context_url, headers=auth_headers())

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "task_locked_context_invalid"


async def test_submission_requirements_fail_closed_on_hash_consistent_malformed_policy_shape(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)

    ready_task = await create_ready_task(task_client, project["id"])
    await corrupt_locked_policy_reads(monkeypatch, ready_task["id"], "schema")
    response = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}/submission-requirements",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "task_locked_context_invalid"
    assert body["details"]["field"] == "effective_policy.schema_version"


async def test_task_context_apis_use_v1_locked_requirements_after_v2_activation(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)

    v1_requirements = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/submission-requirements",
        headers=auth_headers(),
    )
    assert v1_requirements.status_code == 200, v1_requirements.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    guide_v2 = await task_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=complete_guide_payload("v2"),
    )
    assert guide_v2.status_code == 201, guide_v2.text
    policy_v2 = task_artifact_proposal().model_copy(
        update={"required_artifacts": ("v2-answer.md",)}
    )
    await create_policy_bundle_for_guide(
        task_client,
        project["id"],
        guide_v2.json()["id"],
        policy_v2,
    )
    activate_v2 = await seed_active_guide_for_downstream_test(
        db_session.get_session_factory(),
        project_id=project["id"],
        guide_id=guide_v2.json()["id"],
    )
    assert activate_v2["guide"]["version"] == "v2"

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    work_context = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/work-context",
        headers=auth_headers(),
    )
    requirements = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/submission-requirements",
        headers=auth_headers(),
    )

    assert work_context.status_code == 200, work_context.text
    assert requirements.status_code == 200, requirements.text
    assert work_context.json()["guide"]["version"] == "v1"
    assert requirements.json()["guide_version"] == "v1"
    assert requirements.json()["required_artifacts"] == v1_requirements.json()["required_artifacts"]
    assert requirements.json()["required_artifacts"][0]["path"] == "answer.md"


async def test_tasks_under_same_active_guide_share_project_pre_submit_checker(
    task_client: AsyncClient,
) -> None:
    project = await create_active_project(task_client)
    first_task = await create_ready_task(task_client, project["id"])
    second_task = await create_ready_task(task_client, project["id"])

    assert first_task["locked_guide_version"] == "v1"
    assert second_task["locked_guide_version"] == "v1"
    assert (
        first_task["locked_guide_source_snapshot_id"]
        == second_task["locked_guide_source_snapshot_id"]
    )
    assert (
        first_task["locked_effective_project_submission_artifact_policy_hash"]
        == second_task["locked_effective_project_submission_artifact_policy_hash"]
    )
    assert (
        first_task["locked_pre_submit_checker_policy_id"]
        == second_task["locked_pre_submit_checker_policy_id"]
    )
    assert (
        first_task["locked_pre_submit_checker_bundle_hash"]
        == second_task["locked_pre_submit_checker_bundle_hash"]
    )


async def test_release_requires_decision_reason(task_client: AsyncClient) -> None:
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    screen = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screen"},
    )
    assert screen.status_code == 200, screen.text

    response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/release",
        headers=auth_headers(),
        json={},
    )

    assert response.status_code == 422
    assert "release decision reason" in response.json()["detail"]


async def test_full_task_claim_start_flow_writes_audit_events(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    grant = await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "worker-one",
    )
    worker_actor_id = grant["actor_profile_id"]

    claim = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "claiming task"},
    )
    assert claim.status_code == 200, claim.text
    assert claim.json()["task"]["status"] == "claimed"
    assert claim.json()["assignment"]["contributor_id"] == worker_actor_id

    start = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/start",
        headers=auth_headers(),
        json={"reason": "starting work"},
    )
    assert start.status_code == 200, start.text
    assert start.json()["status"] == "in_progress"

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    audit = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert audit.status_code == 200, audit.text
    events = audit.json()
    assert [event["to_status"] for event in events] == [
        "draft",
        "screening",
        "ready",
        "claimed",
        "in_progress",
    ]
    assert [event["from_status"] for event in events] == [
        None,
        "draft",
        "screening",
        "ready",
        "claimed",
    ]
    assert [event["reason"] for event in events] == [
        None,
        "screening checklist passed",
        "release decision recorded",
        "claiming task",
        "starting work",
    ]
    assert all(event["created_at"] for event in events)
    screening_event = next(event for event in events if event["to_status"] == "screening")
    release_event = next(event for event in events if event["to_status"] == "ready")
    for event in (screening_event, release_event):
        assert event["event_payload"]["locked_guide_version"] == "v1"
        assert event["event_payload"]["locked_review_policy_id"]
        assert event["event_payload"]["locked_review_policy_generation"] == 1
        assert event["event_payload"]["locked_review_policy_hash"].startswith("sha256:")
        assert event["event_payload"]["locked_revision_policy_id"]
        assert event["event_payload"]["locked_revision_policy_generation"] == 1
        assert event["event_payload"]["locked_revision_policy_hash"].startswith("sha256:")
        assert event["event_payload"]["locked_payment_policy_version"] == "v1"
    claim_event = next(event for event in events if event["to_status"] == "claimed")
    assert claim_event["actor_id"] == worker_actor_id
    assert claim_event["actor_roles"] == []
    assert claim_event["claim_snapshot"] == {}
    assert claim_event["is_dev_auth"] is False
    references = claim_event["event_payload"]["references"]
    assert references["assignment_id"] == claim.json()["assignment"]["id"]
    assert references["task_id"] == ready_task["id"]
    assert references["project_id"] == project["id"]

    async with db_session.get_session_factory()() as session:
        persisted_event = await session.get(AuditEvent, claim_event["id"])
        decision = await session.get(AuditEvent, references["authorization_decision_id"])
        assert decision.action_id == "task.claim"
        assert decision.actor_id == worker_actor_id
        assert decision.after_facts["allowed"] is True
    assert persisted_event is not None
    assert persisted_event.claim_snapshot == {}


@pytest.mark.parametrize("authority_state", ["absent", "revoked"])
async def test_submitter_without_current_project_grant_cannot_claim(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    authority_state: str,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    subject = f"claim-grant-{authority_state}"
    if authority_state == "revoked":
        grant = await admit_and_grant_project_submitter(
            task_client, monkeypatch, project["id"], subject,
        )
        set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
        revoked = await task_client.post(
            f"/api/v1/projects/{project['id']}/role-grants/{grant['grant_id']}/revoke",
            headers=auth_headers(), json={"reason": "Withdraw project authority"},
        )
        assert revoked.status_code == 200, revoked.text
    # Even a token worker role cannot supply absent or revoked project authority.
    set_dev_actor(monkeypatch, roles="worker", subject=subject)
    response = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(), json={"reason": "claim"},
    )
    assert response.status_code == 403, response.text
    context = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}/work-context", headers=auth_headers(),
    )
    assert context.status_code == 403, context.text
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(TaskAssignment).where(
            TaskAssignment.task_id == ready_task["id"],
        )) is None
        task = await session.get(WorkstreamTask, ready_task["id"])
        assert task.status == "ready" and task.assigned_to is None


@pytest.mark.parametrize("state_before_revocation", ["claimed", "in_progress"])
async def test_revocation_blocks_contributor_commands_without_rewriting_assignment(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    state_before_revocation: str,
) -> None:
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    subject = "revoked-assignee"
    grant = await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], subject,
    )
    claimed = await task_client.post(
        f"/api/v1/tasks/{task['id']}/claim", headers=auth_headers(),
    )
    assert claimed.status_code == 200, claimed.text
    if state_before_revocation == "in_progress":
        started = await task_client.post(
            f"/api/v1/tasks/{task['id']}/start", headers=auth_headers(),
        )
        assert started.status_code == 200, started.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    revoked = await task_client.post(
        f"/api/v1/projects/{project['id']}/role-grants/{grant['grant_id']}/revoke",
        headers=auth_headers(), json={"reason": "Withdraw project authority"},
    )
    assert revoked.status_code == 200, revoked.text
    set_dev_actor(monkeypatch, roles="viewer", subject=subject)
    for method, action in (("post", "start"), ("get", "work-context")):
        denied = await getattr(task_client, method)(
            f"/api/v1/tasks/{task['id']}/{action}", headers=auth_headers(),
        )
        assert denied.status_code == 403, denied.text
    async with db_session.get_session_factory()() as session:
        stored = await session.get(WorkstreamTask, task["id"])
        assert stored.status == state_before_revocation
        assert stored.assigned_to == grant["actor_profile_id"]
        assignment = await session.get(TaskAssignment, claimed.json()["assignment"]["id"])
        assert assignment.status == "active"
        assert assignment.contributor_id == grant["actor_profile_id"]
        assert await session.scalar(select(Submission).where(
            Submission.task_id == task["id"],
        )) is None


async def test_project_grant_allows_claim_without_worker_token_role(
    task_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    grant = await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "role-free-submitter",
    )
    claimed = await task_client.post(
        f"/api/v1/tasks/{task['id']}/claim", headers=auth_headers(),
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["assignment"]["contributor_id"] == grant["actor_profile_id"]
    context = await task_client.get(
        f"/api/v1/tasks/{task['id']}/work-context", headers=auth_headers(),
    )
    assert context.status_code == 200, context.text
    assert context.json()["lifecycle"]["next_actions"] == ["start"]


@pytest.mark.parametrize("profile_type", ["admin", "project_manager"])
async def test_stored_role_metadata_does_not_authorize_task_creation(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    profile_type: str,
) -> None:
    project = await create_active_project(task_client)
    subject = f"{profile_type}-profile-only"
    await seed_task_test_actor(subject, stored_role=profile_type)
    set_dev_actor(monkeypatch, roles="worker", subject=subject)

    response = await task_client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        headers=auth_headers(),
        json=complete_task_payload(),
    )

    assert response.status_code == 403
    assert "actor lacks required role" in response.json()["detail"]








async def test_registered_claim_route_rejects_identity_spoof_fields(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    grant = await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "worker-claim-overpost",
    )

    spoofed_fields = {
        "actor_id": actor_id("malicious"),
        "external_subject": "spoofed-subject",
        "external_issuer": "spoofed-issuer",
        "roles": ["admin"],
        "email": "spoofed@example.test",
        "display_name": "Spoofed Name",
    }
    for field_name, field_value in spoofed_fields.items():
        response = await task_client.post(
            f"/api/v1/tasks/{ready_task['id']}/claim",
            headers=auth_headers(),
            json={"reason": "claim", field_name: field_value},
        )
        assert response.status_code == 422
        assert field_name in response.text

    async with db_session.get_session_factory()() as session:
        profile = await session.get(ActorProfile, grant["actor_profile_id"])
        assert profile.actor_kind == "human" and profile.status == "active"
        assert profile.display_name != "Spoofed Name"
        assert profile.contact_email != "spoofed@example.test"
        assert await session.get(ActorProfile, actor_id("malicious")) is None
        assert await session.scalar(select(TaskAssignment).where(
            TaskAssignment.task_id == ready_task["id"],
        )) is None
        task = await session.get(WorkstreamTask, ready_task["id"])
        assert task.status == "ready" and task.assigned_to is None




async def test_second_claim_is_rejected(
    task_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "worker-one",
    )
    first_claim = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "claim"},
    )
    assert first_claim.status_code == 200, first_claim.text

    await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "worker-two",
    )
    second_claim = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "claim again"},
    )

    assert second_claim.status_code == 403, second_claim.text


async def test_different_worker_cannot_start_or_read_claimed_task(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "worker-one",
    )
    claim = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "claim"},
    )
    assert claim.status_code == 200, claim.text

    await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "worker-two",
    )
    start = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/start",
        headers=auth_headers(),
        json={"reason": "start"},
    )
    # Retained detail/audit reads have not yet had their separate authority
    # cutover; exercise their non-owner visibility rule with the accepted role.
    set_dev_actor(monkeypatch, roles="worker", subject="worker-two")
    read = await task_client.get(f"/api/v1/tasks/{ready_task['id']}", headers=auth_headers())
    audit = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}/audit-events",
        headers=auth_headers(),
    )

    assert start.status_code == 403, start.text
    assert read.status_code == 404
    assert audit.status_code == 404




async def test_retained_packet_reads_preserve_locked_lineage_and_redact_audit(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    worker_actor_id = actor_id("worker-one")

    submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )
    # Historical creation evidence is a stored prerequisite for the read
    # contract, not evidence that the retired public writer still executes.
    async with db_session.get_session_factory()() as session:
        stored = await session.get(Submission, submission_id)
        stored_task = await session.get(WorkstreamTask, started_task["id"])
        assert stored is not None and stored_task is not None
        actor = ActorContext(
            actor_id=worker_actor_id, external_subject="worker-one",
            external_issuer="flow-test", roles=("worker",), claim_snapshot={},
            auth_source="dev_mock", is_dev_auth=True,
        )
        service = TaskService(session)
        await service._write_task_audit(
            actor, stored_task, event_type="submission_created",
            from_status="in_progress", to_status="submitted", reason=None,
            event_payload=service._submission_audit_payload(stored),
        )
        await session.commit()
    response = await task_client.get(
        f"/api/v1/submissions/{submission_id}", headers=auth_headers(),
    )
    assert response.status_code == 200, response.text
    submission = response.json()
    assert submission["task_id"] == started_task["id"]
    assert submission["contributor_id"] == worker_actor_id
    assert submission["version"] == 1
    assert submission["status"] == "submitted"
    assert submission["finalized_at"] is not None
    assert submission["evidence_items"][0]["finalized_at"] == submission["finalized_at"]
    for internal_field in (
        "package_uri",
        "package_hash",
        "artifact_hash_manifest",
        "worker_attestation",
        "locked_guide_version",
        "locked_review_policy_id",
        "locked_review_policy_generation",
        "locked_review_policy_hash",
        "locked_revision_policy_id",
        "locked_revision_policy_generation",
        "locked_revision_policy_hash",
        "locked_payment_policy_version",
        "locked_guide_source_snapshot_id",
        "locked_guide_source_snapshot_hash",
        "locked_effective_project_submission_artifact_policy_id",
        "locked_effective_project_submission_artifact_policy_hash",
        "locked_pre_submit_checker_policy_id",
        "locked_pre_submit_checker_bundle_hash",
        "locked_post_submit_checker_policy_id",
        "locked_post_submit_checker_policy_version",
        "locked_post_submit_checker_policy_hash",
        "locked_post_submit_checker_policy_body",
    ):
        assert internal_field not in submission
    assert submission["evidence_items"][0]["metadata"] == {}
    assert "uri" not in submission["evidence_items"][0]
    assert "hash" not in submission["evidence_items"][0]
    async with db_session.get_session_factory()() as session:
        persisted_submission = await session.get(Submission, submission["id"])
        persisted_task = await session.get(WorkstreamTask, started_task["id"])
    assert persisted_submission is not None
    assert persisted_task is not None
    assert (
        persisted_submission.locked_post_submit_checker_policy_id
        == persisted_task.locked_post_submit_checker_policy_id
    )
    assert (
        persisted_submission.locked_post_submit_checker_policy_version
        == persisted_task.locked_post_submit_checker_policy_version
    )
    assert (
        persisted_submission.locked_post_submit_checker_policy_hash
        == persisted_task.locked_post_submit_checker_policy_hash
    )
    assert (
        persisted_submission.locked_review_policy_id,
        persisted_submission.locked_review_policy_generation,
        persisted_submission.locked_review_policy_hash,
    ) == (
        persisted_task.locked_review_policy_id,
        persisted_task.locked_review_policy_generation,
        persisted_task.locked_review_policy_hash,
    )
    assert (
        persisted_submission.locked_revision_policy_id,
        persisted_submission.locked_revision_policy_generation,
        persisted_submission.locked_revision_policy_hash,
    ) == (
        persisted_task.locked_revision_policy_id,
        persisted_task.locked_revision_policy_generation,
        persisted_task.locked_revision_policy_hash,
    )

    task = await task_client.get(f"/api/v1/tasks/{started_task['id']}", headers=auth_headers())
    assert task.status_code == 200, task.text
    task_body = task.json()
    assert task_body["status"] == "review_pending"
    for internal_field in (
        "source_ref",
        "source_payload_hash",
        "import_batch_id",
        "external_task_id",
        "created_by",
        "assigned_to",
    ):
        assert internal_field not in task_body

    audit = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert audit.status_code == 200, audit.text
    audit_events = {event["event_type"]: event for event in audit.json()}
    submission_event = audit_events["submission_created"]
    assert submission_event["event_type"] == "submission_created"
    assert submission_event["from_status"] == "in_progress"
    assert submission_event["to_status"] == "submitted"
    assert submission_event["event_payload"]["submission_id"] == submission["id"]
    assert submission_event["event_payload"]["submission_version"] == 1
    assert "package_hash" not in submission_event["event_payload"]
    assert "artifact_hash_manifest" not in submission_event["event_payload"]
    assert "locked_guide_source_snapshot_id" not in submission_event["event_payload"]
    assert "locked_guide_source_snapshot_hash" not in submission_event["event_payload"]
    assert (
        "locked_effective_project_submission_artifact_policy_hash"
        not in (submission_event["event_payload"])
    )
    assert "locked_pre_submit_checker_bundle_hash" not in submission_event["event_payload"]
    assert "locked_post_submit_checker_policy_hash" not in submission_event["event_payload"]

    async with db_session.get_session_factory()() as session:
        stored_submission_event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_id == started_task["id"],
                AuditEvent.event_type == "submission_created",
            )
        )
    assert stored_submission_event is not None
    assert (
        stored_submission_event.event_payload["locked_post_submit_checker_policy_hash"]
        == persisted_submission.locked_post_submit_checker_policy_hash
    )
    assert stored_submission_event.event_payload["package_hash"] == "sha256:package-v1"
    assert "package_uri" not in submission_event["event_payload"]
    finalized_event = audit_events["submission_finalized"]
    assert finalized_event["actor_id"] == worker_actor_id
    assert finalized_event["external_subject"] == "worker-one"
    assert "finalized_at" not in finalized_event["event_payload"]
    async with db_session.get_session_factory()() as session:
        stored_finalized_event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_id == started_task["id"],
                AuditEvent.event_type == "submission_finalized",
            )
        )
    assert stored_finalized_event is not None
    assert (
        stored_finalized_event.event_payload["finalized_at"].replace("+00:00", "Z")
        == submission["finalized_at"]
    )
    assert "pre_review_gate_started" not in audit_events
    assert "post_submit_checks_processing" in audit.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    manager_audit = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert manager_audit.status_code == 200, manager_audit.text
    manager_audit_events = {event["event_type"]: event for event in manager_audit.json()}
    gate_started_event = manager_audit_events["pre_review_gate_started"]
    assert gate_started_event["actor_id"] == "workstream-system:pre-review-gate"
    assert gate_started_event["event_payload"]["requester_actor_id"] == worker_actor_id
    assert gate_started_event["event_payload"]["requester_external_subject"] == "worker-one"


async def test_submission_pre_submit_rejects_hash_consistent_malformed_effective_policy(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)

    task = await create_draft_task(task_client, project["id"])
    screen = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screening checklist passed"},
    )
    assert screen.status_code == 200, screen.text
    await corrupt_locked_policy_reads(monkeypatch, task["id"], "evidence")
    response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/release",
        headers=auth_headers(),
        json={"reason": "release decision recorded"},
    )

    assert response.status_code == 422, response.text
    assert "locked project pre-submit checker policy" in response.json()["detail"]

    async with db_session.get_session_factory()() as session:
        submissions = (
            (await session.execute(select(Submission).where(Submission.task_id == task["id"])))
            .scalars()
            .all()
        )
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
    assert submissions == []
    assert checker_runs == []


async def test_submission_pre_submit_rejects_hash_consistent_malformed_packaging_policy(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)

    task = await create_draft_task(task_client, project["id"])
    screen = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screening checklist passed"},
    )
    assert screen.status_code == 200, screen.text
    await corrupt_locked_policy_reads(monkeypatch, task["id"], "packaging")
    response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/release",
        headers=auth_headers(),
        json={"reason": "release decision recorded"},
    )

    assert response.status_code == 422, response.text
    assert "locked project pre-submit checker policy" in response.json()["detail"]

    async with db_session.get_session_factory()() as session:
        submissions = (
            (await session.execute(select(Submission).where(Submission.task_id == task["id"])))
            .scalars()
            .all()
        )
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
    assert submissions == []
    assert checker_runs == []


async def test_submission_pre_submit_rejects_hash_consistent_incomplete_checker_bundle(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)

    task = await create_draft_task(task_client, project["id"])
    screen = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screening checklist passed"},
    )
    assert screen.status_code == 200, screen.text
    await corrupt_locked_policy_reads(monkeypatch, task["id"], "bundle")
    response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/release",
        headers=auth_headers(),
        json={"reason": "release decision recorded"},
    )

    assert response.status_code == 422, response.text
    assert "locked project pre-submit checker policy" in response.json()["detail"]

    async with db_session.get_session_factory()() as session:
        submissions = (
            (await session.execute(select(Submission).where(Submission.task_id == task["id"])))
            .scalars()
            .all()
        )
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
    assert submissions == []
    assert checker_runs == []


async def test_database_rejects_null_post_submit_context_on_non_draft_task(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.locked_post_submit_checker_policy_id = None
        task.locked_post_submit_checker_policy_version = None
        task.locked_post_submit_checker_policy_hash = None
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

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
    assert task is not None
    assert task.status == "in_progress"
    assert submissions == []
    assert checker_runs == []


async def test_database_rejects_submission_without_post_submit_policy_context(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        submission = Submission(
            id=str(uuid4()),
            task_id=task.id,
            contributor_id=actor_id("worker-one"),
            version=1,
            status="submitted",
            summary="Bypass submission without post-submit policy provenance.",
            package_hash="sha256:package-bypass",
            artifact_hash_manifest=[{"artifact": "answer.md", "hash": "sha256:answer-bypass"}],
            worker_attestation="Bypass attestation.",
            locked_guide_version=task.locked_guide_version,
            locked_post_submit_checker_policy_id=None,
            locked_post_submit_checker_policy_version=None,
            locked_post_submit_checker_policy_hash=None,
            locked_post_submit_checker_policy_body=None,
            locked_review_policy_id=task.locked_review_policy_id,
            locked_review_policy_generation=task.locked_review_policy_generation,
            locked_review_policy_hash=task.locked_review_policy_hash,
            locked_revision_policy_id=task.locked_revision_policy_id,
            locked_revision_policy_generation=task.locked_revision_policy_generation,
            locked_revision_policy_hash=task.locked_revision_policy_hash,
            locked_payment_policy_version=task.locked_payment_policy_version,
            locked_guide_source_snapshot_id=task.locked_guide_source_snapshot_id,
            locked_guide_source_snapshot_hash=task.locked_guide_source_snapshot_hash,
            locked_effective_project_submission_artifact_policy_id=(
                task.locked_effective_project_submission_artifact_policy_id
            ),
            locked_effective_project_submission_artifact_policy_hash=(
                task.locked_effective_project_submission_artifact_policy_hash
            ),
            locked_pre_submit_checker_policy_id=task.locked_pre_submit_checker_policy_id,
            locked_pre_submit_checker_bundle_hash=task.locked_pre_submit_checker_bundle_hash,
        )
        session.add(submission)
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_database_rejects_checker_run_without_post_submit_policy_context(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    stored_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )
    stored_response = await task_client.get(
        f"/api/v1/submissions/{stored_id}", headers=auth_headers(),
    )
    assert stored_response.status_code == 200, stored_response.text
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        submission = await session.get(Submission, stored_response.json()["id"])
        assert task is not None
        assert submission is not None
        checker_run = db_models.CheckerRun(
            id=str(uuid4()),
            task_id=task.id,
            submission_id=submission.id,
            submission_version=submission.version,
            trigger_source="submission_finalized",
            status="queued",
            routing_recommendation="not_evaluated",
            outcome_source="none",
            triggered_by="project-manager",
            triggered_by_subject="project-manager-subject",
            triggered_by_issuer="flow-test",
            trigger_auth_source="dev_mock",
            attempt_number=1,
            is_current_for_submission=True,
            locked_guide_version=submission.locked_guide_version,
            locked_post_submit_checker_policy_id=None,
            locked_post_submit_checker_policy_version=None,
            locked_post_submit_checker_policy_hash=None,
            locked_post_submit_checker_policy_body=None,
            locked_review_policy_id=submission.locked_review_policy_id,
            locked_review_policy_generation=submission.locked_review_policy_generation,
            locked_review_policy_hash=submission.locked_review_policy_hash,
            locked_revision_policy_id=submission.locked_revision_policy_id,
            locked_revision_policy_generation=submission.locked_revision_policy_generation,
            locked_revision_policy_hash=submission.locked_revision_policy_hash,
            locked_payment_policy_version=submission.locked_payment_policy_version,
            package_hash=submission.package_hash,
            artifact_hash_manifest=submission.artifact_hash_manifest,
            artifact_manifest_hash=canonical_json_hash(submission.artifact_hash_manifest),
        )
        session.add(checker_run)
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_retained_submission_versions_are_readable_without_exposing_packet_hashes(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    v1_payload = complete_submission_payload()
    v1_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], v1_payload,
    )
    v1 = await task_client.get(
        f"/api/v1/submissions/{v1_id}", headers=auth_headers(),
    )
    assert v1.status_code == 200, v1.text
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.status = "needs_revision"
        await session.commit()
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    v2_payload = complete_submission_payload("sha256:package-v2")
    v2_payload["artifact_hash_manifest"][0]["hash"] = "sha256:answer-v2"

    v2_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], v2_payload, predecessor_id=v1_id,
    )
    v2 = await task_client.get(
        f"/api/v1/submissions/{v2_id}", headers=auth_headers(),
    )

    assert v2.status_code == 200, v2.text
    first = v1.json()
    second = v2.json()
    assert second["version"] == 2
    assert second["supersedes_submission_id"] == first["id"]
    assert "package_hash" not in first
    assert "artifact_hash_manifest" not in first
    async with db_session.get_session_factory()() as session:
        persisted_v1 = await session.get(Submission, first["id"])
    assert persisted_v1 is not None
    assert persisted_v1.package_hash == "sha256:package-v1"
    assert persisted_v1.artifact_hash_manifest[0]["hash"] == "sha256:answer-v1"

    listed = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
    )
    assert listed.status_code == 200, listed.text
    assert [submission["version"] for submission in listed.json()] == [1, 2]
    assert all("package_hash" not in submission for submission in listed.json())
    assert all("artifact_hash_manifest" not in submission for submission in listed.json())

    set_dev_actor(monkeypatch, roles="worker", subject="worker-two")
    await seed_task_test_actor("worker-two")
    denied = await task_client.get(
        f"/api/v1/submissions/{second['id']}",
        headers=auth_headers(),
    )
    assert denied.status_code == 404


async def test_retained_submission_finalization_preserves_locked_guide_after_activation(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    guide_v2 = await task_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=complete_guide_payload("v2"),
    )
    assert guide_v2.status_code == 201, guide_v2.text
    await create_policy_bundle_for_guide(task_client, project["id"], guide_v2.json()["id"])
    activate_v2 = await seed_active_guide_for_downstream_test(
        db_session.get_session_factory(),
        project_id=project["id"],
        guide_id=guide_v2.json()["id"],
    )
    assert activate_v2["guide"]["version"] == "v2"

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    response_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )
    response = await task_client.get(
        f"/api/v1/submissions/{response_id}", headers=auth_headers(),
    )

    assert response.status_code == 200, response.text
    submission = response.json()
    assert "locked_guide_version" not in submission
    async with db_session.get_session_factory()() as session:
        persisted_submission = await session.get(Submission, submission["id"])
        persisted_task = await session.get(WorkstreamTask, started_task["id"])
    assert persisted_submission is not None
    assert persisted_task is not None
    assert persisted_submission.locked_guide_version == "v1"
    assert persisted_task.locked_guide_version == "v1"
    task = await task_client.get(f"/api/v1/tasks/{started_task['id']}", headers=auth_headers())
    assert task.status_code == 200, task.text
    assert task.json()["locked_guide_version"] == "v1"
    assert "locked_guide_source_snapshot_hash" not in task.json()


async def test_retained_version_read_does_not_rewrite_prior_finalized_packet(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    v1_payload = complete_submission_payload()
    v1_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], v1_payload,
    )
    v1 = await task_client.get(
        f"/api/v1/submissions/{v1_id}", headers=auth_headers(),
    )
    assert v1.status_code == 200, v1.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    locked_v1 = await task_client.post(
        f"/api/v1/submissions/{v1.json()['id']}/finalize",
        headers=auth_headers(),
    )
    assert locked_v1.status_code == 200, locked_v1.text
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.status = "needs_revision"
        await session.commit()

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    v2_payload = complete_submission_payload("sha256:package-replacement")
    v2_payload["summary"] = "Replacement packet after locked v1."
    v2_payload["artifact_hash_manifest"][0]["hash"] = "sha256:replacement-artifact"
    v2_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], v2_payload, predecessor_id=v1_id,
    )
    v2 = await task_client.get(
        f"/api/v1/submissions/{v2_id}", headers=auth_headers(),
    )

    assert v2.status_code == 200, v2.text
    assert v2.json()["version"] == 2
    assert v2.json()["supersedes_submission_id"] == v1.json()["id"]
    fetched_v1 = await task_client.get(
        f"/api/v1/submissions/{v1.json()['id']}",
        headers=auth_headers(),
    )
    assert fetched_v1.status_code == 200, fetched_v1.text
    assert fetched_v1.json()["finalized_at"] == locked_v1.json()["finalized_at"]
    assert "package_hash" not in fetched_v1.json()
    assert "artifact_hash_manifest" not in fetched_v1.json()
    async with db_session.get_session_factory()() as session:
        persisted_v1 = await session.get(Submission, v1.json()["id"])
    assert persisted_v1 is not None
    assert persisted_v1.package_hash == "sha256:package-v1"
    assert persisted_v1.artifact_hash_manifest[0]["hash"] == "sha256:answer-v1"


async def test_submitted_task_rejects_earlier_lifecycle_actions_without_new_task_audit(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )
    audit_before = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert audit_before.status_code == 200, audit_before.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    screen = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "try rescreen"},
    )
    release = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/release",
        headers=auth_headers(),
        json={"reason": "try release"},
    )
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    claim = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "try claim"},
    )
    start = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/start",
        headers=auth_headers(),
        json={"reason": "try start"},
    )
    audit_after = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )

    assert screen.status_code == 409
    assert release.status_code == 409
    # Canonical AUTH rejects the stale contributor resource before a TASK
    # transition can occur; retained management commands still report conflict.
    assert claim.status_code == 403, claim.text
    assert claim.json()["error"]["code"] == "permission_not_granted"
    assert start.status_code == 403, start.text
    assert start.json()["error"]["code"] == "permission_not_granted"
    assert audit_after.status_code == 200, audit_after.text
    assert len(audit_after.json()) == len(audit_before.json())


async def test_cross_worker_cannot_list_submissions_or_audit_after_submit(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )
    await seed_task_test_actor("worker-two")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-two")

    listed = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
    )
    audit = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )

    assert listed.status_code == 404
    assert audit.status_code == 404


@pytest.mark.parametrize("role", ["reviewer", "finance", "auditor"])
async def test_future_roles_cannot_view_unassigned_task_or_submissions(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )
    set_dev_actor(monkeypatch, roles=role, subject=f"{role}-subject")

    task_read = await task_client.get(f"/api/v1/tasks/{started_task['id']}", headers=auth_headers())
    submissions_read = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
    )

    assert task_read.status_code == 403
    assert submissions_read.status_code == 403


async def test_database_blocks_task_locked_context_mutation_after_submission(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    guide_v2 = await task_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=complete_guide_payload("v2"),
    )
    assert guide_v2.status_code == 201, guide_v2.text
    await create_policy_bundle_for_guide(task_client, project["id"], guide_v2.json()["id"])
    await seed_active_guide_for_downstream_test(
        db_session.get_session_factory(),
        project_id=project["id"],
        guide_id=guide_v2.json()["id"],
    )

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.locked_guide_version = "v2"
        task.locked_review_policy_hash = "sha256:" + "f" * 64
        task.locked_revision_policy_hash = "sha256:" + "e" * 64
        task.locked_payment_policy_version = "v2"
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_finalize_submission_rejects_unfinished_task(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    stored_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.status = "in_progress"
        submission = await TaskRepository(session).get_submission(stored_id)
        assert submission is not None
        submission.locked_at = None
        for evidence in submission.evidence_items:
            evidence.locked_at = None
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    finalize = await task_client.post(
        f"/api/v1/submissions/{stored_id}/finalize",
        headers=auth_headers(),
    )

    assert finalize.status_code == 409
    assert "submission is not locked" in finalize.json()["detail"]


async def test_finalize_submission_rejects_unsubmitted_submission_row(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    stored_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )
    async with db_session.get_session_factory()() as session:
        submission = await session.get(Submission, stored_id)
        assert submission is not None
        submission.status = "draft"
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    finalize = await task_client.post(
        f"/api/v1/submissions/{stored_id}/finalize",
        headers=auth_headers(),
    )

    assert finalize.status_code == 409
    assert "submission must be submitted before repair check" in finalize.json()["detail"]


async def test_finalization_receipt_replay_does_not_reload_policy(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    stored_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )
    stored_response = await task_client.get(
        f"/api/v1/submissions/{stored_id}", headers=auth_headers(),
    )
    assert stored_response.status_code == 200, stored_response.text
    await corrupt_locked_policy_reads(monkeypatch, started_task["id"], "stale_bundle")

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    finalize = await task_client.post(
        f"/api/v1/submissions/{stored_response.json()['id']}/finalize",
        headers=auth_headers(),
    )

    assert finalize.status_code == 200, finalize.text
    assert finalize.json()["finalized_at"] == stored_response.json()["finalized_at"]


async def test_finalize_submission_rejects_non_latest_version(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    first_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.status = "needs_revision"
        await session.commit()
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    v2_payload = complete_submission_payload("sha256:package-v2")
    v2_payload["artifact_hash_manifest"][0]["hash"] = "sha256:answer-v2"
    second_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], v2_payload, predecessor_id=first_id,
    )
    async with db_session.get_session_factory()() as session:
        first = await session.get(Submission, first_id)
        second = await session.get(Submission, second_id)
        assert first is not None and second is not None
        assert second.version == first.version + 1
        assert second.supersedes_submission_id == first.id

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    stale_finalize = await task_client.post(
        f"/api/v1/submissions/{first_id}/finalize",
        headers=auth_headers(),
    )

    assert stale_finalize.status_code == 409
    assert "only latest submission version can be repair-checked" in stale_finalize.json()["detail"]


async def test_finalization_repair_is_authorized_attributed_and_idempotent(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )
    # This is finalization/queue proof from a stored prerequisite. The retired
    # POST is not a submission-creation path. TASK's context owner must still
    # reject a revision before the task enters needs_revision.
    premature_revision = await _submission_context_request_for_started_task(
        started_task["id"], actor_id("worker-one"),
        predecessor_submission_id=submission_id,
    )
    async with db_session.get_session_factory()() as session:
        with pytest.raises(TaskSubmissionContextUnavailable, match="task_submission_context_invalid"):
            await TaskRepository(session).lock_submission_context(premature_revision)

    worker_repair = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
        json={"actor_id": "workstream-system:pre-review-gate"},
    )
    assert worker_repair.status_code == 403, worker_repair.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="other-project-manager")
    wrong_manager_finalize = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
        json={"audit_actor": "workstream-system:pre-review-gate"},
    )
    assert wrong_manager_finalize.status_code == 403
    wrong_manager_audit = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert wrong_manager_audit.status_code == 404
    wrong_manager_locked_context = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/locked-context",
        headers=auth_headers(),
    )
    assert wrong_manager_locked_context.status_code == 404

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    locked = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
        json={"audit_actor": "client-supplied-spoof"},
    )
    assert locked.status_code == 200, locked.text
    locked_body = locked.json()
    assert locked_body["finalized_at"] is not None
    assert locked_body["evidence_items"][0]["finalized_at"] == locked_body["finalized_at"]
    checker_runs = await task_client.get(
        f"/api/v1/submissions/{submission_id}/checker-runs",
        headers=auth_headers(),
    )
    assert checker_runs.status_code == 200, checker_runs.text
    assert len(checker_runs.json()) == 1
    checker_run = checker_runs.json()[0]
    assert checker_run["trigger_source"] == "submission_finalized"
    assert checker_run["triggered_by"] == "workstream-system:pre-review-gate"
    assert checker_run["triggered_by_subject"] == "workstream-system:pre-review-gate"
    assert checker_run["triggered_by_issuer"] == "workstream"
    assert checker_run["trigger_auth_source"] == "workstream_system"
    audit = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert audit.status_code == 200, audit.text
    audit_events = {event["event_type"]: event for event in audit.json()}
    finalized_event = audit_events["submission_finalized"]
    assert finalized_event["actor_id"] == actor_id("worker-one")
    assert finalized_event["external_subject"] == "worker-one"
    assert finalized_event["external_issuer"] == "flow-test"
    assert finalized_event["auth_source"] == "dev_mock"
    assert (
        finalized_event["event_payload"]["finalized_at"].replace("+00:00", "Z")
        == locked_body["finalized_at"]
    )
    for event_type in ("pre_review_gate_started", "pre_review_gate_passed"):
        event = audit_events[event_type]
        assert event["actor_id"] == "workstream-system:pre-review-gate"
        assert event["external_subject"] == "workstream-system:pre-review-gate"
        assert event["external_issuer"] == "workstream"
        assert event["auth_source"] == "workstream_system"
        assert event["event_payload"]["requester_actor_id"] == actor_id("worker-one")
        assert event["event_payload"]["requester_external_subject"] == "worker-one"
        assert event["event_payload"]["requester_external_issuer"] == "flow-test"
        assert event["event_payload"]["requester_auth_source"] == "dev_mock"
        assert event["event_payload"]["trigger_source"] == "submission_finalized"

    set_dev_actor(monkeypatch, roles="worker,project_manager", subject="worker-one")
    multi_role_worker_audit = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert multi_role_worker_audit.status_code == 200, multi_role_worker_audit.text
    assert "pre_review_gate_passed" not in multi_role_worker_audit.text
    assert "requester_actor_id" not in multi_role_worker_audit.text
    assert "post_submit_checks_processing" in multi_role_worker_audit.text
    multi_role_worker_locked_context = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/locked-context",
        headers=auth_headers(),
    )
    assert multi_role_worker_locked_context.status_code == 404

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    second_lock = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert second_lock.status_code == 200, second_lock.text
    assert second_lock.json()["finalized_at"] == locked_body["finalized_at"]
    repeated_checker_runs = await task_client.get(
        f"/api/v1/submissions/{submission_id}/checker-runs",
        headers=auth_headers(),
    )
    assert repeated_checker_runs.status_code == 200, repeated_checker_runs.text
    assert len(repeated_checker_runs.json()) == 1
    repeated_audit = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert repeated_audit.status_code == 200, repeated_audit.text
    repeated_event_types = [event["event_type"] for event in repeated_audit.json()]
    assert repeated_event_types.count("submission_finalized") == 1
    assert repeated_event_types.count("pre_review_gate_started") == 1
    assert repeated_event_types.count("pre_review_gate_passed") == 1


async def test_finalize_repairs_locked_submission_with_missing_pre_review_gate(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.checkers.gate_queue import PreReviewGateQueueError
    from app.modules.tasks import service as task_service_module

    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    original_enqueue = task_service_module.enqueue_pre_review_gate
    enqueue_calls: list[str] = []

    def fail_enqueue(*, checker_run_id: str, requester_provenance: dict) -> str:
        enqueue_calls.append(checker_run_id)
        assert requester_provenance == expected_worker_requester_provenance()
        raise PreReviewGateQueueError("simulated broker outage")

    monkeypatch.setattr(task_service_module, "enqueue_pre_review_gate", fail_enqueue)
    # Exercise initial-dispatch recovery: persistence survives broker failure;
    # the assertions below require the exact retained failure/claim evidence.
    seeded_submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
        raise_on_dispatch_failure=False,
    )
    stored_response = await task_client.get(
        f"/api/v1/submissions/{seeded_submission_id}", headers=auth_headers(),
    )
    assert stored_response.status_code == 200, stored_response.text
    assert stored_response.json()["finalized_at"] is not None

    submissions = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
    )
    assert submissions.status_code == 200, submissions.text
    assert len(submissions.json()) == 1
    submission_id = submissions.json()[0]["id"]
    assert submissions.json()[0]["finalized_at"] is not None
    assert submission_id == stored_response.json()["id"]

    async with db_session.get_session_factory()() as session:
        checker_runs = (
            (
                await session.execute(
                    select(db_models.CheckerRun).where(
                        db_models.CheckerRun.submission_id == submission_id
                    )
                )
            )
            .scalars()
            .all()
        )
        task = await session.get(WorkstreamTask, started_task["id"])
        dispatch_failed_events = (
            (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.entity_id == started_task["id"],
                        AuditEvent.event_type == "pre_review_gate_dispatch_failed",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(checker_runs) == 1
    failed_claim = checker_runs[0]
    assert failed_claim.status == "failed"
    assert failed_claim.failure_code == "pre_review_gate_enqueue_failed"
    assert failed_claim.triggered_by == "workstream-system:pre-review-gate"
    assert enqueue_calls == [failed_claim.id]
    assert task is not None
    assert task.status == "evaluation_pending"
    assert len(dispatch_failed_events) == 1
    assert dispatch_failed_events[0].event_payload["checker_run_id"] == failed_claim.id
    assert dispatch_failed_events[0].actor_id == "workstream-system:pre-review-gate"
    assert dispatch_failed_events[0].event_payload["requester_actor_id"] == actor_id("worker-one")

    monkeypatch.setattr(task_service_module, "enqueue_pre_review_gate", original_enqueue)
    worker_repair = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert worker_repair.status_code == 403, worker_repair.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    repair_response = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert repair_response.status_code == 200, repair_response.text
    assert repair_response.json()["finalized_at"] == submissions.json()[0]["finalized_at"]

    checker_runs_response = await task_client.get(
        f"/api/v1/submissions/{submission_id}/checker-runs",
        headers=auth_headers(),
    )
    assert checker_runs_response.status_code == 200, checker_runs_response.text
    assert len(checker_runs_response.json()) == 1
    repaired_run = checker_runs_response.json()[0]
    assert repaired_run["id"] == failed_claim.id
    assert repaired_run["status"] == "completed"
    assert repaired_run["trigger_source"] == "submission_finalized"
    async with db_session.get_session_factory()() as session:
        persisted_repaired_run = await session.get(db_models.CheckerRun, failed_claim.id)
        repair_event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_id == started_task["id"],
                AuditEvent.event_type == "pre_review_gate_repair_requested",
            )
        )
    assert persisted_repaired_run is not None
    assert persisted_repaired_run.failure_code is None
    assert repair_event is not None
    assert repair_event.actor_id == actor_id("project-manager-subject")
    assert repair_event.event_payload["checker_run_id"] == failed_claim.id
    assert repair_event.event_payload["previous_status"] == "failed"
    assert repair_event.event_payload["previous_failure_code"] == "pre_review_gate_enqueue_failed"
    assert repair_event.event_payload["should_enqueue"] is True

    repeat_repair = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert repeat_repair.status_code == 200, repeat_repair.text
    repeated_checker_runs = await task_client.get(
        f"/api/v1/submissions/{submission_id}/checker-runs",
        headers=auth_headers(),
    )
    assert repeated_checker_runs.status_code == 200, repeated_checker_runs.text
    assert len(repeated_checker_runs.json()) == 1
    async with db_session.get_session_factory()() as session:
        repair_events = (
            (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.entity_id == started_task["id"],
                        AuditEvent.event_type == "pre_review_gate_repair_requested",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(repair_events) == 1


async def test_failed_pre_review_gate_repair_is_idempotent_while_queued(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.checkers.gate_queue import PreReviewGateQueueError
    from app.modules.tasks import service as task_service_module

    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)

    def fail_enqueue(*, checker_run_id: str, requester_provenance: dict) -> str:
        raise PreReviewGateQueueError("simulated broker outage")

    monkeypatch.setattr(task_service_module, "enqueue_pre_review_gate", fail_enqueue)
    # Exercise initial-dispatch recovery: persistence survives broker failure;
    # the assertions below require the exact retained failure/claim evidence.
    seeded_submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
        raise_on_dispatch_failure=False,
    )
    stored_response = await task_client.get(
        f"/api/v1/submissions/{seeded_submission_id}", headers=auth_headers(),
    )
    assert stored_response.status_code == 200, stored_response.text
    assert stored_response.json()["finalized_at"] is not None
    submissions = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
    )
    assert submissions.status_code == 200, submissions.text
    submission_id = submissions.json()[0]["id"]

    async with db_session.get_session_factory()() as session:
        failed_run = await session.scalar(
            select(db_models.CheckerRun).where(db_models.CheckerRun.submission_id == submission_id)
        )
    assert failed_run is not None
    assert failed_run.status == "failed"
    assert failed_run.failure_code == "pre_review_gate_enqueue_failed"

    repair_enqueue_calls: list[str] = []

    def hold_enqueue(*, checker_run_id: str, requester_provenance: dict) -> str:
        repair_enqueue_calls.append(checker_run_id)
        return f"held:{checker_run_id}"

    monkeypatch.setattr(task_service_module, "enqueue_pre_review_gate", hold_enqueue)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    first_repair = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert first_repair.status_code == 200, first_repair.text
    second_repair = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert second_repair.status_code == 200, second_repair.text

    async with db_session.get_session_factory()() as session:
        checker_runs = (
            (
                await session.execute(
                    select(db_models.CheckerRun).where(
                        db_models.CheckerRun.submission_id == submission_id
                    )
                )
            )
            .scalars()
            .all()
        )
        repair_events = (
            (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.entity_id == started_task["id"],
                        AuditEvent.event_type == "pre_review_gate_repair_requested",
                    )
                )
            )
            .scalars()
            .all()
        )

    assert repair_enqueue_calls == [failed_run.id]
    assert len(checker_runs) == 1
    assert checker_runs[0].id == failed_run.id
    assert checker_runs[0].status == "queued"
    assert checker_runs[0].failure_code is None
    assert len(repair_events) == 1


async def test_enqueue_failure_without_current_claim_skips_dispatch_failed_audit(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.checkers.gate_queue import PreReviewGateQueueError
    from app.modules.checkers.service import CheckerService
    from app.modules.tasks import service as task_service_module

    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)

    async def miss_enqueue_failure_cas(_self, _checker_run_id: str) -> bool:
        return False

    def fail_enqueue(*, checker_run_id: str, requester_provenance: dict) -> str:
        raise PreReviewGateQueueError("simulated broker outage after claim moved")

    monkeypatch.setattr(
        task_service_module,
        "enqueue_pre_review_gate",
        fail_enqueue,
    )
    monkeypatch.setattr(
        CheckerService,
        "mark_pre_review_gate_enqueue_failed",
        miss_enqueue_failure_cas,
    )
    # Exercise initial-dispatch recovery: persistence survives broker failure;
    # the assertions below require the exact retained failure/claim evidence.
    seeded_submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
        raise_on_dispatch_failure=False,
    )
    stored_response = await task_client.get(
        f"/api/v1/submissions/{seeded_submission_id}", headers=auth_headers(),
    )
    assert stored_response.status_code == 200, stored_response.text
    submission_id = stored_response.json()["id"]

    async with db_session.get_session_factory()() as session:
        moved_run = await session.scalar(
            select(db_models.CheckerRun).where(db_models.CheckerRun.submission_id == submission_id)
        )
        dispatch_events = (
            (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.entity_type == "task",
                        AuditEvent.entity_id == started_task["id"],
                        AuditEvent.event_type == "pre_review_gate_dispatch_failed",
                    )
                )
            )
            .scalars()
            .all()
        )

    assert moved_run is not None
    assert moved_run.status == "queued"
    assert moved_run.failure_code is None
    assert dispatch_events == []


async def test_unknown_checker_gate_failure_is_repairable(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.tasks import service as task_service_module

    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)

    def hold_initial_enqueue(*, checker_run_id: str, requester_provenance: dict) -> str:
        return f"held:{checker_run_id}"

    monkeypatch.setattr(task_service_module, "enqueue_pre_review_gate", hold_initial_enqueue)
    submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )

    async with db_session.get_session_factory()() as session:
        failed_run = await session.scalar(
            select(db_models.CheckerRun).where(db_models.CheckerRun.submission_id == submission_id)
        )
        assert failed_run is not None
        failed_run.status = "failed"
        failed_run.failure_code = "unknown_checker"
        failed_run.failure_message = "checker registry was missing a required checker"
        failed_run.completed_at = datetime.now(UTC)
        await session.commit()

    repair_enqueue_calls: list[str] = []

    def hold_repair_enqueue(*, checker_run_id: str, requester_provenance: dict) -> str:
        repair_enqueue_calls.append(checker_run_id)
        return f"held:{checker_run_id}"

    monkeypatch.setattr(task_service_module, "enqueue_pre_review_gate", hold_repair_enqueue)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    repair_response = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert repair_response.status_code == 200, repair_response.text

    async with db_session.get_session_factory()() as session:
        repaired_run = await session.get(db_models.CheckerRun, failed_run.id)
        repair_event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_id == started_task["id"],
                AuditEvent.event_type == "pre_review_gate_repair_requested",
            )
        )

    assert repair_enqueue_calls == [failed_run.id]
    assert repaired_run is not None
    assert repaired_run.status == "queued"
    assert repaired_run.failure_code is None
    assert repair_event is not None


async def test_nonrepairable_failed_gate_does_not_return_success(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.tasks import service as task_service_module

    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)

    monkeypatch.setattr(
        task_service_module,
        "enqueue_pre_review_gate",
        hold_pre_review_enqueue,
    )
    submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )

    async with db_session.get_session_factory()() as session:
        failed_run = await session.scalar(
            select(db_models.CheckerRun).where(db_models.CheckerRun.submission_id == submission_id)
        )
        assert failed_run is not None
        failed_run.status = "failed"
        failed_run.failure_code = "nonrepairable_test_failure"
        failed_run.failure_message = "not repairable through finalize"
        failed_run.completed_at = datetime.now(UTC)
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    repair_response = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert repair_response.status_code == 409, repair_response.text
    assert "not repairable through finalize" in repair_response.json()["detail"]


async def test_eager_pre_review_gate_failure_after_submission_is_repairable(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.checkers.service import CheckerExecutionBlocked
    from app.workers import checkers as checker_worker_module

    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    original_run_queued_gate = checker_worker_module.CheckerService.run_queued_pre_review_gate

    async def fail_run_queued_gate(
        self,
        actor: ActorContext,
        checker_run_id: str,
        *,
        requester_provenance: dict,
    ):
        raise CheckerExecutionBlocked("simulated eager worker failure")

    monkeypatch.setattr(
        checker_worker_module.CheckerService,
        "run_queued_pre_review_gate",
        fail_run_queued_gate,
    )
    # Exercise initial-dispatch recovery: persistence survives broker failure;
    # the assertions below require the exact retained failure/claim evidence.
    seeded_submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
        raise_on_dispatch_failure=False,
    )
    stored_response = await task_client.get(
        f"/api/v1/submissions/{seeded_submission_id}", headers=auth_headers(),
    )
    assert stored_response.status_code == 200, stored_response.text
    submission_id = stored_response.json()["id"]
    assert stored_response.json()["finalized_at"] is not None

    async with db_session.get_session_factory()() as session:
        failed_run = await session.scalar(
            select(db_models.CheckerRun).where(db_models.CheckerRun.submission_id == submission_id)
        )
        task = await session.get(WorkstreamTask, started_task["id"])
        dispatch_failed_event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_id == started_task["id"],
                AuditEvent.event_type == "pre_review_gate_dispatch_failed",
            )
        )

    assert failed_run is not None
    assert failed_run.status == "failed"
    assert failed_run.failure_code == "pre_review_gate_enqueue_failed"
    assert task is not None
    assert task.status == "evaluation_pending"
    assert dispatch_failed_event is not None
    assert dispatch_failed_event.actor_id == "workstream-system:pre-review-gate"
    assert dispatch_failed_event.event_payload["checker_run_id"] == failed_run.id
    assert dispatch_failed_event.event_payload["requester_actor_id"] == actor_id("worker-one")

    monkeypatch.setattr(
        checker_worker_module.CheckerService,
        "run_queued_pre_review_gate",
        original_run_queued_gate,
    )
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    repair_response = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert repair_response.status_code == 200, repair_response.text

    async with db_session.get_session_factory()() as session:
        repaired_run = await session.get(db_models.CheckerRun, failed_run.id)
        repaired_task = await session.get(WorkstreamTask, started_task["id"])
        repair_audit = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_type == "task",
                AuditEvent.entity_id == started_task["id"],
                AuditEvent.event_type == "pre_review_gate_repair_requested",
            )
        )

    assert repaired_run is not None
    assert repaired_run.status == "completed"
    assert repaired_run.failure_code is None
    assert repaired_task is not None
    assert repaired_task.status == "review_pending"
    assert repair_audit is not None


async def test_finalize_repairs_stale_running_pre_review_gate(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.tasks import service as task_service_module

    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    original_enqueue = task_service_module.enqueue_pre_review_gate

    monkeypatch.setattr(
        task_service_module,
        "enqueue_pre_review_gate",
        hold_pre_review_enqueue,
    )
    submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )

    stale_started_at = datetime.now(UTC) - timedelta(hours=1)
    async with db_session.get_session_factory()() as session:
        queued_run = await session.scalar(
            select(db_models.CheckerRun).where(db_models.CheckerRun.submission_id == submission_id)
        )
        assert queued_run is not None
        queued_run.status = "running"
        queued_run.started_at = stale_started_at
        await session.commit()

    monkeypatch.setattr(task_service_module, "enqueue_pre_review_gate", original_enqueue)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    repair_response = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert repair_response.status_code == 200, repair_response.text

    checker_runs_response = await task_client.get(
        f"/api/v1/submissions/{submission_id}/checker-runs",
        headers=auth_headers(),
    )
    assert checker_runs_response.status_code == 200, checker_runs_response.text
    checker_runs = checker_runs_response.json()
    assert len(checker_runs) == 2
    stale_run = checker_runs[0]
    repaired_run = checker_runs[1]
    assert stale_run["id"] == queued_run.id
    assert stale_run["status"] == "failed"
    assert stale_run["failure_code"] == "pre_review_gate_running_timed_out"
    assert stale_run["is_current_for_submission"] is False
    assert repaired_run["status"] == "completed"
    assert repaired_run["attempt_number"] == 2
    assert repaired_run["supersedes_checker_run_id"] == queued_run.id
    assert repaired_run["is_current_for_submission"] is True

    async with db_session.get_session_factory()() as session:
        persisted_repaired_run = await session.get(db_models.CheckerRun, repaired_run["id"])
        persisted_stale_run = await session.get(db_models.CheckerRun, queued_run.id)
        repair_event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_id == started_task["id"],
                AuditEvent.event_type == "pre_review_gate_repair_requested",
            )
        )
    assert persisted_repaired_run is not None
    assert persisted_repaired_run.failure_code is None
    assert persisted_stale_run is not None
    assert persisted_stale_run.failure_code == "pre_review_gate_running_timed_out"
    assert persisted_stale_run.is_current_for_submission is False
    assert repair_event is not None
    assert repair_event.actor_id == actor_id("project-manager-subject")
    assert repair_event.event_payload["previous_checker_run_id"] == queued_run.id
    assert repair_event.event_payload["checker_run_id"] == repaired_run["id"]
    assert repair_event.event_payload["previous_status"] == "running"
    assert repair_event.event_payload["previous_failure_code"] is None
    assert repair_event.event_payload["previous_started_at"] is not None
    assert repair_event.event_payload["should_enqueue"] is True


async def test_stale_running_pre_review_gate_repair_is_idempotent_while_queued(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.tasks import service as task_service_module

    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)

    def hold_initial_enqueue(*, checker_run_id: str, requester_provenance: dict) -> str:
        return f"held:{checker_run_id}"

    monkeypatch.setattr(task_service_module, "enqueue_pre_review_gate", hold_initial_enqueue)
    submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )

    stale_started_at = datetime.now(UTC) - timedelta(hours=1)
    async with db_session.get_session_factory()() as session:
        queued_run = await session.scalar(
            select(db_models.CheckerRun).where(db_models.CheckerRun.submission_id == submission_id)
        )
        assert queued_run is not None
        queued_run.status = "running"
        queued_run.started_at = stale_started_at
        await session.commit()

    repair_enqueue_calls: list[str] = []

    def hold_repair_enqueue(*, checker_run_id: str, requester_provenance: dict) -> str:
        repair_enqueue_calls.append(checker_run_id)
        return f"held:{checker_run_id}"

    monkeypatch.setattr(task_service_module, "enqueue_pre_review_gate", hold_repair_enqueue)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    first_repair = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert first_repair.status_code == 200, first_repair.text
    second_repair = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert second_repair.status_code == 200, second_repair.text

    async with db_session.get_session_factory()() as session:
        checker_runs = (
            (
                await session.execute(
                    select(db_models.CheckerRun)
                    .where(db_models.CheckerRun.submission_id == submission_id)
                    .order_by(db_models.CheckerRun.attempt_number.asc())
                )
            )
            .scalars()
            .all()
        )
        repair_events = (
            (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.entity_id == started_task["id"],
                        AuditEvent.event_type == "pre_review_gate_repair_requested",
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(checker_runs) == 2
    stale_run, replacement_run = checker_runs
    assert stale_run.id == queued_run.id
    assert stale_run.status == "failed"
    assert stale_run.is_current_for_submission is False
    assert replacement_run.status == "queued"
    assert replacement_run.is_current_for_submission is True
    assert repair_enqueue_calls == [replacement_run.id]
    assert len(repair_events) == 1


async def test_finalize_redispatches_queued_pre_review_gate_without_duplicate_run(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.tasks import service as task_service_module

    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    enqueue_calls: list[dict] = []

    def hold_enqueue(*, checker_run_id: str, requester_provenance: dict) -> str:
        enqueue_calls.append(
            {
                "checker_run_id": checker_run_id,
                "requester_provenance": requester_provenance,
            }
        )
        return f"held:{checker_run_id}"

    monkeypatch.setattr(task_service_module, "enqueue_pre_review_gate", hold_enqueue)
    submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )
    stored = await task_client.get(
        f"/api/v1/submissions/{submission_id}", headers=auth_headers(),
    )
    assert stored.status_code == 200, stored.text
    assert stored.json()["finalized_at"] is not None
    assert len(enqueue_calls) == 1
    assert enqueue_calls[0]["requester_provenance"] == expected_worker_requester_provenance()
    assert "claim_snapshot" not in enqueue_calls[0]["requester_provenance"]
    assert "roles" not in enqueue_calls[0]["requester_provenance"]

    worker_repair = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert worker_repair.status_code == 403, worker_repair.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    first_repair, second_repair = await asyncio.gather(
        task_client.post(
            f"/api/v1/submissions/{submission_id}/finalize",
            headers=auth_headers(),
        ),
        task_client.post(
            f"/api/v1/submissions/{submission_id}/finalize",
            headers=auth_headers(),
        ),
    )
    assert first_repair.status_code == 200, first_repair.text
    assert second_repair.status_code == 200, second_repair.text
    assert len(enqueue_calls) == 2
    assert enqueue_calls[1]["checker_run_id"] == enqueue_calls[0]["checker_run_id"]

    async with db_session.get_session_factory()() as session:
        checker_runs = (
            (
                await session.execute(
                    select(db_models.CheckerRun).where(
                        db_models.CheckerRun.submission_id == submission_id
                    )
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

    assert len(checker_runs) == 1
    assert checker_runs[0].id == enqueue_calls[0]["checker_run_id"]
    assert checker_runs[0].status == "queued"
    event_types = [event.event_type for event in audit_events]
    assert event_types.count("submission_finalized") == 1
    assert event_types.count("pre_review_gate_repair_requested") == 1
    assert "pre_review_gate_started" not in event_types


async def test_manual_checker_run_cannot_replace_queued_automatic_gate(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.tasks import service as task_service_module

    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)

    monkeypatch.setattr(
        task_service_module,
        "enqueue_pre_review_gate",
        hold_pre_review_enqueue,
    )
    submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    manual_run = await task_client.post(
        f"/api/v1/submissions/{submission_id}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "manual shortcut attempt"},
    )

    assert manual_run.status_code == 409
    assert "automatic pre-review gate must be repaired" in manual_run.json()["detail"]
    async with db_session.get_session_factory()() as session:
        checker_runs = (
            (
                await session.execute(
                    select(db_models.CheckerRun).where(
                        db_models.CheckerRun.submission_id == submission_id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(checker_runs) == 1
    assert checker_runs[0].status == "queued"
    assert checker_runs[0].attempt_number == 1


async def test_manual_checker_run_cannot_bypass_failed_automatic_gate(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.checkers.service import CheckerExecutionBlocked
    from app.modules.tasks import service as task_service_module
    from app.workers.checkers import run_pre_review_gate

    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)

    monkeypatch.setattr(
        task_service_module,
        "enqueue_pre_review_gate",
        hold_pre_review_enqueue,
    )
    submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )

    async with db_session.get_session_factory()() as session:
        queued_run = await session.scalar(
            select(db_models.CheckerRun).where(db_models.CheckerRun.submission_id == submission_id)
        )
        lock_audit = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_id == started_task["id"],
                AuditEvent.event_type == "submission_finalized",
            )
        )
        assert queued_run is not None
        assert lock_audit is not None
        await delete_audit_fixture_as_owner(session, lock_audit.id)

    with pytest.raises(CheckerExecutionBlocked):
        cast(Any, run_pre_review_gate).run(
            queued_run.id,
            expected_worker_requester_provenance(),
        )

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    manual_run = await task_client.post(
        f"/api/v1/submissions/{submission_id}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "manual bypass attempt after failed automatic gate"},
    )
    assert manual_run.status_code == 409, manual_run.text
    assert "automatic pre-review gate must be repaired" in manual_run.json()["detail"]

    async with db_session.get_session_factory()() as session:
        checker_runs = (
            (
                await session.execute(
                    select(db_models.CheckerRun).where(
                        db_models.CheckerRun.submission_id == submission_id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(checker_runs) == 1
    assert checker_runs[0].id == queued_run.id
    assert checker_runs[0].status == "failed"
    assert checker_runs[0].failure_code == "submission_lock_audit_missing"


async def test_queued_gate_policy_error_is_failed_and_repairable(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.checkers.service import CheckerPolicyInvalid
    from app.modules.tasks import service as task_service_module
    from app.workers.checkers import run_pre_review_gate

    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    original_enqueue = task_service_module.enqueue_pre_review_gate

    monkeypatch.setattr(
        task_service_module,
        "enqueue_pre_review_gate",
        hold_pre_review_enqueue,
    )
    submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )

    async with db_session.get_session_factory()() as session:
        submission = await session.get(Submission, submission_id)
        task = await session.get(WorkstreamTask, started_task["id"])
        queued_run = await session.scalar(
            select(db_models.CheckerRun).where(db_models.CheckerRun.submission_id == submission_id)
        )
        assert submission is not None
        assert task is not None
        assert queued_run is not None
    with pytest.MonkeyPatch.context() as fault:
        await corrupt_locked_policy_reads(fault, started_task["id"], "stale_bundle")
        with pytest.raises(CheckerPolicyInvalid):
            cast(Any, run_pre_review_gate).run(
                queued_run.id, expected_worker_requester_provenance(),
            )

    async with db_session.get_session_factory()() as session:
        failed_run = await session.get(db_models.CheckerRun, queued_run.id)
        submission = await session.get(Submission, submission_id)
        task = await session.get(WorkstreamTask, started_task["id"])
        pre_submit_policy = await session.get(
            PreSubmitCheckerPolicy,
            submission.locked_pre_submit_checker_policy_id if submission is not None else "",
        )
        assert failed_run is not None
        assert submission is not None
        assert task is not None
        assert pre_submit_policy is not None
        assert failed_run.status == "failed"
        assert failed_run.failure_code == "pre_review_gate_execution_failed"
        assert task.status == "submitted"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(db_models.CheckerResult)
                .where(db_models.CheckerResult.submission_id == submission_id)
            )
            == 0
        )

    monkeypatch.setattr(task_service_module, "enqueue_pre_review_gate", original_enqueue)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    repair_response = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert repair_response.status_code == 200, repair_response.text

    checker_runs_response = await task_client.get(
        f"/api/v1/submissions/{submission_id}/checker-runs",
        headers=auth_headers(),
    )
    assert checker_runs_response.status_code == 200, checker_runs_response.text
    assert len(checker_runs_response.json()) == 1
    repaired_run = checker_runs_response.json()[0]
    assert repaired_run["id"] == queued_run.id
    assert repaired_run["status"] == "completed"
    async with db_session.get_session_factory()() as session:
        persisted_repaired_run = await session.get(db_models.CheckerRun, queued_run.id)
    assert persisted_repaired_run is not None
    assert persisted_repaired_run.failure_code is None


async def test_queued_gate_rejects_tampered_requester_provenance(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.checkers.service import CheckerExecutionBlocked
    from app.modules.tasks import service as task_service_module
    from app.workers.checkers import run_pre_review_gate

    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    original_enqueue = task_service_module.enqueue_pre_review_gate

    monkeypatch.setattr(
        task_service_module,
        "enqueue_pre_review_gate",
        hold_pre_review_enqueue,
    )
    submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )

    async with db_session.get_session_factory()() as session:
        queued_run = await session.scalar(
            select(db_models.CheckerRun).where(db_models.CheckerRun.submission_id == submission_id)
        )
    assert queued_run is not None

    with pytest.raises(CheckerExecutionBlocked):
        cast(Any, run_pre_review_gate).run(
            queued_run.id,
            {
                "requester_actor_id": actor_id("attacker"),
                "requester_external_subject": "attacker",
                "requester_external_issuer": "flow-test",
                "requester_auth_source": "dev_mock",
            },
        )

    async with db_session.get_session_factory()() as session:
        failed_run = await session.get(db_models.CheckerRun, queued_run.id)
        task = await session.get(WorkstreamTask, started_task["id"])
        gate_events = (
            (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.entity_type == "task",
                        AuditEvent.entity_id == started_task["id"],
                        AuditEvent.event_type.like("pre_review_gate_%"),
                    )
                )
            )
            .scalars()
            .all()
        )
    assert failed_run is not None
    assert failed_run.status == "failed"
    assert failed_run.failure_code == "requester_provenance_mismatch"
    assert task is not None
    assert task.status == "submitted"
    assert [event.event_type for event in gate_events] == []

    monkeypatch.setattr(task_service_module, "enqueue_pre_review_gate", original_enqueue)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    repair_response = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert repair_response.status_code == 409, repair_response.text
    assert (
        "automatic pre-review gate failure is not repairable through finalize"
        in repair_response.json()["detail"]
    )

    checker_runs_response = await task_client.get(
        f"/api/v1/submissions/{submission_id}/checker-runs",
        headers=auth_headers(),
    )
    assert checker_runs_response.status_code == 200, checker_runs_response.text
    checker_runs = checker_runs_response.json()
    assert len(checker_runs) == 1
    unrepaired_run = checker_runs[0]
    assert unrepaired_run["id"] == queued_run.id
    assert unrepaired_run["status"] == "failed"
    assert unrepaired_run["failure_code"] == "requester_provenance_mismatch"


async def test_queued_gate_fails_closed_when_lock_audit_is_missing(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.checkers.service import CheckerExecutionBlocked
    from app.modules.tasks import service as task_service_module
    from app.workers.checkers import run_pre_review_gate

    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)

    monkeypatch.setattr(
        task_service_module,
        "enqueue_pre_review_gate",
        hold_pre_review_enqueue,
    )
    submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )

    async with db_session.get_session_factory()() as session:
        queued_run = await session.scalar(
            select(db_models.CheckerRun).where(db_models.CheckerRun.submission_id == submission_id)
        )
        lock_audit = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_id == started_task["id"],
                AuditEvent.event_type == "submission_finalized",
            )
        )
        assert queued_run is not None
        assert lock_audit is not None
        await delete_audit_fixture_as_owner(session, lock_audit.id)

    with pytest.raises(CheckerExecutionBlocked):
        cast(Any, run_pre_review_gate).run(
            queued_run.id,
            expected_worker_requester_provenance(),
        )

    async with db_session.get_session_factory()() as session:
        failed_run = await session.get(db_models.CheckerRun, queued_run.id)
    assert failed_run is not None
    assert failed_run.status == "failed"
    assert failed_run.failure_code == "submission_lock_audit_missing"

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    repair_response = await task_client.post(
        f"/api/v1/submissions/{submission_id}/finalize",
        headers=auth_headers(),
    )
    assert repair_response.status_code == 409, repair_response.text
    assert "submission lock audit provenance is missing" in repair_response.json()["detail"]


async def test_stale_queued_pre_review_gate_skips_before_task_status_check(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.tasks import service as task_service_module
    from app.workers.checkers import run_pre_review_gate

    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)

    monkeypatch.setattr(
        task_service_module,
        "enqueue_pre_review_gate",
        hold_pre_review_enqueue,
    )
    v1_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.status = "needs_revision"
        v1_run = await session.scalar(
            select(db_models.CheckerRun).where(
                db_models.CheckerRun.submission_id == v1_id
            )
        )
        await session.commit()
    assert v1_run is not None
    assert v1_run.status == "queued"

    v2_payload = complete_submission_payload("sha256:package-v2")
    v2_payload["artifact_hash_manifest"][0]["hash"] = "sha256:answer-v2"
    v2_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], v2_payload, predecessor_id=v1_id,
    )

    result = cast(Any, run_pre_review_gate).run(
        v1_run.id,
        {
            **expected_worker_requester_provenance(),
            "claim_snapshot": {"roles": ["worker"]},
        },
    )
    assert result["status"] == "skipped_stale_submission"
    assert result["checker_run_id"] == v1_run.id

    async with db_session.get_session_factory()() as session:
        stale_run = await session.get(db_models.CheckerRun, v1_run.id)
        fresh_run = await session.scalar(
            select(db_models.CheckerRun).where(
                db_models.CheckerRun.submission_id == v2_id
            )
        )
        audit_events = (
            (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.entity_type == "task",
                        AuditEvent.entity_id == started_task["id"],
                        AuditEvent.event_type.like("pre_review_gate_%"),
                    )
                )
            )
            .scalars()
            .all()
        )

    assert stale_run is not None
    assert stale_run.status == "failed"
    assert stale_run.failure_code == "stale_submission_version"
    assert fresh_run is not None
    assert fresh_run.status == "queued"
    assert [event.event_type for event in audit_events] == []


async def test_submission_finalize_guard_is_atomic(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    submission_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )
    finalized_at = datetime.now(UTC)

    async with db_session.get_session_factory()() as session:
        submission = await TaskRepository(session).get_submission(submission_id)
        assert submission is not None
        submission.locked_at = None
        for evidence in submission.evidence_items:
            evidence.locked_at = None
        await session.commit()

    async with db_session.get_session_factory()() as session:
        repo = TaskRepository(session)
        assert await repo.finalize_submission_if_unlocked(submission_id, finalized_at) is True
        await repo.lock_submission_evidence(submission_id, finalized_at)
        await session.commit()

    async with db_session.get_session_factory()() as session:
        repo = TaskRepository(session)
        assert (
            await repo.finalize_submission_if_unlocked(
                submission_id,
                datetime.now(UTC),
            )
            is False
        )
        persisted = await repo.get_submission(submission_id, populate_existing=True)
        assert persisted is not None
        assert persisted.locked_at == finalized_at
        assert {evidence.locked_at for evidence in persisted.evidence_items} == {finalized_at}


async def test_database_enforces_unique_submission_version(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    stored_id = await seed_finalized_submission_for_checker_test(
        started_task["id"], complete_submission_payload(),
    )
    stored_response = await task_client.get(
        f"/api/v1/submissions/{stored_id}", headers=auth_headers(),
    )
    assert stored_response.status_code == 200, stored_response.text
    body = stored_response.json()

    async with db_session.get_session_factory()() as session:
        persisted = await session.get(Submission, body["id"])
        assert persisted is not None
        task = await session.get(WorkstreamTask, persisted.task_id)
        session.add(build_submission(
            submission_id=str(uuid4()), task=task, contributor_id=persisted.contributor_id,
            version=persisted.version, summary="duplicate",
            worker_attestation=persisted.worker_attestation,
            package_uri=persisted.package_uri, package_hash=persisted.package_hash,
            artifact_hash_manifest=persisted.artifact_hash_manifest,
            supersedes_submission_id=None,
        ))
        with pytest.raises(IntegrityError) as rejected:
            await session.commit()
        assert integrity_constraint_name(rejected.value) == "uq_submissions_task_version"


async def test_worker_cannot_create_screen_or_release_tasks(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")

    create = await task_client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        headers=auth_headers(),
        json=complete_task_payload(),
    )
    screen = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screen"},
    )
    release = await task_client.post(
        f"/api/v1/tasks/{task['id']}/release",
        headers=auth_headers(),
        json={"reason": "release"},
    )

    assert create.status_code == 403
    assert screen.status_code == 403
    assert release.status_code == 403


async def test_invalid_transitions_are_rejected(
    task_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])

    release_from_draft = await task_client.post(
        f"/api/v1/tasks/{task['id']}/release",
        headers=auth_headers(),
        json={"reason": "release"},
    )
    await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "draft-task-submitter",
    )
    start_from_draft = await task_client.post(
        f"/api/v1/tasks/{task['id']}/start",
        headers=auth_headers(),
        json={"reason": "start"},
    )

    assert release_from_draft.status_code == 409
    assert start_from_draft.status_code == 403
    assert start_from_draft.json()["error"]["code"] == "permission_not_granted"
    async with db_session.get_session_factory()() as session:
        unchanged = await session.get(WorkstreamTask, task["id"])
        assert unchanged.status == "draft" and unchanged.assigned_to is None
        assert await session.scalar(select(TaskAssignment).where(
            TaskAssignment.task_id == task["id"],
        )) is None
    with pytest.raises(InvalidTaskTransition):
        ensure_allowed_transition("unknown", "ready")


async def test_database_enforces_one_active_assignment_per_task(task_client: AsyncClient) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    first_contributor_id = await seed_task_test_actor("assignment-contributor-one")
    second_contributor_id = await seed_task_test_actor("assignment-contributor-two")

    async with db_session.get_session_factory()() as session:
        session.add_all(
            [
                TaskAssignment(
                    id=str(uuid4()),
                    task_id=ready_task["id"],
                    contributor_id=first_contributor_id,
                    assigned_by="operator",
                    status="active",
                ),
                TaskAssignment(
                    id=str(uuid4()),
                    task_id=ready_task["id"],
                    contributor_id=second_contributor_id,
                    assigned_by="operator",
                    status="active",
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_released_assignment_does_not_block_new_active_assignment(
    task_client: AsyncClient,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    first_contributor_id = await seed_task_test_actor("released-contributor-one")
    second_contributor_id = await seed_task_test_actor("released-contributor-two")

    async with db_session.get_session_factory()() as session:
        session.add_all(
            [
                TaskAssignment(
                    id=str(uuid4()),
                    task_id=ready_task["id"],
                    contributor_id=first_contributor_id,
                    assigned_by="operator",
                    status="released",
                ),
                TaskAssignment(
                    id=str(uuid4()),
                    task_id=ready_task["id"],
                    contributor_id=second_contributor_id,
                    assigned_by="operator",
                    status="active",
                ),
            ]
        )
        await session.commit()


async def test_json_and_numeric_fields_round_trip_under_postgres(task_client: AsyncClient) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, ready_task["id"])

    assert task is not None
    assert task.skill_tags == ["stem", "proofs"]
    assert task.source_payload_hash == "hash-123"
    assert task.base_amount == Decimal("25.00")
