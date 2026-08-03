"""Live same-generation composition for verified guide-source preparation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.interfaces.artifact_operations import (
    GuideSourceBindingRequest,
    GuideSourceMaterializationRequest,
)
from app.interfaces.artifacts import ArtifactStore
from app.modules.artifacts.authorization import (
    PreparedGuideSourceBindingAuthorization,
    PreparedGuideSourceReadAuthorization,
)
from app.modules.artifacts.guide_bindings import (
    GuideSourceBindingService,
    guide_source_binding_authority_facts,
)
from app.modules.artifacts.guide_extraction import GuideExtractionRegistry
from app.modules.artifacts.guide_extraction_service import (
    GuideExtractionCoordinator,
    GuideExtractionRequest,
    GuideExtractionService,
)
from app.modules.artifacts.guide_formats import GuideFormatDetector, GuideFormatLimits
from app.modules.artifacts.guide_materialization import (
    ArtifactMaterializationService,
    AuthorizedGuideExtractionMaterializer,
)
from app.modules.artifacts.preparation import ArtifactPreparationService
from app.modules.artifacts.repository import ArtifactRepository
from app.modules.artifacts.service import ArtifactStorageNamespaceSpec
from app.modules.projects.models import GuideSourceSnapshotItem, ProjectSetupRun


@dataclass(frozen=True, slots=True)
class _VerifiedItem:
    item_id: UUID
    content_id: UUID
    replica_id: UUID
    sha256: str
    byte_count: int


class GuideSetupPreparationService:
    """Bind, classify, and extract every verified item for one setup generation."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        store: ArtifactStore,
        preparation: ArtifactPreparationService,
        namespace: ArtifactStorageNamespaceSpec,
    ) -> None:
        self._session_factory = session_factory
        self._materialization = ArtifactMaterializationService(
            session_factory,
            store,
            preparation,
            GuideFormatDetector(GuideFormatLimits()),
            namespace,
            authority_factory=lambda session: PreparedGuideSourceReadAuthorization(
                session,
                request_id=uuid4(),
                correlation_id=uuid4(),
            ),
        )
        self._extraction = GuideExtractionCoordinator(
            GuideExtractionService(session_factory, GuideExtractionRegistry()),
            AuthorizedGuideExtractionMaterializer(self._materialization),
        )

    async def prepare_generation(
        self,
        *,
        project_id: UUID,
        guide_id: UUID,
        source_snapshot_id: UUID,
        setup_run_id: UUID,
        setup_generation: int,
    ) -> bool:
        """Return true only when every declared item has canonical extraction usage."""
        async with self._session_factory() as session:
            run = await session.scalar(
                select(ProjectSetupRun).where(
                    ProjectSetupRun.id == str(setup_run_id),
                    ProjectSetupRun.project_id == str(project_id),
                    ProjectSetupRun.guide_id == str(guide_id),
                    ProjectSetupRun.source_snapshot_id == str(source_snapshot_id),
                    ProjectSetupRun.setup_generation == setup_generation,
                )
            )
            if run is None:
                return False
            item_ids = list(
                (
                    await session.scalars(
                        select(GuideSourceSnapshotItem.id)
                        .where(
                            GuideSourceSnapshotItem.source_snapshot_id == str(source_snapshot_id)
                        )
                        .order_by(GuideSourceSnapshotItem.item_order)
                    )
                ).all()
            )
        if not item_ids:
            return False
        verified_items: list[_VerifiedItem] = []
        for item_id in item_ids:
            item = await self._verified_item(UUID(item_id))
            if item is None:
                return False
            verified_items.append(item)
        for item in verified_items:
            await self._prepare_item(
                item,
                project_id=project_id,
                guide_id=guide_id,
                source_snapshot_id=source_snapshot_id,
                setup_run_id=setup_run_id,
                setup_generation=setup_generation,
            )
        return True

    async def _verified_item(self, item_id: UUID) -> _VerifiedItem | None:
        async with self._session_factory() as session:
            candidate = await ArtifactRepository(session).get_verified_guide_content_candidate(
                str(item_id), lock_replica=False
            )
        if candidate is None:
            return None
        return _VerifiedItem(
            item_id=item_id,
            content_id=UUID(candidate.content_id),
            replica_id=UUID(candidate.replica_id),
            sha256=candidate.sha256,
            byte_count=candidate.byte_count,
        )

    async def _prepare_item(
        self,
        item: _VerifiedItem,
        *,
        project_id: UUID,
        guide_id: UUID,
        source_snapshot_id: UUID,
        setup_run_id: UUID,
        setup_generation: int,
    ) -> None:
        facts = guide_source_binding_authority_facts(
            project_id=project_id,
            guide_id=guide_id,
            source_snapshot_id=source_snapshot_id,
            source_item_id=item.item_id,
            setup_run_id=setup_run_id,
            setup_generation=setup_generation,
            content_id=item.content_id,
            replica_id=item.replica_id,
            sha256=item.sha256,
            byte_count=item.byte_count,
        )
        async with self._session_factory() as session, session.begin():
            authority = PreparedGuideSourceBindingAuthorization(
                session,
                request_id=uuid4(),
                correlation_id=uuid4(),
            )
            handle = await authority.prepare(facts=facts, idempotency_key=uuid4())
            binding = await GuideSourceBindingService(session, authority).bind_guide_source(
                GuideSourceBindingRequest(
                    prepared_authorization=handle,
                    project_id=project_id,
                    guide_id=guide_id,
                    guide_source_snapshot_id=source_snapshot_id,
                    source_item_id=item.item_id,
                    project_setup_run_id=setup_run_id,
                    setup_generation=setup_generation,
                    logical_role="guide_source_original",
                    verified_content_id=item.content_id,
                )
            )
        classification = await self._materialization.materialize_guide_source(
            GuideSourceMaterializationRequest(
                idempotency_key=uuid4(),
                project_id=project_id,
                guide_id=guide_id,
                guide_source_snapshot_id=source_snapshot_id,
                source_item_id=item.item_id,
                project_setup_run_id=setup_run_id,
                setup_generation=setup_generation,
                binding_id=binding.binding_id,
            )
        )
        await self._extraction.extract(
            GuideExtractionRequest(
                project_id=project_id,
                guide_id=guide_id,
                source_snapshot_id=source_snapshot_id,
                source_item_id=item.item_id,
                project_setup_run_id=setup_run_id,
                setup_generation=setup_generation,
                binding_id=binding.binding_id,
                classification_id=classification.classification_id,
            )
        )
