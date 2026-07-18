from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import CreateIndex

from app.adapters.auth.dev import actor_id_from_external_identity
from app.core.config import get_settings
from app.core.hashing import canonical_json_hash
from app.core.permissions import PermissionDenied
from app.db import models as db_models
from app.db import session as db_session
from app.db.base import Base
from app.main import create_app
from app.modules.actors.models import (
    ActorIdentityLink,
    ActorProfile,
    LegacyActorIdentity,
    LegacyWorkflowEligibility,
)
from app.modules.actors.schemas import LegacyWorkflowEligibilityActivationRequest
from app.modules.actors.service import ActorService
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    GuideSourceSnapshot,
    PaymentPolicy,
    PostSubmitCheckerPolicy,
    PreSubmitCheckerPolicy,
    ProjectSetupRun,
    ReviewPolicy,
    RevisionPolicy,
    SubmissionArtifactPolicy,
)
from app.modules.projects.post_submit_policy import (
    build_project_post_submit_checker_spec,
    compile_project_post_submit_checker_spec,
)
from app.modules.tasks.lifecycle import InvalidTaskTransition, ensure_allowed_transition
from app.modules.tasks.models import (
    AuditEvent,
    EvidenceItem,
    Submission,
    TaskAssignment,
    WorkstreamTask,
)
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.service import TaskService, TaskServiceError
from app.schemas.auth import ActorContext


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
    repository._audit_repository.list_audit_events.assert_awaited_once_with(
        "task", "task-1"
    )


async def delete_audit_fixture_as_owner(session: AsyncSession, event_id: str) -> None:
    """Construct missing-evidence corruption under explicit test-owner custody."""
    await session.execute(text("lock table audit_events in access exclusive mode"))
    await session.execute(
        text(
            "alter table audit_events disable trigger "
            "audit_events_reject_update_delete"
        )
    )
    await session.execute(
        text("delete from audit_events where id = :event_id"),
        {"event_id": event_id},
    )
    await session.execute(
        text(
            "alter table audit_events enable trigger "
            "audit_events_reject_update_delete"
        )
    )
    await session.commit()


