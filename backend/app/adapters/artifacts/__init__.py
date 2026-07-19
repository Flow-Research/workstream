"""Artifact-store composition and shared scratch construction."""

from __future__ import annotations

from app.core.config import Settings
from app.interfaces.artifacts import (
    ARTIFACT_STORE_CAPABILITY_KEY,
    ArtifactConfigurationError,
    ArtifactProviderLiveProofRequiredError,
    ArtifactStoreBootstrap,
)
from app.interfaces.external_services import ExternalServiceAdapterFactory
from app.modules.artifacts.preparation import (
    ArtifactPreparationLimits,
    ArtifactScratchManager,
)


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

    factory = ExternalServiceAdapterFactory[ArtifactStoreBootstrap](
        ARTIFACT_STORE_CAPABILITY_KEY
    )

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


def create_artifact_scratch_manager(settings: Settings) -> ArtifactScratchManager:
    """Construct a scratch manager from the canonical settings mapping."""
    if settings.artifact_scratch_root is None:
        raise ArtifactConfigurationError("artifact scratch root is not configured")
    return ArtifactScratchManager(
        root=settings.artifact_scratch_root,
        limits=artifact_preparation_limits(settings),
    )


async def cleanup_stale_artifact_scratch(settings: Settings) -> int:
    """Run one database-independent stale cleanup with shared construction."""
    require_artifact_runtime_eligible(settings)
    manager = create_artifact_scratch_manager(settings)
    try:
        return await manager.cleanup_stale()
    finally:
        manager.close()
