from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from app.core.config import get_settings
from app.db import models as db_models
from app.db import session as db_session
from app.db.base import Base
from app.main import create_app
from app.modules.checkers.models import CheckerResult, CheckerRun
from app.modules.checkers.runner import canonical_artifact_manifest_hash
from app.modules.checkers.schemas import CheckerRoutingRecommendation
from app.modules.tasks.models import AuditEvent, Submission, WorkstreamTask
from tests.test_tasks import (
    auth_headers,
    complete_guide_payload,
    complete_submission_payload,
    create_active_project,
    create_started_task,
    seed_worker_profile,
    set_dev_actor,
)


@pytest.fixture
def checker_database_env(
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
async def checker_client(checker_database_env: str) -> AsyncIterator[AsyncClient]:
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


def test_checker_models_are_registered_for_alembic_metadata() -> None:
    expected_tables = {"checker_runs", "checker_results"}

    assert expected_tables.issubset(Base.metadata.tables)
    assert db_models.CheckerRun is CheckerRun
    assert db_models.CheckerResult is CheckerResult


def test_checker_routing_recommendation_schema_uses_canonical_routing_tokens() -> None:
    adapter = TypeAdapter(CheckerRoutingRecommendation)

    assert adapter.validate_python("checker_retry") == "checker_retry"
    assert adapter.validate_python("task_setup_blocked") == "task_setup_blocked"
    with pytest.raises(ValidationError):
        adapter.validate_python("operator" + "_retry")


async def test_checker_migration_creates_expected_tables(checker_database_env: str) -> None:
    async with db_session.get_engine().connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )

    assert {"checker_runs", "checker_results"}.issubset(table_names)


def test_checker_run_current_partial_unique_index_metadata_compiles() -> None:
    index = next(
        index
        for index in CheckerRun.__table__.indexes
        if index.name == "uq_checker_runs_current_per_submission"
    )

    postgres_compiled = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "is_current_for_submission = true" in postgres_compiled


def test_artifact_manifest_hash_is_stable_and_rejects_duplicates() -> None:
    first = [
        {"artifact": "b.txt", "hash": "sha256:b", "size_bytes": 2, "notes": None},
        {"hash": "sha256:a", "artifact": "a.txt", "notes": "main", "size_bytes": 1},
    ]
    second = [
        {"size_bytes": 1, "notes": "main", "artifact": "a.txt", "hash": "sha256:a"},
        {"notes": None, "artifact": "b.txt", "hash": "sha256:b", "size_bytes": 2},
    ]

    assert canonical_artifact_manifest_hash(first) == canonical_artifact_manifest_hash(second)

    with pytest.raises(ValueError, match="duplicate artifact"):
        canonical_artifact_manifest_hash(
            [
                {"artifact": "a.txt", "hash": "sha256:a"},
                {"artifact": "a.txt", "hash": "sha256:b"},
            ]
        )


async def lock_submission_and_get_auto_run(
    client: AsyncClient,
    submission_id: str,
) -> tuple[dict, dict]:
    """Lock a submission and return the automatic pre-review checker run.

    Args:
        client: API client using the current test actor.
        submission_id: Submission id to lock.

    Returns:
        Locked submission payload and the first automatic checker run payload.
    """
    locked = await client.post(
        f"/api/v1/submissions/{submission_id}/lock",
        headers=auth_headers(),
    )
    assert locked.status_code == 200, locked.text

    listed = await client.get(
        f"/api/v1/submissions/{submission_id}/checker-runs",
        headers=auth_headers(),
    )
    assert listed.status_code == 200, listed.text
    runs = listed.json()
    assert len(runs) == 1
    assert runs[0]["trigger_source"] == "submission_locked"
    assert runs[0]["attempt_number"] == 1
    return locked.json(), runs[0]


