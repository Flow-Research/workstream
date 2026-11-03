"""PROJECTS-owned neutral document access and retained-resource cleanup custody."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.projects.api.guide_documents import (
    GuideDocumentAccessReceipt,
    GuideDocumentManifest,
    GuideRuntimeResource,
)

from .models import (
    ProjectGuideCompilationAttempt,
    ProjectGuideDocumentAccess,
    ProjectGuideRuntimeAllocation,
)

_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


def attempt_uses_inference(attempt) -> bool:
    """Read only the frozen all-none versus all-concrete inference identity."""
    configuration = attempt.runtime_configuration
    if type(configuration) is not dict:
        raise ValueError("guide runtime configuration is unavailable")
    identities = tuple(configuration.get(name) for name in ("model_provider", "model_api", "model"))
    if all(value == "none" for value in identities):
        return False
    if all(isinstance(value, str) and value and value != "none" for value in identities):
        return True
    raise ValueError("guide runtime inference identity is invalid")


class SqlAlchemyGuideRuntimeCleanupCustody:
    """Exact retained cleanup scope, usable after source lineage becomes stale."""

    def __init__(self, sessions, attempt_id, manifest_sha256, runtime_key):
        self._sessions = sessions
        self._attempt_id = attempt_id
        self._manifest_sha256 = manifest_sha256
        self._runtime_key = runtime_key

    async def _lock_cleanup_attempt(self, session):
        attempt = await session.scalar(
            select(ProjectGuideCompilationAttempt)
            .where(ProjectGuideCompilationAttempt.id == self._attempt_id)
            .with_for_update()
        )
        if (
            attempt is None
            or attempt.guide_material_hash != self._manifest_sha256
            or attempt.runtime_configuration is None
            or attempt.runtime_configuration.get("runtime_key") != self._runtime_key
            or canonical_json_hash(attempt.runtime_configuration)
            != attempt.runtime_configuration_hash
        ):
            raise RuntimeError("guide resource cleanup scope is unavailable")
        return attempt

    async def _cleanup_allocation(self, session, allocation_id):
        await self._lock_cleanup_attempt(session)
        row = await session.scalar(
            select(ProjectGuideRuntimeAllocation)
            .where(
                ProjectGuideRuntimeAllocation.id == allocation_id,
                ProjectGuideRuntimeAllocation.attempt_id == self._attempt_id,
                ProjectGuideRuntimeAllocation.manifest_sha256 == self._manifest_sha256,
                ProjectGuideRuntimeAllocation.runtime_key == self._runtime_key,
            )
            .with_for_update()
        )
        if row is None:
            raise ValueError("guide resource cleanup allocation is unavailable")
        return row

    async def cleanup_resources(self):
        async with self._sessions() as session, session.begin():
            await self._lock_cleanup_attempt(session)
            rows = await session.scalars(
                select(ProjectGuideRuntimeAllocation)
                .where(
                    ProjectGuideRuntimeAllocation.attempt_id == self._attempt_id,
                    ProjectGuideRuntimeAllocation.manifest_sha256 == self._manifest_sha256,
                    ProjectGuideRuntimeAllocation.runtime_key == self._runtime_key,
                    ProjectGuideRuntimeAllocation.provider_id.is_not(None),
                    ProjectGuideRuntimeAllocation.state.in_(("allocated", "cleanup_failed")),
                )
                .order_by(
                    ProjectGuideRuntimeAllocation.created_at,
                    ProjectGuideRuntimeAllocation.id,
                )
            )
            return tuple(
                GuideRuntimeResource(
                    allocation_id=row.id,
                    kind=row.kind,
                    provider_id=row.provider_id,
                    parent_provider_id=row.parent_provider_id,
                    document_handle=(str(row.document_handle) if row.document_handle else None),
                    expires_at=row.expires_at,
                )
                for row in rows
            )

    async def record_deleted(self, allocation_id):
        async with self._sessions() as session, session.begin():
            row = await self._cleanup_allocation(session, allocation_id)
            if row.state == "deleted":
                return
            if row.provider_id is None or row.state not in {
                "allocated",
                "cleanup_failed",
                "deleted",
            }:
                raise ValueError("unknown resource deletion cannot be confirmed")
            row.state = "deleted"
            row.deleted_at = datetime.now(UTC)

    async def record_cleanup_failed(self, allocation_id):
        async with self._sessions() as session, session.begin():
            row = await self._cleanup_allocation(session, allocation_id)
            if row.state in {"allocated", "cleanup_failed"} and row.provider_id is not None:
                row.state = "cleanup_failed"


class SqlAlchemyGuideDocumentAccessCustody:
    """Persist fixed-parser receipts for one exact already-fenced attempt."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        attempt_id: UUID,
        manifest: GuideDocumentManifest,
        runtime_key: str,
    ) -> None:
        self._sessions = sessions
        self._attempt_id = attempt_id
        self._manifest = manifest
        self._runtime_key = runtime_key
        self._documents = {manifest.handle_for(item): item for item in manifest.documents}

    async def _lock_attempt(self, session: AsyncSession):
        attempt = await session.scalar(
            select(ProjectGuideCompilationAttempt)
            .where(ProjectGuideCompilationAttempt.id == self._attempt_id)
            .with_for_update()
        )
        if (
            attempt is None
            or attempt.status != "compilation_provider_uncertain"
            or attempt.guide_material_hash != self._manifest.sha256
            or attempt.setup_run_id != str(self._manifest.setup_run_id)
            or attempt.runtime_configuration is None
            or attempt.runtime_configuration.get("runtime_key") != self._runtime_key
        ):
            raise RuntimeError("guide document access custody is unavailable")
        return attempt

    async def record_success(self, receipt: GuideDocumentAccessReceipt) -> None:
        document = self._documents.get(receipt.handle)
        if (
            document is None
            or receipt.source_item_id != document.source_item_id
            or receipt.document_version_id != document.ingest_id
            or receipt.sha256 != document.sha256
            or receipt.operation not in {"read", "search"}
            or any(
                _HASH.fullmatch(value) is None
                for value in (
                    receipt.parser_request_hash,
                    receipt.parser_response_hash,
                    receipt.parser_build_digest,
                )
            )
        ):
            raise ValueError("guide document access receipt is invalid")
        async with self._sessions() as session, session.begin():
            await self._lock_attempt(session)
            existing = await session.scalar(
                select(ProjectGuideDocumentAccess).where(
                    ProjectGuideDocumentAccess.attempt_id == self._attempt_id,
                    ProjectGuideDocumentAccess.parser_request_hash == receipt.parser_request_hash,
                )
            )
            if existing is not None:
                if not _same_receipt(existing, receipt, self._manifest.sha256):
                    raise ValueError("guide document access receipt conflicts")
                return
            session.add(
                ProjectGuideDocumentAccess(
                    id=new_record_id(),
                    attempt_id=self._attempt_id,
                    source_item_id=str(document.source_item_id),
                    document_version_id=str(document.ingest_id),
                    attachment_allocation_id=None,
                    access_method="trusted_parser",
                    operation=receipt.operation,
                    parser_request_hash=receipt.parser_request_hash,
                    parser_response_hash=receipt.parser_response_hash,
                    parser_build_digest=receipt.parser_build_digest,
                    manifest_sha256=self._manifest.sha256,
                    sha256=document.sha256,
                    document_handle=UUID(receipt.handle),
                )
            )

    async def opened_handles(self) -> frozenset[str]:
        async with self._sessions() as session, session.begin():
            await self._lock_attempt(session)
            handles = await session.scalars(
                select(ProjectGuideDocumentAccess.document_handle).where(
                    ProjectGuideDocumentAccess.attempt_id == self._attempt_id,
                    ProjectGuideDocumentAccess.manifest_sha256 == self._manifest.sha256,
                    ProjectGuideDocumentAccess.access_method == "trusted_parser",
                )
            )
            return frozenset(str(value) for value in handles)


