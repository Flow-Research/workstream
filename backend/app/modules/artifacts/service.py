"""Internal orchestration for namespace-fenced immutable artifact storage."""

from __future__ import annotations

import asyncio
import hashlib
import sys
from collections.abc import AsyncIterable, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.hashing import canonical_json_hash
from app.db.session import get_session_factory
from app.interfaces.artifacts import (
    ArtifactStore,
    ArtifactCommitment,
    ArtifactIntegrityError,
    ArtifactStoreError,
    ArtifactStoreUnavailableError,
    ArtifactObjectMissingError,
    ArtifactStoreBootstrap,
    ArtifactStoreNamespaceClaim,
    artifact_provider_object_ref,
    artifact_store_namespace_material,
)
from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.interfaces.artifact_operations import (
    ArtifactRecoveryRequest,
    GuideArtifactIngestCommand,
    GuideArtifactIngestRequest,
    GuideArtifactIngestResult,
)
from app.modules.actors.service import ActorService
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.artifacts.models import (
    ArtifactAdmissionCharge,
    ArtifactAdmissionScope,
    ArtifactPutAttempt,
    ArtifactContent,
    ArtifactOperationReceipt,
    ArtifactPutObservationReceipt,
    ArtifactReplica,
    ArtifactRecoveryAttempt,
    ArtifactStorageNamespace,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
)
from app.modules.artifacts.metrics import (
    ArtifactAdmissionMetrics,
    artifact_admission_metrics,
)
from app.modules.artifacts.repository import ArtifactRepository
from app.modules.artifacts.authorization import (
    GuideArtifactPreparedAuthorization,
    guide_ingest_prepared_request_digest,
)
from app.modules.artifacts.preparation import ArtifactPreparationService
from app.modules.artifacts.schemas import (
    ArtifactAdmissionRequest,
    ArtifactAdmissionResult,
    ArtifactAuthorityDeniedError,
    ArtifactInternalAuthority,
    ArtifactInternalResourceType,
    ArtifactPutAttemptAuthorityFacts,
    ArtifactPendingWorkAuthorityFacts,
    ArtifactVerificationAuthorityFacts,
    ArtifactRecoveryResult,
    ArtifactRecoveryAuthority,
    ArtifactRecoveryAuthorityFacts,
    ArtifactRecoveryConflictError,
    ArtifactRecoveryIneligibleError,
    ArtifactRecoveryNotFoundError,
    DenyArtifactInternalAuthority,
    CheckerOutputArtifactAdmissionRequest,
    ContributorArtifactAdmissionRequest,
    GuideArtifactAdmissionRequest,
    GuideArtifactIngestAuthorityFacts,
)
from app.modules.artifacts.sources import CommittedArtifactSource, PreparedArtifact
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    AuthorizationContext,
    HumanAuthorizationContext,
    IdentityLinkStatus,
    ServiceAuthorizationContext,
)
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.audit.repository import AuditRepository
from app.modules.tasks.models import AuditEvent


ARTIFACT_STORAGE_NAMESPACE_ID = "primary"


class ArtifactIngestStateError(Exception):
    """Raised when persisted artifact state cannot perform an internal transition."""


class ArtifactStorageNamespaceError(ArtifactIngestStateError):
    """Raised before provider I/O when deployment storage identity has drifted."""


@dataclass(frozen=True, slots=True)
class ArtifactStorageNamespaceSpec:
    """Canonical non-secret identity for one configured artifact namespace."""

    backend: str
    adapter: str
    provider_profile: str
    namespace_descriptor: dict[str, object]
    namespace_fingerprint: str


class ArtifactAdmissionError(ArtifactIngestStateError):
    """Base failure for durable-byte admission before provider I/O."""


class ArtifactAdmissionConfigurationError(ArtifactAdmissionError):
    """Raised when admission configuration is absent or has drifted."""


class ArtifactAdmissionCapacityError(ArtifactAdmissionError):
    """Raised when one required durable-byte scope lacks capacity."""


class ArtifactAdmissionConflictError(ArtifactAdmissionError):
    """Raised when an operation identity is replayed with changed input."""


class ArtifactAdmissionRelationshipError(ArtifactAdmissionError):
    """Raised when canonical producer ownership cannot be derived."""


@dataclass(frozen=True, slots=True)
class _AdmissionScopeSpec:
    """One server-derived scope and its exact configured byte limit."""

    scope_type: str
    scope_id: str
    limit_bytes: int


@dataclass(frozen=True, slots=True)
class _AdmissionFacts:
    """Canonical producer and product facts loaded for one closed request."""

    request_type: str
    producer_type: str
    producer_ref: str
    project_id: str
    guide_id: str | None
    task_id: str | None
    guide_source_item_id: str | None
    guide_source_snapshot_id: str | None
    upload_item_id: str | None
    checker_run_id: str | None
    logical_role: str | None
    operation_identity: str


def artifact_storage_namespace_spec(
    settings: Settings,
    store: ArtifactStoreBootstrap,
) -> ArtifactStorageNamespaceSpec:
    """Build the canonical descriptor from one already-pinned provider root."""
    identity = store.identity
    if type(identity) is not ExternalServiceAdapterIdentity:
        raise ArtifactStorageNamespaceError("artifact adapter identity is invalid")
    if settings.artifact_store_backend != identity.provider_key:
        raise ArtifactStorageNamespaceError(
            "artifact adapter identity does not match configuration"
        )
    namespace_identity = store.namespace_identity
    descriptor, fingerprint = artifact_store_namespace_material(
        backend=settings.artifact_store_backend,
        adapter_identity=identity,
        namespace_identity=namespace_identity,
    )
    return ArtifactStorageNamespaceSpec(
        backend=settings.artifact_store_backend,
        adapter=identity.provider_key,
        provider_profile=namespace_identity.provider_profile,
        namespace_descriptor=descriptor,
        namespace_fingerprint=fingerprint,
    )


class GuideArtifactIngestService:
    """Hidden guide byte intake composed only from closed ART capabilities."""

    def __init__(
        self,
        runtime_factory: Callable[
            [],
            AbstractAsyncContextManager[
                tuple[
                    ArtifactPreparationService,
                    ArtifactAdmissionService,
                    ArtifactStorageOrchestrator,
                ]
            ],
        ],
        authority: GuideArtifactPreparedAuthorization,
    ) -> None:
        self._runtime_factory = runtime_factory
        self._authority = authority

    def runtime(self):
        """Open the bounded scratch and provider runtime for one request."""
        return self._runtime_factory()

    async def prepare_and_admit(
        self,
        request: GuideArtifactIngestRequest,
        preparation: ArtifactPreparationService,
        admission_service: ArtifactAdmissionService,
    ) -> tuple[PreparedArtifact, ArtifactAdmissionResult]:
        """Prepare bytes and admit them inside the caller's PREP transaction."""
        if request.logical_role != "guide_source":
            raise ArtifactAdmissionRelationshipError("guide artifact logical role is invalid")
        prepared = await preparation.prepare(
            request.byte_source,
            media_type=request.media_type,
        )
        try:
            admission = await admission_service.admit(
                GuideArtifactAdmissionRequest(
                    project_id=request.project_id,
                    guide_id=request.guide_id,
                    guide_source_snapshot_id=request.guide_source_snapshot_id,
                    guide_source_item_id=request.source_item_id,
                    source=prepared.committed_source,
                    operation_identity=request.operation_identity,
                    request_digest=request.request_digest,
                ),
                guide_prepared_authorization=self._authority,
                prepared_authorization=request.prepared_authorization,
                existing_transaction=True,
            )
            return prepared, admission
        except BaseException:
            await prepared.close()
            raise

    @staticmethod
    async def publish(
        prepared: PreparedArtifact,
        admission: ArtifactAdmissionResult,
        orchestrator: ArtifactStorageOrchestrator,
    ) -> GuideArtifactIngestResult:
        """Execute provider work only after the admission transaction commits."""
        source = prepared.committed_source
        try:
            if admission.replayed:
                status = await orchestrator.resume_committed_put(
                    attempt_id=admission.attempt_id,
                    source=source,
                )
            else:
                status = await orchestrator.execute_committed_put(
                    attempt_id=admission.attempt_id,
                    source=source,
                )
            return GuideArtifactIngestResult(
                put_attempt_id=admission.attempt_id,
                operation_identity=admission.operation_identity,
                sha256=source.commitment.sha256,
                byte_count=source.commitment.byte_count,
                status=status,
                replayed=admission.replayed,
            )
        finally:
            await prepared.close()


class PreparedGuideArtifactIngestCommand(GuideArtifactIngestCommand):
    """Own preflight and the issuer-local capability through final consumption."""

    def __init__(
        self,
        service: GuideArtifactIngestService,
        authority: GuideArtifactPreparedAuthorization,
    ) -> None:
        self._service = service
        self._authority = authority

    async def ingest(
        self,
        *,
        authorization_context: AuthorizationContext,
        project_id: UUID,
        guide_id: UUID,
        guide_source_snapshot_id: UUID,
        source_item_id: UUID,
        idempotency_key: UUID,
        byte_source: AsyncIterable[bytes],
    ) -> GuideArtifactIngestResult:
        authority_transaction = self._authority.transaction()
        transaction_open = False
        try:
            await authority_transaction.__aenter__()
            transaction_open = True
            prepared_authorization = await self._authority.prepare(
                authorization_context=authorization_context,
                project_id=project_id,
                guide_id=guide_id,
                guide_source_snapshot_id=guide_source_snapshot_id,
                guide_source_item_id=source_item_id,
                idempotency_key=idempotency_key,
            )
            async with self._service.runtime() as runtime:
                preparation, admission_service, orchestrator = runtime
                prepared, admission = await self._service.prepare_and_admit(
                    GuideArtifactIngestRequest(
                        prepared_authorization=prepared_authorization,
                        project_id=project_id,
                        guide_id=guide_id,
                        guide_source_snapshot_id=guide_source_snapshot_id,
                        source_item_id=source_item_id,
                        operation_identity=canonical_json_hash(
                            {
                                "request_type": "guide",
                                "guide_source_item_id": str(source_item_id),
                            }
                        ),
                        request_digest=guide_ingest_prepared_request_digest(
                            project_id=project_id,
                            guide_id=guide_id,
                            guide_source_snapshot_id=guide_source_snapshot_id,
                            guide_source_item_id=source_item_id,
                            idempotency_key=idempotency_key,
                        ),
                        logical_role="guide_source",
                        media_type="application/octet-stream",
                        byte_source=byte_source,
                    ),
                    preparation,
                    admission_service,
                )
                transaction_open = False
                try:
                    await authority_transaction.__aexit__(None, None, None)
                except BaseException:
                    await prepared.close()
                    raise
                return await self._service.publish(prepared, admission, orchestrator)
        finally:
            if transaction_open:
                await authority_transaction.__aexit__(*sys.exc_info())
            self._authority.close()


