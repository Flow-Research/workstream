"""Composition root for authorized artifact Celery operations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from app.adapters.artifacts import (
    create_artifact_store_bootstrap,
    require_artifact_runtime_eligible,
)
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.artifacts.authorization import PreparedArtifactInternalAuthority
from app.modules.artifacts.service import (
    ArtifactPendingWorkScanner,
    ArtifactStorageOrchestrator,
    artifact_storage_namespace_spec,
    validate_artifact_storage_namespace_at_startup,
)
from app.modules.authorization.runtime import AuthorizationDenied
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError


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
    require_artifact_runtime_eligible(settings)
    bootstrap = create_artifact_store_bootstrap(settings)
    try:
        claim = await validate_artifact_storage_namespace_at_startup(bootstrap, settings)
        store = bootstrap.initialize_after_namespace_claim(claim)
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
                artifact_storage_namespace_spec(settings, store),
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
    finally:
        bootstrap.close()


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
