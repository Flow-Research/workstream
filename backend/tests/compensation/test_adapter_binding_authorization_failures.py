"""Fail-closed AUTH participant proofs for hidden adapter-binding mutations."""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text

from app.db import session as db_session
from app.modules.compensation.api import (
    AdapterBindingCreateRequest,
    AdapterBindingMutationAuthorizationFacts,
    AdapterBindingUnavailable,
)
from app.modules.compensation.models import (
    CompensationAdapterBindingLifecycleEvent,
    ProjectCompensationAdapterBinding,
)
from app.modules.compensation.repository import AdapterBindingRepository
from adapter_binding_fixtures import BindingSeed
from adapter_binding_test_support import Authorization, Prepared, service

pytest_plugins = ("adapter_binding_fixtures",)

FailureMode = Literal["denial", "exception", "wrong_actor"]


class _ParticipantAuthorization(Authorization):
    """Stage transaction-local evidence and inject one consume outcome."""

    def __init__(self, mode: FailureMode | None = None) -> None:
        super().__init__()
        self.mode = mode
        self.last_prepared: Prepared | None = None

    async def prepare_adapter_binding_mutation(
        self, facts: AdapterBindingMutationAuthorizationFacts
    ) -> object:
        prepared = await super().prepare_adapter_binding_mutation(facts)
        assert type(prepared) is Prepared
        self.last_prepared = prepared
        return prepared

    async def consume_adapter_binding_mutation(
        self, prepared: object, facts: AdapterBindingMutationAuthorizationFacts
    ) -> UUID:
        assert type(prepared) is Prepared and not prepared.closed
        assert self._session is not None
        await self._session.execute(
            text("insert into cp02_staged_authorization_effects values (:operation_id)"),
            {"operation_id": str(facts.operation_id)},
        )
        if self.mode == "denial":
            self.consumed += 1
            raise AdapterBindingUnavailable("consume_denied")
        if self.mode == "exception":
            self.consumed += 1
            raise RuntimeError("consume_failed")
        actor = await super().consume_adapter_binding_mutation(prepared, facts)
        return uuid4() if self.mode == "wrong_actor" else actor


class _FailingRepository(AdapterBindingRepository):
    """Fail after the binding insert has reached PostgreSQL."""

    async def add_binding_and_event(self, binding, event) -> None:
        del event
        self._session.add(binding)
        await self._session.flush()
        raise RuntimeError("product_write_failed")


async def _install_participant_probe(session) -> None:
    async with session.begin():
        await session.execute(
            text(
                "create temporary table if not exists cp02_staged_authorization_effects "
                "(operation_id uuid primary key) on commit preserve rows"
            )
        )
        await session.execute(text("delete from cp02_staged_authorization_effects"))


async def _assert_no_effect(session) -> None:
    async with session.begin():
        assert await session.scalar(
            select(func.count()).select_from(ProjectCompensationAdapterBinding)
        ) == 0
        assert await session.scalar(
            select(func.count()).select_from(CompensationAdapterBindingLifecycleEvent)
        ) == 0
        assert await session.scalar(
            text("select count(*) from cp02_staged_authorization_effects")
        ) == 0


@pytest.mark.parametrize("mode", ("denial", "exception", "wrong_actor"))
@pytest.mark.asyncio
async def test_consume_failure_closes_once_and_creates_no_effect(
    compensation_database_env: str,
    binding_seed: BindingSeed,
    mode: FailureMode,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    authorization = _ParticipantAuthorization(mode)
    expected = RuntimeError if mode == "exception" else AdapterBindingUnavailable
    async with db_session.get_session_factory()() as session:
        await _install_participant_probe(session)
        with pytest.raises(expected):
            async with session.begin():
                await service(session, authorization).create(
                    AdapterBindingCreateRequest(
                        operation_id=uuid4(), actor_profile_id=actor_id,
                        project_id=project_id, instrument_type="money",
                        adapter_actor_id=adapter_id, route_key="adapter.primary",
                    )
                )
        assert authorization.last_prepared is not None
        assert authorization.last_prepared.closed
        assert authorization.closed == 1
        await _assert_no_effect(session)
        with pytest.raises(AssertionError):
            async with session.begin():
                await authorization.consume_adapter_binding_mutation(
                    authorization.last_prepared, authorization.last_prepared.facts
                )


@pytest.mark.asyncio
async def test_product_failure_rolls_back_closed_authority_and_all_effects(
    compensation_database_env: str,
    binding_seed: BindingSeed,
) -> None:
    project_id, adapter_id, actor_id = await binding_seed()
    authorization = _ParticipantAuthorization()
    async with db_session.get_session_factory()() as session:
        await _install_participant_probe(session)
        binding_service = service(session, authorization)
        binding_service._repository = _FailingRepository(session)
        with pytest.raises(RuntimeError, match="product_write_failed"):
            async with session.begin():
                await binding_service.create(
                    AdapterBindingCreateRequest(
                        operation_id=uuid4(), actor_profile_id=actor_id,
                        project_id=project_id, instrument_type="money",
                        adapter_actor_id=adapter_id, route_key="adapter.primary",
                    )
                )
        assert authorization.last_prepared is not None
        assert authorization.last_prepared.consumed
        assert authorization.last_prepared.closed
        assert (authorization.prepared, authorization.consumed, authorization.closed) == (
            1, 1, 1,
        )
        await _assert_no_effect(session)
        with pytest.raises(AssertionError):
            async with session.begin():
                await authorization.consume_adapter_binding_mutation(
                    authorization.last_prepared, authorization.last_prepared.facts
                )
