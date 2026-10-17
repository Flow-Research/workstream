"""Real ART admission owners with an in-memory byte provider for retained history.

These prerequisites exercise canonical storage guards, not deployment/provider
conformance. Local/MinIO execution has its own focused integration proof.
"""

from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID
from weakref import WeakKeyDictionary
from zipfile import ZipFile

from sqlalchemy import select

from app.adapters.auth import selected_pre_submit_authority
from app.adapters.checkers import (
    SelectedPreSubmitCheckerExecutionAdapter,
    selected_pre_submit_coordinator,
)
from app.adapters.tasks import task_submission_context_port
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import (
    ArtifactObjectHead,
    ArtifactPutObservation,
    ArtifactPutResult,
    artifact_provider_object_ref,
)
from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.modules.artifacts.api import SubmissionBundlePreparationRequest
from app.modules.artifacts.authorization import (
    PreparedPreSubmitMaterializationAuthorization,
    PreparedSubmissionBundlePreparationAuthorization,
)
from app.modules.artifacts.models import (
    ArtifactStorageNamespace,
    ArtifactVerificationJob,
    SubmissionBundleAdmission,
)
from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactScratchManager
from app.modules.artifacts.service import (
    ArtifactAdmissionService,
    ArtifactStorageNamespaceSpec,
    ArtifactStorageOrchestrator,
)
from app.modules.artifacts.submission_admission import (
    PreparedSubmissionBundlePreparationCommand,
    SubmissionBundleDurablePutService,
    SubmissionBundlePreparationRuntime,
)
from app.modules.artifacts.selected_pre_submit_execution import SelectedPreSubmitExecutionService
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspector,
    SubmissionArchiveLimits,
)
from app.modules.artifacts.submission_materialization import PreparedBundleMaterializationService
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.actors.api import ServiceIdentity
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
from app.modules.projects.models import EffectiveProjectSubmissionArtifactPolicy
from app.modules.tasks.api.submission_context import TaskSubmissionContextRequest
from tests.test_artifact_admission import _AllowArtifactAuthority, _context, _settings
from tests.test_checker_materialization import _limits
from tests.checkers.execution.support import provision_post_submit_service


async def _bytes(value: bytes):
    yield value


class _ForbiddenExternalExecution:
    async def execute(self, *_args, **_kwargs):
        raise AssertionError("empty selected policy invoked an external image")


class MemoryStore:
    """Implement the existing byte port; all database work stays in ART owners."""

    def __init__(self, namespace, *, objects=None):
        self.identity = ExternalServiceAdapterIdentity("artifact_store", namespace.adapter)
        self.objects = {} if objects is None else objects

    async def put(self, source, **_kwargs):
        ref = artifact_provider_object_ref(source.commitment)
        data = b"".join([chunk async for chunk in source.stream()])
        replayed = ref in self.objects
        if replayed:
            assert self.objects[ref] == data
        self.objects[ref] = data
        return ArtifactPutResult(ref, replayed)

    async def observe_put_result(self, commitment, **_kwargs):
        ref = artifact_provider_object_ref(commitment)
        return ArtifactPutObservation(ref, ref in self.objects)

    async def open(self, ref, byte_range=None, **_kwargs):
        data = self.objects[ref]
        if byte_range is not None:
            end = None if byte_range.length is None else byte_range.offset + byte_range.length
            data = data[byte_range.offset : end]
        yield data

    async def head(self, ref, **_kwargs):
        data = self.objects.get(ref)
        return ArtifactObjectHead(ref, data is not None, len(data) if data is not None else None)


_RETAINED_OBJECTS = WeakKeyDictionary()


def retained_archive_store(factory, namespace):
    """Keep immutable fixture bytes until their owning test factory is disposed."""
    namespaces = _RETAINED_OBJECTS.setdefault(factory, {})
    objects = namespaces.setdefault(namespace.namespace_fingerprint, {})
    return MemoryStore(namespace, objects=objects)


def _submission_request(task, assignment, link, packet, predecessor_id, policy, revision_context):
    content = BytesIO()
    paths = {entry["path"] for entry in policy["required_artifacts"] if entry.get("required", True)}
    paths.update(
        entry.get("path") or "evidence/" + entry["key"]
        for entry in policy["required_evidence"]
        if entry.get("required", True)
    )
    with ZipFile(content, "w") as archive:
        for path in sorted(paths):
            archive.writestr(path, f"{task.id}:{predecessor_id}:{packet.summary}\n")
    context = _context(actor_profile_id=UUID(task.assigned_to), identity_link_id=UUID(link.id))
    request = SubmissionBundlePreparationRequest(
        actor=ActorIdentityFacts(
            context.actor_profile_id, context.identity_link_id, ActorKind.HUMAN
        ),
        request_id=context.request_id,
        correlation_id=context.correlation_id,
        task_id=UUID(task.id),
        assignment_id=UUID(assignment.id),
        predecessor_submission_id=UUID(predecessor_id) if predecessor_id else None,
        idempotency_key=new_record_id(),
        summary=packet.summary,
        contributor_attestation=packet.worker_attestation,
        media_type="application/zip",
        byte_source=_bytes(content.getvalue()),
        revision_preparation_id=(str(revision_context.preparation_id) if revision_context else None),
        revision_preparation_sha256=(revision_context.preparation_sha256 if revision_context else None),
    )
    return context, request


