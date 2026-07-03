from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
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
from app.core.hashing import canonical_json_hash
from app.db import models as db_models
from app.db import session as db_session
from app.db.base import Base
from app.main import create_app
from app.modules.tasks.lifecycle import InvalidTaskTransition, ensure_allowed_transition
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    PostSubmitCheckerPolicy,
    PreSubmitCheckerPolicy,
    SubmissionArtifactPolicy,
)
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
        "post_submit_checker_policy": {
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
                "metadata": {"command": "pytest", "policy_key": "checker_log"},
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


def test_submission_create_openapi_documents_domain_error() -> None:
    schema = create_app().openapi()
    responses = schema["paths"]["/api/v1/tasks/{task_id}/submissions"]["post"]["responses"]
    response_422 = responses["422"]["content"]["application/json"]["schema"]

    assert {"$ref": "#/components/schemas/HTTPValidationError"} in response_422["oneOf"]
    domain_schema = next(option for option in response_422["oneOf"] if "properties" in option)
    assert domain_schema["properties"]["code"]["enum"] == ["pre_submission_checker_failed"]
    assert "details" in domain_schema["properties"]


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
    assert "locked_guide_version" not in task
    assert task["skill_tags"] == ["stem", "proofs"]
    assert task["source_ref"] == "local-ticket-1"


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


async def test_screening_maps_ambiguous_active_policy_context_to_controlled_error(
    task_client: AsyncClient,
) -> None:
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])

    async with db_session.get_session_factory()() as session:
        approved_policy = await session.scalar(
            select(SubmissionArtifactPolicy).where(
                SubmissionArtifactPolicy.project_id == project["id"],
                SubmissionArtifactPolicy.guide_version == "v1",
                SubmissionArtifactPolicy.lifecycle_status == "approved",
            )
        )
        assert approved_policy is not None
        session.add(
            SubmissionArtifactPolicy(
                id=str(uuid4()),
                project_id=approved_policy.project_id,
                guide_id=approved_policy.guide_id,
                guide_version=approved_policy.guide_version,
                source_snapshot_id=approved_policy.source_snapshot_id,
                source_snapshot_hash=approved_policy.source_snapshot_hash,
                policy_version="ambiguous-v2",
                lifecycle_status="approved",
                policy_body=approved_policy.policy_body,
                policy_hash=sha256_hash("ambiguous-approved-policy"),
                derivation_source="manual_import",
                source_material_refs=approved_policy.source_material_refs,
                created_by="test",
                approved_by_role="project_manager",
                approved_by_actor=actor_id("project-manager-subject"),
                approved_at=datetime.now(UTC),
                change_summary="Creates an ambiguous approved policy state for screening.",
            )
        )
        await session.commit()

    response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screen"},
    )

    assert response.status_code == 422
    assert "ambiguous" in response.json()["detail"]


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
    assert "locked_checker_policy_version" not in body
    assert body["locked_review_policy_version"] == "v1"
    assert body["locked_revision_policy_version"] == "v1"
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
    assert persisted_task is not None
    assert persisted_task.locked_post_submit_checker_policy_id == expected_post_submit_policy["id"]
    assert persisted_task.locked_post_submit_checker_policy_version == "v1"
    assert (
        persisted_task.locked_post_submit_checker_policy_hash
        == expected_post_submit_policy["policy_hash"]
    )
    assert body["base_amount"] == "25.00"
    assert body["currency"] == "USD"
    assert body["payout_type"] == "fixed"


