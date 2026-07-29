"""PostgreSQL proof for exact hidden guide-source binding."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.hashing import canonical_json_hash
from app.interfaces.artifact_operations import (
    GuideSourceBindingRequest,
    GuideSourceMaterializationRequest,
)
from app.interfaces.artifacts import ArtifactObjectMissingError, ArtifactStoreUnavailableError
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.artifacts.guide_bindings import (
    GuideSourceBindingError,
    GuideSourceBindingService,
)
from app.modules.artifacts.guide_formats import GuideFormatDetector, GuideFormatLimits
from app.modules.artifacts.guide_extraction import GuideExtractionRegistry
from app.modules.artifacts.guide_extraction_service import (
    GuideExtractionRequest,
    GuideExtractionService,
)
from app.modules.artifacts.guide_materialization import (
    ArtifactMaterializationService,
    GuideSourceMaterializationError,
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
    GuideSourceExtractedContent,
    GuideSourceExtractionAttempt,
    GuideSourceExtractionRetryBudget,
    GuideSourceExtractionUsage,
)
from app.modules.artifacts.preparation import (
    HARD_MAXIMUM_ARTIFACT_BYTES,
    ArtifactPreparationDeadlineError,
    ArtifactPreparationLimits,
    ArtifactPreparationService,
    ArtifactScratchManager,
)
from app.modules.artifacts.service import (
    ArtifactStorageNamespaceError,
    ArtifactStorageNamespaceSpec,
)
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    GuideSourceBindingAuthorityFacts,
    GuideSourceReadAuthorityFacts,
)
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.projects.models import (
    GuideSourceArtifactIngest,
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    Project,
    ProjectGuide,
    ProjectSetupRun,
)


class _AllowBindingAuthority:
    """Test-only fixed authority; production composition cannot import it."""

    def __init__(self, *, deny: bool = False) -> None:
        self.handle = object.__new__(PreparedAuthorizationHandle)
        self.deny = deny
        self.facts: list[GuideSourceBindingAuthorityFacts] = []

    async def consume(self, **values: Any) -> None:
        assert values["prepared_authorization"] is self.handle
        self.facts.append(values["facts"])
        if self.deny:
            raise ArtifactAuthorityDeniedError("binding denied")


class _AllowReadAuthority:
    """Test-only fixed guide reader authority."""

    def __init__(self, *, handle: PreparedAuthorizationHandle | None = None) -> None:
        self.handle = handle or object.__new__(PreparedAuthorizationHandle)
        self.facts: list[GuideSourceReadAuthorityFacts] = []

    async def consume(self, **values: Any) -> None:
        assert values["prepared_authorization"] is self.handle
        self.facts.append(values["facts"])


class _ReadStore:
    """Provider-neutral test read probe."""

    def __init__(self, payload: bytes, *, after_read=None) -> None:
        self.payload = payload
        self.after_read = after_read
        self.open_count = 0
        self.identity = SimpleNamespace(provider_key="local")

    async def open(self, provider_object_ref: str) -> AsyncIterator[bytes]:
        assert provider_object_ref.startswith("objects/")
        self.open_count += 1
        yield self.payload
        if self.after_read is not None:
            await self.after_read()


class _FailingReadStore:
    """Raise one sanitized provider failure only when the read begins."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.open_count = 0
        self.identity = SimpleNamespace(provider_key="local")

    async def open(self, provider_object_ref: str) -> AsyncIterator[bytes]:
        del provider_object_ref
        self.open_count += 1
        raise self.error
        yield b""  # pragma: no cover - retain the async-iterator contract


class _BlockingReadStore(_ReadStore):
    """Hold one provider read until the calling task is cancelled."""

    def __init__(self, payload: bytes) -> None:
        super().__init__(payload)
        self.started = asyncio.Event()

    async def open(self, provider_object_ref: str) -> AsyncIterator[bytes]:
        assert provider_object_ref.startswith("objects/")
        self.open_count += 1
        self.started.set()
        await asyncio.Event().wait()
        yield self.payload


async def _byte_stream(payload: bytes) -> AsyncIterator[bytes]:
    yield payload


def _preparation(
    tmp_path: Path, **limit_changes: Any
) -> tuple[ArtifactPreparationService, ArtifactScratchManager]:
    limit_values = {
        "aggregate_reserved_bytes": 2 * HARD_MAXIMUM_ARTIFACT_BYTES,
        "maximum_files": 2,
        "maximum_concurrency": 2,
        "minimum_free_bytes": 0,
        "reservation_ttl_seconds": 30,
        "total_deadline_seconds": 10,
        "cleanup_margin_seconds": 5,
        "stream_buffer_bytes": 1024,
        "maximum_source_bytes": 1024 * 1024,
    }
    limit_values.update(limit_changes)
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(**limit_values),
    )
    return ArtifactPreparationService(manager), manager


def _namespace() -> ArtifactStorageNamespaceSpec:
    return ArtifactStorageNamespaceSpec(
        backend="local",
        adapter="local",
        provider_profile="test",
        namespace_descriptor={"root": "test"},
        namespace_fingerprint="sha256:" + "b" * 64,
    )


