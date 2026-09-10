"""PROJECTS-owned current document lineage and attempt locks."""

from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.orm import load_only
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.projects.api.guide_documents import (
    GuideDocumentManifest, GuideDocumentManifestRequest, GuideDocumentUnavailable,
    ProjectGuideDocumentLineage, ProjectGuideDocumentSource,
)
from app.modules.projects.models import (
    GuideSourceArtifactIngest, GuideSourceSnapshot, GuideSourceSnapshotItem,
    ProjectGuide, ProjectSetupRun,
)
from .models import ProjectGuideCompilationAttempt
from app.modules.projects.api.task_examples import require_task_example_commitment


class SqlAlchemyProjectGuideDocumentScope:
    """Bind PROJECTS scope validation to the caller's existing transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_manifest_source(self, request: GuideDocumentManifestRequest) -> ProjectGuideDocumentLineage:
        """Lock exact current draft ownership and return no ORM or source bodies."""
        header = (await self._session.execute(
            select(ProjectGuide, GuideSourceSnapshot, ProjectSetupRun)
            .options(load_only(ProjectGuide.id, ProjectGuide.project_id, ProjectGuide.version,
                               ProjectGuide.status, ProjectGuide.task_examples, ProjectGuide.task_examples_hash))
            .join(GuideSourceSnapshot, GuideSourceSnapshot.guide_id == ProjectGuide.id)
            .join(ProjectSetupRun, ProjectSetupRun.guide_id == ProjectGuide.id)
            .where(
                ProjectGuide.id == str(request.guide_id),
                ProjectGuide.project_id == str(request.project_id),
                ProjectGuide.status == "draft",
                GuideSourceSnapshot.id == str(request.guide_source_snapshot_id),
                GuideSourceSnapshot.project_id == ProjectGuide.project_id,
                GuideSourceSnapshot.guide_version == ProjectGuide.version,
                ProjectSetupRun.id == str(request.project_setup_run_id),
                ProjectSetupRun.project_id == ProjectGuide.project_id,
                ProjectSetupRun.guide_version == ProjectGuide.version,
                ProjectSetupRun.source_snapshot_id == GuideSourceSnapshot.id,
                ProjectSetupRun.source_snapshot_hash == GuideSourceSnapshot.bundle_hash,
                ProjectSetupRun.setup_generation == request.setup_generation,
            ).with_for_update(of=(ProjectGuide, GuideSourceSnapshot, ProjectSetupRun))
        )).one_or_none()
        if header is None:
            raise GuideDocumentUnavailable("guide_source_stale")
        guide, snapshot, setup = header
        try:
            require_task_example_commitment(
                guide.task_examples, guide.task_examples_hash, manifest=snapshot.manifest_json,
            )
        except ValueError:
            raise GuideDocumentUnavailable("guide_task_examples_unavailable") from None
        latest_generation = await self._session.scalar(
            select(func.max(ProjectSetupRun.setup_generation))
            .where(ProjectSetupRun.guide_id == guide.id)
        )
        competing_snapshot = await self._session.scalar(
            select(select(GuideSourceSnapshot.id).where(
                GuideSourceSnapshot.guide_id == guide.id,
                GuideSourceSnapshot.guide_version == guide.version,
                GuideSourceSnapshot.id != snapshot.id,
                GuideSourceSnapshot.captured_at >= snapshot.captured_at,
            ).exists())
        )
        if latest_generation != setup.setup_generation or competing_snapshot:
            raise GuideDocumentUnavailable("guide_source_stale")
        items = (await self._session.scalars(
            select(GuideSourceSnapshotItem)
            .where(GuideSourceSnapshotItem.source_snapshot_id == snapshot.id)
            .order_by(GuideSourceSnapshotItem.item_order, GuideSourceSnapshotItem.id)
            .with_for_update()
        )).all()
        if not items:
            raise GuideDocumentUnavailable("guide_documents_incomplete")
        documents = []
        for item in items:
            if item.source_kind != "document" or item.ingestion_adapter != "upload":
                raise GuideDocumentUnavailable("guide_document_format_unsupported")
            ingest = await self._session.scalar(select(GuideSourceArtifactIngest).where(
                GuideSourceArtifactIngest.source_item_id == item.id).with_for_update())
            if ingest is None:
                raise GuideDocumentUnavailable("guide_documents_incomplete")
            if item.media_type != ingest.media_type:
                raise GuideDocumentUnavailable("guide_document_identity_mismatch")
            documents.append(ProjectGuideDocumentSource(
                source_item_id=UUID(item.id), ingest_id=UUID(ingest.id), item_order=item.item_order,
                sha256=ingest.sha256, byte_count=ingest.byte_count, media_type=ingest.media_type,
            ))
        return ProjectGuideDocumentLineage(
            project_id=UUID(guide.project_id), guide_id=UUID(guide.id), guide_version=guide.version,
            source_snapshot_id=UUID(snapshot.id), source_snapshot_hash=snapshot.bundle_hash,
            setup_run_id=UUID(setup.id), setup_generation=setup.setup_generation,
            documents=tuple(documents),
        )

    async def lock_access_attempt(self, attempt_id: UUID, manifest: GuideDocumentManifest) -> None:
        """Retain the provider fence lock through authorized original-byte staging."""
        attempt = await self._session.scalar(select(ProjectGuideCompilationAttempt).where(
            ProjectGuideCompilationAttempt.id == attempt_id,
            ProjectGuideCompilationAttempt.status == "compilation_provider_uncertain",
            ProjectGuideCompilationAttempt.project_id == str(manifest.project_id),
            ProjectGuideCompilationAttempt.guide_id == str(manifest.guide_id),
            ProjectGuideCompilationAttempt.guide_version == manifest.guide_version,
            ProjectGuideCompilationAttempt.source_snapshot_hash == manifest.source_snapshot_hash,
            ProjectGuideCompilationAttempt.source_snapshot_id == str(manifest.source_snapshot_id),
            ProjectGuideCompilationAttempt.guide_material_hash == manifest.sha256,
            ProjectGuideCompilationAttempt.setup_run_id == str(manifest.setup_run_id),
            ProjectGuideCompilationAttempt.setup_generation == manifest.setup_generation,
        ).with_for_update())
        if attempt is None:
            raise GuideDocumentUnavailable("guide_document_access_denied")
