"""Internal orchestration for namespace-fenced immutable artifact storage."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.cancellation import await_cancellation_resistant
from app.db.session import get_session_factory
from app.interfaces.artifacts import (
    ArtifactInputMismatchError,
    ArtifactIntegrityError,
    ArtifactPutResult,
    ArtifactStore,
    ArtifactStoreBootstrap,
    ArtifactStoreError,
    ArtifactStoreNamespaceClaim,
    artifact_store_namespace_material,
)
from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.modules.artifacts.models import (
    ArtifactContent,
    ArtifactOperationReceipt,
    ArtifactReplica,
    ArtifactStorageNamespace,
    ArtifactUploadItem,
    ArtifactUploadSession,
)
from app.modules.artifacts.repository import ArtifactRepository
from app.modules.artifacts.sources import ArtifactCommitment, CommittedArtifactSource


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


@dataclass(frozen=True, slots=True)
class ProviderAttemptFence:
    """Committed item CAS value fencing one provider call."""

    item_cas: int


def artifact_storage_namespace_spec(
    settings: Settings,
    store: ArtifactStoreBootstrap,
) -> ArtifactStorageNamespaceSpec:
    """Build the canonical descriptor from one already-pinned provider root."""
    identity = store.identity
    if type(identity) is not ExternalServiceAdapterIdentity:
        raise ArtifactStorageNamespaceError("artifact adapter identity is invalid")
    if settings.artifact_store_backend != identity.provider_key:
        raise ArtifactStorageNamespaceError("artifact adapter identity does not match configuration")
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
    """Sole internal owner of the writable ArtifactStore capability."""

    def __init__(
        self,
        session: AsyncSession,
        store: ArtifactStore,
        namespace: ArtifactStorageNamespaceSpec,
    ) -> None:
        """Bind one database session, byte store, and deployment namespace."""
        self._session = session
        self._store = store
        self._namespace = namespace
        self._repo = ArtifactRepository(session)

    async def ensure_storage_namespace(self) -> ArtifactStorageNamespace:
        """Claim or validate the immutable singleton before provider access."""
        async with self._session.begin():
            return await self._claim_and_validate_namespace()

    async def put_reserved_item(
        self,
        item_id: str,
        source: CommittedArtifactSource,
        *,
        correlation_id: str | None = None,
    ) -> ArtifactPutResult:
        """Publish one already-reserved internal item without activating product ingest."""
        commitment = source.commitment
        fence = await self._start_put(item_id, commitment)
        try:
            result = await self._store.put(source)
        except asyncio.CancelledError as cancellation:
            try:
                await await_cancellation_resistant(
                    self._mark_replay_required(item_id, fence)
                )
            except BaseException:
                raise cancellation from None
            raise
        except ArtifactStoreError as exc:
            if exc.retryable:
                await self._mark_replay_required(item_id, fence)
            else:
                await self._fail_put(item_id, exc.code, fence)
            raise
        except BaseException:
            await self._mark_replay_required(item_id, fence)
            raise

        try:
            await self._finalize_put(
                item_id,
                commitment,
                result,
                fence,
                correlation_id=correlation_id or str(uuid4()),
            )
        except (ArtifactIntegrityError, ArtifactInputMismatchError) as exc:
            await self._fail_put(item_id, exc.code, fence)
            raise
        except asyncio.CancelledError as cancellation:
            try:
                await await_cancellation_resistant(
                    self._mark_replay_required(item_id, fence)
                )
            except BaseException:
                raise cancellation from None
            raise
        except BaseException:
            await self._mark_replay_required(item_id, fence)
            raise
        return result

    async def _start_put(
        self,
        item_id: str,
        commitment: ArtifactCommitment,
    ) -> ProviderAttemptFence:
        """Transaction A validates namespace and exact reserved commitment."""
        async with self._session.begin():
            await self._claim_and_validate_namespace()
            item = await self._repo.lock_upload_item(item_id)
            if item is None:
                raise ArtifactIngestStateError("artifact upload item does not exist")
            upload_session = await self._repo.lock_upload_session(item.session_id)
            if upload_session is None or upload_session.state != "open":
                raise ArtifactIngestStateError("artifact upload session is not open")
            if item.state not in {"reserved", "replay_required"}:
                raise ArtifactIngestStateError("artifact upload item cannot be stored")
            if (
                item.expected_sha256 != commitment.sha256
                or item.expected_size != commitment.byte_count
                or item.media_type != commitment.media_type
                or commitment.byte_count > item.reserved_bytes
            ):
                raise ArtifactIngestStateError("artifact upload commitment changed")
            item.state = "uploading"
            item.error_code = None
            item.cas_version += 1
            upload_session.cas_version += 1
            return ProviderAttemptFence(item.cas_version)

    async def _finalize_put(
        self,
        item_id: str,
        commitment: ArtifactCommitment,
        result: ArtifactPutResult,
        fence: ProviderAttemptFence,
        *,
        correlation_id: str,
    ) -> None:
        """Transaction B records acknowledgement without making bytes bindable."""
        async with self._session.begin():
            namespace = await self._claim_and_validate_namespace()
            item, upload_session = await self._locked_attempt(item_id, fence)
            existing_receipt = await self._repo.get_receipt_for_item(item.id)
            if existing_receipt is not None:
                raise ArtifactIntegrityError("artifact upload item already has put evidence")

            content = await self._repo.get_or_create_content(
                ArtifactContent(
                    id=str(uuid4()),
                    sha256=commitment.sha256,
                    byte_count=commitment.byte_count,
                    media_type=commitment.media_type,
                    normalized_display_name=item.display_name,
                )
            )
            replica = await self._repo.get_or_create_replica(
                ArtifactReplica(
                    id=str(uuid4()),
                    content_id=content.id,
                    storage_namespace_id=namespace.id,
                    namespace_fingerprint=namespace.namespace_fingerprint,
                    adapter=namespace.adapter,
                    provider_profile=namespace.provider_profile,
                    provider_object_ref=result.provider_object_ref,
                    verification_state="pending",
                    availability_state="unknown",
                    integrity_state="unknown",
                )
            )
            if (
                replica.content_id != content.id
                or replica.namespace_fingerprint != namespace.namespace_fingerprint
                or replica.adapter != namespace.adapter
                or replica.provider_profile != namespace.provider_profile
            ):
                raise ArtifactIntegrityError("provider object reference changed content identity")

            await self._repo.add_receipt(
                ArtifactOperationReceipt(
                    id=str(uuid4()),
                    upload_item_id=item.id,
                    replica_id=replica.id,
                    operation="put",
                    idempotency_key=item.idempotency_key,
                    request_digest=item.request_digest,
                    provider_object_ref=result.provider_object_ref,
                    replayed=result.replayed,
                    outcome="stored_pending_verification",
                    attempt_number=1,
                    correlation_id=correlation_id,
                    details=[
                        {
                            "name": "namespace_fingerprint",
                            "value": namespace.namespace_fingerprint,
                        }
                    ],
                )
            )
            item.state = "stored_pending_verification"
            item.content_id = content.id
            item.provider_object_ref = result.provider_object_ref
            item.cas_version += 1
            self._apply_committed_accounting(upload_session, item, commitment.byte_count)

    async def _claim_and_validate_namespace(self) -> ArtifactStorageNamespace:
        """Atomically claim the singleton or reject deployment identity drift."""
        return await _claim_and_validate_storage_namespace(self._repo, self._namespace)

    async def _locked_attempt(
        self,
        item_id: str,
        fence: ProviderAttemptFence,
    ) -> tuple[ArtifactUploadItem, ArtifactUploadSession]:
        """Reload and fence the exact item/session pair after provider I/O."""
        item = await self._repo.lock_upload_item(item_id)
        if item is None or item.state != "uploading" or item.cas_version != fence.item_cas:
            raise ArtifactIngestStateError("artifact upload item is not awaiting acknowledgement")
        upload_session = await self._repo.lock_upload_session(item.session_id)
        if (
            upload_session is None
            or upload_session.state != "open"
        ):
            raise ArtifactIngestStateError("artifact upload session is not open")
        return item, upload_session

    @staticmethod
    def _apply_committed_accounting(
        upload_session: ArtifactUploadSession,
        item: ArtifactUploadItem,
        byte_count: int,
    ) -> None:
        """Move one item from reserved capacity to acknowledged byte usage."""
        ArtifactStorageOrchestrator._validate_reserved_accounting(upload_session, item)
        upload_session.reserved_bytes -= item.reserved_bytes
        upload_session.reserved_items -= 1
        upload_session.current_bytes += byte_count
        upload_session.current_items += 1
        upload_session.cas_version += 1

    async def _mark_replay_required(
        self,
        item_id: str,
        fence: ProviderAttemptFence,
    ) -> None:
        """Record an ambiguous acknowledgement only when the attempt fence matches."""
        await self._session.rollback()
        async with self._session.begin():
            item = await self._repo.lock_upload_item(item_id)
            if item is None or item.state != "uploading" or item.cas_version != fence.item_cas:
                return
            item.state = "replay_required"
            item.error_code = "artifact_put_acknowledgement_unknown"
            item.cas_version += 1

    async def _fail_put(
        self,
        item_id: str,
        error_code: str,
        fence: ProviderAttemptFence,
    ) -> None:
        """Fail one terminal provider attempt and release its reservation once."""
        await self._session.rollback()
        async with self._session.begin():
            item = await self._repo.lock_upload_item(item_id)
            if item is None or item.state != "uploading" or item.cas_version != fence.item_cas:
                return
            upload_session = await self._repo.lock_upload_session(item.session_id)
            if upload_session is None:
                raise ArtifactIntegrityError("artifact upload session is missing")
            self._validate_reserved_accounting(upload_session, item)
            item.state = "failed"
            item.error_code = error_code
            item.cas_version += 1
            upload_session.reserved_bytes -= item.reserved_bytes
            upload_session.reserved_items -= 1
            upload_session.cas_version += 1

    @staticmethod
    def _validate_reserved_accounting(
        upload_session: ArtifactUploadSession,
        item: ArtifactUploadItem,
    ) -> None:
        """Reject aggregate drift before consuming one item's reservation."""
        if (
            upload_session.reserved_bytes < item.reserved_bytes
            or upload_session.reserved_items < 1
        ):
            raise ArtifactIntegrityError(
                "artifact upload session reservation accounting is invalid"
            )


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
