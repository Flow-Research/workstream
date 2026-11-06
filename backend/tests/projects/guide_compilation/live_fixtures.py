"""Shared source delivery and scripted document ports for live setup proofs."""

import pytest
from sqlalchemy import text

from app.modules.projects.api.guide_compilation import ProjectGuideCompilationDelivery
from .runtime_fixtures import (
    scripted_document_access_runtime,
    scripted_guide_document_parser_factory,
)


@pytest.fixture(autouse=True)
def scripted_document_port(monkeypatch):
    monkeypatch.setenv("WORKSTREAM_CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("WORKSTREAM_CELERY_RESULT_BACKEND", "cache+memory://")
    from app.core.config import get_settings
    get_settings.cache_clear()
    from app.workers import project_setup as worker
    monkeypatch.setattr(
        worker, "guide_document_access_runtime", scripted_document_access_runtime
    )
    monkeypatch.setattr(
        worker, "guide_document_parser_factory", scripted_guide_document_parser_factory
    )


async def _delivery(factory, setup_id):
    """Read the exact dispatch identity committed by the explicit PM request."""
    async with factory() as session:
        row = (await session.execute(text(
            "select project_id,guide_id,source_snapshot_id,setup_generation,celery_task_id "
            "from project_setup_runs where id=:id"
        ), {"id": str(setup_id)})).one()
        assert row.celery_task_id is not None, "explicit PM request must precede delivery"
    return ProjectGuideCompilationDelivery(
        project_id=row.project_id,
        guide_id=row.guide_id,
        source_snapshot_id=row.source_snapshot_id,
        setup_run_id=setup_id,
        setup_generation=row.setup_generation,
        task_id=row.celery_task_id,
    )
