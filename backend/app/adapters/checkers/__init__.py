"""CHECKER-owned composition adapters."""

from app.adapters.checkers.external_service import (
    EXTERNAL_CHECKER_CAPABILITY_KEY,
    EXTERNAL_CHECKER_PROVIDER_KEY,
    UnixSocketExternalCheckerAdapter,
)
from app.interfaces.external_checker_execution import (
    ExternalCheckerExecutionAdapter,
    ExternalCheckerExecutionResponse,
    ExternalCheckerMaterialGrant,
    ExternalCheckerModelGrant,
    ExternalCheckerServiceHealth,
)
from app.interfaces.external_services import (
    ExternalServiceAdapterFactory,
    ExternalServiceAdapterIdentity,
    ExternalServiceUnavailableError,
)
from app.interfaces.checker_model_provider import (
    CHECKER_MODEL_CAPABILITY_KEY,
    CheckerModelProvider,
)
from app.modules.tasks.api import TaskSubmissionContextFacts
from app.modules.model_usage.api import ProjectModelProfile

from app.modules.checkers.api.external_policy import LockedExternalPostSubmitPolicy
from app.modules.checkers.api.selected_post_submit import (
    SelectedPostSubmissionContent,
    SelectedPostSubmitLockedContext,
)
from app.modules.checkers.api.history import CheckerHistoryReadPort
from app.modules.checkers.api.revision_feedback import RevisionFeedbackPort
from app.modules.checkers.api.execution import EvaluationCoordinationPort
from typing import Any, Protocol
from pathlib import Path


from app.modules.checkers.api.external import (
    ExternalCheckerCapabilityDefinition,
    ExternalCheckerCapabilityProjection,
    ExternalCheckerExecutionRequest,
    PreSubmitExternalCheckerIdentity,
    PreSubmitExternalCheckerMaterial,
    external_checker_json_hash,
)
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_CHECKER_ID,
    WORKSTREAM_DEFAULT_CHECKER_VERSION,
)
from app.modules.checkers.selected_pre_submit_execution import SelectedPreSubmitProcessor
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitInfrastructureUnavailable,
)


def revision_feedback_port(session) -> RevisionFeedbackPort:
    """Compose the exact immutable feedback read under the caller's transaction."""
    from app.modules.checkers.revision_feedback import RevisionFeedbackReader

    return RevisionFeedbackReader(session)


def external_checker_execution_factory(
    *, socket_path: Path, timeout_seconds: float
) -> ExternalServiceAdapterFactory[UnixSocketExternalCheckerAdapter]:
    """Compose the sole instance-local external checker adapter factory."""
    factory = ExternalServiceAdapterFactory[UnixSocketExternalCheckerAdapter](
        EXTERNAL_CHECKER_CAPABILITY_KEY
    )
    factory.register(
        EXTERNAL_CHECKER_PROVIDER_KEY,
        lambda: UnixSocketExternalCheckerAdapter(
            socket_path=socket_path,
            timeout_seconds=timeout_seconds,
        ),
    )
    return factory