def _runtime_factory(
    *,
    session,
    settings,
    namespace,
    authority,
    materialization_authority,
    preparation,
    inspector,
    materialization,
    storage,
    tasks,
    projects,
    coordinator,
):
    @asynccontextmanager
    async def runtime():
        try:
            yield SubmissionBundlePreparationRuntime(
                preparation=preparation,
                inspector=inspector,
                materialization=materialization,
                durable_put=SubmissionBundleDurablePutService(
                    session=session,
                    admission=ArtifactAdmissionService(session, settings, namespace),
                    storage=storage,
                    authorization=authority,
                    task_contexts=tasks,
                    project_contexts=projects,
                ),
                selected_coordinator=coordinator,
                selected_execution=SelectedPreSubmitExecutionService(
                    session=session,
                    coordinator=coordinator,
                    authority=selected_pre_submit_authority(session),
                    materialization=materialization,
                ),
                storage_scheme="s3",
                artifact_deadline_ms=180_000,
            )
        finally:
            materialization_authority.close()

    return runtime


async def _verify_admission(factory, store, namespace, settings, result):
    async with factory() as session:
        job_id = await session.scalar(
            select(ArtifactVerificationJob.id).where(
                ArtifactVerificationJob.originating_put_attempt_id == str(result.put_attempt_id),
            )
        )
        assert job_id is not None, result
        await session.rollback()
        orchestrator = ArtifactStorageOrchestrator(
            session, store, namespace, settings, _AllowArtifactAuthority()
        )
        assert await orchestrator.verify_object(
            UUID(job_id),
            submission_task_contexts=task_submission_context_port(session),
        ) == "verified"
        admission = await session.scalar(
            select(SubmissionBundleAdmission).where(
                SubmissionBundleAdmission.put_attempt_id == str(result.put_attempt_id),
            )
        )
        assert admission.status == "ready"
        return admission.id


async def retained_admission(
    factory,
    task,
    assignment,
    link,
    packet,
    predecessor_id,
    *,
    external_execution=None,
):
    """Prepare/check/publish/verify actual ZIP bytes for this existing assignment."""
    await provision_post_submit_service(factory, ServiceIdentity.ARTIFACT_MATERIALIZER)
    await provision_post_submit_service(factory, ServiceIdentity.CHECKER_PRE_SUBMIT)
    async with factory() as session, session.begin():
        current = await task_submission_context_port(session).lock_submission_context(
            TaskSubmissionContextRequest(
                task_id=UUID(task.id), assignment_id=UUID(assignment.id),
                contributor_id=UUID(task.assigned_to),
                predecessor_submission_id=UUID(predecessor_id) if predecessor_id else None,
            )
        )
        persisted = await session.get(ArtifactStorageNamespace, "primary")
        namespace = ArtifactStorageNamespaceSpec(
            persisted.backend,
            persisted.adapter,
            persisted.provider_profile,
            persisted.namespace_descriptor,
            persisted.namespace_fingerprint,
        )
        policy = (
            await session.get(
                EffectiveProjectSubmissionArtifactPolicy,
                str(current.locked_project_context.effective_policy_id),
            )
        ).effective_policy
    # A retained successor is still a new governed attempt: explicitly acknowledge
    # its canonical current preparation, then let ART revalidate the binding.
    context, request = _submission_request(
        task, assignment, link, packet, predecessor_id, policy, current.revision_context,
    )
    store = retained_archive_store(factory, namespace)
    with TemporaryDirectory(prefix="retained-material-") as directory:
        settings = _settings(Path(directory), maximum_bytes=1024 * 1024)
        # This fixture traverses multiple real database transactions. Its scratch
        # lifetime is not the ten-second unit-test timeout from materialization.
        manager = ArtifactScratchManager(
            root=Path(directory) / "bounded",
            limits=_limits(reservation_ttl_seconds=300, total_deadline_seconds=180),
        )
        try:
            async with factory() as session:
                authority = PreparedSubmissionBundlePreparationAuthorization(session, context)
                materialization_authority = PreparedPreSubmitMaterializationAuthorization(
                    session,
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                )
                tasks = task_submission_context_port(session)
                projects = ProjectLockedPolicyRepository(session)
                preparation = ArtifactPreparationService(manager)
                inspector = SubmissionArchiveInspector(SubmissionArchiveLimits())
                materialization = PreparedBundleMaterializationService(
                    session=session,
                    authorization=materialization_authority,
                    preparation=preparation,
                    checker_execution=SelectedPreSubmitCheckerExecutionAdapter(
                        archive_inspector=inspector,
                        external_execution=external_execution or _ForbiddenExternalExecution(),
                    ),
                    storage_scheme="s3",
                )
                storage = ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority()
                )
                coordinator = selected_pre_submit_coordinator(session)

                result = await PreparedSubmissionBundlePreparationCommand(
                    session=session,
                    authority=authority,
                    task_contexts=tasks,
                    project_contexts=projects,
                    runtime_factory=_runtime_factory(
                        session=session,
                        settings=settings,
                        namespace=namespace,
                        authority=authority,
                        materialization_authority=materialization_authority,
                        preparation=preparation,
                        inspector=inspector,
                        materialization=materialization,
                        storage=storage,
                        tasks=tasks,
                        projects=projects,
                        coordinator=coordinator,
                    ),
                ).prepare(request)
            return await _verify_admission(factory, store, namespace, settings, result)
        finally:
            manager.close()
