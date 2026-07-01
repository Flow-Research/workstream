from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Iterator
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex

from app.adapters.auth.dev import actor_id_from_external_identity
from app.core.config import get_settings
from app.db import models as db_models
from app.db import session as db_session
from app.db.base import Base
from app.main import create_app
from app.modules.tasks.lifecycle import InvalidTaskTransition, ensure_allowed_transition
from app.modules.projects.models import PreSubmitCheckerPolicy
from app.modules.tasks.models import (
    AuditEvent,
    EvidenceItem,
    ReviewerProfile,
    Submission,
    TaskAssignment,
    WorkerProfile,
    WorkstreamTask,
)
from app.modules.tasks.repository import TaskRepository


@pytest.fixture
def task_database_env(
    monkeypatch: pytest.MonkeyPatch,
    postgres_database_url: str,
    migration_lock,
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", postgres_database_url)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    get_settings.cache_clear()
    asyncio.run(db_session.dispose_engine())

    config = alembic_config()
    with migration_lock():
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        yield postgres_database_url
        command.downgrade(config, "base")
    asyncio.run(db_session.dispose_engine())
    get_settings.cache_clear()


@pytest.fixture
async def task_client(task_database_env: str) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


def alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    return config


def auth_headers(token: str = "task-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def set_dev_actor(
    monkeypatch: pytest.MonkeyPatch,
    *,
    roles: str,
    subject: str,
    token: str = "task-token",
    issuer: str = "flow-test",
) -> None:
    monkeypatch.setenv("WORKSTREAM_AUTH_PROVIDER", "dev")
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "test")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_TOKEN", token)
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", subject)
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ISSUER", issuer)
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_EMAIL", f"{subject}@example.test")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_DISPLAY_NAME", subject.replace("-", " ").title())
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", roles)
    get_settings.cache_clear()


def actor_id(subject: str, issuer: str = "flow-test") -> str:
    return actor_id_from_external_identity(issuer, subject)


def complete_guide_payload(version: str = "v1") -> dict:
    return {
        "version": version,
        "content_markdown": f"# Task Guide {version}",
        "required_task_fields": [
            "title",
            "description",
            "acceptance_criteria",
            "required_evidence",
        ],
        "required_submission_fields": ["summary", "evidence", "worker_attestation"],
        "task_instructions": "Complete the task.",
        "output_requirements": "Submit the required output.",
        "acceptance_criteria": "Meets the project guide.",
        "rejection_criteria": "Missing required evidence.",
        "reviewer_rubric": "Review evidence and output.",
        "forbidden_actions": "No copied work.",
        "required_skills": ["stem"],
        "difficulty_scale": {"easy": 1, "hard": 3},
        "estimated_time_policy": {"default_minutes": 60},
        "common_rejection_reasons": ["missing evidence"],
        "evidence_policy": {"required": ["log"]},
        "unacceptable_work_policy": "Copied or unverifiable work.",
        "change_summary": f"Initial {version}",
        "checker_policy": {
            "required_checkers": ["check_policy_context_present"],
            "warning_checkers": [],
            "blocking_severities": ["high"],
        },
        "review_policy": {
            "requires_second_review": False,
            "allowed_decisions": ["accept", "needs_revision", "reject"],
            "minimum_finding_fields": ["issue", "required_fix"],
            "sla_hours": 24,
        },
        "revision_policy": {
            "max_revision_rounds": 7,
            "revision_deadline_hours": 48,
            "auto_reject_after_limit": True,
            "allowed_resubmission_states": ["needs_revision"],
            "reviewer_reassignment_rule": "same reviewer preferred",
        },
        "payment_policy": {
            "base_amount": "25.00",
            "currency": "USD",
            "payout_type": "fixed",
            "revision_payment_rule": "none",
            "rejection_payment_rule": "none",
            "accepted_payment_rule": "pay base amount",
        },
    }


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
            "compiled_bundle": pre_submit_checker_policy.compiled_bundle,
            "compiled_bundle_hash": pre_submit_checker_policy.compiled_bundle_hash,
        }


