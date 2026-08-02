"""Composition root for authorized artifact Celery operations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from threading import Condition
from typing import Iterator
from uuid import UUID, uuid4

from sqlalchemy import select

from app.adapters.artifacts import (
    create_artifact_store_bootstrap,
    require_artifact_runtime_eligible,
)
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.interfaces.artifacts import ArtifactStore, ArtifactStoreBootstrap
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.artifacts.authorization import PreparedArtifactInternalAuthority
from app.modules.artifacts.service import (
    ArtifactPendingWorkScanner,
    ArtifactStorageNamespaceSpec,
    ArtifactStorageOrchestrator,
    artifact_storage_namespace_spec,
    validate_artifact_storage_namespace_at_startup,
)
from app.modules.authorization.runtime import AuthorizationDenied
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError


_runtime_condition = Condition()
_runtime: (
    tuple[
        ArtifactStoreBootstrap,
        ArtifactStore,
        ArtifactStorageNamespaceSpec,
    ]
    | None
) = None
_runtime_active_operations = 0
_runtime_shutting_down = False


async def initialize_artifact_internal_runtime() -> None:
    """Initialize one provider store for this Celery child process."""
    global _runtime, _runtime_shutting_down
    with _runtime_condition:
        if _runtime is not None and not _runtime_shutting_down:
            return
    settings = get_settings()
    if settings.artifact_store_backend == "disabled":
        return
    require_artifact_runtime_eligible(settings)
    bootstrap = create_artifact_store_bootstrap(settings)
    try:
        namespace = artifact_storage_namespace_spec(settings, bootstrap)
        claim = await validate_artifact_storage_namespace_at_startup(bootstrap, settings)
        store = bootstrap.initialize_after_namespace_claim(claim)
    except BaseException:
        bootstrap.close()
        raise
    with _runtime_condition:
        if _runtime is not None:
            bootstrap.close()
            return
        _runtime = (bootstrap, store, namespace)
        _runtime_shutting_down = False


def shutdown_artifact_internal_runtime() -> None:
    """Close the process store only after every admitted operation exits."""
    global _runtime, _runtime_shutting_down
    with _runtime_condition:
        _runtime_shutting_down = True
        while _runtime_active_operations:
            _runtime_condition.wait()
        runtime = _runtime
        _runtime = None
    if runtime is not None:
        runtime[0].close()


@contextmanager
def _artifact_internal_runtime() -> Iterator[tuple[ArtifactStore, ArtifactStorageNamespaceSpec]]:
    """Lease the initialized process store against concurrent shutdown."""
    global _runtime_active_operations
    with _runtime_condition:
        if _runtime is None or _runtime_shutting_down:
            raise RuntimeError("artifact internal runtime is not initialized")
        _runtime_active_operations += 1
        _bootstrap, store, namespace = _runtime
    try:
        yield store, namespace
    finally:
        with _runtime_condition:
            _runtime_active_operations -= 1
            if _runtime_active_operations == 0:
                _runtime_condition.notify_all()


async def run_artifact_internal_operation(kind: str, resource_id: UUID) -> str:
    """Compose one resolver or verifier operation behind the adapter boundary."""
    identities = {
        "put": ServiceIdentity.ARTIFACT_PUT_RESOLVER,
        "verification": ServiceIdentity.ARTIFACT_VERIFIER,
    }
    try:
        service_identity = identities[kind]
    except KeyError as exc:
        raise ValueError("unsupported artifact internal operation") from exc
    settings = get_settings()
    await initialize_artifact_internal_runtime()
    with _artifact_internal_runtime() as (store, namespace):
        async with get_session_factory()() as session:
            request_id = uuid4()
            authority = PreparedArtifactInternalAuthority(
                session,
                service_identity=service_identity,
                request_id=request_id,
                correlation_id=request_id,
            )
            orchestrator = ArtifactStorageOrchestrator(
                session,
                store,
                namespace,
                settings,
                authority,
            )
            try:
                if kind == "put":
                    return await orchestrator.resolve_put_attempt(resource_id)
                elif kind == "verification":
                    return await orchestrator.verify_object(resource_id)
            except AuthorizationDenied:
                await session.rollback()
                await authority.persist_denial()
                raise ArtifactAuthorityDeniedError("artifact internal authority denied") from None
    raise AssertionError("artifact internal operation did not return")


async def continue_guide_setup_after_verification(verification_job_id: UUID) -> None:
    """Compose ART capabilities for the project-owned setup continuation."""
    from app.adapters.artifacts import create_artifact_scratch_manager
    from app.modules.artifacts.guide_setup import GuideSetupPreparationService
    from app.modules.artifacts.models import ArtifactPutAttempt, ArtifactVerificationJob
    from app.modules.artifacts.preparation import ArtifactPreparationService
    from app.modules.projects.models import GuideSourceSnapshotItem
    from app.modules.projects.guide_setup_continuation import (
        continue_setup_after_verified_guide_item,
    )

    settings = get_settings()
    async with get_session_factory()() as session:
        source_snapshot_id = await session.scalar(
            select(GuideSourceSnapshotItem.source_snapshot_id)
            .join(
                ArtifactPutAttempt,
                ArtifactPutAttempt.guide_source_item_id == GuideSourceSnapshotItem.id,
            )
            .join(
                ArtifactVerificationJob,
                ArtifactVerificationJob.originating_put_attempt_id == ArtifactPutAttempt.id,
            )
            .where(
                ArtifactVerificationJob.id == str(verification_job_id),
                ArtifactVerificationJob.status == "verified",
                ArtifactVerificationJob.terminal_result_code == "verified",
            )
        )
    if source_snapshot_id is None:
        return
    await initialize_artifact_internal_runtime()
    manager = create_artifact_scratch_manager(settings)
    try:
        with _artifact_internal_runtime() as (store, namespace):
            preparation_service = GuideSetupPreparationService(
                get_session_factory(),
                store,
                ArtifactPreparationService(manager),
                namespace,
            )
            await continue_setup_after_verified_guide_item(
                verification_job_id,
                UUID(source_snapshot_id),
                session_factory=get_session_factory(),
                prepare_generation=preparation_service.prepare_generation,
            )
    finally:
        manager.close()


async def scan_artifact_pending_work(
    publish_put_attempt: Callable[[str], Awaitable[None]],
    publish_verification_job: Callable[[str], Awaitable[None]],
) -> int:
    """Compose and authorize one bounded pending-work scan."""
    settings = get_settings()
    async with get_session_factory()() as session:
        request_id = uuid4()
        authority = PreparedArtifactInternalAuthority(
            session,
            service_identity=ServiceIdentity.ARTIFACT_SCHEDULER,
            request_id=request_id,
            correlation_id=request_id,
        )
        try:
            return await ArtifactPendingWorkScanner(
                session,
                settings,
                authority,
                publish_put_attempt,
                publish_verification_job,
            ).scan()
        except AuthorizationDenied:
            await session.rollback()
            await authority.persist_denial()
            raise ArtifactAuthorityDeniedError("artifact internal authority denied") from None


async def scan_guide_setup_continuations(
    publish_verification_job: Callable[[str], Awaitable[None]],
) -> int:
    """Publish verified ART jobs only for project-owned retryable snapshots."""
    from app.modules.artifacts.models import ArtifactPutAttempt, ArtifactVerificationJob
    from app.modules.projects.guide_setup_continuation import (
        retryable_source_snapshot_ids,
    )
    from app.modules.projects.models import GuideSourceSnapshotItem

    settings = get_settings()
    snapshot_ids = await retryable_source_snapshot_ids(
        get_session_factory(),
        page_size=settings.artifact_pending_work_scan_page_size,
    )
    if not snapshot_ids:
        return 0
    async with get_session_factory()() as session:
        job_ids = list(
            (
                await session.scalars(
                    select(ArtifactVerificationJob.id)
                    .join(
                        ArtifactPutAttempt,
                        ArtifactPutAttempt.id == ArtifactVerificationJob.originating_put_attempt_id,
                    )
                    .join(
                        GuideSourceSnapshotItem,
                        GuideSourceSnapshotItem.id == ArtifactPutAttempt.guide_source_item_id,
                    )
                    .where(
                        ArtifactVerificationJob.status == "verified",
                        ArtifactVerificationJob.terminal_result_code == "verified",
                        GuideSourceSnapshotItem.source_snapshot_id.in_(
                            [str(value) for value in snapshot_ids]
                        ),
                    )
                    .order_by(
                        ArtifactVerificationJob.terminal_at.asc(),
                        ArtifactVerificationJob.id.asc(),
                    )
                    .limit(settings.artifact_pending_work_scan_page_size)
                )
            ).all()
        )
    for job_id in job_ids:
        await publish_verification_job(job_id)
    return len(job_ids)
