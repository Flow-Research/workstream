"""Transaction-bound, single-use authorization for sensitive mutations."""

from __future__ import annotations

from copy import Error as CopyError
from contextlib import asynccontextmanager
from dataclasses import dataclass
from collections.abc import AsyncIterator
from typing import NoReturn
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.actors.repository import ActorRepository
from app.modules.actors.service_identities import ServiceIdentity
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
from app.modules.authorization.domain.guide_compilation import (
    COMPILATION_RESOURCE_BY_ACTION,
    ProjectGuideCompilationExecuteResourceContext,
    ProjectGuideCompilationRequestResourceContext,
)
from app.modules.authorization.domain.prepared_compilation import prepared_compilation_matches
from app.modules.authorization.domain.adapter_bindings import (
    ADAPTER_BINDING_MUTATION_ACTIONS,
    AdapterBindingMutationResourceContext,
)
from app.modules.authorization.domain.prepared_adapter_bindings import (
    parse_prepared_adapter_binding,
    prepared_adapter_binding_matches,
)
from app.modules.authorization.domain.prepared_service import project_setup_resource_matches
from app.modules.authorization.domain.guide_compilation_projections import (
    ProjectGuideProjectionResourceContext,
    projection_context_matches,
)
from app.modules.authorization.prepared_projection_replay import (
    parse_projection_bindings,
    validate_projection_replay,
)
from app.modules.authorization.runtime import (
    ActorSelfResourceContext,
    ActorKind,
    ActorStatus,
    ArtifactPendingWorkResourceContext,
    ArtifactPutAttemptResourceContext,
    ArtifactVerificationJobResourceContext,
    GuideSourceBindingResourceContext,
    GuideSourceReadResourceContext,
    SubmissionBindingResourceContext,
    SubmissionCreationResourceContext,
    GuideSourceIngestResourceContext,
    PreSubmitCheckerInputResourceContext,
    AuthorizationContext,
    AuthorizationDenialCode,
    AuthorizationDecision,
    AuthorizationResourceContext,
    authorization_resource_digest,
    IdentityLinkStatus,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    PROJECT_MUTATION_RESOURCE_BY_ACTION,
    PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION,
    ProjectCreateResourceContext,
    ProjectGuideMutationResourceContext,
    ProjectGuideSufficiencyMutationResourceContext,
    ProjectSubmissionArtifactPolicyMutationResourceContext,
    ProjectGuideMutationPrepareDenialResourceContext,
    ProjectGuideSourceSnapshotMutationResourceContext,
    ProjectSetupServiceCustodyContext,
    ProjectPolicyMutationPrepareDenialResourceContext,
    ProjectReviewPolicyMutationResourceContext,
    ProjectRevisionPolicyMutationResourceContext,
    ServiceAuthorizationContext,
)
from app.modules.authorization.submission_preparation import (
    parse_submission_preparation_or_invalid,
    submission_preparation_binding_fields,
    submission_preparation_binding_matches,
    SubmissionBundlePreparationPreflightResourceContext,
    SubmissionBundlePreparationResourceContext,
)
from app.modules.authorization.submission_consumption import parse_consumption_binding
from app.modules.authorization.pre_submit_materialization import (
    initialize_artifact_bindings,
    parse_materialization_binding,
    parse_project_create_binding,
    parse_submission_binding,
)


@dataclass(frozen=True, slots=True)
class FixedServicePreparedAuthorization:
    """One AUTH-owned fixed-service principal and its request-local PREP service."""

    actor_profile_id: UUID
    identity_link_id: UUID
    service: PreparedAuthorizationService


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

