"""ART-owned composition for fixed-service prepared authorization."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import asdict
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.authorization import _authorization_context, get_authorization_actor
from app.core.api_controls import request_ids
from app.core.hashing import canonical_json_hash
from app.db.session import get_db_session
from app.modules.actors.service import ResolvedActor
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    GuideArtifactIngestAuthorityFacts,
    GuideSourceBindingAuthorityFacts,
    GuideSourceReadAuthorityFacts,
    ArtifactInternalAuthorityFacts,
    ArtifactInternalResourceType,
    ArtifactPendingWorkAuthorityFacts,
    ArtifactPutAttemptAuthorityFacts,
    ArtifactVerificationAuthorityFacts,
)
from app.modules.artifacts.submission_materialization import (
    PreSubmitMaterializationAuthorityFacts,
    PreSubmitMaterializationPreparationFacts,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import (
    PreparedAuthorizationHandle,
    PreparedAuthorizationService,
    fixed_service_authorization_context,
    fixed_service_context_revalidator,
)
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ArtifactPendingWorkResourceContext,
    ArtifactPutAttemptResourceContext,
    ArtifactVerificationJobResourceContext,
    PreparedAuthorizationInput,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    AuthorizationDecision,
    AuthorizationDenied,
    GuideSourceIngestResourceContext,
    GuideSourceBindingResourceContext,
    GuideSourceReadResourceContext,
    PreSubmitCheckerInputResourceContext,
    PreSubmitCheckerInputPreparationContext,
    HumanAuthorizationContext,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationUnsupported,
    ServiceAuthorizationContext,
    AuthorizationContext,
)


async def get_artifact_authorization_context(
    request: Request,
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
) -> AuthorizationContext:
    """Project canonical actor rows into request-scoped ART preflight facts."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    return _authorization_context(resolved, request_id, correlation_id)


def guide_ingest_prepared_request_value(
    *,
    project_id: UUID,
    guide_id: UUID,
    guide_source_snapshot_id: UUID,
    guide_source_item_id: UUID,
    idempotency_key: UUID,
) -> dict[str, str]:
    """Compose the one canonical caller input shared with AUTH activation."""
    return {
        "project_id": str(project_id),
        "guide_id": str(guide_id),
        "guide_source_snapshot_id": str(guide_source_snapshot_id),
        "guide_source_item_id": str(guide_source_item_id),
        "idempotency_key": str(idempotency_key),
    }


def guide_ingest_prepared_request_digest(
    *,
    project_id: UUID,
    guide_id: UUID,
    guide_source_snapshot_id: UUID,
    guide_source_item_id: UUID,
    idempotency_key: UUID,
) -> str:
    """Match PreparedAuthorizationService's canonical request binding."""
    return canonical_json_hash(
        {
            "domain": "workstream.prepared_authorization.request.v1",
            "request": guide_ingest_prepared_request_value(
                project_id=project_id,
                guide_id=guide_id,
                guide_source_snapshot_id=guide_source_snapshot_id,
                guide_source_item_id=guide_source_item_id,
                idempotency_key=idempotency_key,
            ),
        }
    )


class GuideArtifactPreparedAuthorization(Protocol):
    """Request-local adapter over AUTH's one opaque PREP capability."""

    def transaction(self) -> AbstractAsyncContextManager[None]: ...

    async def prepare(
        self,
        *,
        authorization_context: AuthorizationContext,
        project_id: UUID,
        guide_id: UUID,
        guide_source_snapshot_id: UUID,
        guide_source_item_id: UUID,
        idempotency_key: UUID,
    ) -> PreparedAuthorizationHandle: ...

    async def consume(
        self,
        *,
        prepared_authorization: PreparedAuthorizationHandle,
        facts: GuideArtifactIngestAuthorityFacts,
    ) -> UUID: ...

    def close(self) -> None: ...


