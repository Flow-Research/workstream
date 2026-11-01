"""TASK-owned composition adapters and transaction roots."""

from app.modules.tasks.api.submission_history import SubmissionHistoryReadPort
from app.modules.tasks.api.submitted_bundle import SubmittedBundlePort
from app.modules.tasks.api.evaluation_revision import TaskEvaluationRevisionPort
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.core.config import Settings
from app.db.errors import integrity_constraint_name
from uuid import UUID

from app.modules.artifacts.api import (
    SubmissionAdmissionConsumptionPort,
    SubmissionAdmissionConsumptionRequest,
    SubmissionAdmissionConsumptionError,
)
from app.modules.tasks.api import (
    SubmissionCreationAuthorizationPort,
    SubmissionCreationRequest,
    SubmissionCreationResult,
    SubmissionCreationAdmissionError,
    TaskSubmissionContextUnavailable,
    TaskSubmissionContextPort,
    TaskSubmissionContextRequest,
)
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.api import TaskSubmissionContextFacts
from app.modules.projects.api import ProjectLockedPolicyContextFacts
from app.modules.tasks.service import TaskService
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.api import TaskAuthorizationPort, TaskTransitionAuditPort
from app.modules.tasks.submission_participants import (
    SubmissionArtifactAdmissionRequest,
    SubmissionArtifactAdmissionResult,
    SubmissionArtifactReplayRequest,
    SubmissionArtifactBindingFacts,
)
from app.modules.artifacts.api.submission_admission import ConsumedSubmissionAdmissionRequest
from app.modules.tasks.submission_composition import TaskSubmissionCreationService
from app.modules.tasks.assignment_invalidation import AssignmentInvalidationOperation
from app.modules.tasks.api.assignment_invalidation import AssignmentInvalidationUnavailable
from app.modules.outbox.api import HandlerOutcome
from app.modules.checkers.api.execution import EvaluationTaskGuard
from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitReservationFacts


def evaluation_task_guard(session: AsyncSession) -> EvaluationTaskGuard:
    """Expose TASK-owned locking through the required CHECKERS consumer port."""
    from app.modules.tasks.post_submit_routing.evaluation_guard import TaskEvaluationGuard

    return TaskEvaluationGuard(session)


class _SelectedPreSubmitTaskGuard:
    """Project selected PRE custody through TASK's canonical submission lock."""

    def __init__(self, session: AsyncSession) -> None:
        self._contexts = task_submission_context_port(session)

    async def lock_selected_pre_submit_scope(
        self, reservation: SelectedPreSubmitReservationFacts
    ) -> None:
        lineage = reservation.admission_lineage
        if lineage is None:
            raise RuntimeError("selected PRE admission lineage is unavailable")
        context = await self._contexts.lock_submission_context(
            TaskSubmissionContextRequest(
                task_id=reservation.task_id,
                assignment_id=reservation.assignment_id,
                contributor_id=reservation.actor_profile_id,
                predecessor_submission_id=lineage.predecessor_submission_id,
            )
        )
        predecessor = context.predecessor
        references = context.locked_project_context
        if (
            context.task_id != reservation.task_id
            or context.assignment_id != reservation.assignment_id
            or context.contributor_id != reservation.actor_profile_id
            or (predecessor.submission_id if predecessor is not None else None)
            != lineage.predecessor_submission_id
            or (predecessor.version if predecessor is not None else None)
            != lineage.predecessor_submission_version
            or context.checker_remediation_manifest_id
            != lineage.checker_remediation_manifest_id
            or references.project_id != reservation.project_id
            or references.guide_version != lineage.guide_version
            or references.source_snapshot_id != lineage.source_snapshot_id
            or references.source_snapshot_hash != lineage.source_snapshot_sha256
            or references.effective_policy_id != lineage.effective_policy_id
            or references.effective_policy_hash != lineage.effective_policy_sha256
            or references.pre_submit_policy_id != lineage.pre_submit_policy_id
            or references.pre_submit_policy_bundle_hash != lineage.pre_submit_policy_sha256
        ):
            raise RuntimeError("selected PRE TASK custody changed")