async def test_pre_submit_check_returns_feedback_without_durable_run(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["artifact_hash_manifest"].append(
        {
            "artifact": "answer.md",
            "hash": "sha256:duplicate",
            "size_bytes": 129,
            "notes": "duplicate",
        }
    )

    response = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submission-precheck",
        headers=auth_headers(),
        json={"submission": payload},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["authoritative"] is False
    assert body["status"] == "failed"
    assert body["eligible_to_submit"] is False
    result_names = {result["checker_name"] for result in body["results"]}
    assert {
        "check_submission_packet",
        "check_evidence_present",
        "check_evidence_integrity",
        "check_required_files",
        "check_forbidden_files",
        "check_confidentiality_attestation",
    }.issubset(result_names)
    assert any(
        result["checker_name"] == "check_evidence_integrity"
        and result["would_block_if_submitted"] is True
        for result in body["results"]
    )

    async with db_session.get_session_factory()() as session:
        rows = (await session.execute(CheckerRun.__table__.select())).all()
    assert rows == []


async def test_pre_submit_chunk8_matrix_flags_missing_evidence_and_warning(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["evidence_items"] = []
    payload["summary"] = "Completed the proof evaluation with a placeholder note."

    response = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submission-precheck",
        headers=auth_headers(),
        json={"submission": payload},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["authoritative"] is False
    assert body["status"] == "failed"
    assert body["eligible_to_submit"] is False
    result_by_name = {result["checker_name"]: result for result in body["results"]}
    assert result_by_name["check_evidence_present"]["status"] == "failed"
    assert result_by_name["check_evidence_present"]["would_block_if_submitted"] is True
    assert result_by_name["check_required_files"]["status"] == "passed"
    assert result_by_name["check_forbidden_files"]["status"] == "passed"
    assert result_by_name["check_confidentiality_attestation"]["status"] == "passed"
    assert result_by_name["check_low_quality_generated_artifacts"]["status"] == "warning"
    assert (
        result_by_name["check_low_quality_generated_artifacts"]["would_block_if_submitted"]
        is False
    )

    async with db_session.get_session_factory()() as session:
        rows = (await session.execute(CheckerRun.__table__.select())).all()
    assert rows == []


async def test_locked_submission_checker_run_persists_results_and_allows_review(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, body = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])
    assert body["status"] == "completed"
    assert body["trigger_source"] == "submission_locked"
    assert body["routing_recommendation"] == "allow_review"
    assert body["outcome_source"] == "none"
    assert body["submission_version"] == 1
    assert body["locked_checker_policy_version"] == "v1"
    assert body["artifact_manifest_hash"].startswith("sha256:")
    assert body["audit_event_id"]
    assert body["passed_count"] >= 8
    assert body["blocking_count"] == 0
    assert {
        "check_submission_packet",
        "check_policy_context_present",
        "check_evidence_present",
        "check_evidence_integrity",
        "check_required_files",
        "check_forbidden_files",
        "check_confidentiality_attestation",
        "check_low_quality_generated_artifacts",
    }.issubset({result["checker_name"] for result in body["results"]})

    listed = await checker_client.get(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
    )
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()] == [body["id"]]

    async with db_session.get_session_factory()() as session:
        audit = await session.get(AuditEvent, body["audit_event_id"])
        task = await session.get(WorkstreamTask, started_task["id"])
    assert audit is not None
    assert audit.event_type == "checker_run_triggered"
    assert audit.entity_id == created.json()["id"]
    assert audit.reason == "submission locked pre-review gate"
    assert audit.event_payload["submission_version"] == 1
    assert audit.event_payload["trigger_source"] == "submission_locked"
    assert task is not None
    assert task.status == "review_pending"
    audit_response = await checker_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert audit_response.status_code == 200, audit_response.text
    audit_events = {event["event_type"]: event for event in audit_response.json()}
    assert "pre_review_gate_started" in audit_events
    assert "pre_review_gate_passed" in audit_events
    assert audit_events["pre_review_gate_started"]["event_payload"]["trigger_source"] == (
        "submission_locked"
    )
    assert audit_events["pre_review_gate_passed"]["event_payload"]["trigger_source"] == (
        "submission_locked"
    )


async def test_checker_run_retry_supersedes_previous_current_run(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, first = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])

    second = await checker_client.post(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "retry run"},
    )

    assert second.status_code == 200, second.text
    assert second.json()["attempt_number"] == 2
    assert second.json()["supersedes_checker_run_id"] == first["id"]
    listed = await checker_client.get(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
    )
    assert listed.status_code == 200, listed.text
    assert [item["attempt_number"] for item in listed.json()] == [1, 2]
    assert listed.json()[0]["is_current_for_submission"] is False
    assert listed.json()[1]["is_current_for_submission"] is True