def policy_body_for_task_tests() -> dict:
    return {
        "required_artifacts": [
            {
                "key": "answer",
                "path": "answer.md",
                "hash_required": True,
                "required": True,
                "description": "Main task answer.",
            }
        ],
        "required_evidence": [
            {
                "key": "checker_log",
                "label": "checker log",
                "hash_required": True,
                "required": True,
                "description": "Evidence used by the reviewer.",
            }
        ],
        "forbidden_artifacts": [],
        "attestation_terms": ["task_test_originality"],
        "manifest_required": True,
        "artifact_hash_required": True,
        "artifact_hash_algorithm": "sha256",
        "allowed_storage_schemes": ["local", "s3", "r2"],
        "maximum_file_size_bytes": 1_000_000,
        "maximum_package_size_bytes": 5_000_000,
        "packaging": {"package_required": False},
    }


async def create_policy_bundle_for_guide(
    client: AsyncClient,
    project_id: str,
    guide_id: str,
) -> dict:
    snapshot_response = await client.post(
        f"/api/v1/projects/{project_id}/guides/{guide_id}/source-snapshots",
        headers=auth_headers(),
        json={
            "items": [
                {
                    "source_kind": "inline_markdown",
                    "durable_ref": f"inline:/guides/{guide_id}/guide",
                    "ingestion_adapter": "manual_import",
                    "content_hash": sha256_hash(f"{guide_id}:guide"),
                    "media_type": "text/markdown",
                }
            ]
        },
    )
    assert snapshot_response.status_code == 201, snapshot_response.text
    snapshot = snapshot_response.json()

    report_response = await client.post(
        f"/api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "status": "passed",
            "findings": [],
            "summary": "Guide is sufficient for test setup.",
        },
    )
    assert report_response.status_code == 201, report_response.text

    policy_response = await client.post(
        f"/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies",
        headers=auth_headers(),
        json={
            "source_snapshot_id": snapshot["id"],
            "policy_version": "v1",
            "policy_body": policy_body_for_task_tests(),
        },
    )
    assert policy_response.status_code == 201, policy_response.text
    policy = policy_response.json()

    effective_response = await client.post(
        f"/api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/"
        f"{policy['id']}/approve",
        headers=auth_headers(),
        json={"approval_note": "Approved for test setup."},
    )
    assert effective_response.status_code == 200, effective_response.text
    compiled_pre_submit_checker = await load_pre_submit_checker_policy(effective_response.json())
    return {
        "source_snapshot": snapshot,
        "sufficiency_report": report_response.json(),
        "submission_artifact_policy": policy,
        "effective_policy": effective_response.json(),
        "pre_submit_checker_policy": compiled_pre_submit_checker,
    }


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
        "required_files": ["answer.md"],
        "required_evidence": ["checker log"],
    }


def complete_submission_payload(package_hash: str = "sha256:package-v1") -> dict:
    return {
        "summary": "Completed the proof evaluation.",
        "package_uri": "local://submissions/proof-evaluation-v1.tar.zst",
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
            "I attest this submission contains no confidential client data, "
            "credentials, secrets, tokens, passwords, API keys, private source material, "
            "source code, copied platform artifacts, or copied platform content."
        ),
        "evidence_items": [
            {
                "type": "log",
                "label": "checker dry run",
                "uri": "local://evidence/checker.log",
                "hash": "sha256:log-v1",
                "size_bytes": 256,
                "metadata": {"command": "pytest"},
            }
        ],
    }


async def create_active_project(client: AsyncClient) -> dict:
    project_response = await client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={
            "name": "Task Queue Project",
            "slug": "task-queue-project",
            "description": "Project for task queue tests",
            "base_amount": "25.00",
            "currency": "USD",
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

    activation_response = await client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/activate",
        headers=auth_headers(),
    )
    assert activation_response.status_code == 200, activation_response.text
    return project


async def create_draft_task(client: AsyncClient, project_id: str, payload: dict | None = None) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers=auth_headers(),
        json=payload or complete_task_payload(),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_ready_task(client: AsyncClient, project_id: str) -> dict:
    task = await create_draft_task(client, project_id)
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
) -> dict:
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    ready_task = await create_ready_task(client, project_id)
    await seed_worker_profile(subject)
    set_dev_actor(monkeypatch, roles="worker", subject=subject)
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
    return start.json()


async def seed_worker_profile(subject: str, *, skill_tags: list[str] | None = None) -> str:
    worker_actor_id = actor_id(subject)
    async with db_session.get_session_factory()() as session:
        session.add(
            WorkerProfile(
                id=str(uuid4()),
                actor_id=worker_actor_id,
                external_subject=subject,
                external_issuer="flow-test",
                display_name=subject.replace("-", " ").title(),
                email=f"{subject}@example.test",
                skill_tags=skill_tags or ["stem"],
                status="active",
            )
        )
        await session.commit()
    return worker_actor_id


