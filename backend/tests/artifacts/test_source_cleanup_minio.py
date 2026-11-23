"""Real PostgreSQL charge custody across uncertain MinIO partial-upload cleanup."""
from datetime import timedelta
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.adapters.artifacts import submission_source_cleanup_execution
from app.adapters.artifacts.source_cleanup import S3SubmissionSourceCleanup
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import ArtifactStoreUnavailableError
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.intake.repository import IntakeCustodyConflict
from tests.artifacts.test_submission_intake_admission import (
    admission_intake as admission_intake, admin_access as admin_access,
    auth_database_env as auth_database_env, clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material, signed_access as signed_access, admit_new,
)
from tests.artifacts.test_submission_intake_custody import repository
from tests.artifacts.test_submission_source_cleanup import age_fixture, owner
from tests.checkers.execution.support import provision_post_submit_service


async def expire_cleanup_claim(f, operation):
    """Prepare only historical lease timestamps in the isolated test database."""
    engine = f.factory.kw["bind"]
    assert engine.url.database.startswith("workstream_test_")
    async with engine.begin() as connection:
        await connection.execute(text("ALTER TABLE submission_source_cleanup_claims DISABLE TRIGGER submission_source_cleanup_guard"))
        await connection.execute(text("UPDATE submission_source_cleanup_claims SET "
            "claimed_at=claimed_at-interval '2 minutes',lease_expires_at=lease_expires_at-interval '2 minutes' "
            "WHERE operation_id=:id"), {"id": operation})
        await connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        await connection.execute(text("ALTER TABLE submission_source_cleanup_claims ENABLE TRIGGER submission_source_cleanup_guard"))


