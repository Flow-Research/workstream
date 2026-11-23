"""Real PostgreSQL charge custody across uncertain MinIO partial-upload cleanup."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.adapters.artifacts import submission_source_cleanup_execution
from app.adapters.artifacts.source_cleanup import S3SubmissionSourceCleanup
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import ArtifactStoreUnavailableError
from app.modules.actors.api import ServiceIdentity
from tests.artifacts.test_submission_intake_admission import (
    admission_intake as admission_intake, admin_access as admin_access,
    auth_database_env as auth_database_env, clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material, signed_access as signed_access, admit_new,
)
from tests.artifacts.test_submission_intake_custody import repository
from tests.artifacts.test_submission_source_cleanup import age_fixture
from tests.checkers.execution.support import provision_post_submit_service


@pytest.mark.parametrize("admission_intake", ["minio"], indirect=True)
async def test_partial_upload_charge_survives_lost_abort_then_releases_once(admission_intake, monkeypatch):
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
        async with f.factory.begin() as session:
            await repository(session).record_upload(operation, foreground.lease_id, foreground.generation, upload=upload)
        await store.upload_source_part(upload, 1, b"interrupted ZIP")
        async with f.factory.begin() as session:
            await repository(session).terminalize(operation, foreground.lease_id, foreground.generation,
                state="failed", failure_code="upload_interrupted")
        await age_fixture(SimpleNamespace(engine=f.factory.kw["bind"]), operation, preserve_upload_deadline=True)
        abort = cleanup_store.request_source_abort

        async def lose_acknowledgment(target):
            await abort(target)
            raise ArtifactStoreUnavailableError("abort acknowledgment lost")

        monkeypatch.setattr(cleanup_store, "request_source_abort", lose_acknowledgment)
        execution = submission_source_cleanup_execution(sessions=f.factory, provider=cleanup,
            lease_duration=timedelta(seconds=60))
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
        assert await store.source_upload_parts_absent(upload) is True
    finally:
        cleanup.close()
        store.close()