def create_checker_model_provider(
    profile: ProjectModelProfile, *, api_key: str
) -> CheckerModelProvider:
    """Select one supported adapter from the exact immutable project profile."""
    from app.modules.model_usage.api import ModelCallUnavailable

    identity = (profile.spec.provider, profile.spec.api)
    provider_key = {
        ("openai_responses", "responses.v1"): "openai_responses",
        ("openrouter", "chat_completions"): "openrouter",
    }.get(identity)
    if provider_key is None:
        raise ModelCallUnavailable("model_profile_provider_unavailable")
    if not isinstance(api_key, str) or not api_key or len(api_key) > 8_192:
        raise ModelCallUnavailable("model_provider_credentials_unavailable")

    def openai_provider():
        from openai import AsyncOpenAI

        from app.adapters.checkers.model_provider import (
            OpenAIResponsesCheckerModelProvider,
            OpenAIResponsesSettings,
        )

        spec = profile.spec
        settings = OpenAIResponsesSettings(
            api_key=api_key,
            model=spec.model_snapshot,
            maximum_request_bytes=spec.maximum_request_bytes,
            maximum_input_tokens=spec.maximum_input_tokens,
            maximum_output_tokens=spec.maximum_output_tokens,
            maximum_output_bytes=spec.maximum_output_bytes,
            request_timeout_seconds=float(spec.deadline_ms / 1000),
            reasoning_effort=spec.settings.reasoning_effort,
            text_verbosity=spec.settings.text_verbosity,
        )
        return OpenAIResponsesCheckerModelProvider(
            settings,
            AsyncOpenAI(api_key=api_key, max_retries=0, timeout=settings.request_timeout_seconds),
        )

    def openrouter_provider():
        import httpx

        from app.adapters.checkers.openrouter_model_provider import OpenRouterCheckerModelProvider

        from app.adapters.model_usage.openrouter import require_direct_openrouter_model

        try:
            require_direct_openrouter_model(profile.spec.model_snapshot)
        except ValueError:
            raise ModelCallUnavailable("model_profile_provider_unavailable") from None
        client = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(retries=0, trust_env=False),
            trust_env=False,
            follow_redirects=False,
            timeout=profile.spec.deadline_ms / 1000.0,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        return OpenRouterCheckerModelProvider(profile, client)

    factory = ExternalServiceAdapterFactory[CheckerModelProvider](CHECKER_MODEL_CAPABILITY_KEY)
    factory.register("openai_responses", openai_provider)
    factory.register("openrouter", openrouter_provider)
    return factory.create(provider_key)


def configured_external_checker_execution_factory(settings):
    """Map configured image-execution settings into the sole adapter factory."""
    if (
        settings.external_checker_service_socket is None
        or settings.external_checker_material_root is None
    ):
        raise ValueError("external checker service is not configured")
    return external_checker_execution_factory(
        socket_path=settings.external_checker_service_socket,
        timeout_seconds=float(settings.external_checker_service_timeout_seconds),
    )


class _ConfiguredExternalCheckerExecution:
    """Resolve the fixed Rust provider only when a locked image is invoked."""

    def __init__(self, settings) -> None:
        self._settings = settings
        self._identity = ExternalServiceAdapterIdentity(
            EXTERNAL_CHECKER_CAPABILITY_KEY,
            EXTERNAL_CHECKER_PROVIDER_KEY,
        )

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Expose the sole provider identity without constructing its transport."""
        return self._identity

    def _resolve(self) -> ExternalCheckerExecutionAdapter:
        """Create the fixed provider or report absent runtime configuration."""
        if (
            self._settings.external_checker_service_socket is None
            and self._settings.external_checker_material_root is None
        ):
            raise ExternalServiceUnavailableError(self._identity)
        return configured_external_checker_execution_factory(self._settings).create(
            EXTERNAL_CHECKER_PROVIDER_KEY
        )

    async def execute(
        self,
        request: ExternalCheckerExecutionRequest,
        grant: ExternalCheckerMaterialGrant,
        *,
        model_grant: ExternalCheckerModelGrant | None = None,
    ) -> ExternalCheckerExecutionResponse:
        """Resolve and invoke the sole provider for one selected binding."""
        return await self._resolve().execute(request, grant, model_grant=model_grant)

    async def health(self) -> ExternalCheckerServiceHealth:
        """Resolve the sole provider before checking runtime readiness."""
        return await self._resolve().health()


def configured_forge_facts(settings):
    """Resolve the forge facts provider a locked binding names, only when it is used.

    Each evaluation builds its own provider: evaluations may run on separate
    event loops, so a provider (and its cached installation token) is not
    shared between them.
    """
    from app.adapters.github import forge_facts_adapter_factory

    return forge_facts_adapter_factory(settings).create


def configured_external_checker_execution(settings) -> ExternalCheckerExecutionAdapter:
    """Create the lazy fixed-provider adapter for selected execution."""
    return _ConfiguredExternalCheckerExecution(settings)


def configured_post_submit_external_execution(
    settings, *, sessions
) -> ExternalCheckerExecutionAdapter:
    """Add durable project model custody to the existing Rust image transport."""
    from app.adapters.checkers.model_execution import ModelAwareExternalExecution

    return ModelAwareExternalExecution(
        execution=configured_external_checker_execution(settings),
        sessions=sessions,
    )


def selected_pre_submit_checker_execution(*, settings):
    """Compose default/PRE checking with deferred project-image transport."""
    return SelectedPreSubmitCheckerExecutionAdapter(
        external_execution=configured_external_checker_execution(settings),
    )


def external_checker_registry_reader(session):
    """Resolve immutable metadata for trusted approval and execution owners."""
    from app.modules.checkers.external_registry import ExternalCheckerRegistryReader

    return ExternalCheckerRegistryReader(session)


def model_profile_reader(session):
    """Resolve exact immutable project model profiles without mutation authority."""
    from app.adapters.model_usage import model_profile_reader as shared_reader

    return shared_reader(session)


def external_checker_registry_service(session, authority):
    """Compose CHECKERS registration and readback with request-scoped AUTH."""
    from app.modules.checkers.external_registry import ExternalCheckerRegistryService

    return ExternalCheckerRegistryService(session, authority)


async def external_checker_capability_projection(
    session,
) -> ExternalCheckerCapabilityProjection:
    """Snapshot one default plus every immutable external registry identity."""
    entries = await external_checker_registry_reader(session).list_entries()
    definitions = tuple(
        sorted(
            (
                ExternalCheckerCapabilityDefinition(
                    capability_id=WORKSTREAM_DEFAULT_CHECKER_ID,
                    capability_version=WORKSTREAM_DEFAULT_CHECKER_VERSION,
                    phase="pre_submit",
                    selectable=False,
                    registry_entry=None,
                ),
                *(
                    ExternalCheckerCapabilityDefinition(
                        capability_id=entry.capability_id,
                        capability_version=entry.capability_version,
                        phase=entry.phase,
                        selectable=True,
                        registry_entry=entry,
                    )
                    for entry in entries
                ),
            ),
            key=lambda item: (
                item.phase,
                item.capability_id,
                item.capability_version,
            ),
        )
    )
    body = {
        "schema_version": "external_checker_capabilities.v1",
        "definitions": [item.model_dump(mode="json") for item in definitions],
    }
    return ExternalCheckerCapabilityProjection(
        definitions=definitions,
        manifest_sha256=external_checker_json_hash(body),
    )


def selected_pre_submit_coordinator(session):
    """Compose selected PRE custody through CHECKERS' public adapter root."""
    from app.adapters.tasks import selected_pre_submit_task_guard
    from app.modules.checkers.selected_pre_submit_coordination import (
        SelectedPreSubmitCoordinator,
    )

    return SelectedPreSubmitCoordinator(
        session,
        tasks=selected_pre_submit_task_guard(session),
    )


