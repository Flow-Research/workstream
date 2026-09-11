"""Resolve public guide document selectors without exposing source snapshots."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.api.guide_documents import GuideDocumentUploadTarget
from app.modules.projects.models import (
    GuideMutationIdempotencyRecord,
    GuideSourceArtifactIngest,
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    Project,
    ProjectGuide,
    ProjectSetupRun,
)


class ProjectGuideDocumentUploadTargets:
    """PROJECTS-owned exact membership lookup sharing the ingest transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(
        self, project_id: UUID, guide_id: UUID, document_id: UUID, *, for_update: bool
    ) -> GuideDocumentUploadTarget | None:
        if for_update:
            project = await self._session.scalar(
                select(Project)
                .where(
                    Project.id == str(project_id),
                )
                .with_for_update()
            )
            if project is None:
                return None
        root = aliased(GuideMutationIdempotencyRecord)
        source = aliased(GuideMutationIdempotencyRecord)
        latest_setup = (
            select(func.max(ProjectSetupRun.setup_generation))
            .where(
                ProjectSetupRun.guide_id == str(guide_id),
            )
            .correlate(None)
            .scalar_subquery()
        )
        statement = (
            select(
                GuideSourceSnapshot.id,
                ProjectSetupRun.id.label("setup_id"),
                ProjectSetupRun.setup_generation,
                GuideSourceSnapshotItem.media_type,
            )
            .select_from(GuideSourceSnapshotItem)
            .join(
                GuideSourceSnapshot,
                GuideSourceSnapshot.id == GuideSourceSnapshotItem.source_snapshot_id,
            )
            .join(ProjectGuide, ProjectGuide.id == GuideSourceSnapshot.guide_id)
            .join(ProjectSetupRun, ProjectSetupRun.source_snapshot_id == GuideSourceSnapshot.id)
            .join(source, source.resource_id == GuideSourceSnapshot.id)
            .join(root, root.resource_id == ProjectGuide.id)
            .where(
                ProjectGuide.id == str(guide_id),
                ProjectGuide.project_id == str(project_id),
                ProjectGuide.status == "draft",
                GuideSourceSnapshot.project_id == str(project_id),
                GuideSourceSnapshot.guide_version == ProjectGuide.version,
                GuideSourceSnapshot.creation_generation == 1,
                GuideSourceSnapshotItem.id == str(document_id),
                GuideSourceSnapshotItem.source_kind == "document",
                GuideSourceSnapshotItem.ingestion_adapter == "upload",
                ProjectSetupRun.project_id == str(project_id),
                ProjectSetupRun.guide_id == str(guide_id),
                ProjectSetupRun.guide_version == ProjectGuide.version,
                ProjectSetupRun.source_snapshot_hash == GuideSourceSnapshot.bundle_hash,
                ProjectSetupRun.setup_generation == latest_setup,
                source.action_id == "project.guide_source_snapshot.create",
                root.action_id == "project.guide.create",
                root.status == "committed",
                source.status == "committed",
                root.idempotency_key == source.idempotency_key,
                root.actor_profile_id == source.actor_profile_id,
                root.identity_link_id == source.identity_link_id,
                root.project_id == source.project_id,
                root.project_id == str(project_id),
                root.response_json["setup"]["id"].as_string() == source.setup_run_id,
            )
        )
        if for_update:
            statement = statement.with_for_update(
                of=(
                    ProjectGuide,
                    GuideSourceSnapshot,
                    GuideSourceSnapshotItem,
                    ProjectSetupRun,
                )
            )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        used = await self._session.scalar(
            select(func.coalesce(func.sum(GuideSourceArtifactIngest.byte_count), 0))
            .join(
                GuideSourceSnapshotItem,
                GuideSourceSnapshotItem.id == GuideSourceArtifactIngest.source_item_id,
            )
            .where(
                GuideSourceSnapshotItem.source_snapshot_id == row.id,
                GuideSourceSnapshotItem.id != str(document_id),
            )
        )
        return GuideDocumentUploadTarget(
            snapshot_id=UUID(row.id),
            setup_id=UUID(row.setup_id),
            setup_generation=row.setup_generation,
            media_type=row.media_type,
            other_document_bytes=int(used),
        )
