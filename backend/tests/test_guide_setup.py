"""Focused coverage for same-generation guide preparation composition."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from app.interfaces.artifact_operations import (
    GuideSufficiencyMaterialRequest,
    GuideSufficiencyMaterialUnavailable,
)
from app.modules.artifacts.guide_setup import GuideSetupPreparationService, _VerifiedItem
from app.modules.artifacts.guide_extraction import GuideExtractionRegistry
from app.modules.artifacts.guide_extraction_service import (
    GuideExtractionCoordinator,
    GuideExtractionService,
)
from app.modules.artifacts.guide_materialization import (
    ArtifactMaterializationService,
    AuthorizedGuideExtractionMaterializer,
)
from app.modules.artifacts.guide_sufficiency_material import (
    SqlAlchemyGuideSufficiencyMaterialAdapter,
)
from app.modules.artifacts.models import (
    GuideSourceArtifactIncident,
    GuideSourceExtractionAttempt,
    GuideSourceFormatClassification,
)
_INCIDENT_ID = uuid4()


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


def test_guide_setup_service_composes_canonical_materialization_and_extraction() -> None:
    session_factory = object()
    service = GuideSetupPreparationService(
        session_factory, object(), object(), object()  # type: ignore[arg-type]
    )

    assert service._session_factory is session_factory
    assert isinstance(service._materialization, ArtifactMaterializationService)
    assert service._materialization._session_factory is session_factory
    assert isinstance(service._extraction, GuideExtractionCoordinator)
    assert isinstance(service._extraction._service, GuideExtractionService)
    assert service._extraction._service._session_factory is session_factory
    assert isinstance(service._extraction._service._registry, GuideExtractionRegistry)
    assert isinstance(
        service._extraction._materializer, AuthorizedGuideExtractionMaterializer
    )
    assert service._extraction._materializer._materialization is service._materialization


def test_project_setup_tasks_dispatch_exact_canonical_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    from app.workers import project_setup as project_setup_worker

    pre_submit = AsyncMock(return_value={"status": "policy_draft_ready"})
    post_submit = AsyncMock(return_value={"status": "completed"})
    monkeypatch.setattr(project_setup_worker, "_run_pre_submit_setup_pipeline", pre_submit)
    monkeypatch.setattr(project_setup_worker, "_run_post_submit_setup_continuation", post_submit)
    monkeypatch.setattr(
        project_setup_worker, "run_async_task", lambda factory: asyncio.run(factory())
    )

    assert project_setup_worker.run_pre_submit_setup_pipeline.run(
        "project", "guide", "snapshot", "run", 3
    ) == {"status": "policy_draft_ready"}
    pre_submit.assert_awaited_once_with("project", "guide", "snapshot", "run", 3)
    assert project_setup_worker.run_post_submit_setup_continuation.run(
        "project", "guide", "snapshot", "run", "effective", "checker"
    ) == {"status": "completed"}
    post_submit.assert_awaited_once_with(
        "project", "guide", "snapshot", "run", "effective", "checker"
    )


@pytest.mark.asyncio
async def test_verified_worker_stops_exactly_on_blocked_sufficiency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    from app.workers import project_setup as project_setup_worker

    engine = SimpleNamespace(dispose=AsyncMock())
    session = _Session()
    report = SimpleNamespace(status="blocked", id="report-id")
    service = SimpleNamespace(
        validate_project_setup_run_context=AsyncMock(),
        update_project_setup_run_status=AsyncMock(),
        run_verified_guide_sufficiency_agent=AsyncMock(return_value=(report, True)),
    )
    monkeypatch.setattr(
        project_setup_worker, "create_async_engine", lambda *_args, **_kwargs: engine
    )
    monkeypatch.setattr(
        project_setup_worker,
        "get_database_url",
        lambda: "postgresql+asyncpg://unused",
    )
    monkeypatch.setattr(
        project_setup_worker,
        "async_sessionmaker",
        lambda *_args, **_kwargs: _factory(session),
    )
    monkeypatch.setattr(
        project_setup_worker, "ProjectService", lambda *_args, **_kwargs: service
    )

    result = await project_setup_worker._run_verified_pre_submit_sufficiency_continuation(
        "project", "guide", "snapshot", "run", 3
    )

    assert result == {
        "status": "sufficiency_blocked",
        "guide_sufficiency_report_id": "report-id",
        "idempotent": False,
    }
    service.validate_project_setup_run_context.assert_awaited_once_with(
        "run",
        project_id="project",
        guide_id="guide",
        source_snapshot_id="snapshot",
        setup_generation=3,
    )
    service.run_verified_guide_sufficiency_agent.assert_awaited_once_with(
        project_setup_worker.project_setup_pipeline_actor(),
        "project",
        "guide",
        "snapshot",
        "run",
        3,
    )
    assert service.update_project_setup_run_status.await_args_list == [
        (("run",), {"status": "running_sufficiency_agent", "current_step": "guide_sufficiency"}),
        (
            ("run",),
            {
                "status": "sufficiency_blocked",
                "current_step": "guide_sufficiency",
                "output_sufficiency_report_id": "report-id",
            },
        ),
    ]
    engine.dispose.assert_awaited_once_with()


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
    assert materialization_request.project_id == ids[0]
    assert materialization_request.guide_id == ids[1]
    assert materialization_request.guide_source_snapshot_id == ids[2]
    assert materialization_request.binding_id == binding_id
    assert materialization_request.source_item_id == item.item_id
    assert materialization_request.project_setup_run_id == ids[3]
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("observed", "expected_code", "expected_incident_id", "queried_tables"),
    [
        (
            (SimpleNamespace(id=str(_INCIDENT_ID)),),
            "guide_artifact_incident",
            _INCIDENT_ID,
            (GuideSourceArtifactIncident.__tablename__,),
        ),
        (
            (None, SimpleNamespace(status="unsupported")),
            "guide_source_format_unsupported",
            None,
            (GuideSourceArtifactIncident.__tablename__, GuideSourceExtractionAttempt.__tablename__),
        ),
        (
            (None, None, SimpleNamespace(status="ambiguous")),
            "guide_source_format_ambiguous",
            None,
            (
                GuideSourceArtifactIncident.__tablename__,
                GuideSourceExtractionAttempt.__tablename__,
                GuideSourceFormatClassification.__tablename__,
            ),
        ),
        (
            (None, None, None),
            "guide_source_extraction_failed",
            None,
            (
                GuideSourceArtifactIncident.__tablename__,
                GuideSourceExtractionAttempt.__tablename__,
                GuideSourceFormatClassification.__tablename__,
            ),
        ),
    ],
)
async def test_sufficiency_failure_maps_exact_persisted_state(
    observed: tuple[object | None, ...],
    expected_code: str,
    expected_incident_id: object | None,
    queried_tables: tuple[str, ...],
) -> None:
    session = SimpleNamespace(scalar=AsyncMock(side_effect=observed))
    adapter = SqlAlchemyGuideSufficiencyMaterialAdapter(session)
    ids = [uuid4() for _ in range(4)]
    request = GuideSufficiencyMaterialRequest(
        project_id=ids[0],
        guide_id=ids[1],
        guide_source_snapshot_id=ids[2],
        project_setup_run_id=ids[3],
        setup_generation=4,
    )

    failure = await adapter._failure_for(request, str(uuid4()))

    assert isinstance(failure, GuideSufficiencyMaterialUnavailable)
    assert failure.code == expected_code
    assert failure.incident_id == expected_incident_id
    statements = tuple(str(call.args[0]) for call in session.scalar.await_args_list)
    assert len(statements) == len(queried_tables)
    for statement, table in zip(statements, queried_tables, strict=True):
        assert table in statement
