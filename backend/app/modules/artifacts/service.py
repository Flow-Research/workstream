"""Internal orchestration for namespace-fenced immutable artifact storage."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

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
    ArtifactStorageNamespace,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
)
from app.modules.artifacts.repository import ArtifactRepository
from app.modules.artifacts.schemas import (
    ArtifactAdmissionRequest,
    ArtifactAdmissionResult,
    ArtifactInternalAuthority,
    ArtifactInternalResourceType,
    ArtifactPutAttemptAuthorityFacts,
    ArtifactPendingWorkAuthorityFacts,
    ArtifactVerificationAuthorityFacts,
    DenyArtifactInternalAuthority,
    CheckerOutputArtifactAdmissionRequest,
    ContributorArtifactAdmissionRequest,
    GuideArtifactAdmissionRequest,
)
from app.modules.artifacts.sources import CommittedArtifactSource
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    AuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.authorization.catalogue import ActionId


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
    task_id: str | None
    guide_source_item_id: str | None
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
        await self._authority.preflight(
            service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
            facts=facts,
        )
        async with self._session.begin():
            claimed = await self._repo.claim_put_attempt(
                attempt_id=attempt_id,
                executor_id=executor_id,
                lease_seconds=self._settings.artifact_execution_lease_seconds,
                mode="caller_put",
                expected_generation=candidate_generation,
            )
            if claimed is None:
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
            return await self._record_put_unavailable(claimed, executor_id)
        except ArtifactStoreError:
            # Any non-acknowledgement provider error is resolved through the
            # read-only observation path; a caller write never fabricates
            # observation evidence.
            return await self._record_put_unavailable(claimed, executor_id)
        return await self._complete_transaction_b(
            claimed=claimed,
            executor_id=executor_id,
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
        await self._authority.preflight(
            service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
            facts=facts,
        )
        async with self._session.begin():
            claimed = await self._repo.claim_put_attempt(
                attempt_id=attempt_id,
                executor_id=executor_id,
                lease_seconds=self._settings.artifact_execution_lease_seconds,
                mode="observation",
                expected_generation=candidate_generation,
            )
            if claimed is None:
                return "stale"
        commitment = _attempt_commitment(claimed)
        try:
            observation = await self._store.observe_put_result(commitment)
            if not observation.committed:
                return await self._record_put_absence(claimed, executor_id)
            observed_sha256, observed_size = await self._read_complete(
                observation.provider_object_ref
            )
        except ArtifactIntegrityError:
            try:
                observed_sha256, observed_size = await self._read_complete(claimed.canonical_target)
            except (ArtifactStoreUnavailableError, TimeoutError):
                return await self._record_put_unavailable(claimed, executor_id)
            except ArtifactStoreError:
                return await self._record_put_conflict(claimed, executor_id)
            return await self._record_put_mismatch(
                claimed,
                executor_id,
                claimed.canonical_target,
                observed_sha256,
                observed_size,
            )
        except ArtifactObjectMissingError:
            return await self._record_put_absence(claimed, executor_id)
        except (ArtifactStoreUnavailableError, TimeoutError):
            return await self._record_put_unavailable(claimed, executor_id)
        except ArtifactStoreError:
            return await self._record_put_conflict(claimed, executor_id)
        if observed_sha256 != claimed.sha256 or observed_size != claimed.byte_count:
            return await self._record_put_mismatch(
                claimed,
                executor_id,
                observation.provider_object_ref,
                observed_sha256,
                observed_size,
            )
        return await self._complete_transaction_b(
            claimed=claimed,
            executor_id=executor_id,
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
        await self._authority.preflight(
            service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
            action_id=ActionId.ARTIFACT_VERIFICATION_EXECUTE,
            facts=facts,
        )
        async with self._session.begin() as claim_transaction:
            persisted_namespace = await self._claim_and_validate_namespace()
            claimed_result = await self._repo.claim_verification_job(
                job_id=job_id,
                executor_id=executor_id,
                lease_seconds=self._settings.artifact_execution_lease_seconds,
                expected_generation=candidate_generation,
            )
            if claimed_result is None:
                return "stale"
            claimed = await self._repo.lock_verification_job(str(job_id))
            if not _matching_job_fence(claimed, executor_id, candidate_generation + 1):
                return "stale"
            assert claimed is not None
            execution_replica = await self._repo.lock_replica(claimed.replica_id)
            execution_attempt = await self._repo.lock_put_attempt(
                claimed.originating_put_attempt_id
            )
            if execution_replica is None or execution_attempt is None:
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
                await self._authority.revalidate_terminal(
                    service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
                    action_id=ActionId.ARTIFACT_VERIFICATION_EXECUTE,
                    facts=execution_facts,
                )
                now = await self._repo.database_now()
                await self._terminalize_verification_conflict(claimed, now)
                relationship_conflict = True
            else:
                relationship_conflict = False
        if relationship_conflict:
            return "conflict"
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
        provider_object_ref: str,
        replayed: bool,
        observed: bool,
    ) -> str:
        async with self._session.begin():
            attempt = await self._repo.lock_put_attempt(claimed.id)
            if not _matching_put_fence(attempt, executor_id, claimed.execution_generation):
                return "stale"
            assert attempt is not None
            facts = _put_authority_facts(attempt, executor_id, claimed.execution_generation)
            await self._authority.revalidate_terminal(
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
        return "verified" if observed else "stored_pending_verification"

    async def _record_put_unavailable(self, claimed: ArtifactPutAttempt, executor_id: UUID) -> str:
        async with self._session.begin():
            attempt = await self._repo.lock_put_attempt(claimed.id)
            if not _matching_put_fence(attempt, executor_id, claimed.execution_generation):
                return "stale"
            assert attempt is not None
            await self._authority.revalidate_terminal(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=_put_authority_facts(attempt, executor_id, claimed.execution_generation),
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

    async def _record_put_absence(self, claimed: ArtifactPutAttempt, executor_id: UUID) -> str:
        async with self._session.begin():
            attempt = await self._repo.lock_put_attempt(claimed.id)
            if not _matching_put_fence(attempt, executor_id, claimed.execution_generation):
                return "stale"
            assert attempt is not None
            await self._authority.revalidate_terminal(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=_put_authority_facts(attempt, executor_id, claimed.execution_generation),
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
        provider_object_ref: str,
        observed_sha256: str,
        observed_size: int,
    ) -> str:
        return await self._record_put_terminal_observation(
            claimed,
            executor_id,
            status="integrity_mismatch",
            outcome="observed_integrity_mismatch",
            observed_sha256=observed_sha256,
            observed_size=observed_size,
            provider_object_ref=provider_object_ref,
        )

    async def _record_put_conflict(self, claimed: ArtifactPutAttempt, executor_id: UUID) -> str:
        return await self._record_put_terminal_observation(
            claimed,
            executor_id,
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
        *,
        status: str,
        outcome: str,
        observed_sha256: str | None,
        observed_size: int | None,
        provider_object_ref: str | None,
    ) -> str:
        async with self._session.begin():
            attempt = await self._repo.lock_put_attempt(claimed.id)
            if not _matching_put_fence(attempt, executor_id, claimed.execution_generation):
                return "stale"
            assert attempt is not None
            await self._authority.revalidate_terminal(
                service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
                action_id=ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
                facts=_put_authority_facts(attempt, executor_id, claimed.execution_generation),
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
            job = await self._repo.lock_verification_job(claimed.id)
            if not _matching_job_fence(job, executor_id, claimed.execution_generation):
                return "stale"
            assert job is not None
            replica = await self._repo.lock_replica(job.replica_id)
            attempt = await self._repo.lock_put_attempt(job.originating_put_attempt_id)
            if replica is None or attempt is None:
                return "conflict"
            content = await self._repo.lock_content(replica.content_id)
            terminal_facts = _verification_authority_facts(
                job, replica, attempt, executor_id, claimed.execution_generation
            )
            if terminal_facts != expected_facts:
                return "stale"
            await self._authority.revalidate_terminal(
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
            job = await self._repo.lock_verification_job(claimed.id)
            if not _matching_job_fence(job, executor_id, claimed.execution_generation):
                return "stale"
            assert job is not None
            replica = await self._repo.lock_replica(job.replica_id)
            attempt = await self._repo.lock_put_attempt(job.originating_put_attempt_id)
            if replica is None or attempt is None:
                return "conflict"
            content = await self._repo.lock_content(replica.content_id)
            terminal_facts = _verification_authority_facts(
                job, replica, attempt, executor_id, claimed.execution_generation
            )
            if terminal_facts != expected_facts:
                return "stale"
            await self._authority.revalidate_terminal(
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
                        item.error_code = "artifact_integrity_failure"
                        item_changed = True
                    if item_changed:
                        item.cas_version += 1
            job.status = outcome
            job.next_run_at = None
            job.terminal_result_code = outcome
            job.terminal_at = now
            _clear_job_fence(job)
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
        facts = ArtifactPendingWorkAuthorityFacts(
            resource_type=ArtifactInternalResourceType.PENDING_WORK,
            resource_id="workstream:artifact_pending_work",
            scanner_kind="put_resolution_and_verification",
            database_cutoff_iso=cutoff.isoformat(),
            page_size=self._settings.artifact_pending_work_scan_page_size,
        )
        await self._authority.preflight(
            service_identity=ServiceIdentity.ARTIFACT_SCHEDULER,
            action_id=ActionId.ARTIFACT_PENDING_WORK_SCAN,
            facts=facts,
        )
        async with self._session.begin():
            put_ids = await self._repo.list_due_put_attempt_ids(
                cutoff=cutoff,
                limit=self._settings.artifact_pending_work_scan_page_size,
            )
            remaining = self._settings.artifact_pending_work_scan_page_size - len(put_ids)
            job_ids = await self._repo.list_due_verification_job_ids(
                cutoff=cutoff,
                limit=remaining,
            )
        for attempt_id in put_ids:
            await self._publish_put_attempt(attempt_id)
        for job_id in job_ids:
            await self._publish_verification_job(job_id)
        return len(put_ids) + len(job_ids)


class ArtifactAdmissionService:
    """Create one fully admitted put attempt without provider execution."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        namespace: ArtifactStorageNamespaceSpec,
    ) -> None:
        """Bind admission to one transaction owner and configured namespace."""
        self._session = session
        self._settings = settings
        self._namespace = namespace
        self._repo = ArtifactRepository(session)
        self._actors = ActorService(session)

    async def admit(
        self,
        request: ArtifactAdmissionRequest,
    ) -> ArtifactAdmissionResult:
        """Reserve every derived scope and persist one prepared attempt atomically."""
        self._validate_request_boundary(request)
        commitment = request.source.commitment
        async with self._session.begin():
            namespace = await _claim_and_validate_storage_namespace(
                self._repo,
                self._namespace,
            )
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
        if type(request.authorization_context) is not AuthorizationContext:
            raise TypeError("invalid artifact admission authorization context")
        if type(request.source) is not CommittedArtifactSource:
            raise TypeError("invalid artifact admission source")
        if type(request) is CheckerOutputArtifactAdmissionRequest:
            ArtifactAdmissionService._validate_logical_role(request.logical_role)
        context = request.authorization_context
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
        context = request.authorization_context
        if context.actor_kind is not ActorKind.HUMAN:
            raise ArtifactAdmissionRelationshipError(
                "guide artifact producer must be a human actor"
            )
        await self._require_active_human_actor(context)
        item_id = str(request.guide_source_item_id)
        row = await self._repo.get_guide_admission_facts(item_id)
        commitment = request.source.commitment
        if (
            row is None
            or row.captured_by != str(context.actor_profile_id)
            or row.content_hash != commitment.sha256
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
            task_id=None,
            guide_source_item_id=item_id,
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
            task_id=row.task_id,
            guide_source_item_id=None,
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
            task_id=row.task_id,
            guide_source_item_id=None,
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
                raise ArtifactAdmissionConfigurationError(
                    "artifact admission scope limit does not match configuration"
                )
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
