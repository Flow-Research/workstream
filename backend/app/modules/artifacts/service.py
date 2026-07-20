"""Internal orchestration for namespace-fenced immutable artifact storage."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.hashing import canonical_json_hash
from app.db.session import get_session_factory
from app.interfaces.artifacts import (
    ArtifactStore,
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
    ArtifactStorageNamespace,
)
from app.modules.artifacts.repository import ArtifactRepository
from app.modules.artifacts.schemas import (
    ArtifactAdmissionRequest,
    ArtifactAdmissionResult,
    CheckerOutputArtifactAdmissionRequest,
    ContributorArtifactAdmissionRequest,
    GuideArtifactAdmissionRequest,
)
from app.modules.artifacts.sources import CommittedArtifactSource
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    AuthorizationContext,
    HumanAuthorizationContext,
    IdentityLinkStatus,
    ServiceAuthorizationContext,
)


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
    """Dormant owner of writable storage until 02C2 adds attempt execution."""

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

    async def _claim_and_validate_namespace(self) -> ArtifactStorageNamespace:
        """Atomically claim the singleton or reject deployment identity drift."""
        return await _claim_and_validate_storage_namespace(self._repo, self._namespace)


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
                [
                    (scope.scope_type, scope.scope_id, scope.limit_bytes)
                    for scope in scopes
                ]
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
                linked_charge_ids = await self._repo.list_put_attempt_charge_ids(
                    replay.id
                )
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
        if type(request.authorization_context) not in {
            HumanAuthorizationContext,
            ServiceAuthorizationContext,
        }:
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
            raise ArtifactAdmissionRelationshipError(
                "artifact admission actor is not active"
            )

    async def _derive_admission_facts(
        self, request: ArtifactAdmissionRequest
    ) -> _AdmissionFacts:
        """Load every product and producer relationship from authoritative rows."""
        if type(request) is GuideArtifactAdmissionRequest:
            return await self._guide_facts(request)
        if type(request) is ContributorArtifactAdmissionRequest:
            return await self._contributor_facts(request)
        if type(request) is CheckerOutputArtifactAdmissionRequest:
            return await self._checker_output_facts(request)
        raise TypeError("invalid artifact admission request")

    async def _guide_facts(
        self, request: GuideArtifactAdmissionRequest
    ) -> _AdmissionFacts:
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
            or service_actor.service_identity
            != ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value
        ):
            raise ArtifactAdmissionRelationshipError(
                "checker output service identity is unavailable"
            )
        checker_run_id = str(request.checker_run_id)
        row = await self._repo.get_checker_output_admission_facts(checker_run_id)
        if row is None:
            raise ArtifactAdmissionRelationshipError(
                "checker run relationship is unavailable"
            )
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

    async def _require_active_human_actor(
        self, context: AuthorizationContext
    ) -> None:
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
            raise ArtifactAdmissionRelationshipError(
                "checker output logical role is invalid"
            )
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
            raise ArtifactAdmissionConflictError(
                "artifact admission operation input changed"
            )
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
        counter_by_key = {
            (counter.scope_type, counter.scope_id): counter for counter in counters
        }
        if len(counter_by_key) != len(scopes):
            raise ArtifactAdmissionConfigurationError(
                "artifact admission scope set is incomplete"
            )
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
                raise ArtifactAdmissionConflictError(
                    "artifact admission charge state is invalid"
                )
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
