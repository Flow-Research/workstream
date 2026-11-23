"""Real unsealed charge release, Local tombstones and uncertain completion retention."""
import os
import time
import json
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.adapters.artifacts import source_cleanup_worker as composition
from app.interfaces.artifacts import ArtifactPreconditionFailedError
from tests.artifacts.test_source_cleanup_worker import settings_for
from tests.artifacts.test_submission_intake_custody import repository, reserve
from tests.artifacts.test_submission_source_cleanup import (
    intake as intake, capacity_limits as capacity_limits,
    provision_cleanup_identity as provision_cleanup_identity, age_fixture,
)
from tests.test_local_artifact_store import initialize_local_store, local_source_completion


async def unfinished(intake, phase, *, old_bytes=True):
    store = initialize_local_store(root=intake.durable_root)
    upload = completion = source = intent = None
    try:
        async with intake.factory.begin() as session:
            row = await reserve(intake, session, with_upload=False)
            operation, lease = UUID(row.id), UUID(row.lease_id)
            if phase != "no_intent":
                intent = await repository(session).prepare_upload(
                    operation, lease, 1, part_bytes=5 * 1024**2, idle_timeout_seconds=20.0)
        if intent is not None:
            upload = await store.begin_source_upload(intent)
            if phase != "begin_unknown":
                async with intake.factory.begin() as session:
                    await repository(session).record_upload(operation, lease, 1, upload=upload)
            if phase == "partial":
                await store.upload_source_part(upload, 1, b"unfinished bytes")
            if phase in {"eof", "completed_unknown"}:
                completion = await local_source_completion(store, upload, b"unaccepted source bytes")
                async with intake.factory.begin() as session:
                    await repository(session).record_eof(operation, lease, 1, completion=completion)
            if phase == "completed_unknown":
                source = await store.complete_source_upload(completion)
        async with intake.factory.begin() as session:
            await repository(session).terminalize(operation, lease, 1, state="failed", failure_code="upload_interrupted")
        await age_fixture(intake, operation, preserve_upload_deadline=True)
        path = intake.durable_root / "objects" / "submission-source" / "v1" / str(operation) / "bundle.zip"
        if path.exists() and old_bytes:
            # Prepare historical provider activity alongside historical SQL ages.
            past = time.time() - 3 * 3600
            os.utime(path, (past, past))
        return operation, intent, upload, completion, source, path
    finally:
        store.close()


@pytest.mark.parametrize("phase", ["no_intent", "begin_unknown", "handle", "partial", "eof"])
async def test_unsealed_cleanup_releases_reserved_bytes_without_a_seal(intake, phase):
    operation, intent, upload, completion, _, path = await unfinished(intake, phase)
    result = await composition.sweep_submission_sources(intake.factory, settings_for(intake))
    assert result["confirmed"] == 1 and not path.exists()
    async with intake.factory() as session:
        row = (await session.execute(text("SELECT state,accounted_bytes,sealed_at FROM submission_source_charges WHERE operation_id=:id"),
                                     {"id": operation})).one()
        assert tuple(row) == ("released", 0, None)
        assert await session.scalar(text("SELECT provider_generation FROM submission_intake_operations WHERE id=:id"),
                                    {"id": operation}) is None
        target = await session.scalar(text("SELECT source FROM submission_source_cleanup_claims WHERE operation_id=:id"),
                                      {"id": operation})
        assert target["kind"] == "unsealed"
    assert (await composition.sweep_submission_sources(intake.factory, settings_for(intake)))["candidates"] == 0
    if intent is not None:
        store = initialize_local_store(root=intake.durable_root)
        try:
            with pytest.raises(ArtifactPreconditionFailedError):
                await store.begin_source_upload(intent)
            with pytest.raises(ArtifactPreconditionFailedError):
                await store.upload_source_part(upload, 1, b"late")
            if completion is not None:
                with pytest.raises(ArtifactPreconditionFailedError):
                    await store.complete_source_upload(completion)
        finally:
            store.close()


@pytest.mark.parametrize("phase", ["partial", "completed_unknown"])
async def test_recent_parts_and_unrecorded_completed_version_remain_charged(intake, phase):
    operation, _, _, _, source, path = await unfinished(intake, phase, old_bytes=False)
    result = await composition.sweep_submission_sources(intake.factory, settings_for(intake))
    assert result["confirmed"] == 0 and result["deferred"] == 1
    assert path.exists()
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges WHERE operation_id=:id"),
                                    {"id": operation}) > 0
        assert await session.scalar(text("SELECT confirmed_at FROM submission_source_cleanup_claims WHERE operation_id=:id"),
                                    {"id": operation}) is None
    if source is not None:
        store = initialize_local_store(root=intake.durable_root)
        try:
            assert await store.observe_sealed_source(source) is not None
        finally:
            store.close()


