"""Controlled fixed service actor provisioning orchestration."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.repository import ActorRepository
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.audit.schemas import (
    ActorReferenceKind,
    AuthorityAuditEventInput,
    AuthorityEventType,
)
from app.modules.audit.service import AuditService
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.runtime import (
    AuthorizationDecision,
    MatchedAuthorityKind,
    ServiceActorProvisionResourceContext,
    authorization_resource_digest,
)
from app.modules.authorization.schemas import (
    AuthorityClaimHandle,
    AuthorityInvalidationContext,
    AuthorityMismatchContext,
    AuthorityReservationResult,
    AuthorityResourceType,
    AuthorityResponseReference,
    ServiceActorCreateRequest,
    derive_reason_digest,
    derive_service_identity_digest,
)
from app.modules.authorization.service import AuthorityMutationService
from app.modules.authorization.service_actor_schemas import ServiceActorProvisionResponse


class ServiceActorConflict(StrEnum):
    """Closed service provisioning occupancy conflicts."""

    SERVICE_IDENTITY = "service_identity_already_provisioned"
    EXTERNAL_IDENTITY = "identity_subject_already_linked"


class ServiceActorProvisioningUnavailable(RuntimeError):
    """A committed provisioning result cannot be reconstructed from storage."""


class ServiceActorProvisioningService:
    """Stage one fixed service actor and its bounded authority evidence."""

    def __init__(self, session: AsyncSession) -> None:
        self._actors = ActorRepository(session)
        self._mutation = AuthorityMutationService(session)
        self._audit = AuditService(session)

    async def reserve(
        self,
        *,
        idempotency_key: UUID,
        actor_profile_id: UUID,
        request: ServiceActorCreateRequest,
    ) -> AuthorityReservationResult:
        """Reserve one caller/service-create/idempotency namespace."""
        return await self._mutation.reserve(
            idempotency_key=idempotency_key,
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=str(actor_profile_id),
            request=request.model_dump(),
        )

    async def lock_and_find_conflict(
        self,
        *,
        service_identity: ServiceIdentity,
        issuer: str,
        subject: str,
    ) -> ServiceActorConflict | None:
        """Serialize both identity domains and return deterministic occupancy."""
        await self._actors.lock_service_identity(service_identity.value)
        await self._actors.lock_external_identity(issuer, subject)
        return await self.find_conflict(
            service_identity=service_identity,
            issuer=issuer,
            subject=subject,
        )

    async def find_conflict(
        self,
        *,
        service_identity: ServiceIdentity,
        issuer: str,
        subject: str,
    ) -> ServiceActorConflict | None:
        """Return fixed-identity occupancy before external-identity occupancy."""
        if await self._actors.get_service_actor(service_identity.value) is not None:
            return ServiceActorConflict.SERVICE_IDENTITY
        if await self._actors.get_identity_link(issuer, subject) is not None:
            return ServiceActorConflict.EXTERNAL_IDENTITY
        return None

    async def complete(
        self,
        *,
        claim: AuthorityClaimHandle,
        request: ServiceActorCreateRequest,
        decision: AuthorizationDecision,
        actor_profile_id: UUID,
        issuer: str,
        subject: str,
        reason: str,
    ) -> ServiceActorProvisionResponse:
        """Create one service profile/link and complete its exact evidence chain."""
        if not _decision_matches(decision, request):
            raise TypeError("service provisioning requires exact matched authority")
        if request.identity_reference_digest != derive_service_identity_digest(issuer, subject):
            raise TypeError("service provisioning identity digest changed")
        if request.reason_digest != derive_reason_digest(reason):
            raise TypeError("service provisioning reason digest changed")

        profile = await self._actors.add_actor_profile(
            ActorProfile(
                id=str(uuid4()),
                actor_kind="service",
                status="active",
                provisioning_method="manual_service_provisioning",
                service_identity=request.service_identity.value,
                display_name=None,
                contact_email=None,
                created_by=str(actor_profile_id),
                last_seen_at=None,
            )
        )
        link = await self._actors.add_identity_link(
            ActorIdentityLink(
                id=str(uuid4()),
                actor_profile_id=profile.id,
                issuer=issuer,
                subject=subject,
                subject_kind="service",
                status="active",
                linked_by=str(actor_profile_id),
                last_verified_at=None,
            )
        )
        response = AuthorityResponseReference(
            resource_type=AuthorityResourceType.ACTOR_PROFILE,
            resource_id=UUID(profile.id),
            version=None,
            http_status=201,
        )
        await self._mutation.complete(
            claim=claim,
            request=request.model_dump(),
            response=response,
            success=AuthorityAuditEventInput(
                event_id=uuid4(),
                event_type=AuthorityEventType.SERVICE_ACTOR_PROVISIONED,
                entity_type="actor_profile",
                entity_id=profile.id,
                actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                actor_ref=str(actor_profile_id),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
                matched_grant_id=str(decision.matched_grant_id),
                permission_id=PermissionId.ACTOR_SERVICE_PROVISION,
                resource_type="actor_profile",
                resource_id=profile.id,
                target_ref_kind="actor_profile",
                target_ref_id=profile.id,
                reason="manual_service_provisioning",
                idempotency_reference=claim.record_id,
                after_facts={
                    "status": "active",
                    "subject_kind": "service",
                    "provisioning_method": "manual_service_provisioning",
                },
            ),
            invalidation=AuthorityInvalidationContext(
                event_id=uuid4(),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
            ),
        )
        return _response(profile, link)

    async def replay_response(
        self,
        *,
        response: AuthorityResponseReference,
        request: ServiceActorCreateRequest,
        issuer: str,
        subject: str,
    ) -> ServiceActorProvisionResponse:
        """Rebuild a committed response only from the exact immutable binding."""
        if response.resource_type is not AuthorityResourceType.ACTOR_PROFILE:
            raise TypeError("service provisioning replay resource changed")
        profile = await self._actors.get_actor_profile(str(response.resource_id))
        if (
            profile is None
            or profile.actor_kind != "service"
            or profile.status != "active"
            or profile.service_identity != request.service_identity.value
        ):
            raise ServiceActorProvisioningUnavailable(
                "committed service actor is unavailable"
            )
        link = await self._actors.get_identity_link_for_actor(profile.id)
        if (
            link is None
            or link.issuer != issuer
            or link.subject != subject
            or link.subject_kind != "service"
            or link.status != "active"
        ):
            raise ServiceActorProvisioningUnavailable(
                "committed service identity link is unavailable"
            )
        return _response(profile, link)

    async def record_mismatch(
        self,
        *,
        actor_profile_id: UUID,
        request: ServiceActorCreateRequest,
        decision: AuthorizationDecision,
    ) -> None:
        """Record one action-bound idempotency mismatch after rollback."""
        if not _decision_matches(decision, request):
            raise TypeError("service mismatch requires exact matched authority")
        await self._mutation.record_mismatch_denial(
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=str(actor_profile_id),
            request=request.model_dump(),
            context=AuthorityMismatchContext(
                event_id=uuid4(),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
                matched_grant_id=decision.matched_grant_id,
            ),
        )

    async def record_conflict(
        self,
        *,
        actor_profile_id: UUID,
        request: ServiceActorCreateRequest,
        decision: AuthorizationDecision,
    ) -> None:
        """Record one privacy-bounded identity occupancy denial after rollback."""
        if not _decision_matches(decision, request):
            raise TypeError("service conflict requires exact matched authority")
        event_id = uuid4()
        await self._audit.add_authority_event(
            AuthorityAuditEventInput(
                event_id=event_id,
                event_type=AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
                entity_type="authorization_decision",
                entity_id=str(event_id),
                actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                actor_ref=str(actor_profile_id),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
                matched_grant_id=str(decision.matched_grant_id),
                permission_id=PermissionId.ACTOR_SERVICE_PROVISION,
                action_id=ActionId.ACTOR_SERVICE_PROVISION,
                reason="authorization_evaluation",
                denial_code="identity_link_conflict",
                after_facts={"allowed": False},
            )
        )


def _decision_matches(
    decision: AuthorizationDecision,
    request: ServiceActorCreateRequest,
) -> bool:
    return (
        decision.allowed
        and decision.revalidated
        and decision.matched_authority_kind is MatchedAuthorityKind.ADMIN_ROLE_GRANT
        and decision.action_id is ActionId.ACTOR_SERVICE_PROVISION
        and decision.permission_id is PermissionId.ACTOR_SERVICE_PROVISION
        and decision.resource_type == "service_actor_provisioning"
        and decision.resource_id == request.service_identity
        and decision.resource_context_digest
        == authorization_resource_digest(
            ServiceActorProvisionResourceContext(
                resource_type="service_actor_provisioning",
                resource_id=request.service_identity,
            )
        )
        and decision.matched_grant_id is not None
        and decision.matched_scope_project_id is None
    )


def _response(
    profile: ActorProfile,
    link: ActorIdentityLink,
) -> ServiceActorProvisionResponse:
    if profile.created_at is None or link.linked_at is None or profile.service_identity is None:
        raise RuntimeError("service actor creation facts are incomplete")
    return ServiceActorProvisionResponse(
        actor_profile_id=UUID(profile.id),
        service_identity=ServiceIdentity(profile.service_identity),
        actor_status="active",
        identity_link_status="active",
        provisioning_method="manual_service_provisioning",
        created_at=profile.created_at,
        linked_at=link.linked_at,
    )