def test_task_models_are_registered_for_alembic_metadata() -> None:
    expected_tables = {
        "worker_profiles",
        "reviewer_profiles",
        "workstream_tasks",
        "task_assignments",
        "submissions",
        "evidence_items",
        "audit_events",
    }

    assert expected_tables.issubset(Base.metadata.tables)
    assert db_models.WorkerProfile is WorkerProfile
    assert db_models.ReviewerProfile is ReviewerProfile
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
        "worker_profiles",
        "reviewer_profiles",
        "workstream_tasks",
        "task_assignments",
        "submissions",
        "evidence_items",
        "audit_events",
    }.issubset(table_names)


def test_chunk4_migration_downgrade_removes_task_tables(task_database_env: str) -> None:
    config = alembic_config()
    asyncio.run(db_session.dispose_engine())
    command.downgrade(config, "0002_project_guide_foundation")

    async def inspect_tables() -> set[str]:
        async with db_session.get_engine().connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names())
            )

    table_names = asyncio.run(inspect_tables())

    assert "projects" in table_names
    assert {
        "worker_profiles",
        "reviewer_profiles",
        "workstream_tasks",
        "task_assignments",
        "submissions",
        "evidence_items",
        "audit_events",
    }.isdisjoint(table_names)

    asyncio.run(db_session.dispose_engine())
    command.upgrade(config, "head")


def test_task_assignment_partial_unique_index_metadata_compiles() -> None:
    index = next(
        index
        for index in TaskAssignment.__table__.indexes
        if index.name == "uq_task_assignments_one_active_per_task"
    )

    postgres_compiled = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "status = 'active'" in postgres_compiled


async def test_profile_upserts_update_existing_actor_rows(task_database_env: str) -> None:
    async with db_session.get_session_factory()() as session:
        repository = TaskRepository(session)
        worker_actor_id = actor_id("worker-upsert")
        first_worker = await repository.upsert_worker_profile(
            WorkerProfile(
                id=str(uuid4()),
                actor_id=worker_actor_id,
                external_subject="worker-upsert",
                external_issuer="flow-test",
                display_name="Worker Upsert",
                email="worker-upsert@example.test",
                skill_tags=["stem"],
                status="active",
            )
        )
        updated_worker = await repository.upsert_worker_profile(
            WorkerProfile(
                id=str(uuid4()),
                actor_id=worker_actor_id,
                external_subject="worker-upsert",
                external_issuer="flow-test",
                display_name="Worker Updated",
                email="worker-updated@example.test",
                skill_tags=["stem", "analysis"],
                status="active",
            )
        )

        reviewer_actor_id = actor_id("reviewer-upsert")
        first_reviewer = await repository.upsert_reviewer_profile(
            ReviewerProfile(
                id=str(uuid4()),
                actor_id=reviewer_actor_id,
                external_subject="reviewer-upsert",
                external_issuer="flow-test",
                display_name="Reviewer Upsert",
                email="reviewer-upsert@example.test",
                skill_tags=["review"],
                status="active",
            )
        )
        updated_reviewer = await repository.upsert_reviewer_profile(
            ReviewerProfile(
                id=str(uuid4()),
                actor_id=reviewer_actor_id,
                external_subject="reviewer-upsert",
                external_issuer="flow-test",
                display_name="Reviewer Updated",
                email="reviewer-updated@example.test",
                skill_tags=["review", "stem"],
                status="active",
            )
        )
        await session.commit()

    async with db_session.get_session_factory()() as session:
        worker_rows = (
            await session.execute(
                select(WorkerProfile).where(WorkerProfile.actor_id == worker_actor_id)
            )
        ).scalars().all()
        reviewer_rows = (
            await session.execute(
                select(ReviewerProfile).where(ReviewerProfile.actor_id == reviewer_actor_id)
            )
        ).scalars().all()

    assert updated_worker.id == first_worker.id
    assert updated_worker.display_name == "Worker Updated"
    assert updated_worker.skill_tags == ["stem", "analysis"]
    assert len(worker_rows) == 1
    assert worker_rows[0].id == first_worker.id
    assert updated_reviewer.id == first_reviewer.id
    assert updated_reviewer.display_name == "Reviewer Updated"
    assert updated_reviewer.skill_tags == ["review", "stem"]
    assert len(reviewer_rows) == 1
    assert reviewer_rows[0].id == first_reviewer.id


