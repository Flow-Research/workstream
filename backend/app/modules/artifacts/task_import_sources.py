"""Declared JSON sources using ART's existing admission and byte lifecycle."""

from collections.abc import AsyncIterable, AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import BinaryIO
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import ArtifactStore, ArtifactStoreError
from app.modules.artifacts.api.task_import_source import (
    TaskImportSourceError,
    TaskImportSourceAction, TaskImportSourceAuthorityDenied, TaskImportSourceAuthorityFacts,
    TaskImportSourceAuthorizationPort, TaskImportSourceDeclare, TaskImportSourceResponse,
    VerifiedTaskImportSourceRead,
)
from app.modules.artifacts.models import (
    ArtifactContent, ArtifactOperationReceipt, ArtifactPutAttempt, ArtifactPutObservationReceipt,
    ArtifactReplica, ArtifactStorageNamespace, ArtifactTaskImportSource,
    ArtifactVerificationJob, ArtifactVerificationReceipt,
)
from app.modules.artifacts.preparation import ArtifactPreparationService
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError, TaskImportSourceAdmissionRequest
from app.modules.artifacts.service import (
    ArtifactAdmissionService, ArtifactStorageNamespaceSpec, ArtifactStorageOrchestrator,
    ArtifactAdmissionError, ArtifactAdmissionConflictError, ArtifactAdmissionCapacityError,
    validate_artifact_replica_execution_namespace,
)
from app.modules.tasks.api.task_import import parse_task_import, TASK_IMPORT_MAXIMUM_BYTES


class _TaskImportInspector:
    def inspect(self, reader: BinaryIO):
        return parse_task_import(reader.read(TASK_IMPORT_MAXIMUM_BYTES + 1))


@dataclass(frozen=True)
class TaskImportSourceRuntime:
    """Existing ART scratch, admission, put and verification owners for one operation."""

    store: ArtifactStore
    namespace: ArtifactStorageNamespaceSpec
    preparation: ArtifactPreparationService
    admission: ArtifactAdmissionService
    puts: ArtifactStorageOrchestrator
    verification: ArtifactStorageOrchestrator
    put_denial_boundary: Callable[[], AbstractAsyncContextManager[None]]
    verification_denial_boundary: Callable[[], AbstractAsyncContextManager[None]]