async def test_screening_uses_persisted_post_submit_policy_body_after_default_drift(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.projects import post_submit_policy as post_submit_policy_module

    project = await create_active_project(task_client)
    async with db_session.get_session_factory()() as session:
        source_policy = await session.scalar(
            select(PostSubmitCheckerPolicy).where(
                PostSubmitCheckerPolicy.project_id == project["id"],
                PostSubmitCheckerPolicy.guide_version == "v1",
            )
        )
        assert source_policy is not None
        persisted_body = dict(source_policy.policy_body or {})

    monkeypatch.setattr(
        post_submit_policy_module,
        "DEFAULT_DURABLE_CHECKERS",
        [
            *post_submit_policy_module.DEFAULT_DURABLE_CHECKERS,
            "check_acceptance_criteria_present",
        ],
    )
    task = await create_draft_task(task_client, project["id"])

    response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screen"},
    )

    assert response.status_code == 200, response.text
    async with db_session.get_session_factory()() as session:
        persisted_task = await session.get(WorkstreamTask, task["id"])
    assert persisted_task is not None
    assert persisted_task.locked_post_submit_checker_policy_body == persisted_body
    assert "check_acceptance_criteria_present" not in (
        persisted_task.locked_post_submit_checker_policy_body or {}
    )["execution_checkers"]


async def test_release_uses_locked_post_submit_policy_body_after_setup_mutation(
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
        await session.commit()

    release = await task_client.post(
        f"/api/v1/tasks/{task['id']}/release",
        headers=auth_headers(),
        json={"reason": "release decision recorded"},
    )

    assert release.status_code == 200, release.text
    assert release.json()["status"] == "ready"
    async with db_session.get_session_factory()() as session:
        persisted_task = await session.get(WorkstreamTask, task["id"])
    assert persisted_task is not None
    assert persisted_task.status == "ready"
    assert persisted_task.locked_post_submit_checker_policy_body == locked_body
    assert "check_acceptance_criteria_present" not in locked_body["required_checkers"]
    assert "check_acceptance_criteria_present" not in locked_body["execution_checkers"]
    assert "check_required_files" in locked_body["default_checkers"]
    assert "check_required_files" in locked_body["execution_checkers"]


async def test_worker_task_response_redacts_locked_policy_hashes(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    operator_response = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}",
        headers=auth_headers(),
    )

    assert operator_response.status_code == 200, operator_response.text
    assert "locked_checker_policy_version" not in operator_response.json()

    await seed_worker_profile("worker-one")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")

    response = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}",
        headers=auth_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert "locked_checker_policy_version" not in body
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
    ):
        assert internal_field not in body


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