@pytest.mark.parametrize("admission_intake", ["minio"], indirect=True)
@pytest.mark.parametrize("missing_handle", [False, True])
async def test_partial_upload_charge_survives_lost_abort_then_releases_once(admission_intake, monkeypatch, missing_handle):
    f = admission_intake
    await provision_post_submit_service(f.factory, ServiceIdentity.ARTIFACT_SOURCE_CLEANUP)
    foreground = await admit_new(f)
    operation = foreground.operation_id
    store = f.source_store_factory()
    cleanup_store = f.source_store_factory()
    cleanup = S3SubmissionSourceCleanup(cleanup_store)
    try:
        async with f.factory.begin() as session:
            intent = await repository(session).prepare_upload(operation, foreground.lease_id, foreground.generation,
                part_bytes=5 * 1024**2, idle_timeout_seconds=20.0)
        upload = await store.begin_source_upload(intent)
        handles = [upload]
        if missing_handle:
            # Reconcile multiple handles left by an older implicit SDK retry.
            handles.append(await store.begin_source_upload(intent))
        handle_ids = sorted(item.provider_upload_id for item in handles)
        if not missing_handle:
            async with f.factory.begin() as session:
                await repository(session).record_upload(operation, foreground.lease_id, foreground.generation, upload=upload)
            await store.upload_source_part(upload, 1, b"interrupted ZIP")
        async with f.factory.begin() as session:
            await repository(session).terminalize(operation, foreground.lease_id, foreground.generation,
                state="failed", failure_code="upload_interrupted")
        await age_fixture(SimpleNamespace(engine=f.factory.kw["bind"]), operation, preserve_upload_deadline=True)
        abort = cleanup_store.request_source_abort
        aborted = []

        async def lose_acknowledgment(target):
            if missing_handle:
                async with f.factory() as session:
                    assert await session.scalar(text("SELECT observed_upload_ids FROM submission_source_cleanup_claims "
                        "WHERE operation_id=:id"), {"id": operation}) == handle_ids
                    assert await session.scalar(text("SELECT public.source_cleanup_authority_valid(c,'claim') "
                        "FROM submission_source_cleanup_claims c WHERE operation_id=:id"), {"id": operation}) is True
            aborted.append(target.provider_upload_id)
            await abort(target)
            raise ArtifactStoreUnavailableError("abort acknowledgment lost")

        monkeypatch.setattr(cleanup_store, "request_source_abort", lose_acknowledgment)
        execution = submission_source_cleanup_execution(sessions=f.factory, provider=cleanup,
            lease_duration=timedelta(seconds=60))
        claim_id = new_record_id()
        if missing_handle:
            async with f.factory.begin() as session:
                await owner(session).claim(operation, claim_id, lease_duration=timedelta(seconds=60))
            for invalid in ([], [handle_ids[0], handle_ids[0]], list(reversed(handle_ids))):
                with pytest.raises(DBAPIError, match="canonical growth"):
                    async with f.factory.begin() as session:
                        await session.execute(text("UPDATE submission_source_cleanup_claims "
                            "SET observed_upload_ids=CAST(:handles AS jsonb) WHERE operation_id=:id"),
                            {"id": operation, "handles": json.dumps(invalid)})
            with pytest.raises(IntakeCustodyConflict, match="upload_observed"):
                await execution.run(operation, claim_id)
            assert aborted == []
            assert await store.source_upload_parts_absent(upload) is False
            with pytest.raises(IntakeCustodyConflict, match="authority_unavailable"):
                await execution.run(operation, claim_id)
            await expire_cleanup_claim(f, operation)
            claim_id = new_record_id()
            async with f.factory.begin() as session:
                current = await owner(session).claim(operation, claim_id, lease_duration=timedelta(seconds=60))
            with pytest.raises(DBAPIError, match="canonical growth"):
                async with f.factory.begin() as session:
                    await session.execute(text("UPDATE submission_source_cleanup_claims "
                        "SET observed_upload_ids=CAST(:handles AS jsonb) WHERE operation_id=:id"),
                        {"id": operation, "handles": json.dumps(handle_ids[:1])})
            with pytest.raises(IntakeCustodyConflict, match="cleanup_stale"):
                async with f.factory.begin() as session:
                    await owner(session).upload_for_claim(replace(current, observed_upload_ids=tuple(handle_ids[:1])))
            # A later discovered handle enlarges custody, not the authority of
            # an already issued claim. Nothing is aborted under the old target.
            handles.append(await store.begin_source_upload(intent))
            handle_ids = sorted(item.provider_upload_id for item in handles)
            with pytest.raises(IntakeCustodyConflict, match="upload_observed"):
                await execution.run(operation, claim_id)
            assert aborted == []
            await expire_cleanup_claim(f, operation)
            claim_id = new_record_id()
        with pytest.raises(ArtifactStoreUnavailableError, match="acknowledgment lost"):
            await execution.run(operation, claim_id)
        async with f.factory() as session:
            assert (await session.execute(text("SELECT state,accounted_bytes,sealed_at "
                "FROM submission_source_charges WHERE operation_id=:id"), {"id": operation})).one() == ("reserved", 1024, None)
            assert await session.scalar(text("SELECT confirmed_at FROM submission_source_cleanup_claims "
                "WHERE operation_id=:id"), {"id": operation}) is None
        monkeypatch.setattr(cleanup_store, "request_source_abort", abort)
        await execution.run(operation, claim_id)
        await execution.run(operation, claim_id)
        async with f.factory() as session:
            assert (await session.execute(text("SELECT state,accounted_bytes,sealed_at "
                "FROM submission_source_charges WHERE operation_id=:id"), {"id": operation})).one() == ("released", 0, None)
            assert await session.scalar(text("SELECT public.source_cleanup_authority_valid(c,'confirm') "
                "FROM submission_source_cleanup_claims c WHERE operation_id=:id"), {"id": operation}) is True
            assert await session.scalar(text("SELECT provider_generation FROM submission_intake_operations "
                "WHERE id=:id"), {"id": operation}) is None
            if missing_handle:
                assert await session.scalar(text("SELECT provider_upload_id FROM submission_source_upload_receipts "
                    "WHERE operation_id=:id"), {"id": operation}) is None
                assert await session.scalar(text("SELECT generation FROM submission_source_cleanup_claims "
                    "WHERE operation_id=:id"), {"id": operation}) == 3
        for target in handles:
            assert await store.source_upload_parts_absent(target) is True
    finally:
        cleanup.close()
        store.close()