class DenyGuideArtifactPreparedAuthorization:
    """Keep guide byte ingest unavailable until exact AUTH activation."""

    @asynccontextmanager
    async def transaction(self):
        """Provide no durable state while the action remains unavailable."""
        yield

    async def prepare(
        self,
        *,
        authorization_context: AuthorizationContext,
        project_id: UUID,
        guide_id: UUID,
        guide_source_snapshot_id: UUID,
        guide_source_item_id: UUID,
        idempotency_key: UUID,
    ) -> PreparedAuthorizationHandle:
        del (
            authorization_context,
            project_id,
            guide_id,
            guide_source_snapshot_id,
            guide_source_item_id,
            idempotency_key,
        )
        raise ArtifactAuthorityDeniedError("guide artifact ingest is unavailable")

    async def consume(
        self,
        *,
        prepared_authorization: PreparedAuthorizationHandle,
        facts: GuideArtifactIngestAuthorityFacts,
    ) -> UUID:
        del prepared_authorization, facts
        raise ArtifactAuthorityDeniedError("guide artifact ingest is unavailable")

    def close(self) -> None:
        """Deny-only adapters hold no capability state."""


class PreparedGuideArtifactAuthorization:
    """Activate exact Project Manager guide ingest through AUTH-owned PREP."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._prepared: PreparedAuthorizationService | None = None
        self._authorization: AuthorizationService | None = None
        self._input: PreparedAuthorizationInput | None = None
        self._handle: PreparedAuthorizationHandle | None = None
        self._expected: tuple[UUID, UUID, UUID, UUID, str] | None = None
        self._actor_profile_id: UUID | None = None

    @asynccontextmanager
    async def transaction(self):
        """Own the one root transaction shared by authorization and admission."""
        if self._session.in_nested_transaction():
            raise ArtifactAuthorityDeniedError(
                "guide prepared authorization transaction is unavailable"
            )
        if not self._session.in_transaction():
            async with self._session.begin():
                yield
            return
        try:
            yield
        except BaseException:
            await self._session.rollback()
            raise
        else:
            await self._session.commit()

    async def prepare(
        self,
        *,
        authorization_context: AuthorizationContext,
        project_id: UUID,
        guide_id: UUID,
        guide_source_snapshot_id: UUID,
        guide_source_item_id: UUID,
        idempotency_key: UUID,
    ) -> PreparedAuthorizationHandle:
        """Lock the exact Project Manager grant before any byte intake."""
        if (
            not isinstance(authorization_context, HumanAuthorizationContext)
            or self._prepared is not None
            or not self._session.in_transaction()
            or self._session.in_nested_transaction()
        ):
            raise ArtifactAuthorityDeniedError("guide artifact ingest is unavailable")
        repository = AdminAuthorizationRepository(self._session)
        authorization = AuthorizationService(
            self._session,
            authorization_context,
            admin_repository=repository,
        )
        prepared = PreparedAuthorizationService(
            self._session,
            authorization_context,
            authorization,
            repository,
        )
        request_value = guide_ingest_prepared_request_value(
            project_id=project_id,
            guide_id=guide_id,
            guide_source_snapshot_id=guide_source_snapshot_id,
            guide_source_item_id=guide_source_item_id,
            idempotency_key=idempotency_key,
        )
        caller_input = PreparedAuthorizationInput(
            idempotency_key=idempotency_key,
            request_value=request_value,
        )
        try:
            handle = await prepared.prepare(
                ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
                caller_input,
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT,
                    project_id=project_id,
                ),
            )
        except (PreparedAuthorizationUnsupported, PreparedAuthorizationHandleInvalid) as exc:
            prepared.close()
            raise ArtifactAuthorityDeniedError("guide artifact ingest is unavailable") from exc
        except BaseException:
            prepared.close()
            raise
        self._prepared = prepared
        self._authorization = authorization
        self._input = caller_input
        self._handle = handle
        self._actor_profile_id = authorization_context.actor_profile_id
        self._expected = (
            project_id,
            guide_id,
            guide_source_snapshot_id,
            guide_source_item_id,
            guide_ingest_prepared_request_digest(
                project_id=project_id,
                guide_id=guide_id,
                guide_source_snapshot_id=guide_source_snapshot_id,
                guide_source_item_id=guide_source_item_id,
                idempotency_key=idempotency_key,
            ),
        )
        return handle

    async def consume(
        self,
        *,
        prepared_authorization: PreparedAuthorizationHandle,
        facts: GuideArtifactIngestAuthorityFacts,
    ) -> UUID:
        """Consume once against locked lineage and server-computed byte facts."""
        if (
            self._prepared is None
            or self._authorization is None
            or self._input is None
            or self._handle is None
            or self._expected is None
            or self._actor_profile_id is None
            or prepared_authorization is not self._handle
            or self._expected
            != (
                facts.project_id,
                facts.guide_id,
                facts.guide_source_snapshot_id,
                facts.guide_source_item_id,
                facts.request_digest,
            )
        ):
            raise ArtifactAuthorityDeniedError("guide artifact ingest is unavailable")
        prepared = self._prepared
        actor_profile_id = self._actor_profile_id
        try:
            await prepared.consume(
                prepared_authorization,
                ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
                self._input,
                GuideSourceIngestResourceContext(
                    resource_type="project",
                    resource_id=facts.project_id,
                    scope_project_id=facts.project_id,
                    guide_id=facts.guide_id,
                    guide_source_snapshot_id=facts.guide_source_snapshot_id,
                    guide_source_item_id=facts.guide_source_item_id,
                    operation_identity=facts.operation_identity,
                    request_digest=facts.request_digest,
                    sha256=facts.sha256,
                    byte_count=facts.byte_count,
                    media_type=facts.media_type,
                ),
            )
        except (AuthorizationDenied, PreparedAuthorizationHandleInvalid, ValidationError) as exc:
            raise ArtifactAuthorityDeniedError("guide artifact ingest is unavailable") from exc
        finally:
            self.close()
        return actor_profile_id

    def close(self) -> None:
        """Invalidate every unconsumed request-local capability."""
        if self._prepared is not None:
            self._prepared.close()
        self._prepared = None
        self._authorization = None
        self._input = None
        self._handle = None
        self._expected = None
        self._actor_profile_id = None


def get_guide_artifact_prepared_authorization(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GuideArtifactPreparedAuthorization:
    """Compose the activated request-local guide ingest authority."""
    return PreparedGuideArtifactAuthorization(session)


class _PreparedArtifactServiceAuthorization:
    """Issue and consume one exact fixed-service artifact capability."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        service_identity: ServiceIdentity,
        action_id: ActionId,
        request_id: UUID,
        correlation_id: UUID,
    ) -> None:
        self._session = session
        self._service_identity = service_identity
        self._action_id = action_id
        self._request_id = request_id
        self._correlation_id = correlation_id
        self._prepared: PreparedAuthorizationService | None = None
        self._input: PreparedAuthorizationInput | None = None
        self._handle: PreparedAuthorizationHandle | None = None
        self._facts: (
            GuideSourceBindingAuthorityFacts
            | GuideSourceReadAuthorityFacts
            | PreSubmitMaterializationAuthorityFacts
            | PreSubmitMaterializationPreparationFacts
            | None
        ) = None

    async def prepare(
        self,
        *,
        facts: GuideSourceBindingAuthorityFacts
        | GuideSourceReadAuthorityFacts
        | PreSubmitMaterializationPreparationFacts,
        idempotency_key: UUID,
    ) -> PreparedAuthorizationHandle:
        """Prepare one process-local capability bound to every canonical fact."""
        if self._prepared is not None:
            raise ArtifactAuthorityDeniedError("artifact service authority is invalid")
        resource = _artifact_service_resource_context(facts)
        try:
            context = await fixed_service_authorization_context(
                self._session,
                self._service_identity,
                self._request_id,
                self._correlation_id,
            )
        except PreparedAuthorizationUnsupported as exc:
            raise ArtifactAuthorityDeniedError("artifact service principal is unavailable") from exc
        repository = AdminAuthorizationRepository(self._session)

        authorization = AuthorizationService(
            self._session,
            context,
            revalidate_service=fixed_service_context_revalidator(
                repository, self._service_identity
            ),
            admin_repository=repository,
        )
        prepared = PreparedAuthorizationService(self._session, context, authorization, repository)
        caller_input = PreparedAuthorizationInput(
            idempotency_key=idempotency_key,
            request_value=resource.model_dump(mode="json"),
        )
        scope = PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.ARTIFACT_INTERNAL,
            artifact_resource_type=resource.resource_type,
            artifact_resource_id=resource.resource_id,
        )
        try:
            handle = await prepared.prepare(self._action_id, caller_input, scope)
        except (
            AuthorizationDenied,
            PreparedAuthorizationHandleInvalid,
            PreparedAuthorizationUnsupported,
            ValidationError,
        ) as exc:
            prepared.close()
            raise ArtifactAuthorityDeniedError("artifact service authority is unavailable") from exc
        except BaseException:
            prepared.close()
            raise
        self._prepared = prepared
        self._input = caller_input
        self._handle = handle
        self._facts = facts
        return handle

    async def consume(
        self,
        *,
        prepared_authorization: PreparedAuthorizationHandle,
        facts: GuideSourceBindingAuthorityFacts
        | GuideSourceReadAuthorityFacts
        | PreSubmitMaterializationAuthorityFacts,
    ) -> None:
        """Consume only the exact handle and facts prepared by this adapter."""
        if (
            self._prepared is None
            or self._input is None
            or self._handle is not prepared_authorization
            or not _prepared_artifact_facts_match(self._facts, facts)
        ):
            raise ArtifactAuthorityDeniedError("artifact service authority is invalid")
        prepared = self._prepared
        try:
            await prepared.consume(
                prepared_authorization,
                self._action_id,
                self._input,
                _artifact_service_resource_context(facts),
            )
        except (AuthorizationDenied, PreparedAuthorizationHandleInvalid, ValidationError) as exc:
            raise ArtifactAuthorityDeniedError("artifact service authority is unavailable") from exc
        finally:
            prepared.close()
            self._prepared = None
            self._input = None
            self._handle = None
            self._facts = None

    def close(self) -> None:
        """Invalidate an unconsumed capability."""
        if self._prepared is not None:
            self._prepared.close()
        self._prepared = None
        self._input = None
        self._handle = None
        self._facts = None


