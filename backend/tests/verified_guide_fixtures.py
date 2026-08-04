"""Shared verified guide-lineage fixtures for backend product tests."""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from sqlalchemy import select

from app.db import session as db_session
from app.modules.artifacts.guide_extraction import EXTRACTION_POLICY_VERSION
from app.modules.artifacts.models import (
    ArtifactContent,
    ArtifactReplica,
    ArtifactStorageNamespace,
    GuideSourceArtifactBinding,
    GuideSourceExtractedContent,
    GuideSourceExtractionAttempt,
    GuideSourceExtractionUsage,
    GuideSourceFormatClassification,
)
from app.interfaces.artifact_operations import (
    GuideSufficiencyExtractionProvenance,
    GuideSufficiencyMaterialResult,
    GuideSufficiencySourceItem,
)
from app.modules.projects.service import (
    PROJECT_GUIDE_SUFFICIENCY_AGENT_NAME,
    PROJECT_GUIDE_SUFFICIENCY_AGENT_VERSION,
)
from app.modules.projects.models import (
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    GuideSufficiencyReport,
    GuideSufficiencyReportSourceUsage,
    ProjectSetupRun,
)


def sha256_hash(seed: str) -> str:
    """Return the canonical SHA-256 shape used by fixture provenance."""
    return "sha256:" + hashlib.sha256(seed.encode()).hexdigest()


