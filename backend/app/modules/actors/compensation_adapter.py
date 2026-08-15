"""ACTORS-owned compensation-adapter eligibility implementation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.api import (
    CompensationAdapterActorEligibilityFacts,
    CompensationAdapterActorUnavailable,
    ServiceIdentity,
)
from app.modules.actors.models import ActorIdentityLink, ActorProfile


class CompensationAdapterActorEligibility:
    """Retain exact adapter profile/link locks in the caller transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_compensation_adapter_actor(
        self, adapter_actor_id: UUID
    ) -> CompensationAdapterActorEligibilityFacts:
        """Lock and conceal every missing or ineligible adapter identity."""
        profile = await self._session.scalar(
            select(ActorProfile)
            .where(ActorProfile.id == str(adapter_actor_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            profile is None
            or profile.actor_kind != "service"
            or profile.status != "active"
            or profile.service_identity != ServiceIdentity.COMPENSATION_ADAPTER.value
        ):
            raise CompensationAdapterActorUnavailable(
                "compensation_adapter_actor_unavailable"
            )

        link = await self._session.scalar(
            select(ActorIdentityLink)
            .where(ActorIdentityLink.actor_profile_id == profile.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            link is None
            or link.subject_kind != "service"
            or link.status != "active"
        ):
            raise CompensationAdapterActorUnavailable(
                "compensation_adapter_actor_unavailable"
            )
        return CompensationAdapterActorEligibilityFacts(
            adapter_actor_id=adapter_actor_id
        )