_EXACT_ARTIFACT_RESOURCE_BY_ACTION = {
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
    ActionId.ARTIFACT_SUBMISSION_BINDING_CREATE: (
        "submission_binding",
        SubmissionBindingResourceContext,
    ),
}


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
    policy_mutation_project_id: UUID | None = None
    policy_mutation_guide_id: UUID | None = None
    policy_mutation_policy_id: UUID | None = None
    policy_mutation_operation_id: UUID | None = None
    policy_mutation_request_digest: str | None = None
    policy_mutation_policy_digest: str | None = None
    policy_mutation_generation: int | None = None
    policy_mutation_predecessor_id: UUID | None = None
    policy_mutation_predecessor_generation: int | None = None
    policy_mutation_predecessor_digest: str | None = None
    policy_mutation_guide_status: str | None = None
    sufficiency_project_id: UUID | None = None
    sufficiency_guide_id: UUID | None = None
    sufficiency_guide_version: str | None = None
    sufficiency_snapshot_id: UUID | None = None
    sufficiency_snapshot_hash: str | None = None
    sufficiency_report_id: UUID | None = None
    sufficiency_operation_id: UUID | None = None
    sufficiency_request_digest: str | None = None
    sufficiency_target_kind: str | None = None
    sufficiency_execution_kind: str | None = None
    sufficiency_setup_generation: int | None = None
    sufficiency_stale_output_digest: str | None = None
    sufficiency_material_digest: str | None = None
    sufficiency_setup_service_custody: dict | None = None
    submission_policy_context: dict | None = None
    submission_policy_resource_digest: str | None = None
    exact_artifact_context: dict | None = None
    exact_artifact_resource_digest: str | None = None
    submission_preparation_context: dict | None = None
    submission_preparation_resource_digest: str | None = None
    submission_preparation_final_context: dict | None = None
    submission_preparation_final_digest: str | None = None
    guide_compilation_context: dict | None = None
    guide_compilation_resource_digest: str | None = None
    adapter_binding_context: dict | None = None
    adapter_binding_resource_digest: str | None = None
    guide_projection_prepare_context: dict | None = None


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


def _policy_mutation_binding_matches(
    binding: _PreparedAuthorizationBinding,
    resource: ProjectReviewPolicyMutationResourceContext
    | ProjectRevisionPolicyMutationResourceContext,
) -> bool:
    """Return whether final policy lineage matches prepared route facts."""
    return (
        binding.policy_mutation_project_id == resource.scope_project_id
        and binding.policy_mutation_guide_id == resource.guide_id
        and binding.policy_mutation_policy_id == resource.resource_id
        and binding.policy_mutation_operation_id == resource.operation_id
        and binding.policy_mutation_request_digest == resource.request_digest
        and binding.policy_mutation_policy_digest == resource.policy_digest
        and binding.policy_mutation_generation == resource.policy_generation
        and binding.policy_mutation_predecessor_id == resource.predecessor_policy_id
        and binding.policy_mutation_predecessor_generation == resource.predecessor_policy_generation
        and binding.policy_mutation_predecessor_digest == resource.current_policy_digest
        and binding.policy_mutation_guide_status == resource.guide_status
    )


def _policy_mutation_denial_binding_matches(
    binding: _PreparedAuthorizationBinding,
    resource: ProjectPolicyMutationPrepareDenialResourceContext,
) -> bool:
    """Return whether bounded denial facts match the prepared policy request."""
    expected_action = (
        ActionId.PROJECT_REVIEW_POLICY_UPDATE
        if resource.requested_policy_kind == "review"
        else ActionId.PROJECT_REVISION_POLICY_UPDATE
    )
    return (
        binding.action_id is expected_action
        and binding.policy_mutation_project_id == resource.scope_project_id
        and binding.policy_mutation_guide_id == resource.requested_guide_id
        and binding.policy_mutation_request_digest == resource.request_digest
    )


def _sufficiency_binding_matches(
    binding: _PreparedAuthorizationBinding,
    resource: ProjectGuideSufficiencyMutationResourceContext,
) -> bool:
    """Return whether final sufficiency lineage matches every prepared fact."""
    custody = (
        resource.setup_service_custody.model_dump(mode="json")
        if resource.setup_service_custody is not None
        else None
    )
    return (
        binding.sufficiency_project_id == resource.scope_project_id
        and binding.sufficiency_guide_id == resource.guide_id
        and binding.sufficiency_guide_version == resource.guide_version
        and binding.sufficiency_snapshot_id == resource.source_snapshot_id
        and binding.sufficiency_snapshot_hash == resource.source_snapshot_hash
        and binding.sufficiency_report_id == resource.sufficiency_report_id
        and binding.sufficiency_operation_id == resource.operation_id
        and binding.sufficiency_request_digest == resource.request_digest
        and binding.sufficiency_target_kind == resource.target_kind
        and binding.sufficiency_execution_kind == resource.execution_kind
        and binding.sufficiency_setup_generation == resource.setup_generation
        and binding.sufficiency_stale_output_digest == resource.stale_output_digest
        and binding.sufficiency_material_digest == resource.material_digest
        and binding.sufficiency_setup_service_custody == custody
    )


