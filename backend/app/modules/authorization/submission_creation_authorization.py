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
    AuthorizationContext,
    AuthorizationDenied,
    HumanAuthorizationContext,
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
        ):
            raise SubmissionCreationUnavailable("submission creation is unavailable")

    async def consume(self, facts: SubmissionCreationAuthorityFacts) -> None:
        """Consume one project-scoped capability for exact locked TASK facts."""
        from app.modules.authorization.prepared import PreparedAuthorizationService

        context = self._context
        repository = AdminAuthorizationRepository(self._session)
        prepared = PreparedAuthorizationService(
            self._session,
            context,
            AuthorizationService(self._session, context, admin_repository=repository),
            repository,
        )
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
            await prepared.consume(
                handle, ActionId.SUBMISSION_CREATE, prepared_input, resource
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