@pytest.fixture
def task_database_env(
    monkeypatch: pytest.MonkeyPatch,
    postgres_database_url: str,
    migration_lock,
    reset_test_database_state,
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", postgres_database_url)
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    monkeypatch.setenv(
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET",
        "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
    )
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    get_settings.cache_clear()
    asyncio.run(db_session.dispose_engine())

    config = alembic_config()
    try:
        with migration_lock():
            command.downgrade(config, "base")
            try:
                command.upgrade(config, "head")
                yield postgres_database_url
            finally:
                try:
                    asyncio.run(reset_test_database_state(postgres_database_url))
                finally:
                    try:
                        asyncio.run(db_session.dispose_engine())
                    finally:
                        command.downgrade(config, "base")
    finally:
        try:
            asyncio.run(db_session.dispose_engine())
        finally:
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
    monkeypatch.setenv("WORKSTREAM_PROJECT_SETUP_PIPELINE_AUTOSTART", "false")
    get_settings.cache_clear()


def actor_id(subject: str, issuer: str = "flow-test") -> str:
    return actor_id_from_external_identity(issuer, subject)


async def fetch_legacy_actor_rows(
    subject: str,
    issuer: str = "flow-test",
) -> tuple[LegacyActorIdentity | None, list[LegacyWorkflowEligibility]]:
    """Load non-authoritative compatibility rows for assertions."""
    expected_actor_id = actor_id(subject, issuer)
    async with db_session.get_session_factory()() as session:
        identity = await session.get(LegacyActorIdentity, expected_actor_id)
        profiles = (
            await session.scalars(
                select(LegacyWorkflowEligibility)
                .where(LegacyWorkflowEligibility.actor_id == expected_actor_id)
                .order_by(
                    LegacyWorkflowEligibility.profile_type.asc(),
                    LegacyWorkflowEligibility.scope_type.asc(),
                )
            )
        ).all()
    return identity, list(profiles)


def complete_guide_payload(version: str = "v1") -> dict:
    return {
        "version": version,
        "content_markdown": (
            f"# Task Guide {version}\n\n"
            "Workers submit complete task packets with artifact hashes, evidence "
            "references, and attestations. The project policy bundle controls "
            "submission intake while the guide gives human review context."
        ),
        "change_summary": f"Initial {version}",
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


async def create_generated_post_submit_setup_output(
    *,
    project_id: str,
    guide_id: str,
    source_snapshot: dict,
    sufficiency_report: dict,
    submission_artifact_policy: dict,
    pre_submit_checker_policy: dict,
    required_checkers: list[str] | None = None,
    warning_checkers: list[str] | None = None,
    blocking_severities: list[str] | None = None,
) -> dict:
    """Persist approved generated post-submit setup output for task tests."""
    async with db_session.get_session_factory()() as session:
        snapshot = await session.get(GuideSourceSnapshot, source_snapshot["id"])
        assert snapshot is not None
        spec = build_project_post_submit_checker_spec(
            project_id=project_id,
            guide_version=snapshot.guide_version,
            required_checkers=(
                ["check_policy_context_present"] if required_checkers is None else required_checkers
            ),
            warning_checkers=[] if warning_checkers is None else warning_checkers,
            blocking_severities=blocking_severities,
        )
        compiled = compile_project_post_submit_checker_spec(
            project_id=project_id,
            guide_version=snapshot.guide_version,
            spec=spec,
        )
        post_submit_policy = PostSubmitCheckerPolicy(
            id=str(uuid4()),
            project_id=project_id,
            guide_id=guide_id,
            guide_version=snapshot.guide_version,
            source_snapshot_id=snapshot.id,
            source_snapshot_hash=snapshot.bundle_hash,
            effective_policy_id=pre_submit_checker_policy["effective_policy_id"],
            effective_policy_hash=pre_submit_checker_policy["effective_policy_hash"],
            pre_submit_checker_policy_id=pre_submit_checker_policy["id"],
            pre_submit_checker_bundle_hash=pre_submit_checker_policy["compiled_bundle_hash"],
            required_checkers=compiled.required_checkers,
            warning_checkers=compiled.warning_checkers,
            blocking_severities=compiled.blocking_severities,
            policy_hash=compiled.policy_hash,
            policy_body=compiled.policy_body,
            lifecycle_status="approved",
            approved_by_role="project_manager",
            approved_by_actor="project-manager-subject",
            approved_at=datetime.now(UTC),
            created_by="project-manager-subject",
        )
        setup_run = ProjectSetupRun(
            id=str(uuid4()),
            project_id=project_id,
            guide_id=guide_id,
            guide_version=snapshot.guide_version,
            source_snapshot_id=snapshot.id,
            source_snapshot_hash=snapshot.bundle_hash,
            status="post_submit_policy_compiled",
            current_step="post_submit_checker_policy_compilation",
            output_sufficiency_report_id=sufficiency_report["id"],
            output_submission_artifact_policy_id=submission_artifact_policy["id"],
            output_post_submit_checker_policy_id=post_submit_policy.id,
            post_submit_derivation_summary={
                "status": "compiled",
                "post_submit_checker_policy_id": post_submit_policy.id,
                "required_checkers": post_submit_policy.required_checkers,
                "warning_checkers": post_submit_policy.warning_checkers,
                "blocking_severities": post_submit_policy.blocking_severities,
            },
            created_by="project-manager-subject",
        )
        session.add(post_submit_policy)
        session.add(setup_run)
        await session.commit()
        return {
            "id": post_submit_policy.id,
            "policy_hash": post_submit_policy.policy_hash,
            "policy_body": post_submit_policy.policy_body,
        }


async def delete_generated_post_submit_output_for_pre_submit(
    session,
    pre_submit_checker_policy_id: str,
) -> None:
    """Remove generated post-submit output before test-only pre-submit corruption."""
    post_submit_policy = await session.scalar(
        select(PostSubmitCheckerPolicy).where(
            PostSubmitCheckerPolicy.pre_submit_checker_policy_id
            == pre_submit_checker_policy_id
        )
    )
    if post_submit_policy is None:
        return
    setup_runs = (
        await session.scalars(
            select(ProjectSetupRun).where(
                ProjectSetupRun.output_post_submit_checker_policy_id == post_submit_policy.id
            )
        )
    ).all()
    for setup_run in setup_runs:
        await session.delete(setup_run)
    await session.flush()
    await session.delete(post_submit_policy)
    await session.flush()


def generated_post_submit_output_for_pre_submit(
    *,
    effective_policy: EffectiveProjectSubmissionArtifactPolicy,
    pre_submit_checker_policy_id: str,
    pre_submit_checker_bundle_hash: str,
) -> PostSubmitCheckerPolicy:
    """Build generated post-submit output matching a test-only pre-submit row."""
    spec = build_project_post_submit_checker_spec(
        project_id=effective_policy.project_id,
        guide_version=effective_policy.guide_version,
        required_checkers=["check_policy_context_present"],
        warning_checkers=[],
        blocking_severities=["critical", "high"],
    )
    compiled = compile_project_post_submit_checker_spec(
        project_id=effective_policy.project_id,
        guide_version=effective_policy.guide_version,
        spec=spec,
    )
    return PostSubmitCheckerPolicy(
        id=str(uuid4()),
        project_id=effective_policy.project_id,
        guide_id=effective_policy.guide_id,
        guide_version=effective_policy.guide_version,
        source_snapshot_id=effective_policy.source_snapshot_id,
        source_snapshot_hash=effective_policy.source_snapshot_hash,
        effective_policy_id=effective_policy.id,
        effective_policy_hash=effective_policy.effective_policy_hash,
        pre_submit_checker_policy_id=pre_submit_checker_policy_id,
        pre_submit_checker_bundle_hash=pre_submit_checker_bundle_hash,
        required_checkers=compiled.required_checkers,
        warning_checkers=compiled.warning_checkers,
        blocking_severities=compiled.blocking_severities,
        policy_hash=compiled.policy_hash,
        policy_body=compiled.policy_body,
        lifecycle_status="approved",
        approved_by_role="project_manager",
        approved_by_actor="project-manager-subject",
        approved_at=datetime.now(UTC),
        created_by="project-manager-subject",
    )


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
    policy_body: dict | None = None,
    *,
    post_submit_required_checkers: list[str] | None = None,
    post_submit_warning_checkers: list[str] | None = None,
    post_submit_blocking_severities: list[str] | None = None,
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
            "policy_body": policy_body or policy_body_for_task_tests(),
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
    effective_policy = effective_response.json()
    compiled_pre_submit_checker = await load_pre_submit_checker_policy(effective_policy)
    post_submit_checker_policy = await create_generated_post_submit_setup_output(
        project_id=project_id,
        guide_id=guide_id,
        source_snapshot=snapshot,
        sufficiency_report=report_response.json(),
        submission_artifact_policy=policy,
        pre_submit_checker_policy=compiled_pre_submit_checker,
        required_checkers=post_submit_required_checkers,
        warning_checkers=post_submit_warning_checkers,
        blocking_severities=post_submit_blocking_severities,
    )
    return {
        "source_snapshot": snapshot,
        "sufficiency_report": report_response.json(),
        "submission_artifact_policy": policy,
        "effective_policy": effective_policy,
        "pre_submit_checker_policy": compiled_pre_submit_checker,
        "post_submit_checker_policy": post_submit_checker_policy,
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


async def seed_worker_profile(subject: str, *, skill_tags: list[str] | None = None) -> str:
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
                    last_seen_roles=["worker"],
                    last_claim_snapshot={"seeded_for_task_test": True},
                    auth_source="dev_mock",
                    is_dev_auth=True,
                ),
                LegacyWorkflowEligibility(
                    id=str(uuid4()),
                    actor_id=worker_actor_id,
                    profile_type="worker",
                    status="active",
                    skill_tags=skill_tags or ["stem"],
                    scope_type="global",
                    scope_id="global",
                    profile_metadata={"seeded_for_task_test": True},
                ),
            ]
        )
        await session.commit()
    return worker_actor_id


async def seed_actor_profile(
    subject: str,
    *,
    profile_type: str,
    status: str = "active",
    skill_tags: list[str] | None = None,
) -> str:
    """Seed one actor identity and global actor profile for authorization tests."""
    seeded_actor_id = actor_id(subject)
    async with db_session.get_session_factory()() as session:
        session.add_all(
            [
                ActorProfile(
                    id=seeded_actor_id,
                    actor_kind="human",
                    status="active",
                    provisioning_method="automatic_first_access",
                    created_by=seeded_actor_id,
                ),
                ActorIdentityLink(
                    id=str(uuid4()),
                    actor_profile_id=seeded_actor_id,
                    issuer="flow-test",
                    subject=subject,
                    subject_kind="human",
                    status="active",
                    linked_by=seeded_actor_id,
                    last_verified_at=datetime.now(UTC),
                ),
                LegacyActorIdentity(
                    actor_id=seeded_actor_id,
                    external_subject=subject,
                    external_issuer="flow-test",
                    display_name=subject.replace("-", " ").title(),
                    email=f"{subject}@example.test",
                    last_seen_roles=[profile_type],
                    last_claim_snapshot={"seeded_for_task_test": True},
                    auth_source="dev_mock",
                    is_dev_auth=True,
                ),
                LegacyWorkflowEligibility(
                    id=str(uuid4()),
                    actor_id=seeded_actor_id,
                    profile_type=profile_type,
                    status=status,
                    skill_tags=skill_tags or [],
                    scope_type="global",
                    scope_id="global",
                    profile_metadata={"seeded_for_task_test": True},
                ),
            ]
        )
        await session.commit()
    return seeded_actor_id


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
        "actor_identities",
        "actor_profiles",
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
    assert set(domain_schema["required"]) == {"code", "details", "error"}
    assert domain_schema["additionalProperties"] is False


