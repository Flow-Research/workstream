"""PostgreSQL integration tests for the ArtifactStore v2 orchestration boundary."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.artifacts.local import LocalStorageAdapter, LocalStorageBootstrap
from app.core.config import Settings
from app.core.hashing import canonical_json_hash
from app.interfaces.artifacts import (
    ArtifactByteRange,
    ArtifactConfigurationError,
    ArtifactInputMismatchError,
    ArtifactIntegrityError,
    ArtifactObjectHead,
    ArtifactPutObservation,
    ArtifactPutResult,
    ArtifactStoreUnavailableError,
    ArtifactStoreNamespaceIdentity,
)
from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.modules.artifacts.models import (
    ArtifactContent,
    ArtifactOperationReceipt,
    ArtifactReplica,
    ArtifactStorageNamespace,
    ArtifactUploadItem,
    ArtifactUploadSession,
)
from app.modules.artifacts.service import (
    ArtifactIngestStateError,
    ArtifactStorageNamespaceError,
    ArtifactStorageNamespaceSpec,
    ArtifactStorageOrchestrator,
    ProviderAttemptFence,
    artifact_storage_namespace_spec,
    validate_artifact_storage_namespace_at_startup,
)
import app.modules.artifacts.service as artifact_service_module
from app.modules.artifacts.sources import ArtifactCommitment, CommittedArtifactSource
from app.modules.projects.models import Project
from tests.artifact_store_helpers import (
    local_namespace_claim,
    minted_source as _minted_source,
)


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return config


@pytest.fixture
def artifact_database_env(isolated_database_env: str, migration_lock) -> str:
    """Provide one fully migrated empty PostgreSQL database per test."""
    config = _alembic_config()
    with migration_lock():
        asyncio.run(_truncate_artifacts_if_present(isolated_database_env))
        command.downgrade(config, "base")
        command.upgrade(config, "head")
    yield isolated_database_env
    with migration_lock():
        asyncio.run(_truncate_artifacts(isolated_database_env))
        command.downgrade(config, "base")


async def _truncate_artifacts(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "truncate table artifact_storage_namespaces, artifact_upload_sessions, "
                    "artifact_contents cascade"
                )
            )
    finally:
        await engine.dispose()


async def _truncate_artifacts_if_present(database_url: str) -> None:
    """Clear only artifact tables that exist at the database's current revision."""
    engine = create_async_engine(database_url)
    candidates = (
        "artifact_storage_namespaces",
        "artifact_upload_sessions",
        "artifact_contents",
    )
    try:
        async with engine.begin() as connection:
            existing = [
                table_name
                for table_name in candidates
                if await connection.scalar(
                    text("select to_regclass(:table_name) is not null"),
                    {"table_name": f"public.{table_name}"},
                )
            ]
            if existing:
                await connection.execute(text(f"truncate table {', '.join(existing)} cascade"))
    finally:
        await engine.dispose()


def _settings(tmp_path: Path) -> Settings:
    (tmp_path / "store").mkdir(mode=0o700, exist_ok=True)
    return Settings(
        environment="test",
        artifact_store_backend="local",
        artifact_local_root=tmp_path / "store",
        artifact_scratch_root=tmp_path / "scratch",
        artifact_scratch_minimum_free_bytes=0,
    )


async def _seed_reserved_item(
    session,
    commitment: ArtifactCommitment,
) -> str:
    project_id = str(uuid4())
    session_id = str(uuid4())
    item_id = str(uuid4())
    session.add(Project(id=project_id, name="Artifact project", slug=f"artifact-{project_id}"))
    await session.flush()
    session.add(
        ArtifactUploadSession(
            id=session_id,
            actor_id="actor-1",
            project_id=project_id,
            permitted_roles=["submission"],
            state="open",
            maximum_bytes=1024,
            current_bytes=0,
            reserved_bytes=commitment.byte_count,
            maximum_items=1,
            current_items=0,
            reserved_items=1,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            cas_version=0,
        )
    )
    await session.flush()
    session.add(
        ArtifactUploadItem(
            id=item_id,
            session_id=session_id,
            logical_role="submission",
            display_name="result.bin",
            media_type=commitment.media_type,
            reserved_bytes=commitment.byte_count,
            expected_sha256=commitment.sha256,
            expected_size=commitment.byte_count,
            idempotency_key=f"put-{item_id}",
            request_digest=canonical_json_hash(
                {
                    "sha256": commitment.sha256,
                    "byte_count": commitment.byte_count,
                    "media_type": commitment.media_type,
                }
            ),
            state="reserved",
            cas_version=0,
        )
    )
    await session.commit()
    return item_id