def selected_pre_submit_task_guard(session: AsyncSession) -> _SelectedPreSubmitTaskGuard:
    """Expose TASK-first selected PRE locking to CHECKERS composition."""
    return _SelectedPreSubmitTaskGuard(session)


class TransactionalAssignmentInvalidationHandler:
    """Exact registered handler; commits before acknowledgement, with explicit authority."""

    def __init__(self, session_factory, *, observer, authorization_factory):
        self._sessions = session_factory
        self._observer, self._authorization = observer, authorization_factory

    async def __call__(self, envelope):
        from app.adapters.audit import (
            assignment_invalidation_audit,
            committed_authority_invalidation,
        )
        from app.adapters.outbox import outbox_invocation_fence

        try:
            async with self._sessions() as session, session.begin():
                outcome = await AssignmentInvalidationOperation(
                    session,
                    observer=self._observer,
                    fence=outbox_invocation_fence(session),
                    causes=committed_authority_invalidation(self._sessions),
                    authorization=self._authorization(session),
                    audit=assignment_invalidation_audit(session),
                ).reconcile(envelope)
            return outcome
        except AssignmentInvalidationUnavailable:
            # The context has rolled back every staged TASK/AUTH/audit change.
            return HandlerOutcome.REJECT


class TransactionalTaskRevisionExpiryHandler:
    """Commit the exact TASK timeout effect before OUTBOX acknowledgement."""

    def __init__(self, session_factory, *, observer, authorization_factory):
        self._sessions = session_factory
        self._observer, self._authorization = observer, authorization_factory

    async def __call__(self, envelope):
        from app.adapters.audit import task_revision_expiry_audit
        from app.adapters.outbox import outbox_append, outbox_invocation_fence
        from app.modules.tasks.api.revision_expiry import TaskRevisionExpiryUnavailable
        from app.modules.tasks.revision.expiry import TaskRevisionExpiryOperation

        try:
            async with self._sessions() as session, session.begin():
                outcome = await TaskRevisionExpiryOperation(
                    session, observer=self._observer,
                    fence=outbox_invocation_fence(session),
                    authorization=self._authorization(session),
                    audit=task_revision_expiry_audit(session),
                    outbox=outbox_append(session),
                ).expire(envelope)
            return outcome
        except TaskRevisionExpiryUnavailable:
            return HandlerOutcome.REJECT


class TransactionalTaskRevisionExpiredNoticeHandler:
    """ACK the committed outcome only after exact TASK receipt and audit validation."""

    def __init__(self, session_factory, *, observer):
        self._sessions, self._observer = session_factory, observer

    async def __call__(self, envelope):
        from app.adapters.audit import task_revision_expiry_audit
        from app.modules.tasks.api.revision_expiry import TaskRevisionExpiryUnavailable
        from app.modules.tasks.revision.expired_notice import TaskRevisionExpiredNoticeOperation

        try:
            async with self._sessions() as session:
                return await TaskRevisionExpiredNoticeOperation(
                    session, observer=self._observer,
                    audit=task_revision_expiry_audit(session),
                ).acknowledge(envelope)
        except TaskRevisionExpiryUnavailable:
            return HandlerOutcome.REJECT


class TransactionalTaskRevisionBlockedNoticeHandler:
    """Validate a durable paused-context notice without external delivery claims."""

    def __init__(self, session_factory, *, observer):
        self._sessions, self._observer = session_factory, observer

    async def __call__(self, envelope):
        from app.modules.tasks.revision.blocked_notice import TaskRevisionBlockedNoticeOperation

        async with self._sessions() as session:
            return await TaskRevisionBlockedNoticeOperation(
                session, observer=self._observer,
            ).acknowledge(envelope)


class TransactionalTaskRevisionExhaustedNoticeHandler:
    """Validate the committed recovery outcome against immutable terminal evidence."""

    def __init__(self, session_factory, *, observer):
        """Bind caller sessions and the committed delivery observer."""
        self._sessions, self._observer = session_factory, observer

    async def __call__(self, envelope):
        """Acknowledge exact terminal facts without changing lifecycle state."""
        from app.modules.tasks.revision.exhausted_notice import TaskRevisionExhaustedNoticeOperation

        async with self._sessions() as session:
            return await TaskRevisionExhaustedNoticeOperation(
                session, observer=self._observer,
            ).acknowledge(envelope)