def _same_receipt(row, receipt, manifest_sha256) -> bool:
    return (
        row.access_method == "trusted_parser"
        and str(row.document_handle) == receipt.handle
        and row.source_item_id == str(receipt.source_item_id)
        and row.document_version_id == str(receipt.document_version_id)
        and row.manifest_sha256 == manifest_sha256
        and row.sha256 == receipt.sha256
        and row.operation == receipt.operation
        and row.parser_request_hash == receipt.parser_request_hash
        and row.parser_response_hash == receipt.parser_response_hash
        and row.parser_build_digest == receipt.parser_build_digest
        and row.attachment_allocation_id is None
    )


async def require_compilation_document_access(session, attempt_id, manifest, result):
    """Bind accepted output to immutable exact-version source-access evidence."""
    rows = list(
        await session.scalars(
            select(ProjectGuideDocumentAccess).where(
                ProjectGuideDocumentAccess.attempt_id == attempt_id
            )
        )
    )
    documents = {str(item.source_item_id): item for item in manifest.documents}
    if not rows:
        raise ValueError("compilation has no document access evidence")
    opened = set()
    for row in rows:
        document = documents.get(row.source_item_id)
        if (
            document is None
            or row.manifest_sha256 != manifest.sha256
            or row.document_version_id != str(document.ingest_id)
            or row.sha256 != document.sha256
            or row.document_handle != UUID(manifest.handle_for(document))
            or not _valid_access_evidence(row)
        ):
            raise ValueError("compilation document access lineage mismatch")
        if row.access_method == "provider_attachment":
            await _require_historical_attachment(session, attempt_id, manifest, document, row)
        opened.add(row.source_item_id)
    references = (
        *(ref for finding in result.findings for ref in finding.evidence_refs),
        *(ref for requirement in result.requirements for ref in requirement.evidence_refs),
    )
    cited = {str(ref.source_item_id) for ref in references}
    if not cited <= opened:
        raise ValueError("compilation cites unopened documents")
    if result.status != "guide_blocked" and (opened != set(documents) or cited != set(documents)):
        raise ValueError("ready compilation does not account for every document")