async def _seed_reserved_items_in_one_session(
    session,
    commitments: tuple[ArtifactCommitment, ...],
) -> tuple[str, ...]:
    """Create multiple independently fenced items under one aggregate ledger."""
    project_id = str(uuid4())
    session_id = str(uuid4())
    item_ids = tuple(str(uuid4()) for _ in commitments)
    total_bytes = sum(commitment.byte_count for commitment in commitments)
    session.add(Project(id=project_id, name="Artifact project", slug=f"artifact-{project_id}"))
    await session.flush()
    session.add(
        ArtifactUploadSession(
            id=session_id,
            actor_id="actor-1",
            project_id=project_id,
            permitted_roles=["submission"],
            state="open",
            maximum_bytes=1024,
            current_bytes=0,
            reserved_bytes=total_bytes,
            maximum_items=len(commitments),
            current_items=0,
            reserved_items=len(commitments),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            cas_version=0,
        )
    )
    await session.flush()
    for item_id, commitment in zip(item_ids, commitments, strict=True):
        session.add(
            ArtifactUploadItem(
                id=item_id,
                session_id=session_id,
                logical_role="submission",
                display_name=f"{item_id}.bin",
                media_type=commitment.media_type,
                reserved_bytes=commitment.byte_count,
                expected_sha256=commitment.sha256,
                expected_size=commitment.byte_count,
                idempotency_key=f"put-{item_id}",
                request_digest=canonical_json_hash(
                    {
                        "sha256": commitment.sha256,
                        "byte_count": commitment.byte_count,
                        "media_type": commitment.media_type,
                    }
                ),
                state="reserved",
                cas_version=0,
            )
        )
    await session.commit()
    return item_ids


@pytest.mark.asyncio
async def test_put_acknowledgement_stops_at_pending_verification(
    artifact_database_env: str,
    tmp_path: Path,
) -> None:
    content = b"artifact-v2"
    engine = create_async_engine(artifact_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = _settings(tmp_path)
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=tmp_path / "store", buffer_bytes=2))
    namespace = artifact_storage_namespace_spec(settings, bootstrap)
    store = bootstrap.initialize_after_namespace_claim(local_namespace_claim(bootstrap))
    try:
        async with _minted_source(tmp_path / "scratch", content) as source:
            async with factory() as session:
                item_id = await _seed_reserved_item(session, source.commitment)
                result = await ArtifactStorageOrchestrator(
                    session, store, namespace
                ).put_reserved_item(item_id, source)
        async with _minted_source(tmp_path / "scratch-replay", content) as replay_source:
            async with factory() as session:
                replay_item_id = await _seed_reserved_item(session, replay_source.commitment)
                replay = await ArtifactStorageOrchestrator(
                    session, store, namespace
                ).put_reserved_item(replay_item_id, replay_source)
                assert replay.replayed is True

        async with factory() as session:
            item = await session.get(ArtifactUploadItem, item_id)
            replica = (await session.execute(select(ArtifactReplica))).scalar_one()
            receipts = (await session.execute(select(ArtifactOperationReceipt))).scalars().all()
            receipt = next(value for value in receipts if value.upload_item_id == item_id)
            replay_receipt = next(
                value for value in receipts if value.upload_item_id == replay_item_id
            )
            namespace_row = (await session.execute(select(ArtifactStorageNamespace))).scalar_one()
            assert item is not None
            assert item.state == "stored_pending_verification"
            assert item.provider_object_ref == result.provider_object_ref
            assert replica.verification_state == "pending"
            assert replica.availability_state == "unknown"
            assert replica.integrity_state == "unknown"
            assert replica.namespace_fingerprint == namespace_row.namespace_fingerprint
            assert receipt.operation == "put"
            assert receipt.outcome == "stored_pending_verification"
            assert receipt.provider_object_ref == result.provider_object_ref
            assert receipt.replayed is False
            assert len(receipts) == 2
            assert replay_receipt.replayed is True
            assert await store.head(result.provider_object_ref) == ArtifactObjectHead(
                result.provider_object_ref,
                exists=True,
                byte_count=len(content),
                media_type=None,
            )
    finally:
        store.close()
        await engine.dispose()


