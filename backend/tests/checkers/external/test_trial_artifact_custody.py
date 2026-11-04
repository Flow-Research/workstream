"""Real trial owner and ART custody retain exact bytes across publication replay."""

import asyncio
import hashlib
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select, func, text, event

from app.adapters.artifacts import checker_output_binding, checker_output_storage
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.models import ArtifactPutAttempt, ArtifactBinding
from app.modules.artifacts.preparation import HARD_MAXIMUM_ARTIFACT_BYTES
from app.modules.checkers.api.output_custody import CheckerOutputUnavailable
from app.modules.checkers.api.trial_evidence import (
    TrialEvidenceArtifactRequest,
    TrialEvidenceBindingRequest,
    TrialEvidenceSelector,
    TrialEvidenceUnavailable,
)
from app.modules.checkers.models import CheckerTrialEvidence
from tests.checkers.execution.support import (
    ControlledSelectedExecution,
    live_executor,
    reserve,
    provision_post_submit_service,
)
from tests.checkers.external.test_trial_evidence import _owner, _subject, _trial_fixture
from tests.checkers.external.test_revision_materialization import DiagnosticMaterialization
from tests.post_submit_materialization_helpers import material_fixture
from tests.test_checker_materialization import _limits


async def _bytes(value):
    """Stream one bounded receipt without exposing provider coordinates."""
    yield value


class PublishingExecution(ControlledSelectedExecution):
    """Use real owner authorization, storage admission, verification and binding."""

    def __init__(self, harness, catalog, projected):
        super().__init__()
        self.h, self.catalog, self.projected = harness, catalog, projected
        self.ack = None

    async def execute(self, request, grant):
        h = self.h

        def reservations(session):
            return _owner(session, request, self.catalog)

        async with h.factory() as session, session.begin():
            ticket = await reservations(session).reserve(_subject(request, self.projected))
        data = b'{"trial":"retained-original"}'
        selector = TrialEvidenceSelector(
            trial_evidence_id=ticket.trial_evidence_id,
            project_id=request.identity.project_id,
            content_sha256="sha256:" + hashlib.sha256(data).hexdigest(),
        )
        outputs = checker_output_storage(
            sessions=h.factory,
            store=h.store.wrapped,
            namespace=h.namespace,
            preparation=h.preparation,
            settings=h.settings,
            reservations=reservations,
        )
        # Probing an unfinished reservation must commit without pinning content.
        assert await outputs.recover_trial_evidence(selector) is None
        async with h.factory() as session:
            row = await session.get(CheckerTrialEvidence, str(ticket.trial_evidence_id))
            assert row.content_sha256 is None
        with pytest.raises(CheckerOutputUnavailable, match="checker_output_authority_unavailable"):
            await outputs.store_trial_evidence(
                TrialEvidenceArtifactRequest(selector, _bytes(b"{}"))
            )
        async with h.factory() as session:
            row = await session.get(CheckerTrialEvidence, str(ticket.trial_evidence_id))
            assert row.content_sha256 is None
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ArtifactPutAttempt)
                    .where(
                        ArtifactPutAttempt.checker_trial_evidence_id
                        == str(ticket.trial_evidence_id),
                    )
                )
                == 0
            )
        stored = await outputs.store_trial_evidence(
            TrialEvidenceArtifactRequest(selector, _bytes(data))
        )
        assert stored.status == "verified" and not stored.replayed
        # The caller lost its storage response: recover instead of regenerating.
        recovered = await outputs.recover_trial_evidence(selector)
        assert recovered.put_attempt_id == stored.put_attempt_id and recovered.replayed
        binding_request = TrialEvidenceBindingRequest(
            selector,
            stored.put_attempt_id,
            stored.verification_receipt_id,
        )
        async with h.factory() as session, session.begin():
            ack = await checker_output_binding(
                session,
                namespace=h.namespace,
                reservations=reservations(session),
            ).bind_trial_evidence(binding_request)
        assert not ack.replayed
        assert await outputs.read_trial_evidence(selector, ack) == data
        async with h.factory() as session, session.begin():
            replay = await checker_output_binding(
                session,
                namespace=h.namespace,
                reservations=reservations(session),
            ).bind_trial_evidence(binding_request)
        assert replay.replayed and replay.binding_id == ack.binding_id
        with pytest.raises(CheckerOutputUnavailable):
            await outputs.read_trial_evidence(
                selector, ack.model_copy(update={"owner_digest": "sha256:" + "f" * 64})
            )
        async with h.factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ArtifactBinding)
                    .where(
                        ArtifactBinding.resource_type == "checker_trial_evidence",
                        ArtifactBinding.resource_id == str(ticket.trial_evidence_id),
                    )
                )
                == 1
            )
        self.ack = ack
        return await super().execute(request, grant)


