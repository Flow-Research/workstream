"""Composition root for authorized artifact Celery operations."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from threading import Condition
from typing import Iterator
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.artifacts import (
    artifact_provider_activation_guard,
    create_artifact_store_bootstrap,
)
from app.core.config import Settings, get_settings
from app.db.session import get_database_url
from app.interfaces.artifacts import (
    ArtifactProviderActivationGuard,
    ArtifactProviderActivationLease,
    ArtifactProviderLiveProofRequiredError,
    ArtifactStore,
    ArtifactStoreBootstrap,
)
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.authorization import PreparedArtifactInternalAuthority
from app.modules.artifacts.service import (
    ArtifactPendingWorkScanner,
    ArtifactStorageNamespaceSpec,
    ArtifactStorageOrchestrator,
    artifact_storage_namespace_spec,
    validate_artifact_storage_namespace_at_startup,
)


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
_loop_sessions: ContextVar[async_sessionmaker[AsyncSession] | None] = ContextVar(
    "artifact_worker_loop_sessions",
    default=None,
)


@asynccontextmanager
async def _artifact_worker_database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Own SQLAlchemy resources for exactly one worker event loop."""
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    token = _loop_sessions.set(sessions)
    try:
        yield sessions
    finally:
        _loop_sessions.reset(token)
        await engine.dispose()


class _LoopScopedArtifactProviderActivationGuard(ArtifactProviderActivationGuard):
    """Resolve every worker activation through the current event loop's DB owner."""

    def __init__(self, settings: Settings) -> None:
        """Retain validated settings while sessions remain loop-owned."""
        self._settings = settings

    def _delegate(self) -> ArtifactProviderActivationGuard:
        """Create the canonical guard from the current event loop's sessions."""
        sessions = _loop_sessions.get()
        if sessions is None:
            raise ArtifactProviderLiveProofRequiredError(
                "AWS artifact worker operation lacks loop-scoped database custody"
            )
        guard = artifact_provider_activation_guard(self._settings, sessions)
        if guard is None:
            raise ArtifactProviderLiveProofRequiredError(
                "AWS artifact worker activation guard is unavailable"
            )
        return guard

    async def select_for_call(
        self,
        *,
        namespace_fingerprint: str,
    ) -> ArtifactProviderActivationLease:
        """Select an activation through the current event loop's DB owner."""
        return await self._delegate().select_for_call(
            namespace_fingerprint=namespace_fingerprint,
        )

    async def require_for_call(
        self,
        activation_id: UUID,
        *,
        namespace_fingerprint: str,
    ) -> ArtifactProviderActivationLease:
        """Reload one activation through the current event loop's DB owner."""
        return await self._delegate().require_for_call(
            activation_id,
            namespace_fingerprint=namespace_fingerprint,
        )


async def initialize_artifact_internal_runtime() -> None:
    """Initialize one provider store for this Celery child process."""
    with _runtime_condition:
        if _runtime is not None and not _runtime_shutting_down:
            return
    settings = get_settings()
    if settings.artifact_store_backend == "disabled":
        return
    async with _artifact_worker_database() as session_factory:
        await _initialize_artifact_internal_runtime(settings, session_factory)


async def validate_artifact_internal_runtime_startup() -> None:
    """Validate namespace and AWS activation for a non-provider Beat process."""
    settings = get_settings()
    if settings.artifact_store_backend == "disabled":
        return
    async with _artifact_worker_database() as session_factory:
        activation_guard = artifact_provider_activation_guard(settings, session_factory)
        bootstrap = create_artifact_store_bootstrap(
            settings,
            activation_guard=activation_guard,
        )
        try:
            claim = await validate_artifact_storage_namespace_at_startup(
                bootstrap,
                settings,
                session_factory,
            )
            if activation_guard is not None:
                await activation_guard.select_for_call(
                    namespace_fingerprint=claim.namespace_fingerprint,
                )
        finally:
            bootstrap.close()


