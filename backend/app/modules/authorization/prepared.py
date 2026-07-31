"""Transaction-bound, single-use authorization for sensitive mutations."""

from __future__ import annotations

from copy import Error as CopyError
from dataclasses import dataclass
from typing import NoReturn
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.audit.schemas import ActorReferenceKind
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.kernel import (
    _ADMIN_MUTATIONS,
    _PrelockedAuthority,
    AuthorizationService,
)
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorSelfResourceContext,
    ArtifactPendingWorkResourceContext,
    ArtifactPutAttemptResourceContext,
    ArtifactVerificationJobResourceContext,
    GuideSourceIngestResourceContext,
    AuthorizationContext,
    AuthorizationDecision,
    AuthorizationResourceContext,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    PROJECT_MUTATION_RESOURCE_BY_ACTION,
    ProjectCreateResourceContext,
    ProjectGuideMutationResourceContext,
    ProjectGuideMutationPrepareDenialResourceContext,
    ProjectGuideSourceSnapshotMutationResourceContext,
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
    project_create_operation_id: UUID | None = None
    project_create_project_id: UUID | None = None
    project_create_generation: int | None = None
    guide_mutation_project_id: UUID | None = None
    guide_mutation_guide_id: UUID | None = None
    guide_mutation_target_resource_id: UUID | None = None
    guide_mutation_operation_id: UUID | None = None


@dataclass(slots=True)
class _Issuance:
    binding: _PreparedAuthorizationBinding
    transaction: object
    authority: _PrelockedAuthority


class _Consumed:
    """Bounded replay tombstone retaining no session or authority graph."""

    __slots__ = ()


def _project_create_binding_matches(
    binding: _PreparedAuthorizationBinding,
    resource: ProjectCreateResourceContext,
) -> bool:
    """Return whether final project-create identity matches the prepared binding."""
    return (
        binding.project_create_operation_id == resource.resource_id
        and binding.project_create_project_id == resource.requested_project_id
        and binding.project_create_generation == resource.operation_generation
    )


def _guide_mutation_binding_matches(
    binding: _PreparedAuthorizationBinding,
    resource: ProjectGuideMutationResourceContext
    | ProjectGuideSourceSnapshotMutationResourceContext,
) -> bool:
    """Return whether final guide lineage matches the prepared route selectors."""
    return (
        binding.guide_mutation_project_id == resource.scope_project_id
        and binding.guide_mutation_guide_id == resource.guide_id
        and binding.guide_mutation_target_resource_id == resource.resource_id
        and binding.guide_mutation_operation_id == resource.operation_id
    )


_CONSUMED = _Consumed()