class _UnavailableStore:
    """Count provider calls and fail with one sanitized retryable error."""

    identity = ExternalServiceAdapterIdentity("artifact_store", "local")
    namespace_identity = ArtifactStoreNamespaceIdentity(
        provider_profile="local-v2",
        descriptor_items=(
            ("private_prefix", "objects/sha256"),
            ("private_root_identity", "sha256:" + "0" * 64),
        ),
    )

    def __init__(self) -> None:
        self.put_calls = 0

    async def put(self, _source: CommittedArtifactSource) -> ArtifactPutResult:
        self.put_calls += 1
        raise ArtifactStoreUnavailableError()

    async def observe_put_result(self, _commitment: ArtifactCommitment) -> ArtifactPutObservation:
        raise NotImplementedError

    def open(
        self, _provider_object_ref: str, _byte_range: ArtifactByteRange | None = None
    ) -> AsyncIterator[bytes]:
        raise NotImplementedError

    async def head(self, _provider_object_ref: str) -> ArtifactObjectHead:
        raise NotImplementedError


class _TerminalStore(_UnavailableStore):
    async def put(self, _source: CommittedArtifactSource) -> ArtifactPutResult:
        self.put_calls += 1
        raise ArtifactInputMismatchError()


class _AcknowledgementUnknownThenReplayStore(_UnavailableStore):
    """Lose the first acknowledgement and return an exact replay next."""

    async def put(self, source: CommittedArtifactSource) -> ArtifactPutResult:
        self.put_calls += 1
        if self.put_calls == 1:
            raise RuntimeError("provider acknowledgement lost")
        digest_hex = source.commitment.sha256[7:]
        return ArtifactPutResult(
            f"sha256/{digest_hex[:2]}/{digest_hex[2:]}",
            replayed=True,
        )


class _CancelledStore(_UnavailableStore):
    async def put(self, _source: CommittedArtifactSource) -> ArtifactPutResult:
        self.put_calls += 1
        raise asyncio.CancelledError("provider put cancelled")


class _AcknowledgingStore(_UnavailableStore):
    async def put(self, source: CommittedArtifactSource) -> ArtifactPutResult:
        self.put_calls += 1
        digest_hex = source.commitment.sha256[7:]
        return ArtifactPutResult(
            f"sha256/{digest_hex[:2]}/{digest_hex[2:]}",
            replayed=False,
        )