async def test_late_completion_requires_new_age_and_version_bound_claim(intake):
    from datetime import timedelta
    from app.core.identifiers import new_record_id
    from app.modules.artifacts.intake.repository import IntakeCustodyConflict
    from tests.artifacts.test_submission_source_cleanup import owner
    operation, _, _, _, source, path = await unfinished(intake, "completed_unknown", old_bytes=False)
    first = await composition.sweep_submission_sources(intake.factory, settings_for(intake))
    assert first["deferred"] == 1 and path.exists()
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT observed_source FROM submission_source_cleanup_claims WHERE operation_id=:id"),
                                    {"id": operation}) == source.model_dump(mode="json")
        assert await session.scalar(text("SELECT public.source_cleanup_authority_valid(c,'claim') "
            "FROM submission_source_cleanup_claims c WHERE operation_id=:id"), {"id": operation}) is False
    with pytest.raises(IntakeCustodyConflict, match="recent_completion"):
        async with intake.factory.begin() as session:
            await owner(session).claim(operation, new_record_id(), lease_duration=timedelta(seconds=30))
    assert (await composition.sweep_submission_sources(intake.factory, settings_for(intake)))["candidates"] == 0
    assert intake.engine.url.database.startswith("workstream_test_")
    async with intake.engine.begin() as connection:
        # Only prepare historical observation/lease timestamps; target and
        # authority values remain untouched, and the guard is restored here.
        await connection.execute(text("ALTER TABLE submission_source_cleanup_claims DISABLE TRIGGER submission_source_cleanup_guard"))
        await connection.execute(text("UPDATE submission_source_cleanup_claims SET observed_at=observed_at-interval '3 hours', "
            "claimed_at=claimed_at-interval '3 hours',lease_expires_at=lease_expires_at-interval '3 hours' WHERE operation_id=:id"),
            {"id": operation})
        await connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        await connection.execute(text("ALTER TABLE submission_source_cleanup_claims ENABLE TRIGGER submission_source_cleanup_guard"))
    assert (await composition.sweep_submission_sources(intake.factory, settings_for(intake)))["confirmed"] == 1
    assert not path.exists()
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT generation FROM submission_source_cleanup_claims WHERE operation_id=:id"),
                                    {"id": operation}) == 2
        assert await session.scalar(text("SELECT public.source_cleanup_authority_valid(c,'confirm') "
            "FROM submission_source_cleanup_claims c WHERE operation_id=:id"), {"id": operation}) is True
        assert (await session.execute(text("SELECT state,accounted_bytes,sealed_at FROM submission_source_charges WHERE operation_id=:id"),
                                      {"id": operation})).one() == ("released", 0, None)


async def test_completion_observation_rejects_substituted_source_and_old_claim(intake):
    from datetime import timedelta
    from app.core.identifiers import new_record_id
    from app.modules.artifacts.intake.repository import IntakeCustodyConflict
    from tests.artifacts.test_submission_source_cleanup import owner

    operation, _, _, _, source, path = await unfinished(intake, "completed_unknown")
    async with intake.factory.begin() as session:
        claim = await owner(session).claim(operation, new_record_id(), lease_duration=timedelta(minutes=5))
    original = source.model_dump(mode="json")
    substitutions = [
        {**original, "location": {**original["location"], "operation_id": str(new_record_id())}},
        {**original, "raw_sha256": "sha256:" + "0" * 64},
        {**original, "sealed_upload_fence": original["sealed_upload_fence"] + 1},
    ]
    for substituted in substitutions:
        # Bypass Python validation to exercise the persisted authority boundary.
        with pytest.raises(DBAPIError, match="completion observation differs"):
            async with intake.factory.begin() as session:
                await session.execute(text("UPDATE submission_source_cleanup_claims "
                    "SET observed_source=CAST(:source AS jsonb),observed_at=clock_timestamp() "
                    "WHERE operation_id=:id"), {"id": operation, "source": json.dumps(substituted)})
    async with intake.factory.begin() as session:
        await owner(session).record_completion_observation(claim, source)
    with pytest.raises(IntakeCustodyConflict, match="recent_completion"):
        async with intake.factory.begin() as session:
            await owner(session).confirm(claim, object_absent=True, writes_settled=True, parts_absent=True)
    async with intake.factory() as session:
        assert await session.scalar(text("SELECT observed_source FROM submission_source_cleanup_claims WHERE operation_id=:id"),
                                    {"id": operation}) == original
        assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges WHERE operation_id=:id"),
                                    {"id": operation}) > 0
    assert path.exists()
