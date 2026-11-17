"""Real MinIO T1/PRE/T5/POST proof excludes newer same-key source versions."""
from contextlib import asynccontextmanager
from datetime import timedelta

import pytest

from app.adapters.artifacts import submission_admission_consumption_port
from app.adapters.checkers import selected_pre_submit_coordinator
from app.adapters.outbox import outbox_append
from app.adapters.tasks import accepted_submission_creation_service
from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.authorization import PreparedSubmissionFinalizationAuthorization
from app.modules.artifacts.intake.finalization import AcceptedSubmissionFinalization
from tests.artifacts.intake_acceptance_support import completed_source
from tests.artifacts.intake_post_support import exercise_source_post
from tests.artifacts.test_submission_intake_admission import (
    admission_intake as admission_intake,
    admin_access as admin_access,
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
    signed_access as signed_access,
)
from tests.checkers.execution.support import provision_post_submit_service
from tests.test_artifact_admission import _settings
from tests.test_s3_artifact_store import MINIO_BUCKET


@pytest.mark.parametrize("admission_intake", ["minio"], indirect=True)
@pytest.mark.parametrize("remove_original", [False, True])
async def test_post_uses_recorded_version_despite_newer_same_key(admission_intake, tmp_path, monkeypatch, remove_original):
    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    await f.admission.accept(owner, request, terminal.terminal_digest,
        checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    await provision_post_submit_service(f.factory, ServiceIdentity.ARTIFACT_BINDING)
    store = f.source_store_factory()
    def submissions(session):
        return accepted_submission_creation_service(session, settings=_settings(tmp_path),
            admissions=submission_admission_consumption_port(session,
                request_id=new_record_id(), correlation_id=owner.operation_id))
    finalizer = AcceptedSubmissionFinalization(
        f.factory, tasks=f.admission._tasks, submissions=submissions,
        checkers=selected_pre_submit_coordinator, store=store, lease_duration=timedelta(seconds=60),
        authorization=lambda session: PreparedSubmissionFinalizationAuthorization(
            session, request_id=new_record_id(), correlation_id=owner.operation_id))
    try:
        created = await finalizer.run(owner.operation_id)
        source = request.source
        original_client = store._client
        async with original_client() as client:
            newer = await client.put_object(Bucket=MINIO_BUCKET, Key=store._source_key(source.location),
                                           Body=b"a different, invalid ZIP")
            assert newer["VersionId"] != source.provider_generation
            if remove_original:
                await client.delete_object(Bucket=MINIO_BUCKET, Key=store._source_key(source.location),
                                           VersionId=source.provider_generation)
        reads = []
        class ReadOnlyClient:
            def __init__(self, client):
                self.client = client
            async def get_object(self, **kwargs):
                reads.append(kwargs)
                return await self.client.get_object(**kwargs)
        @asynccontextmanager
        async def recorded_reads():
            async with original_client() as client:
                yield ReadOnlyClient(client)
        monkeypatch.setattr(store, "_client", recorded_reads)
        await exercise_source_post(f, created, store, source, tmp_path, missing=remove_original)
        assert reads == [dict(Bucket=MINIO_BUCKET, Key=store._source_key(source.location),
                              VersionId=source.provider_generation)]
        assert await finalizer.run(owner.operation_id) == created
        assert len(reads) == 1
    finally:
        store.close()