async def test_submission_runtime_uses_locked_project_policy_not_task_required_fields(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    conflicting_task_payload = complete_task_payload()
    conflicting_task_payload["required_files"] = ["legacy-only.md"]
    conflicting_task_payload["required_evidence"] = ["legacy evidence"]

    project_policy_task = await create_started_task(
        task_client,
        project["id"],
        monkeypatch,
        "worker-one",
        conflicting_task_payload,
    )
    project_policy_response = await task_client.post(
        f"/api/v1/tasks/{project_policy_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert project_policy_response.status_code == 201, project_policy_response.text

    legacy_only_task = await create_started_task(
        task_client,
        project["id"],
        monkeypatch,
        "worker-two",
        conflicting_task_payload,
    )
    legacy_only_payload = complete_submission_payload("sha256:legacy-package")
    legacy_only_payload["artifact_hash_manifest"] = [
        {
            "artifact": "legacy-only.md",
            "hash": "sha256:legacy-only-v1",
            "size_bytes": 128,
            "notes": "matches transitional task field only",
        }
    ]
    legacy_only_response = await task_client.post(
        f"/api/v1/tasks/{legacy_only_task['id']}/submissions",
        headers=auth_headers(),
        json=legacy_only_payload,
    )

    assert legacy_only_response.status_code == 422, legacy_only_response.text
    detail = legacy_only_response.json()
    assert detail["code"] == "pre_submission_checker_failed"
    required_files = next(
        result
        for result in detail["details"]["results"]
        if result["checker_name"] == "check_required_files"
    )
    assert required_files["status"] == "failed"

    legacy_evidence_task = await create_started_task(
        task_client,
        project["id"],
        monkeypatch,
        "worker-three",
        conflicting_task_payload,
    )
    legacy_evidence_payload = complete_submission_payload("sha256:legacy-evidence-package")
    legacy_evidence_payload["artifact_hash_manifest"][0]["hash"] = "sha256:answer-legacy-evidence"
    legacy_evidence_payload["evidence_items"] = [
        {
            "type": "note",
            "label": "legacy evidence",
            "uri": "local://evidence/legacy-evidence.txt",
            "hash": "sha256:legacy-evidence-v1",
            "size_bytes": 128,
            "metadata": {"policy_key": "legacy_evidence"},
        }
    ]
    legacy_evidence_response = await task_client.post(
        f"/api/v1/tasks/{legacy_evidence_task['id']}/submissions",
        headers=auth_headers(),
        json=legacy_evidence_payload,
    )

    assert legacy_evidence_response.status_code == 422, legacy_evidence_response.text
    detail = legacy_evidence_response.json()
    assert detail["code"] == "pre_submission_checker_failed"
    required_evidence = next(
        result
        for result in detail["details"]["results"]
        if result["checker_name"] == "check_evidence_present"
    )
    assert required_evidence["status"] == "failed"


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
        assert "locked_checker_policy_version" not in event["event_payload"]
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
    assert "locked_checker_policy_version" not in submission
    for internal_field in (
        "package_uri",
        "package_hash",
        "artifact_hash_manifest",
        "worker_attestation",
        "locked_guide_version",
        "locked_review_policy_version",
        "locked_revision_policy_version",
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
    assert "package_hash" not in submission_event["event_payload"]
    assert "artifact_hash_manifest" not in submission_event["event_payload"]
    assert "locked_guide_source_snapshot_id" not in submission_event["event_payload"]
    assert "locked_guide_source_snapshot_hash" not in submission_event["event_payload"]
    assert "locked_effective_project_submission_artifact_policy_hash" not in (
        submission_event["event_payload"]
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
            "locked_post_submit_checker_policy_id": "malicious",
            "locked_post_submit_checker_policy_version": "malicious",
            "locked_post_submit_checker_policy_hash": "sha256:" + "0" * 64,
            "locked_post_submit_checker_policy_body": {"required_checkers": []},
            "locked_review_policy_version": "malicious",
            "locked_revision_policy_version": "malicious",
            "locked_payment_policy_version": "malicious",
            "locked_guide_source_snapshot_id": "malicious",
            "locked_guide_source_snapshot_hash": "sha256:" + "0" * 64,
            "locked_effective_project_submission_artifact_policy_id": "malicious",
            "locked_effective_project_submission_artifact_policy_hash": "sha256:" + "0" * 64,
            "locked_pre_submit_checker_policy_id": "malicious",
            "locked_pre_submit_checker_bundle_hash": "sha256:" + "0" * 64,
            "runtime_parameters": {"required_artifacts": []},
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


async def test_submission_pre_submit_failure_returns_structured_domain_error(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["evidence_items"] = []
    async with db_session.get_session_factory()() as session:
        audit_ids_before = {
            event.id
            for event in (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.entity_type == "task",
                        AuditEvent.entity_id == started_task["id"],
                    )
                )
            ).scalars()
        }

    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422
    detail = response.json()
    assert detail["code"] == "pre_submission_checker_failed"
    assert detail["details"]["status"] == "failed"
    assert detail["details"]["eligible_to_submit"] is False
    evidence_result = next(
        result
        for result in detail["details"]["results"]
        if result["checker_name"] == "check_evidence_present"
    )
    assert evidence_result["status"] == "failed"

    async with db_session.get_session_factory()() as session:
        submissions = (
            await session.execute(select(Submission).where(Submission.task_id == started_task["id"]))
        ).scalars().all()
        audit_events = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "task",
                    AuditEvent.entity_id == started_task["id"],
                )
            )
        ).scalars().all()
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
        task = await session.get(WorkstreamTask, started_task["id"])
    assert submissions == []
    assert {event.id for event in audit_events} == audit_ids_before
    assert checker_runs == []
    assert task is not None
    assert task.status == "in_progress"


