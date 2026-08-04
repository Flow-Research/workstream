"""Celery tasks for automatic project guide setup."""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import get_database_url
from app.interfaces.artifact_operations import GuideSufficiencyMaterialUnavailable
from app.modules.artifacts.guide_sufficiency_material import (
    SqlAlchemyGuideSufficiencyMaterialAdapter,
)
from app.modules.projects.service import (
    PolicySetupBlocked,
    PolicySetupConflict,
    ProjectService,
    ProjectServiceError,
    StaleProjectSetupContinuation,
    safe_project_setup_error_summary,
)
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.authorization.prepared import fixed_service_prepared_authorization
from app.modules.projects.sufficiency_mutation_service import GuideSufficiencyMutationService
from app.modules.projects.setup_queue import pre_submit_setup_task_id
from app.schemas.auth import ActorContext
from app.workers.async_runner import run_async_task
from app.workers.celery_app import celery_app

PROJECT_SETUP_PIPELINE_ACTOR_ID = "workstream-system:project-setup-pipeline"
PROJECT_SETUP_PIPELINE_TASK = "workstream.project_setup.run_pre_submit_setup_pipeline"
PROJECT_SETUP_POST_SUBMIT_CONTINUATION_TASK = (
    "workstream.project_setup.run_post_submit_setup_continuation"
)

logger = get_task_logger(__name__)


async def _run_authorized_setup_sufficiency(
    session,
    *,
    project_id: str,
    guide_id: str,
    source_snapshot_id: str,
    setup_run_id: str,
    setup_generation: int,
):
    """Compose the exact fixed-service command for one verified sufficiency run."""
    mutation = GuideSufficiencyMutationService(
        session,
        material=SqlAlchemyGuideSufficiencyMaterialAdapter(session),
    )
    execution_name = pre_submit_setup_task_id(setup_run_id, setup_generation)
    task_id = UUID(execution_name)
    correlation_id = uuid5(NAMESPACE_URL, f"{execution_name}:correlation")
    custody = await mutation.resolve_setup_service_custody(
        project_id=UUID(project_id),
        guide_id=UUID(guide_id),
        source_snapshot_id=UUID(source_snapshot_id),
        setup_run_id=UUID(setup_run_id),
        setup_generation=setup_generation,
        task_id=task_id,
        correlation_id=correlation_id,
    )
    async with fixed_service_prepared_authorization(
        session,
        service_identity=ServiceIdentity.PROJECT_SETUP,
        request_id=task_id,
        correlation_id=correlation_id,
    ) as authority:
        execution = mutation.run_setup_service(
            actor_profile_id=authority.actor_profile_id,
            identity_link_id=authority.identity_link_id,
            prepared=authority.service,
            project_id=UUID(project_id),
            guide_id=UUID(guide_id),
            source_snapshot_id=UUID(source_snapshot_id),
            custody=custody,
        )
        async with execution as outcome:
            await (session.rollback() if outcome.replayed else session.commit())
    return outcome


def project_setup_pipeline_actor() -> ActorContext:
    """Return the internal actor used for server-owned setup automation."""
    return ActorContext(
        actor_id=PROJECT_SETUP_PIPELINE_ACTOR_ID,
        external_subject=PROJECT_SETUP_PIPELINE_ACTOR_ID,
        external_issuer="workstream-internal",
        email=None,
        display_name="Workstream Project Setup Pipeline",
        roles=("admin", "project_manager"),
        claim_snapshot={"system_actor": True, "pipeline": "project_setup"},
        auth_source="workstream_system",
        is_dev_auth=False,
    )


@celery_app.task(name=PROJECT_SETUP_PIPELINE_TASK)
def run_pre_submit_setup_pipeline(
    project_id: str,
    guide_id: str,
    source_snapshot_id: str,
    setup_run_id: str,
    setup_generation: int,
) -> dict[str, Any]:
    """Run guide sufficiency and policy derivation for a source snapshot.

    Args:
        project_id: Project that owns the guide.
        guide_id: Guide whose latest source snapshot should be processed.
        source_snapshot_id: Immutable source snapshot to analyze.
        setup_run_id: Project setup run ledger row to update.
        setup_generation: Exact generation associated with this setup run.

    Returns:
        Machine-readable terminal pipeline state.
    """
    return run_async_task(
        lambda: _run_pre_submit_setup_pipeline(
            project_id,
            guide_id,
            source_snapshot_id,
            setup_run_id,
            setup_generation,
        )
    )


