"""ART exact-original reads for TASK's assigned contributor and a project's Project Manager."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.artifacts import ArtifactStore, ArtifactStoreError
from app.modules.artifacts.guide_documents import SqlAlchemyGuideDocumentManifest
from app.modules.artifacts.models import ArtifactReplica, ArtifactStorageNamespace
from app.modules.artifacts.service import (
    ArtifactStorageNamespaceError,
    ArtifactStorageNamespaceSpec,
    validate_artifact_replica_execution_namespace,
)
from app.modules.artifacts.preparation import ArtifactPreparationService
from app.modules.projects.api.guide_documents import (
    GuideDocumentUnavailable,
    LabeledGuideOriginal,
    LockedGuideOriginalsRequest,
    ProjectGuideDocumentScopePort,
    GuideDocumentVersion,
)
from app.modules.projects.api.guide_reads import VerifiedGuideDocumentRead
from app.modules.tasks.api.guide_documents import (
    ContributorGuideDocument,
    TaskGuideDocumentNotFound,
    TaskGuideUnavailable,
    VerifiedTaskGuideRead,
    TaskGuideSelection,
)


class ArtifactTaskGuideDocuments:
    """Require caller-owned TASK/AUTH transaction, then prepare immutable originals."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        scope: ProjectGuideDocumentScopePort,
        manifest: SqlAlchemyGuideDocumentManifest,
        runtime: Callable[
            [],
            AbstractAsyncContextManager[
                tuple[ArtifactStore, ArtifactStorageNamespaceSpec, ArtifactPreparationService]
            ],
        ],
    ) -> None:
        """Bind the caller transaction, PROJECTS scope, committed-original resolution and provider runtime."""
        self._session, self._scope, self._manifest, self._runtime = (
            session,
            scope,
            manifest,
            runtime,
        )

    async def _resolve(
        self, task_id: UUID, request: TaskGuideSelection
    ) -> tuple[tuple[ContributorGuideDocument, GuideDocumentVersion], ...]:
        """Pair each original of the task's exact locked snapshot with its committed version."""
        if not self._session.in_transaction():
            raise TaskGuideUnavailable("guide document transaction is unavailable")
        originals = await self._scope.lock_task_originals(
            LockedGuideOriginalsRequest(
                project_id=request.project_id,
                guide_id=request.guide_id,
                guide_version=request.guide_version,
                source_snapshot_id=request.source_snapshot_id,
                source_snapshot_hash=request.source_snapshot_hash,
            )
        )
        versions = await self._manifest.versions(
            request.project_id, tuple(item.source for item in originals)
        )
        return tuple(
            (
                ContributorGuideDocument(
                    document_id=version.source_item_id,
                    order=version.item_order,
                    label=original.label,
                    media_type=version.media_type,
                    byte_count=version.byte_count,
                    sha256=version.sha256,
                    read_reference=f"/api/v1/tasks/{task_id}/guide/documents/{version.source_item_id}/content",
                ),
                version,
            )
            for original, version in zip(originals, versions, strict=True)
        )

    async def list(
        self, task_id: UUID, request: TaskGuideSelection
    ) -> tuple[ContributorGuideDocument, ...]:
        """The task's locked originals as contributor read references; no provider I/O."""
        try:
            return tuple(document for document, _ in await self._resolve(task_id, request))
        except (GuideDocumentUnavailable, ValueError) as exc:
            raise TaskGuideUnavailable("guide document integrity unavailable") from exc

    @asynccontextmanager
    async def open(
        self, task_id: UUID, document_id: UUID, request: TaskGuideSelection
    ) -> AsyncIterator[VerifiedTaskGuideRead]:
        """Resolve the document in the task's exact snapshot, then serve its verified bytes."""
        try:
            resolved = await self._resolve(task_id, request)
            member = next((pair for pair in resolved if pair[0].document_id == document_id), None)
            if member is None:
                raise TaskGuideDocumentNotFound("task guide document not found")
            document, version = member
            async with verified_original(self._session, self._runtime, version) as content:
                yield VerifiedTaskGuideRead(document, content)
        except _INTEGRITY_FAULTS as exc:
            raise TaskGuideUnavailable("guide document integrity unavailable") from exc


class ArtifactProjectGuideDocuments:
    """Serve one uploaded guide original to an already authorized Project Manager."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        manifest: SqlAlchemyGuideDocumentManifest,
        runtime: Callable[
            [],
            AbstractAsyncContextManager[
                tuple[ArtifactStore, ArtifactStorageNamespaceSpec, ArtifactPreparationService]
            ],
        ],
    ) -> None:
        """Bind the caller transaction, committed-original resolution and provider runtime."""
        self._session, self._manifest, self._runtime = session, manifest, runtime

    @asynccontextmanager
    async def open(
        self, project_id: UUID, original: LabeledGuideOriginal
    ) -> AsyncIterator[VerifiedGuideDocumentRead]:
        """Resolve the committed original by its ingest, then serve its verified bytes."""
        try:
            if not self._session.in_transaction():
                raise GuideDocumentUnavailable("guide_document_transaction_unavailable")
            (version,) = await self._manifest.versions(project_id, (original.source,))
            async with verified_original(self._session, self._runtime, version) as content:
                yield VerifiedGuideDocumentRead(
                    document_id=version.source_item_id, media_type=version.media_type,
                    byte_count=version.byte_count, sha256=version.sha256, stream=content,
                )
        except _INTEGRITY_FAULTS as exc:
            raise GuideDocumentUnavailable("guide_document_integrity_unavailable") from exc


_INTEGRITY_FAULTS = (
    GuideDocumentUnavailable,
    ArtifactStoreError,
    ArtifactStorageNamespaceError,
    ValueError,
    StopAsyncIteration,
)


@asynccontextmanager
async def verified_original(
    session: AsyncSession,
    runtime: Callable[
        [],
        AbstractAsyncContextManager[
            tuple[ArtifactStore, ArtifactStorageNamespaceSpec, ArtifactPreparationService]
        ],
    ],
    version: GuideDocumentVersion,
) -> AsyncIterator[AsyncIterator[bytes]]:
    """Check replica custody, stage and re-verify the exact bytes, then yield the sealed stream.

    Opens the provider only after the caller resolved ``version``; the stream
    and its scratch are valid only inside this context.
    """
    async with runtime() as (store, namespace, preparation):
        prepared = None
        stream = None
        try:
            replica = await session.get(
                ArtifactReplica, str(version.replica_id),
                with_for_update={"read": True}, populate_existing=True,
            )
            persisted = await session.get(ArtifactStorageNamespace, version.storage_namespace_id)
            if (replica is None or persisted is None
                    or replica.integrity_state == "invalid"
                    or replica.availability_state not in ("unknown", "available")):
                raise GuideDocumentUnavailable("guide_document_integrity_unavailable")
            validate_artifact_replica_execution_namespace(
                replica=replica,
                persisted=persisted,
                namespace=namespace,
                store=store,
            )
            prepared = await preparation.prepare(
                store.open(replica.provider_object_ref),
                media_type=version.media_type,
                expected_sha256=version.sha256,
                expected_size=version.byte_count,
                maximum_bytes=version.byte_count,
            )
            stream = prepared.committed_source.stream()
            # Opening the sealed second pass re-verifies scratch before headers.
            first = await anext(stream)

            async def content() -> AsyncIterator[bytes]:
                """Replay the already verified first chunk, then the rest of the sealed pass."""
                yield first
                async for chunk in stream:
                    yield chunk

            yield content()
        finally:
            try:
                if stream is not None:
                    await stream.aclose()
            finally:
                if prepared is not None:
                    await prepared.close()
