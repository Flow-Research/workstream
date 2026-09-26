
from __future__ import annotations

from app.adapters.tasks import task_service

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Iterator
from contextlib import suppress
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID
from app.core.identifiers import new_record_id

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
from tests.submission_fixtures import seed_retained_submission

from app.core.config import get_settings
from app.core.hashing import canonical_json_hash
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
from app.modules.tasks.service import (
    TaskLockedContextInvalid,
    TaskServiceError,
)


def _locked_task_context_references() -> TaskLockedProjectContextReferences:
    """Build complete immutable locked references for focused unit tests."""
    return TaskLockedProjectContextReferences(locked_contribution_policy_version_id=UUID(int=100),
        project_id=new_record_id(),
        guide_version="v1",
        source_snapshot_id=new_record_id(),
        source_snapshot_hash="sha256:" + "1" * 64,
        effective_policy_id=new_record_id(),
        effective_policy_hash="sha256:" + "2" * 64,
        pre_submit_policy_id=new_record_id(),
        pre_submit_policy_bundle_hash="sha256:" + "3" * 64,
    )


def test_task_submission_context_public_facts_are_immutable_and_consistent() -> None:
    """Reject mutation, invalid failures, and inconsistent lifecycle facts."""
    predecessor = SubmissionPredecessorFacts(submission_id=new_record_id(), version=2)
    facts = TaskSubmissionContextFacts(submitter_contribution_policy_version_id=UUID(int=100),
        task_id=new_record_id(),
        assignment_id=new_record_id(),
        contributor_id=new_record_id(),
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
        SubmissionPredecessorFacts(submission_id=new_record_id(), version=0)
    with pytest.raises(ValueError, match="reference is empty"):
        TaskLockedProjectContextReferences(locked_contribution_policy_version_id=UUID(int=100),
            project_id=new_record_id(),
            guide_version=" ",
            source_snapshot_id=new_record_id(),
            source_snapshot_hash="sha256:" + "1" * 64,
            effective_policy_id=new_record_id(),
            effective_policy_hash="sha256:" + "2" * 64,
            pre_submit_policy_id=new_record_id(),
            pre_submit_policy_bundle_hash="sha256:" + "3" * 64,
        )
    with pytest.raises(ValueError, match="predecessor is inconsistent"):
        TaskSubmissionContextFacts(submitter_contribution_policy_version_id=UUID(int=100),
            task_id=new_record_id(),
            assignment_id=new_record_id(),
            contributor_id=new_record_id(),
            status="in_progress",
            kind="initial",
            predecessor=predecessor,
            locked_project_context=_locked_task_context_references(),
        )
    with pytest.raises(ValueError, match="predecessor is inconsistent"):
        TaskSubmissionContextFacts(submitter_contribution_policy_version_id=UUID(int=100),
            task_id=new_record_id(),
            assignment_id=new_record_id(),
            contributor_id=new_record_id(),
            status="needs_revision",
            kind="initial",
            predecessor=None,
            locked_project_context=_locked_task_context_references(),
        )


@pytest.mark.asyncio
async def test_task_repository_locks_initial_and_revision_submission_context() -> None:
    """Project exact initial and revision facts through the owner-local port."""
    contributor_id = new_record_id()
    task_id = new_record_id()
    assignment_id = new_record_id()
    predecessor_id = new_record_id()
    references = _locked_task_context_references()
    task = MagicMock(
        project_id=str(references.project_id),
        locked_contribution_policy_version_id=references.locked_contribution_policy_version_id,
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
        project_id=str(references.project_id),
        submitter_contribution_policy_version_id=references.locked_contribution_policy_version_id,
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
    assert initial == TaskSubmissionContextFacts(submitter_contribution_policy_version_id=UUID(int=100),
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
    assert revision == TaskSubmissionContextFacts(submitter_contribution_policy_version_id=UUID(int=100),
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
    task_id = new_record_id()
    contributor_id = new_record_id()
    assignment_id = new_record_id()
    task = MagicMock(assigned_to=str(contributor_id), status="in_progress",
                     project_id="same-project", locked_contribution_policy_version_id=UUID(int=100))
    assignment = MagicMock(
        task_id=str(task_id), contributor_id=str(contributor_id), status="active",
        project_id="same-project", submitter_contribution_policy_version_id=UUID(int=100)
    )
    session = MagicMock()
    session.scalar = AsyncMock(return_value=assignment)
    repository = TaskRepository(session)
    repository.get_task = AsyncMock(return_value=task)
    repository.get_latest_submission_for_task = AsyncMock(
        return_value=MagicMock(id=str(new_record_id()), version=1, contributor_id=str(contributor_id))
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
                predecessor_submission_id=new_record_id(),
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("cross_contributor", (False, True))
async def test_task_repository_rejects_invalid_revision_lineage(
    cross_contributor: bool,
) -> None:
    """Reject crossed lifecycle state and cross-contributor predecessors."""
    task_id = new_record_id()
    contributor_id = new_record_id()
    assignment_id = new_record_id()
    predecessor_id = new_record_id()
    task = MagicMock(assigned_to=str(contributor_id), status="in_progress")
    assignment = MagicMock(
        task_id=str(task_id), contributor_id=str(contributor_id), status="active"
    )
    predecessor = MagicMock(
        id=str(predecessor_id),
        version=1,
        contributor_id=str(new_record_id()) if cross_contributor else str(contributor_id),
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
    service = task_service(MagicMock(spec=AsyncSession), settings=get_settings())

    with pytest.raises(TaskLockedContextInvalid) as failure:
        getattr(service, method_name)(*args)

    assert failure.value.details == {"field": expected_field}


def test_task_service_optional_locked_policy_helpers_preserve_absence() -> None:
    service = task_service(MagicMock(spec=AsyncSession), settings=get_settings())

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
        "Idempotency-Key": str(new_record_id()),
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


async def actor_id(subject: str, issuer: str = "flow-test") -> str:
    """Look up the canonical actor registered for one external identity."""
    async with db_session.get_session_factory()() as session:
        registered_actor_id = await session.scalar(
            select(ActorIdentityLink.actor_profile_id).where(
                ActorIdentityLink.issuer == issuer,
                ActorIdentityLink.subject == subject,
            )
        )
    assert registered_actor_id is not None, (
        f"actor is not registered for issuer={issuer!r}, subject={subject!r}"
    )
    return str(registered_actor_id)


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


async def create_active_project(client: AsyncClient, *, slug: str = "task-queue-project") -> dict:
    project_response = await client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(new_record_id())},
        json={
            "name": "Task Queue Project",
            "slug": slug,
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


async def seed_task_test_actor(subject: str, *, stored_role: str = "worker") -> str:
    """Seed identity facts for row/read tests; never seed eligibility or a grant."""
    async with db_session.get_session_factory()() as session:
        existing_actor_id = await session.scalar(
            select(ActorIdentityLink.actor_profile_id).where(
                ActorIdentityLink.issuer == "flow-test",
                ActorIdentityLink.subject == subject,
            )
        )
        if existing_actor_id is not None:
            return str(existing_actor_id)
        worker_actor_id = str(new_record_id())
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
                    id=str(new_record_id()),
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


async def test_seed_task_test_actor_reuses_canonical_external_identity(
    task_client: AsyncClient,
) -> None:
    """Seed one UUIDv7 actor and reuse it for repeated identity setup."""
    first_actor_id = await seed_task_test_actor("task-seed-idempotency")
    second_actor_id = await seed_task_test_actor("task-seed-idempotency")

    assert second_actor_id == first_actor_id
    assert UUID(first_actor_id).version == 7
    async with db_session.get_session_factory()() as session:
        profile = await session.get(ActorProfile, first_actor_id)
        identity_link_count = await session.scalar(
            select(func.count())
            .select_from(ActorIdentityLink)
            .where(
                ActorIdentityLink.issuer == "flow-test",
                ActorIdentityLink.subject == "task-seed-idempotency",
            )
        )
    assert profile is not None
    assert profile.provisioning_method == "automatic_first_access"
    assert identity_link_count == 1


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
    contributor_id = await actor_id(subject)
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
    set_dev_actor(monkeypatch, roles="worker", subject=subject)
    submission_id = await seed_retained_submission(
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
        predecessor_submission_id=new_record_id(),
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
    replacement_assignment_id = str(new_record_id())
    async with db_session.get_session_factory()() as session:
        await session.execute(
            update(TaskAssignment)
            .where(TaskAssignment.id == str(revision_request.assignment_id))
            .values(status="released")
        )
        stored_task = await session.get(WorkstreamTask, task["id"])
        session.add(TaskAssignment(
            id=replacement_assignment_id, task_id=stored_task.id,
            project_id=stored_task.project_id, contributor_id=replacement_contributor_id,
            assigned_by=stored_task.created_by, status="active",
            submitter_contribution_policy_version_id=stored_task.locked_contribution_policy_version_id,
        ))
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
        assignment_id=UUID(replacement_assignment_id),
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
    request = await _submission_context_request_for_started_task(
        task["id"], await actor_id(subject)
    )
    contender_name = f"task-context-{new_record_id()}"

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
    assert domain_schema["properties"] == {"error": {"$ref": "#/components/schemas/ApiError"}}
    assert set(domain_schema["required"]) == {"error"}
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
        ("create_task", "POST", f"/api/v1/projects/{new_record_id()}/tasks", complete_task_payload()),
        ("contributor_detail", "GET", f"/api/v1/tasks/{new_record_id()}", None),
        (
            "contributor_requirements",
            "GET",
            f"/api/v1/tasks/{new_record_id()}/submission-requirements",
            None,
        ),
        ("management_locked_context", "GET", f"/api/v1/projects/{new_record_id()}/tasks/{new_record_id()}/locked-context", None),
        ("operational_locked_context", "GET", f"/api/v1/operations/projects/{new_record_id()}/tasks/{new_record_id()}/locked-context", None),
        ("audit_locked_context", "GET", f"/api/v1/audit/projects/{new_record_id()}/tasks/{new_record_id()}/locked-context", None),
        ("screen", "POST", f"/api/v1/tasks/{new_record_id()}/screen", None),
        ("release", "POST", f"/api/v1/tasks/{new_record_id()}/release", None),
        ("audit_evidence", "GET", f"/api/v1/audit/projects/{new_record_id()}/tasks/{new_record_id()}/evidence", None),
    ]

    for service_method, method, path, payload in cases:
        owner = ("app.modules.tasks.authorized_commands.AuthorizedTaskCommands."
                 if service_method in {"create_task", "screen", "release", "contributor_detail", "contributor_requirements", "management_locked_context", "operational_locked_context", "audit_locked_context", "audit_evidence"}
                 else "app.modules.tasks.service.TaskService.")
        monkeypatch.setattr(owner + service_method, fail_with_service_error)
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
        headers=auth_headers() | {"Idempotency-Key": str(new_record_id())},
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


async def test_screening_maps_unavailable_active_policy_context_to_controlled_error(
    task_client: AsyncClient,
) -> None:
    from app.modules.projects.api import ProjectLockedPolicyContextUnavailable
    from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository

    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    with pytest.MonkeyPatch.context() as patch:
        async def unavailable(*args, **kwargs):
            raise ProjectLockedPolicyContextUnavailable("invalid activation custody")
        patch.setattr(ProjectLockedPolicyRepository, "lock_active_policy_context", unavailable)
        response = await task_client.post(
            f"/api/v1/tasks/{task['id']}/screen", headers=auth_headers(), json={"reason": "screen"},
        )
    assert response.status_code == 422
    async with db_session.get_session_factory()() as session:
        stored = await session.get(WorkstreamTask, task["id"])
        assert stored.status == "draft"
        assert stored.locked_contribution_policy_version_id is None


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


async def test_screening_locks_exact_activated_policy_context(
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
    assert "locked_payment_policy_version" not in body
    assert UUID(body["locked_contribution_policy_version_id"])
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
    assert persisted_task.base_amount is None
    assert persisted_task.currency is None
    assert persisted_task.payout_type is None


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
        policy_id = post_submit_policy.id
        audit_ids = sorted(await session.scalars(select(AuditEvent.id)))
        await session.commit()

    from tests.projects.post_submit_fixtures import crossed_post_policy_read

    with crossed_post_policy_read(policy_id) as seen:
        release = await task_client.post(
            f"/api/v1/tasks/{task['id']}/release",
            headers=auth_headers(),
            json={"reason": "release decision recorded"},
        )
    assert seen

    assert release.status_code == 422, release.text
    assert release.json()["error"]["code"] == "task_locked_context_invalid"
    assert "task locked policy custody is invalid" in release.json()["detail"]
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
        f"/api/v1/projects/{project['id']}/tasks/{ready_task['id']}",
        headers=auth_headers(),
    )

    assert operator_response.status_code == 200, operator_response.text

    await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], "worker-one")
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
    assert work_body["task"]["task_id"] == started_task["id"]
    assert work_body["guide"]["version"] == "v1"
    assert work_body["guide"]["change_summary"] == "Initial v1"
    assert "content_markdown" not in work_body["guide"]
    assert "payment_policy" not in work_body
    assert set(work_body["lifecycle"]) == {"assigned_to_current_actor", "next_actions"}
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
        f"/api/v1/projects/{project['id']}/tasks/{started_task['id']}/locked-context",
        headers=auth_headers(),
    )
    assert worker_locked_context.status_code == 404

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    locked_context = await task_client.get(
        f"/api/v1/projects/{project['id']}/tasks/{started_task['id']}/locked-context",
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


async def test_task_context_apis_fail_closed_when_locked_context_is_missing(
    task_client: AsyncClient,
) -> None:
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])

    response = await task_client.get(
        f"/api/v1/projects/{project['id']}/tasks/{task['id']}/submission-requirements",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert set(response.json()) == {"error"}
    assert response.json()["error"]["code"] == "task_locked_context_invalid"
    assert "locked_guide_version" in response.json()["error"]["details"]["missing_fields"]


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
    assert response.json()["error"]["code"] == "task_locked_context_invalid"


async def test_submission_requirements_reject_detached_policy_not_matching_approval(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)

    ready_task = await create_ready_task(task_client, project["id"])
    await corrupt_locked_policy_reads(monkeypatch, ready_task["id"], "schema")
    response = await task_client.get(
        f"/api/v1/projects/{project['id']}/tasks/{ready_task['id']}/submission-requirements",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "task_locked_context_invalid"
    assert body["error"]["message"] == "Task locked context is invalid"


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


async def stored_task_audit_events(task_id: str) -> list[dict]:
    """Inspect committed owner evidence for internal lifecycle/provenance assertions."""
    from app.modules.tasks.repository import TaskRepository
    async with db_session.get_session_factory()() as session:
        rows = await TaskRepository(session).list_audit_events("task", task_id)
        return [{column.name: getattr(row, column.name) for column in AuditEvent.__table__.columns} for row in rows]


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
    audit = await stored_task_audit_events(ready_task['id'])
    events = audit
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
        assert UUID(event["event_payload"]["locked_contribution_policy_version_id"])
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
    assert response.json()["detail"] == "Task authority denied"


async def test_registered_claim_route_rejects_identity_spoof_fields(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    grant = await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "worker-claim-overpost",
    )

    malicious_actor_id = str(new_record_id())
    spoofed_fields = {
        "actor_id": malicious_actor_id,
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
        assert await session.get(ActorProfile, malicious_actor_id) is None
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
    set_dev_actor(monkeypatch, roles="worker", subject="worker-two")
    read = await task_client.get(f"/api/v1/tasks/{ready_task['id']}", headers=auth_headers())
    audit = await task_client.get(
        f"/api/v1/audit/projects/{project['id']}/tasks/{ready_task['id']}/evidence",
        headers=auth_headers(),
    )

    assert start.status_code == 403, start.text
    assert read.status_code == 404
    assert audit.status_code == 404


async def test_release_rejects_detached_effective_policy_not_matching_approval(
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
    assert response.json()["detail"] == "task locked policy custody is invalid"

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
    assert response.json()["detail"] == "task locked policy custody is invalid"

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
    assert response.json()["detail"] == "task locked policy custody is invalid"

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
        assignment = await session.scalar(select(TaskAssignment).where(TaskAssignment.task_id == task.id))
        submission = Submission(
            id=str(new_record_id()),
            task_id=task.id,
            task_assignment_id=assignment.id,
            contributor_id=await actor_id("worker-one"),
            version=1,
            status="submitted",
            summary="Bypass submission without post-submit policy provenance.",
            contribution_policy_version_id=task.locked_contribution_policy_version_id,
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
    stored_id = await seed_retained_submission(
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
            id=str(new_record_id()),
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
    v1_id = await seed_retained_submission(
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

    v2_id = await seed_retained_submission(
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
    assert [submission["version"] for submission in listed.json()["items"]] == [1, 2]
    assert all("package_hash" not in submission for submission in listed.json()["items"])
    assert all("artifact_hash_manifest" not in submission for submission in listed.json()["items"])

    set_dev_actor(monkeypatch, roles="worker", subject="worker-two")
    await seed_task_test_actor("worker-two")
    denied = await task_client.get(
        f"/api/v1/submissions/{second['id']}",
        headers=auth_headers(),
    )
    assert denied.status_code == 404


async def test_retained_submission_history_preserves_locked_guide_after_activation(
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
    response_id = await seed_retained_submission(
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
    assert task.json()["task_id"] == started_task["id"]
    assert task.json()["status"] == persisted_task.status
    assert "locked_guide_version" not in task.json()
    assert "locked_guide_source_snapshot_hash" not in task.json()


async def test_retained_version_read_does_not_rewrite_prior_finalized_packet(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    v1_payload = complete_submission_payload()
    v1_id = await seed_retained_submission(
        started_task["id"], v1_payload,
    )
    v1 = await task_client.get(
        f"/api/v1/submissions/{v1_id}", headers=auth_headers(),
    )
    assert v1.status_code == 200, v1.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    locked_v1 = v1
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.status = "needs_revision"
        await session.commit()

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    v2_payload = complete_submission_payload("sha256:package-replacement")
    v2_payload["summary"] = "Replacement packet after locked v1."
    v2_payload["artifact_hash_manifest"][0]["hash"] = "sha256:replacement-artifact"
    v2_id = await seed_retained_submission(
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
    assert fetched_v1.json()["locked_at"] == locked_v1.json()["locked_at"]
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
    await seed_retained_submission(
        started_task["id"], complete_submission_payload(),
    )
    audit_before = await stored_task_audit_events(started_task["id"])

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
    audit_after = await stored_task_audit_events(started_task["id"])

    assert screen.status_code == 403
    assert release.status_code == 403
    assert screen.json()["error"]["code"] == "permission_not_granted"
    assert release.json()["error"]["code"] == "permission_not_granted"
    # Canonical AUTH rejects stale manager and contributor resources before TASK writes.
    assert claim.status_code == 403, claim.text
    assert claim.json()["error"]["code"] == "permission_not_granted"
    assert start.status_code == 403, start.text
    assert start.json()["error"]["code"] == "permission_not_granted"
    assert len(audit_after) == len(audit_before)


async def test_cross_worker_cannot_list_submissions_or_audit_after_submit(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    await seed_retained_submission(
        started_task["id"], complete_submission_payload(),
    )
    await seed_task_test_actor("worker-two")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-two")

    listed = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
    )
    audit = await task_client.get(
        f"/api/v1/audit/projects/{project['id']}/tasks/{started_task['id']}/evidence",
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
    await seed_retained_submission(
        started_task["id"], complete_submission_payload(),
    )
    set_dev_actor(monkeypatch, roles=role, subject=f"{role}-subject")

    task_read = await task_client.get(f"/api/v1/tasks/{started_task['id']}", headers=auth_headers())
    submissions_read = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
    )

    assert task_read.status_code == 404
    assert task_read.json()["error"]["code"] == "project_authorization_resource_not_found"
    assert submissions_read.status_code == 404


async def test_database_blocks_task_locked_context_mutation_after_submission(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    await seed_retained_submission(
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
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_database_enforces_unique_submission_version(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    stored_id = await seed_retained_submission(
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
            submission_id=str(new_record_id()), task=task, contributor_id=persisted.contributor_id,
            task_assignment_id=persisted.task_assignment_id,
            contribution_policy_version_id=persisted.contribution_policy_version_id,
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

    assert release_from_draft.status_code == 403
    assert release_from_draft.json()["error"]["code"] == "permission_not_granted"
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
                    id=str(new_record_id()),
                    task_id=ready_task["id"],
                    project_id=project["id"],
                    submitter_contribution_policy_version_id=UUID(ready_task["locked_contribution_policy_version_id"]),
                    contributor_id=first_contributor_id,
                    assigned_by="operator",
                    status="active",
                ),
                TaskAssignment(
                    id=str(new_record_id()),
                    task_id=ready_task["id"],
                    project_id=project["id"],
                    submitter_contribution_policy_version_id=UUID(ready_task["locked_contribution_policy_version_id"]),
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
                    id=str(new_record_id()),
                    task_id=ready_task["id"],
                    project_id=project["id"],
                    submitter_contribution_policy_version_id=UUID(ready_task["locked_contribution_policy_version_id"]),
                    contributor_id=first_contributor_id,
                    assigned_by="operator",
                    status="released",
                ),
                TaskAssignment(
                    id=str(new_record_id()),
                    task_id=ready_task["id"],
                    project_id=project["id"],
                    submitter_contribution_policy_version_id=UUID(ready_task["locked_contribution_policy_version_id"]),
                    contributor_id=second_contributor_id,
                    assigned_by="operator",
                    status="active",
                ),
            ]
        )
        await session.commit()


async def test_task_metadata_round_trips_without_obsolete_payment_stamping(task_client: AsyncClient) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, ready_task["id"])

    assert task is not None
    assert task.skill_tags == ["stem", "proofs"]
    assert task.source_payload_hash == "hash-123"
    assert task.base_amount is None


@pytest.mark.parametrize("transition", ("screen", "release"))
@pytest.mark.parametrize("phase", ("pre", "post_missing", "post_substituted"))
async def test_catalogue_rollout_blocks_task_transition_without_writes(
    task_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, transition: str, phase: str,
) -> None:
    from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
    from app.modules.checkers.runner import default_checker_registry

    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    if transition == "release":
        screened = await task_client.post(
            f"/api/v1/tasks/{task['id']}/screen", headers=auth_headers(),
            json={"reason": "initial screening"},
        )
        assert screened.status_code == 200, screened.text
    task_query = select(WorkstreamTask.__table__).where(WorkstreamTask.id == task["id"])
    audit_query = select(AuditEvent.id).where(AuditEvent.entity_id == task["id"]).order_by(AuditEvent.id)
    async with db_session.get_session_factory()() as session:
        before = dict((await session.execute(task_query)).mappings().one())
        audits = list(await session.scalars(audit_query))
    if transition == "screen":
        assert before["status"] == "draft"
        assert all(value is None for key, value in before.items() if key.startswith("locked_"))
    else:
        assert before["status"] == "screening"
    if phase.startswith("post_"):
        metadata = current_post_submit_catalogue()
        registry = default_checker_registry()
        missing = "check_acceptance_criteria_present"
        if phase == "post_missing":
            registry._checkers.pop(missing)
        else:
            registry._checkers[missing] = registry.resolve("check_evidence_present")
        monkeypatch.setattr("app.modules.checkers.runner.default_checker_registry", lambda: registry)
        assert current_post_submit_catalogue() == metadata
    else:
        from app.modules.checkers.catalogue import build_pre_submission_checker_catalogue
        disabled = build_pre_submission_checker_catalogue().entries[0].stable_id
        monkeypatch.setattr(get_settings(), "artifact_pre_submission_checker_disabled_ids", disabled)
    if transition == "release":
        historical = await task_client.get(
            f"/api/v1/projects/{project['id']}/tasks/{task['id']}/locked-context", headers=auth_headers(),
        )
        assert historical.status_code == 200, historical.text
    response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/{transition}", headers=auth_headers(),
        json={"reason": "must remain unchanged"},
    )
    assert response.status_code == 422, response.text
    expected = "installed checkers cannot execute the locked policies"
    assert expected in response.text
    async with db_session.get_session_factory()() as session:
        assert dict((await session.execute(task_query)).mappings().one()) == before
        assert list(await session.scalars(audit_query)) == audits
        assert list(await session.scalars(select(TaskAssignment.id).where(
            TaskAssignment.task_id == task["id"],
        ))) == []
