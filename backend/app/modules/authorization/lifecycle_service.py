"""Actor-profile lifecycle orchestration on the shared authority foundation."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.models import ActorProfile
from app.modules.audit.schemas import (
    ActorReferenceKind,
    AuthorityAuditEventInput,
    AuthorityEventType,
)
from app.modules.audit.service import AuditService
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.lifecycle_schemas import ActorLifecycleMutationResponse
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorProfileLifecycleResourceContext,
    AuthorizationDecision,
    MatchedAuthorityKind,
    authorization_resource_digest,
)
from app.modules.authorization.schemas import (
    ActorProfileDeactivateRequest,
    ActorProfileReactivateRequest,
    ActorProfileSuspendRequest,
    AuthorityClaimHandle,
    AuthorityInvalidationContext,
    AuthorityMismatchContext,
    AuthorityOperation,
    AuthorityReservationResult,
    AuthorityResourceType,
    AuthorityResponseReference,
    derive_reason_digest,
)
from app.modules.authorization.service import AuthorityMutationService

ActorLifecycleRequest = (
    ActorProfileSuspendRequest
    | ActorProfileReactivateRequest
    | ActorProfileDeactivateRequest
)


class ActorLifecycleConflict(RuntimeError):
    """One exact target-state or final-administrator conflict."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_ACTION = {
    AuthorityOperation.ACTOR_PROFILE_SUSPEND: ActionId.ACTOR_PROFILE_SUSPEND,
    AuthorityOperation.ACTOR_PROFILE_REACTIVATE: ActionId.ACTOR_PROFILE_REACTIVATE,
    AuthorityOperation.ACTOR_PROFILE_DEACTIVATE: ActionId.ACTOR_PROFILE_DEACTIVATE,
}
_PERMISSION = {
    AuthorityOperation.ACTOR_PROFILE_SUSPEND: PermissionId.ACTOR_PROFILE_SUSPEND,
    AuthorityOperation.ACTOR_PROFILE_REACTIVATE: PermissionId.ACTOR_PROFILE_REACTIVATE,
    AuthorityOperation.ACTOR_PROFILE_DEACTIVATE: PermissionId.ACTOR_PROFILE_DEACTIVATE,
}
_TRANSITION = {
    AuthorityOperation.ACTOR_PROFILE_SUSPEND: "suspend",
    AuthorityOperation.ACTOR_PROFILE_REACTIVATE: "reactivate",
    AuthorityOperation.ACTOR_PROFILE_DEACTIVATE: "deactivate",
}
_EVENT = {
    AuthorityOperation.ACTOR_PROFILE_SUSPEND: AuthorityEventType.ACTOR_PROFILE_SUSPENDED,
    AuthorityOperation.ACTOR_PROFILE_REACTIVATE: AuthorityEventType.ACTOR_PROFILE_REACTIVATED,
    AuthorityOperation.ACTOR_PROFILE_DEACTIVATE: AuthorityEventType.ACTOR_PROFILE_DEACTIVATED,
}


