"""ART-owned composition for fixed-service prepared authorization."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.repository import ActorRepository
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    ArtifactInternalAuthorityFacts,
    ArtifactInternalResourceType,
    ArtifactPendingWorkAuthorityFacts,
    ArtifactPutAttemptAuthorityFacts,
    ArtifactVerificationAuthorityFacts,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import (
    PreparedAuthorizationHandle,
    PreparedAuthorizationService,
)
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    ArtifactPendingWorkResourceContext,
    ArtifactPutAttemptResourceContext,
    ArtifactVerificationJobResourceContext,
    IdentityLinkStatus,
    PreparedAuthorizationInput,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    AuthorizationDecision,
    AuthorizationDenied,
    PreparedAuthorizationUnsupported,
    ServiceAuthorizationContext,
)


class PreparedArtifactInternalAuthority:
    """Adapt one fixed ART service to the shared transaction-bound PREP kernel."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        service_identity: ServiceIdentity,
        request_id: UUID,
        correlation_id: UUID,
    ) -> None:
        self._session = session
        self._service_identity = service_identity
        self._request_id = request_id
        self._correlation_id = correlation_id
        self._prepared: PreparedAuthorizationService | None = None
        self._handle: PreparedAuthorizationHandle | None = None
        self._input: PreparedAuthorizationInput | None = None
        self._facts: ArtifactInternalAuthorityFacts | None = None
        self._action_id: ActionId | None = None
        self._authorization: AuthorizationService | None = None
        self._denial: AuthorizationDecision | None = None
        self._denial_authorization: AuthorizationService | None = None

    async def prepare(
        self,
        *,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        facts: ArtifactInternalAuthorityFacts,
        phase: str,
        idempotency_key: UUID,
    ) -> None:
        """Lock exact service authority before ART locks its requested resource."""
        if (
            service_identity is not self._service_identity
            or self._prepared is not None
            or phase not in {"claim", "terminal", "scan"}
        ):
            raise ArtifactAuthorityDeniedError("artifact internal authority is invalid")
        scope = _scope(facts.resource_type, facts.resource_id)
        context = await self._service_context()
        repository = AdminAuthorizationRepository(self._session)

        async def revalidate_service(
            original: ServiceAuthorizationContext,
            _requested_action: ActionId,
        ) -> ServiceAuthorizationContext | None:
            locked = await repository.lock_request_actor(
                original.identity_link_id, original.actor_profile_id
            )
            if locked is None:
                return None
            link, profile = locked
            if (
                profile.actor_kind != ActorKind.SERVICE.value
                or profile.service_identity != original.service_identity.value
            ):
                return None
            return ServiceAuthorizationContext(
                actor_profile_id=UUID(profile.id),
                actor_kind=ActorKind.SERVICE,
                actor_status=ActorStatus(profile.status),
                identity_link_id=UUID(link.id),
                identity_link_status=IdentityLinkStatus(link.status),
                service_identity=original.service_identity,
                request_id=original.request_id,
                correlation_id=original.correlation_id,
            )

        authorization = AuthorizationService(
            self._session,
            context,
            revalidate_service=revalidate_service,
            admin_repository=repository,
        )
        prepared = PreparedAuthorizationService(
            self._session, context, authorization, repository
        )
        caller_input = PreparedAuthorizationInput(
            idempotency_key=idempotency_key,
            request_value=_prepared_request_value(facts, phase),
        )
        try:
            handle = await prepared.prepare(action_id, caller_input, scope)
        except PreparedAuthorizationUnsupported:
            prepared.close()
            try:
                await authorization.require(action_id, _resource_context(facts))
            except AuthorizationDenied as denial:
                self._denial = denial.decision
                self._denial_authorization = authorization
                raise
            raise ArtifactAuthorityDeniedError("artifact internal authority is invalid")
        except BaseException:
            prepared.close()
            raise
        self._prepared = prepared
        self._handle = handle
        self._input = caller_input
        self._facts = facts
        self._action_id = action_id
        self._authorization = authorization

    async def consume(
        self,
        *,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        facts: ArtifactInternalAuthorityFacts,
    ) -> None:
        """Consume against ART's final locked facts and stage decision evidence."""
        if (
            service_identity is not self._service_identity
            or self._prepared is None
            or self._handle is None
            or self._input is None
            or self._facts is None
            or action_id is not self._action_id
            or not _consume_facts_match(self._facts, facts)
        ):
            raise ArtifactAuthorityDeniedError("artifact internal authority is invalid")
        prepared = self._prepared
        try:
            await prepared.consume(
                self._handle,
                action_id,
                self._input,
                _resource_context(facts),
            )
        except AuthorizationDenied as denial:
            self._denial = denial.decision
            self._denial_authorization = self._authorization
            raise
        finally:
            prepared.close()
            self._prepared = None
            self._handle = None
            self._input = None
            self._facts = None
            self._action_id = None
            self._authorization = None

    def discard(self) -> None:
        """Invalidate one unconsumed preparation after a stale ART selector."""
        if self._prepared is not None:
            self._prepared.close()
        self._prepared = None
        self._handle = None
        self._input = None
        self._facts = None
        self._action_id = None
        self._authorization = None

    async def persist_denial(self) -> None:
        """Restage one rolled-back denial in a clean AUTH-only transaction."""
        if self._denial is None or self._denial_authorization is None:
            raise ArtifactAuthorityDeniedError("artifact denial evidence is unavailable")
        decision = self._denial
        authorization = self._denial_authorization
        self._denial = None
        self._denial_authorization = None
        await authorization.restage_denial(decision)
        await self._session.commit()

    async def _service_context(self) -> ServiceAuthorizationContext:
        actors = ActorRepository(self._session)
        profile = await actors.get_service_actor(self._service_identity.value)
        if profile is None:
            raise ArtifactAuthorityDeniedError("artifact service principal is unavailable")
        link = await actors.get_identity_link_for_actor(profile.id)
        if (
            link is None
            or link.actor_profile_id != profile.id
            or link.subject_kind != ActorKind.SERVICE.value
        ):
            raise ArtifactAuthorityDeniedError("artifact service principal is unavailable")
        try:
            return ServiceAuthorizationContext(
                actor_profile_id=UUID(profile.id),
                actor_kind=ActorKind.SERVICE,
                actor_status=ActorStatus(profile.status),
                identity_link_id=UUID(link.id),
                identity_link_status=IdentityLinkStatus(link.status),
                service_identity=ServiceIdentity(profile.service_identity),
                request_id=self._request_id,
                correlation_id=self._correlation_id,
            )
        except (TypeError, ValueError) as exc:
            raise ArtifactAuthorityDeniedError(
                "artifact service principal is unavailable"
            ) from exc


