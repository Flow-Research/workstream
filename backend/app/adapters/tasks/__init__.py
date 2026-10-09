"""TASK-owned composition adapters and transaction roots."""

from app.modules.tasks.api.submission_history import SubmissionHistoryReadPort
from app.modules.tasks.api.submitted_bundle import SubmittedBundlePort
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import Settings
from uuid import UUID

from app.modules.artifacts.api import (
    SubmissionAdmissionConsumptionPort,
    SubmissionAdmissionConsumptionRequest,
)
from app.modules.tasks.api import (
    SubmissionCreationAuthorizationPort,
    SubmissionCreationRequest,
    SubmissionCreationResult,
    TaskSubmissionContextPort,
)
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.api import TaskSubmissionContextFacts
from app.modules.projects.api import ProjectLockedPolicyContextFacts
from app.modules.tasks.service import TaskService
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.api import TaskAuthorizationPort, TaskTransitionAuditPort
from app.modules.tasks.submission_participants import (
    SubmissionArtifactAdmissionRequest, SubmissionArtifactAdmissionResult,
    SubmissionArtifactReplayRequest, SubmissionArtifactBindingFacts,
)
from app.modules.artifacts.api.submission_admission import ConsumedSubmissionAdmissionRequest
from app.modules.tasks.submission_composition import TaskSubmissionCreationService
from app.modules.tasks.assignment_invalidation import AssignmentInvalidationOperation
from app.modules.tasks.api.assignment_invalidation import AssignmentInvalidationUnavailable
from app.modules.outbox.api import HandlerOutcome
from app.modules.checkers.api.execution import EvaluationTaskGuard


def evaluation_task_guard(session: AsyncSession) -> EvaluationTaskGuard:
    """Expose TASK-owned locking through the required CHECKERS consumer port."""
    from app.modules.tasks.post_submit_routing.evaluation_guard import TaskEvaluationGuard
    return TaskEvaluationGuard(session)


class TransactionalAssignmentInvalidationHandler:
    """Exact registered handler; commits before acknowledgement, with explicit authority."""

    def __init__(self, session_factory, *, observer, authorization_factory):
        self._sessions = session_factory
        self._observer, self._authorization = observer, authorization_factory

    async def __call__(self, envelope):
        from app.adapters.audit import assignment_invalidation_audit, committed_authority_invalidation
        from app.adapters.outbox import outbox_invocation_fence

        try:
            async with self._sessions() as session, session.begin():
                outcome = await AssignmentInvalidationOperation(
                    session, observer=self._observer, fence=outbox_invocation_fence(session),
                    causes=committed_authority_invalidation(self._sessions),
                    authorization=self._authorization(session),
                    audit=assignment_invalidation_audit(session),
                ).reconcile(envelope)
            return outcome
        except AssignmentInvalidationUnavailable:
            # The context has rolled back every staged TASK/AUTH/audit change.
            return HandlerOutcome.REJECT

__all__ = (
    "TransactionalAssignmentInvalidationHandler",
    "task_commands",
    "task_service",
    "TransactionalSubmissionCreationCommand",
    "task_submission_context_port",
)


def task_service(session: AsyncSession, *, settings: Settings) -> TaskService:
    """Compose exact PROJECTS custody and installed CHECKERS at the existing TASK root."""
    from app.adapters.projects import project_locked_policy_context_port
    from app.adapters.checkers import project_guide_approval_compiler, installed_post_submit_catalogue

    planner, _, _ = project_guide_approval_compiler(
        disabled_checker_ids=settings.artifact_pre_submission_checker_disabled_ids,
    )
    return TaskService(
        session, project_contexts=project_locked_policy_context_port(session),
        pre_submit_planner=planner, post_submit_catalogue=installed_post_submit_catalogue,
    )


def task_commands(
    session: AsyncSession, *, authorization: TaskAuthorizationPort,
    audit: TaskTransitionAuditPort, actor_profile_id: UUID, settings: Settings,
) -> AuthorizedTaskCommands:
    """Compose TASK commands without exposing private product imports to delivery."""
    from app.adapters.artifacts import task_guide_documents_port
    from app.adapters.contributions import locked_compensation_terms_port
    return AuthorizedTaskCommands(
        session, authorization=authorization, audit=audit, actor_profile_id=actor_profile_id,
        contexts=task_service(session, settings=settings),
        guide_documents=task_guide_documents_port(session, settings),
        compensation_terms=locked_compensation_terms_port(session),
    )


def contributor_task_repository(session: AsyncSession) -> TaskRepository:
    """Compose contributor reads with CON's bounded locked-terms public port."""
    from app.adapters.contributions import locked_compensation_terms_port
    return TaskRepository(session, compensation_terms=locked_compensation_terms_port(session))


def task_submission_context_port(session: AsyncSession) -> TaskSubmissionContextPort:
    """Bind the public TASK submission-context port to its repository."""
    return TaskRepository(session)