async def test_trial_bytes_use_real_art_custody_and_recover_exact_original(
    tmp_path,
    isolated_database_env,
):
    """A failed admission rolls back the pin; verified replay never duplicates effects."""
    from tests.test_s3_artifact_store import provision_minio_bucket

    await provision_minio_bucket.__wrapped__()
    spec, parameters, projected, catalog_for = _trial_fixture()
    async with material_fixture(
        tmp_path,
        isolated_database_env,
        provider="minio",
        post_submit_registry_spec=spec,
        post_submit_configuration_setup=parameters,
        scratch_limits=_limits(
            # Input material remains reserved while ART prepares the output.
            # Use the production aggregate budget for this composed journey.
            aggregate_reserved_bytes=4 * HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=4,
            maximum_concurrency=4,
            total_deadline_seconds=120.0,
            reservation_ttl_seconds=150.0,
        ),
    ) as h:
        catalog = catalog_for(h.request)
        await provision_post_submit_service(h.factory, ServiceIdentity.ARTIFACT_CHECKER_OUTPUT)
        await reserve(h)
        h.service = DiagnosticMaterialization(h.service)
        adapter = PublishingExecution(h, catalog, projected)
        result = await live_executor(h, selected_execution=adapter).evaluate_post_submission(
            h.request
        )
        assert result.outcome == "completed", result.model_dump_json()
        assert adapter.ack is not None
        assert list((h.scratch / "workspaces").iterdir()) == []
        assert not h.preparation._active


