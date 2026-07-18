"""Typed orchestration for authority mutation replay and invalidation evidence."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.audit.schemas import (
    ActorReferenceKind,
    AuthorityAuditEventInput,
    AuthorityEventType,
)
from app.modules.audit.service import AuditService
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.repository import AuthorityIdempotencyRepository
from app.modules.authorization.schemas import (
    ActorIdentityLinkReactivateRequest,
    ActorIdentityLinkRevokeRequest,
    ActorProfileDeactivateRequest,
    ActorProfileReactivateRequest,
    ActorProfileSuspendRequest,
    AdminRoleGrantIssueRequest,
    AdminRoleGrantRevokeRequest,
    AuthorityClaimHandle,
    AuthorityCompletionResult,
    AuthorityInvalidationContext,
    AuthorityMismatchContext,
    AuthorityMutationRequest,
    AuthorityOperation,
    AuthorityReservationResult,
    AuthorityResourceType,
    AuthorityResponseReference,
    ProjectRoleGrantIssueRequest,
    ProjectRoleGrantRevokeRequest,
    ServiceActorCreateRequest,
    parse_authority_request,
)


@dataclass(frozen=True)
class _OperationEvidence:
    """Closed success and invalidation evidence mapping for one operation."""

    permission: str
    action: ActionId | None
    resource_type: AuthorityResourceType
    http_status: int
    events: tuple[AuthorityEventType, ...]


_EVIDENCE = {
    AuthorityOperation.SERVICE_ACTOR_CREATE: _OperationEvidence(
        "actor.service.provision",
        ActionId.ACTOR_SERVICE_PROVISION,
        AuthorityResourceType.ACTOR_PROFILE,
        201,
        (AuthorityEventType.SERVICE_ACTOR_PROVISIONED,),
    ),
    AuthorityOperation.ADMIN_ROLE_GRANT_ISSUE: _OperationEvidence(
        "admin_role.grant",
        ActionId.ADMIN_ROLE_GRANT_ISSUE,
        AuthorityResourceType.ADMIN_ROLE_GRANT,
        201,
        (AuthorityEventType.ADMIN_ROLE_GRANT_ISSUED,),
    ),
    AuthorityOperation.ADMIN_ROLE_GRANT_REVOKE: _OperationEvidence(
        "admin_role.revoke",
        ActionId.ADMIN_ROLE_GRANT_REVOKE,
        AuthorityResourceType.ADMIN_ROLE_GRANT,
        200,
        (AuthorityEventType.ADMIN_ROLE_GRANT_REVOKED,),
    ),
    AuthorityOperation.PROJECT_ROLE_GRANT_ISSUE: _OperationEvidence(
        "project.role_grant.manage",
        None,
        AuthorityResourceType.PROJECT_ROLE_GRANT,
        201,
        (
            AuthorityEventType.PROJECT_ROLE_GRANT_ISSUED,
            AuthorityEventType.PROJECT_ROLE_GRANT_REPLACED,
        ),
    ),
    AuthorityOperation.PROJECT_ROLE_GRANT_REVOKE: _OperationEvidence(
        "project.role_grant.manage",
        None,
        AuthorityResourceType.PROJECT_ROLE_GRANT,
        200,
        (AuthorityEventType.PROJECT_ROLE_GRANT_REVOKED,),
    ),
    AuthorityOperation.ACTOR_PROFILE_SUSPEND: _OperationEvidence(
        "actor.profile.suspend",
        ActionId.ACTOR_PROFILE_SUSPEND,
        AuthorityResourceType.ACTOR_PROFILE,
        200,
        (AuthorityEventType.ACTOR_PROFILE_SUSPENDED,),
    ),
    AuthorityOperation.ACTOR_PROFILE_REACTIVATE: _OperationEvidence(
        "actor.profile.reactivate",
        ActionId.ACTOR_PROFILE_REACTIVATE,
        AuthorityResourceType.ACTOR_PROFILE,
        200,
        (AuthorityEventType.ACTOR_PROFILE_REACTIVATED,),
    ),
    AuthorityOperation.ACTOR_PROFILE_DEACTIVATE: _OperationEvidence(
        "actor.profile.deactivate",
        ActionId.ACTOR_PROFILE_DEACTIVATE,
        AuthorityResourceType.ACTOR_PROFILE,
        200,
        (AuthorityEventType.ACTOR_PROFILE_DEACTIVATED,),
    ),
    AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE: _OperationEvidence(
        "actor.identity_link.revoke",
        None,
        AuthorityResourceType.ACTOR_IDENTITY_LINK,
        200,
        (AuthorityEventType.ACTOR_IDENTITY_LINK_REVOKED,),
    ),
    AuthorityOperation.ACTOR_IDENTITY_LINK_REACTIVATE: _OperationEvidence(
        "actor.identity_link.reactivate",
        None,
        AuthorityResourceType.ACTOR_IDENTITY_LINK,
        200,
        (AuthorityEventType.ACTOR_IDENTITY_LINK_REACTIVATED,),
    ),
}


def _canonical_actor(kind: ActorReferenceKind, reference: str) -> bool:
    """Accept only the shared canonical actor-reference forms."""

    if kind == ActorReferenceKind.SYSTEM_PRINCIPAL:
        return reference == "workstream:system:bootstrap"
    try:
        return str(UUID(reference)) == reference
    except (ValueError, AttributeError):
        return False


class AuthorityMutationService:
    """Coordinate idempotency and shared audit writes in one caller transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind idempotency and audit writers to one caller transaction."""

        self._repository = AuthorityIdempotencyRepository(session)
        self._audit = AuditService(session)

    async def reserve(
        self,
        *,
        idempotency_key: UUID,
        actor_ref_kind: ActorReferenceKind,
        actor_ref: str,
        request: object,
    ) -> AuthorityReservationResult:
        """Validate, hash, and reserve before any caller business-state flush."""
        mutation = parse_authority_request(request)
        if not _canonical_actor(actor_ref_kind, actor_ref):
            raise TypeError("invalid authority reservation input")
        digest = canonical_json_hash(mutation.model_dump(mode="json", exclude_none=True))
        return await self._repository.reserve(
            idempotency_key=idempotency_key,
            actor_ref_kind=actor_ref_kind,
            actor_ref=actor_ref,
            operation=mutation.operation,
            request_digest=digest,
        )

    async def complete(
        self,
        *,
        claim: AuthorityClaimHandle,
        request: object,
        response: AuthorityResponseReference,
        success: AuthorityAuditEventInput,
        invalidation: AuthorityInvalidationContext,
    ) -> AuthorityCompletionResult:
        """Flush one mapped success/invalidation pair, then complete its claim."""
        mutation = parse_authority_request(request)
        spec = _EVIDENCE[claim.operation]
        expected_digest = canonical_json_hash(mutation.model_dump(mode="json", exclude_none=True))
        allowed_events = spec.events
        if isinstance(mutation, ProjectRoleGrantIssueRequest):
            allowed_events = (
                AuthorityEventType.PROJECT_ROLE_GRANT_REPLACED
                if mutation.replaced_grant_id
                else AuthorityEventType.PROJECT_ROLE_GRANT_ISSUED,
            )
        valid = (
            mutation.operation == claim.operation
            and expected_digest == claim.request_digest
            and success.event_type in allowed_events
            and success.actor_ref_kind == claim.actor_ref_kind
            and success.actor_ref == claim.actor_ref
            and success.idempotency_reference == claim.record_id
            and success.permission_id == spec.permission
            and success.entity_type == spec.resource_type.value
            and success.entity_id == str(response.resource_id)
            and success.resource_type == spec.resource_type.value
            and success.resource_id == str(response.resource_id)
            and success.target_ref_kind == spec.resource_type.value
            and success.target_ref_id == str(response.resource_id)
            and response.resource_type == spec.resource_type
            and response.http_status == spec.http_status
            and _request_matches_success(mutation, response, success)
            and success.request_id == invalidation.request_id
            and success.correlation_id == invalidation.correlation_id
        )
        if not valid:
            raise TypeError("invalid authority completion input")
        stored_success = await self._audit.add_authority_event(success)
        admin_mutation = isinstance(
            mutation,
            (AdminRoleGrantIssueRequest, AdminRoleGrantRevokeRequest),
        )
        identity_link_mutation = isinstance(
            mutation,
            (ActorIdentityLinkRevokeRequest, ActorIdentityLinkReactivateRequest),
        )
        invalidation_target_kind = spec.resource_type.value
        invalidation_target_ref = success.resource_id
        invalidation_resource_type = success.resource_type
        invalidation_resource_id = success.resource_id
        before_facts = {"effective": True}
        after_facts = {"effective": False}
        if admin_mutation or identity_link_mutation:
            if success.target_actor_ref is None:
                raise TypeError("projected authority success requires target actor")
            invalidation_target_kind = AuthorityResourceType.ACTOR_PROFILE.value
            invalidation_target_ref = success.target_actor_ref
            invalidation_resource_type = AuthorityResourceType.ACTOR_PROFILE.value
            invalidation_resource_id = success.target_actor_ref
            if isinstance(
                mutation,
                (AdminRoleGrantIssueRequest, ActorIdentityLinkReactivateRequest),
            ):
                before_facts = {"effective": False}
                after_facts = {"effective": True}
        elif isinstance(mutation, ActorProfileReactivateRequest):
            before_facts = {"effective": False}
            after_facts = {"effective": True}
        invalidation_input = AuthorityAuditEventInput(
            event_id=invalidation.event_id,
            event_type=AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED,
            entity_type="authority_invalidation",
            entity_id=str(invalidation.event_id),
            actor_ref_kind=claim.actor_ref_kind,
            actor_ref=claim.actor_ref,
            request_id=invalidation.request_id,
            correlation_id=invalidation.correlation_id,
            permission_id=spec.permission,
            project_id=success.project_id,
            resource_type=invalidation_resource_type,
            resource_id=invalidation_resource_id,
            reason="authority_state_changed",
            idempotency_reference=claim.record_id,
            invalidation_cause_event_id=UUID(stored_success.id),
            invalidation_target_kind=invalidation_target_kind,
            invalidation_target_ref=invalidation_target_ref,
            before_facts=before_facts,
            after_facts=after_facts,
        )
        await self._audit.add_authority_event(invalidation_input)
        await self._repository.complete(claim, response)
        return AuthorityCompletionResult(
            response=response,
            success_event_id=success.event_id,
            invalidation_event_id=invalidation.event_id,
        )

    async def record_mismatch_denial(
        self,
        *,
        actor_ref_kind: ActorReferenceKind,
        actor_ref: str,
        request: object,
        context: AuthorityMismatchContext,
    ) -> UUID:
        """Append privacy-safe mismatch evidence in a caller-started clean transaction."""
        mutation: AuthorityMutationRequest = parse_authority_request(request)
        spec = _EVIDENCE[mutation.operation]
        resource_id = _existing_request_resource_id(mutation)
        event = AuthorityAuditEventInput(
            event_id=context.event_id,
            event_type=AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
            entity_type="authorization_decision",
            entity_id=str(context.event_id),
            actor_ref_kind=actor_ref_kind,
            actor_ref=actor_ref,
            request_id=context.request_id,
            correlation_id=context.correlation_id,
            matched_grant_id=(
                str(context.matched_grant_id) if context.matched_grant_id else None
            ),
            permission_id=spec.permission,
            action_id=spec.action,
            project_id=_request_project_id(mutation),
            resource_type=spec.resource_type.value if resource_id else None,
            resource_id=str(resource_id) if resource_id else None,
            reason="authorization_evaluation",
            denial_code="idempotency_mismatch",
            after_facts={"allowed": False},
        )
        await self._audit.add_authority_event(event)
        return context.event_id


def _existing_request_resource_id(request: AuthorityMutationRequest) -> UUID | None:
    """Return an existing mutated resource; issue/create operations return none."""
    for field in ("grant_id", "actor_profile_id", "identity_link_id"):
        value = getattr(request, field, None)
        if value is not None:
            return value
    return None


def _request_project_id(request: AuthorityMutationRequest) -> str | None:
    """Derive project audit scope only from the canonical request."""
    if isinstance(request, AdminRoleGrantIssueRequest):
        project_id = request.scope_project_id
    else:
        project_id = getattr(request, "project_id", None)
    return str(project_id) if project_id is not None else None


def _request_matches_success(
    request: AuthorityMutationRequest,
    response: AuthorityResponseReference,
    success: AuthorityAuditEventInput,
) -> bool:
    """Bind the canonical request target and scope to its concrete success evidence."""
    resource_id = response.resource_id
    if isinstance(request, ServiceActorCreateRequest):
        return success.project_id is None and success.target_actor_ref is None
    if isinstance(request, AdminRoleGrantIssueRequest):
        facts = success.after_facts or {}
        return (
            success.target_actor_ref_kind == ActorReferenceKind.ACTOR_PROFILE
            and success.target_actor_ref == str(request.target_actor_id)
            and success.project_id
            == (str(request.scope_project_id) if request.scope_project_id else None)
            and success.matched_grant_id is not None
            and facts.get("role") == request.role.value
            and facts.get("scope_type") == request.scope_type.value
            and facts.get("scope_id")
            == (str(request.scope_project_id) if request.scope_project_id else None)
        )
    if isinstance(request, AdminRoleGrantRevokeRequest):
        return (
            resource_id == request.grant_id
            and success.target_actor_ref_kind == ActorReferenceKind.ACTOR_PROFILE
            and success.target_actor_ref is not None
            and success.matched_grant_id is not None
        )
    if isinstance(request, ProjectRoleGrantIssueRequest):
        facts = success.after_facts or {}
        return (
            success.target_actor_ref_kind == ActorReferenceKind.ACTOR_PROFILE
            and success.target_actor_ref == str(request.target_actor_id)
            and success.project_id == str(request.project_id)
            and success.matched_grant_id
            == (str(request.replaced_grant_id) if request.replaced_grant_id else None)
            and facts.get("role") == request.role.value
            and facts.get("scope_type") == "project"
            and facts.get("scope_id") == str(request.project_id)
        )
    if isinstance(request, ProjectRoleGrantRevokeRequest):
        return resource_id == request.grant_id and success.project_id == str(request.project_id)
    if isinstance(
        request,
        (ActorProfileSuspendRequest, ActorProfileReactivateRequest, ActorProfileDeactivateRequest),
    ):
        return resource_id == request.actor_profile_id and success.project_id is None
    if isinstance(request, (ActorIdentityLinkRevokeRequest, ActorIdentityLinkReactivateRequest)):
        return (
            resource_id == request.identity_link_id
            and success.project_id is None
            and success.target_actor_ref_kind == ActorReferenceKind.ACTOR_PROFILE
            and success.target_actor_ref is not None
        )
    return False