def _scope(
    resource_type: ArtifactInternalResourceType,
    resource_id: UUID | str,
) -> PreparedAuthorityScope:
    normalized_id: UUID | str
    if resource_type is ArtifactInternalResourceType.PENDING_WORK:
        normalized_id = resource_id
    else:
        normalized_id = resource_id if isinstance(resource_id, UUID) else UUID(resource_id)
    return PreparedAuthorityScope(
        kind=PreparedAuthorityScopeKind.ARTIFACT_INTERNAL,
        artifact_resource_type=resource_type.value,
        artifact_resource_id=normalized_id,
    )


def _resource_context(facts: ArtifactInternalAuthorityFacts):
    if isinstance(facts, ArtifactPutAttemptAuthorityFacts):
        return ArtifactPutAttemptResourceContext(
            resource_type=facts.resource_type.value,
            resource_id=facts.resource_id,
            operation_identity=facts.operation_identity,
            namespace_fingerprint=facts.namespace_fingerprint,
            sha256=facts.sha256,
            byte_count=facts.byte_count,
            executor_id=facts.executor_id,
            execution_generation=facts.execution_generation,
        )
    if isinstance(facts, ArtifactVerificationAuthorityFacts):
        return ArtifactVerificationJobResourceContext(
            resource_type=facts.resource_type.value,
            resource_id=facts.resource_id,
            replica_id=facts.replica_id,
            namespace_fingerprint=facts.namespace_fingerprint,
            provider_object_ref=facts.provider_object_ref,
            sha256=facts.sha256,
            byte_count=facts.byte_count,
            executor_id=facts.executor_id,
            execution_generation=facts.execution_generation,
        )
    if isinstance(facts, ArtifactPendingWorkAuthorityFacts):
        return ArtifactPendingWorkResourceContext(
            resource_type=facts.resource_type.value,
            resource_id=facts.resource_id,
            scanner_kind=facts.scanner_kind,
            database_cutoff_iso=facts.database_cutoff_iso,
            page_size=facts.page_size,
            put_attempt_ids=facts.put_attempt_ids,
            verification_job_ids=facts.verification_job_ids,
        )
    raise TypeError("unsupported artifact internal authority facts")


def _prepared_request_value(
    facts: ArtifactInternalAuthorityFacts,
    phase: str,
) -> dict[str, object]:
    """Bind every fact known before ART locks the final resource graph."""
    context = _resource_context(facts)
    value: dict[str, object] = {
        "phase": phase,
        "resource_type": context.resource_type,
        "resource_id": str(context.resource_id),
    }
    if isinstance(facts, ArtifactPutAttemptAuthorityFacts):
        value.update(
            operation_identity=facts.operation_identity,
            namespace_fingerprint=facts.namespace_fingerprint,
            sha256=facts.sha256,
            byte_count=facts.byte_count,
            executor_id=str(facts.executor_id),
            execution_generation=facts.execution_generation,
        )
    elif isinstance(facts, ArtifactVerificationAuthorityFacts):
        value.update(
            replica_id=str(facts.replica_id),
            namespace_fingerprint=facts.namespace_fingerprint,
            provider_object_ref=facts.provider_object_ref,
            sha256=facts.sha256,
            byte_count=facts.byte_count,
            executor_id=str(facts.executor_id),
            execution_generation=facts.execution_generation,
        )
    elif isinstance(facts, ArtifactPendingWorkAuthorityFacts):
        value.update(
            scanner_kind=facts.scanner_kind,
            database_cutoff_iso=facts.database_cutoff_iso,
            page_size=facts.page_size,
        )
    return value


def _consume_facts_match(
    prepared: ArtifactInternalAuthorityFacts,
    final: ArtifactInternalAuthorityFacts,
) -> bool:
    """Reject same-resource substitution while allowing a scanner's locked page."""
    if type(prepared) is not type(final):
        return False
    if not isinstance(prepared, ArtifactPendingWorkAuthorityFacts):
        return prepared == final
    assert isinstance(final, ArtifactPendingWorkAuthorityFacts)
    returned_ids = final.put_attempt_ids + final.verification_job_ids
    return (
        prepared.put_attempt_ids == ()
        and prepared.verification_job_ids == ()
        and prepared.resource_type is final.resource_type
        and prepared.resource_id == final.resource_id
        and prepared.scanner_kind == final.scanner_kind
        and prepared.database_cutoff_iso == final.database_cutoff_iso
        and prepared.page_size == final.page_size
        and len(returned_ids) <= prepared.page_size
        and len(set(returned_ids)) == len(returned_ids)
    )