def test_task_context_openapi_documents_locked_context_domain_error() -> None:
    schema = create_app().openapi()
    responses = schema["paths"]["/api/v1/tasks/{task_id}/work-context"]["get"][
        "responses"
    ]
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
        ("get_task_work_context", "GET", "/api/v1/tasks/task-id/work-context", None),
        (
            "get_task_submission_requirements",
            "GET",
            "/api/v1/tasks/task-id/submission-requirements",
            None,
        ),
        ("get_task_locked_context", "GET", "/api/v1/tasks/task-id/locked-context", None),
        ("move_to_screening", "POST", "/api/v1/tasks/task-id/screen", None),
        ("release_to_ready", "POST", "/api/v1/tasks/task-id/release", None),
        ("claim_task", "POST", "/api/v1/tasks/task-id/claim", None),
        ("start_task", "POST", "/api/v1/tasks/task-id/start", None),
        (
            "create_submission",
            "POST",
            "/api/v1/tasks/task-id/submissions",
            complete_submission_payload(),
        ),
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
        assert response.json()["error"]["correlation_id"] == response.headers[
            "x-correlation-id"
        ]

    async def fail_with_permission_error(*_args, **_kwargs):
        raise PermissionDenied("bounded permission failure")

    monkeypatch.setattr(TaskService, "get_task", fail_with_permission_error)
    denied = await task_client.get("/api/v1/tasks/task-id", headers=auth_headers())

    assert denied.status_code == 403
    assert denied.json()["detail"] == "bounded permission failure"
    assert denied.json()["error"]["code"] == "permission_not_granted"


async def test_legacy_eligibility_service_updates_existing_submitter_row(
    task_database_env: str,
) -> None:
    async with db_session.get_session_factory()() as session:
        service = ActorService(session)
        worker_actor = ActorContext(
            actor_id=actor_id("worker-upsert"),
            external_subject="worker-upsert",
            external_issuer="flow-test",
            display_name="Worker Upsert",
            email="worker-upsert@example.test",
            roles=("worker",),
            claim_snapshot={"roles": ("worker",)},
            auth_source="dev_mock",
            is_dev_auth=True,
        )
        first_worker = await service.activate_legacy_workflow_eligibility(
            worker_actor,
            LegacyWorkflowEligibilityActivationRequest(skill_tags=["stem"]),
        )
        updated_worker = await service.activate_legacy_workflow_eligibility(
            worker_actor.model_copy(
                update={"display_name": "Worker Updated", "email": "worker-updated@example.test"}
            ),
            LegacyWorkflowEligibilityActivationRequest(skill_tags=["stem", "analysis"]),
        )

    async with db_session.get_session_factory()() as session:
        worker_rows = (
            await session.execute(
                select(LegacyWorkflowEligibility).where(
                    LegacyWorkflowEligibility.actor_id == worker_actor.actor_id,
                    LegacyWorkflowEligibility.profile_type == "worker",
                )
            )
        ).scalars().all()

    assert updated_worker.id == first_worker.id
    assert updated_worker.skill_tags == ["stem", "analysis"]
    assert len(worker_rows) == 1
    assert worker_rows[0].id == first_worker.id


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


async def test_screening_uses_versioned_post_submit_policy_body_after_default_drift(
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
        expected_policy_body = dict(source_policy.policy_body or {})
        expected_policy_hash = source_policy.policy_hash

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
    assert persisted_task.locked_post_submit_checker_policy_body == expected_policy_body
    assert persisted_task.locked_post_submit_checker_policy_hash == expected_policy_hash


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
    payload = complete_task_payload()
    payload["import_batch_id"] = "private-import-batch"
    payload["external_task_id"] = "private-external-task"
    ready_task = await create_ready_task(task_client, project["id"], payload=payload)
    operator_response = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}",
        headers=auth_headers(),
    )

    assert operator_response.status_code == 200, operator_response.text

    await seed_worker_profile("worker-one")
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
    started_task = await create_started_task(task_client, project["id"], monkeypatch, payload=payload)

    work_context = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/work-context",
        headers=auth_headers(),
    )
    assert work_context.status_code == 200, work_context.text
    work_body = work_context.json()
    assert work_body["task"]["locked_guide_version"] == "v1"
    assert work_body["guide"]["version"] == "v1"
    assert "# Task Guide v1" in work_body["guide"]["content_markdown"]
    assert work_body["payment_policy"]["base_amount"] == "25.00"
    assert work_body["lifecycle"]["can_submit"] is True
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
            "key": "answer",
            "path": "answer.md",
            "hash_required": True,
            "required": True,
            "description": "Main task answer.",
        }
    ]
    assert requirements_body["required_evidence"] == [
        {
            "key": "checker_log",
            "label": "checker log",
            "hash_required": True,
            "required": True,
            "description": "Evidence used by the reviewer.",
        }
    ]
    assert requirements_body["artifact_hash_algorithm"] == "sha256"
    assert set(requirements_body["allowed_storage_schemes"]) == {"local", "s3", "r2"}
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
    assert locked_body[
        "locked_effective_project_submission_artifact_policy_hash"
    ].startswith("sha256:")
    assert locked_body["locked_pre_submit_checker_bundle_hash"].startswith("sha256:")
    assert locked_body["locked_post_submit_checker_policy_hash"].startswith("sha256:")
    assert locked_body["locked_post_submit_checker_policy_body_summary"][
        "required_checkers"
    ] == ["check_policy_context_present"]


