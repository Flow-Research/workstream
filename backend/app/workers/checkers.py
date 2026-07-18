"""Celery tasks for automatic post-submit checker execution."""

from __future__ import annotations

from typing import Any

from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import get_database_url
from app.modules.checkers.service import (
    CheckerExecutionBlocked,
    CheckerService,
    CheckerServiceError,
    pre_review_gate_system_actor,
)
from app.workers.async_runner import run_async_task
from app.workers.celery_app import celery_app

PRE_REVIEW_GATE_TASK = "workstream.checkers.run_pre_review_gate"

logger = get_task_logger(__name__)


@celery_app.task(name=PRE_REVIEW_GATE_TASK)
def run_pre_review_gate(
    checker_run_id: str,
    requester_provenance: dict[str, Any],
) -> dict[str, Any]:
    """Run the automatic post-submit checker gate for one locked submission.

    Args:
        checker_run_id: Queued checker run claim to execute.
        requester_provenance: Minimal audit-safe requester provenance for the
            submitter whose locked submission caused this system-owned gate.

    Returns:
        Machine-readable gate run summary.
    """
    return run_async_task(
        lambda: _run_pre_review_gate(checker_run_id, requester_provenance)
    )


async def _run_pre_review_gate(
    checker_run_id: str,
    requester_provenance: dict[str, Any],
) -> dict[str, Any]:
    """Execute the pre-review gate using a fresh async database session."""
    actor = pre_review_gate_system_actor()
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            try:
                result = await CheckerService(session).run_queued_pre_review_gate(
                    actor,
                    checker_run_id,
                    requester_provenance=requester_provenance,
                )
            except CheckerServiceError as exc:
                if _is_stale_submission_gate(exc):
                    logger.info(
                        "automatic pre-review gate skipped stale submission",
                        extra={"checker_run_id": checker_run_id},
                    )
                    return {
                        "status": "skipped_stale_submission",
                        "submission_id": None,
                        "checker_run_id": checker_run_id,
                        "routing_recommendation": "not_evaluated",
                    }
                logger.warning(
                    "automatic pre-review gate failed",
                    extra={
                        "checker_run_id": checker_run_id,
                        "error_code": exc.__class__.__name__,
                        "error_summary": str(exc)[:250],
                    },
                )
                raise
            return {
                "status": result.status,
                "submission_id": result.submission_id,
                "checker_run_id": result.id,
                "routing_recommendation": result.routing_recommendation,
            }
    finally:
        await engine.dispose()


def _is_stale_submission_gate(exc: CheckerServiceError) -> bool:
    """Return true when a queued gate targets a superseded submission version."""
    return isinstance(exc, CheckerExecutionBlocked) and (
        str(exc) == "only latest submission version can be checked"
    )
