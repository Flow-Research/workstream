"""Administrative grant orchestration on the shared authorization foundation."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
import json
from uuid import UUID, uuid4

from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.schemas import (
    ActorReferenceKind,
    AuthorityAuditEventInput,
    AuthorityEventType,
)
from app.modules.audit.service import AuditService
from app.modules.authorization.admin_schemas import (
    AdminRoleDefinitionResponse,
    AdminRoleDefinitionsResponse,
    AdminRoleGrantCollectionResponse,
    AdminRoleGrantResponse,
    AuthorityMutationResponse,
    PermissionDefinitionResponse,
    PermissionDefinitionsResponse,
)
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.models import AdminRoleGrant, AuthorityControl
from app.modules.authorization.policy import permissions_for, scopes_for
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    AdminRoleGrantIssueResourceContext,
    AdminRoleGrantResourceContext,
    MatchedAuthorityKind,
    AuthorizationDecision,
    authorization_resource_digest,
)
from app.modules.authorization.schemas import (
    AdminRole,
    AdminRoleGrantIssueRequest,
    AdminRoleGrantRevokeRequest,
    AdminScope,
    AuthorityClaimHandle,
    AuthorityInvalidationContext,
    AuthorityMismatchContext,
    AuthorityReservationResult,
    AuthorityResourceType,
    AuthorityResponseReference,
    derive_reason_digest,
)
from app.modules.authorization.service import AuthorityMutationService

BOOTSTRAP_PRINCIPAL = "workstream:system:bootstrap"
BOOTSTRAP_REASON = "Initial Access Administrator bootstrap"


class BootstrapAlreadyCompleted(RuntimeError):
    """The irreversible bootstrap transition has already completed."""

    def __init__(self, grant_id: UUID) -> None:
        self.grant_id = grant_id
        super().__init__("bootstrap already completed")


class BootstrapTargetIneligible(RuntimeError):
    """The selected actor cannot receive the bootstrap grant."""


class LastAccessAdministratorConflict(RuntimeError):
    """Revocation would remove the final effective Access Administrator."""

    def __init__(self, grant_id: UUID, target_actor_profile_id: UUID) -> None:
        self.grant_id = grant_id
        self.target_actor_profile_id = target_actor_profile_id
        super().__init__("final Access Administrator cannot be revoked")


class AdminRoleGrantService:
    """Stage administrative grant reads, mutations, and bounded evidence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = AdminAuthorizationRepository(session)
        self._mutation = AuthorityMutationService(session)
        self._audit = AuditService(session)

    @staticmethod
    def permission_definitions() -> PermissionDefinitionsResponse:
        """Return the complete deterministic permission catalogue."""
        return PermissionDefinitionsResponse(
            items=tuple(
                PermissionDefinitionResponse(permission_id=permission)
                for permission in sorted(PermissionId, key=lambda value: value.value)
            ),
            total=74,
        )

    @staticmethod
    def role_definitions() -> AdminRoleDefinitionsResponse:
        """Return the complete immutable five-role matrix."""
        return AdminRoleDefinitionsResponse(
            items=tuple(
                AdminRoleDefinitionResponse(
                    role=role,
                    allowed_scopes=scopes_for(role),
                    permission_ids=permissions_for(role),
                )
                for role in AdminRole
            ),
            total=5,
        )

    async def reserve(
        self,
        *,
        idempotency_key: UUID,
        actor_profile_id: UUID,
        request: AdminRoleGrantIssueRequest | AdminRoleGrantRevokeRequest,
    ) -> AuthorityReservationResult:
        """Reserve one actor/operation/key namespace before mutation work."""
        return await self._mutation.reserve(
            idempotency_key=idempotency_key,
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=str(actor_profile_id),
            request=request.model_dump(),
        )

    async def complete_issue(
        self,
        *,
        claim: AuthorityClaimHandle,
        request: AdminRoleGrantIssueRequest,
        decision: AuthorizationDecision,
        actor_profile_id: UUID,
        reason: str,
    ) -> AuthorityMutationResponse:
        """Create one grant and atomically complete its shared evidence."""
        if not _issue_decision_matches(decision, request) or request.reason_digest != (
            derive_reason_digest(reason)
        ):
            raise TypeError("grant issuance requires exact matched authority")
        grant = await self._repository.add_grant(
            AdminRoleGrant(
                id=uuid4(),
                target_actor_profile_id=str(request.target_actor_id),
                role=request.role.value,
                scope_type=request.scope_type.value,
                scope_project_id=(
                    str(request.scope_project_id) if request.scope_project_id else None
                ),
                status="active",
                version=1,
                granted_by_actor_profile_id=str(actor_profile_id),
                granted_by_system_principal=None,
                granted_by_admin_role_grant_id=decision.matched_grant_id,
                grant_reason=reason,
            )
        )
        response = AuthorityResponseReference(
            resource_type=AuthorityResourceType.ADMIN_ROLE_GRANT,
            resource_id=grant.id,
            version=1,
            http_status=201,
        )
        await self._mutation.complete(
            claim=claim,
            request=request.model_dump(),
            response=response,
            success=AuthorityAuditEventInput(
                event_id=uuid4(),
                event_type=AuthorityEventType.ADMIN_ROLE_GRANT_ISSUED,
                entity_type="admin_role_grant",
                entity_id=str(grant.id),
                actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                actor_ref=str(actor_profile_id),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
                target_actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                target_actor_ref=str(request.target_actor_id),
                matched_grant_id=str(decision.matched_grant_id),
                permission_id=PermissionId.ADMIN_ROLE_GRANT,
                project_id=(str(request.scope_project_id) if request.scope_project_id else None),
                resource_type="admin_role_grant",
                resource_id=str(grant.id),
                target_ref_kind="admin_role_grant",
                target_ref_id=str(grant.id),
                reason="authority_assignment",
                idempotency_reference=claim.record_id,
                after_facts=_grant_facts(grant),
            ),
            invalidation=AuthorityInvalidationContext(
                event_id=uuid4(),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
            ),
        )
        return _mutation_response(response)

    async def complete_revoke(
        self,
        *,
        claim: AuthorityClaimHandle,
        request: AdminRoleGrantRevokeRequest,
        decision: AuthorizationDecision,
        actor_profile_id: UUID,
        reason: str,
    ) -> AuthorityMutationResponse:
        """Revoke one locked grant and atomically complete shared evidence."""
        if not _revoke_decision_matches(decision, request) or request.reason_digest != (
            derive_reason_digest(reason)
        ):
            raise TypeError("grant revocation requires exact matched authority")
        conflict = await self.final_access_administrator_conflict(request.grant_id)
        if conflict is not None:
            raise LastAccessAdministratorConflict(
                UUID(str(conflict.id)),
                UUID(str(conflict.target_actor_profile_id)),
            )
        grant = await self._repository.get_grant(request.grant_id, for_update=True)
        if grant is None or grant.status != "active":
            raise RuntimeError("authorized grant disappeared")
        before = _grant_facts(grant)
        grant.status = "revoked"
        grant.version = 2
        grant.revoked_by_actor_profile_id = str(actor_profile_id)
        grant.revoked_by_admin_role_grant_id = decision.matched_grant_id
        grant.revoked_reason = reason
        grant.revoked_at = func.clock_timestamp()
        await self._session.flush()
        await self._session.refresh(grant)
        response = AuthorityResponseReference(
            resource_type=AuthorityResourceType.ADMIN_ROLE_GRANT,
            resource_id=grant.id,
            version=2,
            http_status=200,
        )
        await self._mutation.complete(
            claim=claim,
            request=request.model_dump(),
            response=response,
            success=AuthorityAuditEventInput(
                event_id=uuid4(),
                event_type=AuthorityEventType.ADMIN_ROLE_GRANT_REVOKED,
                entity_type="admin_role_grant",
                entity_id=str(grant.id),
                actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                actor_ref=str(actor_profile_id),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
                target_actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                target_actor_ref=grant.target_actor_profile_id,
                matched_grant_id=str(decision.matched_grant_id),
                permission_id=PermissionId.ADMIN_ROLE_REVOKE,
                project_id=grant.scope_project_id,
                resource_type="admin_role_grant",
                resource_id=str(grant.id),
                target_ref_kind="admin_role_grant",
                target_ref_id=str(grant.id),
                reason="authority_revocation",
                idempotency_reference=claim.record_id,
                before_facts=before,
                after_facts=_grant_facts(grant),
            ),
            invalidation=AuthorityInvalidationContext(
                event_id=uuid4(),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
            ),
        )
        return _mutation_response(response)

    async def find_active_duplicate(
        self,
        request: AdminRoleGrantIssueRequest,
    ) -> AdminRoleGrant | None:
        """Return an exact active duplicate after the caller has been authorized."""
        return await self._repository.find_active_duplicate(
            target_actor_profile_id=request.target_actor_id,
            role=request.role,
            scope_type=request.scope_type,
            scope_project_id=request.scope_project_id,
        )

    async def final_access_administrator_conflict(
        self,
        grant_id: UUID,
    ) -> AdminRoleGrant | None:
        """Return the locked grant only when revocation would remove final access."""
        grant = await self._repository.get_grant(grant_id, for_update=True)
        if grant is None or grant.status != "active":
            return None
        if (
            grant.role == AdminRole.ACCESS_ADMINISTRATOR.value
            and grant.scope_type == AdminScope.SYSTEM.value
            and await self._repository.lock_eligible_human(UUID(grant.target_actor_profile_id))
            is not None
            and await self._repository.count_effective_access_administrators() <= 1
        ):
            return grant
        return None

    async def record_mismatch(
        self,
        *,
        actor_profile_id: UUID,
        request: AdminRoleGrantIssueRequest | AdminRoleGrantRevokeRequest,
        decision: AuthorizationDecision,
    ) -> None:
        """Record the existing action-bound mismatch denial in a clean transaction."""
        valid_decision = (
            _issue_decision_matches(decision, request)
            if isinstance(request, AdminRoleGrantIssueRequest)
            else _revoke_decision_matches(
                decision,
                request,
                existing_idempotency_record=True,
            )
        )
        if not valid_decision:
            raise TypeError("idempotency mismatch requires exact matched authority")
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

    async def record_issue_conflict(
        self,
        *,
        actor_profile_id: UUID,
        request: AdminRoleGrantIssueRequest,
        grant_id: UUID,
        decision: AuthorizationDecision,
    ) -> None:
        """Record one duplicate-issue domain denial after rollback."""
        if not _issue_decision_matches(decision, request):
            raise TypeError("grant issue conflict requires exact matched authority")
        await self._audit.add_authority_event(
            AuthorityAuditEventInput(
                event_id=uuid4(),
                event_type=AuthorityEventType.ADMIN_ROLE_GRANT_ISSUE_DENIED,
                entity_type="admin_role_grant",
                entity_id=str(grant_id),
                actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                actor_ref=str(actor_profile_id),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
                target_actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                target_actor_ref=str(request.target_actor_id),
                matched_grant_id=str(decision.matched_grant_id),
                project_id=(str(request.scope_project_id) if request.scope_project_id else None),
                resource_type="admin_role_grant",
                resource_id=str(grant_id),
                target_ref_kind="admin_role_grant",
                target_ref_id=str(grant_id),
                reason="authorization_policy_denial",
                denial_code="admin_role_grant_exists",
            )
        )

    async def record_last_admin_denial(
        self,
        *,
        actor_profile_id: UUID,
        grant_id: UUID,
        target_actor_profile_id: UUID,
        decision: AuthorizationDecision,
    ) -> None:
        """Record one final-administrator domain denial after rollback."""
        if not _revoke_decision_matches_grant(decision, grant_id):
            raise TypeError("final administrator denial requires exact matched authority")
        await self._audit.add_authority_event(
            AuthorityAuditEventInput(
                event_id=uuid4(),
                event_type=AuthorityEventType.LAST_ACCESS_ADMIN_OPERATION_DENIED,
                entity_type="admin_role_grant",
                entity_id=str(grant_id),
                actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                actor_ref=str(actor_profile_id),
                request_id=decision.request_id,
                correlation_id=decision.correlation_id,
                target_actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                target_actor_ref=str(target_actor_profile_id),
                matched_grant_id=str(decision.matched_grant_id),
                resource_type="admin_role_grant",
                resource_id=str(grant_id),
                target_ref_kind="admin_role_grant",
                target_ref_id=str(grant_id),
                reason="authorization_policy_denial",
                denial_code="last_access_administrator",
            )
        )

    async def list_page(
        self,
        *,
        scope_type: AdminScope,
        scope_project_id: UUID | None,
        target_actor_profile_id: UUID | None,
        status: str,
        limit: int,
        cursor: str | None,
    ) -> AdminRoleGrantCollectionResponse:
        """Return one already-authorized scope-filtered page."""
        decoded = _decode_cursor(cursor) if cursor else None
        rows, total = await self._repository.list_grants(
            scope_type=scope_type,
            scope_project_id=scope_project_id,
            target_actor_profile_id=target_actor_profile_id,
            status=status,
            limit=limit,
            cursor=decoded,
        )
        has_next = len(rows) > limit
        visible = rows[:limit]
        next_cursor = _encode_cursor(visible[-1]) if has_next and visible else None
        return AdminRoleGrantCollectionResponse(
            items=tuple(_grant_response(grant) for grant in visible),
            total=total,
            next_cursor=next_cursor,
        )

    async def active_roles_for_actor(self, actor_profile_id: UUID) -> tuple[str, ...]:
        """Return sorted active role names for the non-authoritative self projection."""
        return await self._repository.active_roles_for_actor(actor_profile_id)

    async def bootstrap_eligible(self, actor_profile_id: UUID) -> bool:
        """Check read-only bootstrap eligibility without promising success."""
        control = await self._session.get(AuthorityControl, 1)
        if control is None:
            raise RuntimeError("authority control is missing")
        if control.bootstrap_completed:
            if control.bootstrap_grant_id is None:
                raise RuntimeError("completed bootstrap is missing its grant")
            raise BootstrapAlreadyCompleted(control.bootstrap_grant_id)
        return await self._repository.get_eligible_human(actor_profile_id) is not None

    async def bootstrap(self, actor_profile_id: UUID) -> UUID:
        """Stage the irreversible first Access Administrator transition."""
        control = await self._repository.lock_control()
        if control.bootstrap_completed:
            if control.bootstrap_grant_id is None:
                raise RuntimeError("completed bootstrap is missing its grant")
            raise BootstrapAlreadyCompleted(control.bootstrap_grant_id)
        if await self._repository.lock_eligible_human(actor_profile_id) is None:
            raise BootstrapTargetIneligible("bootstrap target is not eligible")
        grant = await self._repository.add_grant(
            AdminRoleGrant(
                id=uuid4(),
                target_actor_profile_id=str(actor_profile_id),
                role=AdminRole.ACCESS_ADMINISTRATOR.value,
                scope_type=AdminScope.SYSTEM.value,
                scope_project_id=None,
                status="active",
                version=1,
                granted_by_actor_profile_id=None,
                granted_by_system_principal=BOOTSTRAP_PRINCIPAL,
                granted_by_admin_role_grant_id=None,
                grant_reason=BOOTSTRAP_REASON,
            )
        )
        control.bootstrap_completed = True
        control.bootstrap_grant_id = grant.id
        control.version = 1
        control.updated_at = func.clock_timestamp()
        event_id = uuid4()
        await self._audit.add_authority_event(
            AuthorityAuditEventInput(
                event_id=event_id,
                event_type=AuthorityEventType.INITIAL_ACCESS_ADMIN_BOOTSTRAPPED,
                entity_type="admin_role_grant",
                entity_id=str(grant.id),
                actor_ref_kind=ActorReferenceKind.SYSTEM_PRINCIPAL,
                actor_ref=BOOTSTRAP_PRINCIPAL,
                request_id=uuid4(),
                correlation_id=uuid4(),
                target_actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                target_actor_ref=str(actor_profile_id),
                resource_type="admin_role_grant",
                resource_id=str(grant.id),
                target_ref_kind="admin_role_grant",
                target_ref_id=str(grant.id),
                reason="initial_access_bootstrap",
                after_facts=_grant_facts(grant),
            )
        )
        await self._session.flush()
        return grant.id

    async def record_bootstrap_conflict(
        self,
        *,
        actor_profile_id: UUID,
        grant_id: UUID,
    ) -> None:
        """Record one bounded later/losing bootstrap conflict."""
        await self._audit.add_authority_event(
            AuthorityAuditEventInput(
                event_id=uuid4(),
                event_type=AuthorityEventType.ADMIN_ROLE_GRANT_ISSUE_DENIED,
                entity_type="admin_role_grant",
                entity_id=str(grant_id),
                actor_ref_kind=ActorReferenceKind.SYSTEM_PRINCIPAL,
                actor_ref=BOOTSTRAP_PRINCIPAL,
                request_id=uuid4(),
                correlation_id=uuid4(),
                target_actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                target_actor_ref=str(actor_profile_id),
                resource_type="admin_role_grant",
                resource_id=str(grant_id),
                target_ref_kind="admin_role_grant",
                target_ref_id=str(grant_id),
                reason="authorization_policy_denial",
                denial_code="admin_role_grant_exists",
            )
        )


