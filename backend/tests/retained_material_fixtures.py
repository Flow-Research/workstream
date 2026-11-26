"""Current intake and finalization owners with a retained in-memory byte provider.

These prerequisites exercise custody and authorization, not provider qualification.
Old object reads remain available for checksum-bound historical migration fixtures.
"""
from datetime import timedelta
import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import UUID
from weakref import WeakKeyDictionary
from zipfile import ZipFile

from app.adapters.artifacts import submission_intake_pre_source_port, submission_finalization_handler
from app.adapters.auth import selected_pre_submit_authority, outbox_dispatch_authorization
from app.adapters.checkers import SelectedPreSubmitCheckerExecutionAdapter, selected_pre_submit_coordinator
from app.adapters.outbox import outbox_append, finalized_unknown_deliveries, outbox_delivery
from app.adapters.projects import project_locked_policy_context_port
from app.adapters.tasks import task_submission_context_port, intake_task_custody_port
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import (
    ArtifactObjectHead, ArtifactObjectMissingError, ArtifactIntegrityError,
    ArtifactPutObservation, ArtifactPutResult, SealedSourceObservation, artifact_provider_object_ref,
)
from workstream_external_services import ExternalServiceAdapterIdentity
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.api.submission_intake import (
    SealedSubmissionSource, SubmissionIntakeMetadata, SubmissionSourceCapacityLimits,
    SubmissionSourceUpload, SubmissionSourcePart,
)
from app.modules.artifacts.authorization import PreparedPreSubmitMaterializationAuthorization
from app.modules.artifacts.intake.foreground_admission import ForegroundIntakeAdmission
from app.modules.artifacts.intake.foreground_command import ForegroundSubmissionCommand, SubmissionForegroundLimits
from app.modules.artifacts.intake.foreground_lease import ForegroundIntakeLease
from app.modules.artifacts.intake.foreground_upload import ForegroundSourceUpload
from app.modules.artifacts.intake.models import SubmissionIntakeOperation
from app.modules.artifacts.models import ArtifactStorageNamespace
from app.modules.artifacts.selected_pre_submit_execution import SelectedPreSubmitExecutionService, SelectedPreSubmitSourceReads
from app.modules.artifacts.service import ArtifactStorageNamespaceSpec
from app.modules.authorization.submission_intake import SubmissionIntakeAuthorization
from app.modules.outbox.api import DeliveryOptions
from app.modules.outbox.registry import HandlerRegistry
from app.modules.projects.models import EffectiveProjectSubmissionArtifactPolicy
from app.modules.tasks.api.submission_context import TaskSubmissionContextRequest
from tests.artifacts.test_submission_pre_source import _source_runtime
from tests.checkers.execution.support import provision_post_submit_service
from tests.checkers.external.test_selected_pre_submit_coordination import _source_reservation
from tests.test_artifact_admission import _context, _settings


async def _bytes(value):
    yield value