async def test_checker_run_with_duplicate_artifact_persists_needs_revision_result(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["artifact_hash_manifest"].append(
        {
            "artifact": "answer.md",
            "hash": "sha256:duplicate",
            "size_bytes": 129,
            "notes": "duplicate",
        }
    )
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )
    assert created.status_code == 201, created.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, body = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])
    assert body["routing_recommendation"] == "needs_revision"
    assert body["outcome_source"] == "auto_checker"
    assert body["artifact_manifest_hash"] == "invalid:artifact_manifest"
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
    assert task is not None
    assert task.status == "needs_revision"
    audit_response = await checker_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert audit_response.status_code == 200, audit_response.text
    assert "pre_review_gate_needs_revision" in {
        event["event_type"] for event in audit_response.json()
    }
    duplicate_result = next(
        result
        for result in body["results"]
        if result["checker_name"] == "check_evidence_integrity"
    )
    assert duplicate_result["status"] == "failed"
    assert duplicate_result["blocks_review"] is True
    assert duplicate_result["worker_message"] == (
        "Artifact manifest contains invalid or duplicate entries."
    )
    assert "duplicate artifact" in duplicate_result["metadata"]["integrity_error"]


async def test_chunk8_missing_required_file_routes_to_needs_revision(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["artifact_hash_manifest"] = [
        {
            "artifact": "other.md",
            "hash": "sha256:other-v1",
            "size_bytes": 128,
            "notes": "wrong artifact",
        }
    ]
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )
    assert created.status_code == 201, created.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, body = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])
    assert body["routing_recommendation"] == "needs_revision"
    assert body["outcome_source"] == "auto_checker"
    required_files = next(
        result for result in body["results"] if result["checker_name"] == "check_required_files"
    )
    assert required_files["status"] == "failed"
    assert required_files["blocks_review"] is True
    assert "missing required artifact files" in required_files["worker_message"]


async def test_chunk8_default_blocking_checker_survives_empty_blocking_severities(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_response = await checker_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={
            "name": "Empty Blocking Severity Project",
            "slug": "empty-blocking-severity-project",
            "base_amount": "25.00",
            "currency": "USD",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    guide_payload = complete_guide_payload()
    guide_payload["checker_policy"]["required_checkers"] = ["check_policy_context_present"]
    guide_payload["checker_policy"]["blocking_severities"] = []
    guide_response = await checker_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=guide_payload,
    )
    assert guide_response.status_code == 201, guide_response.text
    activation_response = await checker_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide_response.json()['id']}/activate",
        headers=auth_headers(),
    )
    assert activation_response.status_code == 200, activation_response.text
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["artifact_hash_manifest"] = [
        {
            "artifact": "other.md",
            "hash": "sha256:other-v1",
            "size_bytes": 128,
            "notes": "wrong artifact",
        }
    ]
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )
    assert created.status_code == 201, created.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, body = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])
    assert body["routing_recommendation"] == "needs_revision"
    required_files = next(
        result for result in body["results"] if result["checker_name"] == "check_required_files"
    )
    assert required_files["status"] == "failed"
    assert required_files["blocks_review"] is True


async def test_chunk8_forbidden_file_blocks_without_worker_path_leakage(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["artifact_hash_manifest"].append(
        {
            "artifact": "secrets/.env",
            "hash": "sha256:env-v1",
            "size_bytes": 64,
            "notes": "should be removed",
        }
    )
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )
    assert created.status_code == 201, created.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, body = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])
    assert body["routing_recommendation"] == "needs_revision"
    forbidden = next(
        result for result in body["results"] if result["checker_name"] == "check_forbidden_files"
    )
    assert forbidden["status"] == "failed"
    assert forbidden["blocks_review"] is True
    assert forbidden["worker_visible"] is True
    assert ".env" not in forbidden["worker_message"]
    assert "secrets/" not in forbidden["worker_message"]
    assert "local://" not in forbidden["worker_message"]