class ArtifactTaskImportSourceCommands:
    """Each declaration precedes provider work and remains its retained parent."""

    def __init__(self, session: AsyncSession, *, actor_profile_id: UUID,
                 identity_link_id: UUID,
                 authorization: TaskImportSourceAuthorizationPort,
                 runtime: Callable[[], AbstractAsyncContextManager[TaskImportSourceRuntime]]):
        self._session, self._actor_id, self._authorization, self._runtime = session, actor_profile_id, authorization, runtime
        self._identity_link_id = identity_link_id

    @asynccontextmanager
    async def _operation_boundary(self, *, concealed: bool = False):
        try:
            yield
        except TaskImportSourceAuthorityDenied as exc:
            await self._session.rollback()
            async with self._session.begin():
                await self._authorization.restage_denial(exc)
            raise TaskImportSourceError("task_import_source_not_found" if concealed else "task_import_source_authority_denied",
                                       404 if concealed else 403) from exc
        except ArtifactAuthorityDeniedError as exc:
            raise TaskImportSourceError("task_import_source_service_unavailable", 503) from exc
        except ArtifactAdmissionError as exc:
            if isinstance(exc, ArtifactAdmissionConflictError):
                code, status = "task_import_source_conflict", 409
            elif isinstance(exc, ArtifactAdmissionCapacityError):
                code, status = "task_import_source_limit_exceeded", 413
            else:
                code, status = "task_import_source_unavailable", 503
            raise TaskImportSourceError(code, status) from exc

    def _facts(self, source: ArtifactTaskImportSource) -> TaskImportSourceAuthorityFacts:
        return TaskImportSourceAuthorityFacts(
            UUID(source.id), UUID(source.project_id), self._actor_id, source.sha256,
            source.byte_count, source.operation_identity, UUID(source.idempotency_key),
        )

    async def _lock_source(self, project_id: UUID, source_id: UUID) -> ArtifactTaskImportSource:
        source = await self._session.scalar(select(ArtifactTaskImportSource).where(
            ArtifactTaskImportSource.id == str(source_id), ArtifactTaskImportSource.project_id == str(project_id),
        ).with_for_update())
        if source is None:
            raise TaskImportSourceError("task_import_source_not_found", 404)
        return source

    @staticmethod
    def _response(source: ArtifactTaskImportSource, status: str) -> TaskImportSourceResponse:
        return TaskImportSourceResponse(
            source_id=UUID(source.id), project_id=UUID(source.project_id), sha256=source.sha256,
            byte_count=source.byte_count, status=status, created_at=source.created_at,
        )

    async def declare(self, project_id: UUID, payload: TaskImportSourceDeclare, key: UUID) -> TaskImportSourceResponse:
        """Retain one immutable project/key declaration with exact fresh AUTH custody."""
        async with self._operation_boundary():
            async with self._session.begin():
                # Serialize only this source replay namespace before source/AUTH
                # locks; no row or authority is derived from the lock token.
                token = int(canonical_json_hash({"task_import_source_project": str(project_id), "key": str(key)})[7:23], 16)
                token = token if token < 2**63 else token - 2**64
                await self._session.execute(text("select pg_advisory_xact_lock(:token)"), {"token": token})
                source = await self._session.scalar(select(ArtifactTaskImportSource).where(
                    ArtifactTaskImportSource.project_id == str(project_id), ArtifactTaskImportSource.idempotency_key == str(key),
                ).with_for_update())
                created = source is None
                if source is None:
                    source_id = new_record_id()
                    source = ArtifactTaskImportSource(
                        id=str(source_id), project_id=str(project_id), actor_profile_id=str(self._actor_id),
                        identity_link_id=str(self._identity_link_id), idempotency_key=str(key),
                        sha256=payload.sha256, byte_count=payload.byte_count, media_type="application/json",
                        operation_identity=canonical_json_hash({"request_type": "task_import_source", "source_id": str(source_id)}),
                    )
                decision_id = await self._authorization.authorize(TaskImportSourceAction.DECLARE, self._facts(source))
                if (source.sha256, source.byte_count) != (payload.sha256, payload.byte_count):
                    raise TaskImportSourceError("task_import_source_idempotency_mismatch", 409)
                if created:
                    source.authorization_decision_id = str(decision_id)
                    self._session.add(source)
                    await self._session.flush()
                return self._response(source, await self._status(source))

    async def status(self, project_id: UUID, source_id: UUID) -> TaskImportSourceResponse:
        """Authorize exact source metadata and resolve its retained ART lifecycle state."""
        async with self._operation_boundary(concealed=True):
            async with self._session.begin():
                source = await self._lock_source(project_id, source_id)
                await self._authorization.authorize(TaskImportSourceAction.READ, self._facts(source))
                return self._response(source, await self._status(source))

    async def _status(self, source: ArtifactTaskImportSource) -> str:
        attempt = await self._session.scalar(select(ArtifactPutAttempt).where(ArtifactPutAttempt.task_import_source_id == source.id))
        if attempt is None:
            return "declared"
        if attempt.status != "object_confirmed":
            return attempt.status
        job = await self._session.scalar(select(ArtifactVerificationJob).where(
            ArtifactVerificationJob.originating_put_attempt_id == attempt.id,
        ).order_by(ArtifactVerificationJob.created_at.desc(), ArtifactVerificationJob.id.desc()).limit(1))
        if job is None or job.status in {"pending", "running"}:
            return "object_confirmed"
        if job.status == "verified":
            await self._verified_replica(source)
        return job.status

    async def upload(self, project_id: UUID, source_id: UUID, byte_source: AsyncIterable[bytes]) -> TaskImportSourceResponse:
        """Inspect sealed JSON before fresh-authority admission and existing ART recovery."""
        async with self._operation_boundary(concealed=True):
            # Check authority before reading bytes. Roll back preflight ALLOW:
            # final admission consumes fresh exact authority after scratch work.
            async with self._session.begin() as preflight:
                source = await self._lock_source(project_id, source_id)
                facts = self._facts(source)
                await self._authorization.authorize(TaskImportSourceAction.UPLOAD, facts)
                await preflight.rollback()
            async with self._runtime() as runtime:
                prepared = await runtime.preparation.prepare(
                    byte_source, media_type="application/json", expected_sha256=facts.sha256,
                    expected_size=facts.byte_count, maximum_bytes=facts.byte_count,
                )
                try:
                    await prepared.inspect(_TaskImportInspector())
                    async with self._session.begin():
                        source = await self._lock_source(project_id, source_id)
                        admission = await runtime.admission.admit(
                            TaskImportSourceAdmissionRequest(source_id, prepared.committed_source),
                            task_import_source_authority=_UploadAuthority(self, source), existing_transaction=True,
                        )
                    async with runtime.put_denial_boundary():
                        if admission.replayed:
                            await runtime.puts.resume_committed_put(attempt_id=admission.attempt_id, source=prepared.committed_source)
                        else:
                            await runtime.puts.execute_committed_put(attempt_id=admission.attempt_id, source=prepared.committed_source)
                    async with self._session.begin():
                        job_id = await self._session.scalar(select(ArtifactVerificationJob.id).where(
                            ArtifactVerificationJob.originating_put_attempt_id == str(admission.attempt_id),
                        ).order_by(ArtifactVerificationJob.created_at.desc(), ArtifactVerificationJob.id.desc()).limit(1))
                    if job_id is not None:
                        async with runtime.verification_denial_boundary():
                            await runtime.verification.verify_object(UUID(job_id))
                finally:
                    await prepared.close()
            return await self.status(project_id, source_id)

    async def _verified_replica(self, source: ArtifactTaskImportSource) -> ArtifactReplica:
        row = (await self._session.execute(select(
            ArtifactPutAttempt, ArtifactReplica, ArtifactContent, ArtifactVerificationJob, ArtifactVerificationReceipt,
        ).join(ArtifactReplica, ArtifactReplica.id == ArtifactPutAttempt.replica_id)
         .join(ArtifactContent, ArtifactContent.id == ArtifactReplica.content_id)
         .join(ArtifactVerificationJob, ArtifactVerificationJob.originating_put_attempt_id == ArtifactPutAttempt.id)
         .join(ArtifactVerificationReceipt, (ArtifactVerificationReceipt.verification_job_id == ArtifactVerificationJob.id)
               & (ArtifactVerificationReceipt.execution_generation == ArtifactVerificationJob.execution_generation))
         .where(ArtifactPutAttempt.task_import_source_id == source.id, ArtifactVerificationJob.status == "verified")
         .order_by(ArtifactVerificationJob.created_at.desc(), ArtifactVerificationJob.id.desc()).limit(1))).one_or_none()
        if row is None:
            raise TaskImportSourceError("task_import_source_unverified", 409)
        attempt, replica, content, job, receipt = row
        if (attempt.producer_request_type != "task_import_source" or attempt.project_id != source.project_id
                or attempt.logical_role != "task_import_source" or attempt.status != "object_confirmed"
                or (attempt.sha256, attempt.byte_count, attempt.media_type) != (source.sha256, source.byte_count, source.media_type)
                or (content.sha256, content.byte_count) != (source.sha256, source.byte_count)
                or job.replica_id != replica.id or job.execution_generation != receipt.execution_generation
                or receipt.verification_job_id != job.id or receipt.outcome != "verified"
                or (receipt.observed_sha256, receipt.observed_byte_count) != (source.sha256, source.byte_count)
                or (replica.verification_state, replica.availability_state, replica.integrity_state) != ("verified", "available", "valid")
                or (replica.storage_namespace_id, replica.namespace_fingerprint) != (attempt.storage_namespace_id, attempt.namespace_fingerprint)):
            raise TaskImportSourceError("task_import_source_custody_invalid", 409)
        if attempt.receipt_id is not None:
            acknowledged = await self._session.scalar(select(ArtifactOperationReceipt.id).where(
                ArtifactOperationReceipt.id == attempt.receipt_id, ArtifactOperationReceipt.put_attempt_id == attempt.id,
                ArtifactOperationReceipt.replica_id == replica.id, ArtifactOperationReceipt.request_digest == attempt.request_digest,
                ArtifactOperationReceipt.provider_object_ref == replica.provider_object_ref,
                ArtifactOperationReceipt.logical_role == "task_import_source", ArtifactOperationReceipt.outcome == "stored_pending_verification",
            ))
        else:
            acknowledged = await self._session.scalar(select(ArtifactPutObservationReceipt.id).where(
                ArtifactPutObservationReceipt.put_attempt_id == attempt.id,
                ArtifactPutObservationReceipt.execution_generation == attempt.execution_generation,
                ArtifactPutObservationReceipt.outcome == "observed_confirmed",
                ArtifactPutObservationReceipt.observed_sha256 == source.sha256,
                ArtifactPutObservationReceipt.expected_sha256 == source.sha256,
                ArtifactPutObservationReceipt.observed_byte_count == source.byte_count,
                ArtifactPutObservationReceipt.expected_byte_count == source.byte_count,
            ))
        if acknowledged is None:
            raise TaskImportSourceError("task_import_source_custody_invalid", 409)
        return replica

    @asynccontextmanager
    async def open(self, project_id: UUID, source_id: UUID) -> AsyncIterator[VerifiedTaskImportSourceRead]:
        """Fence exact receipt ancestry and verify provider bytes before yielding content."""
        async with self._operation_boundary(concealed=True):
            async with self._runtime() as runtime:
                prepared = stream = None
                try:
                    async with self._session.begin():
                        source = await self._lock_source(project_id, source_id)
                        await self._authorization.authorize(TaskImportSourceAction.READ, self._facts(source))
                        replica = await self._verified_replica(source)
                        persisted = await self._session.get(ArtifactStorageNamespace, replica.storage_namespace_id)
                        if persisted is None:
                            raise TaskImportSourceError("task_import_source_custody_invalid", 409)
                        validate_artifact_replica_execution_namespace(
                            replica=replica, persisted=persisted, namespace=runtime.namespace, store=runtime.store,
                        )
                        prepared = await runtime.preparation.prepare(
                            runtime.store.open(replica.provider_object_ref), media_type="application/json",
                            expected_sha256=source.sha256, expected_size=source.byte_count, maximum_bytes=source.byte_count,
                        )
                        stream = prepared.committed_source.stream()
                        first = await anext(stream)
                        response = self._response(source, "verified")

                    async def content():
                        yield first
                        async for chunk in stream:
                            yield chunk

                    yield VerifiedTaskImportSourceRead(response, content())
                except ArtifactStoreError as exc:
                    raise TaskImportSourceError("task_import_source_bytes_unavailable", 503) from exc
                finally:
                    if stream is not None:
                        await stream.aclose()
                    if prepared is not None:
                        await prepared.close()


class _UploadAuthority:
    def __init__(self, commands: ArtifactTaskImportSourceCommands, source: ArtifactTaskImportSource):
        self._commands, self._source = commands, source

    async def consume(self, request: TaskImportSourceAdmissionRequest) -> UUID:
        if request.source_id != UUID(self._source.id):
            raise TaskImportSourceAuthorityDenied("task-import source selector changed")
        await self._commands._authorization.authorize(TaskImportSourceAction.UPLOAD, self._commands._facts(self._source))
        return UUID(self._source.actor_profile_id)