class MemoryStore:
    """Keep exact fixture object/source versions across owner transactions."""
    def __init__(self, namespace):
        self.namespace = namespace
        self.identity = ExternalServiceAdapterIdentity("artifact_store", namespace.adapter)
        self.objects, self.uploads, self.sources = {}, {}, {}

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
        if ref not in self.objects:
            raise ArtifactObjectMissingError()
        data = self.objects[ref]
        if byte_range is not None:
            end = None if byte_range.length is None else byte_range.offset + byte_range.length
            data = data[byte_range.offset:end]
        for offset in range(0, len(data), 65536):
            yield data[offset:offset + 65536]

    async def head(self, ref, **_kwargs):
        data = self.objects.get(ref)
        return ArtifactObjectHead(ref, data is not None, len(data) if data is not None else None)

    def _namespace(self, location):
        assert location.namespace_id == "primary"
        assert location.namespace_fingerprint == self.namespace.namespace_fingerprint
        assert location.provider_profile == self.namespace.provider_profile

    def _upload(self, upload):
        self._namespace(upload.intent.location)
        stored = self.uploads[upload.provider_upload_id]
        assert stored.upload == upload
        return stored

    async def begin_source_upload(self, intent, **_kwargs):
        self._namespace(intent.location)
        assert intent.maximum_raw_bytes <= 1024 * 1024
        assert not any(item.upload.intent.location == intent.location for item in self.uploads.values())
        upload = SubmissionSourceUpload(intent=intent, provider_upload_id=str(new_record_id()))
        self.uploads[upload.provider_upload_id] = SimpleNamespace(upload=upload, parts=[], receipts=[], completion=None)
        return upload

    async def upload_source_part(self, upload, number, data, **_kwargs):
        stored = self._upload(upload)
        assert stored.completion is None and number == len(stored.parts) + 1
        assert 0 < len(data) <= upload.intent.part_bytes
        assert sum(map(len, stored.parts)) + len(data) <= upload.intent.maximum_raw_bytes
        receipt = SubmissionSourcePart(number=number, byte_count=len(data), provider_etag=hashlib.sha256(data).hexdigest())
        stored.parts.append(bytes(data))
        stored.receipts.append(receipt)
        return receipt

    async def complete_source_upload(self, completion, **_kwargs):
        stored = self._upload(completion.upload)
        if stored.completion is not None:
            assert stored.completion == completion
            return self.sources[completion.upload.intent.location.operation_id][0]
        data = b"".join(stored.parts)
        assert tuple(stored.receipts) == completion.parts
        assert len(data) == completion.raw_byte_count
        assert "sha256:" + hashlib.sha256(data).hexdigest() == completion.raw_sha256
        source = SealedSubmissionSource(
            location=completion.upload.intent.location, provider_generation=str(new_record_id()),
            raw_sha256=completion.raw_sha256, raw_byte_count=completion.raw_byte_count,
            sealed_upload_fence=completion.upload.intent.upload_fence,
        )
        assert source.location.operation_id not in self.sources
        self.sources[source.location.operation_id] = source, data
        stored.completion = completion
        return source

    def _source(self, source):
        self._namespace(source.location)
        if source.location.operation_id not in self.sources:
            raise ArtifactObjectMissingError()
        retained, data = self.sources[source.location.operation_id]
        if source != retained:
            raise ArtifactIntegrityError("fixture source identity differs")
        return data

    async def open_source(self, source, *, maximum_chunk_bytes=65536, **_kwargs):
        assert 1 <= maximum_chunk_bytes <= 65536
        data = self._source(source)
        for offset in range(0, len(data), maximum_chunk_bytes):
            yield data[offset:offset + maximum_chunk_bytes]

    async def observe_sealed_source(self, source, **_kwargs):
        self._source(source)
        return SealedSourceObservation(source.location, source.provider_generation, source.raw_byte_count, source.sealed_upload_fence)

    async def observe_source_upload(self, completion, **_kwargs):
        stored = self._upload(completion.upload)
        if stored.completion is None:
            return None
        assert stored.completion == completion
        return self.sources[completion.upload.intent.location.operation_id][0]


_RETAINED_STORES = WeakKeyDictionary()


def retained_archive_store(factory, namespace):
    """Keep all provider state until its owning test session factory is disposed."""
    namespaces = _RETAINED_STORES.setdefault(factory, {})
    store = namespaces.setdefault(namespace.namespace_fingerprint, MemoryStore(namespace))
    assert store.namespace == namespace
    return store


def _submission_source(task, assignment, link, packet, predecessor_id, policy, revision_context):
    content = BytesIO()
    paths = {entry["path"] for entry in policy["required_artifacts"] if entry.get("required", True)}
    paths.update(entry.get("path") or "evidence/" + entry["key"]
                 for entry in policy["required_evidence"] if entry.get("required", True))
    with ZipFile(content, "w") as archive:
        for path in sorted(paths):
            archive.writestr(path, f"{task.id}:{predecessor_id}:{packet.summary}\n")
    context = _context(actor_profile_id=UUID(task.assigned_to), identity_link_id=UUID(link.id))
    metadata = SubmissionIntakeMetadata(
        task_id=UUID(task.id), assignment_id=UUID(assignment.id),
        feedback=packet.summary,
    )
    return context, metadata, content.getvalue()


