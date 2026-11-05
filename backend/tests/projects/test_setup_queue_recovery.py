"""Explicit guide setup dispatch failure and stale publication recovery."""

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db import session as db_session
from app.modules.projects import api as project_setup_identity
from app.modules.projects import setup_queue as project_setup_queue_module
from app.modules.projects.models import ProjectSetupRun
from app.modules.projects.setup_queue import ProjectSetupQueueError
from tests.committed_guide_fixtures import create_committed_document_fixture
from tests.projects.client_fixtures import (
    project_client as project_client, project_database_env as project_database_env, auth_headers,
)
from tests.projects.guide_fixtures import complete_guide_payload, create_project, create_guide


async def test_explicit_setup_request_enqueue_failure_is_sanitized_and_retryable(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()

    def fail_enqueue(**_: object) -> str:
        raise ProjectSetupQueueError(
            "broker rejected https://storage.flow.test/signed?token=secret"
        )

    monkeypatch.setattr(
        project_setup_queue_module, "enqueue_project_guide_compilation", fail_enqueue
    )
    project = await create_project(project_client)
    guide = await create_guide(
        project_client,
        project["id"],
        {
            **complete_guide_payload(),
            "documents": complete_guide_payload()["documents"],
        },
    )

    async with db_session.get_session_factory()() as session:
        run = await session.scalar(
            select(ProjectSetupRun).where(ProjectSetupRun.guide_id == guide["id"])
        )
        assert run is not None
        source_snapshot_id = run.source_snapshot_id
        await session.commit()
        await create_committed_document_fixture(source_snapshot_id)
        from tests.projects.guide_compilation.pending_source import request_pending_source
        from tests.projects.guide_compilation.helpers import manager_runtime_configuration
        await request_pending_source(
            db_session.get_session_factory(), UUID(run.id), manager_runtime_configuration()
        )
        await project_setup_queue_module.dispatch_project_guide_compilation_after_commit(
            session, project_id=run.project_id, guide_id=run.guide_id,
            source_snapshot_id=run.source_snapshot_id, setup_run_id=run.id,
            setup_generation=run.setup_generation,
            claimed_task_id=project_setup_identity.project_guide_compilation_task_id(run.id, run.setup_generation),
        )

    response = await project_client.get(
        f"/api/v1/projects/{project['id']}/guides/{guide['id']}/setup-runs/latest",
        headers=auth_headers(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "enqueue_failed"
    assert body["current_step"] == "enqueue"
    assert body["celery_task_id"] is None
    assert body["error_code"] == "ProjectSetupQueueError"
    assert body["error_summary"] == "project setup failed"
    assert "token" not in body["error_summary"]
    assert "https://" not in body["error_summary"]

    monkeypatch.setattr(
        project_setup_queue_module,
        "enqueue_project_guide_compilation",
        lambda **facts: cast(str, facts["task_id"]),
    )
    async with db_session.get_session_factory()() as session:
        task_id = await project_setup_queue_module.dispatch_project_guide_compilation_after_commit(
            session,
            project_id=run.project_id,
            guide_id=run.guide_id,
            source_snapshot_id=run.source_snapshot_id,
            setup_run_id=run.id,
            setup_generation=run.setup_generation,
        )
    expected_task_id = project_setup_identity.project_guide_compilation_task_id(
        run.id, run.setup_generation
    )
    assert task_id == expected_task_id
    async with db_session.get_session_factory()() as session:
        recovered = await session.get(ProjectSetupRun, run.id)
        assert recovered is not None
        assert recovered.status == "queued"
        assert recovered.celery_task_id == expected_task_id
        assert recovered.error_code is None


async def test_dispatch_pending_republishes_only_after_stale_cutoff(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    project = await create_project(project_client)
    guide = await create_guide(
        project_client,
        project["id"],
        {**complete_guide_payload(), "documents": complete_guide_payload()["documents"]},
    )
    published: list[str | None] = []

    def capture_enqueue(**facts: object) -> str:
        published.append(cast(str | None, facts["task_id"]))
        return cast(str, facts["task_id"])

    monkeypatch.setattr(
        project_setup_queue_module,
        "enqueue_project_guide_compilation",
        capture_enqueue,
    )
    async with db_session.get_session_factory()() as session:
        run = await session.scalar(
            select(ProjectSetupRun).where(ProjectSetupRun.guide_id == guide["id"])
        )
        assert run is not None
        from tests.projects.guide_compilation.pending_source import request_pending_source
        from tests.projects.guide_compilation.helpers import manager_runtime_configuration
        await session.commit()
        await create_committed_document_fixture(run.source_snapshot_id)
        await request_pending_source(
            db_session.get_session_factory(), UUID(run.id), manager_runtime_configuration()
        )
        await session.refresh(run)
        run.status = "dispatch_pending"
        run.celery_task_id = project_setup_identity.project_guide_compilation_task_id(
            run.id, run.setup_generation
        )
        run.updated_at = datetime.now(UTC)
        await session.commit()
        fresh = await project_setup_queue_module.dispatch_project_guide_compilation_after_commit(
            session,
            project_id=run.project_id,
            guide_id=run.guide_id,
            source_snapshot_id=run.source_snapshot_id,
            setup_run_id=run.id,
            setup_generation=run.setup_generation,
        )
        assert fresh == run.celery_task_id
        assert published == []
        stale_updated_at = datetime.now(UTC) - timedelta(seconds=61)
        run.updated_at = stale_updated_at
        await session.commit()
        stale = await project_setup_queue_module.dispatch_project_guide_compilation_after_commit(
            session,
            project_id=run.project_id,
            guide_id=run.guide_id,
            source_snapshot_id=run.source_snapshot_id,
            setup_run_id=run.id,
            setup_generation=run.setup_generation,
        )
    assert stale == run.celery_task_id
    assert published == [run.celery_task_id]
    async with db_session.get_session_factory()() as session:
        reclaimed = await session.get(ProjectSetupRun, run.id)
        assert reclaimed is not None
        assert reclaimed.updated_at > stale_updated_at
