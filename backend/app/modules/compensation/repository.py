"""Caller-transaction persistence for compensation adapter bindings."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.compensation.models import ProjectCompensationAdapterBinding
from app.modules.compensation.schemas import ProjectCompensationAdapterBindingInput


class CompensationAdapterActorInvalid(RuntimeError):
    """The requested adapter actor is not the exact active service principal."""


class CompensationBindingRepository:
    """Persist binding identity without authorization or lifecycle commands."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_binding(
        self,
        value: ProjectCompensationAdapterBindingInput,
        *,
        expected_service_identity: ServiceIdentity,
    ) -> ProjectCompensationAdapterBinding:
        """Validate and lock AUTH-owned identity facts, then flush one active binding."""
        identity = await self._session.execute(
            select(ActorProfile, ActorIdentityLink)
            .join(
                ActorIdentityLink,
                ActorIdentityLink.actor_profile_id == ActorProfile.id,
            )
            .where(ActorProfile.id == value.adapter_actor_id)
            .with_for_update(of=(ActorProfile, ActorIdentityLink))
        )
        row = identity.one_or_none()
        if row is None:
            raise CompensationAdapterActorInvalid("compensation_adapter_actor_invalid")
        profile, link = row
        if not (
            profile.actor_kind == "service"
            and profile.status == "active"
            and profile.service_identity == expected_service_identity.value
            and link.subject_kind == "service"
            and link.status == "active"
        ):
            raise CompensationAdapterActorInvalid("compensation_adapter_actor_invalid")

        binding = ProjectCompensationAdapterBinding(
            id=value.id,
            project_id=value.project_id,
            instrument_type=value.instrument_type.value,
            adapter_actor_id=value.adapter_actor_id,
            route_key=value.route_key,
            status="active",
            binding_lifecycle_version=1,
            created_by=value.created_by,
        )
        self._session.add(binding)
        await self._session.flush()
        return binding
