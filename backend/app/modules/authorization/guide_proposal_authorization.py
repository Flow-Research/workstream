"""Project-manager proposal authority over the canonical request-local kernel/PREP."""

from contextlib import asynccontextmanager, contextmanager

from app.modules.authorization.api import (
    AuthorizationDenied as BoundaryDenied,
    AuthorizationUnavailable,
    PreparedAuthorizationInvalid,
)
from app.modules.authorization.api.guide_proposal_review import (
    GuideProposalAuthorityReceipt,
    PreparedGuideProposalOperation,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.guide_proposals import proposal_resource, proposal_selectors
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    AuthorizationDenied,
    AuthorizationEvidenceUnavailable,
    HumanAuthorizationContext,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)


@contextmanager
def _authority_errors():
    """Translate AUTH failures without swallowing product-owner exceptions."""
    try:
        yield
    except PreparedAuthorizationHandleInvalid as exc:
        raise PreparedAuthorizationInvalid("invalid proposal authority") from exc
    except (PreparedAuthorizationUnsupported, AuthorizationDenied) as exc:
        raise BoundaryDenied("proposal authority denied") from exc
    except AuthorizationEvidenceUnavailable as exc:
        raise AuthorizationUnavailable("proposal authority unavailable") from exc


class _PreparedProposal(PreparedGuideProposalOperation):
    """Nominal view; shared PREP alone owns one-use/session/transaction custody."""

    def __init__(self, service, handle, caller_input, locator):
        self._service, self._handle = service, handle
        self._input, self._locator = caller_input, locator

    def _resource(self, facts):
        try:
            resource = proposal_resource(facts)
            if facts.locator != self._locator:
                raise ValueError("locator changed")
            return resource
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreparedAuthorizationInvalid("invalid proposal facts") from exc

    async def authorize_read(self, facts):
        if self._locator.action_id != "project.guide_compilation.review_package.read":
            raise PreparedAuthorizationInvalid("proposal read action required")
        resource = self._resource(facts)
        with _authority_errors():
            await self._service.consume(
                self._handle, ActionId(self._locator.action_id), self._input, resource
            )

    async def consume_new(self, facts):
        if self._locator.action_id == "project.guide_compilation.review_package.read":
            raise PreparedAuthorizationInvalid("proposal mutation action required")
        resource = self._resource(facts)
        with _authority_errors():
            decision = await self._service.consume(
                self._handle,
                ActionId(self._locator.action_id),
                self._input,
                resource,
            )
        return GuideProposalAuthorityReceipt(
            actor_profile_id=self._locator.actor_profile_id,
            identity_link_id=self._locator.identity_link_id,
            admin_role_grant_id=decision.matched_grant_id,
            authorization_decision_event_id=decision.decision_id,
            action_id=self._locator.action_id,
            permission_id=decision.permission_id.value,
            scope_project_id=resource.scope_project_id,
            resource_context_digest=decision.resource_context_digest,
        )

    async def validate_replay(self, facts, decision_event_id):
        if self._locator.action_id == "project.guide_compilation.review_package.read":
            raise PreparedAuthorizationInvalid("proposal mutation replay required")
        resource = self._resource(facts)
        with _authority_errors():
            await self._service.validate_replay(
                self._handle,
                ActionId(self._locator.action_id),
                self._input,
                resource,
                decision_event_id,
            )


class GuideProposalAuthorizationAdapter:
    """Compose shared AUTH from authenticated context; never resolve identity from selectors."""

    def __init__(self, session, context):
        self._session, self._context = session, context

    @asynccontextmanager
    async def prepare_proposal_operation(self, locator):
        try:
            selectors = proposal_selectors(locator)
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreparedAuthorizationInvalid("invalid proposal locator") from exc
        context = self._context
        if (
            type(context) is not HumanAuthorizationContext
            or context.actor_profile_id != locator.actor_profile_id
            or context.identity_link_id != locator.identity_link_id
            or context.request_id != locator.request_id
        ):
            raise BoundaryDenied("proposal identity denied")
        # POL supplies its stable business operation; transport request remains unchanged.
        context = context.model_copy(update={"correlation_id": locator.operation_id})
        repository = AdminAuthorizationRepository(self._session)
        kernel = AuthorizationService(self._session, context, admin_repository=repository)
        service = PreparedAuthorizationService(self._session, context, kernel, repository)
        try:
            caller_input = PreparedAuthorizationInput(
                idempotency_key=locator.operation_id, request_value=selectors
            )
            with _authority_errors():
                handle = await service.prepare(
                    ActionId(locator.action_id),
                    caller_input,
                    PreparedAuthorityScope(
                        kind=PreparedAuthorityScopeKind.PROJECT, project_id=locator.project_id
                    ),
                )
            yield _PreparedProposal(service, handle, caller_input, locator)
        finally:
            service.close()
