"""AUTH-owned external-checker registry registration adapter."""

from __future__ import annotations

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.checker_registry import (
    ExternalCheckerRegistryResourceContext,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.runtime import (
    AuthorizationDenied,
    AuthorizationEvidenceUnavailable,
    HumanAuthorizationContext,
)
from app.modules.checkers.api import (
    ExternalCheckerRegistrationAuthorityFacts,
    ExternalCheckerRegistrationAuthorityReceipt,
    ExternalCheckerRegistryUnavailable,
)


class ExternalCheckerRegistryAuthorizationAdapter:
    """Bind CHECKERS registration facts to fresh system Operator authority."""

    def __init__(self, authorization: AuthorizationService) -> None:
        self._authorization = authorization

    async def authorize_registration(
        self, facts: ExternalCheckerRegistrationAuthorityFacts
    ) -> ExternalCheckerRegistrationAuthorityReceipt:
        """Authorize one exact immutable entry and return its durable decision ID."""
        facts = ExternalCheckerRegistrationAuthorityFacts.model_validate(facts)
        context = self._authorization._context
        if (
            not isinstance(context, HumanAuthorizationContext)
            or context.actor_profile_id != facts.actor_profile_id
            or context.correlation_id != facts.operation_id
        ):
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            )
        resource = ExternalCheckerRegistryResourceContext(
            resource_type="external_checker_registry_entry",
            resource_id=facts.registry_entry_id,
            operation_id=facts.operation_id,
            request_digest=facts.request_digest,
            entry_digest=facts.entry_digest,
        )
        try:
            decision = await self._authorization.require(
                ActionId.CHECKER_REGISTRY_REGISTER, resource
            )
        except (AuthorizationDenied, AuthorizationEvidenceUnavailable) as exc:
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            ) from exc
        return ExternalCheckerRegistrationAuthorityReceipt(
            actor_profile_id=context.actor_profile_id,
            authorization_decision_event_id=decision.decision_id,
        )