async def test_submission_pre_submit_requires_specific_evidence_key(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["evidence_items"] = [
        {
            "type": "note",
            "label": "unrelated evidence",
            "uri": "local://evidence/unrelated.txt",
            "hash": "sha256:unrelated-v1",
            "size_bytes": 64,
            "metadata": {"policy_key": "other_evidence"},
        }
    ]

    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422, response.text
    detail = response.json()
    assert detail["code"] == "pre_submission_checker_failed"
    evidence_result = next(
        result
        for result in detail["details"]["results"]
        if result["checker_name"] == "check_evidence_present"
    )
    assert evidence_result["status"] == "failed"
    assert evidence_result["would_block_if_submitted"] is True
    assert "required evidence" in evidence_result["worker_message"]

    async with db_session.get_session_factory()() as session:
        submissions = (
            await session.execute(select(Submission).where(Submission.task_id == started_task["id"]))
        ).scalars().all()
    assert submissions == []


async def test_submission_pre_submit_requires_project_attestation_terms(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["worker_attestation"] = (
        "I attest this submission contains no confidential client data, credentials, secrets, "
        "tokens, passwords, API keys, private source material, source code, copied platform "
        "artifacts, or copied platform content."
    )

    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 422, response.text
    detail = response.json()
    assert detail["code"] == "pre_submission_checker_failed"
    attestation_result = next(
        result
        for result in detail["details"]["results"]
        if result["checker_name"] == "check_confidentiality_attestation"
    )
    assert attestation_result["status"] == "failed"
    assert attestation_result["would_block_if_submitted"] is True
    assert "confidentiality attestation" in attestation_result["worker_message"]

    async with db_session.get_session_factory()() as session:
        submissions = (
            await session.execute(select(Submission).where(Submission.task_id == started_task["id"]))
        ).scalars().all()
    assert submissions == []


async def test_submission_pre_submit_rejects_mutated_effective_policy_body(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        effective_policy = await session.get(
            EffectiveProjectSubmissionArtifactPolicy,
            task.locked_effective_project_submission_artifact_policy_id,
        )
        assert effective_policy is not None
        effective_policy.effective_policy = {
            **effective_policy.effective_policy,
            "required_evidence": [],
        }
        await session.commit()

    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )

    assert response.status_code == 422, response.text
    assert "locked effective project submission policy" in response.json()["detail"]

    async with db_session.get_session_factory()() as session:
        submissions = (
            await session.execute(select(Submission).where(Submission.task_id == started_task["id"]))
        ).scalars().all()
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
    assert submissions == []
    assert checker_runs == []


async def test_submission_pre_submit_rejects_hash_consistent_malformed_effective_policy(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    async with db_session.get_session_factory()() as session:
        effective_policy = await session.scalar(
            select(EffectiveProjectSubmissionArtifactPolicy).where(
                EffectiveProjectSubmissionArtifactPolicy.project_id == project["id"],
                EffectiveProjectSubmissionArtifactPolicy.guide_version == "v1",
                EffectiveProjectSubmissionArtifactPolicy.lifecycle_status == "approved",
            )
        )
        assert effective_policy is not None
        pre_submit_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == effective_policy.id,
                PreSubmitCheckerPolicy.lifecycle_status == "compiled",
            )
        )
        assert pre_submit_policy is not None
        replacement_bundle = dict(pre_submit_policy.compiled_bundle)
        replacement_checker_names = list(pre_submit_policy.checker_names)
        replacement_checker_configs = dict(pre_submit_policy.checker_configs)
        compiler_version = pre_submit_policy.compiler_version
        await session.delete(pre_submit_policy)
        await session.flush()

        malformed_policy_body = {
            **effective_policy.effective_policy,
            "required_evidence": ["bad-shape"],
        }
        malformed_policy_hash = canonical_json_hash(malformed_policy_body)
        effective_policy.effective_policy = malformed_policy_body
        effective_policy.effective_policy_hash = malformed_policy_hash

        replacement_bundle["effective_policy_hash"] = malformed_policy_hash
        replacement_bundle_hash = canonical_json_hash(replacement_bundle)
        session.add(
            PreSubmitCheckerPolicy(
                id=str(uuid4()),
                project_id=effective_policy.project_id,
                guide_id=effective_policy.guide_id,
                guide_version=effective_policy.guide_version,
                source_snapshot_id=effective_policy.source_snapshot_id,
                source_snapshot_hash=effective_policy.source_snapshot_hash,
                effective_policy_id=effective_policy.id,
                effective_policy_hash=malformed_policy_hash,
                lifecycle_status="compiled",
                compiler_version=compiler_version,
                compiled_bundle=replacement_bundle,
                compiled_bundle_hash=replacement_bundle_hash,
                checker_names=replacement_checker_names,
                checker_configs=replacement_checker_configs,
                created_by="test",
            )
        )
        await session.commit()

    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )

    assert response.status_code == 422, response.text
    assert "locked effective project submission policy" in response.json()["detail"]

    async with db_session.get_session_factory()() as session:
        submissions = (
            await session.execute(select(Submission).where(Submission.task_id == started_task["id"]))
        ).scalars().all()
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
    assert submissions == []
    assert checker_runs == []


