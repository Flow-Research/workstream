"""Complete same-generation guide material for the hidden sufficiency continuation."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.artifact_operations import (
    GuideSufficiencyMaterialRequest,
    GuideSufficiencyMaterialResult,
    GuideSufficiencyMaterialUnavailable,
    GuideSufficiencyExtractionProvenance,
    GuideSufficiencySourceItem,
)
from app.modules.artifacts.guide_extraction import extraction_policy_version
from app.modules.artifacts.guide_formats import DETECTOR_NAME, DETECTOR_VERSION
from app.modules.artifacts.models import (
    ArtifactContent,
    GuideSourceArtifactBinding,
    GuideSourceArtifactIncident,
    GuideSourceExtractedContent,
    GuideSourceExtractionAttempt,
    GuideSourceExtractionUsage,
    GuideSourceFormatClassification,
)
from app.modules.projects.models import (
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    ProjectGuide,
    ProjectSetupRun,
)

IMAGE_FORMATS = frozenset({"png", "jpeg", "webp"})
FAILURE_CODES = {
    "unsupported": "guide_source_format_unsupported",
    "ambiguous": "guide_source_format_ambiguous",
    "malformed": "guide_source_malformed",
    "limit_exceeded": "guide_source_limit_exceeded",
    "parser_failure": "guide_source_extraction_failed",
    "cancelled": "guide_source_extraction_cancelled",
    "artifact_incident": "guide_artifact_incident",
}


class SqlAlchemyGuideSufficiencyMaterialAdapter:
    """Read and validate ART-owned canonical extraction persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(
        self, request: GuideSufficiencyMaterialRequest
    ) -> GuideSufficiencyMaterialResult:
        """Lock and assemble every required item for one exact current generation."""
        project_id = str(request.project_id)
        guide_id = str(request.guide_id)
        snapshot_id = str(request.guide_source_snapshot_id)
        setup_run_id = str(request.project_setup_run_id)
        header = (
            await self._session.execute(
                select(ProjectGuide, GuideSourceSnapshot, ProjectSetupRun)
                .join(
                    GuideSourceSnapshot,
                    GuideSourceSnapshot.guide_id == ProjectGuide.id,
                )
                .join(ProjectSetupRun, ProjectSetupRun.guide_id == ProjectGuide.id)
                .where(
                    ProjectGuide.id == guide_id,
                    ProjectGuide.project_id == project_id,
                    ProjectGuide.status == "draft",
                    GuideSourceSnapshot.id == snapshot_id,
                    GuideSourceSnapshot.project_id == project_id,
                    GuideSourceSnapshot.guide_version == ProjectGuide.version,
                    ProjectSetupRun.id == setup_run_id,
                    ProjectSetupRun.project_id == project_id,
                    ProjectSetupRun.source_snapshot_id == snapshot_id,
                    ProjectSetupRun.source_snapshot_hash == GuideSourceSnapshot.bundle_hash,
                    ProjectSetupRun.setup_generation == request.setup_generation,
                )
                .with_for_update(of=(ProjectGuide, GuideSourceSnapshot, ProjectSetupRun))
            )
        ).one_or_none()
        if header is None:
            raise GuideSufficiencyMaterialUnavailable("guide_source_stale")
        latest_generation = await self._session.scalar(
            select(func.max(ProjectSetupRun.setup_generation)).where(
                ProjectSetupRun.guide_id == guide_id
            )
        )
        if latest_generation != request.setup_generation:
            raise GuideSufficiencyMaterialUnavailable("guide_source_stale")

        items = (
            await self._session.execute(
                select(GuideSourceSnapshotItem)
                .where(GuideSourceSnapshotItem.source_snapshot_id == snapshot_id)
                .order_by(GuideSourceSnapshotItem.item_order, GuideSourceSnapshotItem.id)
                .with_for_update()
            )
        ).scalars().all()
        if not items:
            raise GuideSufficiencyMaterialUnavailable("guide_source_extraction_failed")

        material_items: list[GuideSufficiencySourceItem] = []
        provenance: list[GuideSufficiencyExtractionProvenance] = []
        for item in items:
            rows = (
                await self._session.execute(
                    select(
                        GuideSourceArtifactBinding,
                        ArtifactContent,
                        GuideSourceFormatClassification,
                        GuideSourceExtractionAttempt,
                        GuideSourceExtractionUsage,
                        GuideSourceExtractedContent,
                    )
                    .join(
                        ArtifactContent,
                        ArtifactContent.id == GuideSourceArtifactBinding.content_id,
                    )
                    .join(
                        GuideSourceFormatClassification,
                        GuideSourceFormatClassification.binding_id
                        == GuideSourceArtifactBinding.id,
                    )
                    .join(
                        GuideSourceExtractionUsage,
                        GuideSourceExtractionUsage.binding_id == GuideSourceArtifactBinding.id,
                    )
                    .join(
                        GuideSourceExtractionAttempt,
                        GuideSourceExtractionAttempt.id
                        == GuideSourceExtractionUsage.extraction_attempt_id,
                    )
                    .join(
                        GuideSourceExtractedContent,
                        GuideSourceExtractedContent.id
                        == GuideSourceExtractionUsage.extracted_content_id,
                    )
                    .where(
                        GuideSourceArtifactBinding.project_id == project_id,
                        GuideSourceArtifactBinding.guide_id == guide_id,
                        GuideSourceArtifactBinding.source_snapshot_id == snapshot_id,
                        GuideSourceArtifactBinding.source_item_id == item.id,
                        GuideSourceArtifactBinding.project_setup_run_id == setup_run_id,
                        GuideSourceArtifactBinding.setup_generation == request.setup_generation,
                        GuideSourceFormatClassification.status == "classified",
                        GuideSourceFormatClassification.detector_name == DETECTOR_NAME,
                        GuideSourceFormatClassification.detector_version == DETECTOR_VERSION,
                        GuideSourceFormatClassification.content_id == ArtifactContent.id,
                        GuideSourceFormatClassification.sha256 == ArtifactContent.sha256,
                        GuideSourceFormatClassification.byte_count == ArtifactContent.byte_count,
                        GuideSourceFormatClassification.media_type == ArtifactContent.media_type,
                        GuideSourceExtractionAttempt.status == "extracted",
                        GuideSourceExtractionAttempt.classification_id
                        == GuideSourceFormatClassification.id,
                        GuideSourceExtractionUsage.source_item_id == item.id,
                        GuideSourceExtractionUsage.project_setup_run_id == setup_run_id,
                        GuideSourceExtractionUsage.setup_generation == request.setup_generation,
                        GuideSourceExtractedContent.content_id == ArtifactContent.id,
                        GuideSourceExtractedContent.source_sha256 == ArtifactContent.sha256,
                        GuideSourceExtractedContent.source_byte_count == ArtifactContent.byte_count,
                    )
                    .with_for_update(
                        of=(
                            GuideSourceArtifactBinding,
                            ArtifactContent,
                            GuideSourceFormatClassification,
                            GuideSourceExtractionAttempt,
                            GuideSourceExtractionUsage,
                            GuideSourceExtractedContent,
                        )
                    )
                )
            ).all()
            current_rows = [
                row
                for row in rows
                if row[3].policy_version == extraction_policy_version(row[2].detected_format)
                and row[5].policy_version == row[3].policy_version
            ]
            if len(current_rows) != 1:
                raise await self._failure_for(request, item.id)
            row = current_rows[0]
            binding, content, classification, attempt, usage, extracted = row
            if (
                extracted.output_sha256
                != f"sha256:{hashlib.sha256(extracted.canonical_output.encode('utf-8')).hexdigest()}"
            ):
                raise GuideSufficiencyMaterialUnavailable("guide_source_extraction_failed")
            structural = None
            canonical = extracted.canonical_output
            if classification.detected_format in IMAGE_FORMATS:
                try:
                    structural = json.loads(canonical)
                except (TypeError, ValueError):
                    raise GuideSufficiencyMaterialUnavailable("guide_source_malformed") from None
                if not isinstance(structural, dict):
                    raise GuideSufficiencyMaterialUnavailable("guide_source_malformed")
                canonical = None
            dto = GuideSufficiencySourceItem(
                source_kind=item.source_kind,
                ingestion_adapter=item.ingestion_adapter,
                media_type=content.media_type,
                source_item_id=UUID(item.id),
                item_order=item.item_order,
                binding_id=UUID(binding.id),
                content_id=UUID(content.id),
                artifact_sha256=content.sha256,
                artifact_byte_count=content.byte_count,
                classification_id=UUID(classification.id),
                detected_format=classification.detected_format,
                extraction_attempt_id=UUID(attempt.id),
                extraction_usage_id=UUID(usage.id),
                extracted_content_id=UUID(extracted.id),
                extractor_name=extracted.extractor_name,
                extractor_version=extracted.extractor_version,
                extraction_policy_version=extracted.policy_version,
                canonical_output_sha256=extracted.output_sha256,
                omission_facts=extracted.omission_facts,
                canonical_content=canonical,
                structural_metadata=structural,
            )
            material_items.append(dto)
            provenance.append(
                GuideSufficiencyExtractionProvenance(
                    item_order=item.item_order,
                    source_item_id=UUID(item.id),
                    binding_id=UUID(binding.id),
                    content_id=UUID(content.id),
                    extraction_usage_id=UUID(usage.id),
                    extraction_attempt_id=UUID(attempt.id),
                    extracted_content_id=UUID(extracted.id),
                    canonical_output_sha256=extracted.output_sha256,
                )
            )
        return GuideSufficiencyMaterialResult(
            source_items=tuple(material_items),
            provenance=tuple(provenance),
        )

    async def _failure_for(
        self,
        request: GuideSufficiencyMaterialRequest,
        source_item_id: str,
    ) -> GuideSufficiencyMaterialUnavailable:
        lineage = (
            GuideSourceArtifactBinding.project_id == str(request.project_id),
            GuideSourceArtifactBinding.guide_id == str(request.guide_id),
            GuideSourceArtifactBinding.source_snapshot_id
            == str(request.guide_source_snapshot_id),
            GuideSourceArtifactBinding.source_item_id == source_item_id,
            GuideSourceArtifactBinding.project_setup_run_id
            == str(request.project_setup_run_id),
            GuideSourceArtifactBinding.setup_generation == request.setup_generation,
        )
        incident = await self._session.scalar(
            select(GuideSourceArtifactIncident)
            .join(
                GuideSourceArtifactBinding,
                GuideSourceArtifactBinding.id == GuideSourceArtifactIncident.binding_id,
            )
            .where(*lineage)
            .order_by(GuideSourceArtifactIncident.created_at.desc())
            .limit(1)
        )
        if incident is not None:
            return GuideSufficiencyMaterialUnavailable(
                "guide_artifact_incident", incident_id=UUID(incident.id)
            )
        attempt = await self._session.scalar(
            select(GuideSourceExtractionAttempt)
            .join(
                GuideSourceArtifactBinding,
                GuideSourceArtifactBinding.id == GuideSourceExtractionAttempt.binding_id,
            )
            .where(*lineage)
            .order_by(GuideSourceExtractionAttempt.attempt_number.desc())
            .limit(1)
        )
        if attempt is not None:
            return GuideSufficiencyMaterialUnavailable(
                FAILURE_CODES.get(attempt.status, "guide_source_extraction_failed")
            )
        classification = await self._session.scalar(
            select(GuideSourceFormatClassification)
            .join(
                GuideSourceArtifactBinding,
                GuideSourceArtifactBinding.id == GuideSourceFormatClassification.binding_id,
            )
            .where(*lineage)
            .order_by(GuideSourceFormatClassification.created_at.desc())
            .limit(1)
        )
        if classification is not None:
            return GuideSufficiencyMaterialUnavailable(
                FAILURE_CODES.get(classification.status, "guide_source_extraction_failed")
            )
        return GuideSufficiencyMaterialUnavailable("guide_source_extraction_failed")
