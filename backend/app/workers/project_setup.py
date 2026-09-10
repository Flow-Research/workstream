"""Celery composition for automatic unified project-guide compilation."""

from celery.utils.log import get_task_logger
from functools import partial
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.project_agents import create_project_guide_runtime
from app.core.config import get_settings
from app.core.project_agents import (
    project_guide_runtime_configuration,
)
from app.db.session import get_database_url
from app.adapters.auth import (
    guide_compilation_request_authority,
    guide_compilation_execution_authority,
    guide_sufficiency_projection_authorization,
    artifact_policy_projection_authorization,
    setup_finalization_authorization,
)
from app.adapters.projects import project_guide_compilation_delivery_port
from app.adapters.checkers import project_guide_pre_submission_catalogue
from app.adapters.artifacts import guide_document_manifest_port, guide_document_access_runtime
from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
from app.modules.projects.api.guide_compilation import (
    ProjectGuideCompilationDelivery,
    ProjectGuideCompilationDeliveryError,
)
from app.workers.async_runner import run_async_task
from app.workers.celery_app import celery_app

PROJECT_GUIDE_COMPILATION_TASK = "workstream.project_setup.compile_project_guide"
logger = get_task_logger(__name__)


def _coordinator(session_factory):
    """Compose owner ports and the sole registered runtime at the worker boundary."""
    return project_guide_compilation_delivery_port(
        session_factory,
        material_factory=guide_document_manifest_port,
        document_access_factory=partial(guide_document_access_runtime, session_factory),
        pre_capabilities=project_guide_pre_submission_catalogue(),
        post_capabilities=current_post_submit_catalogue(),
        request_authority=guide_compilation_request_authority,
        execution_authority=guide_compilation_execution_authority,
        configuration_factory=lambda: project_guide_runtime_configuration(get_settings()),
        runtime_factory=create_project_guide_runtime,
        sufficiency_authorization_factory=guide_sufficiency_projection_authorization,
        policy_authorization_factory=artifact_policy_projection_authorization,
        finalization_authorization_factory=setup_finalization_authorization,
    )


@celery_app.task(
    name=PROJECT_GUIDE_COMPILATION_TASK, bind=True, acks_late=True, reject_on_worker_lost=True
)
def run_project_guide_compilation(
    self, project_id, guide_id, source_snapshot_id, setup_run_id, setup_generation
):
    """Deliver one exact generation using the broker-bound task ID."""
    try:
        delivery = ProjectGuideCompilationDelivery(
            project_id=project_id,
            guide_id=guide_id,
            source_snapshot_id=source_snapshot_id,
            setup_run_id=setup_run_id,
            setup_generation=setup_generation,
            task_id=self.request.id,
        )
    except (TypeError, ValueError):
        return {"status": "delivery_rejected", "error_code": "invalid_compilation_delivery"}
    outcome = run_async_task(lambda: _run_project_guide_compilation(delivery))
    if outcome["status"] == "compilation_unavailable":
        # Celery preserves this delivery's ID and arguments. The durable attempt
        # fence, not the transport retry count, prevents a second provider call.
        raise self.retry(
            exc=RuntimeError("project guide compilation unavailable"),
            countdown=30 * (2**self.request.retries),
            max_retries=3,
        )
    return outcome


async def _run_project_guide_compilation(delivery: ProjectGuideCompilationDelivery) -> dict:
    """Own the worker connection lifecycle and return only bounded failures."""
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    try:
        return await _coordinator(async_sessionmaker(engine, expire_on_commit=False)).run(delivery)
    except ProjectGuideCompilationDeliveryError:
        return {"status": "delivery_rejected", "error_code": "stale_compilation_delivery"}
    except Exception:
        logger.warning(
            "project guide compilation stopped", extra={"setup_run_id": str(delivery.setup_run_id)}
        )
        return {
            "status": "compilation_unavailable",
            "error_code": "project_guide_compilation_unavailable",
        }
    finally:
        await engine.dispose()


@celery_app.task(name="workstream.project_setup.cleanup_runtime_resources")
def cleanup_guide_runtime_resources():
    """Recover exact provider-resource deletion without delivering a setup attempt."""
    return run_async_task(_cleanup_guide_runtime_resources)


async def _cleanup_guide_runtime_resources():
    """Keep SDK and PROJECTS internals behind their public composition boundaries."""
    from app.adapters.projects import cleanup_project_guide_runtime_resources

    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    try:
        return await cleanup_project_guide_runtime_resources(
            async_sessionmaker(engine, expire_on_commit=False),
            runtime_factory=create_project_guide_runtime,
        )
    finally:
        await engine.dispose()
