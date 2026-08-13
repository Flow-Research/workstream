"""Human prepared authorization adapter for hidden Submission creation."""

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.api import (
    SubmissionCreationAuthorityFacts,
    SubmissionCreationPreparationFacts,
    SubmissionCreationUnavailable,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    AuthorizationContext,
    AuthorizationDenied,
    HumanAuthorizationContext,
    IdentityLinkStatus,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)
from app.modules.authorization.submission_consumption import (
    SubmissionCreationResourceContext,
)


class PreparedSubmissionCreationAuthorization:
    """Consume fresh human authority using locked TASK-owned final facts."""

    def __init__(self, session: AsyncSession, context: AuthorizationContext) -> None:
        self._session = session
        self._context = context

    async def authorize(self, facts: SubmissionCreationPreparationFacts) -> None:
        """Reject any caller other than the exact human contributor."""
        context = self._context
        if (
            not isinstance(context, HumanAuthorizationContext)
            or context.actor_kind is not ActorKind.HUMAN
            or context.actor_profile_id != facts.contributor_id
            or context.actor_status is not ActorStatus.ACTIVE
            or context.identity_link_status is not IdentityLinkStatus.ACTIVE
        ):
            raise SubmissionCreationUnavailable("submission creation is unavailable")

    async def prepare(self, facts: SubmissionCreationAuthorityFacts) -> object:
        """Prepare fresh project-scoped authority before ART state is inspected."""
        from app.modules.authorization.prepared import PreparedAuthorizationService

        context = self._context
        repository = AdminAuthorizationRepository(self._session)
        prepared = PreparedAuthorizationService(
            self._session,
            context,
            AuthorizationService(self._session, context, admin_repository=repository),
            repository,
        )
        retained = False
        try:
            resource = _creation_resource(context, facts)
            prepared_input = PreparedAuthorizationInput(
                idempotency_key=facts.admission_id,
                request_value=resource.model_dump(mode="json"),
            )
            handle = await prepared.prepare(
                ActionId.SUBMISSION_CREATE,
                prepared_input,
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT,
                    project_id=resource.scope_project_id,
                ),
            )
            retained = True
            return _PreparedSubmissionCreation(prepared, handle, prepared_input, resource)
        except (
            AuthorizationDenied,
            PreparedAuthorizationHandleInvalid,
            PreparedAuthorizationUnsupported,
            ValidationError,
        ) as exc:
            raise SubmissionCreationUnavailable("submission creation is unavailable") from exc
        finally:
            if not retained:
                prepared.close()

    async def consume(
        self, prepared_authorization: object, facts: SubmissionCreationAuthorityFacts
    ) -> None:
        """Consume the exact capability prepared before admission inspection."""
        if not isinstance(prepared_authorization, _PreparedSubmissionCreation):
            raise SubmissionCreationUnavailable("submission creation is unavailable")
        prepared = prepared_authorization.service
        try:
            resource = _creation_resource(self._context, facts)
            prepared_input = PreparedAuthorizationInput(
                idempotency_key=facts.admission_id,
                request_value=resource.model_dump(mode="json"),
            )
            if (
                prepared_input != prepared_authorization.prepared_input
                or resource != prepared_authorization.resource
            ):
                raise SubmissionCreationUnavailable("submission creation is unavailable")
            await prepared.consume(
                prepared_authorization.handle,
                ActionId.SUBMISSION_CREATE,
                prepared_input,
                resource,
            )
        except (
            AuthorizationDenied,
            PreparedAuthorizationHandleInvalid,
            PreparedAuthorizationUnsupported,
            ValidationError,
        ) as exc:
            raise SubmissionCreationUnavailable("submission creation is unavailable") from exc
        finally:
            prepared.close()

    def close(self, prepared_authorization: object) -> None:
        """Discard an AUTH-owned process-local carrier on every exit path."""
        if isinstance(prepared_authorization, _PreparedSubmissionCreation):
            prepared_authorization.service.close()


class _PreparedSubmissionCreation:
    """AUTH-private carrier for one process-local prepared capability."""

    __slots__ = ("handle", "prepared_input", "resource", "service")

    def __init__(self, service, handle, prepared_input, resource) -> None:
        self.service = service
        self.handle = handle
        self.prepared_input = prepared_input
        self.resource = resource


def _creation_resource(
    context: AuthorizationContext,
    facts: SubmissionCreationAuthorityFacts,
) -> SubmissionCreationResourceContext:
    """Compose strict final resource facts inside the translation boundary."""
    task = facts.task_context
    project = task.locked_project_context
    predecessor = task.predecessor
    return SubmissionCreationResourceContext(
        resource_type="submission_creation",
        resource_id=facts.submission_id,
        scope_project_id=project.project_id,
        actor_profile_id=facts.contributor_id,
        identity_link_id=context.identity_link_id,
        task_id=facts.task_id,
        assignment_id=facts.assignment_id,
        admission_id=facts.admission_id,
        predecessor_submission_id=facts.predecessor_submission_id,
        predecessor_submission_version=(predecessor.version if predecessor else None),
        submission_id=facts.submission_id,
        submission_version=facts.submission_version,
        task_status=task.status,
        submission_kind=task.kind,
        guide_version=project.guide_version,
        source_snapshot_id=project.source_snapshot_id,
        source_snapshot_sha256=project.source_snapshot_hash,
        effective_policy_id=project.effective_policy_id,
        effective_policy_sha256=project.effective_policy_hash,
        pre_submit_policy_id=project.pre_submit_policy_id,
        pre_submit_policy_sha256=project.pre_submit_policy_bundle_hash,
    )