@celery_app.task(name=PROJECT_SETUP_POST_SUBMIT_CONTINUATION_TASK)
def run_post_submit_setup_continuation(
    project_id: str,
    guide_id: str,
    source_snapshot_id: str,
    setup_run_id: str,
    effective_policy_id: str,
    pre_submit_checker_policy_id: str,
) -> dict[str, Any]:
    """Resume setup after pre-submit policy approval and compilation.

    Args:
        project_id: Project that owns the guide.
        guide_id: Guide whose latest source snapshot should be processed.
        source_snapshot_id: Immutable source snapshot to analyze.
        setup_run_id: Existing project setup run ledger row to update.
        effective_policy_id: Effective submission artifact policy id.
        pre_submit_checker_policy_id: Compiled pre-submit checker policy id.

    Returns:
        Machine-readable terminal continuation state.
    """
    return run_async_task(
        lambda: _run_post_submit_setup_continuation(
            project_id,
            guide_id,
            source_snapshot_id,
            setup_run_id,
            effective_policy_id,
            pre_submit_checker_policy_id,
        )
    )


async def _run_pre_submit_setup_pipeline(
    project_id: str,
    guide_id: str,
    source_snapshot_id: str,
    setup_run_id: str,
    setup_generation: int,
) -> dict[str, Any]:
    """Execute only the verified same-generation project setup pipeline."""
    return await _run_verified_pre_submit_sufficiency_continuation(
        project_id,
        guide_id,
        source_snapshot_id,
        setup_run_id,
        setup_generation,
    )


async def _run_verified_pre_submit_sufficiency_continuation(
    project_id: str,
    guide_id: str,
    source_snapshot_id: str,
    setup_run_id: str,
    setup_generation: int,
) -> dict[str, Any]:
    """Run the live ART-backed same-generation sufficiency continuation."""
    actor = project_setup_pipeline_actor()
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            service = ProjectService(session)
            expected_task_id = pre_submit_setup_task_id(setup_run_id, setup_generation)
            try:
                await service.validate_project_setup_run_context(
                    setup_run_id,
                    project_id=project_id,
                    guide_id=guide_id,
                    source_snapshot_id=source_snapshot_id,
                    setup_generation=setup_generation,
                    celery_task_id=expected_task_id,
                )
            except ProjectServiceError:
                await session.rollback()
                logger.warning(
                    "stale project setup delivery rejected",
                    exc_info=True,
                    extra={
                        "project_id": project_id,
                        "guide_id": guide_id,
                        "source_snapshot_id": source_snapshot_id,
                        "setup_run_id": setup_run_id,
                        "error_code": "project_setup_run_context_mismatch",
                        "error_summary": "project setup delivery rejected",
                    },
                )
                return {
                    "status": "stale_delivery_rejected",
                    "guide_sufficiency_report_id": None,
                    "submission_artifact_policy_id": None,
                }
            try:
                await service.update_project_setup_run_status(
                    setup_run_id,
                    status="running_sufficiency_agent",
                    current_step="guide_sufficiency",
                )
                sufficiency_outcome = await _run_authorized_setup_sufficiency(
                    session,
                    project_id=project_id,
                    guide_id=guide_id,
                    source_snapshot_id=source_snapshot_id,
                    setup_run_id=setup_run_id,
                    setup_generation=setup_generation,
                )
                sufficiency_report = sufficiency_outcome.response
                if sufficiency_report.status == "blocked":
                    await service.update_project_setup_run_status(
                        setup_run_id,
                        status="sufficiency_blocked",
                        current_step="guide_sufficiency",
                        output_sufficiency_report_id=sufficiency_report.id,
                    )
                    return {
                        "status": "sufficiency_blocked",
                        "guide_sufficiency_report_id": sufficiency_report.id,
                        "submission_artifact_policy_id": None,
                    }
                await service.update_project_setup_run_status(
                    setup_run_id,
                    status="running_policy_derivation_agent",
                    current_step="submission_artifact_policy_derivation",
                    output_sufficiency_report_id=sufficiency_report.id,
                )
                policy, _ = await service.run_submission_artifact_policy_derivation_agent(
                    actor,
                    project_id,
                    guide_id,
                    source_snapshot_id,
                )
                await service.update_project_setup_run_status(
                    setup_run_id,
                    status="policy_draft_ready",
                    current_step="submission_artifact_policy_derivation",
                    output_sufficiency_report_id=sufficiency_report.id,
                    output_submission_artifact_policy_id=policy.id,
                )
                return {
                    "status": "policy_draft_ready",
                    "guide_sufficiency_report_id": sufficiency_report.id,
                    "submission_artifact_policy_id": policy.id,
                }
            except GuideSufficiencyMaterialUnavailable as exc:
                await session.rollback()
                public_error = "project setup failed; inspect server logs with the setup run id"
                await service.update_project_setup_run_status(
                    setup_run_id,
                    status="setup_blocked",
                    current_step="guide_sufficiency",
                    error_code=exc.code,
                    error_artifact_incident_id=(
                        str(exc.incident_id) if exc.incident_id is not None else None
                    ),
                    error_summary=public_error,
                )
                return {
                    "status": "setup_blocked",
                    "error_code": exc.code,
                    "guide_sufficiency_report_id": None,
                }
            except ProjectServiceError as exc:
                error_code = (
                    "guide_source_material_changed"
                    if isinstance(exc, PolicySetupConflict)
                    else "verified_guide_sufficiency_unavailable"
                    if isinstance(exc, PolicySetupBlocked)
                    else "guide_source_stale"
                )
                public_error = "project setup failed; inspect server logs with the setup run id"
                logger.warning(
                    "project setup pipeline stopped",
                    exc_info=True,
                    extra={
                        "project_id": project_id,
                        "guide_id": guide_id,
                        "source_snapshot_id": source_snapshot_id,
                        "setup_run_id": setup_run_id,
                        "error_code": exc.__class__.__name__,
                        "error_summary": public_error,
                    },
                )
                await service.update_project_setup_run_status(
                    setup_run_id,
                    status="setup_blocked",
                    current_step="guide_sufficiency",
                    error_code=error_code,
                    error_summary=public_error,
                )
                return {
                    "status": "setup_blocked",
                    "error_code": error_code,
                    "guide_sufficiency_report_id": None,
                }
            except Exception as exc:
                public_error = "unexpected project setup pipeline failure"
                logger.error(
                    "project setup pipeline failed",
                    exc_info=True,
                    extra={
                        "project_id": project_id,
                        "guide_id": guide_id,
                        "source_snapshot_id": source_snapshot_id,
                        "setup_run_id": setup_run_id,
                        "error_code": exc.__class__.__name__,
                        "error_summary": public_error,
                    },
                )
                await service.update_project_setup_run_status(
                    setup_run_id,
                    status="setup_blocked",
                    current_step="guide_sufficiency",
                    error_code="project_setup_failed",
                    error_summary=public_error,
                )
                return {
                    "status": "setup_blocked",
                    "error_code": "project_setup_failed",
                    "guide_sufficiency_report_id": None,
                }
    finally:
        await engine.dispose()