class PreparedGuideSourceBindingAuthorization(_PreparedArtifactServiceAuthorization):
    """Prepared authority reserved to the fixed guide binding service."""

    def __init__(self, session: AsyncSession, *, request_id: UUID, correlation_id: UUID) -> None:
        super().__init__(
            session,
            service_identity=ServiceIdentity.ARTIFACT_BINDING,
            action_id=ActionId.ARTIFACT_GUIDE_SOURCE_BINDING_CREATE,
            request_id=request_id,
            correlation_id=correlation_id,
        )


class PreparedGuideSourceReadAuthorization(_PreparedArtifactServiceAuthorization):
    """Prepared authority reserved to the fixed guide reader service."""

    def __init__(self, session: AsyncSession, *, request_id: UUID, correlation_id: UUID) -> None:
        super().__init__(
            session,
            service_identity=ServiceIdentity.ARTIFACT_GUIDE_READER,
            action_id=ActionId.ARTIFACT_GUIDE_SOURCE_READ,
            request_id=request_id,
            correlation_id=correlation_id,
        )


class PreparedPreSubmitMaterializationAuthorization:
    """Issue one exact capability to the fixed pre-submit materializer."""

    def __init__(self, session: AsyncSession, *, request_id: UUID, correlation_id: UUID) -> None:
        """Bind the adapter to the materializer identity and action."""
        self._delegate = _PreparedArtifactServiceAuthorization(
            session,
            service_identity=ServiceIdentity.ARTIFACT_MATERIALIZER,
            action_id=ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE,
            request_id=request_id,
            correlation_id=correlation_id,
        )

    async def prepare(
        self,
        *,
        facts: PreSubmitMaterializationPreparationFacts,
        idempotency_key: UUID,
    ) -> PreparedAuthorizationHandle:
        """Prepare authority from the locked scalar facts before ZIP inspection."""
        return await self._delegate.prepare(facts=facts, idempotency_key=idempotency_key)

    async def consume(
        self,
        *,
        prepared_authorization: object,
        facts: PreSubmitMaterializationAuthorityFacts,
    ) -> None:
        """Consume authority only for the exact materializer and final facts."""
        await self._delegate.consume(
            prepared_authorization=prepared_authorization,
            facts=facts,
        )

    def close(self) -> None:
        """Discard any process-local prepared capability still held by the adapter."""
        self._delegate.close()