class _ExecutionRequest(Protocol):
    project_id: Any
    task_id: Any
    assignment_id: Any
    commitment: Any
    inspection: Any
    manifest: Any
    change_gate: Any
    packet: Any
    prepared_generation_id: Any
    storage_scheme: str


class SelectedPreSubmitCheckerExecutionAdapter:
    """Build the selected default-plus-external PRE processor from exact ART facts."""

    def __init__(self, *, external_execution) -> None:
        self._external_execution = external_execution

    def build(self, request: _ExecutionRequest) -> SelectedPreSubmitProcessor:
        """Reject any incomplete pre-admission identity before projecting bytes."""
        policy = getattr(request, "external_policy", None)
        default_input = getattr(request, "default_checker_input", None)
        attempt_id = getattr(request, "attempt_id", None)
        attempt_request_digest = getattr(request, "attempt_request_digest", None)
        if (
            policy is None
            or default_input is None
            or attempt_id is None
            or attempt_request_digest is None
        ):
            raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
        identity = PreSubmitExternalCheckerIdentity(
            project_id=request.project_id,
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            prepared_generation_id=request.prepared_generation_id,
            attempt_id=attempt_id,
            attempt_request_digest=attempt_request_digest,
            effective_plan_sha256=policy.policy_sha256,
        )
        material = PreSubmitExternalCheckerMaterial(
            role="submission_archive",
            prepared_generation_id=request.prepared_generation_id,
            attempt_id=attempt_id,
            attempt_request_digest=attempt_request_digest,
            archive_sha256=request.commitment.sha256,
            archive_byte_count=request.commitment.byte_count,
            semantic_manifest_sha256=request.manifest.sha256,
            media_type="application/zip",
        )
        return SelectedPreSubmitProcessor(
            policy=policy,
            default_input=default_input,
            identity=identity,
            material=material,
            execution=self._external_execution,
        )