class PreparedAuthorizationService:
    """Issue and consume AUTH-owned capabilities inside one caller transaction."""

    def __init__(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        authorization: AuthorizationService,
        repository: AdminAuthorizationRepository,
    ) -> None:
        if authorization._session is not session:
            raise TypeError("prepared authorization requires one exact session")
        if authorization._admin is not repository:
            raise TypeError("prepared authorization requires one exact repository")
        self._session = session
        self._context = context
        self._authorization = authorization
        self._repository = repository
        self._issued: dict[PreparedAuthorizationHandle, _Issuance | _Consumed] = {}
        self._closed = False
        self._consumer_token = authorization._register_prepared_consumer(
            self,
            session=session,
            repository=repository,
            context=context,
        )

    async def prepare(
        self,
        action_id: ActionId,
        caller_input: PreparedAuthorizationInput,
        requested_authority_scope: PreparedAuthorityScope,
    ) -> PreparedAuthorizationHandle:
        """Lock one supported authority source and issue an opaque capability."""
        transaction = self._root_transaction()
        binding = self._binding(action_id, caller_input, requested_authority_scope)
        authority = await self._authorization._prepare_prelocked(
            self._consumer_token, action_id, requested_authority_scope
        )
        handle = PreparedAuthorizationHandle(_HANDLE_CONSTRUCTOR_TOKEN)
        self._issued[handle] = _Issuance(binding, transaction, authority)
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
        if issuance is None or issuance is _CONSUMED:
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
        if isinstance(final_resource_context, ProjectCreateResourceContext) and not (
            _project_create_binding_matches(issuance.binding, final_resource_context)
        ):
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        if isinstance(
            final_resource_context,
            (ProjectGuideMutationResourceContext, ProjectGuideSourceSnapshotMutationResourceContext),
        ) and not _guide_mutation_binding_matches(issuance.binding, final_resource_context):
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        self._issued[handle] = _CONSUMED
        return await self._authorization._require_prelocked(
            self._consumer_token,
            expected_action_id,
            final_resource_context,
            issuance.authority,
        )

    async def deny_unsupported(
        self,
        action_id: ActionId,
        caller_input: PreparedAuthorizationInput,
        final_resource_context: AuthorizationResourceContext,
        denial: PreparedAuthorizationUnsupported,
    ) -> NoReturn:
        """Evidence an exact prepare-time denial without issuing a handle."""
        scope = (
            PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM)
            if isinstance(final_resource_context, ProjectCreateResourceContext)
            else self._scope_from_resource(action_id, final_resource_context)
        )
        binding = self._binding(action_id, caller_input, scope)
        if isinstance(final_resource_context, ProjectCreateResourceContext) and not (
            _project_create_binding_matches(binding, final_resource_context)
        ):
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        await self._authorization._complete_prepared_denial(
            self._consumer_token,
            action_id,
            final_resource_context,
            denial.denial_code,
        )
        raise RuntimeError("denied prepared authorization unexpectedly returned")

    def close(self) -> None:
        """Invalidate all outstanding request-local capabilities."""
        for issuance in self._issued.values():
            if isinstance(issuance, _Issuance):
                self._authorization._discard_prelocked(issuance.authority)
        self._authorization._unregister_prepared_consumer(self._consumer_token, self)
        self._closed = True
        self._issued.clear()

    def _root_transaction(self) -> object:
        if self._closed or self._session.in_nested_transaction():
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        transaction = self._session.sync_session.get_transaction()
        if transaction is None or not transaction.is_active:
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        stale = [
            handle
            for handle, issuance in self._issued.items()
            if isinstance(issuance, _Issuance) and issuance.transaction is not transaction
        ]
        for handle in stale:
            issuance = self._issued[handle]
            if isinstance(issuance, _Issuance):
                self._authorization._discard_prelocked(issuance.authority)
            del self._issued[handle]
        return transaction

    def _binding(
        self,
        action_id: ActionId,
        caller_input: PreparedAuthorizationInput,
        scope: PreparedAuthorityScope,
    ) -> _PreparedAuthorizationBinding:
        operation_id = project_id = None
        operation_generation = None
        guide_mutation_project_id = guide_mutation_guide_id = None
        guide_mutation_target_resource_id = guide_mutation_operation_id = None
        if action_id is ActionId.PROJECT_CREATE:
            try:
                operation_id = UUID(str(caller_input.request_value["operation_id"]))
                project_id = UUID(str(caller_input.request_value["project_id"]))
                operation_generation = caller_input.request_value["operation_generation"]
            except (KeyError, TypeError, ValueError) as exc:
                raise PreparedAuthorizationHandleInvalid(
                    "invalid prepared authorization handle"
                ) from exc
            if (
                type(operation_generation) is not int
                or operation_generation < 1
                or operation_id == project_id
            ):
                raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        if action_id in {
            ActionId.PROJECT_GUIDE_CREATE,
            ActionId.PROJECT_GUIDE_UPDATE,
            ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE,
        }:
            try:
                guide_mutation_project_id = UUID(
                    str(caller_input.request_value["project_id"])
                )
                raw_guide_id = caller_input.request_value.get("guide_id")
                guide_mutation_guide_id = (
                    UUID(str(raw_guide_id)) if raw_guide_id is not None else None
                )
                guide_mutation_target_resource_id = UUID(
                    str(caller_input.request_value["target_resource_id"])
                )
                guide_mutation_operation_id = UUID(
                    str(caller_input.request_value["operation_id"])
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise PreparedAuthorizationHandleInvalid(
                    "invalid prepared authorization handle"
                ) from exc
            if (
                guide_mutation_guide_id is None
                or guide_mutation_target_resource_id is None
                or guide_mutation_operation_id is None
                or (
                    action_id is ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE
                    and guide_mutation_target_resource_id == guide_mutation_guide_id
                )
                or (
                    action_id is not ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE
                    and guide_mutation_target_resource_id != guide_mutation_guide_id
                )
            ):
                raise PreparedAuthorizationHandleInvalid(
                    "invalid prepared authorization handle"
                )
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
            project_create_operation_id=operation_id,
            project_create_project_id=project_id,
            project_create_generation=operation_generation,
            guide_mutation_project_id=guide_mutation_project_id,
            guide_mutation_guide_id=guide_mutation_guide_id,
            guide_mutation_target_resource_id=guide_mutation_target_resource_id,
            guide_mutation_operation_id=guide_mutation_operation_id,
        )

    @staticmethod
    def _scope_from_resource(
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
            target_actor_profile_id = None
            role = None
            grant_id = None
            if action_id is ActionId.PROJECT_ROLE_GRANT_ISSUE:
                target_actor_profile_id = resource.target_actor_profile_id
                role = resource.role
            elif action_id is ActionId.PROJECT_ROLE_GRANT_REVOKE:
                grant_id = resource.resource_id
            return PreparedAuthorityScope(
                kind=(
                    PreparedAuthorityScopeKind.PROJECT
                    if project_id is not None
                    else PreparedAuthorityScopeKind.SYSTEM
                ),
                project_id=project_id,
                target_actor_profile_id=target_actor_profile_id,
                role=role,
                grant_id=grant_id,
            )
        expected_project_mutation = PROJECT_MUTATION_RESOURCE_BY_ACTION.get(action_id)
        if action_id in {
            ActionId.PROJECT_GUIDE_CREATE,
            ActionId.PROJECT_GUIDE_UPDATE,
            ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE,
        } and isinstance(resource, ProjectGuideMutationPrepareDenialResourceContext):
            return PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT,
                project_id=resource.scope_project_id,
            )
        if expected_project_mutation is not None and isinstance(
            resource, expected_project_mutation
        ):
            if isinstance(resource, ProjectCreateResourceContext):
                return PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM)
            return PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT,
                project_id=resource.scope_project_id,
            )
        artifact_resource_type = {
            ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE: ArtifactPutAttemptResourceContext,
            ActionId.ARTIFACT_VERIFICATION_EXECUTE: ArtifactVerificationJobResourceContext,
            ActionId.ARTIFACT_PENDING_WORK_SCAN: ArtifactPendingWorkResourceContext,
        }.get(action_id)
        if artifact_resource_type is not None and isinstance(resource, artifact_resource_type):
            return PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.ARTIFACT_INTERNAL,
                artifact_resource_type=resource.resource_type,
                artifact_resource_id=resource.resource_id,
            )
        if action_id is ActionId.ARTIFACT_GUIDE_SOURCE_INGEST and isinstance(
            resource, GuideSourceIngestResourceContext
        ):
            return PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT,
                project_id=resource.scope_project_id,
            )
        raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