class CompetingPublication(ControlledSelectedExecution):
    """Observe a real lock wait while the first publisher's pin is uncommitted."""

    def __init__(self, harness, catalog, projected, rollback):
        super().__init__()
        self.h, self.catalog, self.projected = harness, catalog, projected
        self.rollback = rollback

    async def execute(self, request, grant):
        h = self.h
        pinned, release, contending = asyncio.Event(), asyncio.Event(), asyncio.Event()
        pids = {}
        async with h.factory() as session, session.begin():
            ticket = await _owner(session, request, self.catalog).reserve(
                _subject(request, self.projected)
            )
        first_data, second_data = b'{"trial":"first"}', b'{"trial":"second"}'

        def selector(data):
            return TrialEvidenceSelector(
                trial_evidence_id=ticket.trial_evidence_id,
                project_id=request.identity.project_id,
                content_sha256="sha256:" + hashlib.sha256(data).hexdigest(),
            )

        catalog = self.catalog

        class ObservedOwner:
            def __init__(self, session, label):
                self.session, self.label = session, label
                self.owner = _owner(session, request, catalog)

            async def resolve(self, selected):
                return await self.owner.resolve(selected)

            async def pin_content(self, selected):
                resolved = await self.owner.pin_content(selected)
                if self.label == "first":
                    pids[self.label] = await self.session.scalar(text("SELECT pg_backend_pid()"))
                    pinned.set()
                    await release.wait()
                return resolved

        def output(label):
            @asynccontextmanager
            async def sessions():
                async with h.factory() as session:
                    if label == "second":
                        # AUTH custody precedes the trial owner. Observe the
                        # actual connection before AUTH can itself block.
                        def began(_session, _transaction, connection):
                            pids[label] = connection.exec_driver_sql(
                                "SELECT pg_backend_pid()"
                            ).scalar()
                            contending.set()

                        event.listen(session.sync_session, "after_begin", began)
                    yield session

            return checker_output_storage(
                sessions=sessions,
                store=h.store.wrapped,
                namespace=h.namespace,
                preparation=h.preparation,
                settings=h.settings,
                reservations=lambda session: ObservedOwner(session, label),
            )

        first = asyncio.create_task(
            output("first").store_trial_evidence(
                TrialEvidenceArtifactRequest(
                    selector(first_data),
                    _bytes(b"{}" if self.rollback else first_data),
                ),
            )
        )
        second = None
        try:
            await asyncio.wait_for(pinned.wait(), 15)
            second = asyncio.create_task(
                output("second").store_trial_evidence(
                    TrialEvidenceArtifactRequest(selector(second_data), _bytes(second_data)),
                )
            )
            await asyncio.wait_for(contending.wait(), 5)
            async with asyncio.timeout(10):
                async with h.factory() as observer:
                    while not await observer.scalar(
                        text("SELECT :holder = ANY(pg_blocking_pids(:contender))"),
                        {"holder": pids["first"], "contender": pids["second"]},
                    ):
                        assert not second.done(), "publisher escaped the uncommitted pin"
                        await asyncio.sleep(0.02)
            release.set()
            if self.rollback:
                with pytest.raises(
                    CheckerOutputUnavailable, match="checker_output_authority_unavailable"
                ):
                    await asyncio.wait_for(first, 30)
                stored = await asyncio.wait_for(second, 30)
                winning_data = second_data
            else:
                stored = await asyncio.wait_for(first, 30)
                with pytest.raises(TrialEvidenceUnavailable, match="trial_content_conflict"):
                    await asyncio.wait_for(second, 30)
                winning_data = first_data
            assert stored.status == "verified"
            async with h.factory() as session:
                retained = await session.get(CheckerTrialEvidence, str(ticket.trial_evidence_id))
                assert retained.content_sha256 == selector(winning_data).content_sha256
                attempts = (
                    await session.scalars(
                        select(ArtifactPutAttempt).where(
                            ArtifactPutAttempt.checker_trial_evidence_id
                            == str(ticket.trial_evidence_id),
                        )
                    )
                ).all()
                assert len(attempts) == 1
                assert attempts[0].id == str(stored.put_attempt_id)
        finally:
            release.set()
            pending = [item for item in (first, second) if item is not None]
            for item in pending:
                if not item.done():
                    item.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        return await super().execute(request, grant)


@pytest.mark.parametrize("rollback", [False, True], ids=["committed-pin", "rolled-back-pin"])
async def test_competing_trial_publication_observes_pin_commit_or_complete_rollback(
    tmp_path,
    isolated_database_env,
    rollback,
):
    """One exact content wins; an aborted first admission leaves no partial effects."""
    from tests.test_s3_artifact_store import provision_minio_bucket

    await provision_minio_bucket.__wrapped__()
    spec, parameters, projected, catalog_for = _trial_fixture()
    async with material_fixture(
        tmp_path,
        isolated_database_env,
        provider="minio",
        post_submit_registry_spec=spec,
        post_submit_configuration_setup=parameters,
        scratch_limits=_limits(
            aggregate_reserved_bytes=4 * HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=4,
            maximum_concurrency=4,
            total_deadline_seconds=120.0,
            reservation_ttl_seconds=150.0,
        ),
    ) as h:
        catalog = catalog_for(h.request)
        await provision_post_submit_service(h.factory, ServiceIdentity.ARTIFACT_CHECKER_OUTPUT)
        await reserve(h)
        h.service = DiagnosticMaterialization(h.service)
        adapter = CompetingPublication(h, catalog, projected, rollback)
        result = await live_executor(h, selected_execution=adapter).evaluate_post_submission(
            h.request
        )
        assert result.outcome == "completed", result.model_dump_json()
        assert list((h.scratch / "workspaces").iterdir()) == []
        assert not h.preparation._active


