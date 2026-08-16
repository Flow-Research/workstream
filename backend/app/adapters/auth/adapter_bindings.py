"""Application adapter from CON's public binding port to AUTH's public port."""

from __future__ import annotations

from uuid import UUID

from app.modules.authorization.api import (
    AdapterBindingAuthorizationPort,
    AdapterBindingMutationAuthorityFacts,
    AdapterBindingReadFacts,
    AuthorizationBoundaryError,
    action_id,
)
from app.modules.compensation.api import (
    AdapterBindingMutationAuthorizationFacts,
    AdapterBindingReadRequest,
    AdapterBindingUnavailable,
)


class CompensationAdapterBindingAuthorization:
    """Translate immutable CON facts without importing either private domain."""

    def __init__(self, authorization: AdapterBindingAuthorizationPort) -> None:
        """Bind the CON-facing adapter to AUTH's public authorization port."""
        self._authorization = authorization

    async def authorize_adapter_binding_read(self, request: AdapterBindingReadRequest) -> None:
        """Authorize one exact adapter-binding read or return a concealed denial."""
        try:
            await self._authorization.authorize_read(
                actor_profile_id=request.actor_profile_id,
                facts=AdapterBindingReadFacts(
                    project_id=request.project_id,
                    adapter_binding_id=request.adapter_binding_id,
                ),
            )
        except (AuthorizationBoundaryError, ValueError) as exc:
            raise AdapterBindingUnavailable("compensation_adapter_binding_unavailable") from exc

    @staticmethod
    def _facts(
        facts: AdapterBindingMutationAuthorizationFacts,
    ) -> AdapterBindingMutationAuthorityFacts:
        """Copy immutable CON facts into AUTH's public mutation contract."""
        return AdapterBindingMutationAuthorityFacts(
            action_id=action_id(facts.action),
            actor_profile_id=facts.actor_profile_id,
            operation_id=facts.operation_id,
            request_digest=facts.request_digest,
            project_id=facts.project_id,
            adapter_binding_id=facts.adapter_binding_id,
            instrument_type=facts.instrument_type,
            adapter_actor_id=facts.adapter_actor_id,
            route_key=facts.route_key,
            expected_status=facts.expected_status,
            expected_lifecycle_version=facts.expected_lifecycle_version,
        )

    async def prepare_adapter_binding_mutation(
        self, facts: AdapterBindingMutationAuthorizationFacts
    ) -> object:
        """Prepare opaque authority for one exact adapter-binding mutation."""
        try:
            return await self._authorization.prepare_mutation(self._facts(facts))
        except (AuthorizationBoundaryError, ValueError) as exc:
            raise AdapterBindingUnavailable("compensation_adapter_binding_unavailable") from exc

    async def consume_adapter_binding_mutation(
        self, prepared: object, facts: AdapterBindingMutationAuthorizationFacts
    ) -> UUID:
        """Consume prepared mutation authority and return its authorized actor."""
        try:
            return await self._authorization.consume_mutation(prepared, self._facts(facts))
        except (AuthorizationBoundaryError, ValueError) as exc:
            raise AdapterBindingUnavailable("compensation_adapter_binding_unavailable") from exc

    def close_adapter_binding_mutation(self, prepared: object) -> None:
        """Invalidate prepared mutation authority through AUTH's public port."""
        try:
            self._authorization.close_mutation(prepared)
        except AuthorizationBoundaryError as exc:
            raise AdapterBindingUnavailable("compensation_adapter_binding_unavailable") from exc