class _ArtifactAdmissionAdapter:
    def __init__(self, admissions: SubmissionAdmissionConsumptionPort) -> None:
        self._admissions = admissions

    async def consume(
        self, request: SubmissionArtifactAdmissionRequest
    ) -> SubmissionArtifactAdmissionResult:
        result = await self._admissions.consume(
            SubmissionAdmissionConsumptionRequest(
                admission_id=request.admission_id,
                submission_id=request.submission_id,
                submission_version=request.submission_version,
                task_context=request.task_context,
                packet_sha256=request.packet.sha256,
            )
        )
        if (result.binding_id is None or result.status != "consumed"
                or result.material is None or result.binding_decision_id is None):
            raise RuntimeError("admission did not produce a binding")
        from app.adapters.checkers import submission_evaluation_content
        return SubmissionArtifactAdmissionResult(
            binding_id=result.binding_id, content_id=result.content_id,
            binding_decision_id=result.binding_decision_id,
            archive_sha256=result.material.archive_sha256,
            byte_count=result.material.archive_byte_count,
            evaluation_content=submission_evaluation_content(
                request.task_context, request.project_context, request.packet,
                result.material.files, result.material.archive_sha256,
            ),
        )

    async def read_consumed(self, request: SubmissionArtifactReplayRequest) -> SubmissionArtifactBindingFacts:
        result = await self._admissions.read_consumed(ConsumedSubmissionAdmissionRequest(
            admission_id=request.admission_id, project_id=request.project_id,
            task_id=request.task_id, assignment_id=request.assignment_id,
            contributor_id=request.contributor_id, submission_id=request.submission_id,
            submission_version=request.submission_version, packet_sha256=request.packet_sha256,
        ))
        if (result.binding_id is None or result.material is None
                or result.binding_decision_id is None or result.status != "consumed"):
            raise RuntimeError("retained admission custody unavailable")
        return SubmissionArtifactBindingFacts(
            binding_id=result.binding_id, content_id=result.content_id,
            binding_decision_id=result.binding_decision_id,
            archive_sha256=result.material.archive_sha256, byte_count=result.material.archive_byte_count,
        )


class TransactionalSubmissionCreationCommand:
    """Open the sole root transaction and delegate sequencing to TASK."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        authorization: SubmissionCreationAuthorizationPort,
        admissions: SubmissionAdmissionConsumptionPort,
        settings: Settings,
    ) -> None:
        self._session = session
        self._settings = settings
        self._authorization = authorization
        self._admissions = admissions

    async def create(self, request: SubmissionCreationRequest) -> SubmissionCreationResult:
        if self._session.in_transaction():
            raise RuntimeError("submission composition requires a transaction-free session")
        from app.adapters.checkers import evaluation_coordinator
        from app.adapters.outbox import outbox_append

        async with self._session.begin():
            return await TaskSubmissionCreationService(
                self._session,
                contexts=task_service(self._session, settings=self._settings),
                authorization=self._authorization,
                admissions=_ArtifactAdmissionAdapter(self._admissions),
                evaluations=evaluation_coordinator(self._session),
                events=outbox_append(self._session),
            ).create(request)


def assignment_invalidation_targets(session: AsyncSession):
    """Compose the TASK-owned nonlocking exact-target projection."""
    return TaskRepository(session)


def submission_history_repository(session) -> SubmissionHistoryReadPort:
    """Compose TASK-owned immutable history selectors and projections."""
    from app.modules.tasks.submission_history import SubmissionHistoryRepository
    return SubmissionHistoryRepository(session)


def submitted_bundle_port(session: AsyncSession) -> SubmittedBundlePort:
    """Compose the exact immutable Submission read without private owner imports in ART."""
    from app.modules.tasks.submitted_bundle import SubmittedBundleReader
    return SubmittedBundleReader(session)


def routing_source_preparer(session):
    """Compose exact hidden source preparation through existing owner ports."""
    from app.adapters.checkers import evaluation_coordinator
    from app.adapters.projects import project_locked_policy_context_port
    from app.modules.tasks.post_submit_routing.source import TaskRoutingSourcePreparer

    return TaskRoutingSourcePreparer(
        session, evaluations=evaluation_coordinator(session),
        projects=project_locked_policy_context_port(session),
    )


def validate_submission_policy_context(task_context: TaskSubmissionContextFacts, project_context: ProjectLockedPolicyContextFacts) -> None:
    """Use TASK's canonical stamp projection without exposing its implementation."""
    TaskService.validate_submission_policy_context(task_context, project_context)


def evaluation_request_handler(*, sessions, materialization):
    """Compose one hidden TASK request handler; production registration is separate."""
    from app.adapters.checkers import evaluation_coordinator, delivery_bound_post_submission_executor
    from app.adapters.outbox import committed_invocation_reader
    from app.modules.tasks.evaluation_delivery import EvaluationRequestHandler

    def executor(envelope, request):
        return delivery_bound_post_submission_executor(
            sessions=sessions, materialization=materialization, envelope=envelope, request=request,
        )

    return EvaluationRequestHandler(
        sessions, observer=committed_invocation_reader(sessions),
        evaluations=evaluation_coordinator, executor=executor,
    )
