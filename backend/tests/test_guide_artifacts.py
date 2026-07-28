"""Focused proof for hidden guide-source byte ingest."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.adapters.artifacts import get_guide_artifact_ingest_command
from app.core.config import Settings
from app.interfaces.artifact_operations import GuideArtifactIngestRequest
from app.modules.artifacts.preparation import (
    HARD_MAXIMUM_ARTIFACT_BYTES,
    ArtifactPreparationLimits,
    ArtifactPreparationService,
    ArtifactScratchManager,
)
from app.modules.artifacts.schemas import (
    ArtifactAdmissionResult,
    ArtifactAuthorityDeniedError,
    DenyArtifactInternalAuthority,
    GuideArtifactIngestAuthorityFacts,
)
from app.modules.artifacts.authorization import DenyGuideArtifactPreparedAuthorization
from app.modules.artifacts.authorization import get_artifact_authorization_context
from app.modules.artifacts.service import (
    ArtifactStorageOrchestrator,
    GuideArtifactIngestService,
    PreparedGuideArtifactIngestCommand,
    _artifact_admission_transaction,
)
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.projects.router import ingest_guide_source_artifact
from app.modules.projects.router import router as projects_router


async def _bytes(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


def _context() -> HumanAuthorizationContext:
    return HumanAuthorizationContext(
        actor_kind=ActorKind.HUMAN,
        actor_profile_id=uuid4(),
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )


def _preparation(tmp_path: Path) -> tuple[ArtifactPreparationService, ArtifactScratchManager]:
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=2 * HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=2,
            maximum_concurrency=2,
            minimum_free_bytes=0,
            reservation_ttl_seconds=30,
            total_deadline_seconds=10,
            cleanup_margin_seconds=5,
            stream_buffer_bytes=3,
            maximum_source_bytes=64,
        ),
    )
    return ArtifactPreparationService(manager), manager


class _AllowPreparedAuthority:
    def __init__(self) -> None:
        self.intakes: list[tuple[UUID, UUID, UUID, UUID]] = []
        self.admissions: list[GuideArtifactIngestAuthorityFacts] = []
        self.context = _context()
        self.handle = object.__new__(PreparedAuthorizationHandle)
        self.closed = False
        self.transaction_active = False
        self.transaction_committed = False

    @asynccontextmanager
    async def transaction(self):
        assert not self.transaction_active
        self.transaction_active = True
        try:
            yield
        finally:
            self.transaction_active = False
            self.transaction_committed = True

    async def prepare(self, **values: Any) -> PreparedAuthorizationHandle:
        assert self.transaction_active
        self.intakes.append(
            (
                values["project_id"],
                values["guide_id"],
                values["guide_source_snapshot_id"],
                values["guide_source_item_id"],
            )
        )
        return self.handle

    async def consume(self, **values: Any) -> UUID:
        assert self.transaction_active
        assert values["prepared_authorization"] is self.handle
        self.admissions.append(values["facts"])
        return self.context.actor_profile_id

    def close(self) -> None:
        self.closed = True


class _FailCommitAuthority(_AllowPreparedAuthority):
    @asynccontextmanager
    async def transaction(self):
        assert not self.transaction_active
        self.transaction_active = True
        try:
            yield
        except BaseException:
            raise
        else:
            raise RuntimeError("PREP commit failed")
        finally:
            self.transaction_active = False


class _Admission:
    def __init__(
        self,
        *,
        authority: _AllowPreparedAuthority | None = None,
        replayed: bool = False,
        drift: bool = False,
    ) -> None:
        self.authority = authority
        self.replayed = replayed
        self.drift = drift
        self.source = None

    async def admit(
        self,
        request: Any,
        *,
        guide_prepared_authorization: Any,
        prepared_authorization: PreparedAuthorizationHandle,
        existing_transaction: bool,
    ):
        assert existing_transaction
        if self.authority is not None:
            assert self.authority.transaction_active
        self.source = request.source
        commitment = request.source.commitment
        if self.drift:
            raise RuntimeError("guide source request does not match canonical lineage")
        await guide_prepared_authorization.consume(
            prepared_authorization=prepared_authorization,
            facts=GuideArtifactIngestAuthorityFacts(
                project_id=uuid4() if self.drift else PROJECT_ID,
                guide_id=GUIDE_ID,
                guide_source_snapshot_id=SNAPSHOT_ID,
                guide_source_item_id=ITEM_ID,
                operation_identity=request.operation_identity,
                request_digest=request.request_digest,
                sha256=commitment.sha256,
                byte_count=commitment.byte_count,
                media_type=commitment.media_type,
            ),
        )
        return ArtifactAdmissionResult(
            attempt_id=ATTEMPT_ID,
            status="prepared",
            operation_identity="operation",
            request_digest="request",
            charge_ids=(uuid4(),),
            replayed=self.replayed,
        )


class _Orchestrator:
    def __init__(
        self,
        *,
        authority: _AllowPreparedAuthority | None = None,
        resolution: str = "stale",
    ) -> None:
        self.authority = authority
        self.resolution = resolution
        self.puts = 0
        self.resolutions = 0

    async def resolve_put_attempt(self, _attempt_id: UUID) -> str:
        if self.authority is not None:
            assert self.authority.transaction_committed
            assert not self.authority.transaction_active
        self.resolutions += 1
        return self.resolution

    async def resume_committed_put(self, *, attempt_id: UUID, source: Any) -> str:
        status = await self.resolve_put_attempt(attempt_id)
        if status == "missing":
            return await self.execute_committed_put(attempt_id=attempt_id, source=source)
        return status

    async def execute_committed_put(self, *, attempt_id: UUID, source: Any) -> str:
        if self.authority is not None:
            assert self.authority.transaction_committed
            assert not self.authority.transaction_active
        assert attempt_id == ATTEMPT_ID
        assert source.commitment.sha256.startswith("sha256:")
        self.puts += 1
        return "stored_pending_verification"


class _UnavailableCommand:
    async def ingest(self, **_values: Any):
        raise ArtifactAuthorityDeniedError("unavailable")


class _MustNotCallCommand:
    def __init__(self) -> None:
        self.called = False

    async def ingest(self, **_values: Any):
        self.called = True
        raise AssertionError("ingest command must not run for invalid request metadata")


class _TransactionSession:
    @asynccontextmanager
    async def begin(self):
        yield


class _PutAttemptRepository:
    def __init__(self, status: str | None) -> None:
        self.status = status

    async def lock_put_attempt(self, _attempt_id: str):
        if self.status is None:
            return None
        return SimpleNamespace(status=self.status)


PROJECT_ID = uuid4()
GUIDE_ID = uuid4()
SNAPSHOT_ID = uuid4()
ITEM_ID = uuid4()
ATTEMPT_ID = uuid4()


def _service(
    preparation: ArtifactPreparationService,
    admission: _Admission,
    orchestrator: _Orchestrator,
    authority: Any,
) -> GuideArtifactIngestService:
    @asynccontextmanager
    async def runtime():
        yield preparation, admission, orchestrator

    return GuideArtifactIngestService(runtime, authority)


@pytest.mark.asyncio
async def test_guide_ingest_denies_before_reading_bytes(tmp_path: Path) -> None:
    preparation, manager = _preparation(tmp_path)
    read = False

    async def source() -> AsyncIterator[bytes]:
        nonlocal read
        read = True
        yield b"must not be read"

    authority = DenyGuideArtifactPreparedAuthorization()
    command = PreparedGuideArtifactIngestCommand(
        _service(
            preparation,
            _Admission(),
            _Orchestrator(),
            authority,
        ),
        authority,
    )
    try:
        with pytest.raises(ArtifactAuthorityDeniedError):
            await command.ingest(
                authorization_context=_context(),
                project_id=PROJECT_ID,
                guide_id=GUIDE_ID,
                guide_source_snapshot_id=SNAPSHOT_ID,
                source_item_id=ITEM_ID,
                idempotency_key=uuid4(),
                byte_source=source(),
            )
        assert not read
        assert preparation.pending_cleanup_count == 0
    finally:
        manager.close()


@pytest.mark.asyncio
async def test_guide_ingest_uses_server_commitment_and_existing_put_path(
    tmp_path: Path,
) -> None:
    preparation, manager = _preparation(tmp_path)
    authority = _AllowPreparedAuthority()
    admission = _Admission(authority=authority)
    orchestrator = _Orchestrator(authority=authority)
    service = _service(
        preparation,
        admission,
        orchestrator,
        authority,
    )
    try:
        command = PreparedGuideArtifactIngestCommand(service, authority)
        result = await command.ingest(
            authorization_context=authority.context,
            project_id=PROJECT_ID,
            guide_id=GUIDE_ID,
            guide_source_snapshot_id=SNAPSHOT_ID,
            source_item_id=ITEM_ID,
            idempotency_key=uuid4(),
            byte_source=_bytes(b"guide ", b"bytes"),
        )
        assert result.sha256 == authority.admissions[0].sha256
        assert result.byte_count == 11
        assert result.status == "stored_pending_verification"
        assert orchestrator.puts == 1
        assert orchestrator.resolutions == 0
        assert authority.intakes == [(PROJECT_ID, GUIDE_ID, SNAPSHOT_ID, ITEM_ID)]
        assert authority.closed
        assert preparation.pending_cleanup_count == 0
    finally:
        manager.close()


@pytest.mark.asyncio
async def test_guide_ingest_rejects_invalid_logical_role_before_preparation(
    tmp_path: Path,
) -> None:
    preparation, manager = _preparation(tmp_path)
    authority = _AllowPreparedAuthority()
    service = _service(preparation, _Admission(), _Orchestrator(), authority)
    read = False

    async def source() -> AsyncIterator[bytes]:
        nonlocal read
        read = True
        yield b"must not be prepared"

    request = GuideArtifactIngestRequest(
        prepared_authorization=authority.handle,
        project_id=PROJECT_ID,
        guide_id=GUIDE_ID,
        guide_source_snapshot_id=SNAPSHOT_ID,
        source_item_id=ITEM_ID,
        operation_identity="operation",
        request_digest="sha256:" + "a" * 64,
        logical_role="not-guide-source",
        media_type="application/octet-stream",
        byte_source=source(),
    )
    try:
        with pytest.raises(Exception, match="logical role is invalid"):
            await service.prepare_and_admit(request, preparation, _Admission())
        assert not read
        assert preparation.pending_cleanup_count == 0
    finally:
        manager.close()


@pytest.mark.asyncio
async def test_guide_ingest_cleans_prepared_bytes_when_prep_commit_fails(
    tmp_path: Path,
) -> None:
    preparation, manager = _preparation(tmp_path)
    authority = _FailCommitAuthority()
    orchestrator = _Orchestrator(authority=authority)
    command = PreparedGuideArtifactIngestCommand(
        _service(preparation, _Admission(authority=authority), orchestrator, authority),
        authority,
    )
    try:
        with pytest.raises(RuntimeError, match="PREP commit failed"):
            await command.ingest(
                authorization_context=authority.context,
                project_id=PROJECT_ID,
                guide_id=GUIDE_ID,
                guide_source_snapshot_id=SNAPSHOT_ID,
                source_item_id=ITEM_ID,
                idempotency_key=uuid4(),
                byte_source=_bytes(b"prepared then rolled back"),
            )
        assert orchestrator.puts == 0
        assert authority.closed
        assert preparation.pending_cleanup_count == 0
    finally:
        manager.close()


@pytest.mark.asyncio
async def test_exact_replay_observes_without_second_provider_put(tmp_path: Path) -> None:
    preparation, manager = _preparation(tmp_path)
    authority = _AllowPreparedAuthority()
    orchestrator = _Orchestrator(authority=authority, resolution="stale")
    service = _service(
        preparation,
        _Admission(authority=authority, replayed=True),
        orchestrator,
        authority,
    )
    try:
        result = await PreparedGuideArtifactIngestCommand(service, authority).ingest(
            authorization_context=authority.context,
            project_id=PROJECT_ID,
            guide_id=GUIDE_ID,
            guide_source_snapshot_id=SNAPSHOT_ID,
            source_item_id=ITEM_ID,
            idempotency_key=uuid4(),
            byte_source=_bytes(b"same bytes"),
        )
        assert result.replayed
        assert result.status == "stale"
        assert orchestrator.resolutions == 1
        assert orchestrator.puts == 0
    finally:
        manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("persisted_status", "resolved_status", "expected_status", "expected_execute"),
    [
        ("absent_replay_required", "unused", "stored_pending_verification", 1),
        (None, "missing", "stored_pending_verification", 1),
        ("ambiguous", "stale", "stale", 0),
    ],
)
async def test_committed_put_replay_uses_persisted_resolution(
    persisted_status: str | None,
    resolved_status: str,
    expected_status: str,
    expected_execute: int,
) -> None:
    """Exercise the production replay selector for absent, missing, and resolved puts."""
    orchestrator = object.__new__(ArtifactStorageOrchestrator)
    orchestrator._session = _TransactionSession()  # type: ignore[attr-defined]
    orchestrator._repo = _PutAttemptRepository(persisted_status)  # type: ignore[attr-defined]
    executed = 0

    async def execute_committed_put(*, attempt_id: UUID, source: Any) -> str:
        nonlocal executed
        assert attempt_id == ATTEMPT_ID
        assert source == "source"
        executed += 1
        return "stored_pending_verification"

    async def resolve_put_attempt(attempt_id: UUID) -> str:
        assert attempt_id == ATTEMPT_ID
        return resolved_status

    orchestrator.execute_committed_put = execute_committed_put  # type: ignore[method-assign]
    orchestrator.resolve_put_attempt = resolve_put_attempt  # type: ignore[method-assign]

    result = await orchestrator.resume_committed_put(
        attempt_id=ATTEMPT_ID,
        source="source",  # type: ignore[arg-type]
    )

    assert result == expected_status
    assert executed == expected_execute


@pytest.mark.asyncio
async def test_existing_guide_admission_requires_active_root_transaction() -> None:
    """Fail closed when a PREP handle has no issuer-owned transaction to consume in."""
    session = SimpleNamespace(
        sync_session=SimpleNamespace(get_transaction=lambda: None),
        in_nested_transaction=lambda: False,
    )

    with pytest.raises(
        ArtifactAuthorityDeniedError,
        match="prepared authorization transaction is unavailable",
    ):
        async with _artifact_admission_transaction(session, existing=True):  # type: ignore[arg-type]
            pytest.fail("an unavailable PREP transaction must not admit bytes")


@pytest.mark.asyncio
async def test_canonical_lineage_drift_stops_before_provider_io(tmp_path: Path) -> None:
    preparation, manager = _preparation(tmp_path)
    authority = _AllowPreparedAuthority()
    orchestrator = _Orchestrator(authority=authority)
    service = _service(
        preparation,
        _Admission(authority=authority, drift=True),
        orchestrator,
        authority,
    )
    try:
        with pytest.raises(Exception, match="canonical lineage"):
            await PreparedGuideArtifactIngestCommand(service, authority).ingest(
                authorization_context=authority.context,
                project_id=PROJECT_ID,
                guide_id=GUIDE_ID,
                guide_source_snapshot_id=SNAPSHOT_ID,
                source_item_id=ITEM_ID,
                idempotency_key=uuid4(),
                byte_source=_bytes(b"guide"),
            )
        assert orchestrator.puts == 0
        assert preparation.pending_cleanup_count == 0
    finally:
        manager.close()


def test_hidden_guide_ingest_route_is_not_in_openapi() -> None:
    route = next(
        route
        for route in projects_router.routes
        if getattr(route, "name", None) == "ingest_guide_source_artifact"
    )
    assert route.include_in_schema is False


@pytest.mark.asyncio
async def test_production_composition_denies_before_disabled_runtime_is_opened() -> None:
    request = Request({"type": "http", "method": "POST", "path": "/hidden", "headers": []})
    request.scope["app"] = type("App", (), {"state": type("State", (), {})()})()
    request.app.state.settings = Settings()
    command = get_guide_artifact_ingest_command(
        request,
        object(),  # type: ignore[arg-type]
        DenyGuideArtifactPreparedAuthorization(),
        DenyArtifactInternalAuthority(),
    )
    with pytest.raises(ArtifactAuthorityDeniedError):
        await command.ingest(
            authorization_context=_context(),
            project_id=PROJECT_ID,
            guide_id=GUIDE_ID,
            guide_source_snapshot_id=SNAPSHOT_ID,
            source_item_id=ITEM_ID,
            idempotency_key=uuid4(),
            byte_source=_bytes(b"never read"),
        )


@pytest.mark.asyncio
async def test_hidden_http_route_conceals_fail_closed_authority() -> None:
    body_read = False

    async def receive() -> dict[str, object]:
        nonlocal body_read
        body_read = True
        return {"type": "http.request", "body": b"secret", "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/hidden",
            "headers": [],
        },
        receive,
    )
    with pytest.raises(HTTPException) as denied:
        await ingest_guide_source_artifact(
            project_id=str(PROJECT_ID),
            guide_id=str(GUIDE_ID),
            source_snapshot_id=str(SNAPSHOT_ID),
            source_item_id=str(ITEM_ID),
            request=request,
            context=_context(),
            ingest=_UnavailableCommand(),  # type: ignore[arg-type]
            idempotency_key=str(uuid4()),
        )
    assert denied.value.status_code == 404
    assert not body_read


@pytest.mark.asyncio
@pytest.mark.parametrize("idempotency_key", [None, "not-a-uuid"])
async def test_hidden_http_route_conceals_invalid_idempotency_key(
    idempotency_key: str | None,
) -> None:
    app = FastAPI()
    app.include_router(projects_router)
    app.dependency_overrides[get_artifact_authorization_context] = _context
    command = _MustNotCallCommand()
    app.dependency_overrides[get_guide_artifact_ingest_command] = lambda: command
    headers = {} if idempotency_key is None else {"Idempotency-Key": idempotency_key}
    path = (
        f"/projects/{PROJECT_ID}/guides/{GUIDE_ID}/source-snapshots/"
        f"{SNAPSHOT_ID}/items/{ITEM_ID}/artifact"
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(path, headers=headers, content=b"never read")
    assert response.status_code == 404
    assert not command.called