async def _seed_binding_lineage(
    session,
    *,
    verified: bool = True,
    verification_receipt: bool = True,
    sha256: str | None = None,
    byte_count: int = 42,
    media_type: str = "application/pdf",
) -> dict[str, UUID]:
    ids = {
        name: uuid4()
        for name in (
            "actor",
            "project",
            "guide",
            "snapshot",
            "item",
            "run",
            "content",
            "replica",
            "attempt",
            "job",
        )
    }
    digest = sha256 or "sha256:" + "a" * 64
    namespace_fingerprint = "sha256:" + "b" * 64
    session.add(
        ActorProfile(
            id=str(ids["actor"]),
            actor_kind="human",
            status="active",
            provisioning_method="automatic_first_access",
            created_by="test",
        )
    )
    await session.flush()
    session.add(
        ActorIdentityLink(
            id=str(uuid4()),
            actor_profile_id=str(ids["actor"]),
            issuer="https://issuer.example.test",
            subject=f"human-{ids['actor']}",
            subject_kind="human",
            status="active",
            linked_by="test",
            last_verified_at=datetime.now(UTC),
        )
    )
    session.add(
        Project(
            id=str(ids["project"]),
            name="Guide binding",
            slug=f"guide-binding-{ids['project']}",
            status="draft",
        )
    )
    await session.flush()
    session.add(
        ProjectGuide(
            id=str(ids["guide"]),
            project_id=str(ids["project"]),
            version="v1",
            status="draft",
            content_markdown="# Guide",
            created_by="test",
        )
    )
    await session.flush()
    snapshot_hash = canonical_json_hash({"item": str(ids["item"])})
    session.add(
        GuideSourceSnapshot(
            id=str(ids["snapshot"]),
            project_id=str(ids["project"]),
            guide_id=str(ids["guide"]),
            guide_version="v1",
            manifest_schema_version="v1",
            manifest_json={"item": str(ids["item"])},
            bundle_hash=snapshot_hash,
            captured_by=str(ids["actor"]),
        )
    )
    await session.flush()
    session.add(
        GuideSourceSnapshotItem(
            id=str(ids["item"]),
            source_snapshot_id=str(ids["snapshot"]),
            item_order=0,
            source_kind="file",
            durable_ref="guide.pdf",
            ingestion_adapter="pdf",
            content_hash="caller-metadata-is-not-authority",
            media_type=media_type,
        )
    )
    session.add(
        ProjectSetupRun(
            id=str(ids["run"]),
            project_id=str(ids["project"]),
            guide_id=str(ids["guide"]),
            guide_version="v1",
            source_snapshot_id=str(ids["snapshot"]),
            source_snapshot_hash=snapshot_hash,
            setup_generation=1,
            status="queued",
            current_step="queued",
            created_by="test",
        )
    )
    await session.flush()
    session.add(
        GuideSourceArtifactIngest(
            id=str(uuid4()),
            source_item_id=str(ids["item"]),
            actor_profile_id=str(ids["actor"]),
            sha256=digest,
            byte_count=byte_count,
            media_type=media_type,
        )
    )
    session.add(
        ArtifactStorageNamespace(
            id="primary",
            backend="local",
            adapter="local",
            provider_profile="test",
            namespace_descriptor={"root": "test"},
            namespace_fingerprint=namespace_fingerprint,
        )
    )
    session.add(
        ArtifactContent(
            id=str(ids["content"]),
            sha256=digest,
            byte_count=byte_count,
            media_type=media_type,
        )
    )
    await session.flush()
    session.add(
        ArtifactReplica(
            id=str(ids["replica"]),
            content_id=str(ids["content"]),
            storage_namespace_id="primary",
            namespace_fingerprint=namespace_fingerprint,
            adapter="local",
            provider_profile="test",
            provider_object_ref=f"objects/{ids['content']}",
            verification_state="verified" if verified else "pending",
            availability_state="available" if verified else "unknown",
            integrity_state="valid" if verified else "unknown",
        )
    )
    await session.flush()
    session.add(
        ArtifactPutAttempt(
            id=str(ids["attempt"]),
            producer_request_type="guide",
            producer_type="actor_profile",
            producer_ref=str(ids["actor"]),
            project_id=str(ids["project"]),
            guide_source_item_id=str(ids["item"]),
            sha256=digest,
            byte_count=byte_count,
            media_type=media_type,
            storage_namespace_id="primary",
            namespace_fingerprint=namespace_fingerprint,
            canonical_target="sha256/aa/" + "a" * 62,
            operation_identity="sha256:" + "c" * 64,
            request_digest="sha256:" + "d" * 64,
            status="object_confirmed",
            replica_id=str(ids["replica"]),
            terminal_result_code="object_confirmed",
            terminal_at=datetime.now(UTC),
        )
    )
    await session.flush()
    session.add(
        ArtifactVerificationJob(
            id=str(ids["job"]),
            originating_put_attempt_id=str(ids["attempt"]),
            replica_id=str(ids["replica"]),
            status="verified" if verified else "pending",
            attempt_count=1 if verified else 0,
            maximum_attempts=3,
            terminal_result_code="verified" if verified else None,
            terminal_at=datetime.now(UTC) if verified else None,
        )
    )
    if verified and verification_receipt:
        session.add(
            ArtifactVerificationReceipt(
                id=str(uuid4()),
                verification_job_id=str(ids["job"]),
                execution_generation=0,
                outcome="verified",
                observed_sha256=digest,
                observed_byte_count=byte_count,
            )
        )
    await session.commit()
    return ids