class ArtifactStorageOrchestrator:
    """Sole owner of writable storage and fenced provider observation."""

    def __init__(
        self,
        session: AsyncSession,
        store: ArtifactStore,
        namespace: ArtifactStorageNamespaceSpec,
        settings: Settings,
        authority: ArtifactInternalAuthority | None = None,
    ) -> None:
        """Bind one database session, byte store, and deployment namespace."""
        self._session = session
        self._store = store
        self._namespace = namespace
        self._repo = ArtifactRepository(session)
        self._settings = settings
        self._authority = authority or DenyArtifactInternalAuthority()

    async def ensure_storage_namespace(self) -> ArtifactStorageNamespace:
        """Claim or validate the immutable singleton before provider access."""
        async with self._session.begin():
            return await self._claim_and_validate_namespace()

    async def resume_committed_put(
        self,
        *,
        attempt_id: UUID,
        source: CommittedArtifactSource,
    ) -> str:
        """Replay absent bytes or observe an otherwise ambiguous prior put."""
        async with self._session.begin():
            attempt = await self._repo.lock_put_attempt(str(attempt_id))
            replay_required = (
                attempt is not None and attempt.status == "absent_replay_required"
            )
        if replay_required:
            return await self.execute_committed_put(attempt_id=attempt_id, source=source)
        status = await self.resolve_put_attempt(attempt_id)
        if status == "missing":
            return await self.execute_committed_put(attempt_id=attempt_id, source=source)
        return status

    async def execute_committed_put(
        self,
        *,
        attempt_id: UUID,
        source: CommittedArtifactSource,
    ) -> str:
        """Claim a caller-held source and invoke the sole writable port once."""
        async with self._session.begin():
            persisted_namespace = await self._claim_and_validate_namespace()
            candidate = await self._repo.lock_put_attempt(str(attempt_id))
            if (
                candidate is None
                or source.commitment.sha256 != candidate.sha256
                or (source.commitment.byte_count != candidate.byte_count)
            ):
                raise ArtifactIngestStateError("committed source does not match put attempt")
            self._validate_put_execution_namespace(candidate, persisted_namespace)
            candidate_generation = candidate.execution_generation
        executor_id = uuid4()
        facts = _put_authority_facts(candidate, executor_id, candidate_generation + 1)
        async with self._session.begin() as claim_transaction:
            await self._authority.prepare(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=facts,
                phase="claim",
                idempotency_key=executor_id,
            )
            persisted_namespace = await self._claim_and_validate_namespace()
            current = await self._repo.lock_put_attempt(str(attempt_id))
            if (
                current is None
                or _put_authority_facts(current, executor_id, candidate_generation + 1) != facts
            ):
                self._authority.discard()
                return "stale"
            await self._authority.consume(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=facts,
            )
            claimed_result = await self._repo.claim_put_attempt(
                attempt_id=attempt_id,
                executor_id=executor_id,
                lease_seconds=self._settings.artifact_execution_lease_seconds,
                mode="caller_put",
                expected_generation=candidate_generation,
            )
            if claimed_result is None:
                await claim_transaction.rollback()
                return "stale"
            claimed = await self._repo.lock_put_attempt(str(attempt_id))
            if not _matching_put_fence(claimed, executor_id, candidate_generation + 1):
                await claim_transaction.rollback()
                return "stale"
            assert claimed is not None
            self._validate_put_execution_namespace(claimed, persisted_namespace)
            claimed_facts = _put_authority_facts(claimed, executor_id, claimed.execution_generation)
            if (
                claimed_facts != facts
                or source.commitment.sha256 != claimed.sha256
                or source.commitment.byte_count != claimed.byte_count
            ):
                await claim_transaction.rollback()
                return "stale"
            charges = await self._repo.lock_attempt_charges(str(attempt_id))
            if any(charge.state == "released" for charge in charges):
                scopes = await self._repo.lock_charge_scopes(charges)
                scope_by_key = {(scope.scope_type, scope.scope_id): scope for scope in scopes}
                now = await self._repo.database_now()
                for charge in charges:
                    if charge.state != "released":
                        continue
                    scope = scope_by_key[(charge.scope_type, charge.scope_id)]
                    if scope.counted_bytes + charge.byte_count > scope.limit_bytes:
                        raise ArtifactAdmissionCapacityError(
                            "artifact replay cannot reacquire durable-byte capacity"
                        )
                    scope.counted_bytes += charge.byte_count
                    scope.cas_version += 1
                    charge.state = "provisional"
                    charge.reserved_at = now
                    charge.released_at = None
                    charge.cas_version += 1
        try:
            result = await self._store.put(source)
        except ArtifactStoreUnavailableError:
            return await self._record_put_unavailable(claimed, executor_id, facts)
        except ArtifactStoreError:
            # Any non-acknowledgement provider error is resolved through the
            # read-only observation path; a caller write never fabricates
            # observation evidence.
            return await self._record_put_unavailable(claimed, executor_id, facts)
        return await self._complete_transaction_b(
            claimed=claimed,
            executor_id=executor_id,
            expected_facts=facts,
            provider_object_ref=result.provider_object_ref,
            replayed=result.replayed,
            observed=False,
        )

    async def resolve_put_attempt(self, attempt_id: UUID) -> str:
        """Resolve ambiguous publication using observation only, never write replay."""
        async with self._session.begin():
            persisted_namespace = await self._claim_and_validate_namespace()
            candidate = await self._repo.lock_put_attempt(str(attempt_id))
            if candidate is None:
                return "stale"
            self._validate_put_execution_namespace(candidate, persisted_namespace)
            candidate_generation = candidate.execution_generation
        executor_id = uuid4()
        facts = _put_authority_facts(candidate, executor_id, candidate_generation + 1)
        async with self._session.begin() as claim_transaction:
            await self._authority.prepare(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=facts,
                phase="claim",
                idempotency_key=executor_id,
            )
            persisted_namespace = await self._claim_and_validate_namespace()
            current = await self._repo.lock_put_attempt(str(attempt_id))
            if (
                current is None
                or _put_authority_facts(current, executor_id, candidate_generation + 1) != facts
            ):
                self._authority.discard()
                return "stale"
            await self._authority.consume(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=facts,
            )
            claimed_result = await self._repo.claim_put_attempt(
                attempt_id=attempt_id,
                executor_id=executor_id,
                lease_seconds=self._settings.artifact_execution_lease_seconds,
                mode="observation",
                expected_generation=candidate_generation,
            )
            if claimed_result is None:
                await claim_transaction.rollback()
                return "stale"
            claimed = await self._repo.lock_put_attempt(str(attempt_id))
            if not _matching_put_fence(claimed, executor_id, candidate_generation + 1):
                await claim_transaction.rollback()
                return "stale"
            assert claimed is not None
            self._validate_put_execution_namespace(claimed, persisted_namespace)
            if _put_authority_facts(claimed, executor_id, claimed.execution_generation) != facts:
                await claim_transaction.rollback()
                return "stale"
        commitment = _attempt_commitment(claimed)
        try:
            observation = await self._store.observe_put_result(commitment)
            if not observation.committed:
                return await self._record_put_absence(claimed, executor_id, facts)
            observed_sha256, observed_size = await self._read_complete(
                observation.provider_object_ref
            )
        except ArtifactIntegrityError:
            try:
                observed_sha256, observed_size = await self._read_complete(claimed.canonical_target)
            except (ArtifactStoreUnavailableError, TimeoutError):
                return await self._record_put_unavailable(claimed, executor_id, facts)
            except ArtifactStoreError:
                return await self._record_put_conflict(claimed, executor_id, facts)
            return await self._record_put_mismatch(
                claimed,
                executor_id,
                facts,
                claimed.canonical_target,
                observed_sha256,
                observed_size,
            )
        except ArtifactObjectMissingError:
            return await self._record_put_absence(claimed, executor_id, facts)
        except (ArtifactStoreUnavailableError, TimeoutError):
            return await self._record_put_unavailable(claimed, executor_id, facts)
        except ArtifactStoreError:
            return await self._record_put_conflict(claimed, executor_id, facts)
        if observed_sha256 != claimed.sha256 or observed_size != claimed.byte_count:
            return await self._record_put_mismatch(
                claimed,
                executor_id,
                facts,
                observation.provider_object_ref,
                observed_sha256,
                observed_size,
            )
        return await self._complete_transaction_b(
            claimed=claimed,
            executor_id=executor_id,
            expected_facts=facts,
            provider_object_ref=observation.provider_object_ref,
            replayed=True,
            observed=True,
        )

    async def verify_object(self, job_id: UUID) -> str:
        """Run one deadline-bounded complete-object verification claim."""
        async with self._session.begin():
            persisted_namespace = await self._claim_and_validate_namespace()
            candidate = await self._repo.lock_verification_job(str(job_id))
            if candidate is None:
                return "stale"
            replica = await self._repo.lock_replica(candidate.replica_id)
            attempt = await self._repo.lock_put_attempt(candidate.originating_put_attempt_id)
            if replica is None or attempt is None:
                return "conflict"
            self._validate_put_execution_namespace(attempt, persisted_namespace)
            self._validate_replica_execution_namespace(replica, persisted_namespace)
            candidate_generation = candidate.execution_generation
        executor_id = uuid4()
        facts = _verification_authority_facts(
            candidate, replica, attempt, executor_id, candidate_generation + 1
        )
        async with self._session.begin() as claim_transaction:
            await self._authority.prepare(
                service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
                action_id=ActionId.ARTIFACT_VERIFICATION_EXECUTE,
                facts=facts,
                phase="claim",
                idempotency_key=executor_id,
            )
            persisted_namespace = await self._claim_and_validate_namespace()
            current = await self._repo.lock_verification_job(str(job_id))
            if current is None or current.execution_generation != candidate_generation:
                self._authority.discard()
                return "stale"
            current_replica = await self._repo.lock_replica(current.replica_id)
            current_attempt = await self._repo.lock_put_attempt(current.originating_put_attempt_id)
            if current_replica is None or current_attempt is None:
                self._authority.discard()
                return "conflict"
            current_facts = _verification_authority_facts(
                current,
                current_replica,
                current_attempt,
                executor_id,
                candidate_generation + 1,
            )
            if current_facts != facts:
                self._authority.discard()
                return "stale"
            await self._authority.consume(
                service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
                action_id=ActionId.ARTIFACT_VERIFICATION_EXECUTE,
                facts=facts,
            )
            claimed_result = await self._repo.claim_verification_job(
                job_id=job_id,
                executor_id=executor_id,
                lease_seconds=self._settings.artifact_execution_lease_seconds,
                expected_generation=candidate_generation,
            )
            if claimed_result is None:
                await claim_transaction.rollback()
                return "stale"
            claimed = await self._repo.lock_verification_job(str(job_id))
            if not _matching_job_fence(claimed, executor_id, candidate_generation + 1):
                await claim_transaction.rollback()
                return "stale"
            assert claimed is not None
            execution_replica = await self._repo.lock_replica(claimed.replica_id)
            execution_attempt = await self._repo.lock_put_attempt(
                claimed.originating_put_attempt_id
            )
            if execution_replica is None or execution_attempt is None:
                await claim_transaction.rollback()
                return "conflict"
            execution_content = await self._repo.lock_content(execution_replica.content_id)
            self._validate_put_execution_namespace(execution_attempt, persisted_namespace)
            self._validate_replica_execution_namespace(execution_replica, persisted_namespace)
            execution_facts = _verification_authority_facts(
                claimed,
                execution_replica,
                execution_attempt,
                executor_id,
                claimed.execution_generation,
            )
            if execution_facts != facts:
                await claim_transaction.rollback()
                return "stale"
            if not _verification_relationship_matches(
                claimed,
                execution_replica,
                execution_attempt,
                execution_content,
            ):
                relationship_conflict = True
            else:
                relationship_conflict = False
        if relationship_conflict:
            return await self._complete_verification(
                claimed, executor_id, facts, "conflict", None, None
            )
        try:
            observed_sha256, observed_size = await self._read_complete(
                execution_replica.provider_object_ref
            )
        except ArtifactObjectMissingError:
            return await self._complete_verification(
                claimed, executor_id, facts, "missing", None, None
            )
        except (ArtifactStoreUnavailableError, TimeoutError):
            return await self._record_verification_unavailable(claimed, executor_id, facts)
        except ArtifactStoreError:
            return await self._complete_verification(
                claimed, executor_id, facts, "conflict", None, None
            )
        outcome = (
            "verified"
            if observed_sha256 == execution_attempt.sha256
            and observed_size == execution_attempt.byte_count
            else "integrity_mismatch"
        )
        return await self._complete_verification(
            claimed, executor_id, facts, outcome, observed_sha256, observed_size
        )

    async def _read_complete(self, provider_object_ref: str) -> tuple[str, int]:
        digest = hashlib.sha256()
        byte_count = 0
        async with asyncio.timeout(self._settings.artifact_complete_read_deadline_seconds):
            try:
                async for chunk in self._store.open(provider_object_ref):
                    digest.update(chunk)
                    byte_count += len(chunk)
            except ArtifactIntegrityError:
                # A byte store may reject a content-addressed stream only
                # after yielding it completely. Workstream still owns the
                # canonical digest/size classification of those bytes.
                pass
        return f"sha256:{digest.hexdigest()}", byte_count

    async def _complete_transaction_b(
        self,
        *,
        claimed: ArtifactPutAttempt,
        executor_id: UUID,
        expected_facts: ArtifactPutAttemptAuthorityFacts,
        provider_object_ref: str,
        replayed: bool,
        observed: bool,
    ) -> str:
        async with self._session.begin():
            await self._authority.prepare(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=expected_facts,
                phase="terminal",
                idempotency_key=executor_id,
            )
            attempt = await self._repo.lock_put_attempt(claimed.id)
            if not _matching_put_fence(attempt, executor_id, claimed.execution_generation):
                self._authority.discard()
                return "stale"
            assert attempt is not None
            facts = _put_authority_facts(attempt, executor_id, claimed.execution_generation)
            if facts != expected_facts:
                self._authority.discard()
                return "stale"
            await self._authority.consume(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=facts,
            )
            charges = await self._repo.lock_attempt_charges(attempt.id)
            now = await self._repo.database_now()
            for charge in charges:
                if charge.state == "provisional":
                    charge.state = "completed"
                    charge.completed_at = now
                    charge.cas_version += 1
            content = await self._repo.get_or_create_content(
                ArtifactContent(
                    id=str(uuid4()),
                    sha256=attempt.sha256,
                    byte_count=attempt.byte_count,
                    media_type=attempt.media_type,
                    normalized_display_name=None,
                )
            )
            replica = await self._repo.get_or_create_replica(
                ArtifactReplica(
                    id=str(uuid4()),
                    content_id=content.id,
                    storage_namespace_id=attempt.storage_namespace_id,
                    namespace_fingerprint=attempt.namespace_fingerprint,
                    adapter=self._store.identity.provider_key,
                    provider_profile=self._namespace.provider_profile,
                    provider_object_ref=provider_object_ref,
                    verification_state="pending",
                    availability_state="unknown",
                    integrity_state="unknown",
                )
            )
            replica_identity = (
                replica.content_id,
                replica.namespace_fingerprint,
                replica.adapter,
                replica.provider_profile,
            )
            expected_replica_identity = (
                content.id,
                attempt.namespace_fingerprint,
                self._store.identity.provider_key,
                self._namespace.provider_profile,
            )
            if replica_identity != expected_replica_identity:
                await self._repo.add_put_observation_receipt(
                    ArtifactPutObservationReceipt(
                        id=str(uuid4()),
                        put_attempt_id=attempt.id,
                        execution_generation=attempt.execution_generation,
                        outcome="conflict",
                        expected_sha256=attempt.sha256,
                        expected_byte_count=attempt.byte_count,
                        observed_sha256=None,
                        observed_byte_count=None,
                    )
                )
                attempt.status = "conflict"
                attempt.terminal_result_code = "conflict"
                attempt.terminal_at = now
                _clear_put_fence(attempt)
                return "conflict"
            if observed:
                observation_receipt = await self._repo.add_put_observation_receipt(
                    ArtifactPutObservationReceipt(
                        id=str(uuid4()),
                        put_attempt_id=attempt.id,
                        execution_generation=attempt.execution_generation,
                        outcome="observed_confirmed",
                        expected_sha256=attempt.sha256,
                        expected_byte_count=attempt.byte_count,
                        observed_sha256=attempt.sha256,
                        observed_byte_count=attempt.byte_count,
                    )
                )
                receipt_id = observation_receipt.id
            else:
                receipt = await self._repo.add_receipt(
                    ArtifactOperationReceipt(
                        id=str(uuid4()),
                        put_attempt_id=attempt.id,
                        upload_item_id=attempt.upload_item_id,
                        guide_source_item_id=attempt.guide_source_item_id,
                        checker_run_id=attempt.checker_run_id,
                        logical_role=attempt.logical_role,
                        replica_id=replica.id,
                        operation="put",
                        idempotency_key=attempt.operation_identity,
                        request_digest=attempt.request_digest,
                        provider_object_ref=provider_object_ref,
                        replayed=replayed,
                        outcome="stored_pending_verification",
                        attempt_number=max(1, attempt.execution_generation),
                        correlation_id=attempt.operation_identity,
                        details=[],
                    )
                )
                receipt_id = receipt.id
            await self._repo.add_verification_job(
                ArtifactVerificationJob(
                    id=str(uuid4()),
                    originating_put_attempt_id=attempt.id,
                    replica_id=replica.id,
                    status="pending",
                    maximum_attempts=self._settings.artifact_provider_observation_maximum_attempts,
                )
            )
            if attempt.upload_item_id is not None:
                item = await self._repo.lock_upload_item(attempt.upload_item_id)
                if item is not None:
                    item.state = "stored_pending_verification"
                    item.content_id = content.id
                    item.provider_object_ref = provider_object_ref
                    item.cas_version += 1
            attempt.status = "object_confirmed"
            attempt.replica_id = replica.id
            # observation receipts are not acknowledgement receipts; retain the
            # typed evidence through the attempt result rather than the FK.
            attempt.receipt_id = None if observed else receipt_id
            attempt.executor_id = None
            attempt.lease_expires_at = None
            attempt.execution_mode = None
            attempt.next_run_at = None
            attempt.terminal_result_code = "observed_confirmed" if observed else "acknowledged"
            attempt.terminal_at = now
            attempt.cas_version += 1
        return "observed_confirmed" if observed else "stored_pending_verification"

    async def _record_put_unavailable(
        self,
        claimed: ArtifactPutAttempt,
        executor_id: UUID,
        expected_facts: ArtifactPutAttemptAuthorityFacts,
    ) -> str:
        async with self._session.begin():
            await self._authority.prepare(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=expected_facts,
                phase="terminal",
                idempotency_key=executor_id,
            )
            attempt = await self._repo.lock_put_attempt(claimed.id)
            if not _matching_put_fence(attempt, executor_id, claimed.execution_generation):
                self._authority.discard()
                return "stale"
            assert attempt is not None
            terminal_facts = _put_authority_facts(
                attempt, executor_id, claimed.execution_generation
            )
            if terminal_facts != expected_facts:
                self._authority.discard()
                return "stale"
            await self._authority.consume(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=terminal_facts,
            )
            now = await self._repo.database_now()
            exhausted = attempt.observation_count >= attempt.maximum_observations
            attempt.status = "provider_unavailable" if exhausted else "acknowledgement_unknown"
            attempt.next_run_at = (
                None
                if exhausted
                else now
                + timedelta(seconds=self._settings.artifact_pending_work_scan_interval_seconds)
            )
            attempt.terminal_at = now if exhausted else None
            attempt.terminal_result_code = "provider_unavailable" if exhausted else None
            _clear_put_fence(attempt)
        return "provider_unavailable" if exhausted else "acknowledgement_unknown"

    async def _record_put_absence(
        self,
        claimed: ArtifactPutAttempt,
        executor_id: UUID,
        expected_facts: ArtifactPutAttemptAuthorityFacts,
    ) -> str:
        async with self._session.begin():
            await self._authority.prepare(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=expected_facts,
                phase="terminal",
                idempotency_key=executor_id,
            )
            attempt = await self._repo.lock_put_attempt(claimed.id)
            if not _matching_put_fence(attempt, executor_id, claimed.execution_generation):
                self._authority.discard()
                return "stale"
            assert attempt is not None
            terminal_facts = _put_authority_facts(
                attempt, executor_id, claimed.execution_generation
            )
            if terminal_facts != expected_facts:
                self._authority.discard()
                return "stale"
            await self._authority.consume(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=terminal_facts,
            )
            charges = await self._repo.lock_attempt_charges(attempt.id)
            scopes = await self._repo.lock_charge_scopes(charges)
            scope_by_key = {(scope.scope_type, scope.scope_id): scope for scope in scopes}
            now = await self._repo.database_now()
            for charge in charges:
                if charge.state == "provisional":
                    charge.state = "released"
                    charge.released_at = now
                    charge.cas_version += 1
                    scope = scope_by_key[(charge.scope_type, charge.scope_id)]
                    scope.counted_bytes -= charge.byte_count
                    scope.cas_version += 1
            await self._repo.add_put_observation_receipt(
                ArtifactPutObservationReceipt(
                    id=str(uuid4()),
                    put_attempt_id=attempt.id,
                    execution_generation=attempt.execution_generation,
                    outcome="observed_missing",
                    expected_sha256=attempt.sha256,
                    expected_byte_count=attempt.byte_count,
                )
            )
            if attempt.upload_item_id is not None:
                item = await self._repo.lock_upload_item(attempt.upload_item_id)
                if item is not None:
                    item.state = "replay_required"
                    item.content_id = None
                    item.provider_object_ref = None
                    item.cas_version += 1
            attempt.status = "absent_replay_required"
            attempt.terminal_result_code = "missing"
            attempt.terminal_at = now
            _clear_put_fence(attempt)
        return "missing"

    async def _record_put_mismatch(
        self,
        claimed: ArtifactPutAttempt,
        executor_id: UUID,
        expected_facts: ArtifactPutAttemptAuthorityFacts,
        provider_object_ref: str,
        observed_sha256: str,
        observed_size: int,
    ) -> str:
        return await self._record_put_terminal_observation(
            claimed,
            executor_id,
            expected_facts,
            status="integrity_mismatch",
            outcome="observed_integrity_mismatch",
            observed_sha256=observed_sha256,
            observed_size=observed_size,
            provider_object_ref=provider_object_ref,
        )

    async def _record_put_conflict(
        self,
        claimed: ArtifactPutAttempt,
        executor_id: UUID,
        expected_facts: ArtifactPutAttemptAuthorityFacts,
    ) -> str:
        return await self._record_put_terminal_observation(
            claimed,
            executor_id,
            expected_facts,
            status="conflict",
            outcome="conflict",
            observed_sha256=None,
            observed_size=None,
            provider_object_ref=None,
        )

    async def _record_put_terminal_observation(
        self,
        claimed: ArtifactPutAttempt,
        executor_id: UUID,
        expected_facts: ArtifactPutAttemptAuthorityFacts,
        *,
        status: str,
        outcome: str,
        observed_sha256: str | None,
        observed_size: int | None,
        provider_object_ref: str | None,
    ) -> str:
        async with self._session.begin():
            await self._authority.prepare(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=expected_facts,
                phase="terminal",
                idempotency_key=executor_id,
            )
            attempt = await self._repo.lock_put_attempt(claimed.id)
            if not _matching_put_fence(attempt, executor_id, claimed.execution_generation):
                self._authority.discard()
                return "stale"
            assert attempt is not None
            terminal_facts = _put_authority_facts(
                attempt, executor_id, claimed.execution_generation
            )
            if terminal_facts != expected_facts:
                self._authority.discard()
                return "stale"
            await self._authority.consume(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=terminal_facts,
            )
            now = await self._repo.database_now()
            for charge in await self._repo.lock_attempt_charges(attempt.id):
                if charge.state == "provisional":
                    charge.state = "completed"
                    charge.completed_at = now
                    charge.cas_version += 1
            if status == "integrity_mismatch" and provider_object_ref is not None:
                content = await self._repo.get_or_create_content(
                    ArtifactContent(
                        id=str(uuid4()),
                        sha256=attempt.sha256,
                        byte_count=attempt.byte_count,
                        media_type=attempt.media_type,
                        normalized_display_name=None,
                    )
                )
                locked_content = await self._repo.lock_content(content.id)
                if locked_content is None:
                    raise ArtifactIngestStateError("artifact content is unavailable")
                content = locked_content
                replica = await self._repo.get_or_create_replica(
                    ArtifactReplica(
                        id=str(uuid4()),
                        content_id=content.id,
                        storage_namespace_id=attempt.storage_namespace_id,
                        namespace_fingerprint=attempt.namespace_fingerprint,
                        adapter=self._store.identity.provider_key,
                        provider_profile=self._namespace.provider_profile,
                        provider_object_ref=provider_object_ref,
                        verification_state="integrity_mismatch",
                        availability_state="available",
                        integrity_state="invalid",
                    )
                )
                existing_states = (
                    replica.verification_state,
                    replica.availability_state,
                    replica.integrity_state,
                )
                if existing_states not in {
                    ("pending", "unknown", "unknown"),
                    ("integrity_mismatch", "available", "invalid"),
                }:
                    status = "conflict"
                    outcome = "conflict"
                else:
                    replica.verification_state = "integrity_mismatch"
                    replica.availability_state = "available"
                    replica.integrity_state = "invalid"
                attempt.replica_id = replica.id
                if outcome == "observed_integrity_mismatch" and attempt.upload_item_id is not None:
                    item = await self._repo.lock_upload_item(attempt.upload_item_id)
                    binding = await self._repo.lock_binding_for_content(content.id)
                    if (
                        item is not None
                        and binding is None
                        and item.state in {"reserved", "replay_required"}
                    ):
                        item.state = "failed"
                        item.error_code = "artifact_integrity_failure"
                        item.cas_version += 1
            await self._repo.add_put_observation_receipt(
                ArtifactPutObservationReceipt(
                    id=str(uuid4()),
                    put_attempt_id=attempt.id,
                    execution_generation=attempt.execution_generation,
                    outcome=outcome,
                    expected_sha256=attempt.sha256,
                    expected_byte_count=attempt.byte_count,
                    observed_sha256=(None if outcome == "conflict" else observed_sha256),
                    observed_byte_count=(None if outcome == "conflict" else observed_size),
                )
            )
            attempt.status = status
            attempt.terminal_result_code = status
            attempt.terminal_at = now
            _clear_put_fence(attempt)
        return status

    async def _record_verification_unavailable(
        self,
        claimed: ArtifactVerificationJob,
        executor_id: UUID,
        expected_facts: ArtifactVerificationAuthorityFacts,
    ) -> str:
        async with self._session.begin():
            await self._authority.prepare(
                service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
                action_id=ActionId.ARTIFACT_VERIFICATION_EXECUTE,
                facts=expected_facts,
                phase="terminal",
                idempotency_key=executor_id,
            )
            job = await self._repo.lock_verification_job(claimed.id)
            if not _matching_job_fence(job, executor_id, claimed.execution_generation):
                self._authority.discard()
                return "stale"
            assert job is not None
            replica = await self._repo.lock_replica(job.replica_id)
            attempt = await self._repo.lock_put_attempt(job.originating_put_attempt_id)
            if replica is None or attempt is None:
                self._authority.discard()
                return "conflict"
            content = await self._repo.lock_content(replica.content_id)
            terminal_facts = _verification_authority_facts(
                job, replica, attempt, executor_id, claimed.execution_generation
            )
            if terminal_facts != expected_facts:
                self._authority.discard()
                return "stale"
            await self._authority.consume(
                service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
                action_id=ActionId.ARTIFACT_VERIFICATION_EXECUTE,
                facts=terminal_facts,
            )
            now = await self._repo.database_now()
            if not _verification_relationship_matches(job, replica, attempt, content):
                await self._terminalize_verification_conflict(job, now)
                return "conflict"
            exhausted = job.attempt_count >= job.maximum_attempts
            job.status = "provider_unavailable"
            job.next_run_at = (
                None
                if exhausted
                else now
                + timedelta(seconds=self._settings.artifact_pending_work_scan_interval_seconds)
            )
            job.terminal_at = now if exhausted else None
            job.terminal_result_code = "provider_unavailable" if exhausted else None
            _clear_job_fence(job)
            if exhausted:
                await self._finalize_recovery_for_job(job, "provider_unavailable", now)
        return "provider_unavailable"

    async def _complete_verification(
        self,
        claimed: ArtifactVerificationJob,
        executor_id: UUID,
        expected_facts: ArtifactVerificationAuthorityFacts,
        outcome: str,
        observed_sha256: str | None,
        observed_size: int | None,
    ) -> str:
        async with self._session.begin():
            await self._authority.prepare(
                service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
                action_id=ActionId.ARTIFACT_VERIFICATION_EXECUTE,
                facts=expected_facts,
                phase="terminal",
                idempotency_key=executor_id,
            )
            job = await self._repo.lock_verification_job(claimed.id)
            if not _matching_job_fence(job, executor_id, claimed.execution_generation):
                self._authority.discard()
                return "stale"
            assert job is not None
            replica = await self._repo.lock_replica(job.replica_id)
            attempt = await self._repo.lock_put_attempt(job.originating_put_attempt_id)
            if replica is None or attempt is None:
                self._authority.discard()
                return "conflict"
            content = await self._repo.lock_content(replica.content_id)
            terminal_facts = _verification_authority_facts(
                job, replica, attempt, executor_id, claimed.execution_generation
            )
            if terminal_facts != expected_facts:
                self._authority.discard()
                return "stale"
            await self._authority.consume(
                service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
                action_id=ActionId.ARTIFACT_VERIFICATION_EXECUTE,
                facts=terminal_facts,
            )
            now = await self._repo.database_now()
            if not _verification_relationship_matches(job, replica, attempt, content):
                outcome = "conflict"
                observed_sha256 = None
                observed_size = None
            mapping = {
                "verified": ("verified", "available", "valid"),
                "missing": ("missing", "unavailable", "unknown"),
                "integrity_mismatch": ("integrity_mismatch", "available", "invalid"),
                "conflict": (
                    replica.verification_state,
                    replica.availability_state,
                    replica.integrity_state,
                ),
            }
            states = mapping[outcome]
            if replica.verification_state in {"integrity_mismatch", "missing"}:
                expected_existing = {
                    "integrity_mismatch": ("integrity_mismatch", "available", "invalid"),
                    "missing": ("missing", "unavailable", "unknown"),
                }[replica.verification_state]
                if states != expected_existing:
                    outcome = "conflict"
                    observed_sha256 = None
                    observed_size = None
                    states = (
                        replica.verification_state,
                        replica.availability_state,
                        replica.integrity_state,
                    )
            else:
                replica.verification_state, replica.availability_state, replica.integrity_state = (
                    states
                )
                replica.last_reconciled_at = now
            await self._repo.add_verification_receipt(
                ArtifactVerificationReceipt(
                    id=str(uuid4()),
                    verification_job_id=job.id,
                    execution_generation=job.execution_generation,
                    outcome=outcome,
                    observed_sha256=observed_sha256,
                    observed_byte_count=observed_size,
                )
            )
            if attempt.upload_item_id is not None:
                item = await self._repo.lock_upload_item(attempt.upload_item_id)
                if item is not None:
                    item_changed = False
                    if outcome == "verified":
                        item.state = "ready"
                        item_changed = True
                    elif outcome == "missing":
                        content = await self._repo.lock_content(replica.content_id)
                        if content is None:
                            raise ArtifactIngestStateError(
                                "artifact replica content is unavailable"
                            )
                        binding = await self._repo.lock_binding_for_content(replica.content_id)
                        if binding is None:
                            item.state = "replay_required"
                            item.content_id = None
                            item.provider_object_ref = None
                            item_changed = True
                    elif outcome == "integrity_mismatch":
                        item.state = "failed"
                        item.content_id = None
                        item.provider_object_ref = None
                        item.error_code = "artifact_integrity_failure"
                        item_changed = True
                    if item_changed:
                        item.cas_version += 1
            job.status = outcome
            job.next_run_at = None
            job.terminal_result_code = outcome
            job.terminal_at = now
            _clear_job_fence(job)
            await self._finalize_recovery_for_job(job, outcome, now)
        return outcome

    async def _terminalize_verification_conflict(
        self,
        job: ArtifactVerificationJob,
        now: datetime,
    ) -> None:
        """Append typed conflict evidence without mutating unrelated artifact facts."""
        await self._repo.add_verification_receipt(
            ArtifactVerificationReceipt(
                id=str(uuid4()),
                verification_job_id=job.id,
                execution_generation=job.execution_generation,
                outcome="conflict",
                observed_sha256=None,
                observed_byte_count=None,
            )
        )
        job.status = "conflict"
        job.next_run_at = None
        job.terminal_result_code = "conflict"
        job.terminal_at = now
        _clear_job_fence(job)
        await self._finalize_recovery_for_job(job, "conflict", now)

    async def _finalize_recovery_for_job(
        self, job: ArtifactVerificationJob, outcome: str, now: datetime
    ) -> None:
        """Terminalize the linked recovery envelope under the job's held fence."""
        recovery = await self._repo.lock_recovery_by_retry(job.id)
        if recovery is None:
            return
        if recovery.status != "requested" or recovery.terminal_at is not None:
            raise ArtifactIngestStateError("artifact recovery envelope is already terminal")
        audit_id = str(uuid4())
        await AuditRepository(self._session).add_audit_event(
            ArtifactRecoveryService._audit_event(
                event_id=audit_id,
                event_type="ArtifactRecoveryCompleted",
                recovery_id=recovery.id,
                actor_id=ServiceIdentity.ARTIFACT_VERIFIER.value,
                reason=recovery.reason,
                payload={
                    "source_verification_job_id": recovery.source_verification_job_id,
                    "retry_verification_job_id": job.id,
                    "terminal_result_code": outcome,
                    "execution_actor_kind": "service_identity",
                    "execution_service_identity": ServiceIdentity.ARTIFACT_VERIFIER.value,
                },
            )
        )
        recovery.status = "succeeded" if outcome == "verified" else "failed"
        recovery.terminal_result_code = outcome
        recovery.terminal_at = now
        recovery.terminal_audit_event_id = audit_id
        recovery.cas_version += 1

    async def _claim_and_validate_namespace(self) -> ArtifactStorageNamespace:
        """Atomically claim the singleton or reject deployment identity drift."""
        return await _claim_and_validate_storage_namespace(self._repo, self._namespace)

    def _validate_put_execution_namespace(
        self,
        attempt: ArtifactPutAttempt,
        persisted: ArtifactStorageNamespace,
    ) -> None:
        """Reject provider execution outside the active storage namespace."""
        if (
            attempt.storage_namespace_id != persisted.id
            or attempt.namespace_fingerprint != persisted.namespace_fingerprint
            or self._store.identity.provider_key != persisted.adapter
            or self._namespace.provider_profile != persisted.provider_profile
        ):
            raise ArtifactStorageNamespaceError(
                "artifact put attempt does not match the active storage namespace"
            )

    def _validate_replica_execution_namespace(
        self,
        replica: ArtifactReplica,
        persisted: ArtifactStorageNamespace,
    ) -> None:
        """Reject reads when replica identity differs from active composition."""
        if (
            replica.storage_namespace_id != persisted.id
            or replica.namespace_fingerprint != persisted.namespace_fingerprint
            or replica.adapter != persisted.adapter
            or replica.provider_profile != persisted.provider_profile
            or self._store.identity.provider_key != persisted.adapter
        ):
            raise ArtifactStorageNamespaceError(
                "artifact replica does not match the active storage namespace"
            )