async def test_chunk8_confidentiality_attestation_blocks_generic_text(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["worker_attestation"] = "ok"
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )
    assert created.status_code == 201, created.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, body = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])
    assert body["routing_recommendation"] == "needs_revision"
    attestation = next(
        result
        for result in body["results"]
        if result["checker_name"] == "check_confidentiality_attestation"
    )
    assert attestation["status"] == "failed"
    assert attestation["blocks_review"] is True
    assert "confidentiality attestation" in attestation["worker_message"]


async def test_chunk8_low_quality_generated_artifacts_warns_without_blocking(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["summary"] = "Completed the proof evaluation with a placeholder note to revise."
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=payload,
    )
    assert created.status_code == 201, created.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, body = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])
    assert body["routing_recommendation"] == "allow_review"
    assert body["outcome_source"] == "none"
    assert body["warning_count"] >= 1
    low_quality = next(
        result
        for result in body["results"]
        if result["checker_name"] == "check_low_quality_generated_artifacts"
    )
    assert low_quality["status"] == "warning"
    assert low_quality["blocks_review"] is False


async def test_chunk8_task_setup_blocked_takes_priority_over_worker_revision(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_response = await checker_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={
            "name": "Task Setup Checker Project",
            "slug": "task-setup-checker-project",
            "base_amount": "25.00",
            "currency": "USD",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    guide_payload = complete_guide_payload()
    guide_payload["checker_policy"]["required_checkers"] = [
        "check_acceptance_criteria_present"
    ]
    guide_response = await checker_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=guide_payload,
    )
    assert guide_response.status_code == 201, guide_response.text
    activation_response = await checker_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide_response.json()['id']}/activate",
        headers=auth_headers(),
    )
    assert activation_response.status_code == 200, activation_response.text
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.acceptance_criteria = None
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, body = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])
    assert body["routing_recommendation"] == "task_setup_blocked"
    assert body["outcome_source"] == "auto_checker"
    setup_result = next(
        result
        for result in body["results"]
        if result["checker_name"] == "check_acceptance_criteria_present"
    )
    assert setup_result["status"] == "failed"
    assert setup_result["blocks_review"] is True
    assert setup_result["worker_visible"] is False
    assert setup_result["worker_message"] is None
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
    assert task is not None
    assert task.status == "auto_checking"
    manager_audit = await checker_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert manager_audit.status_code == 200, manager_audit.text
    manager_events = {event["event_type"]: event for event in manager_audit.json()}
    assert "pre_review_gate_blocked" in manager_events
    assert manager_events["pre_review_gate_blocked"]["event_payload"]["routing_recommendation"] == (
        "task_setup_blocked"
    )
    assert manager_events["pre_review_gate_blocked"]["event_payload"]["trigger_source"] == (
        "submission_locked"
    )

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    worker_read = await checker_client.get(
        f"/api/v1/checker-runs/{body['id']}",
        headers=auth_headers(),
    )
    assert worker_read.status_code == 200, worker_read.text
    worker_body = worker_read.json()
    assert worker_body["routing_recommendation"] == "not_evaluated"
    assert worker_body["outcome_source"] == "none"
    assert worker_body["passed_count"] == 0
    assert worker_body["warning_count"] == 0
    assert worker_body["failed_count"] == 0
    assert worker_body["blocking_count"] == 0
    assert worker_body["results"] == []
    assert "task_setup_blocked" not in worker_read.text
    assert "acceptance_criteria" not in worker_read.text

    worker_audit = await checker_client.get(
        f"/api/v1/tasks/{started_task['id']}/audit-events",
        headers=auth_headers(),
    )
    assert worker_audit.status_code == 200, worker_audit.text
    assert "task_setup_blocked" not in worker_audit.text
    assert "acceptance_criteria" not in worker_audit.text
    assert "routing_recommendation" not in worker_audit.text
    assert "checker_run_id" not in worker_audit.text

    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
        assert task is not None
        task.acceptance_criteria = "Worker output must satisfy the project rubric."
        await session.commit()

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    retry = await checker_client.post(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "task setup repaired"},
    )
    assert retry.status_code == 200, retry.text
    retry_body = retry.json()
    assert retry_body["attempt_number"] == 2
    assert retry_body["supersedes_checker_run_id"] == body["id"]
    assert retry_body["routing_recommendation"] == "allow_review"
    assert retry_body["trigger_source"] == "manual_checker_trigger"
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
    assert task is not None
    assert task.status == "review_pending"