def _request(ids: dict[str, UUID], authority: _AllowBindingAuthority, **changes: Any):
    values = {
        "prepared_authorization": authority.handle,
        "project_id": ids["project"],
        "guide_id": ids["guide"],
        "guide_source_snapshot_id": ids["snapshot"],
        "source_item_id": ids["item"],
        "project_setup_run_id": ids["run"],
        "setup_generation": 1,
        "logical_role": "guide_source_original",
        "verified_content_id": ids["content"],
    }
    values.update(changes)
    return GuideSourceBindingRequest(**values)


def _materialization_request(
    ids: dict[str, UUID],
    *,
    binding_id: UUID,
    authority: _AllowReadAuthority,
    **changes: Any,
) -> GuideSourceMaterializationRequest:
    values = {
        "prepared_authorization": authority.handle,
        "project_id": ids["project"],
        "guide_id": ids["guide"],
        "guide_source_snapshot_id": ids["snapshot"],
        "source_item_id": ids["item"],
        "project_setup_run_id": ids["run"],
        "setup_generation": 1,
        "binding_id": binding_id,
    }
    values.update(changes)
    return GuideSourceMaterializationRequest(**values)


async def _create_binding(factory, ids: dict[str, UUID]) -> UUID:
    authority = _AllowBindingAuthority()
    async with factory() as session, session.begin():
        result = await GuideSourceBindingService(session, authority).bind_guide_source(
            _request(ids, authority)
        )
    return result.binding_id