async def test_task_can_be_created_in_draft(task_client: AsyncClient) -> None:
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])

    assert task["status"] == "draft"
    assert task["locked_guide_version"] is None
    assert task["skill_tags"] == ["stem", "proofs"]
    assert task["source_ref"] == "local-ticket-1"


async def test_screening_requires_active_guide_context(task_client: AsyncClient) -> None:
    project_response = await task_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
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


async def test_screening_rejects_missing_required_task_fields(task_client: AsyncClient) -> None:
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
    assert body["locked_checker_policy_version"] == "v1"
    assert body["locked_review_policy_version"] == "v1"
    assert body["locked_revision_policy_version"] == "v1"
    assert body["locked_payment_policy_version"] == "v1"
    assert body["base_amount"] == "25.00"
    assert body["currency"] == "USD"
    assert body["payout_type"] == "fixed"


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
    worker_actor_id = await seed_worker_profile("worker-one")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")

    claim = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "claiming task"},
    )
    assert claim.status_code == 200, claim.text
    assert claim.json()["task"]["status"] == "claimed"
    assert claim.json()["assignment"]["worker_id"] == worker_actor_id

    start = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/start",
        headers=auth_headers(),
        json={"reason": "starting work"},
    )
    assert start.status_code == 200, start.text
    assert start.json()["status"] == "in_progress"

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
        assert event["event_payload"]["locked_checker_policy_version"] == "v1"
        assert event["event_payload"]["locked_review_policy_version"] == "v1"
        assert event["event_payload"]["locked_revision_policy_version"] == "v1"
        assert event["event_payload"]["locked_payment_policy_version"] == "v1"
    claim_event = next(event for event in events if event["to_status"] == "claimed")
    assert claim_event["actor_id"] == worker_actor_id
    assert claim_event["external_subject"] == "worker-one"
    assert claim_event["external_issuer"] == "flow-test"
    assert claim_event["actor_roles"] == ["worker"]
    assert claim_event["claim_snapshot"] == {}
    assert claim_event["auth_source"] == "dev_mock"
    assert claim_event["is_dev_auth"] is True
    assert claim_event["event_payload"]["assignment_id"] == claim.json()["assignment"]["id"]

    async with db_session.get_session_factory()() as session:
        persisted_event = await session.get(AuditEvent, claim_event["id"])
    assert persisted_event is not None
    assert persisted_event.claim_snapshot["roles"] == ["worker"]


async def test_worker_without_profile_cannot_claim_ready_task(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    set_dev_actor(monkeypatch, roles="worker", subject="worker-without-profile")

    response = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "claim"},
    )

    assert response.status_code == 403
    assert "active worker profile" in response.json()["detail"]


async def test_second_claim_is_rejected(task_client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    await seed_worker_profile("worker-one")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    first_claim = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "claim"},
    )
    assert first_claim.status_code == 200, first_claim.text

    await seed_worker_profile("worker-two")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-two")
    second_claim = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "claim again"},
    )

    assert second_claim.status_code == 409


async def test_different_worker_cannot_start_or_read_claimed_task(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    await seed_worker_profile("worker-one")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    claim = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "claim"},
    )
    assert claim.status_code == 200, claim.text

    await seed_worker_profile("worker-two")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-two")
    start = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/start",
        headers=auth_headers(),
        json={"reason": "start"},
    )
    read = await task_client.get(f"/api/v1/tasks/{ready_task['id']}", headers=auth_headers())
    audit = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}/audit-events",
        headers=auth_headers(),
    )

    assert start.status_code == 409
    assert read.status_code == 404
    assert audit.status_code == 404


async def test_operator_start_override_requires_reason_and_records_distinct_event(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    await seed_worker_profile("worker-one")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    claim = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "claim"},
    )
    assert claim.status_code == 200, claim.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    missing_reason = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/start",
        headers=auth_headers(),
        json={},
    )
    assert missing_reason.status_code == 422

    started = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/start",
        headers=auth_headers(),
        json={"reason": "operator verified worker started"},
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "in_progress"

    audit = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert audit.status_code == 200, audit.text
    assert audit.json()[-1]["event_type"] == "task_start_override"
    assert audit.json()[-1]["event_payload"]["operator_override"] is True