async def test_worker_can_read_only_worker_visible_checker_result_fields(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, run = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    read = await checker_client.get(
        f"/api/v1/checker-runs/{run['id']}",
        headers=auth_headers(),
    )

    assert read.status_code == 200, read.text
    body = read.json()
    assert body["failure_message"] is None
    assert body["triggered_by"] is None
    assert body["triggered_by_subject"] is None
    assert body["triggered_by_issuer"] is None
    assert body["trigger_auth_source"] is None
    assert body["trigger_reason"] is None
    assert body["audit_event_id"] is None
    assert body["locked_guide_version"] is None
    assert body["locked_checker_policy_version"] is None
    assert body["locked_review_policy_version"] is None
    assert body["locked_revision_policy_version"] is None
    assert body["locked_payment_policy_version"] is None
    assert body["package_hash"] is None
    assert body["artifact_hash_manifest"] == []
    assert body["artifact_manifest_hash"] is None
    assert body["results"]
    assert all(result["message"] is None for result in body["results"])
    assert all(result["metadata"] == {} for result in body["results"])
    assert all(result["worker_visible"] is True for result in body["results"])


async def test_worker_cannot_see_hidden_checker_results(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    _, run = await lock_submission_and_get_auto_run(checker_client, created.json()["id"])

    async with db_session.get_session_factory()() as session:
        session.add(
            CheckerResult(
                id="hidden-result",
                checker_run_id=run["id"],
                task_id=started_task["id"],
                submission_id=created.json()["id"],
                checker_name="internal_hidden_checker",
                status="failed",
                severity="high",
                blocks_review=True,
                message="internal stack and private path",
                worker_message=None,
                worker_suggested_fix=None,
                worker_evidence_refs=[],
                worker_visible=False,
                metadata_json={"private_path": "local://private/hidden"},
            )
        )
        await session.commit()

    manager_read = await checker_client.get(
        f"/api/v1/checker-runs/{run['id']}",
        headers=auth_headers(),
    )
    assert manager_read.status_code == 200, manager_read.text
    assert "internal_hidden_checker" in {
        result["checker_name"] for result in manager_read.json()["results"]
    }

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    worker_read = await checker_client.get(
        f"/api/v1/checker-runs/{run['id']}",
        headers=auth_headers(),
    )
    assert worker_read.status_code == 200, worker_read.text
    worker_names = {result["checker_name"] for result in worker_read.json()["results"]}
    assert "internal_hidden_checker" not in worker_names


async def test_checker_endpoints_reject_unassigned_worker_and_fake_result_payloads(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    payload = complete_submission_payload()
    payload["status"] = "completed"
    payload["routing_recommendation"] = "allow_review"
    payload["results"] = [{"checker_name": "fake", "status": "passed"}]

    fake_precheck = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submission-precheck",
        headers=auth_headers(),
        json={"submission": payload},
    )
    assert fake_precheck.status_code == 422

    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    await lock_submission_and_get_auto_run(checker_client, created.json()["id"])
    fake_run = await checker_client.post(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={
            "trigger_reason": "manual checker dry run",
            "status": "completed",
            "routing_recommendation": "allow_review",
            "results": [{"checker_name": "fake", "status": "passed"}],
        },
    )
    assert fake_run.status_code == 422
    blank_reason = await checker_client.post(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "   "},
    )
    assert blank_reason.status_code == 422

    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    worker_run = await checker_client.post(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "worker tries to trigger"},
    )
    assert worker_run.status_code == 403

    await seed_worker_profile("worker-two")
    set_dev_actor(monkeypatch, roles="worker", subject="worker-two")
    denied = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submission-precheck",
        headers=auth_headers(),
        json={"submission": complete_submission_payload()},
    )
    assert denied.status_code == 404

    set_dev_actor(monkeypatch, roles="auditor", subject="auditor-subject")
    no_role_existing = await checker_client.get(
        f"/api/v1/submissions/{created.json()['id']}/checker-runs",
        headers=auth_headers(),
    )
    no_role_missing = await checker_client.get(
        "/api/v1/submissions/00000000-0000-0000-0000-000000000000/checker-runs",
        headers=auth_headers(),
    )
    assert no_role_existing.status_code == 403
    assert no_role_missing.status_code == 403

    async with db_session.get_session_factory()() as session:
        rows = (await session.execute(select(CheckerRun))).scalars().all()
    assert len(rows) == 1
    assert rows[0].trigger_source == "submission_locked"