async def create_verified_material_fixture(
    source_snapshot_id: str,
) -> GuideSufficiencyMaterialResult:
    """Persist exact ART lineage and return material backed by those same rows."""
    async with db_session.get_session_factory()() as session:
        snapshot = await session.get(GuideSourceSnapshot, source_snapshot_id)
        setup_run = await session.scalar(
            select(ProjectSetupRun)
            .where(ProjectSetupRun.source_snapshot_id == source_snapshot_id)
            .order_by(ProjectSetupRun.setup_generation.desc())
            .limit(1)
        )
        items = list(
            (
                await session.scalars(
                    select(GuideSourceSnapshotItem)
                    .where(GuideSourceSnapshotItem.source_snapshot_id == source_snapshot_id)
                    .order_by(GuideSourceSnapshotItem.item_order)
                )
            ).all()
        )
        assert snapshot is not None
        assert setup_run is not None
        assert items
        namespace = await session.get(ArtifactStorageNamespace, "primary")
        if namespace is None:
            namespace = ArtifactStorageNamespace(
                id="primary",
                backend="local",
                adapter="local",
                provider_profile="test",
                namespace_descriptor={"root": "verified-material-fixture"},
                namespace_fingerprint=sha256_hash("verified-material-namespace"),
            )
            session.add(namespace)
            await session.flush()
        material_items: list[GuideSufficiencySourceItem] = []
        provenance: list[GuideSufficiencyExtractionProvenance] = []
        for item in items:
            canonical_output = f"Verified content for {item.source_label}."
            source_digest = sha256_hash(f"source:{item.id}")
            output_digest = sha256_hash(canonical_output)
            content_id, replica_id, binding_id, classification_id = (
                str(uuid4()) for _ in range(4)
            )
            attempt_id, extracted_content_id, usage_id = (
                str(uuid4()) for _ in range(3)
            )
            byte_count = len(canonical_output.encode())
            session.add(
                ArtifactContent(
                    id=content_id,
                    sha256=source_digest,
                    byte_count=byte_count,
                    media_type="text/plain",
                    normalized_display_name=item.source_label,
                )
            )
            await session.flush()
            session.add(
                ArtifactReplica(
                    id=replica_id,
                    content_id=content_id,
                    storage_namespace_id=namespace.id,
                    namespace_fingerprint=namespace.namespace_fingerprint,
                    adapter=namespace.adapter,
                    provider_profile=namespace.provider_profile,
                    provider_object_ref=f"fixtures/{content_id}",
                    verification_state="verified",
                    availability_state="available",
                    integrity_state="valid",
                )
            )
            await session.flush()
            session.add(
                GuideSourceArtifactBinding(
                    id=binding_id,
                    project_id=snapshot.project_id,
                    guide_id=snapshot.guide_id,
                    source_snapshot_id=source_snapshot_id,
                    source_item_id=item.id,
                    project_setup_run_id=setup_run.id,
                    setup_generation=setup_run.setup_generation,
                    content_id=content_id,
                    verified_replica_id=replica_id,
                    logical_role="guide_source_original",
                    created_by_service="test.verified_material_fixture",
                )
            )
            await session.flush()
            session.add(
                GuideSourceFormatClassification(
                    id=classification_id,
                    binding_id=binding_id,
                    content_id=content_id,
                    verified_replica_id=replica_id,
                    setup_generation=setup_run.setup_generation,
                    sha256=source_digest,
                    byte_count=byte_count,
                    media_type="text/plain",
                    detected_format="plain_text",
                    status="classified",
                    detector_name="workstream.guide_format",
                    detector_version="1",
                    classification_facts={},
                )
            )
            await session.flush()
            session.add_all(
                [
                    GuideSourceExtractionAttempt(
                        id=attempt_id,
                        binding_id=binding_id,
                        content_id=content_id,
                        classification_id=classification_id,
                        setup_generation=setup_run.setup_generation,
                        detected_format="plain_text",
                        extractor_name="workstream.plain_text",
                        extractor_version="1",
                        policy_version=EXTRACTION_POLICY_VERSION,
                        attempt_number=1,
                        status="extracted",
                        error_code=None,
                        bounded_facts={},
                    ),
                    GuideSourceExtractedContent(
                        id=extracted_content_id,
                        content_id=content_id,
                        detected_format="plain_text",
                        extractor_name="workstream.plain_text",
                        extractor_version="1",
                        policy_version=EXTRACTION_POLICY_VERSION,
                        source_sha256=source_digest,
                        source_byte_count=byte_count,
                        status="extracted",
                        output_sha256=output_digest,
                        canonical_output=canonical_output,
                        omission_facts={},
                    ),
                ]
            )
            await session.flush()
            session.add(
                GuideSourceExtractionUsage(
                    id=usage_id,
                    extracted_content_id=extracted_content_id,
                    extraction_attempt_id=attempt_id,
                    attempt_status="extracted",
                    binding_id=binding_id,
                    content_id=content_id,
                    source_item_id=item.id,
                    project_setup_run_id=setup_run.id,
                    setup_generation=setup_run.setup_generation,
                )
            )
            await session.flush()
            material_items.append(
                GuideSufficiencySourceItem(
                    source_kind=item.source_kind,
                    ingestion_adapter=item.ingestion_adapter,
                    source_item_id=UUID(item.id),
                    item_order=item.item_order,
                    binding_id=UUID(binding_id),
                    content_id=UUID(content_id),
                    artifact_sha256=source_digest,
                    artifact_byte_count=byte_count,
                    media_type="text/plain",
                    classification_id=UUID(classification_id),
                    detected_format="plain_text",
                    extraction_attempt_id=UUID(attempt_id),
                    extraction_usage_id=UUID(usage_id),
                    extracted_content_id=UUID(extracted_content_id),
                    extractor_name="workstream.plain_text",
                    extractor_version="1",
                    extraction_policy_version=EXTRACTION_POLICY_VERSION,
                    canonical_output_sha256=output_digest,
                    omission_facts={},
                    canonical_content=canonical_output,
                    structural_metadata={"source_kind": item.source_kind},
                )
            )
            provenance.append(
                GuideSufficiencyExtractionProvenance(
                    item_order=item.item_order,
                    source_item_id=UUID(item.id),
                    binding_id=UUID(binding_id),
                    content_id=UUID(content_id),
                    extraction_usage_id=UUID(usage_id),
                    extraction_attempt_id=UUID(attempt_id),
                    extracted_content_id=UUID(extracted_content_id),
                    canonical_output_sha256=output_digest,
                )
            )
        await session.commit()
        return GuideSufficiencyMaterialResult(
            source_items=tuple(material_items),
            provenance=tuple(provenance),
        )