async def test_submission_pre_submit_rejects_hash_consistent_malformed_packaging_policy(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    async with db_session.get_session_factory()() as session:
        effective_policy = await session.scalar(
            select(EffectiveProjectSubmissionArtifactPolicy).where(
                EffectiveProjectSubmissionArtifactPolicy.project_id == project["id"],
                EffectiveProjectSubmissionArtifactPolicy.guide_version == "v1",
                EffectiveProjectSubmissionArtifactPolicy.lifecycle_status == "approved",
            )
        )
        assert effective_policy is not None
        pre_submit_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == effective_policy.id,
                PreSubmitCheckerPolicy.lifecycle_status == "compiled",
            )
        )
        assert pre_submit_policy is not None
        replacement_bundle = dict(pre_submit_policy.compiled_bundle)
        replacement_checker_names = list(pre_submit_policy.checker_names)
        replacement_checker_configs = dict(pre_submit_policy.checker_configs)
        compiler_version = pre_submit_policy.compiler_version
        await session.delete(pre_submit_policy)
        await session.flush()

        malformed_policy_body = {
            **effective_policy.effective_policy,
            "packaging": {"package_required": "yes", "allowed_package_formats": "zip"},
        }
        malformed_policy_hash = canonical_json_hash(malformed_policy_body)
        effective_policy.effective_policy = malformed_policy_body
        effective_policy.effective_policy_hash = malformed_policy_hash

        replacement_bundle["effective_policy_hash"] = malformed_policy_hash
        replacement_bundle_hash = canonical_json_hash(replacement_bundle)
        session.add(
            PreSubmitCheckerPolicy(
                id=str(uuid4()),
                project_id=effective_policy.project_id,
                guide_id=effective_policy.guide_id,
                guide_version=effective_policy.guide_version,
                source_snapshot_id=effective_policy.source_snapshot_id,
                source_snapshot_hash=effective_policy.source_snapshot_hash,
                effective_policy_id=effective_policy.id,
                effective_policy_hash=malformed_policy_hash,
                lifecycle_status="compiled",
                compiler_version=compiler_version,
                compiled_bundle=replacement_bundle,
                compiled_bundle_hash=replacement_bundle_hash,
                checker_names=replacement_checker_names,
                checker_configs=replacement_checker_configs,
                created_by="test",
            )
        )
        await session.commit()

    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )

    assert response.status_code == 422, response.text
    assert "locked effective project submission policy" in response.json()["detail"]

    async with db_session.get_session_factory()() as session:
        submissions = (
            await session.execute(select(Submission).where(Submission.task_id == started_task["id"]))
        ).scalars().all()
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
    assert submissions == []
    assert checker_runs == []