class _NamespaceObservingAcknowledgingStore(_AcknowledgingStore):
    """Assert the committed namespace exists before the provider is invoked."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__()
        self._factory = factory
        self.observed_namespace_fingerprint: str | None = None

    async def put(self, source: CommittedArtifactSource) -> ArtifactPutResult:
        async with self._factory() as session:
            namespace = await session.scalar(select(ArtifactStorageNamespace))
        assert namespace is not None
        self.observed_namespace_fingerprint = namespace.namespace_fingerprint
        return await super().put(source)


class _ConcurrentAcknowledgingStore(_AcknowledgingStore):
    """Release two same-object acknowledgements into finalization together."""

    def __init__(self) -> None:
        super().__init__()
        self._arrivals = 0
        self._release = asyncio.Event()

    async def put(self, source: CommittedArtifactSource) -> ArtifactPutResult:
        self.put_calls += 1
        self._arrivals += 1
        arrival = self._arrivals
        if self._arrivals == 2:
            self._release.set()
        await asyncio.wait_for(self._release.wait(), timeout=2)
        digest_hex = source.commitment.sha256[7:]
        return ArtifactPutResult(
            f"sha256/{digest_hex[:2]}/{digest_hex[2:]}",
            replayed=arrival > 1,
        )


class _ConcurrentDistinctAcknowledgingStore(_ConcurrentAcknowledgingStore):
    """Release two distinct initial publications into finalization together."""

    async def put(self, source: CommittedArtifactSource) -> ArtifactPutResult:
        result = await super().put(source)
        return ArtifactPutResult(result.provider_object_ref, replayed=False)


@pytest.mark.asyncio
async def test_concurrent_same_object_finalization_reuses_one_replica(
    artifact_database_env: str,
    tmp_path: Path,
) -> None:
    """Finalize two exact replays with one replica and two receipts."""
    content = b"concurrent-artifact-v2"
    engine = create_async_engine(artifact_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    store = _ConcurrentAcknowledgingStore()
    namespace = artifact_storage_namespace_spec(_settings(tmp_path), store)
    try:
        async with _minted_source(tmp_path / "scratch-first", content) as first_source:
            async with _minted_source(tmp_path / "scratch-second", content) as second_source:
                async with factory() as session:
                    first_item_id = await _seed_reserved_item(session, first_source.commitment)
                    second_item_id = await _seed_reserved_item(session, second_source.commitment)
                    await ArtifactStorageOrchestrator(
                        session, store, namespace
                    ).ensure_storage_namespace()
                    async with session.begin():
                        session.add(
                            ArtifactContent(
                                id=str(uuid4()),
                                sha256=first_source.commitment.sha256,
                                byte_count=first_source.commitment.byte_count,
                                media_type=first_source.commitment.media_type,
                                normalized_display_name="preexisting.bin",
                            )
                        )

                async def finalize(item_id: str, source: CommittedArtifactSource) -> None:
                    async with factory() as session:
                        await ArtifactStorageOrchestrator(
                            session, store, namespace
                        ).put_reserved_item(item_id, source)

                await asyncio.gather(
                    finalize(first_item_id, first_source),
                    finalize(second_item_id, second_source),
                )

        async with factory() as session:
            items = (
                (
                    await session.execute(
                        select(ArtifactUploadItem).where(
                            ArtifactUploadItem.id.in_((first_item_id, second_item_id))
                        )
                    )
                )
                .scalars()
                .all()
            )
            replicas = (await session.execute(select(ArtifactReplica))).scalars().all()
            receipts = (await session.execute(select(ArtifactOperationReceipt))).scalars().all()

        assert {item.state for item in items} == {"stored_pending_verification"}
        assert len(items) == 2
        assert len(replicas) == 1
        assert replicas[0].verification_state == "pending"
        assert replicas[0].availability_state == "unknown"
        assert replicas[0].integrity_state == "unknown"
        assert len(receipts) == 2
        assert {receipt.replica_id for receipt in receipts} == {replicas[0].id}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_independent_items_in_one_session_finalize_without_shared_cas_replay(
    artifact_database_env: str,
    tmp_path: Path,
) -> None:
    """Fence provider acknowledgements per item while accounting one session."""
    engine = create_async_engine(artifact_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    store = _ConcurrentDistinctAcknowledgingStore()
    namespace = artifact_storage_namespace_spec(_settings(tmp_path), store)
    try:
        async with _minted_source(tmp_path / "scratch-first", b"first-item") as first:
            async with _minted_source(tmp_path / "scratch-second", b"second-item") as second:
                async with factory() as session:
                    item_ids = await _seed_reserved_items_in_one_session(
                        session,
                        (first.commitment, second.commitment),
                    )
                    await ArtifactStorageOrchestrator(
                        session, store, namespace
                    ).ensure_storage_namespace()

                async def finalize(item_id: str, source: CommittedArtifactSource) -> None:
                    async with factory() as candidate_session:
                        await ArtifactStorageOrchestrator(
                            candidate_session, store, namespace
                        ).put_reserved_item(item_id, source)

                await asyncio.gather(
                    finalize(item_ids[0], first),
                    finalize(item_ids[1], second),
                )

        async with factory() as session:
            items = (
                (
                    await session.execute(
                        select(ArtifactUploadItem).where(ArtifactUploadItem.id.in_(item_ids))
                    )
                )
                .scalars()
                .all()
            )
            upload_session = await session.get(ArtifactUploadSession, items[0].session_id)
            receipts = (await session.execute(select(ArtifactOperationReceipt))).scalars().all()

        assert {item.state for item in items} == {"stored_pending_verification"}
        assert upload_session is not None
        assert upload_session.reserved_bytes == 0
        assert upload_session.reserved_items == 0
        assert upload_session.current_bytes == len(b"first-item") + len(b"second-item")
        assert upload_session.current_items == 2
        assert len(receipts) == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_rejects_partial_upload_result_metadata(
    artifact_database_env: str,
    tmp_path: Path,
) -> None:
    """Require both stored-result references or neither in every item state."""
    engine = create_async_engine(artifact_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with _minted_source(tmp_path / "scratch", b"constraint") as source:
            async with factory() as session:
                item_id = await _seed_reserved_item(session, source.commitment)
                content_id = str(uuid4())
                session.add(
                    ArtifactContent(
                        id=content_id,
                        sha256=source.commitment.sha256,
                        byte_count=source.commitment.byte_count,
                        media_type=source.commitment.media_type,
                        normalized_display_name="constraint.bin",
                    )
                )
                await session.commit()

            with pytest.raises(IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "update artifact_upload_items set content_id = :content_id "
                            "where id = :item_id"
                        ),
                        {"content_id": content_id, "item_id": item_id},
                    )
            with pytest.raises(IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "update artifact_upload_items "
                            "set provider_object_ref = 'sha256/00/object' where id = :item_id"
                        ),
                        {"item_id": item_id},
                    )

        async with factory() as session:
            item = await session.get(ArtifactUploadItem, item_id)
            assert item is not None
            assert item.content_id is None
            assert item.provider_object_ref is None
    finally:
        await engine.dispose()


def test_reservation_accounting_rejects_drift_without_clamping() -> None:
    """Never consume capacity belonging to a different upload item."""
    upload_session = ArtifactUploadSession(reserved_bytes=3, reserved_items=1)
    item = ArtifactUploadItem(reserved_bytes=4)

    with pytest.raises(ArtifactIntegrityError, match="reservation accounting"):
        ArtifactStorageOrchestrator._apply_committed_accounting(upload_session, item, 4)

    assert upload_session.reserved_bytes == 3
    assert upload_session.reserved_items == 1


class _FinalizationCancelledOrchestrator(ArtifactStorageOrchestrator):
    async def _finalize_put(
        self,
        item_id: str,
        commitment: ArtifactCommitment,
        result: ArtifactPutResult,
        fence: ProviderAttemptFence,
        *,
        correlation_id: str,
    ) -> None:
        del item_id, commitment, result, fence, correlation_id
        raise asyncio.CancelledError("put finalization cancelled")


async def _assert_replay_required_without_durable_facts(
    factory: async_sessionmaker,
    item_id: str,
) -> None:
    async with factory() as session:
        item = await session.get(ArtifactUploadItem, item_id)
        assert item is not None
        upload_session = await session.get(ArtifactUploadSession, item.session_id)
        assert upload_session is not None
        assert item.state == "replay_required"
        assert item.error_code == "artifact_put_acknowledgement_unknown"
        assert upload_session.reserved_bytes == item.reserved_bytes
        assert upload_session.reserved_items == 1
        assert await session.scalar(select(ArtifactContent)) is None
        assert await session.scalar(select(ArtifactReplica)) is None
        assert await session.scalar(select(ArtifactOperationReceipt)) is None


@pytest.mark.asyncio
async def test_retryable_put_marks_existing_item_replay_required(
    artifact_database_env: str,
    tmp_path: Path,
) -> None:
    engine = create_async_engine(artifact_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    store = _UnavailableStore()
    try:
        async with _minted_source(tmp_path / "scratch", b"retry") as source:
            async with factory() as session:
                item_id = await _seed_reserved_item(session, source.commitment)
                orchestrator = ArtifactStorageOrchestrator(
                    session,
                    store,
                    artifact_storage_namespace_spec(_settings(tmp_path), store),
                )
                with pytest.raises(ArtifactStoreUnavailableError):
                    await orchestrator.put_reserved_item(item_id, source)

        async with factory() as session:
            item = await session.get(ArtifactUploadItem, item_id)
            assert item is not None
            assert item.state == "replay_required"
            assert item.error_code == "artifact_put_acknowledgement_unknown"
            assert await session.scalar(select(ArtifactReplica)) is None
            assert await session.scalar(select(ArtifactOperationReceipt)) is None
        assert store.put_calls == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_same_item_replay_finalizes_once_without_double_accounting(
    artifact_database_env: str,
    tmp_path: Path,
) -> None:
    engine = create_async_engine(artifact_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    store = _AcknowledgementUnknownThenReplayStore()
    content = b"same-item-replay"
    try:
        async with _minted_source(tmp_path / "scratch-first", content) as source:
            async with factory() as session:
                item_id = await _seed_reserved_item(session, source.commitment)
                orchestrator = ArtifactStorageOrchestrator(
                    session,
                    store,
                    artifact_storage_namespace_spec(_settings(tmp_path), store),
                )
                with pytest.raises(RuntimeError, match="acknowledgement lost"):
                    await orchestrator.put_reserved_item(item_id, source)

        async with _minted_source(tmp_path / "scratch-replay", content) as replay:
            async with factory() as session:
                result = await ArtifactStorageOrchestrator(
                    session,
                    store,
                    artifact_storage_namespace_spec(_settings(tmp_path), store),
                ).put_reserved_item(item_id, replay)

        assert result.replayed is True
        async with factory() as session:
            item = await session.get(ArtifactUploadItem, item_id)
            assert item is not None
            upload_session = await session.get(ArtifactUploadSession, item.session_id)
            assert upload_session is not None
            receipts = (await session.execute(select(ArtifactOperationReceipt))).scalars().all()
            replicas = (await session.execute(select(ArtifactReplica))).scalars().all()
            contents = (await session.execute(select(ArtifactContent))).scalars().all()

        assert item.state == "stored_pending_verification"
        assert item.error_code is None
        assert upload_session.reserved_bytes == 0
        assert upload_session.reserved_items == 0
        assert upload_session.current_bytes == len(content)
        assert upload_session.current_items == 1
        assert len(contents) == 1
        assert len(replicas) == 1
        assert len(receipts) == 1
        assert receipts[0].upload_item_id == item_id
        assert receipts[0].replayed is True
        assert store.put_calls == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_provider_cancellation_persists_replay_required_without_facts(
    artifact_database_env: str,
    tmp_path: Path,
) -> None:
    engine = create_async_engine(artifact_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    store = _CancelledStore()
    try:
        async with _minted_source(tmp_path / "scratch", b"provider cancellation") as source:
            async with factory() as session:
                item_id = await _seed_reserved_item(session, source.commitment)
                orchestrator = ArtifactStorageOrchestrator(
                    session,
                    store,
                    artifact_storage_namespace_spec(_settings(tmp_path), store),
                )
                with pytest.raises(asyncio.CancelledError, match="provider put cancelled"):
                    await orchestrator.put_reserved_item(item_id, source)

        await _assert_replay_required_without_durable_facts(factory, item_id)
        assert store.put_calls == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_finalization_cancellation_persists_replay_required_without_facts(
    artifact_database_env: str,
    tmp_path: Path,
) -> None:
    engine = create_async_engine(artifact_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    store = _AcknowledgingStore()
    try:
        async with _minted_source(tmp_path / "scratch", b"finalization cancellation") as source:
            async with factory() as session:
                item_id = await _seed_reserved_item(session, source.commitment)
                orchestrator = _FinalizationCancelledOrchestrator(
                    session,
                    store,
                    artifact_storage_namespace_spec(_settings(tmp_path), store),
                )
                with pytest.raises(asyncio.CancelledError, match="finalization cancelled"):
                    await orchestrator.put_reserved_item(item_id, source)

        await _assert_replay_required_without_durable_facts(factory, item_id)
        assert store.put_calls == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_terminal_put_failure_releases_reservation_and_fails_item(
    artifact_database_env: str,
    tmp_path: Path,
) -> None:
    engine = create_async_engine(artifact_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    store = _TerminalStore()
    try:
        async with _minted_source(tmp_path / "scratch", b"terminal") as source:
            async with factory() as session:
                item_id = await _seed_reserved_item(session, source.commitment)
                with pytest.raises(ArtifactInputMismatchError):
                    await ArtifactStorageOrchestrator(
                        session,
                        store,
                        artifact_storage_namespace_spec(_settings(tmp_path), store),
                    ).put_reserved_item(item_id, source)

        async with factory() as session:
            item = await session.get(ArtifactUploadItem, item_id)
            assert item is not None
            upload_session = await session.get(ArtifactUploadSession, item.session_id)
            assert item.state == "failed"
            assert item.error_code == "artifact_input_mismatch"
            assert upload_session is not None
            assert upload_session.reserved_bytes == 0
            assert upload_session.reserved_items == 0
        assert store.put_calls == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_changed_commitment_is_rejected_before_provider_io(
    artifact_database_env: str,
    tmp_path: Path,
) -> None:
    engine = create_async_engine(artifact_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    store = _UnavailableStore()
    try:
        async with _minted_source(tmp_path / "scratch-first", b"first") as first:
            async with factory() as session:
                item_id = await _seed_reserved_item(session, first.commitment)
        async with _minted_source(tmp_path / "scratch-second", b"second") as second:
            async with factory() as session:
                with pytest.raises(ArtifactIngestStateError, match="commitment changed"):
                    await ArtifactStorageOrchestrator(
                        session,
                        store,
                        artifact_storage_namespace_spec(_settings(tmp_path), store),
                    ).put_reserved_item(item_id, second)
        assert store.put_calls == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_namespace_mismatch_fails_before_provider_io(
    artifact_database_env: str,
    tmp_path: Path,
) -> None:
    engine = create_async_engine(artifact_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    store = _UnavailableStore()
    settings = _settings(tmp_path)
    canonical = artifact_storage_namespace_spec(settings, store)
    conflicting_descriptor = dict(canonical.namespace_descriptor)
    conflicting_descriptor["private_root_identity"] = "sha256:" + "f" * 64
    conflicting = ArtifactStorageNamespaceSpec(
        backend=canonical.backend,
        adapter=canonical.adapter,
        provider_profile=canonical.provider_profile,
        namespace_descriptor=conflicting_descriptor,
        namespace_fingerprint=canonical_json_hash(conflicting_descriptor),
    )
    try:
        async with factory() as session:
            await ArtifactStorageOrchestrator(session, store, canonical).ensure_storage_namespace()
        async with _minted_source(tmp_path / "scratch", b"blocked") as source:
            async with factory() as session:
                item_id = await _seed_reserved_item(session, source.commitment)
                with pytest.raises(ArtifactStorageNamespaceError):
                    await ArtifactStorageOrchestrator(
                        session, store, conflicting
                    ).put_reserved_item(item_id, source)
        assert store.put_calls == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_different_first_namespace_writers_have_one_winner(
    artifact_database_env: str,
    tmp_path: Path,
) -> None:
    engine = create_async_engine(artifact_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    first_store = _NamespaceObservingAcknowledgingStore(factory)
    second_store = _NamespaceObservingAcknowledgingStore(factory)
    first = artifact_storage_namespace_spec(_settings(tmp_path), first_store)
    second_descriptor = dict(first.namespace_descriptor)
    second_descriptor["private_root_identity"] = "sha256:" + "a" * 64
    second = ArtifactStorageNamespaceSpec(
        backend=first.backend,
        adapter=first.adapter,
        provider_profile=first.provider_profile,
        namespace_descriptor=second_descriptor,
        namespace_fingerprint=canonical_json_hash(second_descriptor),
    )

    async def publish(
        item_id: str,
        source: CommittedArtifactSource,
        store: _NamespaceObservingAcknowledgingStore,
        spec: ArtifactStorageNamespaceSpec,
    ) -> object:
        async with factory() as session:
            try:
                return await ArtifactStorageOrchestrator(session, store, spec).put_reserved_item(
                    item_id, source
                )
            except ArtifactStorageNamespaceError as exc:
                return exc

    try:
        async with _minted_source(tmp_path / "scratch-first", b"first") as first_source:
            async with _minted_source(tmp_path / "scratch-second", b"second") as second_source:
                async with factory() as session:
                    first_item_id = await _seed_reserved_item(session, first_source.commitment)
                    second_item_id = await _seed_reserved_item(session, second_source.commitment)
                outcomes = await asyncio.gather(
                    publish(first_item_id, first_source, first_store, first),
                    publish(second_item_id, second_source, second_store, second),
                )

        assert sum(isinstance(value, ArtifactPutResult) for value in outcomes) == 1
        assert sum(isinstance(value, ArtifactStorageNamespaceError) for value in outcomes) == 1
        winning_index = next(
            index for index, value in enumerate(outcomes) if isinstance(value, ArtifactPutResult)
        )
        stores = (first_store, second_store)
        specs = (first, second)
        assert stores[winning_index].put_calls == 1
        assert (
            stores[winning_index].observed_namespace_fingerprint
            == specs[winning_index].namespace_fingerprint
        )
        assert stores[1 - winning_index].put_calls == 0
        assert stores[1 - winning_index].observed_namespace_fingerprint is None
        async with factory() as session:
            namespace = await session.scalar(select(ArtifactStorageNamespace))
            assert namespace is not None
            assert namespace.namespace_fingerprint == specs[winning_index].namespace_fingerprint
    finally:
        await engine.dispose()


def test_namespace_descriptor_is_canonical_and_does_not_store_local_path(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    store = _UnavailableStore()
    spec = artifact_storage_namespace_spec(settings, store)
    serialized = repr(spec.namespace_descriptor)

    assert spec.backend == "local"
    assert spec.provider_profile == "local-v2"
    assert spec.namespace_fingerprint == canonical_json_hash(spec.namespace_descriptor)
    assert str(settings.artifact_local_root) not in serialized
    assert spec.namespace_descriptor["private_root_identity"].startswith("sha256:")


def test_namespace_descriptor_changes_when_local_root_is_replaced(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    first_store = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    original = artifact_storage_namespace_spec(settings, first_store)
    first_store.close()

    root = settings.artifact_local_root
    assert root is not None
    root.rename(tmp_path / "replaced-store")
    root.mkdir(mode=0o700)

    replacement_store = LocalStorageBootstrap(LocalStorageAdapter(root=root))
    replacement = artifact_storage_namespace_spec(settings, replacement_store)
    replacement_store.close()
    assert replacement.namespace_descriptor != original.namespace_descriptor
    assert replacement.namespace_fingerprint != original.namespace_fingerprint


def test_store_bootstrap_requires_preprovisioned_private_root(tmp_path: Path) -> None:
    with pytest.raises(ArtifactConfigurationError, match="storage is unavailable"):
        LocalStorageAdapter(root=tmp_path / "missing-store")


def test_namespace_spec_rejects_adapter_drift(tmp_path: Path) -> None:
    local_store = _UnavailableStore()
    with pytest.raises(ArtifactStorageNamespaceError, match="identity"):
        artifact_storage_namespace_spec(Settings(), local_store)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_failure",
    [asyncio.CancelledError("cancelled"), RuntimeError("provider crashed")],
)
async def test_unexpected_or_cancelled_provider_failure_requires_replay(
    tmp_path: Path,
    provider_failure: BaseException,
) -> None:
    store = _UnavailableStore()
    store.put = AsyncMock(side_effect=provider_failure)  # type: ignore[method-assign]
    orchestrator = ArtifactStorageOrchestrator(
        None,  # type: ignore[arg-type]
        store,
        artifact_storage_namespace_spec(_settings(tmp_path), store),
    )
    orchestrator._start_put = AsyncMock(  # type: ignore[method-assign]
        return_value=ProviderAttemptFence(1)
    )
    orchestrator._mark_replay_required = AsyncMock()  # type: ignore[method-assign]

    async with _minted_source(tmp_path / "scratch", b"provider") as source:
        with pytest.raises(type(provider_failure)):
            await orchestrator.put_reserved_item("item", source)
    orchestrator._mark_replay_required.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "finalization_failure",
    [
        ArtifactInputMismatchError("mismatch"),
        asyncio.CancelledError("cancelled"),
        RuntimeError("database unavailable"),
    ],
)
async def test_finalization_failure_never_leaves_uploading_unresolved(
    tmp_path: Path,
    finalization_failure: BaseException,
) -> None:
    store = _UnavailableStore()
    store.put = AsyncMock(  # type: ignore[method-assign]
        return_value=ArtifactPutResult("sha256/00/" + "0" * 62, replayed=False)
    )
    orchestrator = ArtifactStorageOrchestrator(
        None,  # type: ignore[arg-type]
        store,
        artifact_storage_namespace_spec(_settings(tmp_path), store),
    )
    orchestrator._start_put = AsyncMock(  # type: ignore[method-assign]
        return_value=ProviderAttemptFence(1)
    )
    orchestrator._finalize_put = AsyncMock(  # type: ignore[method-assign]
        side_effect=finalization_failure
    )
    orchestrator._fail_put = AsyncMock()  # type: ignore[method-assign]
    orchestrator._mark_replay_required = AsyncMock()  # type: ignore[method-assign]

    async with _minted_source(tmp_path / "scratch", b"finalize") as source:
        with pytest.raises(type(finalization_failure)):
            await orchestrator.put_reserved_item("item", source)
    if isinstance(finalization_failure, ArtifactInputMismatchError):
        orchestrator._fail_put.assert_awaited_once()  # type: ignore[attr-defined]
        orchestrator._mark_replay_required.assert_not_awaited()  # type: ignore[attr-defined]
    else:
        orchestrator._mark_replay_required.assert_awaited_once()  # type: ignore[attr-defined]
        orchestrator._fail_put.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_startup_namespace_validation_uses_canonical_session_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    store = _UnavailableStore()

    class _TransactionContext:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> None:
            return None

    class _Session:
        def begin(self) -> _TransactionContext:
            return _TransactionContext()

    session = _Session()

    class _SessionContext:
        async def __aenter__(self) -> object:
            return session

        async def __aexit__(self, *_args: object) -> None:
            return None

    repository = object()
    ensured = AsyncMock()

    def create_repository(candidate_session: object) -> object:
        assert candidate_session is session
        return repository

    monkeypatch.setattr(
        artifact_service_module,
        "get_session_factory",
        lambda: lambda: _SessionContext(),
    )
    monkeypatch.setattr(artifact_service_module, "ArtifactRepository", create_repository)
    monkeypatch.setattr(
        artifact_service_module,
        "_claim_and_validate_storage_namespace",
        ensured,
    )

    claim = await validate_artifact_storage_namespace_at_startup(store, settings)
    assert isinstance(ensured.await_args.args[1], ArtifactStorageNamespaceSpec)
    assert ensured.await_args.args[0] is repository
    assert claim.namespace_identity == store.namespace_identity


def test_models_remove_v1_provider_retention_and_receipt_fields() -> None:
    assert not hasattr(ArtifactReplica, "retention_state")
    assert not hasattr(ArtifactReplica, "provider_artifact_id")
    assert not hasattr(ArtifactReplica, "provider_manifest_id")
    assert not hasattr(ArtifactOperationReceipt, "provider_receipt_id")
    assert not hasattr(ArtifactOperationReceipt, "retention_reference")
    assert not hasattr(ArtifactOperationReceipt, "service_principal")
    assert not hasattr(ArtifactUploadItem, "provider_operation_reference")
    assert hasattr(ArtifactReplica, "provider_object_ref")
    assert hasattr(ArtifactStorageNamespace, "namespace_fingerprint")
