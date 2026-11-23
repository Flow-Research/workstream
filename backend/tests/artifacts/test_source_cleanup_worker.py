"""Scheduled cleanup composition with real custody, bytes and retry ownership."""
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text

from app.adapters.artifacts import source_cleanup_worker as composition
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.api.submission_cleanup import SubmissionSourceRemoval
from app.modules.artifacts.intake.repository import IntakeCustodyConflict
from tests.artifacts import test_submission_source_cleanup as cleanup_fixtures
from tests.artifacts.test_submission_intake_custody import repository, reserve
from tests.checkers.execution.support import service_link_state
from tests.test_artifact_admission import _settings
from tests.test_local_artifact_store import initialize_local_store, local_source_completion

intake = cleanup_fixtures.intake
capacity_limits = cleanup_fixtures.capacity_limits
provision_cleanup_identity = cleanup_fixtures.provision_cleanup_identity


def settings_for(intake):
    return _settings(intake.durable_root.parent).model_copy(update={
        "submission_source_cleanup_profile": {
            "maximum_candidates": 10, "lease_seconds": 30, "run_seconds": 60,
        },
    })


async def sealed_local_source(intake, *, terminal=True):
    store = initialize_local_store(root=intake.durable_root)
    try:
        async with intake.factory.begin() as session:
            row = await reserve(intake, session, with_upload=False)
            operation, lease = UUID(row.id), UUID(row.lease_id)
            intent = await repository(session).prepare_upload(
                operation, lease, 1, part_bytes=5 * 1024**2, idle_timeout_seconds=20.0)
        upload = await store.begin_source_upload(intent)
        async with intake.factory.begin() as session:
            await repository(session).record_upload(operation, lease, 1, upload=upload)
        completion = await local_source_completion(store, upload, b"worker-source")
        async with intake.factory.begin() as session:
            await repository(session).record_eof(operation, lease, 1, completion=completion)
        source = await store.complete_source_upload(completion)
        async with intake.factory.begin() as session:
            deadline = datetime.now(UTC) + timedelta(minutes=2)
            await repository(session).seal(operation, lease, 1, provider_generation=source.provider_generation,
                                          pre_deadline_at=deadline, lease_expires_at=deadline)
        if terminal:
            async with intake.factory.begin() as session:
                await repository(session).terminalize(operation, lease, 1, state="rejected", failure_code="pre_failed")
        return operation, source
    finally:
        store.close()


async def state(intake):
    async with intake.factory() as session:
        return tuple([await session.scalar(text(
            f"SELECT jsonb_agg(to_jsonb(r) ORDER BY to_jsonb(r)::text) FROM public.{table} r"
        )) for table in ("submission_intake_operations", "submission_source_charges",
                        "submission_source_cleanup_claims", "audit_events")])


async def test_sweep_reclaims_real_source_once_and_leaves_live_pre_input(intake):
    operation, source = await sealed_local_source(intake)
    settings = settings_for(intake)
    assert (await composition.sweep_sealed_submission_sources(intake.factory, settings))["candidates"] == 0
    await cleanup_fixtures.age_fixture(intake, operation, preserve_upload_deadline=True)
    live, protected = await sealed_local_source(intake, terminal=False)
    result = await composition.sweep_sealed_submission_sources(intake.factory, settings)
    assert result == {"candidates": 1, "confirmed": 1, "deferred": 0, "timed_out": False}
    after = await state(intake)
    for _ in range(2):
        assert (await composition.sweep_sealed_submission_sources(intake.factory, settings))["candidates"] == 0
        assert await state(intake) == after
    store = initialize_local_store(root=intake.durable_root)
    try:
        assert await store.observe_sealed_source(source) is None
        assert await store.observe_sealed_source(protected) is not None
    finally:
        store.close()
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges WHERE operation_id=:id"),
                                    {"id": operation}) == 0
        assert await session.scalar(text("SELECT state FROM submission_intake_operations WHERE id=:id"),
                                    {"id": live}) == "pre_checking"
        assert await session.scalar(text("SELECT count(*) FROM submission_source_cleanup_claims WHERE confirmed_at IS NOT NULL")) == 1