async def test_submission_pre_submit_rejects_mutated_compiled_checker_bundle(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        pre_submit_policy = await session.get(
            PreSubmitCheckerPolicy,
            task.locked_pre_submit_checker_policy_id,
        )
        assert pre_submit_policy is not None
        pre_submit_policy.compiled_bundle = {
            **pre_submit_policy.compiled_bundle,
            "effective_policy_hash": "sha256:" + "0" * 64,
        }
        await session.commit()

    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )

    assert response.status_code == 422, response.text
    assert "locked project pre-submit checker policy" in response.json()["detail"]

    async with db_session.get_session_factory()() as session:
        submissions = (
            await session.execute(select(Submission).where(Submission.task_id == started_task["id"]))
        ).scalars().all()
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
    assert submissions == []
    assert checker_runs == []


async def test_submission_pre_submit_rejects_hash_consistent_incomplete_checker_bundle(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    async with db_session.get_session_factory()() as session:
        effective_policy = await session.scalar(
            select(EffectiveProjectSubmissionArtifactPolicy).where(
                EffectiveProjectSubmissionArtifactPolicy.project_id == project["id"],
                EffectiveProjectSubmissionArtifactPolicy.guide_version == "v1",
                EffectiveProjectSubmissionArtifactPolicy.lifecycle_status == "approved",
            )
        )
        assert effective_policy is not None
        pre_submit_policy = await session.scalar(
            select(PreSubmitCheckerPolicy).where(
                PreSubmitCheckerPolicy.effective_policy_id == effective_policy.id,
                PreSubmitCheckerPolicy.lifecycle_status == "compiled",
            )
        )
        assert pre_submit_policy is not None
        replacement_bundle = {
            **pre_submit_policy.compiled_bundle,
            "rules": [
                rule
                for rule in pre_submit_policy.compiled_bundle["rules"]
                if rule["primitive"] != "require_file"
            ],
        }
        replacement_bundle_hash = canonical_json_hash(replacement_bundle)
        pre_submit_policy.compiled_bundle = replacement_bundle
        pre_submit_policy.compiled_bundle_hash = replacement_bundle_hash
        await session.commit()

    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )

    assert response.status_code == 422, response.text
    assert "locked project pre-submit checker policy" in response.json()["detail"]

    async with db_session.get_session_factory()() as session:
        submissions = (
            await session.execute(select(Submission).where(Submission.task_id == started_task["id"]))
        ).scalars().all()
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
    assert submissions == []
    assert checker_runs == []


async def test_submission_pre_submit_checker_setup_error_is_controlled(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        pre_submit_policy = await session.get(
            PreSubmitCheckerPolicy,
            task.locked_pre_submit_checker_policy_id,
        )
        assert pre_submit_policy is not None
        pre_submit_policy.checker_names = ["unknown_project_checker"]
        await session.commit()

    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )

    assert response.status_code == 422, response.text
    assert "locked project pre-submit checker" in response.json()["detail"]

    async with db_session.get_session_factory()() as session:
        submissions = (
            await session.execute(select(Submission).where(Submission.task_id == started_task["id"]))
        ).scalars().all()
    assert submissions == []


