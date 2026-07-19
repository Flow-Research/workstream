"""Persistence for canonical actors and bounded legacy workflow metadata."""

from __future__ import annotations

import hashlib

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.models import (
    ActorIdentityLink,
    ActorProfile,
    LegacyActorIdentity,
    LegacyWorkflowEligibility,
)


class ActorRepository:
    """Wrap canonical actor persistence in the caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_external_identity(self, issuer: str, subject: str) -> None:
        """Serialize first access for one exact external identity."""
        key = self._advisory_key(issuer, subject)
        await self._session.execute(select(func.pg_advisory_xact_lock(key)))

    async def lock_service_identity(self, service_identity: str) -> None:
        """Serialize provisioning for one fixed local service identity."""
        key = self._advisory_key(service_identity, domain=b"\x01")
        await self._session.execute(select(func.pg_advisory_xact_lock(key)))

    @staticmethod
    def _advisory_key(*values: str, domain: bytes = b"") -> int:
        framed = bytearray(domain)
        for value in values:
            encoded = value.encode()
            framed.extend(len(encoded).to_bytes(4, "big"))
            framed.extend(encoded)
        digest = hashlib.sha256(framed).digest()
        return int.from_bytes(digest[:8], "big", signed=True)

    async def get_identity_link(
        self,
        issuer: str,
        subject: str,
        *,
        for_update: bool = False,
    ) -> ActorIdentityLink | None:
        """Load the immutable link for one issuer and opaque subject."""
        query = select(ActorIdentityLink).where(
            ActorIdentityLink.issuer == issuer,
            ActorIdentityLink.subject == subject,
        )
        if for_update:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def get_identity_link_by_id(
        self,
        identity_link_id: str,
        *,
        for_update: bool = False,
    ) -> ActorIdentityLink | None:
        """Load one canonical identity link by its internal identifier."""
        query = select(ActorIdentityLink).where(ActorIdentityLink.id == identity_link_id)
        if for_update:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def get_identity_link_for_actor(
        self,
        actor_profile_id: str,
    ) -> ActorIdentityLink | None:
        """Load the single identity link owned by one canonical actor."""
        query = select(ActorIdentityLink).where(
            ActorIdentityLink.actor_profile_id == actor_profile_id
        )
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def get_actor_profile(
        self,
        actor_profile_id: str,
        *,
        for_update: bool = False,
    ) -> ActorProfile | None:
        """Load one canonical actor profile."""
        query = select(ActorProfile).where(ActorProfile.id == actor_profile_id)
        if for_update:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def lock_exact_actor_identity(
        self,
        actor_profile_id: str,
        identity_link_id: str,
    ) -> tuple[ActorProfile, ActorIdentityLink] | None:
        """Lock an exact canonical profile then its requested identity link."""
        profile = await self.get_actor_profile(actor_profile_id, for_update=True)
        if profile is None:
            return None
        link = await self.get_identity_link_by_id(identity_link_id, for_update=True)
        if link is None or link.actor_profile_id != actor_profile_id:
            return None
        return profile, link

    async def get_service_actor(
        self,
        service_identity: str,
    ) -> ActorProfile | None:
        """Load one fixed service ActorProfile by its immutable local identity."""
        query = select(ActorProfile).where(
            ActorProfile.actor_kind == "service",
            ActorProfile.service_identity == service_identity,
        )
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def add_actor_profile(self, profile: ActorProfile) -> ActorProfile:
        """Stage one canonical actor profile."""
        self._session.add(profile)
        await self._session.flush()
        return profile

    async def add_identity_link(self, link: ActorIdentityLink) -> ActorIdentityLink:
        """Stage one canonical identity link."""
        self._session.add(link)
        await self._session.flush()
        return link

    async def touch_verified_actor(
        self,
        profile: ActorProfile,
        link: ActorIdentityLink,
    ) -> None:
        """Record monotonic execution-time verification under canonical locks."""
        locked_profile = await self.get_actor_profile(profile.id, for_update=True)
        if locked_profile is None:
            raise RuntimeError("resolved actor profile disappeared")
        locked_link = await self.get_identity_link_by_id(link.id, for_update=True)
        if locked_link is None or locked_link.actor_profile_id != profile.id:
            raise RuntimeError("resolved identity link disappeared")
        await self._session.execute(
            update(ActorIdentityLink)
            .where(ActorIdentityLink.id == locked_link.id)
            .values(
                last_verified_at=func.greatest(
                    ActorIdentityLink.last_verified_at,
                    func.clock_timestamp(),
                )
            )
        )
        await self._session.execute(
            update(ActorProfile)
            .where(ActorProfile.id == locked_profile.id)
            .values(
                last_seen_at=func.greatest(
                    func.coalesce(ActorProfile.last_seen_at, func.clock_timestamp()),
                    func.clock_timestamp(),
                ),
                updated_at=func.greatest(
                    ActorProfile.updated_at,
                    func.clock_timestamp(),
                ),
            )
        )
        await self._session.flush()

    async def get_legacy_identity(
        self,
        actor_id: str,
        *,
        populate_existing: bool = False,
    ) -> LegacyActorIdentity | None:
        """Load non-authoritative legacy token-observation metadata."""
        return await self._session.get(
            LegacyActorIdentity,
            actor_id,
            populate_existing=populate_existing,
        )

    async def upsert_legacy_identity(
        self,
        identity: LegacyActorIdentity,
    ) -> LegacyActorIdentity:
        """Refresh bounded compatibility metadata without touching canonical actors."""
        await self._session.execute(
            insert(LegacyActorIdentity)
            .values(
                actor_id=identity.actor_id,
                external_subject=identity.external_subject,
                external_issuer=identity.external_issuer,
                display_name=identity.display_name,
                email=identity.email,
                last_seen_roles=identity.last_seen_roles,
                last_claim_snapshot=identity.last_claim_snapshot,
                auth_source=identity.auth_source,
                is_dev_auth=identity.is_dev_auth,
            )
            .on_conflict_do_update(
                index_elements=[LegacyActorIdentity.actor_id],
                set_={
                    "external_subject": identity.external_subject,
                    "external_issuer": identity.external_issuer,
                    "last_seen_roles": identity.last_seen_roles,
                    "last_claim_snapshot": identity.last_claim_snapshot,
                    "auth_source": identity.auth_source,
                    "is_dev_auth": identity.is_dev_auth,
                    "last_seen_at": func.now(),
                    "updated_at": func.now(),
                },
            )
        )
        await self._session.flush()
        persisted = await self.get_legacy_identity(identity.actor_id, populate_existing=True)
        if persisted is None:
            raise RuntimeError("legacy identity upsert did not return a row")
        return persisted

    async def get_legacy_eligibility(
        self,
        actor_id: str,
        profile_type: str,
        scope_type: str,
        scope_id: str,
    ) -> LegacyWorkflowEligibility | None:
        """Load one classified legacy workflow-eligibility row."""
        return await self._session.scalar(
            select(LegacyWorkflowEligibility)
            .where(
                LegacyWorkflowEligibility.actor_id == actor_id,
                LegacyWorkflowEligibility.profile_type == profile_type,
                LegacyWorkflowEligibility.scope_type == scope_type,
                LegacyWorkflowEligibility.scope_id == scope_id,
            )
            .execution_options(populate_existing=True)
        )

    async def insert_legacy_eligibility_if_absent(
        self,
        eligibility: LegacyWorkflowEligibility,
    ) -> bool:
        """Insert compatibility metadata without overwriting established state."""
        result = await self._session.execute(
            insert(LegacyWorkflowEligibility)
            .values(
                id=eligibility.id,
                actor_id=eligibility.actor_id,
                profile_type=eligibility.profile_type,
                status=eligibility.status,
                skill_tags=eligibility.skill_tags,
                scope_type=eligibility.scope_type,
                scope_id=eligibility.scope_id,
                profile_metadata=eligibility.profile_metadata,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    LegacyWorkflowEligibility.actor_id,
                    LegacyWorkflowEligibility.profile_type,
                    LegacyWorkflowEligibility.scope_type,
                    LegacyWorkflowEligibility.scope_id,
                ]
            )
            .returning(LegacyWorkflowEligibility.id)
        )
        await self._session.flush()
        return result.scalar_one_or_none() is not None
