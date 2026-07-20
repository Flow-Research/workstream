"""Transaction-bound, single-use authorization for sensitive mutations."""

from __future__ import annotations

from copy import Error as CopyError
from dataclasses import dataclass
from secrets import token_bytes
from typing import NoReturn
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.audit.schemas import ActorReferenceKind
from app.modules.authorization.catalogue import (
    ACTION_BY_ID,
    SERVICE_ACTIONS_BY_IDENTITY,
    ActionAvailability,
    ActionId,
)
from app.modules.authorization.kernel import (
    _ADMIN_MUTATIONS,
    _PrelockedAuthority,
    AuthorizationService,
)
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind,
    ActorSelfResourceContext,
    ActorStatus,
    AuthorizationContext,
    AuthorizationDecision,
    AuthorizationResourceContext,
    HumanAuthorizationContext,
    IdentityLinkStatus,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    ServiceAuthorizationContext,
)


class PreparedAuthorizationHandle:
    """Opaque capability whose validity exists only in its issuing service."""

    __slots__ = ("__weakref__",)

    def __new__(cls, token: object = None):
        if token is not _HANDLE_CONSTRUCTOR_TOKEN:
            raise TypeError("prepared authorization handles are internal")
        return super().__new__(cls)

    def __repr__(self) -> str:
        return "<PreparedAuthorizationHandle>"

    def __copy__(self) -> NoReturn:
        raise CopyError("prepared authorization handles cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise CopyError("prepared authorization handles cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("prepared authorization handles cannot be serialized")


_HANDLE_CONSTRUCTOR_TOKEN = object()


@dataclass(frozen=True, slots=True)
class _PreparedAuthorizationBinding:
    action_id: ActionId
    actor_ref_kind: ActorReferenceKind
    actor_ref: UUID
    scope: PreparedAuthorityScope
    idempotency_key: UUID
    request_digest: str


@dataclass(slots=True)
class _Issuance:
    capability: bytes
    binding: _PreparedAuthorizationBinding
    transaction: object
    authority: _PrelockedAuthority
    consumed: bool = False


class PreparedAuthorizationService:
    """Issue and consume AUTH-owned capabilities inside one caller transaction."""

    def __init__(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        authorization: AuthorizationService,
        repository: AdminAuthorizationRepository,
    ) -> None:
        self._session = session
        self._context = context
        self._authorization = authorization
        self._repository = repository
        self._issued: dict[PreparedAuthorizationHandle, _Issuance] = {}
        self._closed = False

    async def prepare(
        self,
        action_id: ActionId,
        caller_input: PreparedAuthorizationInput,
        requested_authority_scope: PreparedAuthorityScope,
    ) -> PreparedAuthorizationHandle:
        """Lock one supported authority source and issue an opaque capability."""
        transaction = self._root_transaction()
        action = ACTION_BY_ID.get(action_id) if isinstance(action_id, ActionId) else None
        if action is None:
            raise PreparedAuthorizationUnsupported("prepared action is unsupported")
        binding = self._binding(action_id, caller_input, requested_authority_scope)
        context = self._context
        grant = None
        if isinstance(context, ServiceAuthorizationContext):
            if action_id not in SERVICE_ACTIONS_BY_IDENTITY[context.service_identity]:
                raise PreparedAuthorizationUnsupported("prepared authority is unsupported")
            locked = await self._repository.lock_request_actor(
                context.identity_link_id, context.actor_profile_id
            )
            context = self._locked_service_context(locked)
            if action.availability is not ActionAvailability.ACTIVE:
                raise PreparedAuthorizationUnsupported("prepared action is unsupported")
            # A positive fixed-service lock plan is activated with its first consumer.
            raise PreparedAuthorizationUnsupported("prepared action is unsupported")
        if action.availability is not ActionAvailability.ACTIVE:
            raise PreparedAuthorizationUnsupported("prepared action is unsupported")
        if action_id is ActionId.ACTOR_PROFILE_UPDATE_SELF:
            if (
                not isinstance(context, HumanAuthorizationContext)
                or requested_authority_scope.kind is not PreparedAuthorityScopeKind.ACTOR_SELF
                or requested_authority_scope.actor_profile_id != context.actor_profile_id
            ):
                raise PreparedAuthorizationUnsupported("prepared authority is unsupported")
            locked = await self._repository.lock_actor_self(
                context.actor_profile_id, context.identity_link_id
            )
            context = self._locked_human_context(locked)
        elif action_id in _ADMIN_MUTATIONS:
            if not isinstance(context, HumanAuthorizationContext):
                raise PreparedAuthorizationUnsupported("prepared authority is unsupported")
            if requested_authority_scope.kind not in {
                PreparedAuthorityScopeKind.SYSTEM,
                PreparedAuthorityScopeKind.PROJECT,
            }:
                raise PreparedAuthorizationUnsupported("prepared authority is unsupported")
            if (
                requested_authority_scope.kind is PreparedAuthorityScopeKind.PROJECT
                and action_id is not ActionId.ADMIN_ROLE_GRANT_ISSUE
            ):
                raise PreparedAuthorizationUnsupported("prepared authority is unsupported")
            await self._repository.lock_control()
            locked = await self._repository.lock_request_actor(
                context.identity_link_id, context.actor_profile_id
            )
            context = self._locked_human_context(locked)
            project_id = requested_authority_scope.project_id
            grant = await self._repository.find_effective_grant(
                context.actor_profile_id,
                action.permission_id,
                scope_project_id=project_id,
                system_scope_only=project_id is None,
                for_update=True,
            )
            if grant is None:
                raise PreparedAuthorizationUnsupported("prepared authority is unsupported")
        else:
            raise PreparedAuthorizationUnsupported("prepared action is unsupported")

        lifecycle = AuthorizationService._lifecycle_denial(context)
        if lifecycle is not None or context.actor_kind is not ActorKind.HUMAN:
            raise PreparedAuthorizationUnsupported("prepared authority is unsupported")
        authority = _PrelockedAuthority(
            context=context,
            action_id=action_id,
            scope_project_id=requested_authority_scope.project_id,
            matched_grant_id=UUID(str(grant.id)) if grant is not None else None,
            matched_grant_status=grant.status if grant is not None else None,
            permission_id=action.permission_id,
        )
        handle = PreparedAuthorizationHandle(_HANDLE_CONSTRUCTOR_TOKEN)
        self._issued[handle] = _Issuance(token_bytes(32), binding, transaction, authority)
        return handle

    async def consume(
        self,
        handle: PreparedAuthorizationHandle,
        expected_action_id: ActionId,
        caller_input: PreparedAuthorizationInput,
        final_resource_context: AuthorizationResourceContext,
    ) -> AuthorizationDecision:
        """Consume one exact capability before evaluating and evidencing final facts."""
        if self._closed or type(handle) is not PreparedAuthorizationHandle:
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        issuance = self._issued.get(handle)
        if issuance is None or issuance.consumed:
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        if expected_action_id is not issuance.binding.action_id:
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        rebound = self._binding(expected_action_id, caller_input, issuance.binding.scope)
        if rebound != issuance.binding:
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        transaction = self._root_transaction()
        if transaction is not issuance.transaction:
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        final_scope = self._scope_from_resource(expected_action_id, final_resource_context)
        if final_scope != issuance.binding.scope:
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        issuance.consumed = True
        return await self._authorization._require_prelocked(
            expected_action_id, final_resource_context, issuance.authority
        )

    def close(self) -> None:
        """Invalidate all outstanding request-local capabilities."""
        self._closed = True
        self._issued.clear()

    def _root_transaction(self) -> object:
        if self._closed or self._session.in_nested_transaction():
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        transaction = self._session.sync_session.get_transaction()
        if transaction is None or not transaction.is_active:
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        return transaction

    def _binding(
        self,
        action_id: ActionId,
        caller_input: PreparedAuthorizationInput,
        scope: PreparedAuthorityScope,
    ) -> _PreparedAuthorizationBinding:
        return _PreparedAuthorizationBinding(
            action_id=action_id,
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=self._context.actor_profile_id,
            scope=scope,
            idempotency_key=caller_input.idempotency_key,
            request_digest=canonical_json_hash(
                {
                    "domain": "workstream.prepared_authorization.request.v1",
                    "request": caller_input.request_value,
                }
            ),
        )

    def _locked_human_context(self, locked) -> HumanAuthorizationContext:
        if locked is None:
            raise PreparedAuthorizationUnsupported("prepared authority is unsupported")
        link, profile = locked
        if (
            profile.id != str(self._context.actor_profile_id)
            or link.id != str(self._context.identity_link_id)
            or link.actor_profile_id != profile.id
        ):
            raise PreparedAuthorizationUnsupported("prepared authority is unsupported")
        return HumanAuthorizationContext(
            actor_profile_id=UUID(profile.id),
            actor_kind=ActorKind(profile.actor_kind),
            actor_status=ActorStatus(profile.status),
            identity_link_id=UUID(link.id),
            identity_link_status=IdentityLinkStatus(link.status),
            request_id=self._context.request_id,
            correlation_id=self._context.correlation_id,
        )

    def _locked_service_context(self, locked) -> ServiceAuthorizationContext:
        if locked is None or not isinstance(self._context, ServiceAuthorizationContext):
            raise PreparedAuthorizationUnsupported("prepared authority is unsupported")
        link, profile = locked
        if (
            profile.id != str(self._context.actor_profile_id)
            or link.id != str(self._context.identity_link_id)
            or link.actor_profile_id != profile.id
            or profile.actor_kind != ActorKind.SERVICE.value
            or profile.service_identity != self._context.service_identity.value
        ):
            raise PreparedAuthorizationUnsupported("prepared authority is unsupported")
        return ServiceAuthorizationContext(
            actor_profile_id=UUID(profile.id),
            actor_kind=ActorKind.SERVICE,
            actor_status=ActorStatus(profile.status),
            identity_link_id=UUID(link.id),
            identity_link_status=IdentityLinkStatus(link.status),
            service_identity=self._context.service_identity,
            request_id=self._context.request_id,
            correlation_id=self._context.correlation_id,
        )

    def _scope_from_resource(
        self,
        action_id: ActionId,
        resource: AuthorizationResourceContext,
    ) -> PreparedAuthorityScope:
        if action_id is ActionId.ACTOR_PROFILE_UPDATE_SELF and isinstance(
            resource, ActorSelfResourceContext
        ):
            return PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.ACTOR_SELF,
                actor_profile_id=resource.resource_id,
            )
        if action_id in _ADMIN_MUTATIONS and AuthorizationService._admin_resource_matches(
            action_id, resource
        ):
            project_id = AuthorizationService._resource_project_id(resource)
            return PreparedAuthorityScope(
                kind=(
                    PreparedAuthorityScopeKind.PROJECT
                    if project_id is not None
                    else PreparedAuthorityScopeKind.SYSTEM
                ),
                project_id=project_id,
            )
        raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
