"""ART-owned immutable guide document metadata, without extraction or provider reads."""

from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.api.guide_documents import (
    GuideDocumentManifest,
    GuideDocumentManifestRequest,
    GuideDocumentUnavailable,
    GuideDocumentVersion,
)
from app.modules.artifacts.models import ArtifactContent, ArtifactPutAttempt, ArtifactReplica, ArtifactOperationReceipt, ArtifactPutObservationReceipt
from app.modules.projects.api.guide_documents import ProjectGuideDocumentScopePort


class SqlAlchemyGuideDocumentManifest:
    """Resolve every exact assigned source from its committed upload metadata."""

    def __init__(self, session: AsyncSession, scope: ProjectGuideDocumentScopePort) -> None:
        self._session = session
        self._scope = scope

    async def load(self, request: GuideDocumentManifestRequest) -> GuideDocumentManifest:
        """Require current lineage and all committed originals, with no source-body query."""
        lineage = await self._scope.lock_manifest_source(request)
        documents = []
        for item in lineage.documents:
            row = (await self._session.execute(
                select(ArtifactPutAttempt, ArtifactReplica, ArtifactContent)
                .select_from(ArtifactPutAttempt)
                .join(ArtifactReplica, ArtifactReplica.id == ArtifactPutAttempt.replica_id)
                .join(ArtifactContent, ArtifactContent.id == ArtifactReplica.content_id)
                .where(
                    ArtifactPutAttempt.guide_source_item_id == str(item.source_item_id),
                    ArtifactPutAttempt.producer_request_type == "guide",
                    ArtifactPutAttempt.logical_role.is_(None),
                    ArtifactPutAttempt.project_id == str(lineage.project_id),
                    ArtifactPutAttempt.status == "object_confirmed",
                    or_(
                        and_(ArtifactPutAttempt.terminal_result_code == "document_stored",
                            select(ArtifactOperationReceipt.id).where(
                                ArtifactOperationReceipt.id == ArtifactPutAttempt.receipt_id,
                                ArtifactOperationReceipt.put_attempt_id == ArtifactPutAttempt.id,
                                ArtifactOperationReceipt.guide_source_item_id == str(item.source_item_id),
                                ArtifactOperationReceipt.replica_id == ArtifactReplica.id,
                                ArtifactOperationReceipt.request_digest == ArtifactPutAttempt.request_digest,
                                ArtifactOperationReceipt.provider_object_ref == ArtifactReplica.provider_object_ref,
                                ArtifactOperationReceipt.outcome == "document_stored",
                            ).exists()),
                        and_(ArtifactPutAttempt.terminal_result_code == "document_stored_observed",
                            ArtifactPutAttempt.receipt_id.is_(None),
                            select(ArtifactPutObservationReceipt.id).where(
                                ArtifactPutObservationReceipt.put_attempt_id == ArtifactPutAttempt.id,
                                ArtifactPutObservationReceipt.execution_generation == ArtifactPutAttempt.execution_generation,
                                ArtifactPutObservationReceipt.outcome == "observed_confirmed",
                                ArtifactPutObservationReceipt.expected_sha256 == ArtifactPutAttempt.sha256,
                                ArtifactPutObservationReceipt.observed_sha256 == ArtifactPutAttempt.sha256,
                                ArtifactPutObservationReceipt.expected_byte_count == ArtifactPutAttempt.byte_count,
                                ArtifactPutObservationReceipt.observed_byte_count == ArtifactPutAttempt.byte_count,
                            ).exists()),
                    ),
                    ArtifactReplica.integrity_state != "invalid",
                    ArtifactReplica.availability_state.in_(("unknown", "available")),
                    ArtifactPutAttempt.terminal_result_code.in_(("document_stored", "document_stored_observed")),
                )
            )).one_or_none()
            if row is None:
                raise GuideDocumentUnavailable("guide_documents_incomplete")
            attempt, replica, content = row
            if (
                (item.sha256, item.byte_count, item.media_type)
                != (attempt.sha256, attempt.byte_count, attempt.media_type)
                or (content.sha256, content.byte_count, content.media_type)
                != (item.sha256, item.byte_count, item.media_type)
                or replica.storage_namespace_id != attempt.storage_namespace_id
                or replica.namespace_fingerprint != attempt.namespace_fingerprint
            ):
                raise GuideDocumentUnavailable("guide_document_identity_mismatch")
            try:
                documents.append(GuideDocumentVersion(
                    source_item_id=item.source_item_id, ingest_id=item.ingest_id, item_order=item.item_order,
                    put_attempt_id=attempt.id, content_id=content.id, replica_id=replica.id,
                    storage_namespace_id=replica.storage_namespace_id,
                    namespace_fingerprint=replica.namespace_fingerprint,
                    sha256=item.sha256, byte_count=item.byte_count, media_type=item.media_type,
                ))
            except ValueError:
                raise GuideDocumentUnavailable("guide_document_identity_mismatch") from None
        return GuideDocumentManifest(
            project_id=lineage.project_id, guide_id=lineage.guide_id, guide_version=lineage.guide_version,
            source_snapshot_id=lineage.source_snapshot_id, source_snapshot_hash=lineage.source_snapshot_hash,
            setup_run_id=lineage.setup_run_id, setup_generation=lineage.setup_generation,
            documents=tuple(documents),
        )