def _valid_access_evidence(row) -> bool:
    if row.access_method == "trusted_parser":
        return (
            row.attachment_allocation_id is None
            and row.operation in {"read", "search"}
            and all(
                value is not None and _HASH.fullmatch(value) is not None
                for value in (
                    row.parser_request_hash,
                    row.parser_response_hash,
                    row.parser_build_digest,
                )
            )
        )
    if row.access_method == "provider_attachment":
        return row.attachment_allocation_id is not None and all(
            value is None
            for value in (
                row.operation,
                row.parser_request_hash,
                row.parser_response_hash,
                row.parser_build_digest,
            )
        )
    if row.access_method == "direct_original":
        return row.attachment_allocation_id is None and all(
            value is None
            for value in (
                row.operation,
                row.parser_request_hash,
                row.parser_response_hash,
                row.parser_build_digest,
            )
        )
    return False


async def _require_historical_attachment(session, attempt_id, manifest, document, row):
    attachment = await session.get(ProjectGuideRuntimeAllocation, row.attachment_allocation_id)
    file = (
        await session.get(ProjectGuideRuntimeAllocation, attachment.source_file_allocation_id)
        if attachment is not None and attachment.source_file_allocation_id is not None
        else None
    )
    if (
        attachment is None
        or file is None
        or attachment.kind != "attachment"
        or file.kind != "file"
        or attachment.attempt_id != attempt_id
        or file.attempt_id != attempt_id
        or attachment.document_handle != row.document_handle
        or file.document_handle != row.document_handle
        or file.manifest_sha256 != manifest.sha256
        or any(getattr(file, key) != value for key, value in _file_document_facts(document).items())
    ):
        raise ValueError("compilation provider file lineage mismatch")


def _file_document_facts(document):
    """Map one retained provider file to its immutable source facts."""
    return {
        "source_item_id": str(document.source_item_id),
        "document_version_id": str(document.ingest_id),
        "put_attempt_id": str(document.put_attempt_id),
        "content_id": str(document.content_id),
        "replica_id": str(document.replica_id),
        "storage_namespace_id": document.storage_namespace_id,
        "namespace_fingerprint": document.namespace_fingerprint,
        "sha256": document.sha256,
        "byte_count": document.byte_count,
        "media_type": document.media_type,
    }


@dataclass(frozen=True, slots=True)
class RetainedGuideRuntimeCleanupCandidate:
    """Verified old configuration identity needed only for exact-ID cleanup."""

    attempt_id: UUID
    manifest_sha256: str
    runtime_key: str


async def pending_runtime_resource_cleanup(
    session,
    *,
    retained_runtime_key: str,
    cleanup_grace_seconds: int = 30,
    limit: int = 50,
):
    """Select immutable old resource facts without current-runtime dispatch."""
    rows = (
        await session.execute(
            select(
                ProjectGuideCompilationAttempt.id,
                ProjectGuideCompilationAttempt.guide_material_hash,
                ProjectGuideCompilationAttempt.runtime_configuration,
                ProjectGuideCompilationAttempt.runtime_configuration_hash,
                ProjectGuideCompilationAttempt.status,
                func.max(ProjectGuideRuntimeAllocation.created_at).label("latest_created_at"),
            )
            .join(
                ProjectGuideRuntimeAllocation,
                ProjectGuideRuntimeAllocation.attempt_id == ProjectGuideCompilationAttempt.id,
            )
            .where(
                ProjectGuideRuntimeAllocation.runtime_key == retained_runtime_key,
                ProjectGuideRuntimeAllocation.provider_id.is_not(None),
                ProjectGuideRuntimeAllocation.state.in_(("allocated", "cleanup_failed")),
            )
            .group_by(ProjectGuideCompilationAttempt.id)
            .order_by(
                ProjectGuideCompilationAttempt.provider_uncertain_at,
                ProjectGuideCompilationAttempt.id,
            )
            .limit(limit)
        )
    ).all()
    now = datetime.now(UTC)
    candidates = []
    terminal = {
        "provider_result_accepted",
        "compilation_invalid_terminal",
        "compilation_persisted",
    }
    for row in rows:
        config = row.runtime_configuration
        if (
            type(config) is not dict
            or config.get("runtime_key") != retained_runtime_key
            or canonical_json_hash(config) != row.runtime_configuration_hash
        ):
            continue
        timeout = config.get("timeout_seconds")
        old_cleanup = config.get("cleanup_timeout_seconds", cleanup_grace_seconds)
        if type(timeout) is not int or type(old_cleanup) is not int:
            continue
        eligible_at = row.latest_created_at + timedelta(
            seconds=timeout + max(old_cleanup, cleanup_grace_seconds)
        )
        if row.status not in terminal and eligible_at > now:
            continue
        candidates.append(
            RetainedGuideRuntimeCleanupCandidate(
                attempt_id=row.id,
                manifest_sha256=row.guide_material_hash,
                runtime_key=retained_runtime_key,
            )
        )
    return tuple(candidates)