def _submission_policy_binding_matches(
    binding: _PreparedAuthorizationBinding,
    resource: ProjectSubmissionArtifactPolicyMutationResourceContext,
) -> bool:
    """Return whether final submission-policy facts exactly match preparation."""
    return binding.submission_policy_context == resource.model_dump(
        mode="json"
    ) and binding.submission_policy_resource_digest == authorization_resource_digest(resource)


def _exact_artifact_binding_matches(
    binding: _PreparedAuthorizationBinding,
    resource: PreSubmitCheckerInputResourceContext
    | SubmissionBindingResourceContext
    | SubmissionCreationResourceContext,
) -> bool:
    """Require every materialization fact to equal the prepared request."""
    if isinstance(resource, PreSubmitCheckerInputResourceContext):
        context = resource.model_dump(mode="json", exclude={"semantic_manifest_sha256"})
        return binding.exact_artifact_context == context and (
            binding.exact_artifact_resource_digest
            == canonical_json_hash({"pre_submit_checker_input_preparation": context})
        )
    context = resource.model_dump(mode="json")
    return binding.exact_artifact_context == context and (
        binding.exact_artifact_resource_digest == authorization_resource_digest(resource)
    )


def _submission_preparation_binding_matches(
    binding: _PreparedAuthorizationBinding,
    resource: SubmissionBundlePreparationPreflightResourceContext
    | SubmissionBundlePreparationResourceContext,
) -> bool:
    return submission_preparation_binding_matches(
        request_context=binding.submission_preparation_context,
        request_digest=binding.submission_preparation_resource_digest,
        final_context=binding.submission_preparation_final_context,
        final_digest=binding.submission_preparation_final_digest,
        resource=resource,
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

    async def preflight(
        self,
        action_id: ActionId,
        caller_input: PreparedAuthorizationInput,
        scope: PreparedAuthorityScope,
        resource: AuthorizationResourceContext,
    ) -> None:
        """Revalidate current authority without issuing a handle or staging evidence."""
        self._root_transaction()
        binding = self._binding(action_id, caller_input, scope)
        scope_matches = self._scope_from_resource(action_id, resource) == scope
        if isinstance(resource, SubmissionBundlePreparationPreflightResourceContext):
            resource_matches = _submission_preparation_binding_matches(binding, resource)
        else:
            resource_matches = prepared_compilation_matches(
                binding.guide_compilation_context,
                binding.guide_compilation_resource_digest,
                resource,
            )
        if not scope_matches or not resource_matches:
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization preflight")
        authority = await self._authorization._prepare_prelocked(
            self._consumer_token, action_id, scope
        )
        try:
            setup_match = project_setup_resource_matches(
                action_id, resource, authority.scope_project_id
            )
            if setup_match is False or (
                setup_match is None and action_id is not ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE
            ):
                raise PreparedAuthorizationUnsupported(
                    AuthorizationDenialCode.RESOURCE_GUARD_DENIED
                )
        finally:
            self._authorization._discard_prelocked(authority)

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
            (
                ProjectGuideMutationResourceContext,
                ProjectGuideSourceSnapshotMutationResourceContext,
            ),
        ) and not _guide_mutation_binding_matches(issuance.binding, final_resource_context):
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        if isinstance(
            final_resource_context, AdapterBindingMutationResourceContext
        ) and not prepared_adapter_binding_matches(
            issuance.binding.adapter_binding_context,
            issuance.binding.adapter_binding_resource_digest,
            final_resource_context,
        ):
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        if isinstance(
            final_resource_context,
            (
                ProjectReviewPolicyMutationResourceContext,
                ProjectRevisionPolicyMutationResourceContext,
            ),
        ) and not _policy_mutation_binding_matches(issuance.binding, final_resource_context):
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        if isinstance(
            final_resource_context, ProjectGuideSufficiencyMutationResourceContext
        ) and not _sufficiency_binding_matches(issuance.binding, final_resource_context):
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        if isinstance(
            final_resource_context, ProjectSubmissionArtifactPolicyMutationResourceContext
        ) and not _submission_policy_binding_matches(issuance.binding, final_resource_context):
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        if isinstance(
            final_resource_context,
            (
                PreSubmitCheckerInputResourceContext,
                SubmissionBindingResourceContext,
                SubmissionCreationResourceContext,
            ),
        ) and not _exact_artifact_binding_matches(issuance.binding, final_resource_context):
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        if isinstance(
            final_resource_context, SubmissionBundlePreparationResourceContext
        ) and not _submission_preparation_binding_matches(issuance.binding, final_resource_context):
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        if isinstance(
            final_resource_context,
            (
                ProjectGuideCompilationRequestResourceContext,
                ProjectGuideCompilationExecuteResourceContext,
            ),
        ) and not prepared_compilation_matches(
            issuance.binding.guide_compilation_context,
            issuance.binding.guide_compilation_resource_digest,
            final_resource_context,
        ):
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        if not (
            projection_context_matches(
                issuance.binding.guide_projection_prepare_context,
                final_resource_context,
            )
        ):
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        self._issued[handle] = _CONSUMED
        return await self._authorization._require_prelocked(
            self._consumer_token,
            expected_action_id,
            final_resource_context,
            issuance.authority,
        )

    async def validate_replay(
        self,
        handle: PreparedAuthorizationHandle,
        expected_action_id: ActionId,
        caller_input: PreparedAuthorizationInput,
        final_resource_context: AuthorizationResourceContext,
        stored_decision_id: UUID,
    ) -> None:
        if self._closed or type(handle) is not PreparedAuthorizationHandle:
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        issuance = self._issued.get(handle)
        if not isinstance(issuance, _Issuance):
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        self._issued[handle] = _CONSUMED
        try:
            await validate_projection_replay(
                self,
                issuance,
                expected_action_id,
                caller_input,
                final_resource_context,
                stored_decision_id,
            )
        finally:
            self._authorization._discard_prelocked(issuance.authority)

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
        if isinstance(
            final_resource_context, ProjectPolicyMutationPrepareDenialResourceContext
        ) and not _policy_mutation_denial_binding_matches(binding, final_resource_context):
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        if isinstance(
            final_resource_context, ProjectGuideSufficiencyMutationResourceContext
        ) and not _sufficiency_binding_matches(binding, final_resource_context):
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        if isinstance(
            final_resource_context, ProjectSubmissionArtifactPolicyMutationResourceContext
        ) and not _submission_policy_binding_matches(binding, final_resource_context):
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

    def close_handle(self, handle: PreparedAuthorizationHandle) -> None:
        """Invalidate one exact capability without closing the request service."""
        if self._closed or type(handle) is not PreparedAuthorizationHandle:
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        issuance = self._issued.pop(handle, None)
        if issuance is None:
            raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        if isinstance(issuance, _Issuance):
            self._authorization._discard_prelocked(issuance.authority)

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
            self._issued[handle] = _CONSUMED
        return transaction

    def _binding(
        self,
        action_id: ActionId,
        caller_input: PreparedAuthorizationInput,
        scope: PreparedAuthorityScope,
    ) -> _PreparedAuthorizationBinding:
        operation_id = project_id = operation_generation = None
        guide_mutation_project_id = guide_mutation_guide_id = guide_mutation_target_resource_id = (
            guide_mutation_operation_id
        ) = None
        policy_mutation_project_id = policy_mutation_guide_id = policy_mutation_policy_id = policy_mutation_operation_id = None
        policy_mutation_request_digest = policy_mutation_policy_digest = policy_mutation_predecessor_digest = None
        policy_mutation_generation = policy_mutation_predecessor_generation = policy_mutation_predecessor_id = policy_mutation_guide_status = None
        sufficiency: dict[str, object] = {}
        submission_policy_context = submission_policy_resource_digest = None
        exact_artifact_context, exact_artifact_resource_digest, submission_preparation_context, submission_preparation_resource_digest, submission_preparation_final_context, submission_preparation_final_digest = initialize_artifact_bindings()
        projection_binding, compilation_binding = parse_projection_bindings(action_id, caller_input.request_value)
        if action_id is ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE:
            exact_artifact_context, exact_artifact_resource_digest = parse_materialization_binding(
                dict(caller_input.request_value), PreparedAuthorizationHandleInvalid
            )
        consumption_resource = parse_consumption_binding(
            action_id, caller_input.request_value, PreparedAuthorizationHandleInvalid
        )
        if consumption_resource is not None:
            exact_artifact_context = consumption_resource.model_dump(mode="json")
            exact_artifact_resource_digest = authorization_resource_digest(consumption_resource)
        if action_id is ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE:
            submission_binding = parse_submission_binding(
                dict(caller_input.request_value),
                PreparedAuthorizationHandleInvalid,
                parse_submission_preparation_or_invalid,
            )
            submission_preparation_context = submission_binding[0]
            submission_preparation_resource_digest = submission_binding[1]
            submission_preparation_final_context = submission_binding[2]
            submission_preparation_final_digest = submission_binding[3]
        if action_id is ActionId.PROJECT_CREATE:
            operation_id, project_id, operation_generation = parse_project_create_binding(
                dict(caller_input.request_value), PreparedAuthorizationHandleInvalid
            )
        if action_id in {
            ActionId.PROJECT_GUIDE_CREATE,
            ActionId.PROJECT_GUIDE_UPDATE,
            ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE,
        }:
            try:
                guide_mutation_project_id = UUID(str(caller_input.request_value["project_id"]))
                raw_guide_id = caller_input.request_value.get("guide_id")
                guide_mutation_guide_id = (
                    UUID(str(raw_guide_id)) if raw_guide_id is not None else None
                )
                guide_mutation_target_resource_id = UUID(
                    str(caller_input.request_value["target_resource_id"])
                )
                guide_mutation_operation_id = UUID(str(caller_input.request_value["operation_id"]))
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
                raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
        if not projection_binding and action_id in {
            ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE,
            ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE,
            ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE,
            ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_APPROVE,
        }:
            try:
                value = dict(caller_input.request_value)
                for field in (
                    "resource_id",
                    "operation_id",
                    "scope_project_id",
                    "guide_id",
                    "source_snapshot_id",
                    "policy_id",
                    "sufficiency_report_id",
                ):
                    value[field] = UUID(str(value[field]))
                raw_successor_policy_id = value.get("successor_policy_id")
                if raw_successor_policy_id is not None:
                    value["successor_policy_id"] = UUID(str(raw_successor_policy_id))
                raw_custody = value.get("setup_service_custody")
                if raw_custody is not None:
                    custody = dict(raw_custody)
                    for field in (
                        "setup_run_id",
                        "scope_project_id",
                        "guide_id",
                        "source_snapshot_id",
                        "task_id",
                        "correlation_id",
                    ):
                        custody[field] = UUID(str(custody[field]))
                    value["setup_service_custody"] = custody
                resource = ProjectSubmissionArtifactPolicyMutationResourceContext.model_validate(
                    value
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise PreparedAuthorizationHandleInvalid(
                    "invalid prepared authorization handle"
                ) from exc
            expected_target = PROJECT_SUBMISSION_POLICY_TARGET_KIND_BY_ACTION[action_id]
            if resource.target_kind != expected_target:
                raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")
            submission_policy_context = resource.model_dump(mode="json")
            submission_policy_resource_digest = authorization_resource_digest(resource)
        if not projection_binding and action_id in {
            ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_CREATE,
            ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN,
            ActionId.PROJECT_GUIDE_SUFFICIENCY_WARNINGS_ACKNOWLEDGE,
        }:
            try:
                raw_report_id = caller_input.request_value["report_id"]
                raw_custody = caller_input.request_value["setup_service_custody"]
                custody = None
                if raw_custody:
                    custody_value = dict(raw_custody)
                    for field in (
                        "setup_run_id",
                        "scope_project_id",
                        "guide_id",
                        "source_snapshot_id",
                        "task_id",
                        "correlation_id",
                    ):
                        custody_value[field] = UUID(str(custody_value[field]))
                    custody = ProjectSetupServiceCustodyContext.model_validate(custody_value)
                sufficiency = {
                    "project_id": UUID(str(caller_input.request_value["project_id"])),
                    "guide_id": UUID(str(caller_input.request_value["guide_id"])),
                    "guide_version": str(caller_input.request_value["guide_version"]),
                    "snapshot_id": UUID(str(caller_input.request_value["source_snapshot_id"])),
                    "snapshot_hash": str(caller_input.request_value["source_snapshot_hash"]),
                    "report_id": UUID(str(raw_report_id)) if raw_report_id else None,
                    "operation_id": UUID(str(caller_input.request_value["operation_id"])),
                    "request_digest": str(caller_input.request_value["request_digest"]),
                    "target_kind": str(caller_input.request_value["target_kind"]),
                    "execution_kind": str(caller_input.request_value["execution_kind"]),
                    "setup_generation": int(caller_input.request_value["setup_generation"]),
                    "stale_output_digest": caller_input.request_value["stale_output_digest"],
                    "material_digest": caller_input.request_value["material_digest"],
                    "setup_service_custody": custody,
                }
                ProjectGuideSufficiencyMutationResourceContext(
                    resource_type="project_guide_sufficiency_mutation",
                    resource_id=sufficiency["report_id"] or sufficiency["snapshot_id"],
                    scope_project_id=sufficiency["project_id"],
                    guide_id=sufficiency["guide_id"],
                    guide_version=sufficiency["guide_version"],
                    source_snapshot_id=sufficiency["snapshot_id"],
                    source_snapshot_hash=sufficiency["snapshot_hash"],
                    sufficiency_report_id=sufficiency["report_id"],
                    operation_id=sufficiency["operation_id"],
                    request_digest=sufficiency["request_digest"],
                    target_kind=sufficiency["target_kind"],
                    execution_kind=sufficiency["execution_kind"],
                    setup_generation=sufficiency["setup_generation"],
                    stale_output_digest=sufficiency["stale_output_digest"],
                    material_digest=sufficiency["material_digest"],
                    setup_service_custody=sufficiency["setup_service_custody"],
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise PreparedAuthorizationHandleInvalid(
                    "invalid prepared authorization handle"
                ) from exc
        if action_id in {
            ActionId.PROJECT_REVIEW_POLICY_UPDATE,
            ActionId.PROJECT_REVISION_POLICY_UPDATE,
        }:
            try:
                policy_mutation_project_id = UUID(str(caller_input.request_value["project_id"]))
                policy_mutation_guide_id = UUID(str(caller_input.request_value["guide_id"]))
                policy_mutation_policy_id = UUID(str(caller_input.request_value["policy_id"]))
                policy_mutation_operation_id = UUID(str(caller_input.request_value["operation_id"]))
                policy_mutation_request_digest = str(caller_input.request_value["request_digest"])
                policy_mutation_policy_digest = str(caller_input.request_value["policy_digest"])
                policy_mutation_generation = int(caller_input.request_value["policy_generation"])
                raw_predecessor_id = caller_input.request_value["predecessor_policy_id"]
                policy_mutation_predecessor_id = (
                    UUID(str(raw_predecessor_id)) if raw_predecessor_id is not None else None
                )
                raw_predecessor_generation = caller_input.request_value[
                    "predecessor_policy_generation"
                ]
                policy_mutation_predecessor_generation = (
                    int(raw_predecessor_generation)
                    if raw_predecessor_generation is not None
                    else None
                )
                raw_predecessor_digest = caller_input.request_value["predecessor_policy_digest"]
                policy_mutation_predecessor_digest = (
                    str(raw_predecessor_digest) if raw_predecessor_digest is not None else None
                )
                policy_mutation_guide_status = str(caller_input.request_value["guide_status"])
            except (KeyError, TypeError, ValueError) as exc:
                raise PreparedAuthorizationHandleInvalid(
                    "invalid prepared authorization handle"
                ) from exc
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
            policy_mutation_project_id=policy_mutation_project_id,
            policy_mutation_guide_id=policy_mutation_guide_id,
            policy_mutation_policy_id=policy_mutation_policy_id,
            policy_mutation_operation_id=policy_mutation_operation_id,
            policy_mutation_request_digest=policy_mutation_request_digest,
            policy_mutation_policy_digest=policy_mutation_policy_digest,
            policy_mutation_generation=policy_mutation_generation,
            policy_mutation_predecessor_id=policy_mutation_predecessor_id,
            policy_mutation_predecessor_generation=(policy_mutation_predecessor_generation),
            policy_mutation_predecessor_digest=policy_mutation_predecessor_digest,
            policy_mutation_guide_status=policy_mutation_guide_status,
            sufficiency_project_id=sufficiency.get("project_id"),
            sufficiency_guide_id=sufficiency.get("guide_id"),
            sufficiency_guide_version=sufficiency.get("guide_version"),
            sufficiency_snapshot_id=sufficiency.get("snapshot_id"),
            sufficiency_snapshot_hash=sufficiency.get("snapshot_hash"),
            sufficiency_report_id=sufficiency.get("report_id"),
            sufficiency_operation_id=sufficiency.get("operation_id"),
            sufficiency_request_digest=sufficiency.get("request_digest"),
            sufficiency_target_kind=sufficiency.get("target_kind"),
            sufficiency_execution_kind=sufficiency.get("execution_kind"),
            sufficiency_setup_generation=sufficiency.get("setup_generation"),
            sufficiency_stale_output_digest=sufficiency.get("stale_output_digest"),
            sufficiency_material_digest=sufficiency.get("material_digest"),
            sufficiency_setup_service_custody=(
                sufficiency["setup_service_custody"].model_dump(mode="json")
                if sufficiency.get("setup_service_custody") is not None
                else None
            ),
            submission_policy_context=submission_policy_context,
            submission_policy_resource_digest=submission_policy_resource_digest,
            exact_artifact_context=exact_artifact_context,
            exact_artifact_resource_digest=exact_artifact_resource_digest,
            **submission_preparation_binding_fields(
                (
                    submission_preparation_context,
                    submission_preparation_resource_digest,
                    submission_preparation_final_context,
                    submission_preparation_final_digest,
                )
            ),
            **compilation_binding,
            **parse_prepared_adapter_binding(action_id, caller_input.request_value),
            **projection_binding,
        )

    @staticmethod
    def _scope_from_resource(
        action_id: ActionId,
        resource: AuthorizationResourceContext,
    ) -> PreparedAuthorityScope:
        artifact_resource = _EXACT_ARTIFACT_RESOURCE_BY_ACTION.get(action_id)
        if artifact_resource is not None and isinstance(resource, artifact_resource[1]):
            return PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.ARTIFACT_INTERNAL,
                artifact_resource_type=artifact_resource[0],
                artifact_resource_id=resource.resource_id,
            )
        if isinstance(resource, ProjectGuideProjectionResourceContext):
            return PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT,
                project_id=resource.scope_project_id,
            )
        if action_id is ActionId.ACTOR_PROFILE_UPDATE_SELF and isinstance(
            resource, ActorSelfResourceContext
        ):
            return PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.ACTOR_SELF,
                actor_profile_id=resource.resource_id,
            )
        if admin_scope := _admin_prepared_scope(action_id, resource):
            return admin_scope
        expected_project_mutation = PROJECT_MUTATION_RESOURCE_BY_ACTION.get(
            action_id
        ) or COMPILATION_RESOURCE_BY_ACTION.get(action_id)
        if action_id in ADAPTER_BINDING_MUTATION_ACTIONS and isinstance(
            resource, AdapterBindingMutationResourceContext
        ):
            return PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT,
                project_id=resource.scope_project_id,
            )
        if action_id in {
            ActionId.PROJECT_GUIDE_CREATE,
            ActionId.PROJECT_GUIDE_UPDATE,
            ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE,
        } and isinstance(resource, ProjectGuideMutationPrepareDenialResourceContext):
            return PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT,
                project_id=resource.scope_project_id,
            )
        if action_id in {
            ActionId.PROJECT_REVIEW_POLICY_UPDATE,
            ActionId.PROJECT_REVISION_POLICY_UPDATE,
        } and isinstance(resource, ProjectPolicyMutationPrepareDenialResourceContext):
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
        if action_id is ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE and isinstance(
            resource,
            (
                SubmissionBundlePreparationPreflightResourceContext,
                SubmissionBundlePreparationResourceContext,
            ),
        ):
            return PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT,
                project_id=resource.scope_project_id,
            )
        if isinstance(resource, SubmissionCreationResourceContext):
            return PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT,
                project_id=resource.scope_project_id,
            )
        raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle")