async def test_ready_worker_work_context_omits_private_task_source_fields(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    payload = complete_task_payload()
    payload["import_batch_id"] = "ready-private-import"
    payload["external_task_id"] = "ready-private-external"
    ready_task = await create_ready_task(task_client, project["id"], payload)
    await seed_worker_profile("worker-one")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")

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


async def test_work_context_uses_stamped_policy_values_after_same_version_policy_mutation(
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
        review_policy = await session.scalar(
            select(ReviewPolicy).where(
                ReviewPolicy.project_id == project["id"],
                ReviewPolicy.guide_version == "v1",
            )
        )
        revision_policy = await session.scalar(
            select(RevisionPolicy).where(
                RevisionPolicy.project_id == project["id"],
                RevisionPolicy.guide_version == "v1",
            )
        )
        payment_policy = await session.scalar(
            select(PaymentPolicy).where(
                PaymentPolicy.project_id == project["id"],
                PaymentPolicy.guide_version == "v1",
            )
        )
        assert review_policy is not None
        assert revision_policy is not None
        assert payment_policy is not None
        review_policy.requires_second_review = True
        review_policy.allowed_decisions = ["reject"]
        revision_policy.max_revision_rounds = 1
        revision_policy.revision_deadline_hours = 1
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
        await session.commit()

    response = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}/work-context",
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "task_locked_context_invalid"


async def test_submission_requirements_fail_closed_on_hash_consistent_malformed_policy_shape(
    task_client: AsyncClient,
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
        replacement_checker_names = list(pre_submit_policy.checker_names)
        replacement_checker_configs = dict(pre_submit_policy.checker_configs)
        compiler_version = pre_submit_policy.compiler_version
        original_compiled_bundle = dict(pre_submit_policy.compiled_bundle)
        await delete_generated_post_submit_output_for_pre_submit(
            session,
            pre_submit_policy.id,
        )
        await session.delete(pre_submit_policy)
        await session.flush()

        malformed_policy = {
            **effective_policy.effective_policy,
            "schema_version": ["not", "a", "string"],
        }
        malformed_policy_hash = canonical_json_hash(malformed_policy)
        malformed_bundle = {
            **original_compiled_bundle,
            "effective_policy_hash": malformed_policy_hash,
        }
        malformed_bundle_hash = canonical_json_hash(malformed_bundle)

        effective_policy.effective_policy = malformed_policy
        effective_policy.effective_policy_hash = malformed_policy_hash
        replacement_pre_submit_policy_id = str(uuid4())
        replacement_pre_submit_policy = PreSubmitCheckerPolicy(
            id=replacement_pre_submit_policy_id,
            project_id=effective_policy.project_id,
            guide_id=effective_policy.guide_id,
            guide_version=effective_policy.guide_version,
            source_snapshot_id=effective_policy.source_snapshot_id,
            source_snapshot_hash=effective_policy.source_snapshot_hash,
            effective_policy_id=effective_policy.id,
            effective_policy_hash=malformed_policy_hash,
            lifecycle_status="compiled",
            compiler_version=compiler_version,
            compiled_bundle=malformed_bundle,
            compiled_bundle_hash=malformed_bundle_hash,
            checker_names=replacement_checker_names,
            checker_configs=replacement_checker_configs,
            created_by="test",
        )
        session.add(replacement_pre_submit_policy)
        await session.flush()
        session.add(
            generated_post_submit_output_for_pre_submit(
                effective_policy=effective_policy,
                pre_submit_checker_policy_id=replacement_pre_submit_policy_id,
                pre_submit_checker_bundle_hash=malformed_bundle_hash,
            )
        )
        await session.commit()

    ready_task = await create_ready_task(task_client, project["id"])
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
    policy_v2 = policy_body_for_task_tests()
    policy_v2["required_artifacts"] = [
        {
            "key": "v2_answer",
            "path": "v2-answer.md",
            "hash_required": True,
            "required": True,
            "description": "New v2 artifact.",
        }
    ]
    await create_policy_bundle_for_guide(
        task_client,
        project["id"],
        guide_v2.json()["id"],
        policy_v2,
    )
    activate_v2 = await task_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide_v2.json()['id']}/activate",
        headers=auth_headers(),
    )
    assert activate_v2.status_code == 200, activate_v2.text
    assert activate_v2.json()["guide"]["version"] == "v2"

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
    assert requirements.json()["required_artifacts"] == v1_requirements.json()[
        "required_artifacts"
    ]
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


async def test_submission_runtime_uses_locked_project_policy_not_task_required_fields(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)

    project_policy_task = await create_started_task(
        task_client,
        project["id"],
        monkeypatch,
        "worker-one",
        complete_task_payload(),
    )
    project_policy_response = await task_client.post(
        f"/api/v1/tasks/{project_policy_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert project_policy_response.status_code == 201, project_policy_response.text

    non_contract_artifact_task = await create_started_task(
        task_client,
        project["id"],
        monkeypatch,
        "worker-two",
        complete_task_payload(),
    )
    non_contract_artifact_payload = complete_submission_payload(
        "sha256:non-contract-package"
    )
    non_contract_artifact_payload["artifact_hash_manifest"] = [
        {
            "artifact": "non-contract-only.md",
            "hash": "sha256:non-contract-only-v1",
            "size_bytes": 128,
            "notes": "does not match the locked project policy",
        }
    ]
    non_contract_artifact_response = await task_client.post(
        f"/api/v1/tasks/{non_contract_artifact_task['id']}/submissions",
        headers=auth_headers(),
        json=non_contract_artifact_payload,
    )

    assert non_contract_artifact_response.status_code == 422, non_contract_artifact_response.text
    detail = non_contract_artifact_response.json()
    assert set(detail) == {"code", "details", "error"}
    assert detail["code"] == "pre_submission_checker_failed"
    assert detail["error"]["code"] == "pre_submission_checker_failed"
    assert detail["error"]["details"] == detail["details"]
    required_files = next(
        result
        for result in detail["details"]["results"]
        if result["checker_name"] == "check_required_files"
    )
    assert required_files["status"] == "failed"

    non_contract_evidence_task = await create_started_task(
        task_client,
        project["id"],
        monkeypatch,
        "worker-three",
        complete_task_payload(),
    )
    non_contract_evidence_payload = complete_submission_payload(
        "sha256:non-contract-evidence-package"
    )
    non_contract_evidence_payload["artifact_hash_manifest"][0]["hash"] = (
        "sha256:answer-non-contract-evidence"
    )
    non_contract_evidence_payload["evidence_items"] = [
        {
            "type": "note",
            "label": "non-contract evidence",
            "uri": "local://evidence/non-contract-evidence.txt",
            "hash": "sha256:non-contract-evidence-v1",
            "size_bytes": 128,
            "metadata": {"policy_key": "non_contract_evidence"},
        }
    ]
    non_contract_evidence_response = await task_client.post(
        f"/api/v1/tasks/{non_contract_evidence_task['id']}/submissions",
        headers=auth_headers(),
        json=non_contract_evidence_payload,
    )

    assert non_contract_evidence_response.status_code == 422, non_contract_evidence_response.text
    detail = non_contract_evidence_response.json()
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
    assert "active legacy submitter eligibility" in response.json()["detail"]
    context = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}/work-context",
        headers=auth_headers(),
    )
    assert context.status_code == 200, context.text
    assert context.json()["lifecycle"]["next_actions"] == []


async def test_disabled_worker_profile_cannot_claim_ready_task(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    await seed_actor_profile("disabled-worker", profile_type="worker", status="disabled")
    set_dev_actor(monkeypatch, roles="worker", subject="disabled-worker")

    response = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "claim with disabled profile"},
    )

    assert response.status_code == 403
    assert "active legacy submitter eligibility" in response.json()["detail"]
    async with db_session.get_session_factory()() as session:
        assignment = await session.scalar(
            select(TaskAssignment).where(TaskAssignment.task_id == ready_task["id"])
        )
        task = await session.get(WorkstreamTask, ready_task["id"])
    assert assignment is None
    assert task is not None
    assert task.status == "ready"