__all__ = (
    "selected_pre_submit_task_guard",
    "TransactionalAssignmentInvalidationHandler",
    "TransactionalTaskRevisionExpiryHandler",
    "TransactionalTaskRevisionExpiredNoticeHandler",
    "TransactionalTaskRevisionBlockedNoticeHandler",
    "TransactionalTaskRevisionExhaustedNoticeHandler",
    "task_commands",
    "task_service",
    "TransactionalSubmissionCreationCommand",
    "task_submission_context_port",
)


def task_service(session: AsyncSession, *, settings: Settings) -> TaskService:
    """Compose exact PROJECTS custody at the existing TASK transaction root."""
    from app.adapters.projects import project_locked_policy_context_port

    return TaskService(
        session,
        project_contexts=project_locked_policy_context_port(session),
    )


def task_revision_recovery(session: AsyncSession):
    """Compose the explicit retained-window recovery owner in one transaction."""
    from app.adapters.audit import task_transition_audit
    from app.adapters.auth import revision_recovery_authorization
    from app.adapters.outbox import outbox_append
    from app.adapters.projects import project_locked_policy_context_port
    from app.modules.tasks.revision.recovery import TaskRevisionRecovery

    return TaskRevisionRecovery(
        session, projects=project_locked_policy_context_port(session),
        authorization=revision_recovery_authorization(session),
        audit=task_transition_audit(session), outbox=outbox_append(session),
    )


async def scan_task_revision_sources(factory, after):
    """Compose one bounded TASK discovery page for the scheduled worker."""
    from app.modules.tasks.revision.recovery_scan import scan_current_revision_sources

    return await scan_current_revision_sources(factory, task_revision_recovery, after)


def task_commands(
    session: AsyncSession,
    *,
    authorization: TaskAuthorizationPort,
    audit: TaskTransitionAuditPort,
    actor_profile_id: UUID,
    settings: Settings,
) -> AuthorizedTaskCommands:
    """Compose TASK commands without exposing private product imports to delivery."""
    from app.adapters.artifacts import task_guide_documents_port
    from app.adapters.contributions import locked_compensation_terms_port
    from app.adapters.outbox import outbox_append

    return AuthorizedTaskCommands(
        session,
        authorization=authorization,
        audit=audit,
        actor_profile_id=actor_profile_id,
        contexts=task_service(session, settings=settings),
        guide_documents=task_guide_documents_port(session, settings),
        compensation_terms=locked_compensation_terms_port(session),
        outbox=outbox_append(session),
    )


def task_import_batch_commands(
    session: AsyncSession, *, authorization, audit: TaskTransitionAuditPort,
    actor_profile_id: UUID, identity_link_id: UUID, settings: Settings, source,
):
    """Compose the batch root from canonical TASK commands and one ART source owner."""
    from app.modules.tasks.task_import_batches import TaskImportBatchCommands
    return TaskImportBatchCommands(
        session, actor_profile_id=actor_profile_id, identity_link_id=identity_link_id,
        authorization=authorization,
        tasks=task_commands(session, authorization=authorization, audit=audit,
                            actor_profile_id=actor_profile_id, settings=settings),
        source=source,
    )


def contributor_task_repository(session: AsyncSession) -> TaskRepository:
    """Compose contributor reads with CON's bounded locked-terms public port."""
    from app.adapters.contributions import locked_compensation_terms_port

    return TaskRepository(session, compensation_terms=locked_compensation_terms_port(session))


def task_batch_transition_commands(
    session: AsyncSession, *, tasks: AuthorizedTaskCommands,
    actor_profile_id: UUID, identity_link_id: UUID,
):
    """Bind the batch root to the same canonical Task authority and participants."""
    from app.modules.tasks.task_batch_transitions import TaskBatchTransitionCommands
    return TaskBatchTransitionCommands(
        session, tasks=tasks, actor_profile_id=actor_profile_id, identity_link_id=identity_link_id,
    )