async def test_assigned_worker_submits_v1_and_task_moves_to_submitted(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    worker_actor_id = actor_id("worker-one")

    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )

    assert response.status_code == 201, response.text
    submission = response.json()
    assert submission["task_id"] == started_task["id"]
    assert submission["worker_id"] == worker_actor_id
    assert submission["version"] == 1
    assert submission["status"] == "submitted"
    assert submission["locked_guide_version"] == "v1"
    assert submission["locked_checker_policy_version"] == "v1"
    assert submission["locked_review_policy_version"] == "v1"
    assert submission["locked_revision_policy_version"] == "v1"
    assert submission["locked_payment_policy_version"] == "v1"
    assert submission["artifact_hash_manifest"][0]["artifact"] == "answer.md"
    assert submission["evidence_items"][0]["metadata"] == {"command": "pytest"}

    task = await task_client.get(f"/api/v1/tasks/{started_task['id']}", headers=auth_headers())
    assert task.status_code == 200, task.text
    assert task.json()["status"] == "submitted"

    audit = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert audit.status_code == 200, audit.text
    submission_event = audit.json()[-1]
    assert submission_event["event_type"] == "submission_created"
    assert submission_event["from_status"] == "in_progress"
    assert submission_event["to_status"] == "submitted"
    assert submission_event["event_payload"]["submission_id"] == submission["id"]
    assert submission_event["event_payload"]["submission_version"] == 1
    assert submission_event["event_payload"]["package_hash"] == "sha256:package-v1"
    assert "package_uri" not in submission_event["event_payload"]


async def test_submission_schema_rejects_worker_supplied_locked_context(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload.update(
        {
            "worker_id": actor_id("worker-one"),
            "version": 1,
            "status": "submitted",
            "locked_guide_version": "malicious",
            "locked_checker_policy_version": "malicious",
            "locked_review_policy_version": "malicious",
            "locked_revision_policy_version": "malicious",
            "locked_payment_policy_version": "malicious",
            "locked_at": "2026-06-07T00:00:00Z",
        }
    )

    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    task = await task_client.get(f"/api/v1/tasks/{started_task['id']}", headers=auth_headers())
    assert task.status_code == 200, task.text
    assert task.json()["status"] == "in_progress"


async def test_submission_requires_assigned_worker_and_in_progress_task(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    await seed_worker_profile("worker-two")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-two")

    ready_response = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )

    assert ready_response.status_code == 409

    started_task = await create_started_task(task_client, project["id"], monkeypatch, "worker-one")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-two")
    other_worker_response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )

    assert other_worker_response.status_code == 409


async def test_submission_validates_locked_guide_required_submission_fields(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["evidence_items"] = []

    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    assert "evidence" in response.json()["detail"]


async def test_submission_versioning_creates_new_rows_and_preserves_v1(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    v1_payload = complete_submission_payload()
    v1_payload["artifact_hash_manifest"] = [
        {
            "artifact": "other.md",
            "hash": "sha256:other-v1",
            "size_bytes": 128,
            "notes": "missing required file so v2 is a revision",
        }
    ]
    v1 = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=v1_payload,
    )
    assert v1.status_code == 201, v1.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    locked_v1 = await task_client.post(
        f"/api/v1/submissions/{v1.json()['id']}/lock",
        headers=auth_headers(),
    )
    assert locked_v1.status_code == 200, locked_v1.text
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    v2_payload = complete_submission_payload("sha256:package-v2")
    v2_payload["artifact_hash_manifest"][0]["hash"] = "sha256:answer-v2"

    v2 = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=v2_payload,
    )

    assert v2.status_code == 201, v2.text
    first = v1.json()
    second = v2.json()
    assert second["version"] == 2
    assert second["supersedes_submission_id"] == first["id"]
    assert first["package_hash"] == "sha256:package-v1"
    assert first["artifact_hash_manifest"][0]["hash"] == "sha256:other-v1"

    listed = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
    )
    assert listed.status_code == 200, listed.text
    assert [submission["version"] for submission in listed.json()] == [1, 2]

    set_dev_actor(monkeypatch, roles="worker", subject="worker-two")
    await seed_worker_profile("worker-two")
    denied = await task_client.get(
        f"/api/v1/submissions/{second['id']}",
        headers=auth_headers(),
    )
    assert denied.status_code == 404