@pytest.mark.asyncio
@pytest.mark.postgres_schema_contract
async def test_extraction_publishes_deterministic_content_and_exact_usage(
    isolated_database_env: str, tmp_path: Path, migration_lock
) -> None:
    payload = b'{"z":2,"a":1}'
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    preparation, manager = _preparation(tmp_path)
    prepared = None
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(
                session,
                sha256=digest,
                byte_count=len(payload),
                media_type="application/json",
            )
        binding_id = await _create_binding(factory, ids)
        classification_id = uuid4()
        async with factory() as session, session.begin():
            session.add(
                GuideSourceFormatClassification(
                    id=str(classification_id),
                    binding_id=str(binding_id),
                    content_id=str(ids["content"]),
                    verified_replica_id=str(ids["replica"]),
                    setup_generation=1,
                    sha256=digest,
                    byte_count=len(payload),
                    media_type="application/json",
                    detected_format="json",
                    status="classified",
                    detector_name="workstream.guide_format",
                    detector_version="1",
                    classification_facts={},
                )
            )
        prepared = await preparation.prepare(_byte_stream(payload), media_type="application/json")
        request = GuideExtractionRequest(
            project_id=ids["project"],
            guide_id=ids["guide"],
            source_snapshot_id=ids["snapshot"],
            source_item_id=ids["item"],
            project_setup_run_id=ids["run"],
            setup_generation=1,
            binding_id=binding_id,
            classification_id=classification_id,
        )
        result = await GuideExtractionService(factory, GuideExtractionRegistry()).extract_prepared(
            request, prepared
        )
        assert result.status == "extracted"
        assert result.extracted_content_id is not None
        assert result.usage_id is not None
        async with factory() as session:
            content = await session.get(
                GuideSourceExtractedContent, str(result.extracted_content_id)
            )
            assert content is not None
            assert content.canonical_output == '{"a":1,"z":2}'
            assert await session.scalar(select(func.count(GuideSourceExtractionAttempt.id))) == 1
            assert await session.scalar(select(func.count(GuideSourceExtractionUsage.id))) == 1
        async with factory() as session:
            with pytest.raises(IntegrityError):
                async with session.begin():
                    await session.execute(
                        text(
                            "update guide_source_extraction_usages "
                            "set attempt_status = 'parser_failure' where id = :usage_id"
                        ),
                        {"usage_id": str(result.usage_id)},
                    )
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.set_main_option(
            "script_location", str(Path(__file__).resolve().parents[1] / "alembic")
        )
        with migration_lock(), pytest.raises(
            RuntimeError, match="cannot downgrade populated guide extraction evidence"
        ):
            command.downgrade(config, "0040_guide_materialization")
    finally:
        if prepared is not None:
            await prepared.close()
        manager.close()
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "retry_allowed"),
    [
        ("malformed", False),
        ("limit_exceeded", False),
        ("unsupported", False),
        ("parser_failure", True),
        ("cancelled", True),
    ],
)
async def test_retry_budget_replays_terminal_outcomes_and_only_claims_transient_slot(
    isolated_database_env: str, status: str, retry_allowed: bool
) -> None:
    payload = b"guide"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(
                session,
                sha256=digest,
                byte_count=len(payload),
                media_type="text/plain",
            )
        binding_id = await _create_binding(factory, ids)
        classification_id = uuid4()
        attempt_id = uuid4()
        async with factory() as session, session.begin():
            session.add_all(
                [
                    GuideSourceFormatClassification(
                        id=str(classification_id),
                        binding_id=str(binding_id),
                        content_id=str(ids["content"]),
                        verified_replica_id=str(ids["replica"]),
                        setup_generation=1,
                        sha256=digest,
                        byte_count=len(payload),
                        media_type="text/plain",
                        detected_format="plain_text",
                        status="classified",
                        detector_name="workstream.guide_format",
                        detector_version="1",
                        classification_facts={},
                    ),
                    GuideSourceExtractionRetryBudget(
                        binding_id=str(binding_id),
                        content_id=str(ids["content"]),
                        classification_id=str(classification_id),
                        setup_generation=1,
                        policy_version="guide-extraction-v1",
                        claimed_slots=1,
                    ),
                    GuideSourceExtractionAttempt(
                        id=str(attempt_id),
                        binding_id=str(binding_id),
                        content_id=str(ids["content"]),
                        classification_id=str(classification_id),
                        setup_generation=1,
                        detected_format="plain_text",
                        extractor_name="workstream.plain_text",
                        extractor_version="1",
                        policy_version="guide-extraction-v1",
                        attempt_number=1,
                        status=status,
                        error_code="test_failure",
                        bounded_facts={},
                    ),
                ]
            )
        request = GuideExtractionRequest(
            project_id=ids["project"],
            guide_id=ids["guide"],
            source_snapshot_id=ids["snapshot"],
            source_item_id=ids["item"],
            project_setup_run_id=ids["run"],
            setup_generation=1,
            binding_id=binding_id,
            classification_id=classification_id,
        )
        result = await GuideExtractionService(
            factory, GuideExtractionRegistry()
        ).claim_materialization_slot(request)
        async with factory() as session:
            budget = await session.get(GuideSourceExtractionRetryBudget, str(binding_id))
            assert budget is not None
            assert budget.claimed_slots == (2 if retry_allowed else 1)
        if retry_allowed:
            assert result is None
        else:
            assert result is not None
            assert result.attempt_id == attempt_id
            assert result.status == status
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_materialization_denies_before_provider_read(
    isolated_database_env: str, tmp_path: Path
) -> None:
    payload = b"%PDF-1.7\nverified"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    preparation, scratch = _preparation(tmp_path)
    store = _ReadStore(payload)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(
                session, sha256=digest, byte_count=len(payload), media_type="application/pdf"
            )
        binding_id = await _create_binding(factory, ids)
        authority = _AllowReadAuthority()
        service = ArtifactMaterializationService(
            factory,
            store,  # type: ignore[arg-type]
            preparation,
            GuideFormatDetector(GuideFormatLimits()),
            _namespace(),
        )

        with pytest.raises(ArtifactAuthorityDeniedError, match="unavailable"):
            await service.materialize_guide_source(
                _materialization_request(ids, binding_id=binding_id, authority=authority)
            )

        assert store.open_count == 0
        async with factory() as session:
            assert await session.scalar(select(func.count(GuideSourceFormatClassification.id))) == 0
    finally:
        scratch.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_materialization_verifies_classifies_replays_and_cleans_scratch(
    isolated_database_env: str, tmp_path: Path
) -> None:
    payload = b"%PDF-1.7\nverified"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    preparation, scratch = _preparation(tmp_path)
    store = _ReadStore(payload)
    authority = _AllowReadAuthority()
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(
                session, sha256=digest, byte_count=len(payload), media_type="application/pdf"
            )
        binding_id = await _create_binding(factory, ids)
        service = ArtifactMaterializationService(
            factory,
            store,  # type: ignore[arg-type]
            preparation,
            GuideFormatDetector(GuideFormatLimits()),
            _namespace(),
            authority_factory=lambda _: authority,
        )
        request = _materialization_request(ids, binding_id=binding_id, authority=authority)

        first = await service.materialize_guide_source(request)
        replay = await service.materialize_guide_source(request)

        assert (first.detected_format, first.status, first.replayed) == (
            "pdf",
            "classified",
            False,
        )
        assert replay.classification_id == first.classification_id
        assert replay.replayed
        assert store.open_count == 2
        assert authority.facts[0].namespace_fingerprint == "sha256:" + "b" * 64
        assert authority.facts[0].verification_generation == 0
        assert (await scratch.usage()).reservation_count == 0
        assert list((tmp_path / "scratch" / "files").iterdir()) == []
        async with factory() as session:
            assert await session.scalar(select(func.count(GuideSourceFormatClassification.id))) == 1
    finally:
        scratch.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_materialization_rejects_conflicting_immutable_classification(
    isolated_database_env: str, tmp_path: Path
) -> None:
    payload = b"%PDF-1.7\nverified"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    preparation, scratch = _preparation(tmp_path)
    store = _ReadStore(payload)
    authority = _AllowReadAuthority()
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(
                session, sha256=digest, byte_count=len(payload), media_type="application/pdf"
            )
        binding_id = await _create_binding(factory, ids)
        service = ArtifactMaterializationService(
            factory,
            store,  # type: ignore[arg-type]
            preparation,
            GuideFormatDetector(GuideFormatLimits()),
            _namespace(),
            authority_factory=lambda _: authority,
        )
        request = _materialization_request(ids, binding_id=binding_id, authority=authority)
        first = await service.materialize_guide_source(request)
        async with factory() as session, session.begin():
            persisted = await session.get(
                GuideSourceFormatClassification, str(first.classification_id)
            )
            assert persisted is not None
            persisted.detected_format = "plain_text"

        with pytest.raises(GuideSourceMaterializationError, match="classification conflicts"):
            await service.materialize_guide_source(request)

        async with factory() as session:
            persisted = await session.get(
                GuideSourceFormatClassification, str(first.classification_id)
            )
            assert persisted is not None
            assert persisted.detected_format == "plain_text"
            assert await session.scalar(select(func.count(GuideSourceFormatClassification.id))) == 1
    finally:
        scratch.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_truncated_materialization_records_incident_without_classification(
    isolated_database_env: str, tmp_path: Path
) -> None:
    expected = b"%PDF-1.7\ncomplete"
    digest = "sha256:" + hashlib.sha256(expected).hexdigest()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    preparation, scratch = _preparation(tmp_path)
    store = _ReadStore(expected[:-4])
    authority = _AllowReadAuthority()
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(
                session, sha256=digest, byte_count=len(expected), media_type="application/pdf"
            )
        binding_id = await _create_binding(factory, ids)
        service = ArtifactMaterializationService(
            factory,
            store,  # type: ignore[arg-type]
            preparation,
            GuideFormatDetector(GuideFormatLimits()),
            _namespace(),
            authority_factory=lambda _: authority,
        )

        with pytest.raises(GuideSourceMaterializationError, match="incident"):
            await service.materialize_guide_source(
                _materialization_request(ids, binding_id=binding_id, authority=authority)
            )

        async with factory() as session:
            incident = await session.scalar(select(GuideSourceArtifactIncident))
            assert incident is not None
            assert incident.code == "truncated"
            assert incident.observed_byte_count == len(expected) - 4
            assert await session.scalar(select(func.count(GuideSourceFormatClassification.id))) == 0
        assert (await scratch.usage()).reservation_count == 0
    finally:
        scratch.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_same_size_changed_materialization_records_incident(
    isolated_database_env: str, tmp_path: Path
) -> None:
    expected = b"%PDF-1.7\nexpected"
    observed = b"%PDF-1.7\nobserved"
    assert len(expected) == len(observed)
    digest = "sha256:" + hashlib.sha256(expected).hexdigest()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    preparation, scratch = _preparation(tmp_path)
    authority = _AllowReadAuthority()
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(
                session, sha256=digest, byte_count=len(expected), media_type="application/pdf"
            )
        binding_id = await _create_binding(factory, ids)
        service = ArtifactMaterializationService(
            factory,
            _ReadStore(observed),  # type: ignore[arg-type]
            preparation,
            GuideFormatDetector(GuideFormatLimits()),
            _namespace(),
            authority_factory=lambda _: authority,
        )

        with pytest.raises(GuideSourceMaterializationError, match="incident"):
            await service.materialize_guide_source(
                _materialization_request(ids, binding_id=binding_id, authority=authority)
            )

        async with factory() as session:
            incident = await session.scalar(select(GuideSourceArtifactIncident))
            assert incident is not None
            assert incident.code == "changed"
            assert incident.observed_byte_count == len(observed)
            assert incident.observed_sha256 == "sha256:" + hashlib.sha256(observed).hexdigest()
            assert await session.scalar(select(func.count(GuideSourceFormatClassification.id))) == 0
    finally:
        scratch.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_post_read_lineage_drift_records_stale_incident(
    isolated_database_env: str, tmp_path: Path
) -> None:
    payload = b"%PDF-1.7\nverified"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    preparation, scratch = _preparation(tmp_path)
    authority = _AllowReadAuthority()
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(
                session, sha256=digest, byte_count=len(payload), media_type="application/pdf"
            )
        binding_id = await _create_binding(factory, ids)

        async def advance_setup_generation() -> None:
            async with factory() as session, session.begin():
                session.add(
                    ProjectSetupRun(
                        id=str(uuid4()),
                        project_id=str(ids["project"]),
                        guide_id=str(ids["guide"]),
                        guide_version="v1",
                        source_snapshot_id=str(ids["snapshot"]),
                        source_snapshot_hash=canonical_json_hash({"item": str(ids["item"])}),
                        setup_generation=2,
                        status="queued",
                        current_step="queued",
                        created_by="test",
                    )
                )

        service = ArtifactMaterializationService(
            factory,
            _ReadStore(payload, after_read=advance_setup_generation),  # type: ignore[arg-type]
            preparation,
            GuideFormatDetector(GuideFormatLimits()),
            _namespace(),
            authority_factory=lambda _: authority,
        )

        with pytest.raises(GuideSourceMaterializationError, match="incident"):
            await service.materialize_guide_source(
                _materialization_request(ids, binding_id=binding_id, authority=authority)
            )

        async with factory() as session:
            incident = await session.scalar(select(GuideSourceArtifactIncident))
            assert incident is not None
            assert incident.code == "stale"
            assert await session.scalar(select(func.count(GuideSourceFormatClassification.id))) == 0
    finally:
        scratch.close()
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed_field",
    [
        "project_id",
        "guide_id",
        "guide_source_snapshot_id",
        "source_item_id",
        "project_setup_run_id",
        "binding_id",
        "setup_generation",
    ],
)
async def test_cross_resource_materialization_denies_before_authority_and_provider_read(
    isolated_database_env: str,
    tmp_path: Path,
    changed_field: str,
) -> None:
    payload = b"%PDF-1.7\nverified"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    preparation, scratch = _preparation(tmp_path)
    authority = _AllowReadAuthority()
    store = _ReadStore(payload)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(
                session, sha256=digest, byte_count=len(payload), media_type="application/pdf"
            )
        binding_id = await _create_binding(factory, ids)
        service = ArtifactMaterializationService(
            factory,
            store,  # type: ignore[arg-type]
            preparation,
            GuideFormatDetector(GuideFormatLimits()),
            _namespace(),
            authority_factory=lambda _: authority,
        )

        wrong_value: UUID | int = 2 if changed_field == "setup_generation" else uuid4()
        request_binding_id = wrong_value if changed_field == "binding_id" else binding_id
        request_changes = {} if changed_field == "binding_id" else {changed_field: wrong_value}
        with pytest.raises(GuideSourceMaterializationError, match="unavailable"):
            await service.materialize_guide_source(
                _materialization_request(
                    ids,
                    binding_id=request_binding_id,
                    authority=authority,
                    **request_changes,
                )
            )

        assert store.open_count == 0
        assert authority.facts == []
    finally:
        scratch.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_composed_namespace_drift_denies_before_authority_and_provider_read(
    isolated_database_env: str, tmp_path: Path
) -> None:
    payload = b"%PDF-1.7\nverified"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    preparation, scratch = _preparation(tmp_path)
    authority = _AllowReadAuthority()
    store = _ReadStore(payload)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(
                session, sha256=digest, byte_count=len(payload), media_type="application/pdf"
            )
        binding_id = await _create_binding(factory, ids)
        drifted = ArtifactStorageNamespaceSpec(
            backend="local",
            adapter="other",
            provider_profile="test",
            namespace_descriptor={"root": "test"},
            namespace_fingerprint="sha256:" + "b" * 64,
        )
        service = ArtifactMaterializationService(
            factory,
            store,  # type: ignore[arg-type]
            preparation,
            GuideFormatDetector(GuideFormatLimits()),
            drifted,
            authority_factory=lambda _: authority,
        )

        with pytest.raises(ArtifactStorageNamespaceError, match="active storage namespace"):
            await service.materialize_guide_source(
                _materialization_request(ids, binding_id=binding_id, authority=authority)
            )

        assert store.open_count == 0
        assert authority.facts == []
    finally:
        scratch.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_materialization_cancellation_cleans_scratch_without_effect(
    isolated_database_env: str, tmp_path: Path
) -> None:
    payload = b"%PDF-1.7\nverified"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    preparation, scratch = _preparation(tmp_path)
    authority = _AllowReadAuthority()
    store = _BlockingReadStore(payload)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(
                session, sha256=digest, byte_count=len(payload), media_type="application/pdf"
            )
        binding_id = await _create_binding(factory, ids)
        service = ArtifactMaterializationService(
            factory,
            store,  # type: ignore[arg-type]
            preparation,
            GuideFormatDetector(GuideFormatLimits()),
            _namespace(),
            authority_factory=lambda _: authority,
        )
        task = asyncio.create_task(
            service.materialize_guide_source(
                _materialization_request(ids, binding_id=binding_id, authority=authority)
            )
        )
        await asyncio.wait_for(store.started.wait(), timeout=5)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert (await scratch.usage()).reservation_count == 0
        async with factory() as session:
            assert await session.scalar(select(func.count(GuideSourceFormatClassification.id))) == 0
            assert await session.scalar(select(func.count(GuideSourceArtifactIncident.id))) == 0
    finally:
        scratch.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_materialization_inspection_timeout_cleans_scratch_and_records_incident(
    isolated_database_env: str, tmp_path: Path
) -> None:
    payload = b"%PDF-1.7\nverified"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    preparation, scratch = _preparation(tmp_path)
    authority = _AllowReadAuthority()
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(
                session, sha256=digest, byte_count=len(payload), media_type="application/pdf"
            )
        binding_id = await _create_binding(factory, ids)

        async def deterministic_timeout(*_args: Any, **_kwargs: Any) -> None:
            raise ArtifactPreparationDeadlineError("artifact preparation deadline exceeded")

        preparation.inspect_prepared_artifact = deterministic_timeout  # type: ignore[method-assign]
        service = ArtifactMaterializationService(
            factory,
            _ReadStore(payload),  # type: ignore[arg-type]
            preparation,
            GuideFormatDetector(GuideFormatLimits()),
            _namespace(),
            authority_factory=lambda _: authority,
        )

        with pytest.raises(GuideSourceMaterializationError, match="incident"):
            await service.materialize_guide_source(
                _materialization_request(ids, binding_id=binding_id, authority=authority)
            )

        assert (await scratch.usage()).reservation_count == 0
        async with factory() as session:
            incident = await session.scalar(select(GuideSourceArtifactIncident))
            assert incident is not None
            assert incident.code == "unavailable"
            assert await session.scalar(select(func.count(GuideSourceFormatClassification.id))) == 0
    finally:
        scratch.close()
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_error", "expected_code"),
    [
        (ArtifactObjectMissingError("missing"), "missing"),
        (ArtifactStoreUnavailableError("unavailable"), "unavailable"),
    ],
)
async def test_provider_failure_records_only_bounded_artifact_incident(
    isolated_database_env: str,
    tmp_path: Path,
    provider_error: Exception,
    expected_code: str,
) -> None:
    payload = b"%PDF-1.7\nverified"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    preparation, scratch = _preparation(tmp_path)
    store = _FailingReadStore(provider_error)
    authority = _AllowReadAuthority()
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(
                session, sha256=digest, byte_count=len(payload), media_type="application/pdf"
            )
        binding_id = await _create_binding(factory, ids)
        service = ArtifactMaterializationService(
            factory,
            store,  # type: ignore[arg-type]
            preparation,
            GuideFormatDetector(GuideFormatLimits()),
            _namespace(),
            authority_factory=lambda _: authority,
        )

        with pytest.raises(GuideSourceMaterializationError, match="incident"):
            await service.materialize_guide_source(
                _materialization_request(ids, binding_id=binding_id, authority=authority)
            )

        async with factory() as session:
            incident = await session.scalar(select(GuideSourceArtifactIncident))
            assert incident is not None
            assert incident.code == expected_code
            assert incident.observed_sha256 is None
            assert incident.bounded_facts == {"verification_generation": 0}
        assert store.open_count == 1
        assert (await scratch.usage()).reservation_count == 0
    finally:
        scratch.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_binding_is_exact_immutable_and_idempotent(isolated_database_env: str) -> None:
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(session)
        first_authority = _AllowBindingAuthority()
        async with factory() as session, session.begin():
            first = await GuideSourceBindingService(session, first_authority).bind_guide_source(
                _request(ids, first_authority)
            )
        replay_authority = _AllowBindingAuthority()
        async with factory() as session, session.begin():
            replay = await GuideSourceBindingService(session, replay_authority).bind_guide_source(
                _request(ids, replay_authority)
            )
        assert not first.replayed
        assert replay.replayed
        assert replay.binding_id == first.binding_id
        assert first_authority.facts[0].verified_replica_id == ids["replica"]
        async with factory() as session:
            assert await session.scalar(select(func.count(GuideSourceArtifactBinding.id))) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_next_generation_explicitly_supersedes_prior_binding(
    isolated_database_env: str,
) -> None:
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(session)
        first_authority = _AllowBindingAuthority()
        async with factory() as session, session.begin():
            first = await GuideSourceBindingService(session, first_authority).bind_guide_source(
                _request(ids, first_authority)
            )
        second_run_id = uuid4()
        async with factory() as session, session.begin():
            snapshot = await session.get(GuideSourceSnapshot, str(ids["snapshot"]))
            assert snapshot is not None
            session.add(
                ProjectSetupRun(
                    id=str(second_run_id),
                    project_id=str(ids["project"]),
                    guide_id=str(ids["guide"]),
                    guide_version="v1",
                    source_snapshot_id=str(ids["snapshot"]),
                    source_snapshot_hash=snapshot.bundle_hash,
                    setup_generation=2,
                    status="queued",
                    current_step="queued",
                    created_by="test",
                )
            )
        second_authority = _AllowBindingAuthority()
        async with factory() as session, session.begin():
            second = await GuideSourceBindingService(session, second_authority).bind_guide_source(
                _request(
                    ids,
                    second_authority,
                    project_setup_run_id=second_run_id,
                    setup_generation=2,
                )
            )
        replay_authority = _AllowBindingAuthority()
        async with factory() as session, session.begin():
            replay = await GuideSourceBindingService(session, replay_authority).bind_guide_source(
                _request(
                    ids,
                    replay_authority,
                    project_setup_run_id=second_run_id,
                    setup_generation=2,
                )
            )
        async with factory() as session:
            successor = await session.get(GuideSourceArtifactBinding, str(second.binding_id))
            assert successor is not None
            assert successor.supersedes_binding_id == str(first.binding_id)
            assert replay.binding_id == second.binding_id
            assert replay.replayed
            assert await session.scalar(select(func.count(GuideSourceArtifactBinding.id))) == 2
    finally:
        await engine.dispose()