def _foreground(factory, context, namespace, store, runtime):
    admission = ForegroundIntakeAdmission(
        factory, tasks=intake_task_custody_port, task_contexts=task_submission_context_port,
        projects=project_locked_policy_context_port,
        authorization=lambda session: SubmissionIntakeAuthorization(session, context), namespace=namespace,
        events=outbox_append, deliveries=finalized_unknown_deliveries,
        capacity_limits=SubmissionSourceCapacityLimits(maximum_total_bytes=16 * 1024**2),
        maximum_raw_bytes=1024**2, upload_duration=timedelta(seconds=300), lease_duration=timedelta(seconds=60),
    )
    async def execute(reservation):
        async with factory() as session:
            return await SelectedPreSubmitExecutionService(
                session=session, coordinator=selected_pre_submit_coordinator(session),
                authority=selected_pre_submit_authority(session),
                source_reads=SelectedPreSubmitSourceReads(
                    session=session, sources=submission_intake_pre_source_port(session),
                    authority=PreparedPreSubmitMaterializationAuthorization(
                        session, request_id=new_record_id(), correlation_id=new_record_id()), store=store),
                execution=SelectedPreSubmitCheckerExecutionAdapter(external_execution=runtime),
            ).execute(reservation=reservation)
    return ForegroundSubmissionCommand(
        admission=admission, upload=ForegroundSourceUpload(factory, intake_task_custody_port, store),
        lease=ForegroundIntakeLease(factory, intake_task_custody_port,
            lease_duration=timedelta(seconds=60), heartbeat_interval=timedelta(seconds=10)),
        limits=SubmissionForegroundLimits(part_bytes=5 * 1024**2, idle_timeout_seconds=20,
            pre_lease_seconds=60, replay_duration=timedelta(seconds=30)),
        runtime_profile=_source_reservation().runtime_profile,
        execute=execute, checkers=selected_pre_submit_coordinator, outbox=outbox_append,
    )


async def retained_intake(factory, task, assignment, link, packet, predecessor_id):
    """Accept exact raw ZIP bytes through current T1, source PRE and atomic T4."""
    for identity in (ServiceIdentity.ARTIFACT_MATERIALIZER, ServiceIdentity.CHECKER_PRE_SUBMIT):
        await provision_post_submit_service(factory, identity)
    async with factory() as session, session.begin():
        current = await task_submission_context_port(session).lock_submission_context(TaskSubmissionContextRequest(
            task_id=UUID(task.id), assignment_id=UUID(assignment.id), contributor_id=UUID(task.assigned_to),
            predecessor_submission_id=UUID(predecessor_id) if predecessor_id else None,
        ))
        persisted = await session.get(ArtifactStorageNamespace, "primary")
        namespace = ArtifactStorageNamespaceSpec(persisted.backend, persisted.adapter, persisted.provider_profile,
                                               persisted.namespace_descriptor, persisted.namespace_fingerprint)
        policy = (await session.get(EffectiveProjectSubmissionArtifactPolicy,
                  str(current.locked_project_context.effective_policy_id))).effective_policy
    context, metadata, payload = _submission_source(task, assignment, link, packet, predecessor_id, policy, current.revision_context)
    store = retained_archive_store(factory, namespace)
    with TemporaryDirectory(prefix="retained-source-pre-") as directory:
        runtime, errors = _source_runtime(payload, Path(directory), "completed")
        command = _foreground(factory, context, namespace, store, runtime)
        receipt = await command.submit(metadata, _bytes(payload), actor_id=context.actor_profile_id,
            identity_link_id=context.identity_link_id, idempotency_key=new_record_id(), declared_raw_bytes=len(payload))
        assert not errors, "\n".join(errors)
        return SimpleNamespace(operation_id=UUID(receipt["operation_id"]), store=store, namespace=namespace,
                               settings=_settings(Path(directory), maximum_bytes=1024**2))


async def finalize_retained_intake(factory, intake):
    """Deliver the exact durable event through production OUTBOX and T5 owners."""
    for identity in (ServiceIdentity.ARTIFACT_BINDING, ServiceIdentity.OUTBOX_DISPATCHER):
        await provision_post_submit_service(factory, identity)
    handler = submission_finalization_handler(sessions=factory, settings=intake.settings,
                                             store=intake.store, lease_duration=timedelta(seconds=120))
    failures = []
    async def observed_handler(envelope):
        try:
            return await handler(envelope)
        except Exception as error:
            failures.append(error)
            raise
    event_type = "SubmissionFinalizationRequested"
    delivery = outbox_delivery(factory, authorization_factory=outbox_dispatch_authorization,
        registry=HandlerRegistry([(event_type, 1, observed_handler)], replay_safe=frozenset({(event_type, 1)})),
        options=DeliveryOptions(lease_seconds=180, handler_timeout_seconds=150))
    async with factory() as session:
        row = await session.get(SubmissionIntakeOperation, intake.operation_id)
        event_id, project_id = UUID(row.finalization_event_id), UUID(row.project_id)
    assert await delivery.deliver(event_id, project_id, "retained-finalizer") is not None
    if failures:
        raise AssertionError("expected successful retained source finalization") from failures[0]
    async with factory() as session:
        row = await session.get(SubmissionIntakeOperation, intake.operation_id)
        assert row.state == "finalized"
        return row.finalized_submission_id
