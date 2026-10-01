"""Real ART admission owners with an in-memory byte provider for retained history.

These prerequisites exercise canonical storage guards, not deployment/provider
conformance. Local/MinIO execution has its own focused integration proof.
"""

from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID
from zipfile import ZipFile

from sqlalchemy import select

from app.adapters.artifacts import CheckerPhaseService
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import (
    ArtifactObjectHead, ArtifactPutObservation, ArtifactPutResult, artifact_provider_object_ref,
)
from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.modules.artifacts.api import SubmissionBundlePreparationRequest
from app.modules.artifacts.authorization import PreparedSubmissionBundlePreparationAuthorization
from app.modules.artifacts.models import ArtifactStorageNamespace, ArtifactVerificationJob, SubmissionBundleAdmission
from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactScratchManager
from app.modules.artifacts.service import ArtifactAdmissionService, ArtifactStorageNamespaceSpec, ArtifactStorageOrchestrator
from app.modules.artifacts.submission_admission import (
    PreparedSubmissionBundlePreparationCommand, SubmissionBundleDurablePutService,
    SubmissionBundlePreparationRuntime,
)
from app.modules.artifacts.submission_archive import SubmissionArchiveInspector, SubmissionArchiveLimits
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.checkers.catalogue import build_pre_submission_checker_catalogue
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
from app.modules.projects.models import EffectiveProjectSubmissionArtifactPolicy
from app.modules.tasks.repository import TaskRepository
from tests.checkers.execution.support import forbidden_post_submission
from tests.pre_submit_test_helpers import evidence_workflow
from tests.test_artifact_admission import _AllowArtifactAuthority, _context, _settings
from tests.test_checker_materialization import _limits
from tests.test_default_pre_submit_execution import _AllowAuthority, _bytes


class MemoryStore:
    """Implement the existing byte port; all database work stays in ART owners."""

    def __init__(self, namespace):
        self.identity = ExternalServiceAdapterIdentity("artifact_store", namespace.adapter)
        self.objects = {}

    async def put(self, source):
        ref = artifact_provider_object_ref(source.commitment)
        data = b"".join([chunk async for chunk in source.stream()])
        replayed = ref in self.objects
        if replayed:
            assert self.objects[ref] == data
        self.objects[ref] = data
        return ArtifactPutResult(ref, replayed)

    async def observe_put_result(self, commitment):
        ref = artifact_provider_object_ref(commitment)
        return ArtifactPutObservation(ref, ref in self.objects)

    async def open(self, ref, byte_range=None):
        data = self.objects[ref]
        if byte_range is not None:
            end = None if byte_range.length is None else byte_range.offset + byte_range.length
            data = data[byte_range.offset:end]
        yield data

    async def head(self, ref):
        data = self.objects.get(ref)
        return ArtifactObjectHead(ref, data is not None, len(data) if data is not None else None)


async def retained_admission(factory, task, assignment, link, packet, predecessor_id):
    """Prepare/check/publish/verify actual ZIP bytes for this existing assignment."""
    async with factory() as session:
        persisted = await session.get(ArtifactStorageNamespace, "primary")
        namespace = ArtifactStorageNamespaceSpec(
            persisted.backend, persisted.adapter, persisted.provider_profile,
            persisted.namespace_descriptor, persisted.namespace_fingerprint,
        )
        policy = (await session.get(
            EffectiveProjectSubmissionArtifactPolicy,
            task.locked_effective_project_submission_artifact_policy_id,
        )).effective_policy
    content = BytesIO()
    paths = {entry["path"] for entry in policy["required_artifacts"] if entry.get("required", True)}
    paths.update(entry.get("path") or "evidence/" + entry["key"]
                 for entry in policy["required_evidence"] if entry.get("required", True))
    with ZipFile(content, "w") as archive:
        for path in sorted(paths):
            archive.writestr(path, f"{task.id}:{predecessor_id}:{packet.summary}\n")
    store = MemoryStore(namespace)
    context = _context(actor_profile_id=UUID(task.assigned_to), identity_link_id=UUID(link.id))
    request = SubmissionBundlePreparationRequest(
        actor=ActorIdentityFacts(context.actor_profile_id, context.identity_link_id, ActorKind.HUMAN),
        request_id=context.request_id, correlation_id=context.correlation_id,
        task_id=UUID(task.id), assignment_id=UUID(assignment.id),
        predecessor_submission_id=UUID(predecessor_id) if predecessor_id else None,
        idempotency_key=new_record_id(), summary=packet.summary,
        contributor_attestation=packet.worker_attestation,
        media_type="application/zip", byte_source=_bytes(content.getvalue()),
    )
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
                tasks, projects = TaskRepository(session), ProjectLockedPolicyRepository(session)
                preparation = ArtifactPreparationService(manager)
                inspector = SubmissionArchiveInspector(SubmissionArchiveLimits())
                catalogue = build_pre_submission_checker_catalogue()
                evidence = evidence_workflow(
                    session=session, preparation=preparation, inspector=inspector, catalogue=catalogue,
                    materialization_authorization=_AllowAuthority(), preparation_authorization=authority,
                )
                storage = ArtifactStorageOrchestrator(session, store, namespace, settings, _AllowArtifactAuthority())

                @asynccontextmanager
                async def runtime():
                    yield SubmissionBundlePreparationRuntime(
                        preparation, inspector, catalogue, evidence._materialization, evidence,
                        CheckerPhaseService(pre_submission=evidence, post_submission=forbidden_post_submission()),
                        SubmissionBundleDurablePutService(
                            session=session, admission=ArtifactAdmissionService(session, settings, namespace),
                            storage=storage, authorization=authority, task_contexts=tasks, project_contexts=projects,
                        ),
                    )

                result = await PreparedSubmissionBundlePreparationCommand(
                    session=session, authority=authority, task_contexts=tasks,
                    project_contexts=projects, runtime_factory=runtime,
                ).prepare(request)
            async with factory() as session:
                job_id = await session.scalar(select(ArtifactVerificationJob.id).where(
                    ArtifactVerificationJob.originating_put_attempt_id == str(result.put_attempt_id),
                ))
                assert job_id is not None, result
                await session.rollback()
                assert await ArtifactStorageOrchestrator(
                    session, store, namespace, settings, _AllowArtifactAuthority(),
                ).verify_object(UUID(job_id)) == "verified"
                admission = await session.scalar(select(SubmissionBundleAdmission).where(
                    SubmissionBundleAdmission.put_attempt_id == str(result.put_attempt_id),
                ))
                assert admission.status == "ready"
                return admission.id
        finally:
            manager.close()


class RetainedBindingAuthority:
    """Controlled binding participant; this fixture does not claim AUTH proof."""

    async def authorize(self, request):
        assert request.submission_version > 0

    async def consume(self, facts):
        assert facts.logical_role == "submission_bundle_original"