def checker_history_repository(session) -> CheckerHistoryReadPort:
    """Compose retained CHECKERS reads through TASK's public ownership port."""
    from app.modules.checkers.history import CheckerHistoryRepository

    return CheckerHistoryRepository(session)


def evaluation_coordinator(session) -> EvaluationCoordinationPort:
    """Compose required TASK locking before CHECKERS reservation custody."""
    from app.modules.checkers.execution_coordination import EvaluationCoordinator
    from app.adapters.tasks import evaluation_task_guard

    return EvaluationCoordinator(session, tasks=evaluation_task_guard(session))


def checker_retry_service(session, context, *, cursor_secret=None):
    """Compose supported Operator recovery from existing owner operations."""
    from app.adapters.audit import checker_retry_audit
    from app.adapters.auth import (
        checker_retry_authorization,
        checker_retry_discovery_authorization,
    )
    from app.adapters.outbox import outbox_append
    from app.adapters.tasks import evaluation_task_guard
    from app.adapters.model_usage import model_recovery_sources
    from app.modules.checkers.checker_retry import CheckerRetryService
    from app.modules.checkers.execution_coordination import EvaluationCoordinator

    tasks = evaluation_task_guard(session)
    return CheckerRetryService(
        session,
        actor_profile_id=context.actor_profile_id,
        tasks=tasks,
        evaluations=EvaluationCoordinator(session, tasks=tasks),
        authorization=checker_retry_authorization(session, context),
        discovery=checker_retry_discovery_authorization(
            session,
            context,
            cursor_secret,
        ),
        events=outbox_append(session),
        audit=checker_retry_audit(session),
        model_recovery=model_recovery_sources(session),
    )


def post_submit_delivery_service(
    session,
    sessions,
    context,
    *,
    cursor_secret=None,
):
    """Compose exact Operator inspection and one-child reconciliation."""
    from app.adapters.auth import (
        post_submit_delivery_authorization,
        post_submit_delivery_read_authorization,
    )
    from app.adapters.outbox import finalized_unknown_deliveries, outbox_append
    from app.adapters.tasks import (
        evaluation_delivery_request_reader,
        post_submit_delivery_outcome,
    )
    from app.modules.checkers.delivery_reconciliation import (
        PostSubmitDeliveryService,
        classify_post_submit_delivery,
    )

    async def detached_classify(delivery):
        async with sessions() as source_session, source_session.begin():
            evaluations = evaluation_coordinator(source_session)
            return await classify_post_submit_delivery(
                delivery,
                evaluations=evaluations,
                requests=evaluation_delivery_request_reader(source_session, evaluations),
                outcomes=post_submit_delivery_outcome(source_session, sessions),
            )

    return PostSubmitDeliveryService(
        session,
        actor_profile_id=context.actor_profile_id,
        deliveries=finalized_unknown_deliveries(session),
        events=outbox_append(session),
        evaluations=evaluation_coordinator(session),
        requests=evaluation_delivery_request_reader(session, evaluation_coordinator(session)),
        outcomes=post_submit_delivery_outcome(session, sessions),
        read_authority=post_submit_delivery_read_authorization(
            session,
            context,
            cursor_secret,
        ),
        authorization=post_submit_delivery_authorization(session, context),
        detached_classify=detached_classify,
    )


def post_submission_executor(*, sessions, materialization):
    """Compose the sole executor with exact fixed-service AUTH at both phases."""
    from app.adapters.outbox import outbox_append
    from app.modules.checkers.execution import PostSubmissionExecutor
    from app.adapters.auth import post_submit_execution_authority

    from app.adapters.projects import project_locked_policy_context_port

    return PostSubmissionExecutor(
        sessions=sessions,
        materialization=materialization,
        execute_authority=post_submit_execution_authority,
        finalize_authority=post_submit_execution_authority,
        outbox=outbox_append,
        review_modes=project_locked_policy_context_port,
    )


def checker_output_reservations(session):
    """Resolve exact call custody with TASK-before-CHECKERS request locking."""
    from app.adapters.tasks import evaluation_task_guard
    from app.adapters.model_usage import model_evidence_custody, model_recovery_sources
    from app.modules.checkers.model_usage_custody import (
        CheckerOutputReservations,
        ModelCallCurrentExecution,
    )

    tasks = evaluation_task_guard(session)
    return CheckerOutputReservations(
        session,
        current=ModelCallCurrentExecution(
            session, tasks=tasks, recovery=model_recovery_sources(session)
        ),
        tasks=tasks,
        model=model_evidence_custody(session),
    )


