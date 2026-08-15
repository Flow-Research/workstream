"""Strict CP02 test doubles shared by adapter-binding behavior tests."""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from app.modules.actors.api import (
    CompensationAdapterActorEligibilityFacts,
    CompensationAdapterActorUnavailable,
)
from app.modules.compensation.api import (
    AdapterBindingMutationAuthorizationFacts,
    AdapterBindingReadRequest,
    AdapterBindingUnavailable,
)
from app.modules.compensation.service import AdapterBindingService
from app.modules.projects.api import (
    ProjectCompensationBindingEligibilityFacts,
    ProjectCompensationBindingUnavailable,
)


class Eligibility:
    def __init__(self, *, project_available: bool = True, actor_available: bool = True) -> None:
        self.project_available = project_available
        self.actor_available = actor_available
        self.calls: list[str] = []

    async def lock_compensation_binding_project(
        self, project_id: UUID
    ) -> ProjectCompensationBindingEligibilityFacts:
        self.calls.append("project")
        if not self.project_available:
            raise ProjectCompensationBindingUnavailable("project_unavailable")
        return ProjectCompensationBindingEligibilityFacts(project_id=project_id)

    async def lock_compensation_adapter_actor(
        self, adapter_actor_id: UUID
    ) -> CompensationAdapterActorEligibilityFacts:
        self.calls.append("actor")
        if not self.actor_available:
            raise CompensationAdapterActorUnavailable("actor_unavailable")
        return CompensationAdapterActorEligibilityFacts(adapter_actor_id=adapter_actor_id)


@dataclass(slots=True)
class Prepared:
    facts: AdapterBindingMutationAuthorizationFacts
    transaction: object
    consumed: bool = False
    closed: bool = False


class Authorization:
    def __init__(self) -> None:
        self.prepared = 0
        self.consumed = 0
        self.closed = 0
        self.read_authorized = 0
        self._session = None
        self._prepared: dict[int, Prepared] = {}
        self.read_available = True

    def bind_session(self, session) -> None:
        self._session = session

    def _transaction(self) -> object:
        assert self._session is not None
        transaction = self._session.sync_session.get_transaction()
        assert transaction is not None
        return transaction

    async def authorize_adapter_binding_read(self, request: AdapterBindingReadRequest) -> None:
        del request
        self.read_authorized += 1
        if not self.read_available:
            raise AdapterBindingUnavailable("read_denied")

    async def prepare_adapter_binding_mutation(
        self, facts: AdapterBindingMutationAuthorizationFacts
    ) -> object:
        self.prepared += 1
        prepared = Prepared(facts=facts, transaction=self._transaction())
        self._prepared[id(prepared)] = prepared
        return prepared

    async def consume_adapter_binding_mutation(
        self, prepared: object, facts: AdapterBindingMutationAuthorizationFacts
    ) -> UUID:
        assert type(prepared) is Prepared
        assert self._prepared.get(id(prepared)) is prepared
        assert prepared.facts == facts
        assert not prepared.consumed and not prepared.closed
        assert prepared.transaction is self._transaction()
        prepared.consumed = True
        self.consumed += 1
        return facts.actor_profile_id

    def close_adapter_binding_mutation(self, prepared: object) -> None:
        assert type(prepared) is Prepared
        assert self._prepared.get(id(prepared)) is prepared
        assert not prepared.closed
        prepared.closed = True
        self.closed += 1


class CloseFailureAuthorization(Authorization):
    def close_adapter_binding_mutation(self, prepared: object) -> None:
        super().close_adapter_binding_mutation(prepared)
        raise AdapterBindingUnavailable("close_failed")


class BlockingAuthorization(Authorization):
    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def consume_adapter_binding_mutation(
        self, prepared: object, facts: AdapterBindingMutationAuthorizationFacts
    ) -> UUID:
        self.entered.set()
        await self.release.wait()
        return await super().consume_adapter_binding_mutation(prepared, facts)


def service(session, authorization: Authorization, eligibility: Eligibility | None = None):
    authorization.bind_session(session)
    eligibility = eligibility or Eligibility()
    return AdapterBindingService(
        session,
        read_authorization=authorization,
        mutation_authorization=authorization,
        projects=eligibility,
        actors=eligibility,
    )
