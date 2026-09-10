"""Fixed-service, exact-original guide access through verified bounded scratch."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import Callable
from sqlalchemy.ext.asyncio import AsyncSession
from io import BytesIO
from hashlib import sha256
from time import monotonic
from uuid import UUID, uuid4


from app.modules.projects.api.guide_documents import (
    GuideDocumentManifest, GuideDocumentManifestRequest, GuideDocumentUnavailable, OpenGuideDocument,
    GuideDocumentManifestPort, ProjectGuideDocumentScopePort,
)
from app.modules.artifacts.models import ArtifactReplica, ArtifactStorageNamespace
from app.modules.artifacts.schemas import GuideSourceReadAuthorityFacts
from app.modules.artifacts.service import validate_artifact_replica_execution_namespace


class ScopedGuideDocumentGrant:
    """An opaque run-local capability; it never accepts a key, URL or provider selector."""

    def __init__(self, sessions, store, namespace, preparation, authority_factory, *,
                 scope_factory: Callable[[AsyncSession], ProjectGuideDocumentScopePort],
                 manifest_factory: Callable[[AsyncSession], GuideDocumentManifestPort],
                 attempt_id: UUID, manifest: GuideDocumentManifest, lifetime_seconds: int,
                 maximum_document_bytes: int) -> None:
        self._scope_factory = scope_factory
        self._manifest_factory = manifest_factory
        self._sessions = sessions
        self._store = store
        self._namespace = namespace
        self._preparation = preparation
        self._authority = authority_factory
        self._attempt_id = attempt_id
        self._manifest = manifest
        self._documents = {manifest.handle_for(item): item for item in manifest.documents}
        self._deadline = monotonic() + lifetime_seconds
        self._maximum_bytes = maximum_document_bytes
        self._closed = False

    def _require_live(self, handle):
        if self._closed or monotonic() >= self._deadline or handle not in self._documents:
            raise GuideDocumentUnavailable("guide_document_access_denied")
        return self._documents[handle]

    @asynccontextmanager
    async def open(self, handle: str):
        """Recheck authority and commitment before allowing any bytes to leave ART."""
        document = self._require_live(handle)
        if document.byte_count > self._maximum_bytes:
            raise GuideDocumentUnavailable("guide_document_limit_exceeded")
        prepared = None
        memory = None
        try:
            async with self._sessions() as session, session.begin():
                current = await self._manifest_factory(session).load(
                    GuideDocumentManifestRequest(
                        project_id=self._manifest.project_id, guide_id=self._manifest.guide_id,
                        guide_source_snapshot_id=self._manifest.source_snapshot_id,
                        project_setup_run_id=self._manifest.setup_run_id,
                        setup_generation=self._manifest.setup_generation,
                    )
                )
                if current != self._manifest:
                    raise GuideDocumentUnavailable("guide_document_identity_mismatch")
                await self._scope_factory(session).lock_access_attempt(self._attempt_id, self._manifest)
                replica = await session.get(ArtifactReplica, str(document.replica_id), with_for_update=True)
                if replica is None:
                    raise GuideDocumentUnavailable("guide_document_unavailable")
                persisted = await session.get(ArtifactStorageNamespace, document.storage_namespace_id)
                if persisted is None:
                    raise GuideDocumentUnavailable("guide_document_namespace_unavailable")
                validate_artifact_replica_execution_namespace(
                    replica=replica, persisted=persisted, namespace=self._namespace, store=self._store,
                )
                facts = GuideSourceReadAuthorityFacts(
                    project_id=current.project_id, guide_id=current.guide_id,
                    guide_source_snapshot_id=current.source_snapshot_id,
                    guide_source_item_id=document.source_item_id,
                    project_setup_run_id=current.setup_run_id, setup_generation=current.setup_generation,
                    compilation_attempt_id=self._attempt_id, manifest_sha256=current.sha256,
                    document_version_id=document.ingest_id, put_attempt_id=document.put_attempt_id,
                    content_id=document.content_id, replica_id=document.replica_id,
                    storage_namespace_id=str(document.storage_namespace_id),
                    namespace_fingerprint=document.namespace_fingerprint,
                    sha256=document.sha256, byte_count=document.byte_count, media_type=document.media_type,
                )
                authority = self._authority(session)
                try:
                    permission = await authority.prepare(facts=facts, idempotency_key=uuid4())
                    await authority.consume(prepared_authorization=permission, facts=facts)
                    self._require_live(handle)
                    async with asyncio.timeout(max(0, self._deadline - monotonic())):
                        prepared = await self._preparation.prepare(
                            self._store.open(replica.provider_object_ref), media_type=document.media_type,
                        )
                    if (prepared.commitment.sha256, prepared.commitment.byte_count) != (
                        document.sha256, document.byte_count,
                    ):
                        raise GuideDocumentUnavailable("guide_document_integrity_mismatch")
                finally:
                    authority.close()
            self._require_live(handle)
            # The entire object has already passed checksum and size verification in
            # canonical scratch. One bounded per-document multipart buffer is transient.
            memory = BytesIO()
            digest = sha256()
            async for block in prepared.committed_source.stream():
                if memory.tell() + len(block) > document.byte_count:
                    raise GuideDocumentUnavailable("guide_document_integrity_mismatch")
                digest.update(block)
                memory.write(block)
            if memory.tell() != document.byte_count or "sha256:" + digest.hexdigest() != document.sha256:
                raise GuideDocumentUnavailable("guide_document_integrity_mismatch")
            memory.seek(0)
            self._require_live(handle)
            yield OpenGuideDocument(document=document, reader=memory)
        finally:
            if memory is not None:
                memory.close()
            if prepared is not None:
                await prepared.close()

    async def close(self):
        """Invalidate the grant; active scratch remains owned by its open scope."""
        self._closed = True