def _grant_facts(grant: AdminRoleGrant) -> dict[str, str | bool]:
    facts: dict[str, str | bool] = {
        "status": grant.status,
        "role": grant.role,
        "scope_type": grant.scope_type,
        "effective": grant.status == "active",
    }
    if grant.scope_project_id is not None:
        facts["scope_id"] = grant.scope_project_id
    return facts


def _issue_decision_matches(
    decision: AuthorizationDecision,
    request: AdminRoleGrantIssueRequest,
) -> bool:
    return (
        decision.allowed
        and decision.revalidated
        and decision.matched_authority_kind is MatchedAuthorityKind.ADMIN_ROLE_GRANT
        and decision.action_id is ActionId.ADMIN_ROLE_GRANT_ISSUE
        and decision.permission_id is PermissionId.ADMIN_ROLE_GRANT
        and decision.resource_type == "admin_role_grant_issue"
        and decision.resource_id == request.target_actor_id
        and decision.resource_context_digest
        == authorization_resource_digest(
            AdminRoleGrantIssueResourceContext(
                resource_type="admin_role_grant_issue",
                resource_id=request.target_actor_id,
                role=request.role,
                scope_type=request.scope_type,
                scope_project_id=request.scope_project_id,
            )
        )
        and decision.matched_grant_id is not None
        and decision.matched_scope_project_id == request.scope_project_id
    )


