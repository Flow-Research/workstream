"""PROJECTS-owned provider allocation and document-access custody for one attempt."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.projects.api.guide_documents import GuideDocumentManifest, GuideRuntimeResource
from .models import ProjectGuideCompilationAttempt, ProjectGuideRuntimeAllocation, ProjectGuideDocumentAccess


class SqlAlchemyGuideRuntimeCleanupCustody:
    """Exact retained cleanup scope, usable after the source or setup becomes stale."""

    def __init__(self, sessions, attempt_id, manifest_sha256, runtime_key):
        self._sessions = sessions
        self._attempt_id = attempt_id
        self._manifest_sha256 = manifest_sha256
        self._runtime_key = runtime_key

    async def _lock_cleanup_attempt(self, session):
        attempt = await session.scalar(select(ProjectGuideCompilationAttempt).where(
            ProjectGuideCompilationAttempt.id == self._attempt_id).with_for_update())
        if (attempt is None or attempt.guide_material_hash != self._manifest_sha256
                or attempt.runtime_configuration is None
                or attempt.runtime_configuration.get("runtime_key") != self._runtime_key):
            raise RuntimeError("guide resource cleanup scope is unavailable")
        return attempt

    async def _cleanup_allocation(self, session, allocation_id):
        await self._lock_cleanup_attempt(session)
        row = await session.scalar(select(ProjectGuideRuntimeAllocation).where(
            ProjectGuideRuntimeAllocation.id == allocation_id,
            ProjectGuideRuntimeAllocation.attempt_id == self._attempt_id,
            ProjectGuideRuntimeAllocation.manifest_sha256 == self._manifest_sha256,
            ProjectGuideRuntimeAllocation.runtime_key == self._runtime_key,
        ).with_for_update())
        if row is None:
            raise ValueError("guide resource cleanup allocation is unavailable")
        return row

    async def cleanup_resources(self):
        async with self._sessions() as session, session.begin():
            await self._lock_cleanup_attempt(session)
            rows = await session.scalars(select(ProjectGuideRuntimeAllocation).where(
                ProjectGuideRuntimeAllocation.attempt_id == self._attempt_id,
                ProjectGuideRuntimeAllocation.manifest_sha256 == self._manifest_sha256,
                ProjectGuideRuntimeAllocation.runtime_key == self._runtime_key,
                ProjectGuideRuntimeAllocation.provider_id.is_not(None),
                ProjectGuideRuntimeAllocation.state != "deleted",
            ).order_by(ProjectGuideRuntimeAllocation.created_at, ProjectGuideRuntimeAllocation.id))
            return tuple(GuideRuntimeResource(
                allocation_id=row.id, kind=row.kind, provider_id=row.provider_id,
                parent_provider_id=row.parent_provider_id,
                document_handle=str(row.document_handle) if row.document_handle else None,
                expires_at=row.expires_at,
            ) for row in rows)

    async def record_deleted(self, allocation_id):
        async with self._sessions() as session, session.begin():
            row = await self._cleanup_allocation(session, allocation_id)
            if row.state == "deleted":
                return
            if row.provider_id is None:
                raise ValueError("unknown resource deletion cannot be confirmed")
            row.state, row.deleted_at = "deleted", datetime.now(timezone.utc)

    async def record_cleanup_failed(self, allocation_id):
        async with self._sessions() as session, session.begin():
            row = await self._cleanup_allocation(session, allocation_id)
            if row.state != "deleted" and row.provider_id is not None:
                row.state = "cleanup_failed"


class SqlAlchemyGuideRuntimeCustody(SqlAlchemyGuideRuntimeCleanupCustody):
    """A fenced attempt's typed resource capability, never a caller-selected lookup service."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], attempt_id: UUID,
                 manifest: GuideDocumentManifest, runtime_key: str) -> None:
        super().__init__(sessions, attempt_id, manifest.sha256, runtime_key)
        self._manifest = manifest
        self._documents = {manifest.handle_for(item): item for item in manifest.documents}

    async def _lock_attempt(self, session: AsyncSession, *, allocating: bool = False):
        attempt = await session.scalar(select(ProjectGuideCompilationAttempt)
                                       .where(ProjectGuideCompilationAttempt.id == self._attempt_id)
                                       .with_for_update())
        if (attempt is None or attempt.guide_material_hash != self._manifest.sha256
                or attempt.setup_run_id != str(self._manifest.setup_run_id)
                or attempt.runtime_configuration is None
                or attempt.runtime_configuration.get("runtime_key") != self._runtime_key
                or (allocating and attempt.status != "compilation_provider_uncertain")):
            raise RuntimeError("guide runtime custody is unavailable")
        return attempt

    async def begin_allocation(self, *, kind, document_handle, parent_provider_id, expires_at,
                               source_file_allocation_id=None, container_allocation_id=None) -> UUID:
        if kind not in {"container", "file", "attachment"} or expires_at <= datetime.now(timezone.utc):
            raise ValueError("guide runtime allocation is invalid")
        if (kind == "container") != (document_handle is None):
            raise ValueError("guide runtime allocation scope is invalid")
        if document_handle is not None and document_handle not in self._documents:
            raise ValueError("guide runtime document is not granted")
        async with self._sessions() as session, session.begin():
            await self._lock_attempt(session, allocating=True)
            if kind == "attachment":
                parent = await session.scalar(select(ProjectGuideRuntimeAllocation).where(
                    ProjectGuideRuntimeAllocation.attempt_id == self._attempt_id,
                    ProjectGuideRuntimeAllocation.kind == "container",
                    ProjectGuideRuntimeAllocation.id == container_allocation_id,
                    ProjectGuideRuntimeAllocation.provider_id == parent_provider_id,
                    ProjectGuideRuntimeAllocation.state == "allocated",
                ))
                file = await session.scalar(select(ProjectGuideRuntimeAllocation).where(
                    ProjectGuideRuntimeAllocation.id == source_file_allocation_id,
                    ProjectGuideRuntimeAllocation.attempt_id == self._attempt_id,
                    ProjectGuideRuntimeAllocation.manifest_sha256 == self._manifest.sha256,
                    ProjectGuideRuntimeAllocation.kind == "file",
                    ProjectGuideRuntimeAllocation.document_handle == UUID(document_handle),
                    ProjectGuideRuntimeAllocation.state == "allocated",
                ))
                if parent is None or file is None:
                    raise ValueError("guide runtime parent is unavailable")
            elif any(value is not None for value in (parent_provider_id, source_file_allocation_id, container_allocation_id)):
                raise ValueError("guide runtime parent is invalid")
            facts = _file_document_facts(self._documents[document_handle]) if kind == "file" else {}
            allocation_id = uuid4()
            session.add(ProjectGuideRuntimeAllocation(
                id=allocation_id, attempt_id=self._attempt_id,
                manifest_sha256=self._manifest.sha256, runtime_key=self._runtime_key,
                kind=kind, state="allocating",
                document_handle=UUID(document_handle) if document_handle else None,
                provider_id=None, parent_provider_id=parent_provider_id, expires_at=expires_at,
                source_file_allocation_id=source_file_allocation_id, container_allocation_id=container_allocation_id,
                **facts,
            ))
            return allocation_id

    async def _allocation(self, session, allocation_id):
        await self._lock_attempt(session)
        row = await session.scalar(select(ProjectGuideRuntimeAllocation).where(
            ProjectGuideRuntimeAllocation.id == allocation_id,
            ProjectGuideRuntimeAllocation.attempt_id == self._attempt_id,
            ProjectGuideRuntimeAllocation.manifest_sha256 == self._manifest.sha256,
        ).with_for_update())
        if row is None:
            raise ValueError("guide runtime allocation is unavailable")
        return row

    async def record_allocated(self, allocation_id, provider_id):
        import re
        if not isinstance(provider_id, str) or re.fullmatch(r"(?:file-|cntr_|cfile_)[A-Za-z0-9_-]{1,120}", provider_id) is None:
            raise ValueError("guide provider resource identity is invalid")
        async with self._sessions() as session, session.begin():
            row = await self._allocation(session, allocation_id)
            prefixes = {"container": "cntr_", "file": "file-", "attachment": "cfile_"}
            if row.state != "allocating" or not provider_id.startswith(prefixes[row.kind]):
                raise ValueError("guide resource receipt conflicts")
            row.provider_id, row.state = provider_id, "allocated"

    async def record_uncertain(self, allocation_id):
        async with self._sessions() as session, session.begin():
            row = await self._allocation(session, allocation_id)
            if row.state == "allocating":
                row.state = "uncertain"

    async def record_document_open(self, handle):
        document = self._documents.get(handle)
        if document is None:
            raise ValueError("guide runtime document is not granted")
        async with self._sessions() as session, session.begin():
            await self._lock_attempt(session, allocating=True)
            attachment = await session.scalar(select(ProjectGuideRuntimeAllocation).where(
                ProjectGuideRuntimeAllocation.attempt_id == self._attempt_id,
                ProjectGuideRuntimeAllocation.kind == "attachment",
                ProjectGuideRuntimeAllocation.document_handle == UUID(handle),
                ProjectGuideRuntimeAllocation.state == "allocated",
            ))
            if attachment is None:
                raise ValueError("guide document staging is unconfirmed")
            session.add(ProjectGuideDocumentAccess(
                id=uuid4(), attempt_id=self._attempt_id, source_item_id=str(document.source_item_id),
                document_version_id=str(document.ingest_id), attachment_allocation_id=attachment.id,
                manifest_sha256=self._manifest.sha256, sha256=document.sha256,
                document_handle=UUID(handle),
            ))

    async def opened_handles(self):
        async with self._sessions() as session, session.begin():
            await self._lock_attempt(session)
            handles = await session.scalars(select(ProjectGuideDocumentAccess.document_handle).where(
                ProjectGuideDocumentAccess.attempt_id == self._attempt_id,
                ProjectGuideDocumentAccess.manifest_sha256 == self._manifest.sha256,
            ))
            return frozenset(str(value) for value in handles)