async def test_disabled_legacy_eligibility_after_claim_blocks_assigned_submitter_start(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    worker_actor_id = await seed_worker_profile("eligibility-disabled-after-claim")
    set_dev_actor(
        monkeypatch,
        roles="worker",
        subject="eligibility-disabled-after-claim",
    )
    claim = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "claim while eligible"},
    )
    assert claim.status_code == 200, claim.text

    async with db_session.get_session_factory()() as session:
        eligibility = await session.scalar(
            select(LegacyWorkflowEligibility).where(
                LegacyWorkflowEligibility.actor_id == worker_actor_id,
                LegacyWorkflowEligibility.profile_type == "worker",
            )
        )
        assert eligibility is not None
        eligibility.status = "disabled"
        await session.commit()

    start = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/start",
        headers=auth_headers(),
        json={"reason": "start after eligibility disabled"},
    )
    assert start.status_code == 403
    assert "active legacy submitter eligibility" in start.json()["detail"]
    read = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}", headers=auth_headers()
    )
    assert read.status_code == 200
    assert read.json()["status"] == "claimed"
    context = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}/work-context",
        headers=auth_headers(),
    )
    assert context.status_code == 200, context.text
    assert context.json()["lifecycle"]["next_actions"] == []


async def test_disabled_eligibility_suppresses_submit_lifecycle_affordances(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    subject = "eligibility-disabled-after-start"
    started_task = await create_started_task(
        task_client,
        project["id"],
        monkeypatch,
        subject=subject,
    )
    async with db_session.get_session_factory()() as session:
        eligibility = await session.scalar(
            select(LegacyWorkflowEligibility).where(
                LegacyWorkflowEligibility.actor_id == actor_id(subject),
                LegacyWorkflowEligibility.profile_type == "worker",
            )
        )
        assert eligibility is not None
        eligibility.status = "disabled"
        await session.commit()

    context = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/work-context",
        headers=auth_headers(),
    )

    assert context.status_code == 200, context.text
    lifecycle = context.json()["lifecycle"]
    assert lifecycle["can_run_pre_submit_check"] is False
    assert lifecycle["can_submit"] is False
    assert lifecycle["next_actions"] == []

    async with db_session.get_session_factory()() as session:
        before = {
            "submissions": await session.scalar(
                select(func.count()).select_from(Submission).where(
                    Submission.task_id == started_task["id"]
                )
            ),
            "checker_runs": await session.scalar(
                select(func.count()).select_from(db_models.CheckerRun)
            ),
            "audit_events": await session.scalar(
                select(func.count()).select_from(AuditEvent)
            ),
        }
    submission = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert submission.status_code == 403
    assert "active legacy submitter eligibility" in submission.json()["detail"]
    async with db_session.get_session_factory()() as session:
        after = {
            "submissions": await session.scalar(
                select(func.count()).select_from(Submission).where(
                    Submission.task_id == started_task["id"]
                )
            ),
            "checker_runs": await session.scalar(
                select(func.count()).select_from(db_models.CheckerRun)
            ),
            "audit_events": await session.scalar(
                select(func.count()).select_from(AuditEvent)
            ),
        }
    assert after == before


async def test_active_worker_profile_without_worker_token_cannot_claim(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    set_dev_actor(monkeypatch, roles="worker", subject="project-manager-subject")
    activation = await task_client.post(
        "/api/v1/workers/me/profile",
        headers=auth_headers(),
        json={"skill_tags": []},
    )
    assert activation.status_code == 200, activation.text
    set_dev_actor(
        monkeypatch,
        roles="project_manager",
        subject="project-manager-subject",
    )

    response = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "claim without worker token role"},
    )

    assert response.status_code == 403
    assert "actor lacks required role" in response.json()["detail"]
    context = await task_client.get(
        f"/api/v1/tasks/{ready_task['id']}/work-context",
        headers=auth_headers(),
    )
    assert context.status_code == 200, context.text
    assert context.json()["lifecycle"]["next_actions"] == []


@pytest.mark.parametrize("profile_type", ["admin", "project_manager"])
async def test_active_operator_profile_without_matching_token_cannot_create_task(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    profile_type: str,
) -> None:
    project = await create_active_project(task_client)
    subject = f"{profile_type}-profile-only"
    await seed_actor_profile(subject, profile_type=profile_type)
    set_dev_actor(monkeypatch, roles="worker", subject=subject)

    response = await task_client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        headers=auth_headers(),
        json=complete_task_payload(),
    )

    assert response.status_code == 403
    assert "actor lacks required role" in response.json()["detail"]


