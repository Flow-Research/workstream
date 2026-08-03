"""Hidden verified guide materialization and syntactic classification."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.interfaces.artifact_operations import (
    GuideSourceMaterializationRequest,
    GuideSourceMaterializationResult,
)
from app.interfaces.artifacts import (
    ArtifactInputMismatchError,
    ArtifactObjectMissingError,
    ArtifactStore,
    ArtifactStoreUnavailableError,
)
from app.modules.artifacts.guide_formats import (
    DETECTOR_NAME,
    DETECTOR_VERSION,
    BoundGuideFormatInspector,
    GuideFormatDetector,
)
from app.modules.artifacts.models import (
    ArtifactContent,
    ArtifactPutAttempt,
    ArtifactReplica,
    ArtifactStorageNamespace,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
    GuideSourceArtifactBinding,
    GuideSourceArtifactIncident,
    GuideSourceFormatClassification,
)

if TYPE_CHECKING:
    from app.modules.artifacts.guide_extraction_service import GuideExtractionRequest
from app.modules.artifacts.preparation import (
    ArtifactPreparationDeadlineError,
    ArtifactPreparationService,
)
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    GuideSourceReadAuthorityFacts,
)
from app.modules.artifacts.service import (
    ArtifactStorageNamespaceSpec,
    validate_artifact_replica_execution_namespace,
)
from app.modules.artifacts.sources import PreparedArtifact
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.projects.models import (
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    ProjectGuide,
    ProjectSetupRun,
)


logger = logging.getLogger(__name__)


class GuideSourceMaterializationError(RuntimeError):
    """Concealed guide materialization failure."""


class _GuideReadIncident(RuntimeError):
    """Internal signal used to persist bounded incidents after lock rollback."""

    def __init__(
        self,
        code: str,
        *,
        observed_sha256: str | None = None,
        observed_byte_count: int | None = None,
    ) -> None:
        self.code = code
        self.observed_sha256 = observed_sha256
        self.observed_byte_count = observed_byte_count
        super().__init__(code)


class GuideSourceReadPreparedAuthorization(Protocol):
    """AUTH-04B seam for one transaction-bound fixed-reader capability."""

    async def prepare(
        self,
        *,
        facts: GuideSourceReadAuthorityFacts,
        idempotency_key: UUID,
    ) -> PreparedAuthorizationHandle: ...

    async def consume(
        self,
        *,
        prepared_authorization: PreparedAuthorizationHandle,
        facts: GuideSourceReadAuthorityFacts,
    ) -> None: ...


class GuideSourceReadAuthorityFactory(Protocol):
    """Create one transaction-local prepared reader adapter."""

    def __call__(self, session: AsyncSession) -> GuideSourceReadPreparedAuthorization: ...


class DenyGuideSourceReadPreparedAuthorization:
    """Production default until AUTH-04B activates exact guide reads."""

    async def prepare(
        self,
        *,
        facts: GuideSourceReadAuthorityFacts,
        idempotency_key: UUID,
    ) -> PreparedAuthorizationHandle:
        del facts, idempotency_key
        raise ArtifactAuthorityDeniedError("guide source read is unavailable")

    async def consume(
        self,
        *,
        prepared_authorization: PreparedAuthorizationHandle,
        facts: GuideSourceReadAuthorityFacts,
    ) -> None:
        del prepared_authorization, facts
        raise ArtifactAuthorityDeniedError("guide source read is unavailable")


def _deny_reader(_: AsyncSession) -> GuideSourceReadPreparedAuthorization:
    return DenyGuideSourceReadPreparedAuthorization()


@dataclass(frozen=True, slots=True)
class _ReadFacts:
    binding_id: str
    project_id: str
    guide_id: str
    snapshot_id: str
    item_id: str
    setup_run_id: str
    setup_generation: int
    content_id: str
    replica_id: str
    storage_namespace_id: str
    namespace_fingerprint: str
    sha256: str
    byte_count: int
    media_type: str
    declared_media_type: str
    ingestion_adapter: str
    provider_object_ref: str
    receipt_id: str
    verification_generation: int


class ArtifactMaterializationService:
    """Canonical hidden materializer, beginning with exact guide-source reads."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        store: ArtifactStore,
        preparation: ArtifactPreparationService,
        detector: GuideFormatDetector,
        namespace: ArtifactStorageNamespaceSpec,
        authority_factory: GuideSourceReadAuthorityFactory = _deny_reader,
    ) -> None:
        self._session_factory = session_factory
        self._store = store
        self._preparation = preparation
        self._detector = detector
        self._namespace = namespace
        self._authority_factory = authority_factory

    async def materialize_guide_source(
        self,
        request: GuideSourceMaterializationRequest,
    ) -> GuideSourceMaterializationResult:
        """Authorize, read, verify, classify, revalidate, and persist one result."""
        if request.setup_generation <= 0:
            raise GuideSourceMaterializationError("guide source read is unavailable")
        before: _ReadFacts | None = None
        prepared = None
        try:
            async with self._session_factory() as session, session.begin():
                before = await self._load_read_facts(session, request)
                if before is None:
                    raise GuideSourceMaterializationError("guide source read is unavailable")
                prepared = await self._authorize_and_prepare(session, request, before)
                try:
                    detected = await prepared.inspect(
                        BoundGuideFormatInspector(
                            detector=self._detector,
                            declared_media_type=before.declared_media_type,
                            ingestion_adapter=before.ingestion_adapter,
                        )
                    )
                except ArtifactPreparationDeadlineError as exc:
                    raise _GuideReadIncident("unavailable") from exc
                existing = await session.scalar(
                    select(GuideSourceFormatClassification)
                    .where(GuideSourceFormatClassification.binding_id == before.binding_id)
                    .with_for_update()
                )
                if existing is not None:
                    if (
                        existing.content_id != before.content_id
                        or existing.verified_replica_id != before.replica_id
                        or existing.setup_generation != before.setup_generation
                        or existing.sha256 != before.sha256
                        or existing.byte_count != before.byte_count
                        or existing.media_type != before.media_type
                        or existing.detected_format != detected.detected_format
                        or existing.status != detected.status
                        or existing.classification_facts != detected.facts
                        or existing.detector_name != DETECTOR_NAME
                        or existing.detector_version != DETECTOR_VERSION
                    ):
                        raise GuideSourceMaterializationError("guide classification conflicts")
                    return self._result(existing, replayed=True)
                classification = GuideSourceFormatClassification(
                    id=str(uuid4()),
                    binding_id=before.binding_id,
                    content_id=before.content_id,
                    verified_replica_id=before.replica_id,
                    setup_generation=before.setup_generation,
                    sha256=before.sha256,
                    byte_count=before.byte_count,
                    media_type=before.media_type,
                    detected_format=detected.detected_format,
                    status=detected.status,
                    detector_name=DETECTOR_NAME,
                    detector_version=DETECTOR_VERSION,
                    classification_facts=detected.facts,
                )
                session.add(classification)
                await session.flush()
                return self._result(classification, replayed=False)
        except _GuideReadIncident as incident:
            if before is not None:
                try:
                    await self._record_incident(
                        before,
                        incident.code,
                        observed_sha256=incident.observed_sha256,
                        observed_byte_count=incident.observed_byte_count,
                    )
                except SQLAlchemyError:
                    logger.exception("guide source incident could not be recorded")
            raise GuideSourceMaterializationError("guide artifact incident") from None
        finally:
            if prepared is not None:
                await prepared.close()

    async def prepare_authorized_guide_source(
        self,
        request: GuideSourceMaterializationRequest,
    ) -> PreparedArtifact:
        """Return one freshly authorized, fully verified scratch artifact."""
        if request.setup_generation <= 0:
            raise GuideSourceMaterializationError("guide source read is unavailable")
        before: _ReadFacts | None = None
        prepared: PreparedArtifact | None = None
        try:
            async with self._session_factory() as session, session.begin():
                before = await self._load_read_facts(session, request)
                if before is None:
                    raise GuideSourceMaterializationError("guide source read is unavailable")
                prepared = await self._authorize_and_prepare(session, request, before)
                after = await self._load_read_facts(session, request)
                if after != before:
                    raise GuideSourceMaterializationError("guide source read is unavailable")
            result = prepared
            prepared = None
            return result
        except _GuideReadIncident as incident:
            if before is not None:
                try:
                    await self._record_incident(
                        before,
                        incident.code,
                        observed_sha256=incident.observed_sha256,
                        observed_byte_count=incident.observed_byte_count,
                    )
                except SQLAlchemyError:
                    logger.exception("guide source incident could not be recorded")
            raise GuideSourceMaterializationError("guide artifact incident") from None
        finally:
            if prepared is not None:
                await prepared.close()

    async def _authorize_and_prepare(
        self,
        session: AsyncSession,
        request: GuideSourceMaterializationRequest,
        before: _ReadFacts,
    ) -> PreparedArtifact:
        """Consume exact read authority and verify one provider stream in scratch."""
        facts = self._authority_facts(before)
        authority = self._authority_factory(session)
        handle = await authority.prepare(
            facts=facts,
            idempotency_key=request.idempotency_key,
        )
        await authority.consume(prepared_authorization=handle, facts=facts)
        try:
            prepared = await self._preparation.prepare(
                self._store.open(before.provider_object_ref),
                media_type=before.media_type,
            )
        except ArtifactObjectMissingError as exc:
            raise _GuideReadIncident("missing") from exc
        except ArtifactInputMismatchError as exc:
            raise _GuideReadIncident("changed") from exc
        except (ArtifactStoreUnavailableError, ArtifactPreparationDeadlineError) as exc:
            raise _GuideReadIncident("unavailable") from exc
        commitment = prepared.commitment
        if commitment.sha256 != before.sha256 or commitment.byte_count != before.byte_count:
            await prepared.close()
            code = "truncated" if commitment.byte_count < before.byte_count else "changed"
            raise _GuideReadIncident(
                code,
                observed_sha256=commitment.sha256,
                observed_byte_count=commitment.byte_count,
            )
        return prepared

    async def _load_read_facts(
        self,
        session: AsyncSession,
        request: GuideSourceMaterializationRequest,
    ) -> _ReadFacts | None:
        latest_generation = (
            select(func.max(ProjectSetupRun.setup_generation))
            .where(ProjectSetupRun.guide_id == str(request.guide_id))
            .scalar_subquery()
        )
        row = (
            await session.execute(
                select(
                    GuideSourceArtifactBinding,
                    ArtifactContent,
                    ArtifactReplica,
                    ArtifactVerificationJob,
                    ArtifactVerificationReceipt,
                    GuideSourceSnapshotItem,
                    ArtifactStorageNamespace,
                )
                .join(ArtifactContent, ArtifactContent.id == GuideSourceArtifactBinding.content_id)
                .join(
                    ArtifactReplica,
                    ArtifactReplica.id == GuideSourceArtifactBinding.verified_replica_id,
                )
                .join(
                    ArtifactStorageNamespace,
                    ArtifactStorageNamespace.id == ArtifactReplica.storage_namespace_id,
                )
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
                .join(ArtifactPutAttempt, ArtifactPutAttempt.replica_id == ArtifactReplica.id)
                .join(
                    ArtifactVerificationJob,
                    ArtifactVerificationJob.originating_put_attempt_id == ArtifactPutAttempt.id,
                )
                .join(
                    ArtifactVerificationReceipt,
                    ArtifactVerificationReceipt.verification_job_id == ArtifactVerificationJob.id,
                )
                .where(
                    GuideSourceArtifactBinding.id == str(request.binding_id),
                    GuideSourceArtifactBinding.project_id == str(request.project_id),
                    GuideSourceArtifactBinding.guide_id == str(request.guide_id),
                    GuideSourceArtifactBinding.source_snapshot_id
                    == str(request.guide_source_snapshot_id),
                    GuideSourceArtifactBinding.source_item_id == str(request.source_item_id),
                    GuideSourceArtifactBinding.project_setup_run_id
                    == str(request.project_setup_run_id),
                    GuideSourceArtifactBinding.setup_generation == request.setup_generation,
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
                    ArtifactContent.media_type.is_not(None),
                    ArtifactReplica.verification_state == "verified",
                    ArtifactReplica.availability_state == "available",
                    ArtifactReplica.integrity_state == "valid",
                    ArtifactVerificationJob.status == "verified",
                    ArtifactVerificationJob.replica_id == ArtifactReplica.id,
                    ArtifactVerificationJob.terminal_result_code == "verified",
                    ArtifactVerificationJob.terminal_at.is_not(None),
                    ArtifactVerificationReceipt.execution_generation
                    == ArtifactVerificationJob.execution_generation,
                    ArtifactVerificationReceipt.outcome == "verified",
                    ArtifactVerificationReceipt.observed_sha256 == ArtifactContent.sha256,
                    ArtifactVerificationReceipt.observed_byte_count == ArtifactContent.byte_count,
                    ArtifactPutAttempt.guide_source_item_id
                    == GuideSourceArtifactBinding.source_item_id,
                    ArtifactPutAttempt.sha256 == ArtifactContent.sha256,
                    ArtifactPutAttempt.byte_count == ArtifactContent.byte_count,
                    ArtifactPutAttempt.storage_namespace_id == ArtifactReplica.storage_namespace_id,
                    ArtifactPutAttempt.namespace_fingerprint
                    == ArtifactReplica.namespace_fingerprint,
                    ArtifactPutAttempt.status == "object_confirmed",
                    ArtifactPutAttempt.terminal_result_code == "object_confirmed",
                )
                .order_by(ArtifactVerificationReceipt.created_at.desc())
                .limit(1)
                .with_for_update(
                    of=(
                        ProjectGuide,
                        GuideSourceSnapshot,
                        GuideSourceSnapshotItem,
                        ProjectSetupRun,
                        GuideSourceArtifactBinding,
                        ArtifactContent,
                        ArtifactReplica,
                        ArtifactVerificationJob,
                        ArtifactVerificationReceipt,
                    )
                )
            )
        ).one_or_none()
        if row is None:
            return None
        binding, content, replica, job, receipt, item, persisted_namespace = row
        validate_artifact_replica_execution_namespace(
            replica=replica,
            persisted=persisted_namespace,
            namespace=self._namespace,
            store=self._store,
        )
        return _ReadFacts(
            binding_id=binding.id,
            project_id=binding.project_id,
            guide_id=binding.guide_id,
            snapshot_id=binding.source_snapshot_id,
            item_id=binding.source_item_id,
            setup_run_id=binding.project_setup_run_id,
            setup_generation=binding.setup_generation,
            content_id=content.id,
            replica_id=replica.id,
            storage_namespace_id=replica.storage_namespace_id,
            namespace_fingerprint=replica.namespace_fingerprint,
            sha256=content.sha256,
            byte_count=content.byte_count,
            media_type=content.media_type,
            declared_media_type=item.media_type or content.media_type,
            ingestion_adapter=item.ingestion_adapter,
            provider_object_ref=replica.provider_object_ref,
            receipt_id=receipt.id,
            verification_generation=job.execution_generation,
        )

    @staticmethod
    def _authority_facts(facts: _ReadFacts) -> GuideSourceReadAuthorityFacts:
        return GuideSourceReadAuthorityFacts(
            project_id=UUID(facts.project_id),
            guide_id=UUID(facts.guide_id),
            guide_source_snapshot_id=UUID(facts.snapshot_id),
            guide_source_item_id=UUID(facts.item_id),
            project_setup_run_id=UUID(facts.setup_run_id),
            setup_generation=facts.setup_generation,
            binding_id=UUID(facts.binding_id),
            content_id=UUID(facts.content_id),
            verified_replica_id=UUID(facts.replica_id),
            storage_namespace_id=facts.storage_namespace_id,
            namespace_fingerprint=facts.namespace_fingerprint,
            verification_receipt_id=UUID(facts.receipt_id),
            verification_generation=facts.verification_generation,
            sha256=facts.sha256,
            byte_count=facts.byte_count,
            media_type=facts.media_type,
        )

    async def _record_incident(
        self,
        facts: _ReadFacts,
        code: str,
        *,
        observed_sha256: str | None = None,
        observed_byte_count: int | None = None,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            await self._add_incident(
                session,
                facts,
                code,
                observed_sha256=observed_sha256,
                observed_byte_count=observed_byte_count,
            )

    @staticmethod
    async def _add_incident(
        session: AsyncSession,
        facts: _ReadFacts,
        code: str,
        *,
        observed_sha256: str | None = None,
        observed_byte_count: int | None = None,
    ) -> None:
        session.add(
            GuideSourceArtifactIncident(
                id=str(uuid4()),
                binding_id=facts.binding_id,
                content_id=facts.content_id,
                verified_replica_id=facts.replica_id,
                setup_generation=facts.setup_generation,
                code=code,
                observed_sha256=observed_sha256,
                observed_byte_count=observed_byte_count,
                bounded_facts={"verification_generation": facts.verification_generation},
            )
        )
        await session.flush()

    @staticmethod
    def _result(
        classification: GuideSourceFormatClassification,
        *,
        replayed: bool,
    ) -> GuideSourceMaterializationResult:
        return GuideSourceMaterializationResult(
            classification_id=UUID(classification.id),
            binding_id=UUID(classification.binding_id),
            content_id=UUID(classification.content_id),
            setup_generation=classification.setup_generation,
            detected_format=classification.detected_format,
            status=classification.status,
            replayed=replayed,
        )


class AuthorizedGuideExtractionMaterializer:
    """Adapt the canonical guide reader to extraction's fresh-source contract."""

    def __init__(self, materialization: ArtifactMaterializationService) -> None:
        self._materialization = materialization

    async def materialize_with_fresh_authority(
        self, request: GuideExtractionRequest
    ) -> PreparedArtifact:
        """Obtain a new AUTH-04B decision and independently read exact bytes."""
        return await self._materialization.prepare_authorized_guide_source(
            GuideSourceMaterializationRequest(
                idempotency_key=uuid4(),
                project_id=request.project_id,
                guide_id=request.guide_id,
                guide_source_snapshot_id=request.source_snapshot_id,
                source_item_id=request.source_item_id,
                project_setup_run_id=request.project_setup_run_id,
                setup_generation=request.setup_generation,
                binding_id=request.binding_id,
            )
        )
