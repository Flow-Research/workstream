"""Celery composition for explicitly requested guide compilation."""

from functools import partial
from pathlib import Path

from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import guide_document_access_runtime, guide_document_manifest_port
from app.adapters.auth import (
    artifact_policy_projection_authorization,
    guide_compilation_execution_authority,
    guide_sufficiency_projection_authorization,
    setup_finalization_authorization,
)
from app.adapters.guide_document_tools import (
    GUIDE_DOCUMENT_PARSER_PROVIDER_KEY,
    guide_document_parser_factory,
)
from app.adapters.project_agents import (
    RETAINED_OPENAI_GUIDE_RUNTIME_KEY,
    create_guide_runtime_cleanup_factory,
    create_project_guide_runtime,
)
from app.adapters.project_agents.setup_model_proxy import setup_model_session_factory
from app.adapters.projects import (
    project_guide_compilation_delivery_port,
    project_guide_document_tools_factory,
)
from app.core.config import get_settings
from app.db.session import get_database_url
from app.modules.projects.api.guide_compilation import (
    ProjectGuideCompilationDelivery,
    ProjectGuideCompilationDeliveryError,
)
from app.workers.async_runner import run_async_task
from app.workers.celery_app import celery_app
from app.workers.project_setup_topology import (
    PROJECT_GUIDE_HARD_LIMIT_SECONDS,
    require_project_setup_worker,
)

PROJECT_GUIDE_COMPILATION_TASK = "workstream.project_setup.compile_project_guide"
logger = get_task_logger(__name__)


async def _coordinator(session_factory):
    """Compose owner ports and the configured runtime at the worker boundary."""
    settings = get_settings()
    return project_guide_compilation_delivery_port(
        session_factory,
        material_factory=guide_document_manifest_port,
        document_tools_factory=project_guide_document_tools_factory(
            session_factory,
            document_access_factory=partial(guide_document_access_runtime, session_factory),
            parser_factory=lambda: guide_document_parser_factory(
                socket_path=Path(settings.guide_document_parser_socket),
                timeout_seconds=30.0,
            ).create(GUIDE_DOCUMENT_PARSER_PROVIDER_KEY),
        ),
        model_session_factory=setup_model_session_factory(
            sessions=session_factory,
            socket_path=settings.checker_model_proxy_socket,
        ),
        execution_authority=guide_compilation_execution_authority,
        runtime_factory=create_project_guide_runtime,
        sufficiency_authorization_factory=guide_sufficiency_projection_authorization,
        policy_authorization_factory=artifact_policy_projection_authorization,
        finalization_authorization_factory=setup_finalization_authorization,
    )


@celery_app.task(
    name=PROJECT_GUIDE_COMPILATION_TASK,
    bind=True,
    acks_late=True,
    acks_on_failure_or_timeout=True,
    reject_on_worker_lost=True,
    time_limit=PROJECT_GUIDE_HARD_LIMIT_SECONDS,
)
def run_project_guide_compilation(
    self, project_id, guide_id, source_snapshot_id, setup_run_id, setup_generation
):
    """Deliver one exact generation using the broker-bound task ID."""
    require_project_setup_worker(self)
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
        coordinator = await _coordinator(async_sessionmaker(engine, expire_on_commit=False))
        return await coordinator.run(delivery)
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
    cleanup_adapters = create_guide_runtime_cleanup_factory()
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    try:
        return await cleanup_project_guide_runtime_resources(
            async_sessionmaker(engine, expire_on_commit=False),
            retained_runtime_key=RETAINED_OPENAI_GUIDE_RUNTIME_KEY,
            cleanup_adapter_factory=cleanup_adapters,
        )
    finally:
        await engine.dispose()
