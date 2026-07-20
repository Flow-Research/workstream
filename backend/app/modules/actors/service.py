"""Canonical actor resolution and bounded legacy workflow compatibility."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_any_role
from app.modules.actors.models import (
    GLOBAL_PROFILE_SCOPE_ID,
    GLOBAL_PROFILE_SCOPE_TYPE,
    ActorIdentityLink,
    ActorProfile,
    LegacyActorIdentity,
    LegacyWorkflowEligibility,
)
from app.modules.actors.repository import ActorRepository
from app.modules.actors.schemas import (
    ActorIdentityLinkAdminResponse,
    ActorProfileAdminResponse,
    ActorProfileSelfResponse,
    ActorProfileUpdateRequest,
    LegacyWorkflowEligibilityActivationRequest,
    LegacyWorkflowEligibilityResponse,
)
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.audit.repository import AuditRepository
from app.modules.audit.schemas import (
    ActorReferenceKind,
    AuthorityAuditEventInput,
    AuthorityEventType,
)
from app.modules.audit.service import AuditService
from app.modules.authorization.runtime import ActorSelfResourceContext
from app.modules.tasks.models import AuditEvent
from app.schemas.auth import ActorContext, VerifiedIssuerToken, actor_id_from_external_identity


class ActorRegistryError(Exception):
    """Stable actor-resolution failure safe for API translation."""

    status_code = 400
    code = "actor_registry_error"


class UnsupportedSubjectKind(ActorRegistryError):
    status_code = 403
    code = "unsupported_subject_kind"


class ServiceActorNotProvisioned(ActorRegistryError):
    status_code = 403
    code = "service_actor_not_provisioned"


class IdentityLinkRevoked(ActorRegistryError):
    status_code = 403
    code = "identity_link_revoked"


class ActorSuspended(ActorRegistryError):
    status_code = 403
    code = "actor_suspended"


class ActorDeactivated(ActorRegistryError):
    status_code = 403
    code = "actor_deactivated"


class ActorProfileDisabled(ActorRegistryError):
    """Temporary compatibility denial for a disabled eligibility row."""

    status_code = 403
    code = "legacy_workflow_eligibility_disabled"


class ActiveHumanWriteActorRequired(ActorRegistryError):
    """The exact canonical caller is not currently eligible to write."""

    status_code = 403
    code = "active_contributor_required"


class CanonicalWriteActorUnavailable(RuntimeError):
    """Canonical profile/link state is missing or internally inconsistent."""


@dataclass(frozen=True)
class ResolvedActor:
    """Canonical profile and exact verified identity link for one request."""

    profile: ActorProfile
    identity_link: ActorIdentityLink


@dataclass(frozen=True, slots=True)
class ActorAdmissionProof:
    """Primitive canonical actor/link state locked for a caller transaction."""

    actor_profile_id: str
    actor_kind: str
    actor_status: str
    service_identity: str | None
    identity_link_id: str
    identity_link_subject_kind: str
    identity_link_status: str


class ActorService:
    """Resolve canonical actors and own first-human provisioning transactions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ActorRepository(session)
        self._audit = AuditService(session)
        self._legacy_audit = AuditRepository(session)

    async def lock_admission_proof(
        self,
        actor_profile_id: UUID,
        identity_link_id: UUID,
    ) -> ActorAdmissionProof | None:
        """Lock and project one exact actor/link pair without deciding authority."""
        locked = await self._repo.lock_exact_actor_identity(
            str(actor_profile_id),
            str(identity_link_id),
        )
        if locked is None:
            return None
        profile, link = locked
        return ActorAdmissionProof(
            actor_profile_id=profile.id,
            actor_kind=profile.actor_kind,
            actor_status=profile.status,
            service_identity=profile.service_identity,
            identity_link_id=link.id,
            identity_link_subject_kind=link.subject_kind,
            identity_link_status=link.status,
        )

    async def find_verified_actor(self, token: VerifiedIssuerToken) -> ResolvedActor | None:
        """Return a canonical actor for an existing exact identity link."""
        resolved = await self.find_actor_for_authorization(token)
        if resolved is None:
            return None
        self._validate_link(token, resolved.identity_link, resolved.profile)
        return resolved

    async def find_actor_for_authorization(
        self,
        token: VerifiedIssuerToken,
    ) -> ResolvedActor | None:
        """Load an exact linked actor while leaving lifecycle denial to AUTH."""
        link = await self._repo.get_identity_link(token.issuer, token.subject)
        if link is None:
            return None
        profile = await self._repo.get_actor_profile(link.actor_profile_id)
        if profile is None:
            raise RuntimeError("identity link references a missing actor profile")
        if link.subject_kind != token.subject_kind or profile.actor_kind != token.subject_kind:
            raise UnsupportedSubjectKind("Subject kind does not match actor")
        return ResolvedActor(profile=profile, identity_link=link)

    async def resolve_verified_actor(
        self,
        token: VerifiedIssuerToken,
        *,
        request_id: UUID,
        correlation_id: UUID,
    ) -> ResolvedActor:
        """Resolve an existing actor or atomically provision one verified human."""
        if token.subject_kind == "service":
            raise ServiceActorNotProvisioned("Service actor is not provisioned")
        if token.subject_kind != "human":
            raise UnsupportedSubjectKind("Unsupported subject kind")

        resolved = await self.find_verified_actor(token)
        if resolved is not None:
            return await self._touch_verified_actor(resolved)

        await self._repo.lock_external_identity(token.issuer, token.subject)
        resolved = await self.find_verified_actor(token)
        if resolved is not None:
            return await self._touch_verified_actor(resolved)

        profile_id = actor_id_from_external_identity(token.issuer, token.subject)
        profile = ActorProfile(
            id=profile_id,
            actor_kind="human",
            status="active",
            provisioning_method="automatic_first_access",
            display_name=None,
            contact_email=None,
            created_by=profile_id,
            last_seen_at=func.now(),
        )
        link = ActorIdentityLink(
            id=str(uuid4()),
            actor_profile_id=profile_id,
            issuer=token.issuer,
            subject=token.subject,
            subject_kind="human",
            status="active",
            linked_by=profile_id,
            last_verified_at=func.clock_timestamp(),
        )
        await self._repo.add_actor_profile(profile)
        await self._repo.add_identity_link(link)
        await self._write_provisioning_events(
            profile,
            link,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        await self._session.commit()
        await self._session.refresh(profile)
        await self._session.refresh(link)
        return ResolvedActor(profile=profile, identity_link=link)

    async def resolve_actor_for_authorization(
        self,
        token: VerifiedIssuerToken,
        *,
        request_id: UUID,
        correlation_id: UUID,
    ) -> ResolvedActor:
        """Resolve self authorization without preempting lifecycle decisions."""
        if token.subject_kind == "service":
            raise ServiceActorNotProvisioned("Service actor is not provisioned")
        if token.subject_kind != "human":
            raise UnsupportedSubjectKind("Unsupported subject kind")

        resolved = await self.find_actor_for_authorization(token)
        if resolved is None:
            return await self.resolve_verified_actor(
                token,
                request_id=request_id,
                correlation_id=correlation_id,
            )
        return resolved

    async def resolve_service_for_authorization(
        self,
        token: VerifiedIssuerToken,
    ) -> ResolvedActor:
        """Resolve one explicitly provisioned service without first access."""
        if token.subject_kind != "service":
            raise UnsupportedSubjectKind("Unsupported subject kind")
        try:
            resolved = await self.find_actor_for_authorization(token)
        except RuntimeError as exc:
            raise ServiceActorNotProvisioned("Service actor is not provisioned") from exc
        if resolved is None or resolved.profile.service_identity is None:
            raise ServiceActorNotProvisioned("Service actor is not provisioned")
        try:
            ServiceIdentity(resolved.profile.service_identity)
        except ValueError as exc:
            raise ServiceActorNotProvisioned("Service actor is not provisioned") from exc
        return resolved

    async def lock_actor_for_authorization(
        self,
        resolved: ResolvedActor,
    ) -> ResolvedActor:
        """Lock profile then exact link and reject missing or drifted rows."""
        profile = await self._repo.get_actor_profile(resolved.profile.id, for_update=True)
        if profile is None:
            raise RuntimeError("resolved actor profile disappeared")
        link = await self._repo.get_identity_link_by_id(
            resolved.identity_link.id,
            for_update=True,
        )
        if link is None:
            raise RuntimeError("resolved identity link disappeared")
        if (
            link.actor_profile_id != resolved.profile.id
            or link.issuer != resolved.identity_link.issuer
            or link.subject != resolved.identity_link.subject
            or link.subject_kind != resolved.identity_link.subject_kind
            or profile.id != resolved.profile.id
        ):
            raise RuntimeError("resolved actor identity changed")
        return ResolvedActor(profile=profile, identity_link=link)

    async def lock_actor_self_for_authorization(
        self,
        resolved: ResolvedActor,
    ) -> ResolvedActor:
        """Lock the exact profile then its link and reject identity drift."""
        return await self.lock_actor_for_authorization(resolved)

    async def require_active_human_write_actor(self, actor: ActorContext) -> None:
        """Lock and revalidate one exact human caller in the current transaction."""
        profile = await self._repo.get_actor_profile(actor.actor_id, for_update=True)
        if profile is None:
            raise CanonicalWriteActorUnavailable("canonical actor profile is missing")
        if profile.actor_kind != "human" or profile.status != "active":
            raise ActiveHumanWriteActorRequired("active contributor identity required")

        link = await self._repo.get_identity_link(
            actor.external_issuer,
            actor.external_subject,
            for_update=True,
        )
        if link is None:
            raise CanonicalWriteActorUnavailable("canonical identity link is missing")
        if link.actor_profile_id != profile.id or link.subject_kind != "human":
            raise CanonicalWriteActorUnavailable("canonical identity link is inconsistent")
        if link.status != "active":
            raise ActiveHumanWriteActorRequired("active contributor identity required")

    async def update_self(
        self,
        resolved: ResolvedActor,
        payload: ActorProfileUpdateRequest,
    ) -> ActorProfileSelfResponse:
        """Stage only the authorized human actor's owned display fields."""
        profile = await self._repo.get_actor_profile(resolved.profile.id, for_update=True)
        if profile is None:
            raise RuntimeError("resolved actor profile disappeared")
        self._require_active_human(profile)
        if "display_name" in payload.model_fields_set:
            profile.display_name = payload.display_name
        if "contact_email" in payload.model_fields_set:
            profile.contact_email = payload.contact_email
        profile.updated_at = func.now()
        await self._session.flush()
        await self._session.refresh(profile)
        return self.self_response(profile)

    async def touch_after_authorization(self, resolved: ResolvedActor) -> ResolvedActor:
        """Stage monotonic verification timestamps after an allowed decision."""
        await self._repo.touch_verified_actor(resolved.profile, resolved.identity_link)
        await self._session.refresh(resolved.profile)
        await self._session.refresh(resolved.identity_link)
        return resolved

    async def read_admin_profile(
        self,
        actor_profile_id: UUID,
    ) -> ActorProfileAdminResponse | None:
        """Return one bounded actor view without changing target state."""
        profile = await self._repo.get_actor_profile(str(actor_profile_id))
        if profile is None:
            return None
        return ActorProfileAdminResponse(
            actor_profile_id=UUID(profile.id),
            actor_kind=profile.actor_kind,
            status=profile.status,
            provisioning_method=profile.provisioning_method,
            service_identity=profile.service_identity,
            display_name=profile.display_name,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            last_seen_at=profile.last_seen_at,
            suspended_at=profile.suspended_at,
            reactivated_at=profile.reactivated_at,
            deactivated_at=profile.deactivated_at,
        )

    async def read_admin_identity_link(
        self,
        actor_profile_id: UUID,
    ) -> ActorIdentityLinkAdminResponse | None:
        """Return one bounded link view selected by its canonical actor."""
        link = await self._repo.get_identity_link_for_actor(str(actor_profile_id))
        if link is None:
            return None
        return ActorIdentityLinkAdminResponse(
            identity_link_id=UUID(link.id),
            actor_profile_id=UUID(link.actor_profile_id),
            subject_kind=link.subject_kind,
            status=link.status,
            linked_at=link.linked_at,
            last_verified_at=link.last_verified_at,
            revoked_at=link.revoked_at,
            reactivated_at=link.reactivated_at,
        )

    @staticmethod
    def actor_self_resource(
        actor_profile_id: str,
        requested_fields: set[str] | frozenset[str],
    ) -> ActorSelfResourceContext:
        """Compose closed server-owned facts for one actor self operation."""
        return ActorSelfResourceContext(
            resource_type="actor_profile",
            resource_id=UUID(actor_profile_id),
            requested_fields=tuple(sorted(requested_fields)),
        )

    async def refresh_legacy_identity(self, actor: ActorContext) -> LegacyActorIdentity:
        """Persist token observations only in the non-authoritative compatibility table."""
        identity = await self._repo.upsert_legacy_identity(self._legacy_identity_from_actor(actor))
        await self._session.commit()
        return identity

    async def activate_legacy_workflow_eligibility(
        self,
        actor: ActorContext,
        payload: LegacyWorkflowEligibilityActivationRequest,
    ) -> LegacyWorkflowEligibilityResponse:
        """Activate temporary submitter intake metadata without creating authority."""
        require_any_role(actor, {"worker"})
        await self._repo.lock_external_identity(
            actor.external_issuer,
            actor.external_subject,
        )
        identity = await self._repo.upsert_legacy_identity(self._legacy_identity_from_actor(actor))
        eligibility = await self._repo.get_legacy_eligibility(
            actor.actor_id,
            "worker",
            GLOBAL_PROFILE_SCOPE_TYPE,
            GLOBAL_PROFILE_SCOPE_ID,
        )
        previous_status = None
        previous_tags: list[str] = []
        inserted = False
        if eligibility is None:
            eligibility = LegacyWorkflowEligibility(
                id=str(uuid4()),
                actor_id=actor.actor_id,
                profile_type="worker",
                status="active",
                skill_tags=payload.skill_tags,
                scope_type=GLOBAL_PROFILE_SCOPE_TYPE,
                scope_id=GLOBAL_PROFILE_SCOPE_ID,
                profile_metadata={"source": "legacy_worker_profile_api"},
            )
            inserted = await self._repo.insert_legacy_eligibility_if_absent(eligibility)
            eligibility = await self._repo.get_legacy_eligibility(
                actor.actor_id,
                "worker",
                GLOBAL_PROFILE_SCOPE_TYPE,
                GLOBAL_PROFILE_SCOPE_ID,
            )
            if eligibility is None:
                raise RuntimeError("legacy eligibility insert did not return a row")
        else:
            if eligibility.status == "disabled":
                raise ActorProfileDisabled("Legacy workflow eligibility is disabled")
            previous_status = eligibility.status
            previous_tags = list(eligibility.skill_tags)
            eligibility.status = "active"
            eligibility.skill_tags = payload.skill_tags
            eligibility.profile_metadata = {"source": "legacy_worker_profile_api"}
            eligibility.updated_at = func.now()

        if (
            inserted
            or previous_status != eligibility.status
            or previous_tags != eligibility.skill_tags
        ):
            await self._write_legacy_eligibility_audit(
                actor,
                eligibility,
                from_status=previous_status,
            )
        await self._session.commit()
        await self._session.refresh(eligibility)
        return LegacyWorkflowEligibilityResponse(
            id=eligibility.id,
            actor_id=eligibility.actor_id,
            profile_type=eligibility.profile_type,
            status=eligibility.status,
            skill_tags=list(eligibility.skill_tags),
            scope_type=eligibility.scope_type,
            scope_id=eligibility.scope_id,
            profile_metadata=dict(eligibility.profile_metadata),
            external_subject=identity.external_subject,
            external_issuer=identity.external_issuer,
            created_at=eligibility.created_at,
            updated_at=eligibility.updated_at,
        )

    @staticmethod
    def self_response(
        profile: ActorProfile,
        *,
        admin_roles: tuple[str, ...] = (),
    ) -> ActorProfileSelfResponse:
        """Build the Contributor-domain response with informational active role names."""
        if profile.actor_kind != "human":
            raise UnsupportedSubjectKind("Unsupported subject kind")
        if profile.status == "deactivated":
            raise ActorDeactivated("Actor is deactivated")
        return ActorProfileSelfResponse(
            actor_profile_id=profile.id,
            actor_kind="human",
            status=profile.status,
            display_name=profile.display_name,
            contact_email=profile.contact_email,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            last_seen_at=profile.last_seen_at,
            admin_roles=admin_roles,
        )

    async def _touch_verified_actor(self, resolved: ResolvedActor) -> ResolvedActor:
        """Persist database-time verification for one existing actor."""
        await self._repo.touch_verified_actor(resolved.profile, resolved.identity_link)
        await self._session.commit()
        await self._session.refresh(resolved.profile)
        await self._session.refresh(resolved.identity_link)
        return resolved

    @staticmethod
    def _legacy_identity_from_actor(actor: ActorContext) -> LegacyActorIdentity:
        """Project privacy-bounded compatibility fields from verified context."""
        return LegacyActorIdentity(
            actor_id=actor.actor_id,
            external_subject=actor.external_subject,
            external_issuer=actor.external_issuer,
            display_name=None,
            email=None,
            last_seen_roles=list(actor.roles),
            last_claim_snapshot={"roles": list(actor.roles)},
            auth_source=actor.auth_source,
            is_dev_auth=actor.is_dev_auth,
        )

    @staticmethod
    def _validate_link(
        token: VerifiedIssuerToken,
        link: ActorIdentityLink,
        profile: ActorProfile,
    ) -> None:
        if link.subject_kind != token.subject_kind or profile.actor_kind != token.subject_kind:
            raise UnsupportedSubjectKind("Subject kind does not match actor")
        if link.status != "active":
            raise IdentityLinkRevoked("Identity link is revoked")

    @staticmethod
    def _require_active_human(profile: ActorProfile) -> None:
        if profile.actor_kind != "human":
            raise UnsupportedSubjectKind("Unsupported subject kind")
        if profile.status == "suspended":
            raise ActorSuspended("Actor is suspended")
        if profile.status == "deactivated":
            raise ActorDeactivated("Actor is deactivated")

    async def _write_provisioning_events(
        self,
        profile: ActorProfile,
        link: ActorIdentityLink,
        *,
        request_id: UUID,
        correlation_id: UUID,
    ) -> None:
        common = {
            "actor_ref_kind": ActorReferenceKind.ACTOR_PROFILE,
            "actor_ref": profile.id,
            "request_id": request_id,
            "correlation_id": correlation_id,
            "target_actor_ref_kind": ActorReferenceKind.ACTOR_PROFILE,
            "target_actor_ref": profile.id,
        }
        await self._audit.add_authority_event(
            AuthorityAuditEventInput(
                event_id=uuid4(),
                event_type=AuthorityEventType.ACTOR_PROFILE_PROVISIONED,
                entity_type="actor_profile",
                entity_id=profile.id,
                resource_type="actor_profile",
                resource_id=profile.id,
                target_ref_kind="actor_profile",
                target_ref_id=profile.id,
                reason="automatic_first_access",
                after_facts={
                    "status": "active",
                    "subject_kind": "human",
                    "provisioning_method": "automatic_first_access",
                },
                **common,
            )
        )
        await self._audit.add_authority_event(
            AuthorityAuditEventInput(
                event_id=uuid4(),
                event_type=AuthorityEventType.ACTOR_IDENTITY_LINKED,
                entity_type="actor_identity_link",
                entity_id=link.id,
                resource_type="actor_identity_link",
                resource_id=link.id,
                target_ref_kind="actor_identity_link",
                target_ref_id=link.id,
                reason="identity_lifecycle_change",
                after_facts={"status": "active", "subject_kind": "human"},
                **common,
            )
        )

    async def _write_legacy_eligibility_audit(
        self,
        actor: ActorContext,
        eligibility: LegacyWorkflowEligibility,
        *,
        from_status: str | None,
    ) -> None:
        audit = actor.audit_context()
        await self._legacy_audit.add_audit_event(
            AuditEvent(
                id=str(uuid4()),
                entity_type="legacy_workflow_eligibility",
                entity_id=eligibility.id,
                event_type="legacy_workflow_eligibility_activated",
                from_status=from_status,
                to_status=eligibility.status,
                actor_id=audit.actor_id,
                external_subject=audit.external_subject,
                external_issuer=audit.external_issuer,
                actor_roles=list(audit.actor_roles),
                claim_snapshot=audit.claim_snapshot,
                auth_source=audit.auth_source,
                is_dev_auth=audit.is_dev_auth,
                reason="legacy_intake_compatibility",
                event_payload={"skill_tags": list(eligibility.skill_tags)},
            )
        )


class LegacyWorkflowEligibilityCompatibility:
    """Enumerated read-only bridge for task eligibility during staged cutover."""

    def __init__(self, session: AsyncSession) -> None:
        self._repository = ActorRepository(session)

    async def get_active_submitter_eligibility(
        self,
        actor_profile_id: str,
    ) -> LegacyWorkflowEligibility | None:
        """Return active legacy submitter metadata without granting permission."""
        eligibility = await self._repository.get_legacy_eligibility(
            actor_profile_id,
            "worker",
            GLOBAL_PROFILE_SCOPE_TYPE,
            GLOBAL_PROFILE_SCOPE_ID,
        )
        if eligibility is None or eligibility.status != "active":
            return None
        return eligibility
