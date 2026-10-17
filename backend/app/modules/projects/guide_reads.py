"""PROJECTS-owned guide reads for an already authorized Project Manager; no content bodies."""

from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.projects.api.guide_documents import LabeledGuideOriginal, ProjectGuideDocumentSource
from app.modules.projects.api.guide_reads import (
    GuideDocumentSelection,
    GuideReviewPolicyValues,
    GuideRevisionPolicyValues,
    ProjectGuideDeclaredDocument,
    ProjectGuideDetail,
    ProjectGuideReadUnavailable,
    ProjectGuideRecord,
    ProjectGuideSummary,
)
from app.modules.projects.guide_compilation.repository import (
    GuideCompilationIntegrityError,
    GuideCompilationRepository,
)
from app.modules.projects.models import (
    GuideSourceArtifactIngest,
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    ProjectGuide,
)
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import ReviewPolicyResponse, RevisionPolicyResponse


class ProjectGuideReader:
    """Fixed projections of one project's guides; the caller owns authority and the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Read through the caller's session and snapshot."""
        self._session = session

    async def list_guides(self, project_id, *, status, after, limit):
        """Page the project's guides by ``(created_at, id)``, optionally by stored status."""
        statement = select(
            ProjectGuide.id, ProjectGuide.version, ProjectGuide.status,
            ProjectGuide.created_at, ProjectGuide.effective_at,
        ).where(ProjectGuide.project_id == str(project_id))
        if status is not None:
            statement = statement.where(ProjectGuide.status == status)
        if after is not None:
            statement = statement.where(
                tuple_(ProjectGuide.created_at, ProjectGuide.id) > (after[0], str(after[1]))
            )
        rows = (await self._session.execute(
            statement.order_by(ProjectGuide.created_at, ProjectGuide.id).limit(limit + 1)
        )).all()
        items = tuple(
            ProjectGuideSummary(
                guide_id=UUID(str(row.id)), version=row.version, status=row.status,
                created_at=row.created_at, effective_at=row.effective_at,
            )
            for row in rows[:limit]
        )
        return items, len(rows) > limit

    async def guide_in_project(self, project_id: UUID, guide_id: UUID) -> bool:
        """Whether the guide belongs to the project."""
        return await self._guide(project_id, guide_id) is not None

    async def read_guide(self, project_id: UUID, guide_id: UUID) -> ProjectGuideDetail | None:
        """The guide record, declared documents, selected policies and latest setup lineage."""
        guide = await self._guide(project_id, guide_id)
        if guide is None:
            return None
        repository = ProjectRepository(self._session)
        snapshot = await self._documents_snapshot(guide)
        rows = () if snapshot is None else (await self._session.execute(
            select(GuideSourceSnapshotItem, GuideSourceArtifactIngest)
            .outerjoin(
                GuideSourceArtifactIngest,
                GuideSourceArtifactIngest.source_item_id == GuideSourceSnapshotItem.id,
            )
            .where(
                GuideSourceSnapshotItem.source_snapshot_id == snapshot.id,
                GuideSourceSnapshotItem.source_kind == "document",
                GuideSourceSnapshotItem.ingestion_adapter == "upload",
            )
            .order_by(GuideSourceSnapshotItem.item_order, GuideSourceSnapshotItem.id)
        )).all()
        documents = tuple(
            ProjectGuideDeclaredDocument(
                document_id=UUID(item.id), label=item.source_label, media_type=item.media_type,
                order=item.item_order, ingest_state="awaiting_upload" if ingest is None else "uploaded",
                sha256=None if ingest is None else ingest.sha256,
                byte_count=None if ingest is None else ingest.byte_count,
            )
            for item, ingest in rows
        )
        review = await repository.get_review_policy(guide.project_id, guide.version)
        revision = await repository.get_revision_policy(guide.project_id, guide.version)
        setup = await repository.get_latest_project_setup_run(guide.project_id, guide.id)
        try:
            compilation = await GuideCompilationRepository(self._session).current_compilation(
                project_id, guide_id, lock=False,
            )
        except GuideCompilationIntegrityError as exc:
            raise ProjectGuideReadUnavailable("guide compilation lineage unavailable") from exc
        return ProjectGuideDetail(
            guide=ProjectGuideRecord(
                guide_id=UUID(guide.id), project_id=UUID(guide.project_id), version=guide.version,
                status=guide.status, change_summary=guide.change_summary,
                task_examples_hash=guide.task_examples_hash,
                contribution_policy_id=guide.contribution_policy_id,
                contribution_policy_version_id=guide.contribution_policy_version_id,
                activation_operation_id=guide.activation_operation_id, approved_by=guide.approved_by,
                created_by=guide.created_by, created_at=guide.created_at, updated_at=guide.updated_at,
                effective_at=guide.effective_at, superseded_at=guide.superseded_at,
            ),
            documents=documents,
            review_policy=None if review is None else _review_values(review),
            revision_policy=None if revision is None else _revision_values(revision),
            latest_setup_run_id=None if setup is None else UUID(setup.id),
            latest_compilation_id=None if compilation is None else compilation.id,
        )

    async def select_document(self, project_id, guide_id, document_id) -> GuideDocumentSelection | None:
        """A declared upload document of a guide in the project and its committed ingest, if any."""
        guide = await self._guide(project_id, guide_id)
        snapshot = None if guide is None else await self._documents_snapshot(guide)
        if snapshot is None:
            return None
        row = (await self._session.execute(
            select(GuideSourceSnapshotItem, GuideSourceArtifactIngest)
            .outerjoin(
                GuideSourceArtifactIngest,
                GuideSourceArtifactIngest.source_item_id == GuideSourceSnapshotItem.id,
            )
            .where(
                GuideSourceSnapshotItem.id == str(document_id),
                GuideSourceSnapshotItem.source_snapshot_id == snapshot.id,
                GuideSourceSnapshotItem.source_kind == "document",
                GuideSourceSnapshotItem.ingestion_adapter == "upload",
            )
        )).one_or_none()
        if row is None:
            return None
        item, ingest = row
        if ingest is None:
            return GuideDocumentSelection(None)
        if ingest.media_type != item.media_type:
            raise ProjectGuideReadUnavailable("guide document identity mismatch")
        return GuideDocumentSelection(LabeledGuideOriginal(item.source_label, ProjectGuideDocumentSource(
            source_item_id=UUID(item.id), ingest_id=UUID(ingest.id), item_order=item.item_order,
            sha256=ingest.sha256, byte_count=ingest.byte_count, media_type=ingest.media_type,
        )))

    async def _guide(self, project_id: UUID, guide_id: UUID) -> ProjectGuide | None:
        """The guide only when it belongs to the project."""
        return await self._session.scalar(select(ProjectGuide).where(
            ProjectGuide.id == str(guide_id), ProjectGuide.project_id == str(project_id),
        ))

    async def _documents_snapshot(self, guide: ProjectGuide) -> GuideSourceSnapshot | None:
        """The one document set written with the guide, integrity-checked; legacy guides have none."""
        snapshots = (await self._session.scalars(select(GuideSourceSnapshot).where(
            GuideSourceSnapshot.guide_id == guide.id,
            GuideSourceSnapshot.project_id == guide.project_id,
            GuideSourceSnapshot.guide_version == guide.version,
            GuideSourceSnapshot.creation_generation == 1,
        ).limit(2))).all()
        if len(snapshots) > 1:
            raise ProjectGuideReadUnavailable("multiple guide document sets")
        if not snapshots:
            return None
        snapshot = snapshots[0]
        if canonical_json_hash(snapshot.manifest_json) != snapshot.bundle_hash:
            raise ProjectGuideReadUnavailable("guide document set integrity mismatch")
        return snapshot


