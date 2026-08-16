"""CP03A composition proof while adapter-binding AUTH remains unavailable."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db import session as db_session
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.compensation_adapter import CompensationAdapterActorEligibility
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.compensation.api import AdapterBindingCreateRequest, AdapterBindingUnavailable
from app.modules.compensation.models import ProjectCompensationAdapterBinding
from app.modules.compensation.service import AdapterBindingService
from app.modules.projects.compensation_binding import ProjectCompensationBindingEligibility
from project_create_fixtures import insert_historical_project

pytest_plugins = ("adapter_binding_fixtures",)


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
