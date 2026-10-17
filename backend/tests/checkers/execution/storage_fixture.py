"""Closed history with canonical stored ART lineage and real fixed-service phase authority."""

from app.modules.checkers.api.selected_post_submit import make_selected_post_submit_request
from uuid import UUID

from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.models import SubmissionBundleAdmission
from app.adapters.checkers import evaluation_coordinator
from tests.checkers.execution.support import live_executor, provision_post_submit_service
from types import SimpleNamespace


async def storage_request(session, submission_id, *, generation=1):
    from app.modules.tasks.models import SubmissionDispatch
    from app.core.identifiers import new_record_id
    receipt = await session.get(SubmissionDispatch, str(submission_id))
    assert receipt is not None
    stored = await evaluation_coordinator(session).read_reserved_evaluation(
        project_id=UUID(receipt.project_id), task_id=UUID(receipt.task_id),
        submission_id=UUID(receipt.submission_id), request_id=UUID(receipt.evaluation_request_id),
    )
    if generation == 1:
        return stored.request
    body = stored.request.model_dump(exclude={"request_sha256"})
    body.update(evaluation_generation=generation, evaluation_request_id=new_record_id())
    return make_selected_post_submit_request(**body)


class _UnavailableArchiveStore:
    """Report a provider outage through the current ART byte-read boundary."""

    def __init__(self, store):
        self.identity = store.identity

    async def open(self, _ref, byte_range=None, **_kwargs):
        from app.interfaces.artifacts import ArtifactStoreUnavailableError

        raise ArtifactStoreUnavailableError()
        yield  # The ArtifactStore.open port is an async byte iterator.


async def seed_storage_run(factory, submission_id, *, verdict="passed", state="completed", generation=1):
    """Execute the locked current policy with controlled image/provider outcomes."""
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from app.adapters.artifacts import post_submission_materialization
    from app.modules.artifacts.models import ArtifactStorageNamespace
    from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactScratchManager
    from app.modules.artifacts.service import ArtifactStorageNamespaceSpec
    from app.modules.artifacts.submission_archive import SubmissionArchiveInspector, SubmissionArchiveLimits
    from tests.checkers.execution.support import ControlledSelectedExecution
    from tests.retained_material_fixtures import retained_archive_store
    from tests.test_checker_materialization import _limits

    assert verdict in {"passed", "failed"}
    assert state in {"queued", "running", "completed", "infrastructure_failed"}
    assert verdict == "passed" or state == "completed"
    async with factory() as session, session.begin():
        request = await storage_request(session, submission_id, generation=generation)
        assert verdict != "failed" or request.policy.entries, "failed verdict requires a locked registered image"
        receipt = await evaluation_coordinator(session).reserve_current_evaluation(request)
    if state == "queued":
        return str(receipt.attempt_id)
    await provision_post_submit_service(factory)
    if state == "running":
        _, replay = await live_executor(SimpleNamespace(factory=factory, service=None))._claim(request)
        assert replay is None
        return str(receipt.attempt_id)
    await provision_post_submit_service(factory, ServiceIdentity.ARTIFACT_MATERIALIZER)
    async with factory() as session:
        persisted = await session.get(ArtifactStorageNamespace, "primary")
        namespace = ArtifactStorageNamespaceSpec(
            persisted.backend, persisted.adapter, persisted.provider_profile,
            persisted.namespace_descriptor, persisted.namespace_fingerprint,
        )
    store = retained_archive_store(factory, namespace)
    if state == "infrastructure_failed":
        store = _UnavailableArchiveStore(store)
    with TemporaryDirectory(prefix="retained-post-material-") as directory:
        manager = ArtifactScratchManager(
            root=Path(directory),
            limits=_limits(reservation_ttl_seconds=300, total_deadline_seconds=180),
        )
        try:
            materialization = post_submission_materialization(
                sessions=factory, store=store, namespace=namespace,
                preparation=ArtifactPreparationService(manager),
                inspector=SubmissionArchiveInspector(SubmissionArchiveLimits()),
            )
            executor = live_executor(
                SimpleNamespace(factory=factory, service=materialization),
                selected_execution=ControlledSelectedExecution(verdict=verdict),
            )
            result = await executor.evaluate_post_submission(request)
            assert result.outcome == state
            if state == "completed":
                assert result.execution.required_external_count == len(request.policy.entries)
                assert all(member.result.verdict == verdict for member in result.execution.external_members)
            return str(receipt.attempt_id)
        finally:
            manager.close()


async def authorize_stored_material(factory, execution, material):
    """Issue real input AUTH over canonical rows for storage-only terminal fixtures.

    This authorizes a read; it does not claim provider I/O was exercised. Real
    materialization tests use the provider and compare this same retained receipt.
    """
    from sqlalchemy import select
    from app.adapters.auth import post_submit_materialization_authority
    from app.modules.artifacts.models import (
        ArtifactReplica,
        ArtifactStorageNamespace,
        ArtifactVerificationReceipt,
    )
    from app.modules.checkers.api.materialization import MaterializationFacts

    async with factory() as session, session.begin():
        async with post_submit_materialization_authority(session).prepare_materialization(
            execution
        ) as prepared:
            a, v, namespace = (
                await session.execute(
                    select(
                        SubmissionBundleAdmission,
                        ArtifactVerificationReceipt,
                        ArtifactStorageNamespace,
                    )
                    .join(
                        ArtifactVerificationReceipt,
                        ArtifactVerificationReceipt.id
                        == SubmissionBundleAdmission.verification_receipt_id,
                    )
                    .join(
                        ArtifactReplica,
                        ArtifactReplica.id == SubmissionBundleAdmission.verified_replica_id,
                    )
                    .join(
                        ArtifactStorageNamespace,
                        ArtifactStorageNamespace.id == ArtifactReplica.storage_namespace_id,
                    )
                    .where(SubmissionBundleAdmission.id == str(material.admission_id))
                )
            ).one()
            return await prepared.consume(
                MaterializationFacts(
                    execution=execution,
                    material=material,
                    evidence_id=UUID(a.selected_pre_submit_run_id),
                    verification_receipt_id=UUID(v.id),
                    verification_job_id=UUID(v.verification_job_id),
                    verification_generation=v.execution_generation,
                    namespace_fingerprint=namespace.namespace_fingerprint,
                    semantic_manifest_id=UUID(a.semantic_manifest_id),
                )
            )
