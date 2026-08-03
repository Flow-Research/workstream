"""Focused coverage for same-generation guide preparation composition."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from app.modules.artifacts.guide_setup import GuideSetupPreparationService, _VerifiedItem


class _ScalarResult:
    def __init__(self, values: list[str]) -> None:
        self._values = values

    def all(self) -> list[str]:
        return self._values


class _Session:
    def __init__(self, *, run: object | None = None, item_ids: list[str] | None = None) -> None:
        self.scalar = AsyncMock(return_value=run)
        self.scalars = AsyncMock(return_value=_ScalarResult(item_ids or []))

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    @asynccontextmanager
    async def begin(self):
        yield


def _factory(session: _Session):
    return lambda: session


@pytest.mark.asyncio
async def test_prepare_generation_rejects_missing_run_and_empty_snapshot() -> None:
    service = object.__new__(GuideSetupPreparationService)
    service._session_factory = _factory(_Session())
    ids = [uuid4() for _ in range(4)]
    assert not await service.prepare_generation(
        project_id=ids[0], guide_id=ids[1], source_snapshot_id=ids[2],
        setup_run_id=ids[3], setup_generation=1,
    )

    service._session_factory = _factory(_Session(run=object()))
    assert not await service.prepare_generation(
        project_id=ids[0], guide_id=ids[1], source_snapshot_id=ids[2],
        setup_run_id=ids[3], setup_generation=1,
    )


@pytest.mark.asyncio
async def test_prepare_generation_requires_every_verified_item() -> None:
    item_id = uuid4()
    service = object.__new__(GuideSetupPreparationService)
    service._session_factory = _factory(_Session(run=object(), item_ids=[str(item_id)]))
    service._verified_item = AsyncMock(return_value=None)
    service._prepare_item = AsyncMock()
    ids = [uuid4() for _ in range(4)]

    assert not await service.prepare_generation(
        project_id=ids[0], guide_id=ids[1], source_snapshot_id=ids[2],
        setup_run_id=ids[3], setup_generation=2,
    )
    service._prepare_item.assert_not_awaited()

    verified = _VerifiedItem(item_id, uuid4(), uuid4(), "a" * 64, 12)
    service._verified_item = AsyncMock(return_value=verified)
    assert await service.prepare_generation(
        project_id=ids[0], guide_id=ids[1], source_snapshot_id=ids[2],
        setup_run_id=ids[3], setup_generation=2,
    )
    service._prepare_item.assert_awaited_once_with(
        verified, project_id=ids[0], guide_id=ids[1], source_snapshot_id=ids[2],
        setup_run_id=ids[3], setup_generation=2,
    )


@pytest.mark.asyncio
async def test_verified_item_projects_repository_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    item_id = uuid4()
    candidate = SimpleNamespace(
        content_id=str(uuid4()), replica_id=str(uuid4()), sha256="b" * 64, byte_count=41
    )
    repository = SimpleNamespace(
        get_verified_guide_content_candidate=AsyncMock(return_value=candidate)
    )
    monkeypatch.setattr(
        "app.modules.artifacts.guide_setup.ArtifactRepository", lambda _session: repository
    )
    service = object.__new__(GuideSetupPreparationService)
    service._session_factory = _factory(_Session())

    projected = await service._verified_item(item_id)
    assert projected == _VerifiedItem(
        item_id, UUID(candidate.content_id), UUID(candidate.replica_id), candidate.sha256, 41
    )
    repository.get_verified_guide_content_candidate.assert_awaited_once_with(
        str(item_id), lock_replica=False
    )
    repository.get_verified_guide_content_candidate.return_value = None
    assert await service._verified_item(item_id) is None


@pytest.mark.asyncio
async def test_prepare_item_binds_materializes_and_extracts(monkeypatch: pytest.MonkeyPatch) -> None:
    ids = [uuid4() for _ in range(6)]
    item = _VerifiedItem(ids[4], ids[5], uuid4(), "c" * 64, 19)
    binding_id = uuid4()
    classification_id = uuid4()
    prepared_handle = object()
    authority = SimpleNamespace(prepare=AsyncMock(return_value=prepared_handle))
    authority_facts = object()
    facts_factory = Mock(return_value=authority_facts)
    binding_service = SimpleNamespace(
        bind_guide_source=AsyncMock(return_value=SimpleNamespace(binding_id=binding_id))
    )
    monkeypatch.setattr(
        "app.modules.artifacts.guide_setup.PreparedGuideSourceBindingAuthorization",
        lambda *_args, **_kwargs: authority,
    )
    monkeypatch.setattr(
        "app.modules.artifacts.guide_setup.GuideSourceBindingService",
        lambda *_args, **_kwargs: binding_service,
    )
    monkeypatch.setattr(
        "app.modules.artifacts.guide_setup.guide_source_binding_authority_facts",
        facts_factory,
    )
    service = object.__new__(GuideSetupPreparationService)
    service._session_factory = _factory(_Session())
    service._materialization = SimpleNamespace(
        materialize_guide_source=AsyncMock(
            return_value=SimpleNamespace(classification_id=classification_id)
        )
    )
    service._extraction = SimpleNamespace(extract=AsyncMock())

    await service._prepare_item(
        item, project_id=ids[0], guide_id=ids[1], source_snapshot_id=ids[2],
        setup_run_id=ids[3], setup_generation=3,
    )

    facts_factory.assert_called_once_with(
        project_id=ids[0], guide_id=ids[1], source_snapshot_id=ids[2],
        source_item_id=item.item_id, setup_run_id=ids[3], setup_generation=3,
        content_id=item.content_id, replica_id=item.replica_id,
        sha256=item.sha256, byte_count=item.byte_count,
    )
    assert authority.prepare.await_args.kwargs["facts"] is authority_facts
    binding_request = binding_service.bind_guide_source.await_args.args[0]
    assert binding_request.prepared_authorization is prepared_handle
    assert binding_request.project_id == ids[0]
    assert binding_request.guide_id == ids[1]
    assert binding_request.guide_source_snapshot_id == ids[2]
    assert binding_request.source_item_id == item.item_id
    assert binding_request.project_setup_run_id == ids[3]
    assert binding_request.setup_generation == 3
    assert binding_request.logical_role == "guide_source_original"
    assert binding_request.verified_content_id == item.content_id
    materialization_request = service._materialization.materialize_guide_source.await_args.args[0]
    assert materialization_request.binding_id == binding_id
    assert materialization_request.source_item_id == item.item_id
    assert materialization_request.setup_generation == 3
    extraction_request = service._extraction.extract.await_args.args[0]
    assert extraction_request.binding_id == binding_id
    assert extraction_request.classification_id == classification_id
    assert extraction_request.project_id == ids[0]
    assert extraction_request.guide_id == ids[1]
    assert extraction_request.source_snapshot_id == ids[2]
    assert extraction_request.source_item_id == item.item_id
    assert extraction_request.project_setup_run_id == ids[3]
    assert extraction_request.setup_generation == 3
