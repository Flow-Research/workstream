"""Deny-by-default request-scoped authorization kernel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.schemas import (
    ActorReferenceKind,
    AuthorityAuditEventInput,
    AuthorityEventType,
)
from app.modules.audit.service import AuditService
from app.modules.authorization.catalogue import (
    ACTION_BY_ID,
    ActionAvailability,
    ActionId,
)
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorAdminRoleGrantHistoryResourceContext,
    ActorIdentityLinkAdminReadResourceContext,
    ActorIdentityLinkLifecycleResourceContext,
    ActorKind,
    ActorProfileAdminReadResourceContext,
    ActorProfileLifecycleResourceContext,
    ActorSelfResourceContext,
    ActorStatus,
    AdminRoleDefinitionsResourceContext,
    AdminRoleGrantCollectionResourceContext,
    AdminRoleGrantIssueResourceContext,
    AdminRoleGrantResourceContext,
    AuthorizationContext,
    AuthorizationDecision,
    AuthorizationDenied,
    AuthorizationDenialCode,
    AuthorizationEvidenceUnavailable,
    AuthorizationResourceContext,
    IdentityLinkStatus,
    MatchedAuthorityKind,
    PermissionCatalogueResourceContext,
    ServiceActorProvisionResourceContext,
    authorization_resource_digest,
)

ContextRevalidator = Callable[
    [AuthorizationContext, ActorSelfResourceContext], Awaitable[AuthorizationContext]
]

_ADMIN_ACTIONS = frozenset(
    {
        ActionId.AUTHORIZATION_PERMISSION_CATALOGUE_READ,
        ActionId.AUTHORIZATION_ADMIN_ROLE_DEFINITIONS_READ,
        ActionId.ADMIN_ROLE_GRANT_LIST,
        ActionId.ACTOR_ADMIN_ROLE_GRANT_HISTORY_READ,
        ActionId.ADMIN_ROLE_GRANT_ISSUE,
        ActionId.ADMIN_ROLE_GRANT_REVOKE,
        ActionId.ADMIN_ROLE_GRANT_BOOTSTRAP,
        ActionId.ACTOR_SERVICE_PROVISION,
        ActionId.ACTOR_PROFILE_READ,
        ActionId.ACTOR_IDENTITY_LINK_READ,
        ActionId.ACTOR_PROFILE_SUSPEND,
        ActionId.ACTOR_PROFILE_REACTIVATE,
        ActionId.ACTOR_PROFILE_DEACTIVATE,
        ActionId.ACTOR_IDENTITY_LINK_REVOKE,
        ActionId.ACTOR_IDENTITY_LINK_REACTIVATE,
    }
)
_SERIALIZED_ADMIN_READS = frozenset(
    {
        ActionId.ACTOR_PROFILE_READ,
        ActionId.ACTOR_IDENTITY_LINK_READ,
    }
)
_ADMIN_MUTATIONS = frozenset(
    {
        ActionId.ADMIN_ROLE_GRANT_ISSUE,
        ActionId.ADMIN_ROLE_GRANT_REVOKE,
        ActionId.ACTOR_SERVICE_PROVISION,
        ActionId.ACTOR_PROFILE_SUSPEND,
        ActionId.ACTOR_PROFILE_REACTIVATE,
        ActionId.ACTOR_PROFILE_DEACTIVATE,
        ActionId.ACTOR_IDENTITY_LINK_REVOKE,
        ActionId.ACTOR_IDENTITY_LINK_REACTIVATE,
    }
)


class AuthorizationService:
    """Evaluate one request against closed action definitions and stage evidence."""

    def __init__(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        *,
        revalidate_actor_self: ContextRevalidator | None = None,
    ) -> None:
        self._audit = AuditService(session)
        self._admin = AdminAuthorizationRepository(session)
        self._context = context
        self._revalidate_actor_self = revalidate_actor_self
        self._pending_denial: AuthorizationDecision | None = None

    async def require(
        self,
        action_id: ActionId,
        resource_context: AuthorizationResourceContext,
    ) -> AuthorizationDecision:
        """Return an allowed decision or raise one bounded, evidenced denial."""
        self._pending_denial = None
        action = ACTION_BY_ID.get(action_id) if isinstance(action_id, ActionId) else None
        context = self._context
        revalidated = False
        matched_grant_id = None
        matched_project_id = None
        matched_kind = None
        if action is not None and action.action_id in _ADMIN_ACTIONS:
            (
                denial,
                context,
                matched_grant_id,
                matched_project_id,
                revalidated,
            ) = await self._admin_denial(action, resource_context, context)
            if denial is None:
                matched_kind = MatchedAuthorityKind.ADMIN_ROLE_GRANT
        else:
            if (
                action is not None
                and action.action_id
                in {
                    ActionId.ACTOR_PROFILE_READ_SELF,
                    ActionId.ACTOR_PROFILE_UPDATE_SELF,
                }
                and isinstance(resource_context, ActorSelfResourceContext)
                and self._revalidate_actor_self is not None
            ):
                context = await self._revalidate_actor_self(context, resource_context)
                revalidated = True
            denial = self._denial(action_id, action, resource_context, context, revalidated)
            if denial is None:
                matched_kind = MatchedAuthorityKind.ACTOR_SELF
        decision = AuthorizationDecision(
            decision_id=uuid4(),
            action_id=action.action_id if action is not None else None,
            permission_id=action.permission_id if action is not None else None,
            allowed=denial is None,
            denial_code=denial,
            resource_type=resource_context.resource_type,
            resource_id=resource_context.resource_id,
            resource_context_digest=authorization_resource_digest(resource_context),
            matched_authority_kind=matched_kind,
            matched_grant_id=matched_grant_id,
            matched_scope_project_id=matched_project_id,
            revalidated=revalidated,
            request_id=context.request_id,
            correlation_id=context.correlation_id,
        )
        await self._stage_decision(decision, context.actor_profile_id)
        if not decision.allowed:
            self._pending_denial = decision
            raise AuthorizationDenied(decision)
        return decision

    async def _admin_denial(
        self,
        action,
        resource: AuthorizationResourceContext,
        context: AuthorizationContext,
    ) -> tuple[
        AuthorizationDenialCode | None,
        AuthorizationContext,
        UUID | None,
        UUID | None,
        bool,
    ]:
        """Evaluate one administrative action against canonical grant state."""
        lifecycle = self._lifecycle_denial(context)
        if lifecycle is not None:
            return lifecycle, context, None, None, False
        if action.availability is not ActionAvailability.ACTIVE:
            return AuthorizationDenialCode.ACTION_UNAVAILABLE, context, None, None, False
        if action.action_id is ActionId.ADMIN_ROLE_GRANT_BOOTSTRAP:
            return AuthorizationDenialCode.RESOURCE_GUARD_DENIED, context, None, None, False
        if not self._admin_resource_matches(action.action_id, resource):
            return AuthorizationDenialCode.RESOURCE_GUARD_DENIED, context, None, None, False

        mutation = action.action_id in _ADMIN_MUTATIONS
        serialized = mutation or action.action_id in _SERIALIZED_ADMIN_READS
        if mutation:
            await self._admin.lock_control()
        if serialized:
            locked = await self._admin.lock_request_actor(
                context.identity_link_id,
                context.actor_profile_id,
            )
            if locked is None:
                return AuthorizationDenialCode.IDENTITY_LINK_REVOKED, context, None, None, True
            link, profile = locked
            context = AuthorizationContext(
                actor_profile_id=UUID(profile.id),
                actor_kind=ActorKind(profile.actor_kind),
                actor_status=ActorStatus(profile.status),
                identity_link_id=UUID(link.id),
                identity_link_status=IdentityLinkStatus(link.status),
                request_id=context.request_id,
                correlation_id=context.correlation_id,
            )
            lifecycle = self._lifecycle_denial(context)
            if lifecycle is not None:
                return lifecycle, context, None, None, True

        project_id = self._resource_project_id(resource)
        system_only = project_id is None
        matched = await self._admin.find_effective_grant(
            context.actor_profile_id,
            action.permission_id,
            scope_project_id=project_id,
            system_scope_only=system_only,
            for_update=serialized,
        )
        if matched is None:
            if project_id is not None and await self._admin.has_effective_permission_any_scope(
                context.actor_profile_id,
                action.permission_id,
            ):
                denial = AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED
            else:
                denial = AuthorizationDenialCode.PERMISSION_NOT_GRANTED
            return denial, context, None, None, serialized

        denial = await self._admin_guard(action.action_id, resource, context)
        return (
            denial,
            context,
            matched.id if denial is None else None,
            project_id if denial is None else None,
            serialized,
        )

    async def _admin_guard(
        self,
        action_id: ActionId,
        resource: AuthorizationResourceContext,
        context: AuthorizationContext,
    ) -> AuthorizationDenialCode | None:
        """Apply target existence and self-authority guards after permission match."""
        if isinstance(resource, AdminRoleGrantIssueResourceContext):
            if resource.resource_id == context.actor_profile_id:
                return AuthorizationDenialCode.SELF_GRANT_FORBIDDEN
            if await self._admin.lock_eligible_human(resource.resource_id) is None:
                return AuthorizationDenialCode.ACTOR_NOT_FOUND
            if resource.scope_project_id is not None and not await self._admin.project_exists(
                resource.scope_project_id,
                for_update=True,
            ):
                return AuthorizationDenialCode.RESOURCE_NOT_FOUND
        elif isinstance(resource, AdminRoleGrantResourceContext):
            grant = await self._admin.get_grant(resource.resource_id, for_update=True)
            if grant is None or (
                grant.status != "active" and not resource.existing_idempotency_record
            ):
                return AuthorizationDenialCode.GRANT_NOT_FOUND
            if grant.target_actor_profile_id == str(context.actor_profile_id):
                return AuthorizationDenialCode.SELF_ROLE_REVOKE_FORBIDDEN
        elif isinstance(resource, ActorProfileLifecycleResourceContext):
            if (
                resource.resource_id == context.actor_profile_id
                and resource.transition in {"suspend", "deactivate"}
            ):
                return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
            if await self._admin.lock_actor_lifecycle_target(resource.resource_id) is None:
                return AuthorizationDenialCode.ACTOR_NOT_FOUND
        elif isinstance(resource, ActorIdentityLinkLifecycleResourceContext):
            if (
                resource.resource_id == context.identity_link_id
                and resource.transition == "revoke"
            ):
                return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
            if (
                await self._admin.lock_identity_link_lifecycle_target(resource.resource_id)
                is None
            ):
                return AuthorizationDenialCode.RESOURCE_NOT_FOUND
        elif isinstance(
            resource,
            (AdminRoleGrantCollectionResourceContext, ActorAdminRoleGrantHistoryResourceContext),
        ):
            if resource.scope_project_id is not None and not await self._admin.project_exists(
                resource.scope_project_id
            ):
                return AuthorizationDenialCode.RESOURCE_NOT_FOUND
            if isinstance(
                resource, ActorAdminRoleGrantHistoryResourceContext
            ) and not await self._admin.actor_exists(resource.resource_id):
                return AuthorizationDenialCode.ACTOR_NOT_FOUND
        return None

    @staticmethod
    def _admin_resource_matches(
        action_id: ActionId,
        resource: AuthorizationResourceContext,
    ) -> bool:
        expected = {
            ActionId.AUTHORIZATION_PERMISSION_CATALOGUE_READ: PermissionCatalogueResourceContext,
            ActionId.AUTHORIZATION_ADMIN_ROLE_DEFINITIONS_READ: AdminRoleDefinitionsResourceContext,
            ActionId.ADMIN_ROLE_GRANT_LIST: AdminRoleGrantCollectionResourceContext,
            ActionId.ACTOR_ADMIN_ROLE_GRANT_HISTORY_READ: ActorAdminRoleGrantHistoryResourceContext,
            ActionId.ADMIN_ROLE_GRANT_ISSUE: AdminRoleGrantIssueResourceContext,
            ActionId.ADMIN_ROLE_GRANT_REVOKE: AdminRoleGrantResourceContext,
            ActionId.ACTOR_SERVICE_PROVISION: ServiceActorProvisionResourceContext,
            ActionId.ACTOR_PROFILE_READ: ActorProfileAdminReadResourceContext,
            ActionId.ACTOR_IDENTITY_LINK_READ: ActorIdentityLinkAdminReadResourceContext,
            ActionId.ACTOR_PROFILE_SUSPEND: ActorProfileLifecycleResourceContext,
            ActionId.ACTOR_PROFILE_REACTIVATE: ActorProfileLifecycleResourceContext,
            ActionId.ACTOR_PROFILE_DEACTIVATE: ActorProfileLifecycleResourceContext,
            ActionId.ACTOR_IDENTITY_LINK_REVOKE: ActorIdentityLinkLifecycleResourceContext,
            ActionId.ACTOR_IDENTITY_LINK_REACTIVATE: ActorIdentityLinkLifecycleResourceContext,
        }.get(action_id)
        if expected is None or not isinstance(resource, expected):
            return False
        transition = {
            ActionId.ACTOR_PROFILE_SUSPEND: "suspend",
            ActionId.ACTOR_PROFILE_REACTIVATE: "reactivate",
            ActionId.ACTOR_PROFILE_DEACTIVATE: "deactivate",
            ActionId.ACTOR_IDENTITY_LINK_REVOKE: "revoke",
            ActionId.ACTOR_IDENTITY_LINK_REACTIVATE: "reactivate",
        }.get(action_id)
        return transition is None or resource.transition == transition

    @staticmethod
    def _resource_project_id(resource: AuthorizationResourceContext):
        return getattr(resource, "scope_project_id", None)

    @staticmethod
    def _lifecycle_denial(
        context: AuthorizationContext,
    ) -> AuthorizationDenialCode | None:
        if context.identity_link_status is IdentityLinkStatus.REVOKED:
            return AuthorizationDenialCode.IDENTITY_LINK_REVOKED
        if context.actor_status is ActorStatus.DEACTIVATED:
            return AuthorizationDenialCode.ACTOR_DEACTIVATED
        if context.actor_status is ActorStatus.SUSPENDED:
            return AuthorizationDenialCode.ACTOR_SUSPENDED
        return None

    async def _restage_denial(self, decision: AuthorizationDecision) -> None:
        """Restage the exact pending denial after composition-root rollback."""
        if (
            decision.allowed
            or decision is not self._pending_denial
            or decision.request_id != self._context.request_id
            or decision.correlation_id != self._context.correlation_id
        ):
            raise TypeError("invalid authorization denial evidence")
        await self._stage_decision(decision, self._context.actor_profile_id)
        self._pending_denial = None

    @staticmethod
    def _denial(
        requested_action: object,
        action,
        resource: AuthorizationResourceContext,
        context: AuthorizationContext,
        revalidated: bool,
    ) -> AuthorizationDenialCode | None:
        """Apply the closed lifecycle, availability, guard, and candidate order."""
        if context.identity_link_status is IdentityLinkStatus.REVOKED:
            return AuthorizationDenialCode.IDENTITY_LINK_REVOKED
        if context.actor_status is ActorStatus.DEACTIVATED:
            return AuthorizationDenialCode.ACTOR_DEACTIVATED
        if (
            requested_action is ActionId.ACTOR_PROFILE_UPDATE_SELF
            and context.actor_status is ActorStatus.SUSPENDED
        ):
            return AuthorizationDenialCode.ACTOR_SUSPENDED
        if action is None:
            return AuthorizationDenialCode.UNKNOWN_ACTION
        if action.availability is not ActionAvailability.ACTIVE:
            return AuthorizationDenialCode.ACTION_UNAVAILABLE
        if action.action_id not in {
            ActionId.ACTOR_PROFILE_READ_SELF,
            ActionId.ACTOR_PROFILE_UPDATE_SELF,
        }:
            return AuthorizationDenialCode.ACTION_UNAVAILABLE
        if not isinstance(resource, ActorSelfResourceContext):
            return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
        if resource.resource_id != context.actor_profile_id:
            return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
        if action.action_id is ActionId.ACTOR_PROFILE_READ_SELF and resource.requested_fields:
            return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
        if action.action_id is ActionId.ACTOR_PROFILE_UPDATE_SELF and not resource.requested_fields:
            return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
        if context.actor_kind is not ActorKind.HUMAN:
            return AuthorizationDenialCode.PERMISSION_NOT_GRANTED
        if action.action_id in {
            ActionId.ACTOR_PROFILE_READ_SELF,
            ActionId.ACTOR_PROFILE_UPDATE_SELF,
        } and not revalidated:
            return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
        return None

    async def _stage_decision(
        self,
        decision: AuthorizationDecision,
        actor_profile_id,
    ) -> None:
        """Write one privacy-bounded event without taking transaction ownership."""
        if decision.action_id is None or decision.permission_id is None:
            return
        denial_code = decision.denial_code
        stored_denial = None
        if denial_code in {
            AuthorizationDenialCode.UNKNOWN_ACTION,
            AuthorizationDenialCode.ACTION_UNAVAILABLE,
        }:
            stored_denial = AuthorizationDenialCode.PERMISSION_NOT_GRANTED.value
        elif denial_code is not None:
            stored_denial = denial_code.value
        target_is_actor = decision.resource_type in {
            "actor_profile",
            "admin_role_grant_issue",
            "actor_admin_role_grant_history",
        }
        audit_resource_type = None
        if target_is_actor:
            audit_resource_type = "actor_profile"
        elif decision.resource_type in {"actor_identity_link", "admin_role_grant"}:
            audit_resource_type = decision.resource_type
        try:
            await self._audit.add_authority_event(
                AuthorityAuditEventInput(
                    event_id=decision.decision_id,
                    event_type=(
                        AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED
                        if decision.allowed
                        else AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED
                    ),
                    entity_type="authorization_decision",
                    entity_id=str(decision.decision_id),
                    actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
                    actor_ref=str(actor_profile_id),
                    request_id=decision.request_id,
                    correlation_id=decision.correlation_id,
                    target_actor_ref_kind=(
                        ActorReferenceKind.ACTOR_PROFILE if target_is_actor else None
                    ),
                    target_actor_ref=str(decision.resource_id) if target_is_actor else None,
                    matched_grant_id=(
                        str(decision.matched_grant_id)
                        if decision.allowed and decision.matched_grant_id is not None
                        else None
                    ),
                    permission_id=decision.permission_id,
                    action_id=decision.action_id,
                    project_id=(
                        str(decision.matched_scope_project_id)
                        if decision.matched_scope_project_id is not None
                        else None
                    ),
                    resource_type=audit_resource_type,
                    resource_id=(str(decision.resource_id) if audit_resource_type else None),
                    target_ref_kind=audit_resource_type,
                    target_ref_id=(str(decision.resource_id) if audit_resource_type else None),
                    reason="authorization_evaluation",
                    denial_code=stored_denial,
                    after_facts={"allowed": decision.allowed},
                )
            )
        except SQLAlchemyError as exc:
            raise AuthorizationEvidenceUnavailable("authorization evidence unavailable") from exc