async def test_submission_uses_task_locked_context_after_new_guide_activation(
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
    activate_v2 = await task_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide_v2.json()['id']}/activate",
        headers=auth_headers(),
    )
    assert activate_v2.status_code == 200, activate_v2.text
    assert activate_v2.json()["guide"]["version"] == "v2"

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )

    assert response.status_code == 201, response.text
    submission = response.json()
    assert submission["locked_guide_version"] == "v1"
    assert submission["locked_checker_policy_version"] == "v1"
    task = await task_client.get(f"/api/v1/tasks/{started_task['id']}", headers=auth_headers())
    assert task.status_code == 200, task.text
    assert task.json()["locked_guide_version"] == "v1"


async def test_locked_submission_can_only_be_replaced_by_new_version(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    v1_payload = complete_submission_payload()
    v1_payload["artifact_hash_manifest"] = [
        {
            "artifact": "other.md",
            "hash": "sha256:other-v1",
            "size_bytes": 128,
            "notes": "missing required file so v1 needs revision",
        }
    ]
    v1 = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=v1_payload,
    )
    assert v1.status_code == 201, v1.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    locked_v1 = await task_client.post(
        f"/api/v1/submissions/{v1.json()['id']}/lock",
        headers=auth_headers(),
    )
    assert locked_v1.status_code == 200, locked_v1.text

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    v2_payload = complete_submission_payload("sha256:package-replacement")
    v2_payload["summary"] = "Replacement packet after locked v1."
    v2_payload["artifact_hash_manifest"][0]["hash"] = "sha256:replacement-artifact"
    v2 = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=v2_payload,
    )

    assert v2.status_code == 201, v2.text
    assert v2.json()["version"] == 2
    assert v2.json()["supersedes_submission_id"] == v1.json()["id"]
    fetched_v1 = await task_client.get(
        f"/api/v1/submissions/{v1.json()['id']}",
        headers=auth_headers(),
    )
    assert fetched_v1.status_code == 200, fetched_v1.text
    assert fetched_v1.json()["locked_at"] == locked_v1.json()["locked_at"]
    assert fetched_v1.json()["package_hash"] == "sha256:package-v1"
    assert fetched_v1.json()["artifact_hash_manifest"][0]["hash"] == "sha256:other-v1"


async def test_project_manager_cannot_submit_as_worker(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")

    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )

    assert response.status_code == 403


async def test_submission_rejects_nested_manifest_and_evidence_injection(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["artifact_hash_manifest"][0]["locked_guide_version"] = "v999"
    payload["evidence_items"][0]["submission_id"] = "attacker-controlled"

    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422


async def test_submission_rejects_signed_or_raw_external_uris(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["package_uri"] = "https://storage.example.test/package.tar?token=secret"

    signed_package_response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )

    assert signed_package_response.status_code == 422

    payload = complete_submission_payload()
    payload["evidence_items"][0]["uri"] = "file:///home/worker/private/evidence.log"
    raw_file_response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )

    assert raw_file_response.status_code == 422

    payload = complete_submission_payload()
    payload["package_uri"] = "local://"
    empty_reference_response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )

    assert empty_reference_response.status_code == 422

    payload = complete_submission_payload()
    payload["evidence_items"][0]["uri"] = "local://../private/evidence.log"
    traversal_response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )

    assert traversal_response.status_code == 422


async def test_submitted_task_rejects_earlier_lifecycle_actions_without_new_audit(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    submitted = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert submitted.status_code == 201, submitted.text
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
    assert claim.status_code == 409
    assert start.status_code == 409
    assert audit_after.status_code == 200, audit_after.text
    assert len(audit_after.json()) == len(audit_before.json())


async def test_concurrent_submission_posts_return_clean_version_outcomes(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)

    async def post_submission(package_hash: str) -> int:
        payload = complete_submission_payload(package_hash)
        response = await task_client.post(
            f"/api/v1/tasks/{started_task['id']}/submissions",
            headers=auth_headers(),
            json=payload,
        )
        return response.status_code

    statuses = await asyncio.gather(
        post_submission("sha256:concurrent-one"),
        post_submission("sha256:concurrent-two"),
    )
    listed = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
    )
    task = await task_client.get(f"/api/v1/tasks/{started_task['id']}", headers=auth_headers())

    assert set(statuses).issubset({201, 409})
    assert statuses.count(201) >= 1
    assert listed.status_code == 200, listed.text
    assert [submission["version"] for submission in listed.json()] == list(
        range(1, statuses.count(201) + 1)
    )
    assert task.status_code == 200, task.text
    assert task.json()["status"] == "submitted"