def task_submission_context_port(session: AsyncSession) -> TaskSubmissionContextPort:
    """Bind every intake caller to TASK's current-source composite."""
    from app.adapters.checkers import evaluation_coordinator
    from app.modules.tasks.submission_context import TaskSubmissionContextService
    return TaskSubmissionContextService(session, evaluation_coordinator(session))


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
        if (
            result.binding_id is None
            or result.status != "consumed"
            or result.material is None
            or result.binding_decision_id is None
        ):
            raise RuntimeError("admission did not produce a binding")
        from app.adapters.checkers import selected_submission_evaluation_content
        from app.modules.checkers.api.external_policy import (
            validate_stored_external_post_policy,
        )

        selected_post_policy = (
            validate_stored_external_post_policy(result.selected_post_submit_policy_body)
            if result.selected_post_submit_policy_body is not None
            else None
        )
        if selected_post_policy is None:
            raise RuntimeError("external checker admission policy is unavailable")
        return SubmissionArtifactAdmissionResult(
            binding_id=result.binding_id,
            content_id=result.content_id,
            binding_decision_id=result.binding_decision_id,
            archive_sha256=result.material.archive_sha256,
            byte_count=result.material.archive_byte_count,
            selected_post_submit_policy=selected_post_policy,
            selected_evaluation_content=selected_submission_evaluation_content(
                request.task_context, selected_post_policy
            ),
        )

    async def read_consumed(
        self, request: SubmissionArtifactReplayRequest
    ) -> SubmissionArtifactBindingFacts:
        result = await self._admissions.read_consumed(
            ConsumedSubmissionAdmissionRequest(
                admission_id=request.admission_id,
                project_id=request.project_id,
                task_id=request.task_id,
                assignment_id=request.assignment_id,
                contributor_id=request.contributor_id,
                submission_id=request.submission_id,
                submission_version=request.submission_version,
                packet_sha256=request.packet_sha256,
            )
        )
        if (
            result.binding_id is None
            or result.material is None
            or result.binding_decision_id is None
            or result.status != "consumed"
        ):
            raise RuntimeError("retained admission custody unavailable")
        from app.adapters.checkers import selected_submission_evaluation_content
        from app.modules.checkers.api.external_policy import (
            validate_stored_external_post_policy,
        )

        selected_post_policy = validate_stored_external_post_policy(
            result.selected_post_submit_policy_body
        )
        return SubmissionArtifactBindingFacts(
            binding_id=result.binding_id,
            content_id=result.content_id,
            binding_decision_id=result.binding_decision_id,
            archive_sha256=result.material.archive_sha256,
            byte_count=result.material.archive_byte_count,
            selected_evaluation_content=selected_submission_evaluation_content(
                request.task_context, selected_post_policy
            ),
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

        try:
            async with self._session.begin():
                return await TaskSubmissionCreationService(
                    self._session,
                    contexts=task_service(self._session, settings=self._settings),
                    submission_contexts=task_submission_context_port(self._session),
                    authorization=self._authorization,
                    admissions=_ArtifactAdmissionAdapter(self._admissions),
                    evaluations=evaluation_coordinator(self._session),
                    events=outbox_append(self._session),
                ).create(request)
        except SubmissionAdmissionConsumptionError as exc:
            raise SubmissionCreationAdmissionError(exc.code) from exc
        except IntegrityError as exc:
            name = integrity_constraint_name(exc)
            if name == "ck_revision_submission_deadline_expired":
                raise TaskSubmissionContextUnavailable("revision_deadline_expired") from exc
            if name == "ck_revision_submission_context_changed":
                raise TaskSubmissionContextUnavailable("revision_context_changed") from exc
            raise


def assignment_invalidation_targets(session: AsyncSession):
    """Compose the TASK-owned nonlocking exact-target projection."""
    return TaskRepository(session)


def submission_history_repository(session) -> SubmissionHistoryReadPort:
    """Compose TASK-owned immutable history selectors and projections."""
    from app.adapters.checkers import checker_history_repository
    from app.modules.tasks.submission_history import SubmissionHistoryRepository

    return SubmissionHistoryRepository(
        session, finding_counts=checker_history_repository(session)
    )


def contributor_work_reader(session: AsyncSession):
    """Compose TASK's own-work projections with CON terms and CHECKERS counts."""
    from app.adapters.checkers import checker_history_repository
    from app.adapters.contributions import locked_compensation_terms_port
    from app.modules.tasks.contributor_reads import ContributorWorkReader

    return ContributorWorkReader(
        session, compensation_terms=locked_compensation_terms_port(session),
        finding_counts=checker_history_repository(session),
    )


def task_evaluation_revision_port(session: AsyncSession) -> TaskEvaluationRevisionPort:
    """Compose the exact immutable revision read under the caller's transaction."""
    from app.modules.tasks.evaluation_revision import TaskEvaluationRevisionReader

    return TaskEvaluationRevisionReader(session)


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
        session,
        evaluations=evaluation_coordinator(session),
        projects=project_locked_policy_context_port(session),
    )