async def test_sweep_retains_uncertain_claim_then_recovers_under_new_generation(intake, monkeypatch):
    operation, source = await sealed_local_source(intake)
    await cleanup_fixtures.age_fixture(intake, operation, preserve_upload_deadline=True)
    settings = settings_for(intake).model_copy(update={"submission_source_cleanup_profile": {
        "maximum_candidates": 10, "lease_seconds": 30, "run_seconds": 60,
    }})
    async def uncertain_remove(self, candidate, upload):
        assert candidate == source
        async with intake.factory.begin() as session:
            await session.execute(text("SELECT id FROM workstream_tasks WHERE id=:id FOR UPDATE NOWAIT"), {"id": intake.task})
            assert await session.scalar(text("SELECT generation FROM submission_source_cleanup_claims WHERE operation_id=:id"),
                                        {"id": operation}) == 1
        return SubmissionSourceRemoval(candidate, False, False, False)
    with monkeypatch.context() as patch:
        from app.adapters.artifacts.source_cleanup import LocalSubmissionSourceCleanup
        patch.setattr(LocalSubmissionSourceCleanup, "remove", uncertain_remove)
        first = await composition.sweep_sealed_submission_sources(intake.factory, settings)
    assert first["deferred"] == 1 and first["confirmed"] == 0
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges WHERE operation_id=:id"),
                                    {"id": operation}) > 0
        remaining = await session.scalar(text("SELECT extract(epoch FROM lease_expires_at-clock_timestamp()) "
            "FROM submission_source_cleanup_claims WHERE operation_id=:id"), {"id": operation})
    assert remaining is not None, "uncertain removal must retain a committed cleanup claim"
    await asyncio.sleep(max(0, float(remaining)) + 0.05)
    assert (await composition.sweep_sealed_submission_sources(intake.factory, settings))["confirmed"] == 1
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT generation FROM submission_source_cleanup_claims WHERE operation_id=:id"),
                                    {"id": operation}) == 2


@pytest.mark.parametrize("denial", ["service", "namespace"])
async def test_sweep_denial_precedes_cleanup_provider_and_preserves_custody(intake, monkeypatch, denial):
    operation, _ = await sealed_local_source(intake)
    await cleanup_fixtures.age_fixture(intake, operation, preserve_upload_deadline=True)
    settings = settings_for(intake)
    if denial == "service":
        await service_link_state(intake.factory, ServiceIdentity.ARTIFACT_SOURCE_CLEANUP, active=False)
    else:
        foreign_root = intake.durable_root.parent / "foreign"
        foreign_root.mkdir(mode=0o700)
        settings = settings.model_copy(update={"artifact_local_root": foreign_root})
    def forbidden(**kwargs):
        pytest.fail("denied sweep constructed deletion capability")
    monkeypatch.setattr(composition, "create_submission_source_cleanup_provider", forbidden)
    before = await state(intake)
    from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
    from app.modules.authorization.runtime import AuthorizationDenied, PreparedAuthorizationUnsupported
    with pytest.raises((IntakeCustodyConflict, ArtifactAuthorityDeniedError, AuthorizationDenied, PreparedAuthorizationUnsupported)):
        await composition.sweep_sealed_submission_sources(intake.factory, settings)
    assert await state(intake) == before


async def test_concurrent_sweeps_release_charge_only_once(intake):
    operation, _ = await sealed_local_source(intake)
    await cleanup_fixtures.age_fixture(intake, operation, preserve_upload_deadline=True)
    results = await asyncio.gather(*(composition.sweep_sealed_submission_sources(
        intake.factory, settings_for(intake)) for _ in range(2)))
    assert sum(result["confirmed"] for result in results) == 1
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges WHERE operation_id=:id"),
                                    {"id": operation}) == 0
        assert await session.scalar(text("SELECT count(*) FROM submission_source_cleanup_claims WHERE confirmed_at IS NOT NULL")) == 1