def _artifact_service_resource_context(
    facts: GuideSourceBindingAuthorityFacts
    | GuideSourceReadAuthorityFacts
    | PreSubmitMaterializationAuthorityFacts
    | PreSubmitMaterializationPreparationFacts,
) -> (
    GuideSourceBindingResourceContext
    | GuideSourceReadResourceContext
    | PreSubmitCheckerInputResourceContext
    | PreSubmitCheckerInputPreparationContext
):
    """Compose the canonical AUTH resource context for fixed ART service facts."""
    values = asdict(facts)
    if isinstance(facts, PreSubmitMaterializationAuthorityFacts):
        values = asdict(facts.preparation)
        return PreSubmitCheckerInputResourceContext(
            resource_type="pre_submit_checker_input",
            resource_id=facts.preparation.prepared_generation_id,
            semantic_manifest_sha256=facts.semantic_manifest_sha256,
            **values,
        )
    if isinstance(facts, PreSubmitMaterializationPreparationFacts):
        return PreSubmitCheckerInputPreparationContext(
            resource_type="pre_submit_checker_input",
            resource_id=facts.prepared_generation_id,
            **values,
        )
    if isinstance(facts, GuideSourceBindingAuthorityFacts):
        return GuideSourceBindingResourceContext(
            resource_type="guide_source_binding",
            resource_id=facts.guide_source_item_id,
            **values,
        )
    return GuideSourceReadResourceContext(
        resource_type="guide_source_read",
        resource_id=facts.binding_id,
        **values,
    )