def _revoke_decision_matches(
    decision: AuthorizationDecision,
    request: AdminRoleGrantRevokeRequest,
    *,
    existing_idempotency_record: bool = False,
) -> bool:
    return _revoke_decision_matches_grant(
        decision,
        request.grant_id,
        existing_idempotency_record=existing_idempotency_record,
    )


def _revoke_decision_matches_grant(
    decision: AuthorizationDecision,
    grant_id: UUID,
    *,
    existing_idempotency_record: bool = False,
) -> bool:
    return (
        decision.allowed
        and decision.revalidated
        and decision.matched_authority_kind is MatchedAuthorityKind.ADMIN_ROLE_GRANT
        and decision.action_id is ActionId.ADMIN_ROLE_GRANT_REVOKE
        and decision.permission_id is PermissionId.ADMIN_ROLE_REVOKE
        and decision.resource_type == "admin_role_grant"
        and decision.resource_id == grant_id
        and decision.resource_context_digest
        == authorization_resource_digest(
            AdminRoleGrantResourceContext(
                resource_type="admin_role_grant",
                resource_id=grant_id,
                existing_idempotency_record=existing_idempotency_record,
            )
        )
        and decision.matched_grant_id is not None
        and decision.matched_scope_project_id is None
    )


def _grant_response(grant: AdminRoleGrant) -> AdminRoleGrantResponse:
    system = grant.granted_by_system_principal is not None
    return AdminRoleGrantResponse(
        grant_id=grant.id,
        target_actor_profile_id=UUID(grant.target_actor_profile_id),
        role=AdminRole(grant.role),
        scope_type=AdminScope(grant.scope_type),
        scope_project_id=(UUID(grant.scope_project_id) if grant.scope_project_id else None),
        status=grant.status,
        version=grant.version,
        granted_by_ref_kind="system_principal" if system else "actor_profile",
        granted_by_ref=(
            grant.granted_by_system_principal if system else str(grant.granted_by_actor_profile_id)
        ),
        granted_by_admin_role_grant_id=grant.granted_by_admin_role_grant_id,
        grant_reason=grant.grant_reason,
        granted_at=grant.granted_at,
        revoked_by_actor_profile_id=(
            UUID(grant.revoked_by_actor_profile_id) if grant.revoked_by_actor_profile_id else None
        ),
        revoked_by_admin_role_grant_id=grant.revoked_by_admin_role_grant_id,
        revoked_reason=grant.revoked_reason,
        revoked_at=grant.revoked_at,
    )


def _mutation_response(response: AuthorityResponseReference) -> AuthorityMutationResponse:
    return AuthorityMutationResponse.model_validate(response.model_dump(mode="json"))


def _encode_cursor(grant: AdminRoleGrant) -> str:
    payload = json.dumps(
        [grant.granted_at.isoformat(), str(grant.id)],
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        padded = (value + "=" * (-len(value) % 4)).encode("ascii")
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
        payload = json.loads(raw)
        if not isinstance(payload, list) or len(payload) != 2:
            raise ValueError
        created_at = datetime.fromisoformat(payload[0])
        grant_id = UUID(payload[1])
        if created_at.tzinfo is None:
            raise ValueError
        return created_at, grant_id
    except (binascii.Error, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid cursor") from exc