def validate_submission_policy_context(
    task_context: TaskSubmissionContextFacts, project_context: ProjectLockedPolicyContextFacts
) -> None:
    """Use TASK's canonical stamp projection without exposing its implementation."""
    TaskService.validate_submission_policy_context(task_context, project_context)


def evaluation_request_handler(*, sessions, materialization):
    """Compose one hidden TASK request handler; production registration is separate."""
    from app.adapters.checkers import (
        configured_forge_facts,
        configured_post_submit_external_execution,
        delivery_bound_post_submission_executor,
        evaluation_coordinator,
    )
    from app.adapters.outbox import committed_invocation_reader
    from app.core.config import get_settings
    from app.modules.tasks.evaluation_delivery import EvaluationRequestHandler

    def executor(envelope, request):
        selected_execution = configured_post_submit_external_execution(get_settings(), sessions=sessions)
        return delivery_bound_post_submission_executor(
            sessions=sessions,
            materialization=materialization,
            envelope=envelope,
            request=request,
            selected_execution=selected_execution,
            forge_facts=configured_forge_facts(get_settings()),
        )

    return EvaluationRequestHandler(
        sessions,
        observer=committed_invocation_reader(sessions),
        evaluations=evaluation_coordinator,
        executor=executor,
    )


def evaluation_delivery_request_reader(session, evaluations):
    """Expose TASK's exact retained request reader behind its public port."""
    from app.modules.checkers.api.delivery_reconciliation import (
        PostSubmitDeliverySourceUnavailable,
    )
    from app.modules.tasks.evaluation_delivery import (
        EvaluationDeliveryRequestReader,
        EvaluationDeliveryUnavailable,
    )

    owner = EvaluationDeliveryRequestReader(session, evaluations)

    class Reader:
        async def read(self, envelope):
            try:
                return await owner.read(envelope)
            except EvaluationDeliveryUnavailable as exc:
                raise PostSubmitDeliverySourceUnavailable(
                    "post_submit_delivery_source_unavailable"
                ) from exc

    return Reader()


def task_post_submit_outcome(session, sessions):
    """Every writer uses the caller session; only committed invocation observation is independent."""
    from app.adapters.audit import task_routing_audit
    from app.adapters.outbox import (
        outbox_append,
        outbox_invocation_fence,
        committed_invocation_reader,
    )
    from app.adapters.tasks.routing_acceptance import RoutingAcceptanceAdapter
    from app.adapters.auth import task_routing_authorization
    from app.adapters.checkers import evaluation_coordinator
    from app.adapters.projects import project_locked_policy_context_port
    from app.modules.tasks.post_submit_routing.outcome import TaskPostSubmitOutcome

    return TaskPostSubmitOutcome(
        session,
        projects=project_locked_policy_context_port(session),
        evaluations=evaluation_coordinator(session),
        authorization=task_routing_authorization(session),
        acceptance=RoutingAcceptanceAdapter(session),
        observer=committed_invocation_reader(sessions),
        invocation_fence=outbox_invocation_fence(session),
        audit=task_routing_audit(session),
        outbox=outbox_append(session),
    )


def post_submit_delivery_outcome(session, sessions):
    """Expose TASK outcome reconciliation through CHECKERS's typed consumer port."""
    return _post_submit_delivery_outcome_adapter(
        task_post_submit_outcome(session, sessions)
    )