def _admin_prepared_scope(action_id, resource):
    """Return the exact administrative prepared scope when applicable."""
    if action_id not in _ADMIN_MUTATIONS or not AuthorizationService._admin_resource_matches(
        action_id, resource
    ):
        return None
    project_id = AuthorizationService._resource_project_id(resource)
    target_actor_profile_id = role = grant_id = None
    if action_id is ActionId.PROJECT_ROLE_GRANT_ISSUE:
        target_actor_profile_id, role = resource.target_actor_profile_id, resource.role
    elif action_id is ActionId.PROJECT_ROLE_GRANT_REVOKE:
        grant_id = resource.resource_id
    return PreparedAuthorityScope(
        kind=(
            PreparedAuthorityScopeKind.PROJECT if project_id else PreparedAuthorityScopeKind.SYSTEM
        ),
        project_id=project_id,
        target_actor_profile_id=target_actor_profile_id,
        role=role,
        grant_id=grant_id,
    )


async def fixed_service_authorization_context(
    session: AsyncSession,
    service_identity: ServiceIdentity,
    request_id: UUID,
    correlation_id: UUID,
) -> ServiceAuthorizationContext:
    """Resolve one provisioned fixed service without synthesizing role claims."""
    actors = ActorRepository(session)
    profile = await actors.get_service_actor(service_identity.value)
    if profile is None or profile.service_identity != service_identity.value:
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.ACTOR_NOT_FOUND)
    link = await actors.get_identity_link_for_actor(profile.id)
    if (
        link is None
        or link.actor_profile_id != profile.id
        or link.subject_kind != ActorKind.SERVICE.value
    ):
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.IDENTITY_LINK_REVOKED)
    try:
        return ServiceAuthorizationContext(
            actor_profile_id=UUID(profile.id),
            actor_kind=ActorKind.SERVICE,
            actor_status=ActorStatus(profile.status),
            identity_link_id=UUID(link.id),
            identity_link_status=IdentityLinkStatus(link.status),
            service_identity=service_identity,
            request_id=request_id,
            correlation_id=correlation_id,
        )
    except (TypeError, ValueError) as exc:
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.ACTOR_NOT_FOUND) from exc