async def test_stale_locked_submission_cannot_receive_checker_run(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_active_project(checker_client)
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    first_payload = complete_submission_payload()
    first_payload["artifact_hash_manifest"] = [
        {
            "artifact": "other.md",
            "hash": "sha256:other-v1",
            "size_bytes": 128,
            "notes": "missing required file so worker can submit v2",
        }
    ]
    first = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=first_payload,
    )
    assert first.status_code == 201, first.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    locked_first = await checker_client.post(
        f"/api/v1/submissions/{first.json()['id']}/lock",
        headers=auth_headers(),
    )
    assert locked_first.status_code == 200, locked_first.text
    first_runs = await checker_client.get(
        f"/api/v1/submissions/{first.json()['id']}/checker-runs",
        headers=auth_headers(),
    )
    assert first_runs.status_code == 200, first_runs.text
    assert first_runs.json()[0]["routing_recommendation"] == "needs_revision"
    set_dev_actor(monkeypatch, roles="worker", subject="worker-one")
    second_payload = complete_submission_payload("sha256:package-v2")
    second_payload["artifact_hash_manifest"][0]["hash"] = "sha256:answer-v2"
    second = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=second_payload,
    )
    assert second.status_code == 201, second.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    stale_run = await checker_client.post(
        f"/api/v1/submissions/{first.json()['id']}/checker-runs",
        headers=auth_headers(),
        json={"trigger_reason": "stale run"},
    )

    assert stale_run.status_code == 409
    assert "latest submission" in stale_run.json()["detail"]

    _, second_run = await lock_submission_and_get_auto_run(checker_client, second.json()["id"])
    assert second_run["submission_version"] == 2
    assert second_run["trigger_source"] == "submission_locked"
    assert second_run["routing_recommendation"] == "allow_review"
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, started_task["id"])
    assert task is not None
    assert task.status == "review_pending"

    async with db_session.get_session_factory()() as session:
        submissions = (
            await session.execute(
                select(Submission).where(Submission.id == first.json()["id"])
            )
        ).scalars().all()
    assert submissions[0].version == 1


@pytest.mark.parametrize(
    "old_checker_name",
    ["check_evidence_references_present", "check_artifact_manifest_integrity"],
)
async def test_old_checker_name_blocks_durable_run_without_alias(
    checker_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    old_checker_name: str,
) -> None:
    project_response = await checker_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={
            "name": "Old Checker Name Project",
            "slug": "old-checker-name-project",
            "base_amount": "25.00",
            "currency": "USD",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    guide_payload = complete_guide_payload()
    guide_payload["checker_policy"]["required_checkers"] = [old_checker_name]
    guide_response = await checker_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json=guide_payload,
    )
    assert guide_response.status_code == 201, guide_response.text
    activation_response = await checker_client.post(
        f"/api/v1/projects/{project['id']}/guides/{guide_response.json()['id']}/activate",
        headers=auth_headers(),
    )
    assert activation_response.status_code == 200, activation_response.text
    started_task = await create_started_task(checker_client, project["id"], monkeypatch)
    created = await checker_client.post(
        f"/api/v1/tasks/{started_task['id']}/submissions",
        headers=auth_headers(),
        json=complete_submission_payload(),
    )
    assert created.status_code == 201, created.text
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    locked = await checker_client.post(
        f"/api/v1/submissions/{created.json()['id']}/lock",
        headers=auth_headers(),
    )
    assert locked.status_code == 422, locked.text
    assert "unregistered checker policy names" in locked.json()["detail"]

    async with db_session.get_session_factory()() as session:
        rows = (await session.execute(CheckerRun.__table__.select())).all()
    assert rows == []
