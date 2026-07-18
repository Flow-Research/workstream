"""Database operations for artifact ingest and immutable facts."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.models import (
    ArtifactContent,
    ArtifactOperationReceipt,
    ArtifactReplica,
    ArtifactStorageNamespace,
    ArtifactUploadItem,
    ArtifactUploadSession,
)


class ArtifactRepository:
    """Persist artifact state transitions under caller-owned transactions."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the repository to one async database session."""
        self._session = session

    async def lock_upload_item(self, item_id: str) -> ArtifactUploadItem | None:
        """Load one upload item with a row lock."""
        result = await self._session.execute(
            select(ArtifactUploadItem)
            .where(ArtifactUploadItem.id == item_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def lock_upload_session(self, session_id: str) -> ArtifactUploadSession | None:
        """Load one upload session with a row lock."""
        result = await self._session.execute(
            select(ArtifactUploadSession)
            .where(ArtifactUploadSession.id == session_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_or_create_content(self, content: ArtifactContent) -> ArtifactContent:
        """Return the immutable content fact for one digest and size."""
        await self._session.execute(
            insert(ArtifactContent)
            .values(
                id=content.id,
                sha256=content.sha256,
                byte_count=content.byte_count,
                media_type=content.media_type,
                normalized_display_name=content.normalized_display_name,
            )
            .on_conflict_do_nothing(constraint="uq_artifact_content_digest_size")
        )
        result = await self._session.execute(
            select(ArtifactContent).where(
                ArtifactContent.sha256 == content.sha256,
                ArtifactContent.byte_count == content.byte_count,
            )
        )
        return result.scalar_one()

    async def get_or_create_replica(self, replica: ArtifactReplica) -> ArtifactReplica:
        """Atomically return one replica for a namespace and provider object."""
        await self._session.execute(
            insert(ArtifactReplica)
            .values(
                id=replica.id,
                content_id=replica.content_id,
                storage_namespace_id=replica.storage_namespace_id,
                namespace_fingerprint=replica.namespace_fingerprint,
                adapter=replica.adapter,
                provider_profile=replica.provider_profile,
                provider_object_ref=replica.provider_object_ref,
                verification_state=replica.verification_state,
                availability_state=replica.availability_state,
                integrity_state=replica.integrity_state,
            )
            .on_conflict_do_nothing(constraint="uq_artifact_replica_provider_object")
        )
        result = await self._session.execute(
            select(ArtifactReplica).where(
                ArtifactReplica.storage_namespace_id == replica.storage_namespace_id,
                ArtifactReplica.provider_object_ref == replica.provider_object_ref,
            )
        )
        return result.scalar_one()

    async def add_receipt(self, receipt: ArtifactOperationReceipt) -> ArtifactOperationReceipt:
        """Persist one append-only Workstream put receipt."""
        self._session.add(receipt)
        await self._session.flush()
        return receipt

    async def get_receipt_for_item(
        self, upload_item_id: str
    ) -> ArtifactOperationReceipt | None:
        """Load the Workstream put receipt for one upload item."""
        result = await self._session.execute(
            select(ArtifactOperationReceipt).where(
                ArtifactOperationReceipt.upload_item_id == upload_item_id,
            )
        )
        return result.scalar_one_or_none()

    async def claim_storage_namespace(
        self, namespace: ArtifactStorageNamespace
    ) -> ArtifactStorageNamespace:
        """Atomically claim or load the immutable deployment namespace."""
        await self._session.execute(
            insert(ArtifactStorageNamespace)
            .values(
                id=namespace.id,
                backend=namespace.backend,
                adapter=namespace.adapter,
                provider_profile=namespace.provider_profile,
                namespace_descriptor=namespace.namespace_descriptor,
                namespace_fingerprint=namespace.namespace_fingerprint,
            )
            .on_conflict_do_nothing(index_elements=[ArtifactStorageNamespace.id])
        )
        result = await self._session.execute(
            select(ArtifactStorageNamespace).where(
                ArtifactStorageNamespace.id == namespace.id
            )
        )
        return result.scalar_one()
