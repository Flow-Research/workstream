"""Real scoped adapter binding for activation's compensated-policy control."""

from uuid import UUID, uuid4

from sqlalchemy import select

from app.adapters.auth import compensation_adapter_binding_authorization
from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorProfile, ActorIdentityLink
from app.modules.actors.compensation_adapter import CompensationAdapterActorEligibility
from app.modules.compensation.api import AdapterBindingCreateRequest
from app.modules.contributions.units.models import (
    ProjectCompensationUnit,
)
from app.modules.compensation.service import AdapterBindingService
from app.modules.projects.compensation_binding import ProjectCompensationBindingEligibility


async def create_binding(factory, world, *, instrument_type="money"):
    async with factory() as session, session.begin():
        existing = await session.scalar(select(ActorProfile.id).where(
            ActorProfile.service_identity == ServiceIdentity.COMPENSATION_ADAPTER.value
        ))
        adapter = UUID(existing) if existing is not None else new_record_id()
        if existing is None:
            session.add(
                ActorProfile(
                    id=str(adapter),
                    actor_kind="service",
                    status="active",
                    provisioning_method="manual_service_provisioning",
                    service_identity=ServiceIdentity.COMPENSATION_ADAPTER.value,
                    created_by="activation-fixture",
                )
            )
            await session.flush()
            session.add(
                ActorIdentityLink(
                    id=str(new_record_id()),
                    actor_profile_id=str(adapter),
                    issuer="workstream-internal",
                    subject=f"activation-compensation-adapter-{adapter}",
                    subject_kind="service",
                    status="active",
                    linked_by="activation-fixture",
                )
            )
        session.add(
            ProjectCompensationUnit(
                project_id=str(world.project),
                instrument_type=instrument_type,
                unit_code="USD" if instrument_type == "money" else "PTS",
                iso_currency_code="USD" if instrument_type == "money" else None,
                status="active",
                created_by=str(world.context.actor_profile_id),
            )
        )
    async with factory() as session, session.begin():
        authority = compensation_adapter_binding_authorization(session, world.context)
        binding = await AdapterBindingService(
            session,
            mutation_authorization=authority,
            projects=ProjectCompensationBindingEligibility(session),
            actors=CompensationAdapterActorEligibility(session),
        ).create(
            AdapterBindingCreateRequest(
                operation_id=uuid4(),
                actor_profile_id=world.context.actor_profile_id,
                project_id=world.project,
                instrument_type=instrument_type,
                adapter_actor_id=adapter,
                route_key=f"activation.{instrument_type}",
            )
        )
    return binding.adapter_binding_id