async def test_worker_can_create_profile_before_claiming_task(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    set_dev_actor(monkeypatch, roles="worker", subject="worker-self-profile")

    profile = await task_client.post(
        "/api/v1/workers/me/profile",
        headers=auth_headers(),
        json={"skill_tags": [" Terminal_Benchmark ", "GO", "go"]},
    )
    assert profile.status_code == 200, profile.text
    profile_body = profile.json()
    assert profile_body["actor_id"] == actor_id("worker-self-profile")
    assert profile_body["external_subject"] == "worker-self-profile"
    assert profile_body["skill_tags"] == ["terminal_benchmark", "go"]
    assert profile_body["status"] == "active"

    refreshed_profile = await task_client.post(
        "/api/v1/workers/me/profile",
        headers=auth_headers(),
        json={"skill_tags": ["stem"]},
    )
    assert refreshed_profile.status_code == 200, refreshed_profile.text
    assert refreshed_profile.json()["id"] == profile_body["id"]
    assert refreshed_profile.json()["skill_tags"] == ["stem"]

    claim = await task_client.post(
        f"/api/v1/tasks/{ready_task['id']}/claim",
        headers=auth_headers(),
        json={"reason": "claim after self profile"},
    )

    assert claim.status_code == 200, claim.text
    assert claim.json()["task"]["status"] == "claimed"
    assert claim.json()["assignment"]["worker_id"] == actor_id("worker-self-profile")


async def test_worker_profile_response_excludes_identity_display_fields(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_dev_actor(
        monkeypatch,
        roles="worker",
        subject="worker-null-identity",
        email=None,
        display_name=None,
    )

    response = await task_client.post(
        "/api/v1/workers/me/profile",
        headers=auth_headers(),
        json={"skill_tags": []},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["actor_id"] == actor_id("worker-null-identity")
    assert body["external_subject"] == "worker-null-identity"
    assert body["external_issuer"] == "flow-test"
    assert "display_name" not in body
    assert "email" not in body
    assert body["skill_tags"] == []
    assert body["status"] == "active"


async def test_worker_profile_request_is_fail_closed_and_validated(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subject = "worker-profile-validation"
    set_dev_actor(monkeypatch, roles="worker", subject=subject)

    spoofed_fields = {
        "actor_id": actor_id("malicious"),
        "external_subject": "spoofed-subject",
        "external_issuer": "spoofed-issuer",
        "roles": ["admin"],
        "email": "spoofed@example.test",
        "display_name": "Spoofed Name",
    }
    for field_name, field_value in spoofed_fields.items():
        unknown_field = await task_client.post(
            "/api/v1/workers/me/profile",
            headers=auth_headers(),
            json={
                "skill_tags": ["stem"],
                field_name: field_value,
            },
        )
        assert unknown_field.status_code == 422
        assert field_name in unknown_field.text

    identity, profiles = await fetch_legacy_actor_rows(subject)
    malicious_identity, malicious_profiles = await fetch_legacy_actor_rows("malicious")

    assert malicious_identity is None
    assert malicious_profiles == []
    assert identity is not None
    assert identity.actor_id == actor_id(subject)
    assert identity.external_subject == subject
    assert identity.external_issuer == "flow-test"
    assert identity.email is None
    assert identity.display_name is None
    assert identity.last_seen_roles == ["worker"]
    assert profiles == []

    blank_tag = await task_client.post(
        "/api/v1/workers/me/profile",
        headers=auth_headers(),
        json={"skill_tags": [" "]},
    )
    long_tag = await task_client.post(
        "/api/v1/workers/me/profile",
        headers=auth_headers(),
        json={"skill_tags": ["x" * 65]},
    )

    assert blank_tag.status_code == 422
    assert "invalid skill tag" in blank_tag.text
    assert long_tag.status_code == 422
    assert "invalid skill tag" in long_tag.text


async def test_registered_claim_route_rejects_identity_spoof_fields(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(task_client)
    ready_task = await create_ready_task(task_client, project["id"])
    set_dev_actor(monkeypatch, roles="worker", subject="worker-claim-overpost")
    profile = await task_client.post(
        "/api/v1/workers/me/profile",
        headers=auth_headers(),
        json={"skill_tags": ["stem"]},
    )
    assert profile.status_code == 200, profile.text

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

    identity, profiles = await fetch_legacy_actor_rows("worker-claim-overpost")
    malicious_identity, malicious_profiles = await fetch_legacy_actor_rows("malicious")

    assert malicious_identity is None
    assert malicious_profiles == []
    assert identity is not None
    assert identity.actor_id == actor_id("worker-claim-overpost")
    assert identity.external_subject == "worker-claim-overpost"
    assert identity.external_issuer == "flow-test"
    assert identity.email is None
    assert identity.display_name is None
    assert identity.last_seen_roles == ["worker"]
    assert [(profile.profile_type, profile.status, profile.skill_tags) for profile in profiles] == [
        ("worker", "active", ["stem"])
    ]


async def test_worker_profile_requires_worker_role(
    task_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")

    response = await task_client.post(
        "/api/v1/workers/me/profile",
        headers=auth_headers(),
        json={"skill_tags": ["stem"]},
    )

    assert response.status_code == 403
    assert "actor lacks required role" in response.json()["detail"]


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


async def test_assigned_worker_submit_auto_enters_pre_review_gate(
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
    assert submission["finalized_at"] is not None
    assert submission["evidence_items"][0]["finalized_at"] == submission["finalized_at"]
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
            "finalized_at": "2026-06-07T00:00:00Z",
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

    assert other_worker_response.status_code == 404


async def test_pre_submit_failure_writes_audit_event_without_submission(
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
    new_audit_events = [event for event in audit_events if event.id not in audit_ids_before]
    assert len(new_audit_events) == 1
    assert new_audit_events[0].event_type == "pre_submission_check_failed"
    assert new_audit_events[0].from_status == "in_progress"
    assert new_audit_events[0].to_status == "in_progress"
    assert new_audit_events[0].event_payload["pre_submit_check"]["status"] == "failed"
    assert (
        new_audit_events[0].event_payload["pre_submit_check"]["eligible_to_submit"]
        is False
    )
    assert checker_runs == []
    assert task is not None
    assert task.status == "in_progress"

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    audit_response = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert audit_response.status_code == 200, audit_response.text
    audit_event = next(
        event
        for event in audit_response.json()
        if event["event_type"] == "pre_submission_check_failed"
    )
    assert audit_event["event_payload"]["pre_submit_check"]["status"] == "failed"


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
    assert response.json()["code"] == "task_locked_context_invalid"
    assert (
        response.json()["details"]["field"]
        == "locked_effective_project_submission_artifact_policy_hash"
    )

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
        await delete_generated_post_submit_output_for_pre_submit(
            session,
            pre_submit_policy.id,
        )
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
        replacement_pre_submit_policy_id = str(uuid4())
        replacement_pre_submit_policy = PreSubmitCheckerPolicy(
            id=replacement_pre_submit_policy_id,
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
        session.add(replacement_pre_submit_policy)
        await session.flush()
        session.add(
            generated_post_submit_output_for_pre_submit(
                effective_policy=effective_policy,
                pre_submit_checker_policy_id=replacement_pre_submit_policy_id,
                pre_submit_checker_bundle_hash=replacement_bundle_hash,
            )
        )
        await session.commit()

    task = await create_draft_task(task_client, project["id"])
    screen = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screening checklist passed"},
    )
    assert screen.status_code == 200, screen.text
    response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/release",
        headers=auth_headers(),
        json={"reason": "release decision recorded"},
    )

    assert response.status_code == 422, response.text
    assert "locked project pre-submit checker policy" in response.json()["detail"]

    async with db_session.get_session_factory()() as session:
        submissions = (
            await session.execute(select(Submission).where(Submission.task_id == task["id"]))
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
        await delete_generated_post_submit_output_for_pre_submit(
            session,
            pre_submit_policy.id,
        )
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
        replacement_pre_submit_policy_id = str(uuid4())
        replacement_pre_submit_policy = PreSubmitCheckerPolicy(
            id=replacement_pre_submit_policy_id,
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
        session.add(replacement_pre_submit_policy)
        await session.flush()
        session.add(
            generated_post_submit_output_for_pre_submit(
                effective_policy=effective_policy,
                pre_submit_checker_policy_id=replacement_pre_submit_policy_id,
                pre_submit_checker_bundle_hash=replacement_bundle_hash,
            )
        )
        await session.commit()

    task = await create_draft_task(task_client, project["id"])
    screen = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screening checklist passed"},
    )
    assert screen.status_code == 200, screen.text
    response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/release",
        headers=auth_headers(),
        json={"reason": "release decision recorded"},
    )

    assert response.status_code == 422, response.text
    assert "locked project pre-submit checker policy" in response.json()["detail"]

    async with db_session.get_session_factory()() as session:
        submissions = (
            await session.execute(select(Submission).where(Submission.task_id == task["id"]))
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
    assert response.json()["code"] == "task_locked_context_invalid"
    assert response.json()["details"]["field"] == "locked_pre_submit_checker_bundle_hash"

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
        await delete_generated_post_submit_output_for_pre_submit(
            session,
            pre_submit_policy.id,
        )
        pre_submit_policy.compiled_bundle = replacement_bundle
        pre_submit_policy.compiled_bundle_hash = replacement_bundle_hash
        await session.flush()
        session.add(
            generated_post_submit_output_for_pre_submit(
                effective_policy=effective_policy,
                pre_submit_checker_policy_id=pre_submit_policy.id,
                pre_submit_checker_bundle_hash=replacement_bundle_hash,
            )
        )
        await session.commit()

    task = await create_draft_task(task_client, project["id"])
    screen = await task_client.post(
        f"/api/v1/tasks/{task['id']}/screen",
        headers=auth_headers(),
        json={"reason": "screening checklist passed"},
    )
    assert screen.status_code == 200, screen.text
    response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/release",
        headers=auth_headers(),
        json={"reason": "release decision recorded"},
    )

    assert response.status_code == 422, response.text
    assert "locked project pre-submit checker policy" in response.json()["detail"]

    async with db_session.get_session_factory()() as session:
        submissions = (
            await session.execute(select(Submission).where(Submission.task_id == task["id"]))
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
    assert response.json()["code"] == "task_locked_context_invalid"
    assert response.json()["details"]["field"] == "locked_pre_submit_checker_policy_id"

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
    assert task.status == "review_pending"
    assert len(submissions) == 1
    assert submissions[0].locked_post_submit_checker_policy_body == locked_body
    assert "check_acceptance_criteria_present" not in locked_body["required_checkers"]
    assert "check_acceptance_criteria_present" not in locked_body["execution_checkers"]
    assert "check_required_files" in locked_body["default_checkers"]
    assert "check_required_files" in locked_body["execution_checkers"]
    assert len(checker_runs) == 1
    assert checker_runs[0].locked_post_submit_checker_policy_body == locked_body


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
    assert fetched_v1.json()["finalized_at"] == locked_v1.json()["finalized_at"]
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
    assert task.json()["status"] == "review_pending"


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
async def test_future_roles_cannot_view_unassigned_task_or_submissions(
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
        task.locked_review_policy_version = "v2"
        task.locked_revision_policy_version = "v2"
        task.locked_payment_policy_version = "v2"
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_finalize_submission_rejects_unfinished_task(
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
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.status = "in_progress"
        submission = await TaskRepository(session).get_submission(created.json()["id"])
        assert submission is not None
        submission.locked_at = None
        for evidence in submission.evidence_items:
            evidence.locked_at = None
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    finalize = await task_client.post(
        f"/api/v1/submissions/{created.json()['id']}/finalize",
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
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    async with db_session.get_session_factory()() as session:
        submission = await session.get(Submission, created.json()["id"])
        assert submission is not None
        submission.status = "draft"
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    finalize = await task_client.post(
        f"/api/v1/submissions/{created.json()['id']}/finalize",
        headers=auth_headers(),
    )

    assert finalize.status_code == 409
    assert "submission must be submitted before repair check" in finalize.json()["detail"]


async def test_finalize_submission_rejects_invalid_locked_context(
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
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        policy = await session.get(PreSubmitCheckerPolicy, task.locked_pre_submit_checker_policy_id)
        assert policy is not None
        policy.compiled_bundle = {**policy.compiled_bundle, "tampered": True}
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    finalize = await task_client.post(
        f"/api/v1/submissions/{created.json()['id']}/finalize",
        headers=auth_headers(),
    )

    assert finalize.status_code == 200, finalize.text
    assert finalize.json()["finalized_at"] == created.json()["finalized_at"]


async def test_finalize_submission_rejects_non_latest_version(
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

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    stale_finalize = await task_client.post(
        f"/api/v1/submissions/{v1.json()['id']}/finalize",
        headers=auth_headers(),
    )

    assert stale_finalize.status_code == 409
    assert "only latest submission version can be repair-checked" in stale_finalize.json()["detail"]


async def test_submitter_finalize_is_idempotent_after_automatic_gate(
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

    worker_repair = await task_client.post(
        f"/api/v1/submissions/{v1.json()['id']}/finalize",
        headers=auth_headers(),
        json={"actor_id": "workstream-system:pre-review-gate"},
    )
    assert worker_repair.status_code == 403, worker_repair.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="other-project-manager")
    wrong_manager_finalize = await task_client.post(
        f"/api/v1/submissions/{v1.json()['id']}/finalize",
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
        f"/api/v1/submissions/{v1.json()['id']}/finalize",
        headers=auth_headers(),
        json={"audit_actor": "client-supplied-spoof"},
    )
    assert locked.status_code == 200, locked.text
    locked_body = locked.json()
    assert locked_body["finalized_at"] is not None
    assert locked_body["evidence_items"][0]["finalized_at"] == locked_body["finalized_at"]
    checker_runs = await task_client.get(
        f"/api/v1/submissions/{v1.json()['id']}/checker-runs",
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
        f"/api/v1/submissions/{v1.json()['id']}/finalize",
        headers=auth_headers(),
    )
    assert second_lock.status_code == 200, second_lock.text
    assert second_lock.json()["finalized_at"] == locked_body["finalized_at"]
    repeated_checker_runs = await task_client.get(
        f"/api/v1/submissions/{v1.json()['id']}/checker-runs",
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
    create_response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert create_response.status_code == 201, create_response.text
    assert create_response.json()["finalized_at"] is not None

    submissions = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
    )
    assert submissions.status_code == 200, submissions.text
    assert len(submissions.json()) == 1
    submission_id = submissions.json()[0]["id"]
    assert submissions.json()[0]["finalized_at"] is not None
    assert submission_id == create_response.json()["id"]

    async with db_session.get_session_factory()() as session:
        checker_runs = (
            await session.execute(
                select(db_models.CheckerRun).where(
                    db_models.CheckerRun.submission_id == submission_id
                )
            )
        ).scalars().all()
        task = await session.get(WorkstreamTask, started_task["id"])
        dispatch_failed_events = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_id == started_task["id"],
                    AuditEvent.event_type == "pre_review_gate_dispatch_failed",
                )
            )
        ).scalars().all()
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
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_id == started_task["id"],
                    AuditEvent.event_type == "pre_review_gate_repair_requested",
                )
            )
        ).scalars().all()
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
    create_response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert create_response.status_code == 201, create_response.text
    assert create_response.json()["finalized_at"] is not None
    submissions = await task_client.get(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
    )
    assert submissions.status_code == 200, submissions.text
    submission_id = submissions.json()[0]["id"]

    async with db_session.get_session_factory()() as session:
        failed_run = await session.scalar(
            select(db_models.CheckerRun).where(
                db_models.CheckerRun.submission_id == submission_id
            )
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
            await session.execute(
                select(db_models.CheckerRun).where(
                    db_models.CheckerRun.submission_id == submission_id
                )
            )
        ).scalars().all()
        repair_events = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_id == started_task["id"],
                    AuditEvent.event_type == "pre_review_gate_repair_requested",
                )
            )
        ).scalars().all()

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
    create_response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert create_response.status_code == 201, create_response.text
    submission_id = create_response.json()["id"]

    async with db_session.get_session_factory()() as session:
        moved_run = await session.scalar(
            select(db_models.CheckerRun).where(
                db_models.CheckerRun.submission_id == submission_id
            )
        )
        dispatch_events = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "task",
                    AuditEvent.entity_id == started_task["id"],
                    AuditEvent.event_type == "pre_review_gate_dispatch_failed",
                )
            )
        ).scalars().all()

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
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    submission_id = created.json()["id"]

    async with db_session.get_session_factory()() as session:
        failed_run = await session.scalar(
            select(db_models.CheckerRun).where(
                db_models.CheckerRun.submission_id == submission_id
            )
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
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    submission_id = created.json()["id"]

    async with db_session.get_session_factory()() as session:
        failed_run = await session.scalar(
            select(db_models.CheckerRun).where(
                db_models.CheckerRun.submission_id == submission_id
            )
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
    create_response = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert create_response.status_code == 201, create_response.text
    submission_id = create_response.json()["id"]
    assert create_response.json()["finalized_at"] is not None

    async with db_session.get_session_factory()() as session:
        failed_run = await session.scalar(
            select(db_models.CheckerRun).where(
                db_models.CheckerRun.submission_id == submission_id
            )
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
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    submission_id = created.json()["id"]

    stale_started_at = datetime.now(UTC) - timedelta(hours=1)
    async with db_session.get_session_factory()() as session:
        queued_run = await session.scalar(
            select(db_models.CheckerRun).where(
                db_models.CheckerRun.submission_id == submission_id
            )
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
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    submission_id = created.json()["id"]

    stale_started_at = datetime.now(UTC) - timedelta(hours=1)
    async with db_session.get_session_factory()() as session:
        queued_run = await session.scalar(
            select(db_models.CheckerRun).where(
                db_models.CheckerRun.submission_id == submission_id
            )
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
            await session.execute(
                select(db_models.CheckerRun)
                .where(db_models.CheckerRun.submission_id == submission_id)
                .order_by(db_models.CheckerRun.attempt_number.asc())
            )
        ).scalars().all()
        repair_events = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_id == started_task["id"],
                    AuditEvent.event_type == "pre_review_gate_repair_requested",
                )
            )
        ).scalars().all()

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
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    submission_id = created.json()["id"]
    assert created.json()["finalized_at"] is not None
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
            await session.execute(
                select(db_models.CheckerRun).where(
                    db_models.CheckerRun.submission_id == submission_id
                )
            )
        ).scalars().all()
        audit_events = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.entity_id == started_task["id"])
            )
        ).scalars().all()

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
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    manual_run = await task_client.post(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "manual shortcut attempt"},
    )

    assert manual_run.status_code == 409
    assert "automatic pre-review gate must be repaired" in manual_run.json()["detail"]
    async with db_session.get_session_factory()() as session:
        checker_runs = (
            await session.execute(
                select(db_models.CheckerRun).where(
                    db_models.CheckerRun.submission_id == created.json()["id"]
                )
            )
        ).scalars().all()
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
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    submission_id = created.json()["id"]

    async with db_session.get_session_factory()() as session:
        queued_run = await session.scalar(
            select(db_models.CheckerRun).where(
                db_models.CheckerRun.submission_id == submission_id
            )
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
        run_pre_review_gate.run(
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
            await session.execute(
                select(db_models.CheckerRun).where(
                    db_models.CheckerRun.submission_id == submission_id
                )
            )
        ).scalars().all()
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
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    submission_id = created.json()["id"]

    async with db_session.get_session_factory()() as session:
        submission = await session.get(Submission, submission_id)
        task = await session.get(WorkstreamTask, started_task["id"])
        queued_run = await session.scalar(
            select(db_models.CheckerRun).where(
                db_models.CheckerRun.submission_id == submission_id
            )
        )
        assert submission is not None
        assert task is not None
        assert queued_run is not None
        pre_submit_policy = await session.get(
            PreSubmitCheckerPolicy,
            submission.locked_pre_submit_checker_policy_id,
        )
        assert pre_submit_policy is not None
        pre_submit_policy.compiled_bundle = {
            **pre_submit_policy.compiled_bundle,
            "tampered": True,
        }
        await session.commit()

    with pytest.raises(CheckerPolicyInvalid):
        run_pre_review_gate.run(
            queued_run.id,
            expected_worker_requester_provenance(),
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
        assert task.status == "evaluation_pending"
        restored_bundle = dict(pre_submit_policy.compiled_bundle)
        restored_bundle.pop("tampered", None)
        pre_submit_policy.compiled_bundle = restored_bundle
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
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    submission_id = created.json()["id"]

    async with db_session.get_session_factory()() as session:
        queued_run = await session.scalar(
            select(db_models.CheckerRun).where(
                db_models.CheckerRun.submission_id == submission_id
            )
        )
    assert queued_run is not None

    with pytest.raises(CheckerExecutionBlocked):
        run_pre_review_gate.run(
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
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "task",
                    AuditEvent.entity_id == started_task["id"],
                    AuditEvent.event_type.like("pre_review_gate_%"),
                )
            )
        ).scalars().all()
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
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    submission_id = created.json()["id"]

    async with db_session.get_session_factory()() as session:
        queued_run = await session.scalar(
            select(db_models.CheckerRun).where(
                db_models.CheckerRun.submission_id == submission_id
            )
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
        run_pre_review_gate.run(
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
    v1 = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert v1.status_code == 201, v1.text
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.status = "needs_revision"
        v1_run = await session.scalar(
            select(db_models.CheckerRun).where(
                db_models.CheckerRun.submission_id == v1.json()["id"]
            )
        )
        await session.commit()
    assert v1_run is not None
    assert v1_run.status == "queued"

    v2_payload = complete_submission_payload("sha256:package-v2")
    v2_payload["artifact_hash_manifest"][0]["hash"] = "sha256:answer-v2"
    v2 = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=v2_payload,
    )
    assert v2.status_code == 201, v2.text

    result = run_pre_review_gate.run(
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
                db_models.CheckerRun.submission_id == v2.json()["id"]
            )
        )
        audit_events = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "task",
                    AuditEvent.entity_id == started_task["id"],
                    AuditEvent.event_type.like("pre_review_gate_%"),
                )
            )
        ).scalars().all()

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
    created = await task_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    submission_id = created.json()["id"]
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
    assert task.source_payload_hash == "hash-123"
    assert task.base_amount == Decimal("25.00")
