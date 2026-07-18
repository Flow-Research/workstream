"""Test-only activation helpers for the namespace-fenced local artifact store."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from app.adapters.artifacts.local import LocalStorageAdapter, LocalStorageBootstrap
from app.interfaces.artifacts import (
    ArtifactStoreNamespaceClaim,
    artifact_store_namespace_material,
)
from app.modules.artifacts.preparation import (
    HARD_MAXIMUM_ARTIFACT_BYTES,
    ArtifactPreparationLimits,
    ArtifactPreparationService,
    ArtifactScratchManager,
)
from app.modules.artifacts.sources import CommittedArtifactSource


async def artifact_byte_stream(*chunks: bytes) -> AsyncIterator[bytes]:
    """Yield exact test bytes through the public preparation boundary."""
    for chunk in chunks:
        yield chunk


def artifact_preparation_limits(
    *,
    maximum_files: int = 8,
    maximum_concurrency: int = 8,
) -> ArtifactPreparationLimits:
    """Return bounded test limits with the production aggregate ceiling."""
    return ArtifactPreparationLimits(
        aggregate_reserved_bytes=HARD_MAXIMUM_ARTIFACT_BYTES,
        maximum_files=maximum_files,
        maximum_concurrency=maximum_concurrency,
        minimum_free_bytes=0,
        reservation_ttl_seconds=30,
        total_deadline_seconds=10,
        cleanup_margin_seconds=1,
        stream_buffer_bytes=2,
        maximum_source_bytes=1024,
    )


@asynccontextmanager
async def minted_source(
    scratch_root: Path,
    *chunks: bytes,
    media_type: str = "application/octet-stream",
    limits: ArtifactPreparationLimits | None = None,
) -> AsyncIterator[CommittedArtifactSource]:
    """Mint and release one real sealed source without exposing scratch internals."""
    manager = ArtifactScratchManager(
        root=scratch_root,
        limits=limits or artifact_preparation_limits(),
    )
    prepared = await ArtifactPreparationService(manager).prepare(
        artifact_byte_stream(*chunks),
        media_type=media_type,
    )
    try:
        async with prepared as source:
            yield source
    finally:
        manager.close()


def initialize_local_store(
    root: Path,
    *,
    buffer_bytes: int = 1024 * 1024,
    lock_timeout_seconds: float = 1800.0,
) -> LocalStorageAdapter:
    """Pre-provision, pin, claim, and initialize one test-only local store."""
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    bootstrap = LocalStorageBootstrap(
        LocalStorageAdapter(
            root=root,
            buffer_bytes=buffer_bytes,
            lock_timeout_seconds=lock_timeout_seconds,
        )
    )
    return bootstrap.initialize_after_namespace_claim(local_namespace_claim(bootstrap))


def local_namespace_claim(bootstrap: LocalStorageBootstrap) -> ArtifactStoreNamespaceClaim:
    """Mint the exact test-only namespace claim for one pinned adapter."""
    namespace_identity = bootstrap.namespace_identity
    _, fingerprint = artifact_store_namespace_material(
        backend="local",
        adapter_identity=bootstrap.identity,
        namespace_identity=namespace_identity,
    )
    return ArtifactStoreNamespaceClaim(
        adapter_identity=bootstrap.identity,
        namespace_identity=namespace_identity,
        namespace_fingerprint=fingerprint,
    )