def _review_values(row) -> GuideReviewPolicyValues:
    """Project a selected review policy through the existing stored-response validation."""
    stored = ReviewPolicyResponse.model_validate(row)
    return GuideReviewPolicyValues(
        policy_id=UUID(stored.id), generation=stored.policy_generation, policy_hash=stored.policy_hash,
        **stored.model_dump(include={
            "human_review_required", "semantics_format", "semantics_status",
            "review_preference_window_seconds", "review_lease_duration_seconds",
            "max_active_review_leases_per_reviewer", "self_review_allowed", "reject_policy",
            "finding_evidence_requirement", "created_at",
        }),
        supersedes_policy_id=stored.supersedes_policy_id,
        allowed_decisions=tuple(stored.allowed_decisions),
        minimum_finding_fields=tuple(stored.minimum_finding_fields),
    )


def _revision_values(row) -> GuideRevisionPolicyValues:
    """Project a selected revision policy through the existing stored-response validation."""
    stored = RevisionPolicyResponse.model_validate(row)
    return GuideRevisionPolicyValues(
        policy_id=UUID(stored.id), generation=stored.policy_generation, policy_hash=stored.policy_hash,
        **stored.model_dump(include={
            "semantics_status", "max_revision_rounds", "revision_deadline_hours",
            "reviewer_reassignment_rule", "created_at",
        }),
        supersedes_policy_id=stored.supersedes_policy_id,
        allowed_resubmission_states=tuple(stored.allowed_resubmission_states),
    )