def model_call_service(session, authority):
    """Compose durable model spending with exact TASK and ART owner ports."""
    from app.adapters.tasks import evaluation_task_guard
    from app.adapters.artifacts import checker_model_evidence
    from app.adapters.model_usage import (
        model_call_service as shared_model_call_service,
        model_recovery_sources,
    )
    from app.modules.checkers.model_usage_custody import ModelCallCurrentExecution

    return shared_model_call_service(
        session,
        authority=authority,
        current_execution=ModelCallCurrentExecution(
            session,
            tasks=evaluation_task_guard(session),
            recovery=model_recovery_sources(session),
        ),
        evidence=checker_model_evidence(session),
    )


def model_invocation_grants(session, authority):
    """Compose short-lived image capabilities without creating provider effects."""
    from app.adapters.tasks import evaluation_task_guard
    from app.adapters.model_usage import (
        model_invocation_grants as shared_model_invocation_grants,
        model_recovery_sources,
    )
    from app.modules.checkers.model_usage_custody import ModelCallCurrentExecution

    return shared_model_invocation_grants(
        session,
        authority=authority,
        current_execution=ModelCallCurrentExecution(
            session,
            tasks=evaluation_task_guard(session),
            recovery=model_recovery_sources(session),
        ),
    )


def checker_model_proxy(**ports):
    """Compose provider orchestration from typed CHECKERS, AUTH and ART ports."""
    from app.adapters.checkers.model_proxy import CheckerModelProxy

    return CheckerModelProxy(**ports)


def current_post_submit_execution(session):
    """Keep ART currentness checks behind the CHECKERS owner port."""
    from app.modules.checkers.execution_coordination import CurrentExecution

    return CurrentExecution(session)


def selected_submission_evaluation_content(
    task_context: TaskSubmissionContextFacts,
    policy: LockedExternalPostSubmitPolicy,
) -> SelectedPostSubmissionContent:
    """Bind selected POST policy to exact TASK lineage without a catalogue hash."""
    locked = task_context.locked_policy
    references = task_context.locked_project_context
    return SelectedPostSubmissionContent(
        project_id=references.project_id,
        expected_context=SelectedPostSubmitLockedContext(
            guide_version=locked.locked_guide_version,
            source_id=locked.locked_guide_source_snapshot_id,
            source_hash=locked.locked_guide_source_snapshot_hash,
            effective_policy_id=(locked.locked_effective_project_submission_artifact_policy_id),
            effective_policy_hash=(locked.locked_effective_project_submission_artifact_policy_hash),
            pre_policy_id=locked.locked_pre_submit_checker_policy_id,
            pre_policy_hash=locked.locked_pre_submit_checker_bundle_hash,
            post_policy_id=(locked.locked_post_submit_checker_policy_id),
            post_policy_version=(locked.locked_post_submit_checker_policy_version),
            post_policy_hash=(locked.locked_post_submit_checker_policy_hash),
            review_policy_id=locked.locked_review_policy_id,
            review_generation=locked.locked_review_policy_generation,
            review_hash=locked.locked_review_policy_hash,
            revision_policy_id=locked.locked_revision_policy_id,
            revision_generation=locked.locked_revision_policy_generation,
            revision_hash=locked.locked_revision_policy_hash,
        ),
        policy=policy,
    )


def delivery_bound_post_submission_executor(
    *, sessions, materialization, envelope, request, forge_facts, selected_execution=None
):
    """Add invocation custody to the existing executor without registering delivery."""
    from app.adapters.auth import post_submit_execution_authority
    from app.adapters.outbox import outbox_append, outbox_invocation_fence
    from app.adapters.tasks import evaluation_task_guard
    from app.modules.checkers.delivery_authority import DeliveryExecutionAuthority
    from app.modules.checkers.execution import PostSubmissionExecutor

    def authority(session):
        return DeliveryExecutionAuthority(
            authority=post_submit_execution_authority(session),
            tasks=evaluation_task_guard(session),
            fence=outbox_invocation_fence(session),
            envelope=envelope,
            request=request,
        )

    from app.adapters.projects import project_locked_policy_context_port

    return PostSubmissionExecutor(
        sessions=sessions,
        execute_authority=authority,
        finalize_authority=authority,
        materialization=materialization,
        selected_execution=selected_execution,
        forge_facts=forge_facts,
        outbox=outbox_append,
        review_modes=project_locked_policy_context_port,
    )


