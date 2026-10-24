"""Prepared AUTH adapters for private checker-model output custody."""

from __future__ import annotations

from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.api.checker_output_authority import (
    CheckerOutputBindingAuthority,
    CheckerOutputCommitmentAuthorityFacts,
    CheckerOutputStoredFacts,
    CheckerOutputWriteAuthority,
)
from app.modules.authorization.catalogue import (
    ACTION_BY_ID,
    SERVICE_ACTIONS_BY_IDENTITY,
    ActionAvailability,
    ActionId,
)
from app.modules.authorization.domain.checker_outputs import (
    BIND,
    WRITE,
    checker_output_admission_resource,
    checker_output_prepare_resource,
    checker_output_stored_resource,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import (
    PreparedAuthorizationHandle,
    PreparedAuthorizationService,
    fixed_service_authorization_context,
    fixed_service_context_revalidator,
)
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    AuthorizationDenied,
    AuthorizationEvidenceUnavailable,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)
from app.modules.checkers.api.output_custody import (
    GENERATED_OUTPUT_RESERVATION,
    GENERATED_OUTPUT_SELECTOR,
    GeneratedOutputReservation,
    GeneratedOutputSelector,
    CheckerOutputUnavailable,
)
from app.modules.checkers.api.trial_evidence import TrialEvidenceUnavailable
from app.modules.model_usage.api import ModelCallUnavailable


_AUTH_ERRORS = (
    AuthorizationDenied,
    AuthorizationEvidenceUnavailable,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationUnsupported,
)


class _PreparedCheckerOutputAuthorization:
    """Own one transaction-local capability from selector through ART facts."""

    __slots__ = (
        "_action",
        "_handle",
        "_input",
        "_prepared",
        "_selector",
        "_service_identity",
        "_session",
    )

    def __init__(
        self,
        session,
        *,
        action: ActionId,
        service_identity: ServiceIdentity,
    ) -> None:
        self._session = session
        self._action = action
        self._service_identity = service_identity
        self._prepared: PreparedAuthorizationService | None = None
        self._handle: PreparedAuthorizationHandle | None = None
        self._input: PreparedAuthorizationInput | None = None
        self._selector: GeneratedOutputSelector | None = None

    async def preflight(self, selector: GeneratedOutputSelector) -> None:
        """Reject malformed or unavailable action shape before protected reads."""
        try:
            GENERATED_OUTPUT_SELECTOR.validate_python(selector)
            action = ACTION_BY_ID[self._action]
            if (
                action.availability is not ActionAvailability.ACTIVE
                or self._action not in SERVICE_ACTIONS_BY_IDENTITY.get(self._service_identity, ())
            ):
                raise ValueError("checker output action unavailable")
        except (KeyError, TypeError, ValueError) as error:
            raise CheckerOutputUnavailable("checker_output_authority_unavailable") from error

    async def prepare(self, selector: GeneratedOutputSelector) -> None:
        """Lock one fixed-service grant before CHECKERS or ART feature rows."""
        self.discard()
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise CheckerOutputUnavailable("checker_output_authority_unavailable")
        prepared: PreparedAuthorizationService | None = None
        try:
            resource = checker_output_prepare_resource(self._action, selector)
            context = await fixed_service_authorization_context(
                self._session,
                self._service_identity,
                resource.resource_id,
                resource.resource_id,
            )
            repository = AdminAuthorizationRepository(self._session)
            authorization = AuthorizationService(
                self._session,
                context,
                revalidate_service=fixed_service_context_revalidator(
                    repository, self._service_identity
                ),
                admin_repository=repository,
            )
            prepared = PreparedAuthorizationService(
                self._session, context, authorization, repository
            )
            caller_input = PreparedAuthorizationInput(
                idempotency_key=resource.resource_id,
                request_value=resource.model_dump(mode="json"),
            )
            handle = await prepared.prepare(
                self._action,
                caller_input,
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT,
                    project_id=resource.scope_project_id,
                ),
            )
        except _AUTH_ERRORS as error:
            if prepared is not None:
                prepared.close()
            raise CheckerOutputUnavailable("checker_output_authority_unavailable") from error
        except (TypeError, ValueError) as error:
            if prepared is not None:
                prepared.close()
            raise CheckerOutputUnavailable("checker_output_authority_unavailable") from error
        self._prepared = prepared
        self._handle = handle
        self._input = caller_input
        self._selector = resource.selector

    async def _consume(self, resource) -> None:
        prepared, handle, caller_input = self._prepared, self._handle, self._input
        if (
            prepared is None
            or handle is None
            or caller_input is None
            or self._selector is None
            or resource.selector != self._selector
        ):
            raise CheckerOutputUnavailable("checker_output_authority_unavailable")
        try:
            await prepared.consume(handle, self._action, caller_input, resource)
        except _AUTH_ERRORS as error:
            raise CheckerOutputUnavailable("checker_output_authority_unavailable") from error
        finally:
            self.discard()

    def discard(self) -> None:
        """Invalidate every unconsumed transaction-local capability."""
        if self._prepared is not None:
            self._prepared.close()
        self._prepared = None
        self._handle = None
        self._input = None
        self._selector = None


