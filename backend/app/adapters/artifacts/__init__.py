"""Artifact-store composition and shared scratch construction."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.api_controls import request_ids
from app.db.session import get_db_session
from app.interfaces.artifact_operations import GuideArtifactIngestCommand
from app.interfaces.artifacts import (
    ARTIFACT_STORE_CAPABILITY_KEY,
    ArtifactConfigurationError,
    ArtifactProviderLiveProofRequiredError,
    ArtifactStoreBootstrap,
    ArtifactStoreNamespaceClaim,
)
from app.interfaces.external_services import ExternalServiceAdapterFactory
from app.modules.artifacts.preparation import (
    ArtifactPreparationLimits,
    ArtifactPreparationService,
    ArtifactScratchManager,
)
from app.modules.artifacts.submission_archive import SubmissionArchiveLimits
from app.modules.artifacts.schemas import (
    ArtifactInternalAuthority,
)
from app.modules.artifacts.authorization import (
    GuideArtifactPreparedAuthorization,
    PreparedArtifactInternalAuthority,
    get_guide_artifact_prepared_authorization,
)
from app.modules.actors.service_identities import ServiceIdentity


def create_artifact_store_bootstrap(settings: Settings) -> ArtifactStoreBootstrap:
    """Construct the selected store bootstrap through one typed factory.

    Args:
        settings: Validated application settings.

    Returns:
        Non-mutating configured artifact store bootstrap.

    Raises:
        ExternalServiceConfigurationError: If the provider is not registered.
    """
    require_artifact_runtime_eligible(settings)

    from app.adapters.artifacts.local import LocalStorageAdapter, LocalStorageBootstrap
    from app.adapters.artifacts.s3_compatible import (
        create_minio_artifact_store_bootstrap,
    )

    factory = ExternalServiceAdapterFactory[ArtifactStoreBootstrap](ARTIFACT_STORE_CAPABILITY_KEY)

    def create_local_store() -> ArtifactStoreBootstrap:
        """Pin the configured development-only LocalStorage provider root."""
        if settings.artifact_local_root is None:
            raise ArtifactConfigurationError("local artifact root is not configured")
        return LocalStorageBootstrap(
            LocalStorageAdapter(
                root=settings.artifact_local_root,
                buffer_bytes=settings.artifact_stream_buffer_bytes,
                lock_timeout_seconds=settings.artifact_operation_lock_timeout_seconds,
            )
        )

    factory.register("local", create_local_store)
    factory.register(
        "s3_compatible",
        lambda: create_minio_artifact_store_bootstrap(settings),
    )
    return factory.create(settings.artifact_store_backend)


def require_artifact_runtime_eligible(settings: Settings) -> None:
    """Reject configured providers that this chunk has not activated."""
    if (
        settings.artifact_store_backend == "s3_compatible"
        and settings.artifact_s3_provider_profile == "aws_s3"
    ):
        raise ArtifactProviderLiveProofRequiredError(
            "AWS artifact provider requires live deployment proof"
        )


def artifact_preparation_limits(settings: Settings) -> ArtifactPreparationLimits:
    """Map validated settings to the one process-independent scratch contract."""
    return ArtifactPreparationLimits(
        aggregate_reserved_bytes=settings.artifact_scratch_aggregate_reserved_bytes,
        maximum_files=settings.artifact_scratch_maximum_files,
        maximum_concurrency=settings.artifact_scratch_maximum_concurrency,
        minimum_free_bytes=settings.artifact_scratch_minimum_free_bytes,
        reservation_ttl_seconds=settings.artifact_scratch_reservation_ttl_seconds,
        total_deadline_seconds=settings.artifact_preparation_total_deadline_seconds,
        cleanup_margin_seconds=settings.artifact_scratch_cleanup_margin_seconds,
        stream_buffer_bytes=settings.artifact_stream_buffer_bytes,
        maximum_source_bytes=settings.artifact_maximum_bytes,
    )


def submission_archive_limits(settings: Settings) -> SubmissionArchiveLimits:
    """Map validated settings to the fixed outer-ZIP safety contract."""
    return SubmissionArchiveLimits(
        maximum_entries=settings.artifact_submission_zip_maximum_entries,
        maximum_path_bytes=settings.artifact_submission_zip_maximum_path_bytes,
        maximum_path_depth=settings.artifact_submission_zip_maximum_path_depth,
        maximum_central_directory_bytes=(
            settings.artifact_submission_zip_maximum_central_directory_bytes
        ),
        maximum_entry_bytes=settings.artifact_submission_zip_maximum_entry_bytes,
        maximum_expanded_bytes=settings.artifact_submission_zip_maximum_expanded_bytes,
        maximum_compression_ratio=(
            settings.artifact_submission_zip_maximum_compression_ratio
        ),
        maximum_inspection_seconds=(
            settings.artifact_submission_zip_maximum_inspection_seconds
        ),
    )


def create_artifact_scratch_manager(settings: Settings) -> ArtifactScratchManager:
    """Construct a scratch manager from the canonical settings mapping."""
    if settings.artifact_scratch_root is None:
        raise ArtifactConfigurationError("artifact scratch root is not configured")
    return ArtifactScratchManager(
        root=settings.artifact_scratch_root,
        limits=artifact_preparation_limits(settings),
    )


def get_artifact_internal_authority(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ArtifactInternalAuthority:
    """Use the activated fixed-service resolver for post-commit provider work."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    return PreparedArtifactInternalAuthority(
        session,
        service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
        request_id=request_id,
        correlation_id=correlation_id,
    )


def get_guide_artifact_ingest_command(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authority: Annotated[
        GuideArtifactPreparedAuthorization,
        Depends(get_guide_artifact_prepared_authorization),
    ],
    internal_authority: Annotated[
        ArtifactInternalAuthority,
        Depends(get_artifact_internal_authority),
    ],
) -> GuideArtifactIngestCommand:
    """Compose real guide ingest lazily so denial performs no provider I/O."""
    from app.modules.artifacts.service import (
        ArtifactAdmissionService,
        ArtifactStorageOrchestrator,
        GuideArtifactIngestService,
        PreparedGuideArtifactIngestCommand,
        artifact_storage_namespace_spec,
    )

    settings = request.app.state.settings

    @asynccontextmanager
    async def runtime():
        bootstrap = create_artifact_store_bootstrap(settings)
        try:
            manager = create_artifact_scratch_manager(settings)
        except BaseException:
            bootstrap.close()
            raise
        try:
            namespace = artifact_storage_namespace_spec(settings, bootstrap)
            store = bootstrap.initialize_after_namespace_claim(
                ArtifactStoreNamespaceClaim(
                    adapter_identity=bootstrap.identity,
                    namespace_identity=bootstrap.namespace_identity,
                    namespace_fingerprint=namespace.namespace_fingerprint,
                )
            )
            yield (
                ArtifactPreparationService(manager),
                ArtifactAdmissionService(session, settings, namespace),
                ArtifactStorageOrchestrator(
                    session,
                    store,
                    namespace,
                    settings,
                    internal_authority,
                ),
            )
        finally:
            manager.close()
            bootstrap.close()

    service = GuideArtifactIngestService(runtime, authority)
    return PreparedGuideArtifactIngestCommand(service, authority)


async def cleanup_stale_artifact_scratch(settings: Settings) -> int:
    """Run one database-independent stale cleanup with shared construction."""
    require_artifact_runtime_eligible(settings)
    manager = create_artifact_scratch_manager(settings)
    try:
        return await manager.cleanup_stale()
    finally:
        manager.close()