def _prepared_artifact_facts_match(
    prepared: GuideSourceBindingAuthorityFacts
    | GuideSourceReadAuthorityFacts
    | PreSubmitMaterializationPreparationFacts
    | PreSubmitMaterializationAuthorityFacts,
    final: GuideSourceBindingAuthorityFacts
    | GuideSourceReadAuthorityFacts
    | PreSubmitMaterializationAuthorityFacts,
) -> bool:
    """Require final facts to preserve every fact bound during preparation."""
    if isinstance(prepared, PreSubmitMaterializationPreparationFacts):
        return (
            isinstance(final, PreSubmitMaterializationAuthorityFacts)
            and prepared == final.preparation
        )
    return prepared == final


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

        authorization = AuthorizationService(
            self._session,
            context,
            revalidate_service=fixed_service_context_revalidator(
                repository, self._service_identity
            ),
            admin_repository=repository,
        )
        prepared = PreparedAuthorizationService(self._session, context, authorization, repository)
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
        try:
            return await fixed_service_authorization_context(
                self._session,
                self._service_identity,
                self._request_id,
                self._correlation_id,
            )
        except PreparedAuthorizationUnsupported as exc:
            raise ArtifactAuthorityDeniedError("artifact service principal is unavailable") from exc


def _scope(
    resource_type: ArtifactInternalResourceType,
    resource_id: UUID | str,
) -> PreparedAuthorityScope:
    normalized_id: UUID | str
    if resource_type is ArtifactInternalResourceType.PENDING_WORK:
        normalized_id = resource_id
    else:
        try:
            normalized_id = resource_id if isinstance(resource_id, UUID) else UUID(resource_id)
        except (TypeError, ValueError) as exc:
            raise ArtifactAuthorityDeniedError("artifact internal resource is invalid") from exc
    try:
        return PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.ARTIFACT_INTERNAL,
            artifact_resource_type=resource_type.value,
            artifact_resource_id=normalized_id,
        )
    except ValidationError as exc:
        raise ArtifactAuthorityDeniedError("artifact internal resource is invalid") from exc


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
