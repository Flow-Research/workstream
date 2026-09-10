"""OpenAI workspace staging and exact-resource cleanup for one fenced attempt."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.core.cancellation import await_completion_preserving_cancellation
from app.modules.projects.api.guide_documents import (
    GuideDocumentManifest,
    GuideRuntimeCapabilities,
    GuideRuntimeResource,
)
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration


class OpenAIGuideWorkspace:
    """Keep storage credentials and provider resource selectors outside agent tools."""

    def __init__(self, client, configuration: ProjectGuideRuntimeConfiguration,
                 manifest: GuideDocumentManifest, capabilities: GuideRuntimeCapabilities) -> None:
        self.client = client
        self.configuration = configuration
        self.manifest = manifest
        self.capabilities = capabilities
        self.container_id: str | None = None
        self.container_allocation_id: UUID | None = None
        self._known: list[GuideRuntimeResource] = []
        self._opened: dict[str, dict[str, str]] = {}
        self._locks = {manifest.handle_for(document): asyncio.Lock()
                       for document in manifest.documents}

    async def _allocate(self, *, kind, create, document_handle=None, parent_provider_id=None,
                        source_file_allocation_id=None, container_allocation_id=None):
        """Record intent before I/O and retain returned identity before another provider call."""
        seconds = (self.configuration.container_expiry_minutes * 60 if kind == "container"
                   else self.configuration.file_expiry_seconds)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        allocation = await self.capabilities.resources.begin_allocation(
            kind=kind, document_handle=document_handle,
            parent_provider_id=parent_provider_id, expires_at=expires_at,
            source_file_allocation_id=source_file_allocation_id, container_allocation_id=container_allocation_id,
        )
        try:
            value = await create()
            self._known.append(GuideRuntimeResource(
                allocation_id=allocation, kind=kind, provider_id=value.id,
                parent_provider_id=parent_provider_id, document_handle=document_handle,
                expires_at=expires_at,
            ))
            await self.capabilities.resources.record_allocated(allocation, value.id)
            return allocation, value
        except BaseException:
            # A failed create/receipt never licenses a second provider attempt.
            try:
                await self.capabilities.resources.record_uncertain(allocation)
            except Exception:
                pass  # The durable allocation intent remains unresolved.
            raise

    async def start(self) -> None:
        """Create a fresh empty container with no network or inherited conversation."""
        self.container_allocation_id, container = await self._allocate(
            kind="container",
            create=lambda: self.client.containers.create(
                name="workstream-guide-" + str(self.manifest.setup_run_id),
                memory_limit="1g",
                network_policy={"type": "disabled"},
                expires_after={"anchor": "last_active_at",
                               "minutes": self.configuration.container_expiry_minutes},
            ),
        )
        self.container_id = container.id
        expiry = container.expires_after
        if (expiry is None or expiry.anchor != "last_active_at"
                or expiry.minutes != self.configuration.container_expiry_minutes):
            raise RuntimeError("guide workspace expiry was not confirmed")
        policy = container.network_policy
        if policy is None or policy.type != "disabled":
            raise RuntimeError("guide workspace network policy was not confirmed")

    async def open_document(self, handle: str) -> dict[str, str]:
        """Revalidate the exact grant on every access, staging each original at most once."""
        lock = self._locks.get(handle)
        if lock is None or self.container_id is None:
            raise RuntimeError("guide document handle is unavailable")
        async with lock:
            # The ART owner authorizes and verifies all bytes before yielding a reader.
            async with self.capabilities.documents.open(handle) as opened:
                expected = next(document for document in self.manifest.documents
                                if self.manifest.handle_for(document) == handle)
                if opened.document != expected:
                    raise RuntimeError("guide document version mismatch")
                if handle in self._opened:
                    return self._opened[handle]
                file_allocation_id, uploaded = await self._allocate(
                    kind="file", document_handle=handle,
                    create=lambda: self.client.files.create(
                        file=(expected.filename, opened.reader, expected.media_type),
                        purpose="user_data",
                        expires_after={"anchor": "created_at",
                                       "seconds": self.configuration.file_expiry_seconds},
                    ),
                )
                if (not isinstance(uploaded.created_at, int)
                        or not isinstance(uploaded.expires_at, int)
                        or uploaded.expires_at - uploaded.created_at != self.configuration.file_expiry_seconds):
                    raise RuntimeError("guide file expiry was not confirmed")
                _, attachment = await self._allocate(
                    kind="attachment", document_handle=handle,
                    parent_provider_id=self.container_id,
                    container_allocation_id=self.container_allocation_id,
                    source_file_allocation_id=file_allocation_id,
                    create=lambda: self.client.containers.files.create(
                        self.container_id, file_id=uploaded.id,
                    ),
                )
                if (attachment.container_id != self.container_id
                        or not attachment.path.startswith("/mnt/data/")
                        or ".." in attachment.path.split("/")):
                    raise RuntimeError("guide workspace attachment is invalid")
                await self.capabilities.resources.record_document_open(handle)
                result = {
                    "path": attachment.path,
                    "source_item_id": str(expected.source_item_id),
                    "document_version_id": str(expected.ingest_id),
                    "sha256": expected.sha256,
                }
                self._opened[handle] = result
                return result

    async def close(self) -> None:
        """Give exact-ID cleanup a bounded shield without changing the attempt outcome."""
        async def bounded_cleanup():
            try:
                async with asyncio.timeout(self.configuration.cleanup_timeout_seconds):
                    try:
                        await self._cleanup()
                    finally:
                        await self.capabilities.documents.close()
            except Exception:
                pass  # Pending custody survives; ART scope exit also closes the run grant.
        await await_completion_preserving_cancellation(bounded_cleanup())

    async def _cleanup(self) -> None:
        """Use the same exact-ID operation as deferred cleanup recovery."""
        await cleanup_owned_resources(self.client, self.capabilities.resources, tuple(self._known))


async def cleanup_owned_resources(client, custody, known=()) -> None:
    """Delete recorded containers first, then their exact uploaded files; never discover IDs."""
    from openai import NotFoundError

    try:
        recorded = await custody.cleanup_resources()
    except Exception:
        recorded = ()
    resources = {item.allocation_id: item for item in (*recorded, *known)}
    removed_containers: set[str] = set()
    for kind in ("container", "attachment", "file"):
        for item in resources.values():
            if item.kind != kind:
                continue
            try:
                if kind == "attachment":
                    if item.parent_provider_id not in removed_containers:
                        # A previous cleanup may have committed the container's
                        # deletion before it could acknowledge this attachment.
                        try:
                            await client.containers.retrieve(item.parent_provider_id)
                        except NotFoundError:
                            removed_containers.add(item.parent_provider_id)
                        else:
                            raise RuntimeError("parent container cleanup is unresolved")
                elif kind == "container":
                    try:
                        await client.containers.delete(item.provider_id)
                    except NotFoundError:
                        pass
                    try:
                        await client.containers.retrieve(item.provider_id)
                    except NotFoundError:
                        removed_containers.add(item.provider_id)
                    else:
                        raise RuntimeError("guide container deletion is unresolved")
                else:
                    try:
                        deletion = await client.files.delete(item.provider_id)
                        if deletion.id != item.provider_id or deletion.deleted is not True:
                            raise RuntimeError("guide file deletion is unresolved")
                    except NotFoundError:
                        pass
                    try:
                        await client.files.retrieve(item.provider_id)
                    except NotFoundError:
                        pass
                    else:
                        raise RuntimeError("guide file deletion is unresolved")
                await custody.record_deleted(item.allocation_id)
            except Exception:
                try:
                    await custody.record_cleanup_failed(item.allocation_id)
                except Exception:
                    pass