async def _run_post_submit_setup_continuation(
    project_id: str,
    guide_id: str,
    source_snapshot_id: str,
    setup_run_id: str,
    effective_policy_id: str,
    pre_submit_checker_policy_id: str,
) -> dict[str, Any]:
    """Execute post-submit setup continuation using async service contracts."""
    actor = project_setup_pipeline_actor()
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            service = ProjectService(
                session,
                guide_sufficiency_material=SqlAlchemyGuideSufficiencyMaterialAdapter(session),
            )
            try:
                start_status = await service.start_post_submit_setup_continuation(
                    setup_run_id,
                    project_id=project_id,
                    guide_id=guide_id,
                    source_snapshot_id=source_snapshot_id,
                    effective_policy_id=effective_policy_id,
                    pre_submit_checker_policy_id=pre_submit_checker_policy_id,
                )
                if start_status == "already_compiled":
                    setup_run = await service.validate_project_setup_run_context(
                        setup_run_id,
                        project_id=project_id,
                        guide_id=guide_id,
                        source_snapshot_id=source_snapshot_id,
                    )
                    return {
                        "status": "post_submit_policy_compiled",
                        "idempotent": True,
                        "post_submit_checker_policy_id": (
                            setup_run.output_post_submit_checker_policy_id
                        ),
                    }
                policy, _, summary = await service.run_post_submit_checker_policy_derivation_agent(
                    actor,
                    project_id,
                    guide_id,
                    source_snapshot_id,
                    effective_policy_id,
                    pre_submit_checker_policy_id,
                    setup_run_id,
                )
                await service.update_project_setup_run_status(
                    setup_run_id,
                    status="post_submit_policy_compiled",
                    current_step="post_submit_checker_policy_compilation",
                    output_post_submit_checker_policy_id=policy.id,
                    post_submit_derivation_summary=summary
                    | {"post_submit_checker_policy_id": policy.id},
                    continuation_effective_policy_id=effective_policy_id,
                    continuation_pre_submit_checker_policy_id=pre_submit_checker_policy_id,
                )
                return {
                    "status": "post_submit_policy_compiled",
                    "idempotent": False,
                    "post_submit_checker_policy_id": policy.id,
                }
            except StaleProjectSetupContinuation as exc:
                logger.info(
                    "stale project setup post-submit continuation ignored",
                    extra={
                        "project_id": project_id,
                        "guide_id": guide_id,
                        "source_snapshot_id": source_snapshot_id,
                        "setup_run_id": setup_run_id,
                        "error_code": exc.__class__.__name__,
                    },
                )
                return {
                    "status": "stale_post_submit_continuation_ignored",
                    "idempotent": True,
                    "post_submit_checker_policy_id": None,
                }
            except ProjectServiceError as exc:
                public_error = safe_project_setup_error_summary(str(exc))
                logger.warning(
                    "project setup post-submit continuation stopped",
                    extra={
                        "project_id": project_id,
                        "guide_id": guide_id,
                        "source_snapshot_id": source_snapshot_id,
                        "setup_run_id": setup_run_id,
                        "error_code": exc.__class__.__name__,
                        "error_summary": public_error,
                    },
                )
                try:
                    status_response = await service.update_project_setup_run_status(
                        setup_run_id,
                        status="post_submit_setup_blocked",
                        current_step="post_submit_checker_policy_derivation",
                        error_code=exc.__class__.__name__,
                        error_summary=public_error,
                        post_submit_derivation_summary={
                            "status": "blocked",
                            "reason": public_error,
                            "unsupported_required_checks": getattr(exc, "details", {}).get(
                                "unsupported_required_checks",
                                [],
                            ),
                        },
                        continuation_effective_policy_id=effective_policy_id,
                        continuation_pre_submit_checker_policy_id=pre_submit_checker_policy_id,
                    )
                    if status_response.status == "post_submit_policy_compiled":
                        return {
                            "status": "post_submit_policy_compiled",
                            "idempotent": True,
                            "post_submit_checker_policy_id": (
                                status_response.output_post_submit_checker_policy_id
                            ),
                        }
                except StaleProjectSetupContinuation:
                    logger.info(
                        "stale project setup post-submit continuation error ignored",
                        extra={
                            "project_id": project_id,
                            "guide_id": guide_id,
                            "source_snapshot_id": source_snapshot_id,
                            "setup_run_id": setup_run_id,
                            "error_code": exc.__class__.__name__,
                        },
                    )
                    return {
                        "status": "stale_post_submit_continuation_ignored",
                        "idempotent": True,
                        "post_submit_checker_policy_id": None,
                    }
                return {
                    "status": "post_submit_setup_blocked",
                    "error": public_error,
                    "post_submit_checker_policy_id": None,
                }
            except Exception as exc:
                public_error = "unexpected project setup continuation failure"
                logger.error(
                    "project setup post-submit continuation failed",
                    extra={
                        "project_id": project_id,
                        "guide_id": guide_id,
                        "source_snapshot_id": source_snapshot_id,
                        "setup_run_id": setup_run_id,
                        "error_code": exc.__class__.__name__,
                        "error_summary": public_error,
                    },
                )
                try:
                    status_response = await service.update_project_setup_run_status(
                        setup_run_id,
                        status="failed",
                        current_step="post_submit_checker_policy_derivation",
                        error_code=exc.__class__.__name__,
                        error_summary=public_error,
                        continuation_effective_policy_id=effective_policy_id,
                        continuation_pre_submit_checker_policy_id=pre_submit_checker_policy_id,
                    )
                    if status_response.status == "post_submit_policy_compiled":
                        return {
                            "status": "post_submit_policy_compiled",
                            "idempotent": True,
                            "post_submit_checker_policy_id": (
                                status_response.output_post_submit_checker_policy_id
                            ),
                        }
                except StaleProjectSetupContinuation:
                    logger.info(
                        "stale project setup post-submit continuation failure ignored",
                        extra={
                            "project_id": project_id,
                            "guide_id": guide_id,
                            "source_snapshot_id": source_snapshot_id,
                            "setup_run_id": setup_run_id,
                            "error_code": exc.__class__.__name__,
                        },
                    )
                    return {
                        "status": "stale_post_submit_continuation_ignored",
                        "idempotent": True,
                        "post_submit_checker_policy_id": None,
                    }
                return {
                    "status": "failed",
                    "error": public_error,
                    "post_submit_checker_policy_id": None,
                }
    finally:
        await engine.dispose()