def _file_document_facts(document):
    """Map the selected original into immutable pre-upload provider custody."""
    return {
        "source_item_id": str(document.source_item_id),
        "document_version_id": str(document.ingest_id),
        "put_attempt_id": str(document.put_attempt_id), "content_id": str(document.content_id),
        "replica_id": str(document.replica_id), "storage_namespace_id": document.storage_namespace_id,
        "namespace_fingerprint": document.namespace_fingerprint, "sha256": document.sha256,
        "byte_count": document.byte_count, "media_type": document.media_type,
    }


async def require_compilation_document_access(session, attempt_id, manifest, result):
    """Bind accepted output to immutable exact-version file-access evidence."""
    rows = list(await session.scalars(select(ProjectGuideDocumentAccess).where(
        ProjectGuideDocumentAccess.attempt_id == attempt_id,
    )))
    documents = {str(item.source_item_id): item for item in manifest.documents}
    if not rows:
        raise ValueError("compilation has no document access evidence")
    opened = set()
    for row in rows:
        document = documents.get(row.source_item_id)
        if (document is None or row.manifest_sha256 != manifest.sha256
                or row.document_version_id != str(document.ingest_id)
                or row.sha256 != document.sha256
                or str(row.document_handle) != manifest.handle_for(document)):
            raise ValueError("compilation document access lineage mismatch")
        attachment = await session.get(ProjectGuideRuntimeAllocation, row.attachment_allocation_id)
        file = (await session.get(ProjectGuideRuntimeAllocation, attachment.source_file_allocation_id)
                if attachment is not None and attachment.source_file_allocation_id is not None else None)
        if (attachment is None or file is None or attachment.kind != "attachment" or file.kind != "file"
                or attachment.attempt_id != attempt_id or file.attempt_id != attempt_id
                or attachment.document_handle != row.document_handle or file.document_handle != row.document_handle
                or file.manifest_sha256 != manifest.sha256
                or any(getattr(file, key) != value for key, value in _file_document_facts(document).items())):
            raise ValueError("compilation provider file lineage mismatch")
        opened.add(row.source_item_id)
    references = (
        *(ref for finding in result.findings for ref in finding.evidence_refs),
        *(ref for requirement in result.requirements for ref in requirement.evidence_refs),
        *(ref for suggestion in result.capability_suggestions for ref in suggestion.evidence_refs),
    )
    cited = {str(ref.source_item_id) for ref in references}
    if not cited <= opened:
        raise ValueError("compilation cites unopened documents")
    if result.status != "guide_blocked" and (opened != set(documents) or cited != set(documents)):
        raise ValueError("ready compilation does not account for every document")