async def fixed_service_action_context(
    session: AsyncSession,
    *,
    service_identity: ServiceIdentity,
    action_id: ActionId,
    request_id: UUID,
    correlation_id: UUID,
) -> ServiceAuthorizationContext:
    """Resolve one active fixed service for one active matrix action."""
    context = await fixed_service_authorization_context(
        session, service_identity, request_id, correlation_id
    )
    action = ACTION_BY_ID[action_id]
    if (
        context.actor_status is not ActorStatus.ACTIVE
        or context.identity_link_status is not IdentityLinkStatus.ACTIVE
        or action.availability is not ActionAvailability.ACTIVE
        or action_id not in SERVICE_ACTIONS_BY_IDENTITY.get(service_identity, ())
    ):
        raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.PERMISSION_NOT_GRANTED)
    return context


def fixed_service_context_revalidator(
    repository: AdminAuthorizationRepository,
    expected_identity: ServiceIdentity,
):
    """Build AUTH's canonical fixed-service lifecycle revalidator."""

    async def revalidate(
        original: ServiceAuthorizationContext,
        _requested_action: ActionId,
    ) -> ServiceAuthorizationContext | None:
        locked = await repository.lock_request_actor(
            original.identity_link_id, original.actor_profile_id
        )
        if locked is None:
            return None
        link, profile = locked
        if (
            profile.actor_kind != ActorKind.SERVICE.value
            or profile.service_identity != expected_identity.value
        ):
            return None
        try:
            return ServiceAuthorizationContext(
                actor_profile_id=UUID(profile.id),
                actor_kind=ActorKind.SERVICE,
                actor_status=ActorStatus(profile.status),
                identity_link_id=UUID(link.id),
                identity_link_status=IdentityLinkStatus(link.status),
                service_identity=expected_identity,
                request_id=original.request_id,
                correlation_id=original.correlation_id,
            )
        except (TypeError, ValueError):
            return None

    return revalidate


@asynccontextmanager
async def fixed_service_prepared_authorization(
    session: AsyncSession,
    *,
    service_identity: ServiceIdentity,
    request_id: UUID,
    correlation_id: UUID,
) -> AsyncIterator[FixedServicePreparedAuthorization]:
    """Compose one exact fixed service through the shared PREP kernel."""
    context = await fixed_service_authorization_context(
        session, service_identity, request_id, correlation_id
    )
    repository = AdminAuthorizationRepository(session)
    authorization = AuthorizationService(
        session,
        context,
        revalidate_service=fixed_service_context_revalidator(repository, service_identity),
        admin_repository=repository,
    )
    prepared = PreparedAuthorizationService(session, context, authorization, repository)
    try:
        yield FixedServicePreparedAuthorization(
            actor_profile_id=context.actor_profile_id,
            identity_link_id=context.identity_link_id,
            service=prepared,
        )
    finally:
        prepared.close()


from app.modules.authorization.submission_creation_authorization import (  # noqa: E402, F401
    PreparedSubmissionCreationAuthorization,
)