def reconciliation_bound_post_submission_executor(
    *,
    sessions,
    materialization,
    child,
    original,
    payload,
    request,
    forge_facts,
    selected_execution=None,
):
    """Run the existing executor behind exact original-and-child recovery custody."""
    from app.adapters.auth import (
        post_submit_delivery_cause_authorization,
        post_submit_execution_authority,
    )
    from app.adapters.outbox import (
        committed_invocation_reader,
        finalized_unknown_deliveries,
        outbox_append,
    )
    from app.adapters.tasks import evaluation_task_guard
    from app.modules.checkers.delivery_authority import DeliveryExecutionAuthority
    from app.modules.checkers.delivery_reconciliation_handler import (
        ReconciliationInvocationCustody,
    )
    from app.modules.checkers.execution import PostSubmissionExecutor

    observer = committed_invocation_reader(sessions)

    def authority(session):
        cause = post_submit_delivery_cause_authorization(session)
        custody = ReconciliationInvocationCustody(
            child=child,
            original=original,
            observer=observer,
            deliveries=finalized_unknown_deliveries(session),
        )

        async def validate_cause():
            await cause.validate_cause(payload, original)

        return DeliveryExecutionAuthority(
            authority=post_submit_execution_authority(session),
            tasks=evaluation_task_guard(session),
            fence=custody,
            envelope=original,
            request=request,
            cause=validate_cause,
        )

    from app.adapters.projects import project_locked_policy_context_port

    return PostSubmissionExecutor(
        sessions=sessions,
        execute_authority=authority,
        finalize_authority=authority,
        materialization=materialization,
        selected_execution=selected_execution,
        forge_facts=forge_facts,
        outbox=outbox_append,
        review_modes=project_locked_policy_context_port,
    )


def post_submit_delivery_reconciliation_handler(*, sessions, materialization):
    """Compose the single registered child handler from existing owner operations."""
    from app.adapters.auth import post_submit_delivery_cause_authorization
    from app.adapters.outbox import (
        committed_invocation_reader,
        finalized_unknown_deliveries,
    )
    from app.adapters.tasks import (
        evaluation_delivery_request_reader,
        reconciliation_task_post_submit_outcome,
    )
    from app.core.config import get_settings
    from app.modules.checkers.delivery_reconciliation_handler import (
        PostSubmitDeliveryReconciliationHandler,
    )

    observer = committed_invocation_reader(sessions)

    def executor(child, original, payload, request):
        return reconciliation_bound_post_submission_executor(
            sessions=sessions,
            materialization=materialization,
            child=child,
            original=original,
            payload=payload,
            request=request,
            selected_execution=configured_post_submit_external_execution(
                get_settings(), sessions=sessions
            ),
            forge_facts=configured_forge_facts(get_settings()),
        )

    return PostSubmitDeliveryReconciliationHandler(
        sessions,
        observer=observer,
        deliveries=finalized_unknown_deliveries,
        evaluations=evaluation_coordinator,
        requests=evaluation_delivery_request_reader,
        authorization=post_submit_delivery_cause_authorization,
        outcomes=lambda session, custody, cause: reconciliation_task_post_submit_outcome(
            session, sessions, custody, cause
        ),
        executor=executor,
    )


def selected_pre_submit_run_reader(session):
    """Read retained selected PRE runs for their own contributor; the caller authorizes."""
    from app.modules.checkers.selected_pre_submit_reads import SelectedPreSubmitRunReader

    return SelectedPreSubmitRunReader(session)


def trial_evidence_reservations(session, request, profiles):
    """Bind trial evidence to the exact current external execution and trusted profile."""
    from app.adapters.auth import post_submit_execution_authority
    from app.adapters.tasks import evaluation_task_guard
    from app.modules.checkers.trial_evidence import TrialEvidenceReservations

    return TrialEvidenceReservations(
        session, request=request, profiles=profiles,
        tasks=evaluation_task_guard(session), authority=post_submit_execution_authority(session),
    )