def reconciliation_task_post_submit_outcome(
    session, sessions, custody, reconciliation_claim,
):
    """Compose the existing TASK owner behind recovery-bound delivery custody."""
    from app.adapters.audit import task_routing_audit
    from app.adapters.auth import task_routing_authorization
    from app.adapters.checkers import evaluation_coordinator
    from app.adapters.outbox import outbox_append
    from app.adapters.projects import project_locked_policy_context_port
    from app.adapters.tasks.routing_acceptance import RoutingAcceptanceAdapter
    from app.modules.tasks.post_submit_routing.outcome import TaskPostSubmitOutcome

    return _post_submit_delivery_outcome_adapter(TaskPostSubmitOutcome(
        session,
        projects=project_locked_policy_context_port(session),
        evaluations=evaluation_coordinator(session),
        authorization=task_routing_authorization(session),
        acceptance=RoutingAcceptanceAdapter(session),
        observer=custody,
        invocation_fence=custody,
        audit=task_routing_audit(session),
        outbox=outbox_append(session),
        reconciliation_claim=reconciliation_claim,
    ))


def _post_submit_delivery_outcome_adapter(owner):
    """Translate TASK-private unavailable facts to CHECKERS's typed consumer port."""
    from app.modules.checkers.api.delivery_reconciliation import (
        PostSubmitDeliveryRetryable,
        PostSubmitDeliverySourceUnavailable,
    )
    from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequestUnavailable
    from app.modules.tasks.api.routing_outcome import TaskRoutingLifecycleDeferred

    class Outcome:
        async def _call(self, name, *args, **kwargs):
            try:
                return await getattr(owner, name)(*args, **kwargs)
            except TaskRoutingRequestUnavailable as exc:
                raise PostSubmitDeliverySourceUnavailable(
                    "post_submit_delivery_source_unavailable"
                ) from exc
            except TaskRoutingLifecycleDeferred as exc:
                raise PostSubmitDeliveryRetryable(
                    "post_submit_delivery_retryable"
                ) from exc

        async def observe_delivery_generation(self, envelope):
            return await self._call("observe_delivery_generation", envelope)

        async def classify_uncertain_delivery(self, envelope, *, current_generation):
            return await self._call(
                "classify_uncertain_delivery",
                envelope,
                current_generation=current_generation,
            )

        async def verify_retained_delivery(self, envelope, *, current_generation):
            return await self._call(
                "verify_retained_delivery",
                envelope,
                current_generation=current_generation,
            )

        async def apply(self, envelope, *, current_generation):
            return await self._call(
                "apply", envelope, current_generation=current_generation
            )

    return Outcome()


def task_accepted_effects_participant(session, fence):
    """Construct TASK's terminal writer under the shared held fence."""
    from app.modules.tasks.accepted_effects import TaskAcceptedEffectsParticipant

    return TaskAcceptedEffectsParticipant(session, fence=fence)


def evaluation_completion_handler(*, sessions):
    """Compose hidden completion delivery; production registration remains separate."""
    from app.adapters.outbox import committed_invocation_reader
    from app.modules.tasks.evaluation_completion_delivery import EvaluationCompletionHandler

    return EvaluationCompletionHandler(
        sessions,
        observer=committed_invocation_reader(sessions),
        outcomes=lambda session: task_post_submit_outcome(session, sessions),
    )


def contribution_task_evidence_port(session):
    """Read exact selected source labels without claims, activation or task mutation."""
    from app.modules.tasks.contribution_evidence import ContributionTaskEvidenceRepository
    from app.adapters.tasks.contribution_reads import ContributionTaskSourceReadAdapter

    return ContributionTaskSourceReadAdapter(ContributionTaskEvidenceRepository(session))


def project_work_reader(session: AsyncSession):
    """Compose TASK's project-wide projections with CON terms and CHECKERS counts."""
    from app.adapters.checkers import checker_history_repository
    from app.adapters.contributions import locked_compensation_terms_port
    from app.modules.tasks.project_reads import ProjectWorkReader

    return ProjectWorkReader(
        session, compensation_terms=locked_compensation_terms_port(session),
        finding_counts=checker_history_repository(session),
    )