class ArtifactPendingWorkScanner:
    """Bounded after-commit publication for due artifact execution IDs."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        authority: ArtifactInternalAuthority,
        publish_put_attempt: Callable[[str], Awaitable[None]],
        publish_verification_job: Callable[[str], Awaitable[None]],
    ) -> None:
        self._session = session
        self._settings = settings
        self._authority = authority
        self._repo = ArtifactRepository(session)
        self._publish_put_attempt = publish_put_attempt
        self._publish_verification_job = publish_verification_job

    async def scan(self) -> int:
        """Read one stable page then publish IDs outside the database transaction."""
        async with self._session.begin():
            cutoff = await self._repo.database_now()
            scan_id = uuid4()
            initial_facts = ArtifactPendingWorkAuthorityFacts(
                resource_type=ArtifactInternalResourceType.PENDING_WORK,
                resource_id="workstream:artifact_pending_work",
                scanner_kind="put_resolution_and_verification",
                database_cutoff_iso=cutoff.isoformat(),
                page_size=self._settings.artifact_pending_work_scan_page_size,
            )
            await self._authority.prepare(
                service_identity=ServiceIdentity.ARTIFACT_SCHEDULER,
                action_id=ActionId.ARTIFACT_PENDING_WORK_SCAN,
                facts=initial_facts,
                phase="scan",
                idempotency_key=scan_id,
            )
            put_ids = await self._repo.list_due_put_attempt_ids(
                cutoff=cutoff,
                limit=self._settings.artifact_pending_work_scan_page_size,
            )
            remaining = self._settings.artifact_pending_work_scan_page_size - len(put_ids)
            job_ids = await self._repo.list_due_verification_job_ids(
                cutoff=cutoff,
                limit=remaining,
            )
            facts = ArtifactPendingWorkAuthorityFacts(
                resource_type=ArtifactInternalResourceType.PENDING_WORK,
                resource_id="workstream:artifact_pending_work",
                scanner_kind="put_resolution_and_verification",
                database_cutoff_iso=cutoff.isoformat(),
                page_size=self._settings.artifact_pending_work_scan_page_size,
                put_attempt_ids=tuple(UUID(value) for value in put_ids),
                verification_job_ids=tuple(UUID(value) for value in job_ids),
            )
            await self._authority.consume(
                service_identity=ServiceIdentity.ARTIFACT_SCHEDULER,
                action_id=ActionId.ARTIFACT_PENDING_WORK_SCAN,
                facts=facts,
            )
        for attempt_id in put_ids:
            await self._publish_put_attempt(attempt_id)
        for job_id in job_ids:
            await self._publish_verification_job(job_id)
        return len(put_ids) + len(job_ids)


class ArtifactRecoveryService:
    """Create one idempotent read-only verification recovery chain link."""

    _RECOVERY_CLASS = "provider_observation"

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        authority: ArtifactRecoveryAuthority,
    ) -> None:
        self._session = session
        self._settings = settings
        self._authority = authority
        self._repo = ArtifactRepository(session)
        self._actors = ActorService(session)
        self._audit = AuditRepository(session)

    async def create(self, request: ArtifactRecoveryRequest) -> ArtifactRecoveryResult:
        """Create or replay one envelope, retry job, and initiation audit atomically."""
        self._validate_request(request)
        digest = self._request_digest(request)
        source_id = str(request.source_verification_job_id)
        try:
            async with self._session.begin():
                return await self._create_locked(request, source_id, digest)
        except IntegrityError:
            # A concurrent winner may have committed either lifetime-source or
            # idempotency ownership.  The failed transaction is closed before
            # the authoritative replay row is read.
            async with self._session.begin():
                existing = await self._repo.lock_recovery_by_source(source_id)
                if existing is not None:
                    await self._authorize_request(
                        request,
                        project_id=UUID(existing.project_id),
                        task_id=UUID(existing.task_id) if existing.task_id else None,
                        submission_id=(
                            UUID(existing.submission_id) if existing.submission_id else None
                        ),
                    )
                    if self._is_exact_replay(existing, request, digest):
                        return self._result(existing, replayed=True)
                    raise ArtifactRecoveryConflictError("artifact recovery source is already owned")
            raise

    async def retry_verification(self, request: ArtifactRecoveryRequest) -> ArtifactRecoveryResult:
        """Implement the approved Operator recovery port."""
        return await self.create(request)

    async def _create_locked(
        self, request: ArtifactRecoveryRequest, source_id: str, digest: str
    ) -> ArtifactRecoveryResult:
        existing = await self._repo.lock_recovery_by_source(source_id)
        if existing is not None:
            await self._authorize_request(
                request,
                project_id=UUID(existing.project_id),
                task_id=UUID(existing.task_id) if existing.task_id else None,
                submission_id=UUID(existing.submission_id) if existing.submission_id else None,
            )
            if self._is_exact_replay(existing, request, digest):
                return self._result(existing, replayed=True)
            raise ArtifactRecoveryConflictError("artifact recovery source is already owned")
        source = await self._repo.lock_verification_job(source_id)
        if source is None:
            raise ArtifactRecoveryNotFoundError("artifact recovery resource was not found")
        put_attempt = await self._repo.lock_put_attempt(source.originating_put_attempt_id)
        if put_attempt is None:
            raise ArtifactRecoveryNotFoundError("artifact recovery resource was not found")
        checker_run = (
            await self._repo.lock_checker_run(put_attempt.checker_run_id)
            if put_attempt.checker_run_id is not None
            else None
        )
        canonical_submission_id = checker_run.submission_id if checker_run is not None else None
        canonical_project_id = UUID(put_attempt.project_id)
        canonical_task_id = UUID(put_attempt.task_id) if put_attempt.task_id else None
        canonical_submission_uuid = (
            UUID(canonical_submission_id) if canonical_submission_id else None
        )
        await self._authorize_request(
            request,
            project_id=canonical_project_id,
            task_id=canonical_task_id,
            submission_id=canonical_submission_uuid,
        )
        if (
            put_attempt.project_id != str(request.project_id)
            or put_attempt.task_id
            != (str(request.task_id) if request.task_id is not None else None)
            or canonical_submission_id
            != (str(request.submission_id) if request.submission_id is not None else None)
        ):
            raise ArtifactRecoveryConflictError("artifact recovery resource facts changed")
        if not self._is_exhausted_unavailable(source):
            raise ArtifactRecoveryIneligibleError(
                "artifact verification job is not exhausted provider-unavailable work"
            )
        if source.cas_version != request.expected_source_job_cas_version:
            raise ArtifactRecoveryConflictError("artifact verification source changed")
        parent = await self._repo.lock_recovery_by_retry(source_id)
        # Revalidate the locked actor/link and exact AUTH decision at the
        # terminal boundary. No await occurs between this proof and staging the
        # atomic retry, recovery, and audit facts below.
        authorization = await self._authorize_request(
            request,
            project_id=canonical_project_id,
            task_id=canonical_task_id,
            submission_id=canonical_submission_uuid,
        )
        context = request.authorization_context
        retry_id = str(uuid4())
        recovery_id = str(uuid4())
        audit_id = str(uuid4())
        retry = ArtifactVerificationJob(
            id=retry_id,
            originating_put_attempt_id=source.originating_put_attempt_id,
            parent_verification_job_id=source.id,
            replica_id=source.replica_id,
            status="pending",
            maximum_attempts=self._settings.artifact_provider_observation_maximum_attempts,
        )
        await self._repo.add_verification_job(retry)
        await self._audit.add_audit_event(
            self._audit_event(
                event_id=audit_id,
                event_type="ArtifactRecoveryInitiated",
                recovery_id=recovery_id,
                actor_id=str(context.actor_profile_id),
                reason=request.reason,
                payload={
                    "source_verification_job_id": source.id,
                    "retry_verification_job_id": retry_id,
                    "recovery_class": self._RECOVERY_CLASS,
                    "request_digest": digest,
                    "authorization_action_id": authorization.action_id.value,
                    "authorization_permission_id": authorization.permission_id,
                    "authorization_decision_id": str(authorization.decision_id),
                    "authorization_request_id": str(context.request_id),
                    "authorization_correlation_id": str(context.correlation_id),
                },
            )
        )
        recovery = ArtifactRecoveryAttempt(
            id=recovery_id,
            requester_actor_profile_id=str(context.actor_profile_id),
            requester_identity_link_id=str(context.identity_link_id),
            authorization_request_id=str(context.request_id),
            authorization_correlation_id=str(context.correlation_id),
            project_id=str(canonical_project_id),
            task_id=str(canonical_task_id) if canonical_task_id is not None else None,
            submission_id=(str(canonical_submission_uuid) if canonical_submission_uuid else None),
            source_verification_job_id=source.id,
            retry_verification_job_id=retry_id,
            parent_recovery_attempt_id=parent.id if parent is not None else None,
            recovery_class=self._RECOVERY_CLASS,
            reason=request.reason,
            client_idempotency_key=request.client_idempotency_key,
            request_digest=digest,
            status="requested",
            initiation_audit_event_id=audit_id,
        )
        await self._repo.add_recovery_attempt(recovery)
        return self._result(recovery, replayed=False)

    async def _authorize_request(
        self,
        request: ArtifactRecoveryRequest,
        *,
        project_id: UUID,
        task_id: UUID | None,
        submission_id: UUID | None,
    ):
        """Revalidate the human requester and exact Operator action on every call."""
        context = request.authorization_context
        actor = await self._actors.lock_admission_proof(
            context.actor_profile_id, context.identity_link_id
        )
        if (
            context.actor_kind is not ActorKind.HUMAN
            or context.actor_status is not ActorStatus.ACTIVE
            or context.identity_link_status is not IdentityLinkStatus.ACTIVE
            or actor is None
            or actor.actor_kind != "human"
            or actor.actor_status != "active"
            or actor.service_identity is not None
            or actor.identity_link_id != str(context.identity_link_id)
            or actor.identity_link_subject_kind != "human"
            or actor.identity_link_status != "active"
        ):
            raise ArtifactAuthorityDeniedError("artifact recovery requester is unavailable")
        authorization = await self._authority.authorize(
            authorization_context=context,
            facts=ArtifactRecoveryAuthorityFacts(
                project_id=project_id,
                task_id=task_id,
                submission_id=submission_id,
                source_verification_job_id=request.source_verification_job_id,
                expected_source_job_cas_version=request.expected_source_job_cas_version,
            ),
        )
        if (
            authorization.action_id is not ActionId.ARTIFACT_VERIFICATION_JOB_RETRY
            or authorization.permission_id != PermissionId.ARTIFACT_VERIFICATION_JOB_RETRY.value
        ):
            raise ArtifactAuthorityDeniedError(
                "artifact recovery authorization evidence is invalid"
            )
        return authorization

    @staticmethod
    def _validate_request(request: ArtifactRecoveryRequest) -> None:
        if type(request) is not ArtifactRecoveryRequest:
            raise TypeError("invalid artifact recovery request")
        if type(request.authorization_context) is not HumanAuthorizationContext:
            raise TypeError("artifact recovery requires a human requester")
        if (
            request.reason != request.reason.strip()
            or not request.reason
            or len(request.reason) > 1000
            or request.client_idempotency_key != request.client_idempotency_key.strip()
            or not request.client_idempotency_key
            or len(request.client_idempotency_key) > 200
            or request.expected_source_job_cas_version < 0
        ):
            raise ValueError("invalid artifact recovery request")

    @classmethod
    def _request_digest(cls, request: ArtifactRecoveryRequest) -> str:
        context = request.authorization_context
        return canonical_json_hash(
            {
                "requester_actor_profile_id": str(context.actor_profile_id),
                "requester_identity_link_id": str(context.identity_link_id),
                "project_id": str(request.project_id),
                "task_id": str(request.task_id) if request.task_id is not None else None,
                "submission_id": (
                    str(request.submission_id) if request.submission_id is not None else None
                ),
                "source_verification_job_id": str(request.source_verification_job_id),
                "recovery_class": cls._RECOVERY_CLASS,
                "reason": request.reason,
                "client_idempotency_key": request.client_idempotency_key,
                "expected_source_job_cas_version": request.expected_source_job_cas_version,
            }
        )

    @staticmethod
    def _is_exhausted_unavailable(job: ArtifactVerificationJob) -> bool:
        return (
            job.status == "provider_unavailable"
            and job.terminal_result_code == "provider_unavailable"
            and job.terminal_at is not None
            and job.next_run_at is None
            and job.executor_id is None
            and job.lease_expires_at is None
            and job.attempt_count >= job.maximum_attempts
        )

    @staticmethod
    def _is_exact_replay(
        attempt: ArtifactRecoveryAttempt,
        request: ArtifactRecoveryRequest,
        digest: str,
    ) -> bool:
        return (
            attempt.requester_actor_profile_id
            == str(request.authorization_context.actor_profile_id)
            and attempt.source_verification_job_id == str(request.source_verification_job_id)
            and attempt.recovery_class == ArtifactRecoveryService._RECOVERY_CLASS
            and attempt.client_idempotency_key == request.client_idempotency_key
            and attempt.request_digest == digest
        )

    @staticmethod
    def _result(attempt: ArtifactRecoveryAttempt, *, replayed: bool) -> ArtifactRecoveryResult:
        return ArtifactRecoveryResult(
            recovery_attempt_id=UUID(attempt.id),
            source_verification_job_id=UUID(attempt.source_verification_job_id),
            retry_verification_job_id=UUID(attempt.retry_verification_job_id),
            replayed=replayed,
        )

    @staticmethod
    def _audit_event(
        *,
        event_id: str,
        event_type: str,
        recovery_id: str,
        actor_id: str,
        reason: str,
        payload: dict[str, object],
    ) -> AuditEvent:
        """Build one privacy-bounded append-only legacy-domain artifact event."""
        return AuditEvent(
            id=event_id,
            entity_type="artifact_recovery_attempt",
            entity_id=recovery_id,
            event_type=event_type,
            actor_id=actor_id,
            external_subject=actor_id,
            external_issuer="workstream",
            actor_roles=[],
            claim_snapshot={},
            auth_source="external_flow",
            is_dev_auth=False,
            reason=reason,
            event_payload=payload,
            event_domain="legacy_lifecycle",
        )


@asynccontextmanager
async def _artifact_admission_transaction(
    session: AsyncSession,
    *,
    existing: bool,
):
    """Use the issuer's root transaction for guide PREP, otherwise own one."""
    if existing:
        transaction = session.sync_session.get_transaction()
        if transaction is None or not transaction.is_active or session.in_nested_transaction():
            raise ArtifactAuthorityDeniedError(
                "guide prepared authorization transaction is unavailable"
            )
        yield
        return
    async with session.begin():
        yield


