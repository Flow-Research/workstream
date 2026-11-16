"""Request-principal AUTH preparation for COMP's original-bound factual evidence."""

from contextlib import asynccontextmanager

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.fulfillment_evidence import (
    fulfillment_evidence_principal_matches, fulfillment_evidence_resource,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    AuthorizationDenied, AuthorizationEvidenceUnavailable,
    PreparedAuthorizationHandleInvalid, PreparedAuthorizationUnsupported,
    PreparedAuthorizationInput, PreparedAuthorityScope, PreparedAuthorityScopeKind,
    ServiceAuthorizationContext,
)
from app.modules.compensation.api.fulfillment_evidence import (
    FulfillmentEvidenceAuthority, FulfillmentEvidenceDenied,
    FulfillmentEvidenceUnavailable,
    FulfillmentReportAuthorityFacts, FulfillmentExceptionAuthorityFacts,
)


class _PreparedEvidence:
    def __init__(self, service, handle, action, caller_input, resource):
        self._service, self._handle, self._action = service, handle, action
        self._input, self._resource = caller_input, resource

    async def consume_new(self):
        decision = await self._service.consume(
            self._handle, self._action, self._input, self._resource,
        )
        return FulfillmentEvidenceAuthority(
            authorization_decision_id=decision.decision_id,
            resource_context_digest=decision.resource_context_digest,
        )

    async def validate_replay(self, authorization_decision_id):
        await self._service.validate_replay(
            self._handle, self._action, self._input, self._resource, authorization_decision_id,
        )


class FulfillmentEvidenceAuthorizationAdapter:
    """Keep the verified request actor/link; never resolve a global service identity."""

    def __init__(self, session, context):
        self._session, self._context = session, context
        self._repository = AdminAuthorizationRepository(session)
        self._kernel = AuthorizationService(session, context, admin_repository=self._repository)

    async def restage_denial(self, error: FulfillmentEvidenceDenied) -> bool:
        """Restage only this kernel's exact pending decision after caller rollback."""
        if isinstance(error.__cause__, AuthorizationDenied):
            try:
                await self._kernel.restage_denial(error.__cause__.decision)
            except AuthorizationEvidenceUnavailable as exc:
                raise FulfillmentEvidenceUnavailable("fulfillment evidence authority unavailable") from exc
            return True
        return False

    @asynccontextmanager
    async def prepare(self, facts):
        context = self._context
        resource = fulfillment_evidence_resource(facts)
        if (
            type(context) is not ServiceAuthorizationContext
            or context.service_identity is not ServiceIdentity.COMPENSATION_ADAPTER
            or not fulfillment_evidence_principal_matches(
                resource, context.actor_profile_id, context.identity_link_id,
            )
        ):
            raise FulfillmentEvidenceDenied("fulfillment evidence authority denied")
        if type(facts) is FulfillmentReportAuthorityFacts:
            action, operation_id = ActionId.COMPENSATION_FULFILLMENT_REPORT, facts.external_event_id
        elif type(facts) is FulfillmentExceptionAuthorityFacts:
            action, operation_id = ActionId.COMPENSATION_FULFILLMENT_EXCEPTION_REPORT, facts.exception_event_id
        else:
            action, operation_id = ActionId.COMPENSATION_FULFILLMENT_SOURCE_READ, context.request_id
        service = PreparedAuthorizationService(self._session, context, self._kernel, self._repository)
        caller_input = PreparedAuthorizationInput(
            idempotency_key=operation_id, request_value=resource.model_dump(mode="json"),
        )
        try:
            try:
                handle = await service.prepare(
                    action, caller_input, PreparedAuthorityScope(
                        kind=PreparedAuthorityScopeKind.PROJECT, project_id=facts.project_id,
                    ),
                )
            except PreparedAuthorizationUnsupported as exc:
                await service.deny_unsupported(action, caller_input, resource, exc)
                raise FulfillmentEvidenceUnavailable("fulfillment evidence authority unavailable") from exc
            yield _PreparedEvidence(service, handle, action, caller_input, resource)
        except AuthorizationDenied as exc:
            raise FulfillmentEvidenceDenied("fulfillment evidence authority denied") from exc
        except (PreparedAuthorizationHandleInvalid, AuthorizationEvidenceUnavailable) as exc:
            raise FulfillmentEvidenceUnavailable("fulfillment evidence authority unavailable") from exc
        finally:
            service.close()
