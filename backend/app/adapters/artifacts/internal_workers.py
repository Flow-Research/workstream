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


async def continue_guide_setup_after_stored_document(put_attempt_id: UUID) -> None:
    """Pass committed document metadata to the PROJECTS dispatch owner."""
    from app.adapters.artifacts import guide_document_manifest_port
    from app.modules.artifacts.models import ArtifactPutAttempt
    from app.modules.projects.models import GuideSourceSnapshotItem
    from app.modules.projects.guide_setup_continuation import continue_setup_after_stored_guide_item

    async with get_session_factory()() as session:
        snapshot_id = await session.scalar(select(GuideSourceSnapshotItem.source_snapshot_id)
            .join(ArtifactPutAttempt, ArtifactPutAttempt.guide_source_item_id == GuideSourceSnapshotItem.id)
            .where(ArtifactPutAttempt.id == str(put_attempt_id),
                   ArtifactPutAttempt.producer_request_type == "guide",
                   ArtifactPutAttempt.status == "object_confirmed",
                   ArtifactPutAttempt.terminal_result_code.in_(("document_stored", "document_stored_observed"))))
    if snapshot_id is not None:
        await continue_setup_after_stored_guide_item(
            UUID(snapshot_id), session_factory=get_session_factory(),
            manifest_factory=guide_document_manifest_port,
        )


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


async def scan_guide_setup_continuations(publish_continuation: Callable[[str], Awaitable[None]]) -> int:
    """Recover complete committed document sets, without scanning verification jobs."""
    from sqlalchemy import func
    from sqlalchemy.orm import aliased
    from app.modules.artifacts.models import ArtifactPutAttempt
    from app.modules.projects.models import (
        GuideSourceSnapshotItem, GuideSourceSnapshot, ProjectGuide, ProjectSetupRun,
    )
    from app.modules.projects.guide_setup_continuation import retryable_compilation_dispatch_predicate

    newer_run = aliased(ProjectSetupRun)
    newer_snapshot = aliased(GuideSourceSnapshot)
    stale_run = select(newer_run.id).where(
        newer_run.guide_id == ProjectSetupRun.guide_id,
        newer_run.setup_generation > ProjectSetupRun.setup_generation,
    ).exists()
    stale_snapshot = select(newer_snapshot.id).where(
        newer_snapshot.guide_id == GuideSourceSnapshot.guide_id,
        newer_snapshot.guide_version == GuideSourceSnapshot.guide_version,
        newer_snapshot.id != GuideSourceSnapshot.id,
        newer_snapshot.captured_at >= GuideSourceSnapshot.captured_at,
    ).exists()
    missing_item = aliased(GuideSourceSnapshotItem)
    matching_put = aliased(ArtifactPutAttempt)
    committed = select(matching_put.id).where(
        matching_put.guide_source_item_id == missing_item.id,
        matching_put.producer_request_type == "guide",
        matching_put.status == "object_confirmed",
        matching_put.terminal_result_code.in_(("document_stored", "document_stored_observed")),
    ).exists()
    missing = select(missing_item.id).where(
        missing_item.source_snapshot_id == ProjectSetupRun.source_snapshot_id, ~committed,
    ).exists()
    async with get_session_factory()() as session:
        ids = list(await session.scalars(
            select(func.min(ArtifactPutAttempt.id))
            .join(GuideSourceSnapshotItem, GuideSourceSnapshotItem.id == ArtifactPutAttempt.guide_source_item_id)
            .join(ProjectSetupRun, ProjectSetupRun.source_snapshot_id == GuideSourceSnapshotItem.source_snapshot_id)
            .join(GuideSourceSnapshot, GuideSourceSnapshot.id == ProjectSetupRun.source_snapshot_id)
            .join(ProjectGuide, ProjectGuide.id == ProjectSetupRun.guide_id)
            .where(retryable_compilation_dispatch_predicate(), ~missing, ~stale_run, ~stale_snapshot,
                   ProjectGuide.status == "draft", ProjectGuide.version == ProjectSetupRun.guide_version,
                   GuideSourceSnapshot.project_id == ProjectSetupRun.project_id,
                   GuideSourceSnapshot.guide_id == ProjectGuide.id,
                   GuideSourceSnapshot.guide_version == ProjectGuide.version,
                   GuideSourceSnapshot.bundle_hash == ProjectSetupRun.source_snapshot_hash,
                   ArtifactPutAttempt.producer_request_type == "guide",
                   ArtifactPutAttempt.status == "object_confirmed",
                   ArtifactPutAttempt.terminal_result_code.in_(("document_stored", "document_stored_observed")))
            .group_by(ProjectSetupRun.id).order_by(func.min(ArtifactPutAttempt.terminal_at), ProjectSetupRun.id)
            .limit(get_settings().guide_setup_continuation_scan_page_size)
        ))
    for identifier in ids:
        await publish_continuation(identifier)
    return len(ids)
