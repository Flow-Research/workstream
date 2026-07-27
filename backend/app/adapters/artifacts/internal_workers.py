"""Composition root for authorized artifact Celery operations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from threading import Condition
from typing import Iterator
from uuid import UUID, uuid4

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
_runtime: tuple[
    ArtifactStoreBootstrap,
    ArtifactStore,
    ArtifactStorageNamespaceSpec,
] | None = None
_runtime_active_operations = 0
_runtime_shutting_down = False


async def initialize_artifact_internal_runtime() -> None:
    """Initialize one provider store for this Celery child process."""
    global _runtime, _runtime_shutting_down
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
def _artifact_internal_runtime() -> Iterator[
    tuple[ArtifactStore, ArtifactStorageNamespaceSpec]
]:
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


async def run_artifact_internal_operation(kind: str, resource_id: UUID) -> None:
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
                    await orchestrator.resolve_put_attempt(resource_id)
                elif kind == "verification":
                    await orchestrator.verify_object(resource_id)
            except AuthorizationDenied:
                await session.rollback()
                await authority.persist_denial()
                raise ArtifactAuthorityDeniedError(
                    "artifact internal authority denied"
                ) from None


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
            raise ArtifactAuthorityDeniedError(
                "artifact internal authority denied"
            ) from None
