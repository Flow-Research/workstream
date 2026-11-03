"""Purpose-specific fixed-service authority for hidden setup finalization."""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.api import (
    AuthorizationDenied,
    AuthorizationUnavailable,
    FINALIZATION_ACTION,
    FINALIZATION_PERMISSION,
    FINALIZATION_SERVICE,
    PreparedAuthorizationInvalid,
    PreparedSetupFinalization,
    ProjectSetupFinalizationAuthorityReceipt,
    ProjectSetupFinalizationFacts,
    ProjectSetupFinalizationLocator,
    setup_finalization_preparation_identity,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.project_setup_finalization import (
    finalization_context_matches,
    finalization_prepare_context,
    finalization_resource_context,
    finalization_resource_digest,
)
from app.modules.authorization.prepared import (
    FixedServicePreparedAuthorization,
    PreparedAuthorizationHandle,
    fixed_service_prepared_authorization,
)
from app.modules.authorization.runtime import (
    AuthorizationEvidenceUnavailable,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)


@contextmanager
def _authority_errors():
    """Translate only AUTH operations; caller body failures retain their original meaning."""
    try:
        yield
    except PreparedAuthorizationHandleInvalid as exc:
        raise PreparedAuthorizationInvalid("prepared finalization authority is invalid") from exc
    except PreparedAuthorizationUnsupported as exc:
        raise AuthorizationDenied("finalization authority denied") from exc
    except AuthorizationEvidenceUnavailable as exc:
        raise AuthorizationUnavailable("finalization authority unavailable") from exc


class _PreparedFinalization(PreparedSetupFinalization):
    """Nominal process-local view of one exact shared PREP handle."""

    __slots__ = ("_custody", "_handle", "_input")

    def __init__(
        self,
        custody: FixedServicePreparedAuthorization,
        handle: PreparedAuthorizationHandle,
        caller_input: PreparedAuthorizationInput,
    ) -> None:
        """Retain only shared custody and its immutable request binding."""
        self._custody = custody
        self._handle = handle
        self._input = caller_input

    def _resource(self, facts: ProjectSetupFinalizationFacts):
        """Validate complete facts and the prepared locator before shared consumption."""
        try:
            resource = finalization_resource_context(
                facts, self._custody.actor_profile_id, self._custody.identity_link_id
            )
            if not finalization_context_matches(self._input.request_value, resource):
                raise ValueError("finalization locator differs from preparation")
            return resource
        except (TypeError, ValueError) as exc:
            raise PreparedAuthorizationInvalid(
                "prepared finalization authority is invalid"
            ) from exc

    async def consume_new(
        self, facts: ProjectSetupFinalizationFacts
    ) -> ProjectSetupFinalizationAuthorityReceipt:
        """Consume once and return every field required by POL receipt custody."""
        if facts.result_schema_version != "project_guide_check_specification.v1":
            raise ValueError("new finalization requires the current proposal format")
        resource = self._resource(facts)
        with _authority_errors():
            decision = await self._custody.service.consume(
                self._handle, ActionId.PROJECT_SETUP_RUN_UPDATE, self._input, resource
            )
        return ProjectSetupFinalizationAuthorityReceipt(
            decision_event_id=decision.decision_id,
            actor_profile_id=self._custody.actor_profile_id,
            identity_link_id=self._custody.identity_link_id,
            service_identity=FINALIZATION_SERVICE,
            action_id=FINALIZATION_ACTION,
            permission_id=FINALIZATION_PERMISSION,
            scope_project_id=resource.scope_project_id,
            resource_type=resource.resource_type,
            resource_id=resource.resource_id,
            resource_context_digest=finalization_resource_digest(resource),
        )

    async def validate_replay(
        self, facts: ProjectSetupFinalizationFacts, stored_decision_id: UUID
    ) -> None:
        """Validate original evidence with freshly prepared current authority, once."""
        resource = self._resource(facts)
        with _authority_errors():
            await self._custody.service.validate_replay(
                self._handle,
                ActionId.PROJECT_SETUP_RUN_UPDATE,
                self._input,
                resource,
                stored_decision_id,
            )


class SetupFinalizationAuthorization:
    """Explicit same-session factory target, unavailable through live POL defaults."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind authority to the caller-owned session without opening a transaction."""
        self._session = session

    @asynccontextmanager
    async def prepare_setup_finalization(self, locator: ProjectSetupFinalizationLocator):
        """Resolve, lock, prepare and close canonical service authority exactly once."""
        request_id, correlation_id = setup_finalization_preparation_identity(
            locator.setup_run_id, locator.setup_generation, locator.compilation_id
        )
        manager = fixed_service_prepared_authorization(
            self._session,
            service_identity=ServiceIdentity.PROJECT_SETUP,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        with _authority_errors():
            custody = await manager.__aenter__()
        try:
            with _authority_errors():
                context = finalization_prepare_context(
                    locator, custody.actor_profile_id, custody.identity_link_id
                )
                caller_input = PreparedAuthorizationInput(
                    idempotency_key=request_id,
                    request_value=context.model_dump(mode="json"),
                )
                handle = await custody.service.prepare(
                    ActionId.PROJECT_SETUP_RUN_UPDATE,
                    caller_input,
                    PreparedAuthorityScope(
                        kind=PreparedAuthorityScopeKind.PROJECT, project_id=locator.project_id
                    ),
                )
            yield _PreparedFinalization(custody, handle, caller_input)
        finally:
            with _authority_errors():
                await manager.__aexit__(None, None, None)