@pytest.mark.postgres_schema_contract
def test_0039_refuses_populated_binding_downgrade(
    isolated_database_env: str,
    migration_lock,
) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[1] / "alembic"),
    )
    asyncio.run(_create_populated_binding(isolated_database_env))
    with (
        migration_lock(),
        pytest.raises(
            RuntimeError,
            match="cannot downgrade populated guide source artifact bindings",
        ),
    ):
        command.downgrade(config, "0038_guide_source_ingest")


async def _create_populated_binding(database_url: str) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(session)
        authority = _AllowBindingAuthority()
        async with factory() as session, session.begin():
            await GuideSourceBindingService(session, authority).bind_guide_source(
                _request(ids, authority)
            )
    finally:
        await engine.dispose()


@pytest.mark.postgres_schema_contract
def test_0040_refuses_populated_classification_downgrade(
    isolated_database_env: str,
    migration_lock,
) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[1] / "alembic"),
    )
    asyncio.run(_create_populated_classification(isolated_database_env))
    with (
        migration_lock(),
        pytest.raises(
            RuntimeError,
            match="cannot downgrade populated guide materialization evidence",
        ),
    ):
        command.downgrade(config, "0039_guide_source_bindings")


async def _create_populated_classification(database_url: str) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(session)
        binding_id = await _create_binding(factory, ids)
        async with factory() as session, session.begin():
            session.add(
                GuideSourceFormatClassification(
                    id=str(uuid4()),
                    binding_id=str(binding_id),
                    content_id=str(ids["content"]),
                    verified_replica_id=str(ids["replica"]),
                    setup_generation=1,
                    sha256="sha256:" + "a" * 64,
                    byte_count=42,
                    media_type="application/pdf",
                    detected_format="pdf",
                    status="classified",
                    detector_name="workstream.guide_format",
                    detector_version="1",
                    classification_facts={},
                )
            )
    finally:
        await engine.dispose()