async def _initialize_artifact_internal_runtime(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Initialize the provider using the current worker loop's SQL resources."""
    global _runtime, _runtime_shutting_down
    with _runtime_condition:
        if _runtime is not None and not _runtime_shutting_down:
            return
    activation_guard = (
        _LoopScopedArtifactProviderActivationGuard(settings)
        if settings.artifact_s3_provider_profile == "aws_s3"
        else artifact_provider_activation_guard(settings, session_factory)
    )
    bootstrap = create_artifact_store_bootstrap(
        settings,
        activation_guard=activation_guard,
    )
    try:
        namespace = artifact_storage_namespace_spec(settings, bootstrap)
        claim = await validate_artifact_storage_namespace_at_startup(
            bootstrap,
            settings,
            session_factory,
        )
        if activation_guard is not None:
            await activation_guard.select_for_call(
                namespace_fingerprint=claim.namespace_fingerprint,
            )
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
    async with _artifact_worker_database() as session_factory:
        await _initialize_artifact_internal_runtime(settings, session_factory)
        with _artifact_internal_runtime() as (store, namespace):
            async with session_factory() as session:
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
                async with authority.denial_boundary():
                    if kind == "put":
                        return await orchestrator.resolve_put_attempt(resource_id)
                    elif kind == "verification":
                        from app.adapters.tasks import task_submission_context_port

                        return await orchestrator.verify_object(
                            resource_id,
                            submission_task_contexts=task_submission_context_port(session),
                        )
    raise AssertionError("artifact internal operation did not return")


async def continue_guide_setup_after_stored_document(put_attempt_id: UUID) -> None:
    """Pass committed document metadata to the PROJECTS dispatch owner."""
    from app.adapters.artifacts import guide_document_manifest_port
    from app.modules.artifacts.models import ArtifactPutAttempt
    from app.modules.projects.models import GuideSourceSnapshotItem
    from app.modules.projects.guide_setup_continuation import continue_setup_after_stored_guide_item

    async with _artifact_worker_database() as session_factory:
        async with session_factory() as session:
            snapshot_id = await session.scalar(select(GuideSourceSnapshotItem.source_snapshot_id)
                .join(ArtifactPutAttempt, ArtifactPutAttempt.guide_source_item_id == GuideSourceSnapshotItem.id)
                .where(ArtifactPutAttempt.id == str(put_attempt_id),
                       ArtifactPutAttempt.producer_request_type == "guide",
                       ArtifactPutAttempt.status == "object_confirmed",
                       ArtifactPutAttempt.terminal_result_code.in_(("document_stored", "document_stored_observed"))))
        if snapshot_id is not None:
            await continue_setup_after_stored_guide_item(
                UUID(snapshot_id), session_factory=session_factory,
                manifest_factory=guide_document_manifest_port,
            )


async def scan_artifact_pending_work(
    publish_put_attempt: Callable[[str], Awaitable[None]],
    publish_verification_job: Callable[[str], Awaitable[None]],
) -> int:
    """Compose and authorize one bounded pending-work scan."""
    settings = get_settings()
    async with _artifact_worker_database() as session_factory:
        async with session_factory() as session:
            request_id = uuid4()
            authority = PreparedArtifactInternalAuthority(
                session,
                service_identity=ServiceIdentity.ARTIFACT_SCHEDULER,
                request_id=request_id,
                correlation_id=request_id,
            )
            async with authority.denial_boundary():
                return await ArtifactPendingWorkScanner(
                    session,
                    settings,
                    authority,
                    publish_put_attempt,
                    publish_verification_job,
                ).scan()


async def scan_guide_setup_continuations(publish_continuation: Callable[[str], Awaitable[None]]) -> int:
    """Recover complete committed document sets, without scanning verification jobs."""
    from sqlalchemy import String, cast, func
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
    async with _artifact_worker_database() as session_factory:
        async with session_factory() as session:
            ids = list(await session.scalars(
                # PostgreSQL 16 has UUID ordering but no min(uuid) aggregate.
                # This representative is published as a canonical string, as before.
                select(func.min(cast(ArtifactPutAttempt.id, String)))
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
