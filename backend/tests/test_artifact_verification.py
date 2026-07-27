"""Focused proof for activated verification, authority, and deadline contracts."""

from __future__ import annotations

import asyncio
import importlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from unittest.mock import AsyncMock, Mock

import app.interfaces.artifact_operations  # noqa: F401 - cumulative contract coverage
from app.core.config import Settings, get_settings
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    ArtifactInternalResourceType,
    ArtifactPendingWorkAuthorityFacts,
    ArtifactPutAttemptAuthorityFacts,
    DenyArtifactInternalAuthority,
)
from app.modules.artifacts.service import ArtifactStorageOrchestrator
from app.modules.authorization.catalogue import ACTION_BY_ID, ActionAvailability, ActionId


@pytest.mark.asyncio
async def test_production_authority_denies_prepare_and_consume() -> None:
    authority = DenyArtifactInternalAuthority()
    facts = ArtifactPutAttemptAuthorityFacts(
        resource_type=ArtifactInternalResourceType.PUT_ATTEMPT,
        resource_id=uuid4(),
        operation_identity="sha256:" + "1" * 64,
        namespace_fingerprint="sha256:" + "2" * 64,
        sha256="sha256:" + "3" * 64,
        byte_count=1,
        executor_id=uuid4(),
        execution_generation=1,
    )
    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.prepare(
            service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
            facts=facts,
            phase="claim",
            idempotency_key=uuid4(),
        )
    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.consume(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=facts,
            )


def test_internal_celery_tasks_and_pending_scan_are_registered_once(monkeypatch) -> None:
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    celery_module = importlib.import_module("app.workers.celery_app")
    worker_module = importlib.import_module("app.workers.artifacts")
    celery_app = celery_module.celery_app
    assert "workstream.artifacts.resolve_put_attempt" in celery_app.tasks
    assert "workstream.artifacts.verify_object" in celery_app.tasks
    assert "workstream.artifacts.scan_pending_work" in celery_app.tasks
    scheduled_tasks = [
        entry["task"] for entry in celery_app.conf.beat_schedule.values()
    ]
    assert scheduled_tasks.count("workstream.artifacts.scan_pending_work") == 1
    assert scheduled_tasks.count("workstream.artifacts.cleanup_stale_scratch") == 1
    operation = AsyncMock(return_value=None)
    scanned: list[str] = []

    async def scan(publish_put, publish_job):
        await publish_put("put-id")
        await publish_job("job-id")
        scanned.append("called")
        return 2

    monkeypatch.setattr(worker_module, "run_artifact_internal_operation", operation)
    monkeypatch.setattr(worker_module, "scan_artifact_pending_work", scan)
    put_delay = Mock()
    job_delay = Mock()
    monkeypatch.setattr(worker_module.resolve_put_attempt, "delay", put_delay)
    monkeypatch.setattr(worker_module.verify_object, "delay", job_delay)
    attempt_id = str(uuid4())
    job_id = str(uuid4())
    worker_module.resolve_put_attempt(attempt_id)
    worker_module.verify_object(job_id)
    assert operation.await_count == 2
    assert operation.await_args_list[0].args == ("put", UUID(attempt_id))
    assert operation.await_args_list[1].args == ("verification", UUID(job_id))
    assert worker_module.scan_pending_work() == 2
    assert scanned == ["called"]
    put_delay.assert_called_once_with("put-id")
    job_delay.assert_called_once_with("job-id")
    get_settings.cache_clear()


def test_internal_artifact_actions_are_active() -> None:
    assert {
        action_id: ACTION_BY_ID[action_id].availability
        for action_id in {
            ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
            ActionId.ARTIFACT_VERIFICATION_EXECUTE,
            ActionId.ARTIFACT_PENDING_WORK_SCAN,
        }
    } == {
        ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE: ActionAvailability.ACTIVE,
        ActionId.ARTIFACT_VERIFICATION_EXECUTE: ActionAvailability.ACTIVE,
        ActionId.ARTIFACT_PENDING_WORK_SCAN: ActionAvailability.ACTIVE,
    }


def test_verification_deadline_and_margin_must_fit_lease() -> None:
    with pytest.raises(ValueError, match="must fit within lease"):
        Settings(
            artifact_execution_lease_seconds=100,
            artifact_complete_read_deadline_seconds=80,
            artifact_terminal_persistence_margin_seconds=20,
        )


@pytest.mark.asyncio
async def test_complete_read_uses_total_deadline_for_progressing_stream() -> None:
    class SlowStore:
        def open(self, _provider_object_ref: str):
            async def chunks():
                while True:
                    await asyncio.sleep(0.02)
                    yield b"x"

            return chunks()

    orchestrator = object.__new__(ArtifactStorageOrchestrator)
    orchestrator._store = SlowStore()  # type: ignore[attr-defined]
    orchestrator._settings = Settings(  # type: ignore[attr-defined]
        artifact_execution_lease_seconds=1,
        artifact_complete_read_deadline_seconds=0.05,
        artifact_terminal_persistence_margin_seconds=0.1,
    )
    with pytest.raises(TimeoutError):
        await orchestrator._read_complete("sha256/" + "a" * 64)


def test_pending_work_facts_are_closed_and_bounded_by_construction() -> None:
    facts = ArtifactPendingWorkAuthorityFacts(
        resource_type=ArtifactInternalResourceType.PENDING_WORK,
        resource_id="workstream:artifact_pending_work",
        scanner_kind="put_resolution",
        database_cutoff_iso=datetime.now(UTC).isoformat(),
        page_size=100,
    )
    assert facts.resource_id == "workstream:artifact_pending_work"