@pytest.fixture
def composition_trial_summary(monkeypatch):
    """Load the canonical fixture owner without executing its native case."""
    import importlib.util
    from pathlib import Path

    tests = (
        Path(__file__).resolve().parents[4]
        / "external_checkers/workstream-checker-service/tests"
    )
    monkeypatch.syspath_prepend(str(tests))
    spec = importlib.util.spec_from_file_location(
        "composition_custody_fixture", tests / "terminal_systems_smol_composition.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._retained_trial_summary


def _composition_custody_rows(count):
    """Synthetic query rows exercise the fixture verifier, not ART publication."""
    from types import SimpleNamespace
    from uuid import uuid4
    from app.modules.checkers.api.external import external_checker_json_hash

    rows, retained, receipts = [], [], []
    for index in range(count):
        receipt = {
            "originating_identity": {"requirement_id": f"requirement_{index}"},
            "execution": {
                "build": {"candidate_image_digest": None, "candidate_archive_digest": None},
                "steps": [{"slot_id": "verification", "outcome": "exit_nonzero"}],
            },
        }
        item = SimpleNamespace(
            id=str(uuid4()), project_id=str(uuid4()),
            content_sha256=external_checker_json_hash(receipt), address_digest="sha256:" + "a" * 64,
        )
        binding = SimpleNamespace(
            id=str(uuid4()), resource_id=item.id, project_id=item.project_id,
            scope_version=1, supersedes_binding_id=None,
            put_attempt_id=str(uuid4()), verification_receipt_id=str(uuid4()),
        )
        content = SimpleNamespace(id=str(uuid4()), sha256=item.content_sha256,
                                  byte_count=100, media_type="application/json")
        attempt = SimpleNamespace(checker_trial_evidence_id=item.id,
                                  status="object_confirmed", checker_output_custody_sealed=True,
                                  sha256=item.content_sha256, byte_count=100, media_type="application/json")
        verification = SimpleNamespace(outcome="verified", observed_sha256=item.content_sha256,
                                       observed_byte_count=100)
        rows.append((binding, content, attempt, verification))
        retained.append(item)
        receipts.append(receipt)
    return rows, retained, receipts


@pytest.mark.parametrize("count", [1, 2])
async def test_composition_custody_matches_selected_one_or_two_trials(composition_trial_summary, count):
    from unittest.mock import AsyncMock

    rows, retained, receipts = _composition_custody_rows(count)
    summary = await composition_trial_summary(
        AsyncMock(execute=AsyncMock(return_value=rows)), retained, receipts, expected_count=count
    )
    assert len(summary) == count
    assert {item["trial_evidence_id"] for item in summary} == {item.id for item in retained}


@pytest.mark.parametrize("expected_count", [0, 2])
async def test_composition_custody_refuses_invalid_or_missing_selected_count(
    composition_trial_summary, expected_count
):
    from unittest.mock import AsyncMock

    rows, retained, receipts = _composition_custody_rows(1)
    with pytest.raises(AssertionError):
        await composition_trial_summary(
            AsyncMock(execute=AsyncMock(return_value=rows)), retained, receipts,
            expected_count=expected_count,
        )


async def test_composition_custody_count_requires_verified_content(composition_trial_summary):
    from unittest.mock import AsyncMock

    rows, retained, receipts = _composition_custody_rows(1)
    rows[0][3].outcome = "unavailable"
    with pytest.raises(AssertionError):
        await composition_trial_summary(
            AsyncMock(execute=AsyncMock(return_value=rows)), retained, receipts, expected_count=1
        )
