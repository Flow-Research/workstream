"""T5-to-POST owner integration with real storage and a controlled checker runtime."""
from types import SimpleNamespace
from uuid import UUID

from app.adapters.artifacts import post_submission_materialization
from app.adapters.checkers import evaluation_coordinator
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactScratchManager
from tests.checkers.execution.support import ControlledSelectedExecution, live_executor, provision_post_submit_service
from tests.test_checker_materialization import _limits
from tests.trusted_intake_fixtures import LocalIntakeAdapter


class ExactSourceStore:
    def __init__(self, store, expected):
        self.store, self.expected, self.opens = store, expected, []
        self.identity = store.identity

    def open(self, *args, **kwargs):
        raise AssertionError("accepted POST must never use an unversioned object read")

    def open_source(self, source, **kwargs):
        assert source == self.expected
        self.opens.append(source)
        return self.store.open_source(source, **kwargs)


async def exercise_source_post(f, created, store, source, tmp_path, *, missing=False):
    """Execute and retain POST with fresh AUTH, exact source I/O and replay."""
    await provision_post_submit_service(f.factory, ServiceIdentity.CHECKER_POST_SUBMIT)
    await provision_post_submit_service(f.factory, ServiceIdentity.ARTIFACT_MATERIALIZER)
    async with f.factory.begin() as session:
        reserved = await evaluation_coordinator(session).read_reserved_evaluation(
            project_id=UUID(str(f.project)), task_id=UUID(str(f.task)),
            submission_id=created.submission_id, request_id=created.evaluation_request_id)
    counted = ExactSourceStore(store, source)
    scratch = ArtifactScratchManager(root=tmp_path / "post-scratch", limits=_limits())
    try:
        service = post_submission_materialization(
            sessions=f.factory, store=counted, namespace=f.namespace,
            preparation=ArtifactPreparationService(scratch), intake=LocalIntakeAdapter(),
            archive_limits=SubmissionArchiveLimits(), artifact_deadline_ms=30_000)
        runtime = ControlledSelectedExecution()
        harness = SimpleNamespace(factory=f.factory, service=service, request=reserved.request)
        executor = live_executor(harness, selected_execution=runtime)
        result = await executor.evaluate_post_submission(reserved.request)
        assert result.outcome == ("infrastructure_failed" if missing else "completed")
        assert len(counted.opens) == 1
        assert len(runtime.requests) == (0 if missing else 1)
        if not missing:
            material = runtime.requests[0].materials[0]
            assert material.source_operation_id == source.location.operation_id
            assert material.verification_receipt_id is None
            assert "verification_receipt_id" not in material.model_dump(mode="json")
        assert await executor.evaluate_post_submission(reserved.request) == result
        assert len(counted.opens) == 1
        assert len(runtime.requests) == (0 if missing else 1)
    finally:
        scratch.close()


async def leave_expired_finalizer_claim(f, finalizer, operation_id):
    """Simulate worker death after claim; a separate delivery cannot compete live."""
    import asyncio
    from datetime import timedelta
    import pytest
    from sqlalchemy import text
    from app.core.identifiers import new_record_id
    from app.modules.artifacts.intake.repository import IntakeCustodyConflict

    finalizer._duration = timedelta(seconds=3)
    first = await finalizer._claim(operation_id, new_record_id())
    assert first.generation == 1
    with pytest.raises(IntakeCustodyConflict, match="finalization_lease_busy"):
        await finalizer._claim(operation_id, new_record_id())
    async with asyncio.timeout(15):
        while True:
            async with f.factory() as session:
                remaining = float(await session.scalar(text("SELECT extract(epoch FROM "
                    "(continuation_expires_at-clock_timestamp())) FROM submission_intake_operations WHERE id=:id"),
                    {"id": operation_id}))
            if remaining <= 0:
                break
            await asyncio.sleep(min(remaining + 0.02, 0.25))
    finalizer._duration = timedelta(seconds=60)


async def minio_source_fixture():
    """Create a versioned test namespace and a reopenable provider factory."""
    from app.adapters.artifacts import create_artifact_store_bootstrap
    from app.core.identifiers import new_record_id
    from app.interfaces.artifacts import ArtifactStoreNamespaceClaim
    from app.modules.artifacts.service import artifact_storage_namespace_spec
    from tests.test_s3_artifact_store import MINIO_BUCKET, minio_settings, provision_minio_bucket
    await provision_minio_bucket.__wrapped__()
    settings = minio_settings(private_prefix=f"post-source/{new_record_id()}", buffer_bytes=65536)
    bootstrap = create_artifact_store_bootstrap(settings, activation_guard=None)
    namespace = artifact_storage_namespace_spec(settings, bootstrap)
    def factory():
        return bootstrap.initialize_after_namespace_claim(ArtifactStoreNamespaceClaim(
            bootstrap.identity, bootstrap.namespace_identity, namespace.namespace_fingerprint))
    store = factory()
    try:
        async with store._client() as client:
            await client.put_bucket_versioning(Bucket=MINIO_BUCKET, VersioningConfiguration={"Status": "Enabled"})
    finally:
        store.close()
    return namespace, factory