class PreparedCheckerOutputWriteAuthorization(
    _PreparedCheckerOutputAuthorization, CheckerOutputWriteAuthority
):
    """Authorize exact private request/response evidence storage and recovery."""

    def __init__(self, session) -> None:
        super().__init__(
            session,
            action=WRITE,
            service_identity=ServiceIdentity.ARTIFACT_CHECKER_OUTPUT,
        )

    async def consume(self, facts: CheckerOutputCommitmentAuthorityFacts) -> None:
        """Consume server-computed commitment facts without receiving raw bytes."""
        if type(facts) is not CheckerOutputCommitmentAuthorityFacts:
            raise CheckerOutputUnavailable("checker_output_authority_unavailable")
        selector = self._require_selector()
        try:
            reservation = GENERATED_OUTPUT_RESERVATION.validate_python(facts.reservation)
            slot = reservation.select(selector)
        except (
            CheckerOutputUnavailable,
            ModelCallUnavailable,
            TrialEvidenceUnavailable,
            TypeError,
            ValueError,
        ) as error:
            self.discard()
            raise CheckerOutputUnavailable("checker_output_authority_unavailable") from error
        if facts.slot_key != slot.key:
            self.discard()
            raise CheckerOutputUnavailable("checker_output_authority_unavailable")
        try:
            resource = checker_output_admission_resource(selector, facts)
        except (TypeError, ValueError) as error:
            self.discard()
            raise CheckerOutputUnavailable("checker_output_authority_unavailable") from error
        await self._consume(resource)

    async def consume_existing(
        self,
        reservation: GeneratedOutputReservation,
        facts: CheckerOutputStoredFacts,
    ) -> None:
        """Consume exact stored ancestry selected under the prepared selector."""
        selector = self._require_selector()
        try:
            resource = checker_output_stored_resource(WRITE, selector, reservation, facts)
        except (TypeError, ValueError) as error:
            self.discard()
            raise CheckerOutputUnavailable("checker_output_authority_unavailable") from error
        await self._consume(resource)

    def _require_selector(self) -> GeneratedOutputSelector:
        if self._selector is None:
            raise CheckerOutputUnavailable("checker_output_authority_unavailable")
        return self._selector


class PreparedCheckerOutputBindingAuthorization(
    _PreparedCheckerOutputAuthorization, CheckerOutputBindingAuthority
):
    """Authorize one binding from verified call-stable evidence."""

    def __init__(self, session) -> None:
        super().__init__(
            session,
            action=BIND,
            service_identity=ServiceIdentity.ARTIFACT_BINDING,
        )

    async def consume(
        self,
        reservation: GeneratedOutputReservation,
        facts: CheckerOutputStoredFacts,
    ) -> None:
        """Consume only complete verified ancestry for the prepared selector."""
        if self._selector is None:
            raise CheckerOutputUnavailable("checker_output_authority_unavailable")
        try:
            resource = checker_output_stored_resource(BIND, self._selector, reservation, facts)
        except (TypeError, ValueError) as error:
            self.discard()
            raise CheckerOutputUnavailable("checker_output_authority_unavailable") from error
        await self._consume(resource)


__all__ = (
    "PreparedCheckerOutputBindingAuthorization",
    "PreparedCheckerOutputWriteAuthorization",
)
