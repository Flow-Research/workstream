"""Scripted document/provider ports for PostgreSQL orchestration proofs.

These tests exercise real allocation/access custody and lifecycle guards. ART
byte authorization and provider I/O are proved separately, not simulated as live.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

from app.modules.projects.api.guide_documents import OpenGuideDocument
from .helpers import SOURCE_BYTES


@asynccontextmanager
async def document_access(_attempt_id, manifest, _configuration):
    class Documents:
        @asynccontextmanager
        async def open(self, handle):
            item = next(item for item in manifest.documents if manifest.handle_for(item) == handle)
            with BytesIO(SOURCE_BYTES) as stream:
                yield OpenGuideDocument(item, stream)

        async def close(self):
            pass

    yield Documents()


async def record_scripted_document_access(context, capabilities):
    resources = capabilities.resources
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=20)
    container_id = "cntr_" + uuid4().hex
    container = await resources.begin_allocation(kind="container", document_handle=None, parent_provider_id=None, expires_at=expires_at)
    await resources.record_allocated(container, container_id)
    for document in context.material.documents:
        handle = context.material.handle_for(document)
        async with capabilities.documents.open(handle) as opened:
            assert opened.document == document
            assert opened.reader.read() == SOURCE_BYTES
        file = await resources.begin_allocation(kind="file", document_handle=handle, parent_provider_id=None, expires_at=expires_at)
        await resources.record_allocated(file, "file-" + uuid4().hex)
        attachment = await resources.begin_allocation(kind="attachment", document_handle=handle, parent_provider_id=container_id, expires_at=expires_at,
            source_file_allocation_id=file, container_allocation_id=container)
        await resources.record_allocated(attachment, "cfile_" + uuid4().hex)
        await resources.record_document_open(handle)


async def record_attempt_document_access(sessions, attempt_id, context):
    """Arrange real pre-upload/allocation/access custody after a committed fence."""
    from app.modules.projects.api.guide_documents import GuideRuntimeCapabilities
    from app.modules.projects.guide_compilation.runtime_resources import SqlAlchemyGuideRuntimeCustody
    async with document_access(attempt_id, context.material, context.runtime_configuration) as documents:
        resources = SqlAlchemyGuideRuntimeCustody(sessions, attempt_id, context.material,
                                                   context.runtime_configuration.runtime_key)
        await record_scripted_document_access(context, GuideRuntimeCapabilities(documents=documents, resources=resources))