async def test_cross_worker_cannot_list_submissions_or_audit_after_submit(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    await seed_worker_profile("worker-two")
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
async def test_future_roles_cannot_view_week1_task_or_submissions(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
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
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    guide_v2 = await task_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=complete_guide_payload("v2"),
    )
    assert guide_v2.status_code == 201, guide_v2.text
    await create_policy_bundle_for_guide(task_client, project["id"], guide_v2.json()["id"])
    activate_v2 = await task_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide_v2.json()['id']}/activate",
        headers=auth_headers(),
    )
    assert activate_v2.status_code == 200, activate_v2.text

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.locked_guide_version = "v2"
        task.locked_checker_policy_version = "v2"
        task.locked_review_policy_version = "v2"
        task.locked_revision_policy_version = "v2"
        task.locked_payment_policy_version = "v2"
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_lock_submission_requires_operator_and_latest_version(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    v1 = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert v1.status_code == 201, v1.text
    premature_v2 = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload("sha256:package-v2"),
    )
    assert premature_v2.status_code == 409
    assert "in progress or needs revision" in premature_v2.json()["detail"]

    worker_lock = await task_client.post(
        f"/api/v1/submissions/{v1.json()['id']}/lock",
        headers=auth_headers(),
    )
    assert worker_lock.status_code == 403

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    locked = await task_client.post(
        f"/api/v1/submissions/{v1.json()['id']}/lock",
        headers=auth_headers(),
    )
    assert locked.status_code == 200, locked.text
    locked_body = locked.json()
    assert locked_body["locked_at"] is not None
    assert locked_body["evidence_items"][0]["locked_at"] == locked_body["locked_at"]

    second_lock = await task_client.post(
        f"/api/v1/submissions/{v1.json()['id']}/lock",
        headers=auth_headers(),
    )
    assert second_lock.status_code == 200, second_lock.text
    assert second_lock.json()["locked_at"] == locked_body["locked_at"]


async def test_database_enforces_unique_submission_version(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    body = created.json()

    async with db_session.get_session_factory()() as session:
        session.add(
            Submission(
                id=str(uuid4()),
                task_id=body["task_id"],
                worker_id=body["worker_id"],
                version=body["version"],
                status="submitted",
                summary="duplicate",
                package_hash="sha256:duplicate",
                artifact_hash_manifest=body["artifact_hash_manifest"],
                worker_attestation="duplicate",
                locked_guide_version=body["locked_guide_version"],
                locked_checker_policy_version=body["locked_checker_policy_version"],
                locked_review_policy_version=body["locked_review_policy_version"],
                locked_revision_policy_version=body["locked_revision_policy_version"],
                locked_payment_policy_version=body["locked_payment_policy_version"],
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


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


async def test_invalid_transitions_are_rejected(task_client: AsyncClient) -> None:
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])

    release_from_draft = await task_client.post(
        f"/api/v1/tasks/{task['id']}/release",
        headers=auth_headers(),
        json={"reason": "release"},
    )
    start_from_draft = await task_client.post(
        f"/api/v1/tasks/{task['id']}/start",
        headers=auth_headers(),
        json={"reason": "start"},
    )

    assert release_from_draft.status_code == 409
    assert start_from_draft.status_code == 409
    with pytest.raises(InvalidTaskTransition):
        ensure_allowed_transition("unknown", "ready")


async def test_database_enforces_one_active_assignment_per_task(task_client: AsyncClient) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])

    async with db_session.get_session_factory()() as session:
        session.add_all(
            [
                TaskAssignment(
                    id=str(uuid4()),
                    task_id=ready_task["id"],
                    worker_id="worker-1",
                    assigned_by="operator",
                    status="active",
                ),
                TaskAssignment(
                    id=str(uuid4()),
                    task_id=ready_task["id"],
                    worker_id="worker-2",
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

    async with db_session.get_session_factory()() as session:
        session.add_all(
            [
                TaskAssignment(
                    id=str(uuid4()),
                    task_id=ready_task["id"],
                    worker_id="worker-1",
                    assigned_by="operator",
                    status="released",
                ),
                TaskAssignment(
                    id=str(uuid4()),
                    task_id=ready_task["id"],
                    worker_id="worker-2",
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
    assert task.required_files == ["answer.md"]
    assert task.required_evidence == ["checker log"]
    assert task.source_payload_hash == "hash-123"
    assert task.base_amount == Decimal("25.00")