class ArtifactAdmissionService:
    """Create one fully admitted put attempt without provider execution."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        namespace: ArtifactStorageNamespaceSpec,
        metrics: ArtifactAdmissionMetrics = artifact_admission_metrics,
    ) -> None:
        """Bind admission to one transaction owner and configured namespace."""
        self._session = session
        self._settings = settings
        self._namespace = namespace
        self._repo = ArtifactRepository(session)
        self._actors = ActorService(session)
        self._metrics = metrics

    async def admit(
        self,
        request: ArtifactAdmissionRequest,
        *,
        guide_prepared_authorization: GuideArtifactPreparedAuthorization | None = None,
        prepared_authorization: PreparedAuthorizationHandle | None = None,
        existing_transaction: bool = False,
    ) -> ArtifactAdmissionResult:
        """Reserve every derived scope and persist one prepared attempt atomically."""
        self._validate_request_boundary(request)
        commitment = request.source.commitment
        async with _artifact_admission_transaction(
            self._session,
            existing=existing_transaction,
        ):
            namespace = await _claim_and_validate_storage_namespace(
                self._repo,
                self._namespace,
            )
            if type(request) is GuideArtifactAdmissionRequest:
                if (
                    guide_prepared_authorization is None
                    or type(prepared_authorization) is not PreparedAuthorizationHandle
                ):
                    raise ArtifactAuthorityDeniedError(
                        "guide artifact ingest admission is unavailable"
                    )
                lineage = await self._repo.get_guide_lineage(str(request.guide_source_item_id))
                if lineage is None:
                    raise ArtifactAdmissionRelationshipError("guide source lineage is unavailable")
                facts = GuideArtifactIngestAuthorityFacts(
                    project_id=UUID(lineage.project_id),
                    guide_id=UUID(lineage.guide_id),
                    guide_source_snapshot_id=UUID(lineage.guide_source_snapshot_id),
                    guide_source_item_id=request.guide_source_item_id,
                    operation_identity=request.operation_identity,
                    request_digest=request.request_digest,
                    sha256=commitment.sha256,
                    byte_count=commitment.byte_count,
                    media_type=commitment.media_type,
                )
                if (
                    (request.project_id is not None and facts.project_id != request.project_id)
                    or (request.guide_id is not None and facts.guide_id != request.guide_id)
                    or (
                        request.guide_source_snapshot_id is not None
                        and facts.guide_source_snapshot_id != request.guide_source_snapshot_id
                    )
                    or facts.operation_identity
                    != canonical_json_hash(
                        {
                            "request_type": "guide",
                            "guide_source_item_id": str(request.guide_source_item_id),
                        }
                    )
                    or not facts.request_digest.startswith("sha256:")
                ):
                    raise ArtifactAdmissionRelationshipError(
                        "guide source request does not match canonical lineage"
                    )
                actor_profile_id = await guide_prepared_authorization.consume(
                    prepared_authorization=prepared_authorization,
                    facts=facts,
                )
                try:
                    await self._repo.stage_guide_source_ingest(
                        project_id=request.project_id,
                        guide_id=request.guide_id,
                        guide_source_snapshot_id=request.guide_source_snapshot_id,
                        guide_source_item_id=request.guide_source_item_id,
                        actor_profile_id=actor_profile_id,
                        sha256=commitment.sha256,
                        byte_count=commitment.byte_count,
                        media_type=commitment.media_type,
                    )
                except ValueError as exc:
                    raise ArtifactAdmissionRelationshipError(str(exc)) from exc
            facts = await self._derive_admission_facts(request)
            scopes = self._derive_scopes(facts)
            request_digest = canonical_json_hash(
                {
                    "operation_identity": facts.operation_identity,
                    "request_type": facts.request_type,
                    "producer_type": facts.producer_type,
                    "producer_ref": facts.producer_ref,
                    "project_id": facts.project_id,
                    "task_id": facts.task_id,
                    "guide_source_item_id": facts.guide_source_item_id,
                    "upload_item_id": facts.upload_item_id,
                    "checker_run_id": facts.checker_run_id,
                    "logical_role": facts.logical_role,
                    "sha256": commitment.sha256,
                    "byte_count": commitment.byte_count,
                    "media_type": commitment.media_type,
                    "namespace_fingerprint": namespace.namespace_fingerprint,
                    "scopes": [
                        {
                            "scope_type": scope.scope_type,
                            "scope_id": scope.scope_id,
                            "limit_bytes": scope.limit_bytes,
                        }
                        for scope in scopes
                    ],
                }
            )
            counters = await self._repo.ensure_and_lock_admission_scopes(
                [(scope.scope_type, scope.scope_id, scope.limit_bytes) for scope in scopes]
            )
            # A concurrent first caller may have committed while these shared
            # scope locks were pending. Recheck under serialization before any
            # counter or charge mutation.
            replay = await self._existing_attempt(
                facts.operation_identity,
                request_digest,
            )
            charges = await self._reserve_charges(
                scopes=scopes,
                counters=counters,
                facts=facts,
                sha256=commitment.sha256,
                byte_count=commitment.byte_count,
            )
            for counter in counters:
                self._metrics.pressure(
                    counter.scope_type, counter.counted_bytes, counter.limit_bytes
                )
            if replay is not None:
                linked_charge_ids = await self._repo.list_put_attempt_charge_ids(replay.id)
                reserved_charge_ids = tuple(sorted(charge.id for charge in charges))
                if linked_charge_ids != reserved_charge_ids:
                    raise ArtifactAdmissionConfigurationError(
                        "artifact admission replay charge set is incomplete"
                    )
                return await self._result(replay, replayed=True)
            database_now = await self._repo.database_now()
            attempt = ArtifactPutAttempt(
                id=str(uuid4()),
                producer_request_type=facts.request_type,
                producer_type=facts.producer_type,
                producer_ref=facts.producer_ref,
                project_id=facts.project_id,
                task_id=facts.task_id,
                guide_source_item_id=facts.guide_source_item_id,
                upload_item_id=facts.upload_item_id,
                checker_run_id=facts.checker_run_id,
                logical_role=facts.logical_role,
                sha256=commitment.sha256,
                byte_count=commitment.byte_count,
                media_type=commitment.media_type,
                storage_namespace_id=namespace.id,
                namespace_fingerprint=namespace.namespace_fingerprint,
                canonical_target=artifact_provider_object_ref(commitment),
                operation_identity=facts.operation_identity,
                request_digest=request_digest,
                status="prepared",
                next_run_at=None,
                executor_id=None,
                lease_expires_at=None,
                execution_generation=0,
                execution_mode=None,
                observation_count=0,
                maximum_observations=self._settings.artifact_provider_observation_maximum_attempts,
                terminal_result_code=None,
                replica_id=None,
                receipt_id=None,
                cas_version=0,
                prepared_at=database_now,
                terminal_at=None,
            )
            await self._repo.add_put_attempt(attempt, charges)
            return await self._result(attempt, replayed=False)

    @staticmethod
    def _validate_request_boundary(request: ArtifactAdmissionRequest) -> None:
        """Reject open-ended or forged internal request shapes."""
        if type(request) not in {
            GuideArtifactAdmissionRequest,
            ContributorArtifactAdmissionRequest,
            CheckerOutputArtifactAdmissionRequest,
        }:
            raise TypeError("invalid artifact admission request")
        if type(request.source) is not CommittedArtifactSource:
            raise TypeError("invalid artifact admission source")
        if type(request) is CheckerOutputArtifactAdmissionRequest:
            ArtifactAdmissionService._validate_logical_role(request.logical_role)
        if type(request) is GuideArtifactAdmissionRequest:
            lineage_claims = (
                request.project_id,
                request.guide_id,
                request.guide_source_snapshot_id,
            )
            if any(value is None for value in lineage_claims) and any(
                value is not None for value in lineage_claims
            ):
                raise TypeError("guide artifact lineage claims are incomplete")
            return
        context = request.authorization_context
        if type(context) not in {HumanAuthorizationContext, ServiceAuthorizationContext}:
            raise TypeError("invalid artifact admission authorization context")
        if (
            context.actor_status is not ActorStatus.ACTIVE
            or context.identity_link_status is not IdentityLinkStatus.ACTIVE
        ):
            raise ArtifactAdmissionRelationshipError("artifact admission actor is not active")

    async def _derive_admission_facts(self, request: ArtifactAdmissionRequest) -> _AdmissionFacts:
        """Load every product and producer relationship from authoritative rows."""
        if type(request) is GuideArtifactAdmissionRequest:
            return await self._guide_facts(request)
        if type(request) is ContributorArtifactAdmissionRequest:
            return await self._contributor_facts(request)
        if type(request) is CheckerOutputArtifactAdmissionRequest:
            return await self._checker_output_facts(request)
        raise TypeError("invalid artifact admission request")

    async def _guide_facts(self, request: GuideArtifactAdmissionRequest) -> _AdmissionFacts:
        """Bind committed bytes to one authoritative guide source item."""
        item_id = str(request.guide_source_item_id)
        row = await self._repo.get_guide_admission_facts(item_id)
        commitment = request.source.commitment
        if (
            row is None
            or row.content_hash != commitment.sha256
            or row.byte_count != commitment.byte_count
            or row.media_type != commitment.media_type
        ):
            raise ArtifactAdmissionRelationshipError(
                "guide source item relationship is unavailable"
            )
        operation_identity = canonical_json_hash(
            {"request_type": "guide", "guide_source_item_id": item_id}
        )
        return _AdmissionFacts(
            request_type="guide",
            producer_type="actor_profile",
            producer_ref=row.captured_by,
            project_id=row.project_id,
            guide_id=row.guide_id,
            task_id=None,
            guide_source_item_id=item_id,
            guide_source_snapshot_id=row.guide_source_snapshot_id,
            upload_item_id=None,
            checker_run_id=None,
            logical_role=None,
            operation_identity=operation_identity,
        )

    async def _contributor_facts(
        self, request: ContributorArtifactAdmissionRequest
    ) -> _AdmissionFacts:
        """Bind committed bytes to one contributor-owned upload item."""
        context = request.authorization_context
        if context.actor_kind is not ActorKind.HUMAN:
            raise ArtifactAdmissionRelationshipError(
                "contributor artifact producer must be a human actor"
            )
        await self._require_active_human_actor(context)
        item_id = str(request.upload_item_id)
        row = await self._repo.get_contributor_admission_facts(item_id)
        commitment = request.source.commitment
        if (
            row is None
            or row.actor_profile_id != str(context.actor_profile_id)
            or row.task_id is None
            or row.session_state != "open"
            or row.item_state not in {"reserved", "replay_required"}
            or row.expected_sha256 != commitment.sha256
            or row.expected_size != commitment.byte_count
            or row.media_type != commitment.media_type
        ):
            raise ArtifactAdmissionRelationshipError(
                "contributor upload item relationship is unavailable"
            )
        operation_identity = canonical_json_hash(
            {"request_type": "contributor", "upload_item_id": item_id}
        )
        return _AdmissionFacts(
            request_type="contributor",
            producer_type="actor_profile",
            producer_ref=str(context.actor_profile_id),
            project_id=row.project_id,
            guide_id=None,
            task_id=row.task_id,
            guide_source_item_id=None,
            guide_source_snapshot_id=None,
            upload_item_id=item_id,
            checker_run_id=None,
            logical_role=None,
            operation_identity=operation_identity,
        )

    async def _checker_output_facts(
        self, request: CheckerOutputArtifactAdmissionRequest
    ) -> _AdmissionFacts:
        """Bind committed bytes to one run and fixed checker service actor."""
        context = request.authorization_context
        if context.actor_kind is not ActorKind.SERVICE:
            raise ArtifactAdmissionRelationshipError(
                "checker output producer must be a service actor"
            )
        logical_role = request.logical_role
        service_actor = await self._actors.lock_admission_proof(
            context.actor_profile_id,
            context.identity_link_id,
        )
        if (
            service_actor is None
            or service_actor.actor_kind != "service"
            or service_actor.actor_status != "active"
            or service_actor.identity_link_id != str(context.identity_link_id)
            or service_actor.identity_link_subject_kind != "service"
            or service_actor.identity_link_status != "active"
            or service_actor.service_identity != ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value
        ):
            raise ArtifactAdmissionRelationshipError(
                "checker output service identity is unavailable"
            )
        checker_run_id = str(request.checker_run_id)
        row = await self._repo.get_checker_output_admission_facts(checker_run_id)
        if row is None:
            raise ArtifactAdmissionRelationshipError("checker run relationship is unavailable")
        operation_identity = canonical_json_hash(
            {
                "request_type": "checker_output",
                "checker_run_id": checker_run_id,
                "logical_role": logical_role,
            }
        )
        return _AdmissionFacts(
            request_type="checker_output",
            producer_type="service_identity",
            producer_ref=ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value,
            project_id=row.project_id,
            guide_id=None,
            task_id=row.task_id,
            guide_source_item_id=None,
            guide_source_snapshot_id=None,
            upload_item_id=None,
            checker_run_id=checker_run_id,
            logical_role=logical_role,
            operation_identity=operation_identity,
        )

    async def _require_active_human_actor(self, context: AuthorizationContext) -> None:
        """Revalidate and lock exact human identity state inside admission."""
        actor = await self._actors.lock_admission_proof(
            context.actor_profile_id,
            context.identity_link_id,
        )
        if (
            actor is None
            or actor.actor_kind != "human"
            or actor.actor_status != "active"
            or actor.service_identity is not None
            or actor.identity_link_id != str(context.identity_link_id)
            or actor.identity_link_subject_kind != "human"
            or actor.identity_link_status != "active"
        ):
            raise ArtifactAdmissionRelationshipError(
                "artifact admission human identity is unavailable"
            )

    @staticmethod
    def _validate_logical_role(value: str) -> str:
        """Require one bounded printable checker-output role."""
        if (
            not isinstance(value, str)
            or value != value.strip()
            or not value
            or not value.isascii()
            or len(value) > 100
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ArtifactAdmissionRelationshipError("checker output logical role is invalid")
        return value

    def _derive_scopes(self, facts: _AdmissionFacts) -> tuple[_AdmissionScopeSpec, ...]:
        """Derive the complete closed scope set without caller participation."""
        limits = self._configured_limits()
        scopes = [
            _AdmissionScopeSpec(
                "deployment",
                ARTIFACT_STORAGE_NAMESPACE_ID,
                limits["deployment"],
            ),
            _AdmissionScopeSpec("project", facts.project_id, limits["project"]),
            _AdmissionScopeSpec(
                "producer",
                f"{facts.producer_type}:{facts.producer_ref}",
                limits["producer"],
            ),
        ]
        if facts.task_id is not None:
            scopes.append(_AdmissionScopeSpec("task", facts.task_id, limits["task"]))
        return tuple(sorted(scopes, key=lambda value: (value.scope_type, value.scope_id)))

    def _configured_limits(self) -> dict[str, int]:
        """Return exact positive limits only for an enabled artifact backend."""
        values = {
            "task": self._settings.artifact_admission_task_maximum_bytes,
            "producer": self._settings.artifact_admission_producer_maximum_bytes,
            "project": self._settings.artifact_admission_project_maximum_bytes,
            "deployment": self._settings.artifact_admission_deployment_maximum_bytes,
        }
        if self._settings.artifact_store_backend == "disabled" or any(
            type(value) is not int or value <= 0 for value in values.values()
        ):
            raise ArtifactAdmissionConfigurationError(
                "artifact durable-byte admission is not configured"
            )
        return {key: int(value) for key, value in values.items()}

    async def _existing_attempt(
        self,
        operation_identity: str,
        request_digest: str,
    ) -> ArtifactPutAttempt | None:
        """Load an exact replay or reject changed input for one operation."""
        existing = await self._repo.get_put_attempt_by_operation(operation_identity)
        if existing is None:
            return None
        if existing.request_digest != request_digest:
            raise ArtifactAdmissionConflictError("artifact admission operation input changed")
        return existing

    async def _reserve_charges(
        self,
        *,
        scopes: tuple[_AdmissionScopeSpec, ...],
        counters: tuple[ArtifactAdmissionScope, ...],
        facts: _AdmissionFacts,
        sha256: str,
        byte_count: int,
    ) -> tuple[ArtifactAdmissionCharge, ...]:
        """Reserve unique content under every locked scope or fail atomically."""
        counter_by_key = {(counter.scope_type, counter.scope_id): counter for counter in counters}
        if len(counter_by_key) != len(scopes):
            raise ArtifactAdmissionConfigurationError("artifact admission scope set is incomplete")
        database_now = await self._repo.database_now()
        charges: list[ArtifactAdmissionCharge] = []
        for scope in scopes:
            counter = counter_by_key[(scope.scope_type, scope.scope_id)]
            if counter.limit_bytes != scope.limit_bytes:
                if scope.limit_bytes < counter.counted_bytes:
                    raise ArtifactAdmissionConfigurationError(
                        "artifact admission configured limit is below counted bytes"
                    )
                counter.limit_bytes = scope.limit_bytes
                counter.cas_version += 1
            charge = await self._repo.get_admission_charge(
                scope_type=scope.scope_type,
                scope_id=scope.scope_id,
                sha256=sha256,
                byte_count=byte_count,
            )
            if charge is not None and charge.state in {"provisional", "completed"}:
                charges.append(charge)
                continue
            if counter.counted_bytes + byte_count > counter.limit_bytes:
                raise ArtifactAdmissionCapacityError(
                    f"artifact durable-byte limit exceeded for {scope.scope_type} scope"
                )
            counter.counted_bytes += byte_count
            counter.cas_version += 1
            if charge is None:
                charge = await self._repo.add_admission_charge(
                    ArtifactAdmissionCharge(
                        id=str(uuid4()),
                        scope_type=scope.scope_type,
                        scope_id=scope.scope_id,
                        sha256=sha256,
                        byte_count=byte_count,
                        producer_type=facts.producer_type,
                        producer_ref=facts.producer_ref,
                        creating_operation_identity=facts.operation_identity,
                        state="provisional",
                        cas_version=0,
                        reserved_at=database_now,
                        completed_at=None,
                        released_at=None,
                    )
                )
            elif charge.state == "released":
                charge.state = "provisional"
                charge.reserved_at = database_now
                charge.released_at = None
                charge.cas_version += 1
            else:
                raise ArtifactAdmissionConflictError("artifact admission charge state is invalid")
            charges.append(charge)
        return tuple(charges)

    async def _result(
        self, attempt: ArtifactPutAttempt, *, replayed: bool
    ) -> ArtifactAdmissionResult:
        """Return one detached-safe internal result."""
        charge_ids = await self._repo.list_put_attempt_charge_ids(attempt.id)
        return ArtifactAdmissionResult(
            attempt_id=UUID(attempt.id),
            status=attempt.status,
            operation_identity=attempt.operation_identity,
            request_digest=attempt.request_digest,
            charge_ids=tuple(UUID(charge_id) for charge_id in charge_ids),
            replayed=replayed,
        )


def _attempt_commitment(attempt: ArtifactPutAttempt) -> ArtifactCommitment:
    return ArtifactCommitment(
        sha256=attempt.sha256,
        byte_count=attempt.byte_count,
        media_type=attempt.media_type,
    )


def _put_authority_facts(
    attempt: ArtifactPutAttempt, executor_id: UUID, generation: int
) -> ArtifactPutAttemptAuthorityFacts:
    return ArtifactPutAttemptAuthorityFacts(
        resource_type=ArtifactInternalResourceType.PUT_ATTEMPT,
        resource_id=UUID(attempt.id),
        operation_identity=attempt.operation_identity,
        namespace_fingerprint=attempt.namespace_fingerprint,
        sha256=attempt.sha256,
        byte_count=attempt.byte_count,
        executor_id=executor_id,
        execution_generation=generation,
    )


def _verification_authority_facts(
    job: ArtifactVerificationJob,
    replica: ArtifactReplica,
    attempt: ArtifactPutAttempt,
    executor_id: UUID,
    generation: int,
) -> ArtifactVerificationAuthorityFacts:
    return ArtifactVerificationAuthorityFacts(
        resource_type=ArtifactInternalResourceType.VERIFICATION_JOB,
        resource_id=UUID(job.id),
        replica_id=UUID(replica.id),
        namespace_fingerprint=replica.namespace_fingerprint,
        provider_object_ref=replica.provider_object_ref,
        sha256=attempt.sha256,
        byte_count=attempt.byte_count,
        executor_id=executor_id,
        execution_generation=generation,
    )


def _verification_relationship_matches(
    job: ArtifactVerificationJob,
    replica: ArtifactReplica,
    attempt: ArtifactPutAttempt,
    content: ArtifactContent | None,
) -> bool:
    """Prove one locked verification chain names the same immutable bytes."""
    return (
        content is not None
        and job.replica_id == replica.id
        and attempt.replica_id == replica.id
        and replica.content_id == content.id
        and content.sha256 == attempt.sha256
        and content.byte_count == attempt.byte_count
    )


def _matching_put_fence(
    attempt: ArtifactPutAttempt | None, executor_id: UUID, generation: int
) -> bool:
    return (
        attempt is not None
        and attempt.status == "put_in_flight"
        and attempt.executor_id == str(executor_id)
        and attempt.execution_generation == generation
    )


def _matching_job_fence(
    job: ArtifactVerificationJob | None, executor_id: UUID, generation: int
) -> bool:
    return (
        job is not None
        and job.status == "running"
        and job.executor_id == str(executor_id)
        and job.execution_generation == generation
    )


def _clear_put_fence(attempt: ArtifactPutAttempt) -> None:
    attempt.executor_id = None
    attempt.lease_expires_at = None
    attempt.execution_mode = None
    attempt.cas_version += 1


def _clear_job_fence(job: ArtifactVerificationJob) -> None:
    job.executor_id = None
    job.lease_expires_at = None
    job.cas_version += 1


async def validate_artifact_storage_namespace_at_startup(
    store: ArtifactStoreBootstrap,
    settings: Settings,
) -> ArtifactStoreNamespaceClaim:
    """Claim one pinned namespace and return its exact initialization proof."""
    namespace = artifact_storage_namespace_spec(settings, store)
    async with get_session_factory()() as session:
        async with session.begin():
            await _claim_and_validate_storage_namespace(
                ArtifactRepository(session),
                namespace,
            )
    return ArtifactStoreNamespaceClaim(
        adapter_identity=store.identity,
        namespace_identity=store.namespace_identity,
        namespace_fingerprint=namespace.namespace_fingerprint,
    )


async def _claim_and_validate_storage_namespace(
    repository: ArtifactRepository,
    namespace: ArtifactStorageNamespaceSpec,
) -> ArtifactStorageNamespace:
    """Atomically claim the singleton or reject deployment identity drift."""
    candidate = ArtifactStorageNamespace(
        id=ARTIFACT_STORAGE_NAMESPACE_ID,
        backend=namespace.backend,
        adapter=namespace.adapter,
        provider_profile=namespace.provider_profile,
        namespace_descriptor=namespace.namespace_descriptor,
        namespace_fingerprint=namespace.namespace_fingerprint,
    )
    persisted = await repository.claim_storage_namespace(candidate)
    if (
        persisted.backend != candidate.backend
        or persisted.adapter != candidate.adapter
        or persisted.provider_profile != candidate.provider_profile
        or persisted.namespace_descriptor != candidate.namespace_descriptor
        or persisted.namespace_fingerprint != candidate.namespace_fingerprint
    ):
        raise ArtifactStorageNamespaceError("artifact storage namespace does not match")
    return persisted