@pytest.mark.postgres_schema_contract
def test_0040_refuses_incident_only_downgrade(
    isolated_database_env: str,
    migration_lock,
) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[1] / "alembic"),
    )
    asyncio.run(_create_populated_incident(isolated_database_env))
    with (
        migration_lock(),
        pytest.raises(
            RuntimeError,
            match="cannot downgrade populated guide materialization evidence",
        ),
    ):
        command.downgrade(config, "0039_guide_source_bindings")


async def _create_populated_incident(database_url: str) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(session)
        binding_id = await _create_binding(factory, ids)
        async with factory() as session, session.begin():
            session.add(
                GuideSourceArtifactIncident(
                    id=str(uuid4()),
                    binding_id=str(binding_id),
                    content_id=str(ids["content"]),
                    verified_replica_id=str(ids["replica"]),
                    setup_generation=1,
                    code="missing",
                    observed_sha256=None,
                    observed_byte_count=None,
                    bounded_facts={"verification_generation": 0},
                )
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "missing_item",
        "unverified",
        "status_only",
        "cross_project",
        "cross_guide",
        "wrong_run",
        "stale_generation",
    ],
)
async def test_binding_fails_closed_before_authority_or_effect(
    isolated_database_env: str,
    failure: str,
) -> None:
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(
                session,
                verified=failure != "unverified",
                verification_receipt=failure != "status_only",
            )
            if failure == "stale_generation":
                session.add(
                    ProjectSetupRun(
                        id=str(uuid4()),
                        project_id=str(ids["project"]),
                        guide_id=str(ids["guide"]),
                        guide_version="v1",
                        source_snapshot_id=str(ids["snapshot"]),
                        source_snapshot_hash=(
                            await session.get(GuideSourceSnapshot, str(ids["snapshot"]))
                        ).bundle_hash,
                        setup_generation=2,
                        status="queued",
                        current_step="queued",
                        created_by="test",
                    )
                )
                await session.commit()
        authority = _AllowBindingAuthority()
        request = _request(
            ids,
            authority,
            project_id=uuid4() if failure == "cross_project" else ids["project"],
            guide_id=uuid4() if failure == "cross_guide" else ids["guide"],
            source_item_id=uuid4() if failure == "missing_item" else ids["item"],
            project_setup_run_id=uuid4() if failure == "wrong_run" else ids["run"],
        )
        with pytest.raises(GuideSourceBindingError):
            async with factory() as session, session.begin():
                await GuideSourceBindingService(session, authority).bind_guide_source(request)
        assert authority.facts == []
        async with factory() as session:
            assert await session.scalar(select(func.count(GuideSourceArtifactBinding.id))) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_binding_denial_rolls_back_without_effect(isolated_database_env: str) -> None:
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(session)
        authority = _AllowBindingAuthority(deny=True)
        with pytest.raises(ArtifactAuthorityDeniedError):
            async with factory() as session, session.begin():
                await GuideSourceBindingService(session, authority).bind_guide_source(
                    _request(ids, authority)
                )
        async with factory() as session:
            assert await session.scalar(select(func.count(GuideSourceArtifactBinding.id))) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_default_live_binding_authority_denies(isolated_database_env: str) -> None:
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(session)
        authority = _AllowBindingAuthority()
        with pytest.raises(ArtifactAuthorityDeniedError):
            async with factory() as session, session.begin():
                await GuideSourceBindingService(session).bind_guide_source(_request(ids, authority))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_binding_creates_one_business_effect(isolated_database_env: str) -> None:
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            ids = await _seed_binding_lineage(session)

        async def bind_once() -> bool:
            authority = _AllowBindingAuthority()
            async with factory() as session, session.begin():
                result = await GuideSourceBindingService(session, authority).bind_guide_source(
                    _request(ids, authority)
                )
                return result.replayed

        assert sorted(await asyncio.gather(bind_once(), bind_once())) == [False, True]
        async with factory() as session:
            assert await session.scalar(select(func.count(GuideSourceArtifactBinding.id))) == 1
    finally:
        await engine.dispose()
