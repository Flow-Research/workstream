"""Exact-lineage persistence for bounded guide extraction."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.cancellation import await_cancellation_resistant

from app.modules.artifacts.guide_extraction import (
    GuideExtractionRegistry,
    extraction_policy_version,
)
from app.modules.artifacts.guide_formats import DETECTOR_NAME, DETECTOR_VERSION
from app.modules.artifacts.models import (
    ArtifactContent,
    GuideSourceArtifactBinding,
    GuideSourceExtractedContent,
    GuideSourceExtractionAttempt,
    GuideSourceExtractionRetryBudget,
    GuideSourceExtractionUsage,
    GuideSourceFormatClassification,
)
from app.modules.artifacts.sources import PreparedArtifact
from app.modules.projects.models import (
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    ProjectGuide,
    ProjectSetupRun,
)


class GuideExtractionError(RuntimeError):
    """Concealed guide extraction persistence failure."""


class FreshAuthorizedGuideMaterializer(Protocol):
    """Supply one newly authorized and newly materialized exact guide source."""

    async def materialize_with_fresh_authority(
        self, request: GuideExtractionRequest
    ) -> PreparedArtifact:
        """Return a fresh prepared artifact after current authority revalidation."""


@dataclass(frozen=True, slots=True)
class GuideExtractionRequest:
    """Exact lineage selected for one prepared extraction."""

    project_id: UUID
    guide_id: UUID
    source_snapshot_id: UUID
    source_item_id: UUID
    project_setup_run_id: UUID
    setup_generation: int
    binding_id: UUID
    classification_id: UUID


@dataclass(frozen=True, slots=True)
class GuideExtractionPersistenceResult:
    """Bounded durable extraction outcome."""

    attempt_id: UUID
    status: str
    error_code: str | None
    extracted_content_id: UUID | None
    usage_id: UUID | None
    replayed: bool


@dataclass(frozen=True, slots=True)
class _ExtractionFacts:
    project_id: str
    guide_id: str
    snapshot_id: str
    item_id: str
    setup_run_id: str
    setup_generation: int
    binding_id: str
    classification_id: str
    content_id: str
    sha256: str
    byte_count: int
    detected_format: str
    classification_status: str


class GuideExtractionService:
    """Extract prepared verified bytes and publish exact immutable provenance."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        registry: GuideExtractionRegistry,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry

    async def extract_prepared(
        self,
        request: GuideExtractionRequest,
        prepared: PreparedArtifact,
    ) -> GuideExtractionPersistenceResult:
        """Revalidate, extract in isolation, revalidate, and persist one outcome."""
        async with self._session_factory() as session, session.begin():
            before = await self._load_facts(session, request)
        if before is None or before.classification_status != "classified":
            raise GuideExtractionError("guide extraction is unavailable")
        if (
            prepared.commitment.sha256 != before.sha256
            or prepared.commitment.byte_count != before.byte_count
        ):
            raise GuideExtractionError("guide extraction is unavailable")
        try:
            extracted = await prepared.extract_guide(self._registry.resolve(before.detected_format))
        except asyncio.CancelledError as cancellation:

            async def record_cancellation() -> None:
                async with self._session_factory() as session, session.begin():
                    after = await self._load_facts(session, request)
                    if after == before:
                        await self._persist_failure(
                            session,
                            before,
                            status="cancelled",
                            error_code="extraction_cancelled",
                        )

            recovery = asyncio.create_task(asyncio.wait_for(record_cancellation(), timeout=5.0))
            try:
                await await_cancellation_resistant(recovery)
            except Exception:
                pass
            raise cancellation from None
        async with self._session_factory() as session, session.begin():
            after = await self._load_facts(session, request)
            if after != before:
                raise GuideExtractionError("guide extraction is unavailable")
            if extracted.policy_version != extraction_policy_version(before.detected_format):
                raise GuideExtractionError("guide extraction result conflicts")
            attempt_number = 1 + int(
                await session.scalar(
                    select(
                        func.coalesce(func.max(GuideSourceExtractionAttempt.attempt_number), 0)
                    ).where(
                        GuideSourceExtractionAttempt.binding_id == before.binding_id,
                        GuideSourceExtractionAttempt.policy_version == extracted.policy_version,
                    )
                )
                or 0
            )
            attempt = GuideSourceExtractionAttempt(
                id=str(uuid4()),
                binding_id=before.binding_id,
                content_id=before.content_id,
                classification_id=before.classification_id,
                setup_generation=before.setup_generation,
                detected_format=before.detected_format,
                extractor_name=extracted.extractor_name,
                extractor_version=extracted.extractor_version,
                policy_version=extracted.policy_version,
                attempt_number=attempt_number,
                status=extracted.status,
                error_code=extracted.error_code,
                bounded_facts={},
            )
            session.add(attempt)
            await session.flush()
            if extracted.status != "extracted":
                return self._result(attempt)
            if extracted.canonical_output is None or extracted.output_sha256 is None:
                raise GuideExtractionError("guide extraction result conflicts")
            content = await session.scalar(
                select(GuideSourceExtractedContent)
                .where(
                    GuideSourceExtractedContent.content_id == before.content_id,
                    GuideSourceExtractedContent.detected_format == before.detected_format,
                    GuideSourceExtractedContent.extractor_name == extracted.extractor_name,
                    GuideSourceExtractedContent.extractor_version == extracted.extractor_version,
                    GuideSourceExtractedContent.policy_version == extracted.policy_version,
                )
                .with_for_update()
            )
            replayed = content is not None
            if content is None:
                content_id = str(uuid4())
                inserted_id = await session.scalar(
                    insert(GuideSourceExtractedContent)
                    .values(
                        id=content_id,
                        content_id=before.content_id,
                        detected_format=before.detected_format,
                        extractor_name=extracted.extractor_name,
                        extractor_version=extracted.extractor_version,
                        policy_version=extracted.policy_version,
                        source_sha256=before.sha256,
                        source_byte_count=before.byte_count,
                        status="extracted",
                        output_sha256=extracted.output_sha256,
                        canonical_output=extracted.canonical_output,
                        omission_facts=extracted.omission_facts,
                    )
                    .on_conflict_do_nothing(constraint="uq_guide_extracted_contents_identity")
                    .returning(GuideSourceExtractedContent.id)
                )
                replayed = inserted_id is None
                content = await session.scalar(
                    select(GuideSourceExtractedContent)
                    .where(
                        GuideSourceExtractedContent.content_id == before.content_id,
                        GuideSourceExtractedContent.detected_format == before.detected_format,
                        GuideSourceExtractedContent.extractor_name == extracted.extractor_name,
                        GuideSourceExtractedContent.extractor_version
                        == extracted.extractor_version,
                        GuideSourceExtractedContent.policy_version == extracted.policy_version,
                    )
                    .with_for_update()
                )
                if content is None:
                    raise GuideExtractionError("guide extraction result conflicts")
            if (
                content.source_sha256 != before.sha256
                or content.source_byte_count != before.byte_count
                or content.output_sha256 != extracted.output_sha256
                or content.canonical_output != extracted.canonical_output
                or content.omission_facts != extracted.omission_facts
            ):
                raise GuideExtractionError("guide extraction result conflicts")
            usage = await session.scalar(
                select(GuideSourceExtractionUsage)
                .where(
                    GuideSourceExtractionUsage.binding_id == before.binding_id,
                    GuideSourceExtractionUsage.extracted_content_id == content.id,
                )
                .with_for_update()
            )
            if usage is None:
                usage = GuideSourceExtractionUsage(
                    id=str(uuid4()),
                    extracted_content_id=content.id,
                    extraction_attempt_id=attempt.id,
                    attempt_status="extracted",
                    binding_id=before.binding_id,
                    content_id=before.content_id,
                    source_item_id=before.item_id,
                    project_setup_run_id=before.setup_run_id,
                    setup_generation=before.setup_generation,
                )
                session.add(usage)
                await session.flush()
            return self._result(attempt, content=content, usage=usage, replayed=replayed)

    async def claim_materialization_slot(
        self, request: GuideExtractionRequest
    ) -> GuideExtractionPersistenceResult | None:
        """Atomically reserve one of two durable materialization slots."""
        async with self._session_factory() as session, session.begin():
            facts = await self._load_facts(session, request)
            if facts is None:
                raise GuideExtractionError("guide extraction is unavailable")
            policy_version = extraction_policy_version(facts.detected_format)
            successful = (
                await session.execute(
                    select(
                        GuideSourceExtractionAttempt,
                        GuideSourceExtractedContent,
                        GuideSourceExtractionUsage,
                    )
                    .join(
                        GuideSourceExtractionUsage,
                        GuideSourceExtractionUsage.extraction_attempt_id
                        == GuideSourceExtractionAttempt.id,
                    )
                    .join(
                        GuideSourceExtractedContent,
                        GuideSourceExtractedContent.id
                        == GuideSourceExtractionUsage.extracted_content_id,
                    )
                    .where(
                        GuideSourceExtractionUsage.binding_id == facts.binding_id,
                        GuideSourceExtractionAttempt.policy_version == policy_version,
                        GuideSourceExtractedContent.policy_version == policy_version,
                    )
                    .order_by(
                        GuideSourceExtractionAttempt.attempt_number.asc(),
                        GuideSourceExtractionUsage.created_at.asc(),
                        GuideSourceExtractionUsage.id.asc(),
                    )
                    .limit(1)
                )
            ).one_or_none()
            if successful is not None:
                attempt, content, usage = successful
                return self._result(attempt, content=content, usage=usage, replayed=True)
            latest_attempt = await session.scalar(
                select(GuideSourceExtractionAttempt)
                .where(
                    GuideSourceExtractionAttempt.binding_id == facts.binding_id,
                    GuideSourceExtractionAttempt.content_id == facts.content_id,
                    GuideSourceExtractionAttempt.classification_id == facts.classification_id,
                    GuideSourceExtractionAttempt.setup_generation == facts.setup_generation,
                    GuideSourceExtractionAttempt.policy_version == policy_version,
                )
                .order_by(GuideSourceExtractionAttempt.attempt_number.desc())
                .limit(1)
            )
            if latest_attempt is not None and latest_attempt.status not in {
                "parser_failure",
                "cancelled",
            }:
                return self._result(latest_attempt)
            budget = await session.scalar(
                select(GuideSourceExtractionRetryBudget)
                .where(GuideSourceExtractionRetryBudget.binding_id == facts.binding_id)
                .with_for_update()
            )
            if budget is None:
                session.add(
                    GuideSourceExtractionRetryBudget(
                        binding_id=facts.binding_id,
                        content_id=facts.content_id,
                        classification_id=facts.classification_id,
                        setup_generation=facts.setup_generation,
                        policy_version=policy_version,
                        claimed_slots=1,
                    )
                )
                await session.flush()
                return None
            if (
                budget.content_id != facts.content_id
                or budget.classification_id != facts.classification_id
                or budget.setup_generation != facts.setup_generation
            ):
                raise GuideExtractionError("guide extraction is unavailable")
            if budget.policy_version != policy_version:
                budget.policy_version = policy_version
                budget.claimed_slots = 1
                await session.flush()
                return None
            if latest_attempt is None:
                raise GuideExtractionError("guide extraction is unavailable")
            if budget.claimed_slots < 2:
                budget.claimed_slots += 1
                await session.flush()
                return None
            if latest_attempt is not None:
                return self._result(latest_attempt)
            raise GuideExtractionError("guide extraction retry budget is exhausted")

    async def _load_facts(
        self,
        session: AsyncSession,
        request: GuideExtractionRequest,
    ) -> _ExtractionFacts | None:
        latest_generation = (
            select(func.max(ProjectSetupRun.setup_generation))
            .where(ProjectSetupRun.guide_id == str(request.guide_id))
            .scalar_subquery()
        )
        row = (
            await session.execute(
                select(GuideSourceArtifactBinding, GuideSourceFormatClassification, ArtifactContent)
                .join(
                    GuideSourceFormatClassification,
                    GuideSourceFormatClassification.binding_id == GuideSourceArtifactBinding.id,
                )
                .join(ArtifactContent, ArtifactContent.id == GuideSourceArtifactBinding.content_id)
                .join(ProjectGuide, ProjectGuide.id == GuideSourceArtifactBinding.guide_id)
                .join(
                    GuideSourceSnapshot,
                    GuideSourceSnapshot.id == GuideSourceArtifactBinding.source_snapshot_id,
                )
                .join(
                    GuideSourceSnapshotItem,
                    GuideSourceSnapshotItem.id == GuideSourceArtifactBinding.source_item_id,
                )
                .join(
                    ProjectSetupRun,
                    ProjectSetupRun.id == GuideSourceArtifactBinding.project_setup_run_id,
                )
                .where(
                    GuideSourceArtifactBinding.id == str(request.binding_id),
                    GuideSourceArtifactBinding.project_id == str(request.project_id),
                    GuideSourceArtifactBinding.guide_id == str(request.guide_id),
                    GuideSourceArtifactBinding.source_snapshot_id
                    == str(request.source_snapshot_id),
                    GuideSourceArtifactBinding.source_item_id == str(request.source_item_id),
                    GuideSourceArtifactBinding.project_setup_run_id
                    == str(request.project_setup_run_id),
                    GuideSourceArtifactBinding.setup_generation == request.setup_generation,
                    GuideSourceFormatClassification.id == str(request.classification_id),
                    GuideSourceFormatClassification.content_id
                    == GuideSourceArtifactBinding.content_id,
                    GuideSourceFormatClassification.setup_generation
                    == GuideSourceArtifactBinding.setup_generation,
                    ProjectGuide.status == "draft",
                    GuideSourceSnapshot.project_id == GuideSourceArtifactBinding.project_id,
                    GuideSourceSnapshot.guide_id == GuideSourceArtifactBinding.guide_id,
                    GuideSourceSnapshot.guide_version == ProjectGuide.version,
                    GuideSourceSnapshotItem.source_snapshot_id
                    == GuideSourceArtifactBinding.source_snapshot_id,
                    ProjectSetupRun.project_id == GuideSourceArtifactBinding.project_id,
                    ProjectSetupRun.guide_version == ProjectGuide.version,
                    ProjectSetupRun.source_snapshot_hash == GuideSourceSnapshot.bundle_hash,
                    ProjectSetupRun.setup_generation == latest_generation,
                    GuideSourceFormatClassification.sha256 == ArtifactContent.sha256,
                    GuideSourceFormatClassification.byte_count == ArtifactContent.byte_count,
                    GuideSourceFormatClassification.media_type == ArtifactContent.media_type,
                    GuideSourceFormatClassification.detector_name == DETECTOR_NAME,
                    GuideSourceFormatClassification.detector_version == DETECTOR_VERSION,
                )
                .with_for_update(
                    of=(
                        GuideSourceArtifactBinding,
                        ProjectGuide,
                        ProjectSetupRun,
                        ArtifactContent,
                    )
                )
            )
        ).one_or_none()
        if row is None:
            return None
        binding, classification, content = row
        return _ExtractionFacts(
            project_id=binding.project_id,
            guide_id=binding.guide_id,
            snapshot_id=binding.source_snapshot_id,
            item_id=binding.source_item_id,
            setup_run_id=binding.project_setup_run_id,
            setup_generation=binding.setup_generation,
            binding_id=binding.id,
            classification_id=classification.id,
            content_id=content.id,
            sha256=content.sha256,
            byte_count=content.byte_count,
            detected_format=classification.detected_format,
            classification_status=classification.status,
        )

    async def _persist_failure(
        self,
        session: AsyncSession,
        facts: _ExtractionFacts,
        *,
        status: str,
        error_code: str,
    ) -> GuideExtractionPersistenceResult:
        policy_version = extraction_policy_version(facts.detected_format)
        attempt_number = 1 + int(
            await session.scalar(
                select(
                    func.coalesce(func.max(GuideSourceExtractionAttempt.attempt_number), 0)
                ).where(
                    GuideSourceExtractionAttempt.binding_id == facts.binding_id,
                    GuideSourceExtractionAttempt.policy_version == policy_version,
                )
            )
            or 0
        )
        attempt = GuideSourceExtractionAttempt(
            id=str(uuid4()),
            binding_id=facts.binding_id,
            content_id=facts.content_id,
            classification_id=facts.classification_id,
            setup_generation=facts.setup_generation,
            detected_format=facts.detected_format,
            extractor_name=f"workstream.{facts.detected_format}",
            extractor_version="1",
            policy_version=policy_version,
            attempt_number=attempt_number,
            status=status,
            error_code=error_code,
            bounded_facts={},
        )
        session.add(attempt)
        await session.flush()
        return self._result(attempt)

    @staticmethod
    def _result(
        attempt: GuideSourceExtractionAttempt,
        *,
        content: GuideSourceExtractedContent | None = None,
        usage: GuideSourceExtractionUsage | None = None,
        replayed: bool = False,
    ) -> GuideExtractionPersistenceResult:
        return GuideExtractionPersistenceResult(
            attempt_id=UUID(attempt.id),
            status=attempt.status,
            error_code=attempt.error_code,
            extracted_content_id=None if content is None else UUID(content.id),
            usage_id=None if usage is None else UUID(usage.id),
            replayed=replayed,
        )


class GuideExtractionCoordinator:
    """Apply the one permitted fresh-authority/materialization executor retry."""

    def __init__(
        self,
        service: GuideExtractionService,
        materializer: FreshAuthorizedGuideMaterializer,
    ) -> None:
        self._service = service
        self._materializer = materializer

    async def extract(self, request: GuideExtractionRequest) -> GuideExtractionPersistenceResult:
        """Retry one executor failure only after obtaining a completely fresh source."""
        for attempt_index in range(2):
            prepared = await self._materializer.materialize_with_fresh_authority(request)
            try:
                exhausted = await self._service.claim_materialization_slot(request)
                if exhausted is not None:
                    return exhausted
                result = await self._service.extract_prepared(request, prepared)
            finally:
                await prepared.close()
            if result.status != "parser_failure" or attempt_index == 1:
                return result
        raise AssertionError("bounded guide extraction retry exhausted")
