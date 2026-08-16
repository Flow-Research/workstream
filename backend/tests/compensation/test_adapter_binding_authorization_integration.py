"""Public-port composition proof for CON-to-AUTH adapter binding."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db import session as db_session
from app.adapters.auth.adapter_bindings import CompensationAdapterBindingAuthorization
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.compensation_adapter import CompensationAdapterActorEligibility
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.authorization.api import AuthorizationDenied
from app.modules.compensation.api import (
    AdapterBindingCreateRequest,
    AdapterBindingMutationAuthorizationFacts,
    AdapterBindingReadRequest,
    AdapterBindingUnavailable,
)
from app.modules.compensation.models import ProjectCompensationAdapterBinding
from app.modules.compensation.service import AdapterBindingService
from app.modules.projects.compensation_binding import ProjectCompensationBindingEligibility
from project_create_fixtures import insert_historical_project


pytest_plugins = ("adapter_binding_fixtures",)


class _Authorization:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.handle = object()

    async def authorize_read(self, **kwargs) -> None:
        self.calls.append(("read", kwargs))

    async def prepare_mutation(self, facts):
        self.calls.append(("prepare", facts))
        return self.handle

    async def consume_mutation(self, prepared, facts):
        self.calls.append(("consume", prepared, facts))
        return facts.actor_profile_id

    def close_mutation(self, prepared) -> None:
        self.calls.append(("close", prepared))


def _facts() -> AdapterBindingMutationAuthorizationFacts:
    return AdapterBindingMutationAuthorizationFacts(
        action="compensation.adapter_binding.suspend",
        actor_profile_id=uuid4(),
        operation_id=uuid4(),
        request_digest="sha256:" + "b" * 64,
        project_id=uuid4(),
        adapter_binding_id=uuid4(),
        instrument_type="project_points",
        adapter_actor_id=uuid4(),
        route_key="points.primary",
        expected_status="active",
        expected_lifecycle_version=3,
    )


@pytest.mark.asyncio
async def test_real_owner_eligibility_does_not_activate_binding_authority(
    compensation_database_env: str,
) -> None:
    project_id, authority_actor_id, adapter_actor_id = uuid4(), uuid4(), uuid4()
    async with db_session.get_session_factory()() as session:
        async with session.begin():
            session.add_all(
                (
                    ActorProfile(
                        id=str(authority_actor_id),
                        actor_kind="human",
                        status="active",
                        provisioning_method="automatic_first_access",
                        created_by=str(authority_actor_id),
                    ),
                    ActorProfile(
                        id=str(adapter_actor_id),
                        actor_kind="service",
                        status="active",
                        provisioning_method="manual_service_provisioning",
                        service_identity=ServiceIdentity.COMPENSATION_ADAPTER.value,
                        created_by=str(authority_actor_id),
                    ),
                )
            )
            await session.flush()
            session.add_all(
                (
                    ActorIdentityLink(
                        id=str(uuid4()),
                        actor_profile_id=str(authority_actor_id),
                        issuer="https://compensation.test",
                        subject=f"authority-{authority_actor_id}",
                        subject_kind="human",
                        status="active",
                        linked_by=str(authority_actor_id),
                        last_verified_at=datetime.now(UTC),
                    ),
                    ActorIdentityLink(
                        id=str(uuid4()),
                        actor_profile_id=str(adapter_actor_id),
                        issuer="https://compensation.test",
                        subject=f"adapter-{adapter_actor_id}",
                        subject_kind="service",
                        status="active",
                        linked_by=str(authority_actor_id),
                    ),
                )
            )
            await insert_historical_project(
                session,
                project_id=str(project_id),
                name="CP03A project",
                slug=f"cp03a-{str(project_id)[:8]}",
            )

        with pytest.raises(AdapterBindingUnavailable):
            async with session.begin():
                await AdapterBindingService(
                    session,
                    projects=ProjectCompensationBindingEligibility(session),
                    actors=CompensationAdapterActorEligibility(session),
                ).create(
                    AdapterBindingCreateRequest(
                        operation_id=uuid4(),
                        actor_profile_id=authority_actor_id,
                        project_id=project_id,
                        instrument_type="money",
                        adapter_actor_id=adapter_actor_id,
                        route_key="adapter.primary",
                    )
                )

        count = await session.scalar(
            select(func.count()).select_from(ProjectCompensationAdapterBinding)
        )
        assert count == 0


@pytest.mark.asyncio
async def test_public_adapter_preserves_exact_read_and_mutation_facts() -> None:
    authorization = _Authorization()
    adapter = CompensationAdapterBindingAuthorization(authorization)
    read = AdapterBindingReadRequest(
        actor_profile_id=uuid4(), project_id=uuid4(), adapter_binding_id=uuid4()
    )
    await adapter.authorize_adapter_binding_read(read)
    facts = _facts()
    prepared = await adapter.prepare_adapter_binding_mutation(facts)
    actor = await adapter.consume_adapter_binding_mutation(prepared, facts)
    adapter.close_adapter_binding_mutation(prepared)
    translated = authorization.calls[1][1]
    assert authorization.calls[0][1]["actor_profile_id"] == read.actor_profile_id
    assert authorization.calls[0][1]["facts"].project_id == read.project_id
    assert authorization.calls[0][1]["facts"].adapter_binding_id == read.adapter_binding_id
    assert translated.action_id == facts.action
    assert translated.actor_profile_id == facts.actor_profile_id
    assert translated.operation_id == facts.operation_id
    assert translated.request_digest == facts.request_digest
    assert translated.project_id == facts.project_id
    assert translated.adapter_binding_id == facts.adapter_binding_id
    assert translated.instrument_type == facts.instrument_type
    assert translated.adapter_actor_id == facts.adapter_actor_id
    assert translated.route_key == facts.route_key
    assert translated.expected_status == facts.expected_status
    assert translated.expected_lifecycle_version == facts.expected_lifecycle_version
    assert actor == facts.actor_profile_id
    assert authorization.calls[-1] == ("close", authorization.handle)


@pytest.mark.asyncio
async def test_public_adapter_conceals_auth_boundary_denial() -> None:
    class _Denied(_Authorization):
        async def authorize_read(self, **kwargs) -> None:
            del kwargs
            raise AuthorizationDenied("denied")

    adapter = CompensationAdapterBindingAuthorization(_Denied())
    with pytest.raises(AdapterBindingUnavailable, match="unavailable"):
        await adapter.authorize_adapter_binding_read(
            AdapterBindingReadRequest(
                actor_profile_id=uuid4(),
                project_id=uuid4(),
                adapter_binding_id=uuid4(),
            )
        )
