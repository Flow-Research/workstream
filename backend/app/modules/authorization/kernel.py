"""Deny-by-default request-scoped authorization kernel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import MappingProxyType
from typing import NoReturn
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
    SERVICE_ACTIONS_BY_IDENTITY,
    ActionAvailability,
    ActionId,
    PermissionId,
)
from app.modules.authorization.domain import adapter_bindings, guide_compilation as compilation
from app.modules.authorization.domain.audit import CONTEXT_DIGEST_RESOURCE_TYPES
from app.modules.authorization.domain.guide_compilation_projections import (
    ProjectGuideProjectionResourceContext,
)
from app.modules.authorization.domain.prepared_service import (
    is_project_setup_scope,
    project_setup_resource_matches,
)
from app.modules.authorization.policy import ACTIVE_GUIDE_ADMIN_ROLES
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.schemas import AdminRole
from app.modules.authorization.runtime import (
    PROJECT_DIAGNOSTIC_TARGET_KIND_BY_ACTION,
    PROJECT_GUIDE_TARGET_KIND_BY_ACTION,
    PROJECT_MUTATION_RESOURCE_BY_ACTION,
    PROJECT_POST_SUBMIT_POLICY_TARGET_KIND_BY_ACTION,
    PROJECT_POLICY_READ_TARGET_KIND_BY_ACTION,
    PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION,
    PROJECT_SUFFICIENCY_TARGET_KIND_BY_ACTION,
    ActorAdminRoleGrantHistoryResourceContext,
    ActorAuthorizationContextResourceContext,
    ActorIdentityLinkAdminReadResourceContext,
    ActorIdentityLinkLifecycleResourceContext,
    ActorKind,
    ActorProfileAdminReadResourceContext,
    ActorProfileLifecycleResourceContext,
    ActorSelfResourceContext,
    ActorStatus,
    ArtifactPendingWorkResourceContext,
    ArtifactPutAttemptResourceContext,
    ArtifactVerificationJobResourceContext,
    GuideSourceBindingResourceContext,
    GuideSourceReadResourceContext,
    SubmissionBindingResourceContext,
    PreSubmitCheckerInputResourceContext,
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
    HumanAuthorizationContext,
    IdentityLinkStatus,
    MatchedAuthorityKind,
    PermissionCatalogueResourceContext,
    ProjectContributorCandidateCollectionResourceContext,
    ProjectCreateResourceContext,
    ProjectGuideMutationPrepareDenialResourceContext,
    ProjectGuideSufficiencyMutationResourceContext,
    ProjectSubmissionArtifactPolicyMutationResourceContext,
    ProjectReadResourceContext,
    ProjectDiagnosticReadResourceContext,
    ProjectPolicyReadResourceContext,
    ProjectPolicyMutationPrepareDenialResourceContext,
    ProjectActiveGuideReadResourceContext,
    ProjectRoleGrantCollectionResourceContext,
    ProjectRoleGrantIssueResourceContext,
    ProjectRoleGrantReadResourceContext,
    ProjectRoleGrantRevokeResourceContext,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    ServiceAuthorizationContext,
    ServiceActorProvisionResourceContext,
    authorization_resource_digest,
)
from app.modules.authorization.artifact_project_authority import (
    evaluate_guide_ingest_authority,
    evaluate_submitter_authority,
    lock_guide_ingest_authority,
    lock_submitter_authority,
)

ContextRevalidator = Callable[
    [
        HumanAuthorizationContext,
        ActorSelfResourceContext
        | ActorAuthorizationContextResourceContext
        | ProjectReadResourceContext,
    ],
    Awaitable[HumanAuthorizationContext],
]

_GUIDE_BOUND_PROJECT_MANAGER_MUTATIONS = frozenset(
    {
        ActionId.PROJECT_GUIDE_CREATE,
        ActionId.PROJECT_GUIDE_UPDATE,
        ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE,
        ActionId.PROJECT_GUIDE_COMPILATION_REQUEST,
        ActionId.PROJECT_REVIEW_POLICY_UPDATE,
        ActionId.PROJECT_REVISION_POLICY_UPDATE,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_CREATE,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_WARNINGS_ACKNOWLEDGE,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_APPROVE,
    }
)
_SUBMISSION_POLICY_MUTATIONS = frozenset(PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION)

ServiceContextRevalidator = Callable[
    [ServiceAuthorizationContext, ActionId],
    Awaitable[ServiceAuthorizationContext | None],
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
        ActionId.PROJECT_ROLE_GRANT_ISSUE,
        ActionId.PROJECT_ROLE_GRANT_REVOKE,
        ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST,
        ActionId.PROJECT_ROLE_GRANT_LIST,
        ActionId.PROJECT_ROLE_GRANT_READ,
        ActionId.PROJECT_SETUP_RUN_READ,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ,
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ,
        ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ,
        ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ,
        ActionId.PROJECT_ACTIVE_GUIDE_READ,
    }
) | adapter_bindings.ADAPTER_BINDING_READ_ACTIONS
_SERIALIZED_ADMIN_READS = frozenset(
    {
        ActionId.ACTOR_PROFILE_READ,
        ActionId.ACTOR_IDENTITY_LINK_READ,
        ActionId.PROJECT_SETUP_RUN_READ,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ,
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ,
        ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ,
        ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ,
        ActionId.PROJECT_ACTIVE_GUIDE_READ,
    }
) | adapter_bindings.ADAPTER_BINDING_READ_ACTIONS
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
        ActionId.PROJECT_ROLE_GRANT_ISSUE,
        ActionId.PROJECT_ROLE_GRANT_REVOKE,
    }
) | adapter_bindings.ADAPTER_BINDING_MUTATION_ACTIONS

_ARTIFACT_INTERNAL_RESOURCES = {
    ActionId.ARTIFACT_GUIDE_SOURCE_BINDING_CREATE: (
        "guide_source_binding",
        GuideSourceBindingResourceContext,
    ),
    ActionId.ARTIFACT_GUIDE_SOURCE_READ: (
        "guide_source_read",
        GuideSourceReadResourceContext,
    ),
    ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE: (
        "pre_submit_checker_input",
        PreSubmitCheckerInputResourceContext,
    ),
    ActionId.ARTIFACT_SUBMISSION_BINDING_CREATE: ("submission_binding", SubmissionBindingResourceContext),
    ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE: (
        "artifact_put_attempt",
        ArtifactPutAttemptResourceContext,
    ),
    ActionId.ARTIFACT_VERIFICATION_EXECUTE: (
        "artifact_verification_job",
        ArtifactVerificationJobResourceContext,
    ),
    ActionId.ARTIFACT_PENDING_WORK_SCAN: (
        "artifact_pending_work",
        ArtifactPendingWorkResourceContext,
    ),
}

_ADMIN_EXPECTED_RESOURCES = MappingProxyType(
    {
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
        ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST: (
            ProjectContributorCandidateCollectionResourceContext
        ),
        ActionId.PROJECT_ROLE_GRANT_LIST: ProjectRoleGrantCollectionResourceContext,
        ActionId.PROJECT_ROLE_GRANT_READ: ProjectRoleGrantReadResourceContext,
        ActionId.PROJECT_ROLE_GRANT_ISSUE: ProjectRoleGrantIssueResourceContext,
        ActionId.PROJECT_ROLE_GRANT_REVOKE: ProjectRoleGrantRevokeResourceContext,
        ActionId.PROJECT_SETUP_RUN_READ: ProjectDiagnosticReadResourceContext,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST: ProjectDiagnosticReadResourceContext,
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ: ProjectDiagnosticReadResourceContext,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST: ProjectDiagnosticReadResourceContext,
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ: ProjectDiagnosticReadResourceContext,
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_SETUP_READ: (
            ProjectDiagnosticReadResourceContext
        ),
        ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ: (
            ProjectPolicyReadResourceContext
        ),
        ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ: ProjectPolicyReadResourceContext,
        ActionId.PROJECT_ACTIVE_GUIDE_READ: ProjectActiveGuideReadResourceContext,
        **adapter_bindings.ADAPTER_BINDING_RESOURCE_BY_ACTION,
        **PROJECT_MUTATION_RESOURCE_BY_ACTION,
    }
)

def project_action_available_for_status(action_id: ActionId, project_status: str) -> bool:
    """Apply project-only lifecycle guards shared by decisions and projections."""
    if action_id in {
        ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST,
        ActionId.PROJECT_ROLE_GRANT_ISSUE,
    }:
        return project_status in {"draft", "active", "paused"}
    if action_id in {
        ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ,
        ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ,
        ActionId.PROJECT_ACTIVE_GUIDE_READ,
    }:
        return project_status == "active"
    return True

class _PrelockedAuthority:
    """AUTH-private authority facts locked by the prepared protocol."""

    __slots__ = (
        "action_id",
        "artifact_resource_id",
        "artifact_resource_type",
        "context",
        "_frozen",
        "issuer",
        "matched_grant_id",
        "matched_grant_scope_project_id",
        "matched_grant_status",
        "permission_id",
        "scope_project_id",
        "transaction",
    )

    def __new__(cls, token: object = None, **_kwargs):
        if token is not _PRELOCKED_CONSTRUCTOR_TOKEN:
            raise TypeError("prelocked authority is internal")
        return super().__new__(cls)

    def __init__(
        self,
        token: object,
        *,
        issuer: AuthorizationService,
        transaction: object,
        context: AuthorizationContext,
        action_id: ActionId,
        scope_project_id: UUID | None,
        matched_grant_id: UUID | None,
        matched_grant_scope_project_id: UUID | None,
        matched_grant_status: str | None,
        permission_id: PermissionId,
        artifact_resource_type: str | None = None,
        artifact_resource_id: UUID | str | None = None,
    ) -> None:
        object.__setattr__(self, "issuer", issuer)
        object.__setattr__(self, "transaction", transaction)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "action_id", action_id)
        object.__setattr__(self, "scope_project_id", scope_project_id)
        object.__setattr__(self, "matched_grant_id", matched_grant_id)
        object.__setattr__(self, "matched_grant_scope_project_id", matched_grant_scope_project_id)
        object.__setattr__(self, "matched_grant_status", matched_grant_status)
        object.__setattr__(self, "permission_id", permission_id)
        object.__setattr__(self, "artifact_resource_type", artifact_resource_type)
        object.__setattr__(self, "artifact_resource_id", artifact_resource_id)
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("prelocked authority is immutable")

_PRELOCKED_CONSTRUCTOR_TOKEN = object()

class AuthorizationService:
    """Evaluate one request against closed action definitions and stage evidence."""

    def __init__(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        *,
        revalidate_actor_self: ContextRevalidator | None = None,
        revalidate_service: ServiceContextRevalidator | None = None,
        admin_repository: AdminAuthorizationRepository | None = None,
    ) -> None:
        self._session = session
        self._audit = AuditService(session)
        self._admin = admin_repository or AdminAuthorizationRepository(session)
        self._context = context
        self._revalidate_actor_self = revalidate_actor_self
        self._revalidate_service = revalidate_service
        self._pending_denial: AuthorizationDecision | None = None
        self._pending_denial_resource_context: AuthorizationResourceContext | None = None
        self._sealed_prelocked: set[_PrelockedAuthority] = set()
        self._prepared_consumers: dict[object, object] = {}

    def _register_prepared_consumer(
        self,
        owner: object,
        *,
        session: AsyncSession,
        repository: AdminAuthorizationRepository,
        context: AuthorizationContext,
    ) -> object:
        """Issue one opaque kernel token only to an exactly composed PREP service."""
        from app.modules.authorization.prepared import PreparedAuthorizationService

        if (
            type(owner) is not PreparedAuthorizationService
            or session is not self._session
            or repository is not self._admin
            or context != self._context
        ):
            raise TypeError("invalid prepared authorization composition")
        token = object()
        self._prepared_consumers[token] = owner
        return token

    def _unregister_prepared_consumer(self, token: object, owner: object) -> None:
        """Revoke one prepared service's access to the private kernel seam."""
        if self._prepared_consumers.get(token) is owner:
            del self._prepared_consumers[token]

    def _validate_prepared_consumer(self, token: object) -> None:
        if token not in self._prepared_consumers:
            raise TypeError("invalid prepared authorization consumer")

    async def _prepare_prelocked(
        self,
        consumer_token: object,
        action_id: ActionId,
        scope: PreparedAuthorityScope,
    ) -> _PrelockedAuthority:
        self._validate_prepared_consumer(consumer_token)
        if self._session.in_nested_transaction():
            raise TypeError("prelocked authority requires one root transaction")
        transaction = self._session.sync_session.get_transaction()
        if transaction is None or not transaction.is_active:
            raise TypeError("prelocked authority requires one active root transaction")
        action = ACTION_BY_ID.get(action_id) if isinstance(action_id, ActionId) else None
        if action is None:
            raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.UNKNOWN_ACTION)
        context, grant = self._context, None
        if isinstance(context, ServiceAuthorizationContext):
            if action_id not in SERVICE_ACTIONS_BY_IDENTITY.get(context.service_identity, ()):
                raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.PERMISSION_NOT_GRANTED)
            if action.availability is not ActionAvailability.ACTIVE:
                raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.ACTION_UNAVAILABLE)
            expected_resource = _ARTIFACT_INTERNAL_RESOURCES.get(action_id)
            project_setup_action = is_project_setup_scope(action_id, scope)
            if not project_setup_action and (
                expected_resource is None
                or scope.kind is not PreparedAuthorityScopeKind.ARTIFACT_INTERNAL
                or scope.artifact_resource_type != expected_resource[0]
            ):
                raise PreparedAuthorizationUnsupported(
                    AuthorizationDenialCode.RESOURCE_GUARD_DENIED
                )
            locked = await self._admin.lock_request_actor(
                context.identity_link_id, context.actor_profile_id
            )
            context = self._locked_service_context(locked, context)
            lifecycle = self._lifecycle_denial(context)
            if lifecycle is not None:
                raise PreparedAuthorizationUnsupported(lifecycle)
            authority = _PrelockedAuthority(
                _PRELOCKED_CONSTRUCTOR_TOKEN,
                issuer=self,
                transaction=transaction,
                context=context,
                action_id=action_id,
                scope_project_id=scope.project_id if project_setup_action else None,
                matched_grant_id=None,
                matched_grant_scope_project_id=None,
                matched_grant_status=None,
                permission_id=action.permission_id,
                artifact_resource_type=scope.artifact_resource_type,
                artifact_resource_id=scope.artifact_resource_id,
            )
            self._sealed_prelocked.add(authority)
            return authority
        if action.availability is not ActionAvailability.ACTIVE:
            raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.ACTION_UNAVAILABLE)
        if action_id is ActionId.ACTOR_PROFILE_UPDATE_SELF:
            if (
                scope.kind is not PreparedAuthorityScopeKind.ACTOR_SELF
                or scope.actor_profile_id != context.actor_profile_id
            ):
                raise PreparedAuthorizationUnsupported(
                    AuthorizationDenialCode.RESOURCE_GUARD_DENIED
                )
            locked = await self._admin.lock_actor_self(
                context.actor_profile_id, context.identity_link_id
            )
            context = self._locked_human_context(locked, context)
        elif action_id in _ADMIN_MUTATIONS:
            if not isinstance(context, HumanAuthorizationContext):
                raise PreparedAuthorizationUnsupported(
                    AuthorizationDenialCode.PERMISSION_NOT_GRANTED
                )
            if scope.kind not in {PreparedAuthorityScopeKind.SYSTEM, PreparedAuthorityScopeKind.PROJECT}:
                raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED)
            if scope.kind is PreparedAuthorityScopeKind.PROJECT and action_id not in {
                ActionId.ADMIN_ROLE_GRANT_ISSUE,
                ActionId.PROJECT_ROLE_GRANT_ISSUE,
                ActionId.PROJECT_ROLE_GRANT_REVOKE,
                *adapter_bindings.ADAPTER_BINDING_MUTATION_ACTIONS,
            }:
                raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED)
            await self._admin.lock_control()
            if action_id is ActionId.PROJECT_ROLE_GRANT_ISSUE:
                if scope.target_actor_profile_id is None or scope.role is None:
                    raise PreparedAuthorizationUnsupported(
                        AuthorizationDenialCode.RESOURCE_GUARD_DENIED
                    )
                locked, _target_eligible = await self._admin.lock_project_role_issue_principals(
                    caller_actor_profile_id=context.actor_profile_id,
                    caller_identity_link_id=context.identity_link_id,
                    target_actor_profile_id=scope.target_actor_profile_id,
                )
            else:
                locked = await self._admin.lock_request_actor(
                    context.identity_link_id, context.actor_profile_id
                )
            context = self._locked_human_context(locked, context)
            if action_id is ActionId.PROJECT_ROLE_GRANT_REVOKE and scope.grant_id is None:
                raise PreparedAuthorizationUnsupported(
                    AuthorizationDenialCode.RESOURCE_GUARD_DENIED
                )
            grant = await self._admin.find_effective_grant(
                context.actor_profile_id,
                action.permission_id,
                scope_project_id=scope.project_id,
                system_scope_only=scope.project_id is None,
                for_update=True,
                **adapter_bindings.finance_authority_grant_filters(action_id),
            )
            if grant is None:
                raise PreparedAuthorizationUnsupported(
                    AuthorizationDenialCode.PERMISSION_NOT_GRANTED
                )
        elif action_id in _GUIDE_BOUND_PROJECT_MANAGER_MUTATIONS:
            if (
                not isinstance(context, HumanAuthorizationContext)
                or scope.kind is not PreparedAuthorityScopeKind.PROJECT
                or scope.project_id is None
            ):
                raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED)
            locked = await self._admin.lock_request_actor(
                context.identity_link_id, context.actor_profile_id
            )
            context = self._locked_human_context(locked, context)
            grant = await self._admin.find_effective_grant(
                context.actor_profile_id,
                action.permission_id,
                scope_project_id=scope.project_id,
                for_update=True,
                allowed_roles=frozenset({AdminRole.PROJECT_MANAGER}),
                exact_project_scope=action_id is ActionId.PROJECT_GUIDE_COMPILATION_REQUEST,
            )
            if grant is None:
                raise PreparedAuthorizationUnsupported(
                    AuthorizationDenialCode.PERMISSION_NOT_GRANTED
                )
            if action_id is ActionId.PROJECT_GUIDE_COMPILATION_REQUEST and (
                grant.scope_type != "project" or grant.scope_project_id != str(scope.project_id)
            ):
                raise PreparedAuthorizationUnsupported(
                    AuthorizationDenialCode.PERMISSION_NOT_GRANTED
                )
        elif action_id is ActionId.PROJECT_CREATE:
            if not isinstance(context, HumanAuthorizationContext):
                raise PreparedAuthorizationUnsupported(
                    AuthorizationDenialCode.PERMISSION_NOT_GRANTED
                )
            if scope.kind is not PreparedAuthorityScopeKind.SYSTEM:
                raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED)
            locked = await self._admin.lock_request_actor(
                context.identity_link_id, context.actor_profile_id
            )
            context = self._locked_human_context(locked, context)
            grant = await self._admin.find_effective_grant(
                context.actor_profile_id,
                PermissionId.PROJECT_CREATE,
                scope_project_id=None,
                system_scope_only=True,
                for_update=True,
            )
            if grant is None:
                raise PreparedAuthorizationUnsupported(
                    AuthorizationDenialCode.PERMISSION_NOT_GRANTED
                )
        elif action_id is ActionId.ARTIFACT_GUIDE_SOURCE_INGEST:
            context, grant = await lock_guide_ingest_authority(self._admin, context, scope, action.permission_id, self._locked_human_context)
        elif action_id in {ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE, ActionId.SUBMISSION_CREATE}:
            context, grant = await lock_submitter_authority(
                self._admin, context, scope, self._locked_human_context
            )
        else:
            raise PreparedAuthorizationUnsupported(
                AuthorizationDenialCode.PERMISSION_NOT_GRANTED
                if action_id in _ARTIFACT_INTERNAL_RESOURCES
                else AuthorizationDenialCode.ACTION_UNAVAILABLE
            )
        lifecycle = self._lifecycle_denial(context)
        if lifecycle is not None or context.actor_kind is not ActorKind.HUMAN:
            raise PreparedAuthorizationUnsupported(
                lifecycle or AuthorizationDenialCode.PERMISSION_NOT_GRANTED
            )
        authority = _PrelockedAuthority(
            _PRELOCKED_CONSTRUCTOR_TOKEN,
            issuer=self,
            transaction=transaction,
            context=context,
            action_id=action_id,
            scope_project_id=scope.project_id,
            matched_grant_id=UUID(str(grant.id)) if grant is not None else None,
            matched_grant_scope_project_id=(
                UUID(str(grant.scope_project_id))
                if grant is not None and getattr(grant, "scope_project_id", None) is not None
                else None
            ),
            matched_grant_status=grant.status if grant is not None else None,
            permission_id=action.permission_id,
        )
        self._sealed_prelocked.add(authority)
        return authority

    @staticmethod
    def _locked_human_context(locked, original) -> HumanAuthorizationContext:
        if locked is None:
            raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.IDENTITY_LINK_REVOKED)
        link, profile = locked
        if (
            profile.id != str(original.actor_profile_id)
            or link.id != str(original.identity_link_id)
            or link.actor_profile_id != profile.id
        ):
            raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.PERMISSION_NOT_GRANTED)
        return HumanAuthorizationContext(
            actor_profile_id=UUID(profile.id),
            actor_kind=ActorKind(profile.actor_kind),
            actor_status=ActorStatus(profile.status),
            identity_link_id=UUID(link.id),
            identity_link_status=IdentityLinkStatus(link.status),
            request_id=original.request_id,
            correlation_id=original.correlation_id,
        )

    @staticmethod
    def _locked_service_context(locked, original) -> ServiceAuthorizationContext:
        if locked is None:
            raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.IDENTITY_LINK_REVOKED)
        link, profile = locked
        if (
            profile.id != str(original.actor_profile_id)
            or link.id != str(original.identity_link_id)
            or link.actor_profile_id != profile.id
            or profile.actor_kind != ActorKind.SERVICE.value
            or profile.service_identity != original.service_identity.value
        ):
            raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.PERMISSION_NOT_GRANTED)
        return ServiceAuthorizationContext(
            actor_profile_id=UUID(profile.id),
            actor_kind=ActorKind.SERVICE,
            actor_status=ActorStatus(profile.status),
            identity_link_id=UUID(link.id),
            identity_link_status=IdentityLinkStatus(link.status),
            service_identity=original.service_identity,
            request_id=original.request_id,
            correlation_id=original.correlation_id,
        )

    def _discard_prelocked(self, authority: _PrelockedAuthority) -> None:
        """Release one unconsumed sealed authority during handle invalidation."""
        self._sealed_prelocked.discard(authority)

    async def _complete_prepared_denial(
        self,
        consumer_token: object,
        action_id: ActionId,
        resource_context: AuthorizationResourceContext,
        denial: AuthorizationDenialCode,
    ) -> NoReturn:
        """Persist one exact prepare-time denial without issuing a capability."""
        self._validate_prepared_consumer(consumer_token)
        action = ACTION_BY_ID.get(action_id)
        supported = (
            (
                action_id is ActionId.PROJECT_CREATE
                and isinstance(resource_context, ProjectCreateResourceContext)
            )
            or (
                action_id in _GUIDE_BOUND_PROJECT_MANAGER_MUTATIONS
                and isinstance(
                    resource_context,
                    (
                        ProjectGuideMutationPrepareDenialResourceContext,
                        ProjectGuideSufficiencyMutationResourceContext,
                    ),
                )
            )
            or (
                action_id
                in {
                    ActionId.PROJECT_REVIEW_POLICY_UPDATE,
                    ActionId.PROJECT_REVISION_POLICY_UPDATE,
                }
                and isinstance(resource_context, ProjectPolicyMutationPrepareDenialResourceContext)
            )
            or (
                action_id in _SUBMISSION_POLICY_MUTATIONS
                and isinstance(
                    resource_context,
                    ProjectSubmissionArtifactPolicyMutationResourceContext,
                )
            )
        )
        if not supported:
            raise TypeError("unsupported prepared denial")
        await self._complete_decision(
            action=action,
            denial=denial,
            resource_context=resource_context,
            context=self._context,
            matched_kind=None,
            matched_grant_id=None,
            matched_project_id=None,
            revalidated=False,
        )
        raise RuntimeError("denied prepared authorization unexpectedly returned")

    async def require(
        self,
        action_id: ActionId,
        resource_context: AuthorizationResourceContext,
    ) -> AuthorizationDecision:
        """Return an allowed decision or raise one bounded, evidenced denial."""
        self._pending_denial = None
        self._pending_denial_resource_context = None
        action = ACTION_BY_ID.get(action_id) if isinstance(action_id, ActionId) else None
        context = self._context
        revalidated = False
        matched_grant_id = None
        matched_project_id = None
        matched_kind = None
        if isinstance(context, ServiceAuthorizationContext):
            denial, context, revalidated = await self._service_denial(
                action_id,
                action,
                context,
                resource_context,
            )
        elif action is not None and action.action_id in _ADMIN_ACTIONS:
            (
                denial,
                context,
                matched_grant_id,
                matched_project_id,
                revalidated,
            ) = await self._admin_denial(action, resource_context, context)
            if denial is None:
                matched_kind = MatchedAuthorityKind.ADMIN_ROLE_GRANT
        elif action is not None and action.action_id is ActionId.PROJECT_READ:
            (
                denial,
                context,
                matched_kind,
                matched_grant_id,
                matched_project_id,
                revalidated,
            ) = await self._project_read_denial(action, resource_context, context)
        elif action is not None and action.action_id is ActionId.ACTOR_AUTHORIZATION_CONTEXT_READ:
            if (
                isinstance(context, HumanAuthorizationContext)
                and isinstance(resource_context, ActorAuthorizationContextResourceContext)
                and self._revalidate_actor_self is not None
            ):
                context = await self._revalidate_actor_self(context, resource_context)
                revalidated = True
            (
                denial,
                matched_kind,
                matched_grant_id,
                matched_project_id,
            ) = await self._authorization_context_denial(
                action, resource_context, context, revalidated
            )
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
        return await self._complete_decision(
            action=action,
            denial=denial,
            resource_context=resource_context,
            context=context,
            matched_kind=matched_kind,
            matched_grant_id=matched_grant_id,
            matched_project_id=matched_project_id,
            revalidated=revalidated,
        )

    async def _project_read_denial(
        self,
        action,
        resource: AuthorizationResourceContext,
        context: AuthorizationContext,
    ) -> tuple[
        AuthorizationDenialCode | None,
        AuthorizationContext,
        MatchedAuthorityKind | None,
        UUID | None,
        UUID | None,
        bool,
    ]:
        """Authorize one canonical project through admin or contributor grants."""
        if not isinstance(context, HumanAuthorizationContext) or not isinstance(
            resource, ProjectReadResourceContext
        ):
            return AuthorizationDenialCode.RESOURCE_GUARD_DENIED, context, None, None, None, False
        if action.availability is not ActionAvailability.ACTIVE:
            return AuthorizationDenialCode.ACTION_UNAVAILABLE, context, None, None, None, False
        if self._revalidate_actor_self is None:
            return AuthorizationDenialCode.RESOURCE_GUARD_DENIED, context, None, None, None, False
        context = await self._revalidate_actor_self(context, resource)
        lifecycle = self._lifecycle_denial(context)
        if lifecycle is not None:
            return lifecycle, context, None, None, None, True
        if not resource.project_exists:
            return (
                AuthorizationDenialCode.RESOURCE_NOT_FOUND,
                context,
                None,
                None,
                None,
                True,
            )
        # Keep the matched grant stable through response projection and commit so a
        # concurrent revoke cannot authorize a stale read from this transaction.
        admin_grant = await self._admin.find_effective_grant(
            context.actor_profile_id,
            action.permission_id,
            scope_project_id=resource.scope_project_id,
            system_scope_only=False,
            for_update=True,
        )
        if admin_grant is not None:
            return (
                None,
                context,
                MatchedAuthorityKind.ADMIN_ROLE_GRANT,
                admin_grant.id,
                resource.scope_project_id,
                True,
            )
        project_grant = await self._admin.find_active_project_role_any(
            project_id=resource.scope_project_id,
            actor_profile_id=context.actor_profile_id,
            for_update=True,
        )
        if project_grant is not None:
            return (
                None,
                context,
                MatchedAuthorityKind.PROJECT_ROLE_GRANT,
                project_grant.id,
                resource.scope_project_id,
                True,
            )
        out_of_scope = await self._admin.has_effective_permission_any_scope(
            context.actor_profile_id, action.permission_id
        ) or await self._admin.has_active_project_role_any_project(context.actor_profile_id)
        return (
            AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED
            if out_of_scope
            else AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
            context,
            None,
            None,
            None,
            True,
        )

    async def _authorization_context_denial(
        self,
        action,
        resource: AuthorizationResourceContext,
        context: AuthorizationContext,
        revalidated: bool,
    ) -> tuple[
        AuthorizationDenialCode | None,
        MatchedAuthorityKind | None,
        UUID | None,
        UUID | None,
    ]:
        """Authorize a caller-owned context projection for one exact project."""
        if (
            not isinstance(context, HumanAuthorizationContext)
            or not isinstance(resource, ActorAuthorizationContextResourceContext)
            or resource.resource_id != context.actor_profile_id
            or not revalidated
        ):
            return AuthorizationDenialCode.RESOURCE_GUARD_DENIED, None, None, None
        if action.availability is not ActionAvailability.ACTIVE:
            return AuthorizationDenialCode.ACTION_UNAVAILABLE, None, None, None
        lifecycle = self._lifecycle_denial(context)
        if lifecycle is not None:
            return lifecycle, None, None, None
        if not resource.project_exists:
            return AuthorizationDenialCode.RESOURCE_NOT_FOUND, None, None, None
        # The context projection reuses these rows after authorization; lock the
        # matched grant until commit so its advertised authority cannot go stale.
        admin_grant = await self._admin.find_effective_grant(
            context.actor_profile_id,
            PermissionId.PROJECT_READ,
            scope_project_id=resource.scope_project_id,
            system_scope_only=False,
            for_update=True,
        )
        if admin_grant is not None:
            return (
                None,
                MatchedAuthorityKind.ADMIN_ROLE_GRANT,
                admin_grant.id,
                resource.scope_project_id,
            )
        project_grant = await self._admin.find_active_project_role_any(
            project_id=resource.scope_project_id,
            actor_profile_id=context.actor_profile_id,
            for_update=True,
        )
        if project_grant is None:
            out_of_scope = await self._admin.has_effective_permission_any_scope(
                context.actor_profile_id, PermissionId.PROJECT_READ
            ) or await self._admin.has_active_project_role_any_project(context.actor_profile_id)
            return (
                AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED
                if out_of_scope
                else AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
                None,
                None,
                None,
            )
        return (
            None,
            MatchedAuthorityKind.PROJECT_ROLE_GRANT,
            project_grant.id,
            resource.scope_project_id,
        )

    async def _require_prelocked(
        self,
        consumer_token: object,
        action_id: ActionId,
        resource_context: AuthorizationResourceContext,
        authority: _PrelockedAuthority,
    ) -> AuthorizationDecision:
        """Evaluate final facts using exact authority already locked by AUTH."""
        self._validate_prepared_consumer(consumer_token)
        transaction = self._session.sync_session.get_transaction()
        if (
            type(authority) is not _PrelockedAuthority
            or authority not in self._sealed_prelocked
            or authority.issuer is not self
            or transaction is None
            or not transaction.is_active
            or transaction is not authority.transaction
            or self._session.in_nested_transaction()
        ):
            raise TypeError("invalid prelocked authority")
        self._sealed_prelocked.remove(authority)
        self._pending_denial = None
        self._pending_denial_resource_context = None
        action = ACTION_BY_ID.get(action_id) if isinstance(action_id, ActionId) else None
        context = authority.context
        denial: AuthorizationDenialCode | None
        matched_kind = None
        matched_grant_id = None
        matched_project_id = None
        if action is None or authority.action_id is not action_id:
            denial = AuthorizationDenialCode.UNKNOWN_ACTION
        elif authority.permission_id != action.permission_id:
            denial = AuthorizationDenialCode.PERMISSION_NOT_GRANTED
        elif isinstance(context, ServiceAuthorizationContext):
            denial = self._lifecycle_denial(context)
            expected_resource = _ARTIFACT_INTERNAL_RESOURCES.get(action_id)
            if denial is None and action.availability is not ActionAvailability.ACTIVE:
                denial = AuthorizationDenialCode.ACTION_UNAVAILABLE
            if denial is None and action_id not in SERVICE_ACTIONS_BY_IDENTITY.get(context.service_identity, ()):
                denial = AuthorizationDenialCode.PERMISSION_NOT_GRANTED
            setup_match = project_setup_resource_matches(
                action_id, resource_context, authority.scope_project_id
            )
            if denial is None and setup_match is False:
                denial = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
            elif (
                denial is None
                and setup_match is None
                and (
                    expected_resource is None
                    or not isinstance(resource_context, expected_resource[1])
                    or resource_context.resource_type != authority.artifact_resource_type
                    or resource_context.resource_id != authority.artifact_resource_id
                )
            ):
                denial = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
            if denial is None:
                matched_kind = MatchedAuthorityKind.FIXED_SERVICE
        elif action_id is ActionId.ACTOR_PROFILE_UPDATE_SELF:
            denial = self._denial(action_id, action, resource_context, context, True)
            if denial is None:
                matched_kind = MatchedAuthorityKind.ACTOR_SELF
        elif action_id in _ADMIN_MUTATIONS:
            denial = self._lifecycle_denial(context)
            if denial is None and action.availability is not ActionAvailability.ACTIVE:
                denial = AuthorizationDenialCode.ACTION_UNAVAILABLE
            if denial is None and not self._admin_resource_matches(action_id, resource_context):
                denial = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
            final_scope = self._resource_project_id(resource_context)
            if denial is None and final_scope != authority.scope_project_id:
                denial = AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED
            if denial is None and (
                authority.matched_grant_id is None or authority.matched_grant_status != "active"
            ):
                denial = AuthorizationDenialCode.PERMISSION_NOT_GRANTED
            if denial is None:
                denial = await self._admin_guard(action_id, resource_context, context)
            if denial is None:
                matched_kind = MatchedAuthorityKind.ADMIN_ROLE_GRANT
                matched_grant_id = authority.matched_grant_id
                matched_project_id = authority.scope_project_id
        elif action_id in _GUIDE_BOUND_PROJECT_MANAGER_MUTATIONS:
            denial = self._lifecycle_denial(context)
            expected = PROJECT_MUTATION_RESOURCE_BY_ACTION.get(
                action_id
            ) or compilation.COMPILATION_RESOURCE_BY_ACTION.get(action_id)
            if denial is None and action.availability is not ActionAvailability.ACTIVE:
                denial = AuthorizationDenialCode.ACTION_UNAVAILABLE
            if denial is None and (expected is None or not isinstance(resource_context, expected)):
                denial = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
            if denial is None and (resource_context.scope_project_id != authority.scope_project_id):
                denial = AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED
            guide_kind = PROJECT_GUIDE_TARGET_KIND_BY_ACTION.get(action_id)
            if (
                denial is None
                and guide_kind is not None
                and (resource_context.target_kind != guide_kind)
            ):
                denial = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
            sufficiency_kind = PROJECT_SUFFICIENCY_TARGET_KIND_BY_ACTION.get(action_id)
            if (
                denial is None
                and sufficiency_kind is not None
                and (
                    resource_context.target_kind != sufficiency_kind
                    or resource_context.execution_kind != "human"
                )
            ):
                denial = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
            submission_policy_kind = PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION.get(action_id)
            if (
                denial is None
                and submission_policy_kind is not None
                and (
                    resource_context.target_kind != submission_policy_kind
                    or resource_context.execution_kind != "human"
                )
            ):
                denial = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
            if denial is None and (
                authority.matched_grant_id is None or authority.matched_grant_status != "active"
            ):
                denial = AuthorizationDenialCode.PERMISSION_NOT_GRANTED
            if denial is None:
                matched_kind = MatchedAuthorityKind.ADMIN_ROLE_GRANT
                matched_grant_id = authority.matched_grant_id
                matched_project_id = authority.matched_grant_scope_project_id
        elif action_id is ActionId.PROJECT_CREATE:
            denial = self._lifecycle_denial(context)
            if denial is None and action.availability is not ActionAvailability.ACTIVE:
                denial = AuthorizationDenialCode.ACTION_UNAVAILABLE
            if denial is None and not isinstance(resource_context, ProjectCreateResourceContext):
                denial = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
            if denial is None and authority.scope_project_id is not None:
                denial = AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED
            if denial is None and (
                authority.matched_grant_id is None or authority.matched_grant_status != "active"
            ):
                denial = AuthorizationDenialCode.PERMISSION_NOT_GRANTED
            if denial is None:
                matched_kind = MatchedAuthorityKind.ADMIN_ROLE_GRANT
                matched_grant_id = authority.matched_grant_id
        elif action_id is ActionId.ARTIFACT_GUIDE_SOURCE_INGEST:
            denial, matched_kind, matched_grant_id, matched_project_id = (
                evaluate_guide_ingest_authority(action, authority, resource_context, self._lifecycle_denial(context))
            )
        elif action_id in {ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE, ActionId.SUBMISSION_CREATE}:
            denial, matched_kind, matched_grant_id, matched_project_id = (
                evaluate_submitter_authority(action, context, authority, resource_context, self._lifecycle_denial(context))
            )
        else:
            denial = AuthorizationDenialCode.ACTION_UNAVAILABLE
        return await self._complete_decision(
            action=action,
            denial=denial,
            resource_context=resource_context,
            context=context,
            matched_kind=matched_kind,
            matched_grant_id=matched_grant_id,
            matched_project_id=matched_project_id,
            revalidated=True,
        )

    async def _complete_decision(
        self,
        *,
        action,
        denial: AuthorizationDenialCode | None,
        resource_context: AuthorizationResourceContext,
        context: AuthorizationContext,
        matched_kind: MatchedAuthorityKind | None,
        matched_grant_id: UUID | None,
        matched_project_id: UUID | None,
        revalidated: bool,
    ) -> AuthorizationDecision:
        """Construct, evidence, and enforce one canonical authorization decision."""
        resource_digest = compilation.request_authority_digest(
            resource_context,
            actor_profile_id=context.actor_profile_id,
            identity_link_id=context.identity_link_id,
            grant_id=matched_grant_id if denial is None else None,
        ) or authorization_resource_digest(resource_context)
        decision = AuthorizationDecision(
            decision_id=uuid4(),
            action_id=action.action_id if action is not None else None,
            permission_id=action.permission_id if action is not None else None,
            allowed=denial is None,
            denial_code=denial,
            resource_type=resource_context.resource_type,
            resource_id=resource_context.resource_id,
            resource_context_digest=resource_digest,
            matched_authority_kind=matched_kind,
            matched_grant_id=matched_grant_id,
            matched_scope_project_id=matched_project_id,
            revalidated=revalidated,
            request_id=context.request_id,
            correlation_id=context.correlation_id,
        )
        await self._stage_decision(decision, context.actor_profile_id, resource_context)
        if not decision.allowed:
            self._pending_denial = decision
            self._pending_denial_resource_context = resource_context
            raise AuthorizationDenied(decision)
        return decision

    async def _service_denial(
        self,
        requested_action: object,
        action,
        context: ServiceAuthorizationContext,
        resource: AuthorizationResourceContext,
    ) -> tuple[AuthorizationDenialCode | None, ServiceAuthorizationContext, bool]:
        """Evaluate lifecycle/matrix state; direct feature access always denies.

        The resource is intentionally not honored here. Active ART service
        actions can allow only through a prepared capability consumption.
        """
        lifecycle = self._lifecycle_denial(context)
        if lifecycle is not None:
            return lifecycle, context, False
        if action is None:
            return AuthorizationDenialCode.UNKNOWN_ACTION, context, False
        if requested_action not in SERVICE_ACTIONS_BY_IDENTITY.get(context.service_identity, ()):
            return AuthorizationDenialCode.PERMISSION_NOT_GRANTED, context, False
        if action.availability is not ActionAvailability.ACTIVE:
            return AuthorizationDenialCode.ACTION_UNAVAILABLE, context, False
        if self._revalidate_service is None:
            return AuthorizationDenialCode.RESOURCE_GUARD_DENIED, context, False
        refreshed = await self._revalidate_service(context, action.action_id)
        if refreshed is None:
            return AuthorizationDenialCode.PERMISSION_NOT_GRANTED, context, True
        lifecycle = self._lifecycle_denial(refreshed)
        if lifecycle is not None:
            return lifecycle, refreshed, True
        if (
            refreshed.service_identity is not context.service_identity
            or action.action_id not in SERVICE_ACTIONS_BY_IDENTITY.get(refreshed.service_identity, ())
            or ACTION_BY_ID[action.action_id].availability is not ActionAvailability.ACTIVE
        ):
            return AuthorizationDenialCode.PERMISSION_NOT_GRANTED, refreshed, True
        return AuthorizationDenialCode.RESOURCE_GUARD_DENIED, refreshed, True

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
            if profile.actor_kind != ActorKind.HUMAN.value:
                return AuthorizationDenialCode.PERMISSION_NOT_GRANTED, context, None, None, True
            context = HumanAuthorizationContext(
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
        grant_filters: dict[str, object] = {}
        if action.action_id is ActionId.PROJECT_ACTIVE_GUIDE_READ:
            grant_filters["allowed_roles"] = ACTIVE_GUIDE_ADMIN_ROLES
        else:
            grant_filters.update(
                adapter_bindings.finance_authority_grant_filters(action.action_id)
            )
        matched = await self._admin.find_effective_grant(
            context.actor_profile_id,
            action.permission_id,
            scope_project_id=project_id,
            system_scope_only=system_only,
            for_update=serialized,
            **grant_filters,
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
        preserve_denied_match = action.action_id in {
            ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ,
            ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ,
            ActionId.PROJECT_ACTIVE_GUIDE_READ,
        }
        return (
            denial,
            context,
            matched.id if denial is None or preserve_denied_match else None,
            project_id if denial is None or preserve_denied_match else None,
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
        elif isinstance(resource, ProjectRoleGrantIssueResourceContext):
            if resource.target_actor_profile_id == context.actor_profile_id:
                return AuthorizationDenialCode.SELF_GRANT_FORBIDDEN
            if not project_action_available_for_status(action_id, resource.project_status):
                return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
            if not resource.target_eligible:
                return AuthorizationDenialCode.ACTOR_NOT_FOUND
        elif isinstance(resource, ProjectRoleGrantRevokeResourceContext):
            if resource.actor_profile_id == context.actor_profile_id:
                return AuthorizationDenialCode.SELF_ROLE_REVOKE_FORBIDDEN
        elif isinstance(resource, ActorProfileLifecycleResourceContext):
            if resource.resource_id == context.actor_profile_id and resource.transition in {
                "suspend",
                "deactivate",
            }:
                return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
            if await self._admin.lock_actor_lifecycle_target(resource.resource_id) is None:
                return AuthorizationDenialCode.ACTOR_NOT_FOUND
        elif isinstance(resource, ActorIdentityLinkLifecycleResourceContext):
            if resource.resource_id == context.identity_link_id and resource.transition == "revoke":
                return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
            if await self._admin.lock_identity_link_lifecycle_target(resource.resource_id) is None:
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
        elif isinstance(resource, ProjectContributorCandidateCollectionResourceContext):
            if not project_action_available_for_status(action_id, resource.project_status):
                return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
        elif isinstance(resource, ProjectDiagnosticReadResourceContext):
            if not (resource.project_exists and resource.guide_exists and resource.target_exists):
                return AuthorizationDenialCode.RESOURCE_NOT_FOUND
        elif isinstance(
            resource,
            (ProjectPolicyReadResourceContext, ProjectActiveGuideReadResourceContext),
        ):
            if not (resource.project_exists and resource.guide_exists and resource.target_exists):
                return AuthorizationDenialCode.RESOURCE_NOT_FOUND
        return None

    @staticmethod
    def _admin_resource_matches(
        action_id: ActionId,
        resource: AuthorizationResourceContext,
    ) -> bool:
        expected = _ADMIN_EXPECTED_RESOURCES.get(action_id)
        if expected is None or not isinstance(resource, expected):
            return False
        diagnostic_kind = PROJECT_DIAGNOSTIC_TARGET_KIND_BY_ACTION.get(action_id)
        if diagnostic_kind is not None and resource.target_kind != diagnostic_kind:
            return False
        policy_kind = PROJECT_POLICY_READ_TARGET_KIND_BY_ACTION.get(action_id)
        if policy_kind is not None and resource.target_kind != policy_kind:
            return False
        sufficiency_kind = PROJECT_SUFFICIENCY_TARGET_KIND_BY_ACTION.get(action_id)
        if sufficiency_kind is not None and resource.target_kind != sufficiency_kind:
            return False
        guide_kind = PROJECT_GUIDE_TARGET_KIND_BY_ACTION.get(action_id)
        if guide_kind is not None and resource.target_kind != guide_kind:
            return False
        submission_policy_kind = PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION.get(action_id)
        if submission_policy_kind is not None and resource.target_kind != submission_policy_kind:
            return False
        post_submit_policy_kind = PROJECT_POST_SUBMIT_POLICY_TARGET_KIND_BY_ACTION.get(action_id)
        if post_submit_policy_kind is not None and resource.target_kind != post_submit_policy_kind:
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

    async def restage_denial(self, decision: AuthorizationDecision) -> None:
        """Restage the exact pending denial after composition-root rollback."""
        if (
            decision.allowed
            or decision is not self._pending_denial
            or decision.request_id != self._context.request_id
            or decision.correlation_id != self._context.correlation_id
        ):
            raise TypeError("invalid authorization denial evidence")
        resource_context = self._pending_denial_resource_context
        if resource_context is None:
            raise TypeError("missing authorization denial resource context")
        await self._stage_decision(decision, self._context.actor_profile_id, resource_context)
        self._pending_denial = None
        self._pending_denial_resource_context = None

    async def _restage_denial(self, decision: AuthorizationDecision) -> None:
        """Retain the existing AUTH-internal dependency seam."""
        await self.restage_denial(decision)

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
        if (
            action.action_id
            in {
                ActionId.ACTOR_PROFILE_READ_SELF,
                ActionId.ACTOR_PROFILE_UPDATE_SELF,
            }
            and not revalidated
        ):
            return AuthorizationDenialCode.RESOURCE_GUARD_DENIED
        return None

    async def _stage_decision(
        self,
        decision: AuthorizationDecision,
        actor_profile_id,
        resource_context: AuthorizationResourceContext | None = None,
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
        audit_resource_id = None
        target_ref_kind = None
        target_ref_id = None
        audit_project_id = (
            str(decision.matched_scope_project_id)
            if decision.matched_scope_project_id is not None
            else None
        )
        if target_is_actor:
            audit_resource_type = "actor_profile"
        elif decision.resource_type in {"actor_identity_link", "admin_role_grant"}:
            audit_resource_type = decision.resource_type
        if isinstance(resource_context, ProjectCreateResourceContext):
            audit_resource_type = "project_create_operation"
            audit_resource_id = str(resource_context.resource_id)
            target_ref_kind = "project"
            target_ref_id = str(resource_context.requested_project_id)
        elif decision.action_id in _SUBMISSION_POLICY_MUTATIONS and isinstance(
            resource_context, ProjectSubmissionArtifactPolicyMutationResourceContext
        ):
            audit_project_id = str(resource_context.scope_project_id)
            audit_resource_type = resource_context.resource_type
            audit_resource_id = str(resource_context.resource_id)
            target_ref_kind = "project"
            target_ref_id = str(resource_context.scope_project_id)
        elif isinstance(
            resource_context,
            (
                PreSubmitCheckerInputResourceContext,
                compilation.ProjectGuideCompilationRequestResourceContext, compilation.ProjectGuideCompilationExecuteResourceContext,
                adapter_bindings.AdapterBindingReadResourceContext, adapter_bindings.AdapterBindingMutationResourceContext,
                ProjectGuideProjectionResourceContext,
            ),
        ):
            project_id = getattr(resource_context, "project_id", None) or getattr(resource_context, "scope_project_id")
            audit_project_id = str(project_id)
            audit_resource_type = resource_context.resource_type
            audit_resource_id = str(resource_context.resource_id)
            target_ref_kind, target_ref_id = "project", str(project_id)
        elif decision.action_id in _GUIDE_BOUND_PROJECT_MANAGER_MUTATIONS:
            if resource_context is not None:
                project_id = self._resource_project_id(resource_context)
                if project_id is not None:
                    audit_project_id = str(project_id)
                    audit_resource_type = "project"
                    audit_resource_id = str(project_id)
                    target_ref_kind = "project"
                    target_ref_id = str(project_id)
        after_facts: dict[str, object] = {"allowed": decision.allowed}
        if isinstance(resource_context, ProjectGuideProjectionResourceContext) or decision.resource_type in CONTEXT_DIGEST_RESOURCE_TYPES or decision.action_id in {
            ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
            ActionId.PROJECT_CREATE,
            *_GUIDE_BOUND_PROJECT_MANAGER_MUTATIONS,
            *_SUBMISSION_POLICY_MUTATIONS,
            *adapter_bindings.ADAPTER_BINDING_ACTIONS,
        }:
            after_facts["resource_context_digest"] = decision.resource_context_digest
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
                        if decision.matched_grant_id is not None
                        else None
                    ),
                    permission_id=decision.permission_id,
                    action_id=decision.action_id,
                    project_id=audit_project_id,
                    resource_type=audit_resource_type,
                    resource_id=(
                        audit_resource_id
                        or (str(decision.resource_id) if audit_resource_type else None)
                    ),
                    target_ref_kind=target_ref_kind or audit_resource_type,
                    target_ref_id=(
                        target_ref_id
                        or (str(decision.resource_id) if audit_resource_type else None)
                    ),
                    reason="authorization_evaluation",
                    denial_code=stored_denial,
                    after_facts=after_facts,
                )
            )
        except SQLAlchemyError as exc:
            raise AuthorizationEvidenceUnavailable("authorization evidence unavailable") from exc