async def pending_runtime_resource_cleanup(session, *, limit=50):
    """Select retained IDs after termination or the latest allocation's full run budget."""
    from sqlalchemy import text
    from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
    import logging

    rows = (await session.execute(text("""
        select attempt.id, attempt.guide_material_hash, attempt.runtime_configuration,
               attempt.runtime_configuration_hash
        from project_guide_compilation_attempts attempt
        where exists(select 1 from project_guide_runtime_allocations resource
          where resource.attempt_id=attempt.id and resource.provider_id is not null
            and resource.state <> 'deleted')
          and (attempt.status in ('provider_result_accepted','compilation_invalid_terminal','compilation_persisted')
            or (select max(resource.created_at) from project_guide_runtime_allocations resource
                  where resource.attempt_id=attempt.id)
               + ((attempt.runtime_configuration->>'timeout_seconds')::integer
                  + (attempt.runtime_configuration->>'cleanup_timeout_seconds')::integer)
                 * interval '1 second' <= now())
        order by attempt.provider_uncertain_at, attempt.id
        limit :limit
    """), {"limit": limit})).all()
    candidates = []
    for row in rows:
        try:
            configuration = ProjectGuideRuntimeConfiguration.model_validate(row.runtime_configuration)
            if configuration.sha256 != row.runtime_configuration_hash:
                raise ValueError("runtime configuration hash mismatch")
        except ValueError:
            logging.getLogger(__name__).warning("guide resource cleanup configuration rejected",
                                               extra={"attempt_id": str(row.id)})
            continue
        candidates.append((row.id, row.guide_material_hash, configuration))
    return tuple(candidates)