async def create_verified_report_fixture(
    report_id: str,
    source_snapshot_id: str,
) -> str:
    """Give broad policy tests exact verified provenance without replaying ART e2e.

    ART binding and extraction integrity is exercised in ``test_guide_bindings``.
    These project-policy fixtures need only a complete, server-owned usage set.
    """
    async with db_session.get_session_factory()() as session:
        diagnostic_report = await session.get(GuideSufficiencyReport, report_id)
        setup_run = await session.scalar(
            select(ProjectSetupRun)
            .where(ProjectSetupRun.source_snapshot_id == source_snapshot_id)
            .order_by(ProjectSetupRun.setup_generation.desc())
            .limit(1)
        )
        items = list(
            (
                await session.scalars(
                    select(GuideSourceSnapshotItem)
                    .where(GuideSourceSnapshotItem.source_snapshot_id == source_snapshot_id)
                    .order_by(GuideSourceSnapshotItem.item_order)
                )
            ).all()
        )
        assert diagnostic_report is not None
        assert items
        if setup_run is None:
            snapshot = await session.get(GuideSourceSnapshot, source_snapshot_id)
            assert snapshot is not None
            setup_run = ProjectSetupRun(
                id=str(uuid4()),
                project_id=diagnostic_report.project_id,
                guide_id=diagnostic_report.guide_id,
                guide_version=diagnostic_report.guide_version,
                source_snapshot_id=source_snapshot_id,
                source_snapshot_hash=diagnostic_report.source_snapshot_hash,
                setup_generation=snapshot.creation_generation,
                status="queued",
                current_step="queued",
                created_by="project-manager-subject",
            )
            session.add(setup_run)
            await session.flush()
        report = GuideSufficiencyReport(
            id=str(uuid4()),
            project_id=diagnostic_report.project_id,
            guide_id=diagnostic_report.guide_id,
            guide_version=diagnostic_report.guide_version,
            source_snapshot_id=diagnostic_report.source_snapshot_id,
            source_snapshot_hash=diagnostic_report.source_snapshot_hash,
            status=diagnostic_report.status,
            findings=diagnostic_report.findings,
            summary=diagnostic_report.summary,
            agent_name=PROJECT_GUIDE_SUFFICIENCY_AGENT_NAME,
            agent_version=PROJECT_GUIDE_SUFFICIENCY_AGENT_VERSION,
            project_setup_run_id=setup_run.id,
            setup_generation=setup_run.setup_generation,
            agent_material_sha256=f"sha256:{'a' * 64}",
            agent_material_byte_count=1,
            created_by="workstream-system:project-policy-fixture",
        )
        session.add(report)
        await session.flush()

        namespace = await session.get(ArtifactStorageNamespace, "primary")
        if namespace is None:
            namespace = ArtifactStorageNamespace(
                id="primary",
                backend="local",
                adapter="local",
                provider_profile="test",
                namespace_descriptor={"root": "project-policy-fixture"},
                namespace_fingerprint=f"sha256:{'c' * 64}",
            )
            session.add(namespace)
            await session.flush()
        for item in items:
            canonical_output = f"verified guide source item {item.item_order}"
            source_digest = sha256_hash(f"source:{item.id}")
            output_digest = sha256_hash(canonical_output)
            content_id = str(uuid4())
            replica_id = str(uuid4())
            binding_id = str(uuid4())
            classification_id = str(uuid4())
            attempt_id = str(uuid4())
            extracted_content_id = str(uuid4())
            extraction_usage_id = str(uuid4())
            session.add(
                ArtifactContent(
                    id=content_id,
                    sha256=source_digest,
                    byte_count=len(canonical_output.encode()),
                    media_type="text/plain",
                    normalized_display_name=item.source_label,
                )
            )
            await session.flush()
            session.add(
                ArtifactReplica(
                    id=replica_id,
                    content_id=content_id,
                    storage_namespace_id=namespace.id,
                    namespace_fingerprint=namespace.namespace_fingerprint,
                    adapter=namespace.adapter,
                    provider_profile=namespace.provider_profile,
                    provider_object_ref=f"fixtures/{content_id}",
                    verification_state="verified",
                    availability_state="available",
                    integrity_state="valid",
                )
            )
            await session.flush()
            session.add(
                GuideSourceArtifactBinding(
                    id=binding_id,
                    project_id=report.project_id,
                    guide_id=report.guide_id,
                    source_snapshot_id=source_snapshot_id,
                    source_item_id=item.id,
                    project_setup_run_id=setup_run.id,
                    setup_generation=setup_run.setup_generation,
                    content_id=content_id,
                    verified_replica_id=replica_id,
                    logical_role="guide_source_original",
                    created_by_service="test.project_policy_fixture",
                )
            )
            await session.flush()
            session.add(
                GuideSourceFormatClassification(
                    id=classification_id,
                    binding_id=binding_id,
                    content_id=content_id,
                    verified_replica_id=replica_id,
                    setup_generation=setup_run.setup_generation,
                    sha256=source_digest,
                    byte_count=len(canonical_output.encode()),
                    media_type="text/plain",
                    detected_format="plain_text",
                    status="classified",
                    detector_name="workstream.guide_format",
                    detector_version="1",
                    classification_facts={},
                )
            )
            await session.flush()
            session.add_all(
                [
                    GuideSourceExtractionAttempt(
                        id=attempt_id,
                        binding_id=binding_id,
                        content_id=content_id,
                        classification_id=classification_id,
                        setup_generation=setup_run.setup_generation,
                        detected_format="plain_text",
                        extractor_name="workstream.plain_text",
                        extractor_version="1",
                        policy_version=EXTRACTION_POLICY_VERSION,
                        attempt_number=1,
                        status="extracted",
                        error_code=None,
                        bounded_facts={},
                    ),
                    GuideSourceExtractedContent(
                        id=extracted_content_id,
                        content_id=content_id,
                        detected_format="plain_text",
                        extractor_name="workstream.plain_text",
                        extractor_version="1",
                        policy_version=EXTRACTION_POLICY_VERSION,
                        source_sha256=source_digest,
                        source_byte_count=len(canonical_output.encode()),
                        status="extracted",
                        output_sha256=output_digest,
                        canonical_output=canonical_output,
                        omission_facts={},
                    ),
                ]
            )
            await session.flush()
            session.add(
                GuideSourceExtractionUsage(
                    id=extraction_usage_id,
                    extracted_content_id=extracted_content_id,
                    extraction_attempt_id=attempt_id,
                    attempt_status="extracted",
                    binding_id=binding_id,
                    content_id=content_id,
                    source_item_id=item.id,
                    project_setup_run_id=setup_run.id,
                    setup_generation=setup_run.setup_generation,
                )
            )
            await session.flush()
            session.add(
                GuideSufficiencyReportSourceUsage(
                    id=str(uuid4()),
                    report_id=report.id,
                    item_order=item.item_order,
                    source_item_id=item.id,
                    binding_id=binding_id,
                    content_id=content_id,
                    extraction_usage_id=extraction_usage_id,
                    extraction_attempt_id=attempt_id,
                    extracted_content_id=extracted_content_id,
                    project_setup_run_id=setup_run.id,
                    setup_generation=setup_run.setup_generation,
                    canonical_output_sha256=output_digest,
                )
            )
        setup_run.output_sufficiency_report_id = report.id
        await session.commit()
        return report.id