class ActorLifecycleService:
    """Stage one profile transition and its exact evidence in the caller transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = AdminAuthorizationRepository(session)
        self._mutation = AuthorityMutationService(session)
        self._audit = AuditService(session)

    async def reserve(
        self,
        *,
        idempotency_key: UUID,
        actor_profile_id: UUID,
        request: ActorLifecycleRequest,
    ) -> AuthorityReservationResult:
        """Reserve one caller/operation/key namespace before authorization."""
        return await self._mutation.reserve(
            idempotency_key=idempotency_key,
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=str(actor_profile_id),
            request=request.model_dump(),
        )

    async def complete(
        self,
        *,
        claim: AuthorityClaimHandle,
        request: ActorLifecycleRequest,
        decision: AuthorizationDecision,
        actor_profile_id: UUID,
        reason: str,
    ) -> ActorLifecycleMutationResponse:
        """Apply one valid transition and complete success/invalidation evidence."""
        if not _decision_matches(decision, request, existing=False):
            raise TypeError("actor lifecycle mutation requires exact matched authority")
        if request.reason_digest != derive_reason_digest(reason):
            raise TypeError("actor lifecycle reason digest changed")
        locked = await self._repository.lock_actor_lifecycle_target(request.actor_profile_id)
        if locked is None:
            raise RuntimeError("authorized actor lifecycle target disappeared")
        link, profile, access_grant = locked
        conflict = await self._conflict(request, profile, link.status, access_grant is not None)
        if conflict is not None:
            raise ActorLifecycleConflict(conflict)

        before_status = profile.status
        self._apply(profile, request, actor_profile_id, reason)
        await self._session.flush()
        response = AuthorityResponseReference(
            resource_type=AuthorityResourceType.ACTOR_PROFILE,
            resource_id=request.actor_profile_id,
            version=None,
            http_status=200,
        )
        await self._mutation.complete(
            claim=claim,
            request=request.model_dump(),
            response=response,
            success=AuthorityAuditEventInput(
                event_id=uuid4(),
                event_type=_EVENT[request.operation],
                entity_type="actor_profile",
                entity_id=str(request.actor_profile_id),
                actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                actor_ref=str(actor_profile_id),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
                target_actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                target_actor_ref=str(request.actor_profile_id),
                matched_grant_id=str(decision.matched_grant_id),
                permission_id=_PERMISSION[request.operation],
                resource_type="actor_profile",
                resource_id=str(request.actor_profile_id),
                target_ref_kind="actor_profile",
                target_ref_id=str(request.actor_profile_id),
                reason="administrative_correction",
                idempotency_reference=claim.record_id,
                before_facts={"status": before_status},
                after_facts={"status": profile.status},
            ),
            invalidation=AuthorityInvalidationContext(
                event_id=uuid4(),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
            ),
        )
        return ActorLifecycleMutationResponse(
            resource_type="actor_profile",
            resource_id=response.resource_id,
            version=None,
            http_status=200,
        )

    async def record_mismatch(
        self,
        *,
        actor_profile_id: UUID,
        request: ActorLifecycleRequest,
        decision: AuthorizationDecision,
    ) -> None:
        """Write one action-bound mismatch after rolling back the reservation."""
        if not _decision_matches(decision, request, existing=True):
            raise TypeError("actor lifecycle mismatch requires exact authority")
        await self._mutation.record_mismatch_denial(
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=str(actor_profile_id),
            request=request.model_dump(),
            context=AuthorityMismatchContext(
                event_id=uuid4(),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
                matched_grant_id=None,
            ),
        )

    async def record_conflict(
        self,
        *,
        actor_profile_id: UUID,
        request: ActorLifecycleRequest,
        decision: AuthorizationDecision,
        code: str,
    ) -> None:
        """Write one clean post-allow lifecycle denial without consuming the key."""
        if not _decision_matches(decision, request, existing=False):
            raise TypeError("actor lifecycle conflict requires exact authority")
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
                target_actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                target_actor_ref=str(request.actor_profile_id),
                matched_grant_id=None,
                permission_id=_PERMISSION[request.operation],
                action_id=_ACTION[request.operation],
                resource_type="actor_profile",
                resource_id=str(request.actor_profile_id),
                target_ref_kind="actor_profile",
                target_ref_id=str(request.actor_profile_id),
                reason="authorization_evaluation",
                denial_code=code,
                after_facts={"allowed": False},
            )
        )

    async def _conflict(
        self,
        request: ActorLifecycleRequest,
        profile: ActorProfile,
        link_status: str,
        has_access_grant: bool,
    ) -> str | None:
        status = profile.status
        if status == "deactivated":
            return "actor_deactivated_terminal"
        if request.operation is AuthorityOperation.ACTOR_PROFILE_SUSPEND and status == "suspended":
            return "actor_already_suspended"
        if request.operation is AuthorityOperation.ACTOR_PROFILE_REACTIVATE and status != "suspended":
            return "actor_not_suspended"
        loses_effective_admin = (
            request.operation
            in {
                AuthorityOperation.ACTOR_PROFILE_SUSPEND,
                AuthorityOperation.ACTOR_PROFILE_DEACTIVATE,
            }
            and profile.actor_kind == "human"
            and status == "active"
            and link_status == "active"
            and has_access_grant
        )
        if (
            loses_effective_admin
            and await self._repository.count_effective_access_administrators() <= 1
        ):
            return "last_access_administrator"
        return None

    @staticmethod
    def _apply(
        profile: ActorProfile,
        request: ActorLifecycleRequest,
        actor_profile_id: UUID,
        reason: str,
    ) -> None:
        actor_id = str(actor_profile_id)
        if request.operation is AuthorityOperation.ACTOR_PROFILE_SUSPEND:
            profile.status = "suspended"
            profile.suspended_by = actor_id
            profile.suspended_at = func.clock_timestamp()
            profile.suspension_reason = reason
        elif request.operation is AuthorityOperation.ACTOR_PROFILE_REACTIVATE:
            profile.status = "active"
            profile.suspended_by = None
            profile.suspended_at = None
            profile.suspension_reason = None
            profile.reactivated_by = actor_id
            profile.reactivated_at = func.clock_timestamp()
            profile.reactivation_reason = reason
        else:
            profile.status = "deactivated"
            profile.deactivated_by = actor_id
            profile.deactivated_at = func.clock_timestamp()
            profile.deactivation_reason = reason


def _decision_matches(
    decision: AuthorizationDecision,
    request: ActorLifecycleRequest,
    *,
    existing: bool,
) -> bool:
    resource = ActorProfileLifecycleResourceContext(
        resource_type="actor_profile",
        resource_id=request.actor_profile_id,
        transition=_TRANSITION[request.operation],
        existing_idempotency_record=existing,
    )
    return (
        decision.allowed
        and decision.action_id is _ACTION[request.operation]
        and decision.permission_id is _PERMISSION[request.operation]
        and decision.resource_type == "actor_profile"
        and decision.resource_id == request.actor_profile_id
        and decision.resource_context_digest == authorization_resource_digest(resource)
        and decision.matched_authority_kind is MatchedAuthorityKind.ADMIN_ROLE_GRANT
        and decision.matched_grant_id is not None
        and decision.matched_scope_project_id is None
        and decision.revalidated
    )