async def test_submission_uses_locked_post_submit_policy_body_after_setup_mutation(
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
        await session.commit()

    response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )

    assert response.status_code == 201, response.text

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        submissions = (
            await session.execute(select(Submission).where(Submission.task_id == started_task["id"]))
        ).scalars().all()
        checker_runs = (await session.execute(select(db_models.CheckerRun))).scalars().all()
    assert task is not None
    assert task.status == "submitted"
    assert len(submissions) == 1
    assert submissions[0].locked_post_submit_checker_policy_body == locked_body
    assert "check_acceptance_criteria_present" not in locked_body["required_checkers"]
    assert "check_acceptance_criteria_present" not in locked_body["execution_checkers"]
    assert "check_required_files" in locked_body["default_checkers"]
    assert "check_required_files" in locked_body["execution_checkers"]
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
            await session.execute(select(Submission).where(Submission.task_id == started_task["id"]))
        ).scalars().all()
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
            worker_id=actor_id("worker-one"),
            version=1,
            status="submitted",
            summary="Bypass submission without post-submit policy provenance.",
            package_hash="sha256:package-bypass",
            artifact_hash_manifest=[{"artifact": "answer.md", "hash": "sha256:answer-bypass"}],
            worker_attestation="Bypass attestation.",
            locked_guide_version=task.locked_guide_version,
            locked_checker_policy_version=task.locked_checker_policy_version,
            locked_post_submit_checker_policy_id=None,
            locked_post_submit_checker_policy_version=None,
            locked_post_submit_checker_policy_hash=None,
            locked_post_submit_checker_policy_body=None,
            locked_review_policy_version=task.locked_review_policy_version,
            locked_revision_policy_version=task.locked_revision_policy_version,
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
    submission_response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert submission_response.status_code == 201, submission_response.text
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        submission = await session.get(Submission, submission_response.json()["id"])
        assert task is not None
        assert submission is not None
        checker_run = db_models.CheckerRun(
            id=str(uuid4()),
            task_id=task.id,
            submission_id=submission.id,
            submission_version=submission.version,
            trigger_source="submission_locked",
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
            locked_checker_policy_version=submission.locked_checker_policy_version,
            locked_post_submit_checker_policy_id=None,
            locked_post_submit_checker_policy_version=None,
            locked_post_submit_checker_policy_hash=None,
            locked_post_submit_checker_policy_body=None,
            locked_review_policy_version=submission.locked_review_policy_version,
            locked_revision_policy_version=submission.locked_revision_policy_version,
            locked_payment_policy_version=submission.locked_payment_policy_version,
            package_hash=submission.package_hash,
            artifact_hash_manifest=submission.artifact_hash_manifest,
            artifact_manifest_hash=canonical_json_hash(submission.artifact_hash_manifest),
        )
        session.add(checker_run)
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_submission_versioning_creates_new_rows_and_preserves_v1(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    v1_payload = complete_submission_payload()
    v1 = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=v1_payload,
    )
    assert v1.status_code == 201, v1.text
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.status = "needs_revision"
        await session.commit()
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
    assert "locked_checker_policy_version" not in submission
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


async def test_locked_submission_can_only_be_replaced_by_new_version(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    started_task = await create_started_task(task_client, project["id"], monkeypatch)
    v1_payload = complete_submission_payload()
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
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.status = "needs_revision"
        await session.commit()

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
    assert "package_hash" not in fetched_v1.json()
    assert "artifact_hash_manifest" not in fetched_v1.json()
    async with db_session.get_session_factory()() as session:
        persisted_v1 = await session.get(Submission, v1.json()["id"])
    assert persisted_v1 is not None
    assert persisted_v1.package_hash == "sha256:package-v1"
    assert persisted_v1.artifact_hash_manifest[0]["hash"] == "sha256:answer-v1"


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
        persisted = await session.get(Submission, body["id"])
        assert persisted is not None
        session.add(
            Submission(
                id=str(uuid4()),
                task_id=body["task_id"],
                worker_id=body["worker_id"],
                version=body["version"],
                status="submitted",
                summary="duplicate",
                package_hash=persisted.package_hash,
                artifact_hash_manifest=persisted.artifact_hash_manifest,
                worker_attestation=persisted.worker_attestation,
                locked_guide_version=persisted.locked_guide_version,
                locked_checker_policy_version=persisted.locked_checker_policy_version,
                locked_post_submit_checker_policy_id=(
                    persisted.locked_post_submit_checker_policy_id
                ),
                locked_post_submit_checker_policy_version=(
                    persisted.locked_post_submit_checker_policy_version
                ),
                locked_post_submit_checker_policy_hash=(
                    persisted.locked_post_submit_checker_policy_hash
                ),
                locked_post_submit_checker_policy_body=(
                    persisted.locked_post_submit_checker_policy_body
                ),
                locked_review_policy_version=persisted.locked_review_policy_version,
                locked_revision_policy_version=persisted.locked_revision_policy_version,
                locked_payment_policy_version=persisted.locked_payment_policy_version,
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
