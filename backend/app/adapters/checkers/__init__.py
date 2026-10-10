"""CHECKER-owned composition adapters."""

import asyncio
import json
from app.adapters.checkers.external_service import (
    EXTERNAL_CHECKER_CAPABILITY_KEY,
    EXTERNAL_CHECKER_PROVIDER_KEY,
    UnixSocketExternalCheckerAdapter,
)
from app.interfaces.external_services import ExternalServiceAdapterFactory
from app.modules.artifacts.api import SubmissionBundleFile
from app.modules.tasks.api import TaskSubmissionContextFacts
from app.modules.projects.api import ProjectLockedPolicyContextFacts
from app.modules.checkers.api import SubmissionPacketView
from app.modules.checkers.api.artifact_paths import required_evidence_path
from app.modules.checkers.api.post_submit_catalogue import CompiledPostSubmitPolicy
from app.modules.checkers.api.post_submit import (
    PostSubmissionEvaluationContent, ExpectedPostSubmitContext, ObservedPostSubmitContext,
    PostSubmitPolicyInputs, PostSubmissionStructuralInput, PostSubmitManifestEntry, PostSubmitEvidenceEntry,
)
from app.modules.checkers.api.history import CheckerHistoryReadPort
from app.modules.checkers.api.execution import EvaluationCoordinationPort
from typing import Any, BinaryIO, Protocol
from pathlib import Path

from app.modules.checkers.api.pre_submit_catalogue import PreSubmissionCapabilityProjection
from app.modules.checkers.api.post_submit_catalogue import PostSubmitCatalogue
from app.modules.checkers.api.policy_compilation import PreSubmissionPolicyCompilationPort

from app.modules.checkers.api import (
    PreSubmissionExecutionFacts,
    PreSubmissionInfrastructureUnavailableError,
)
from app.modules.checkers.catalogue import (
    PreSubmissionCheckerCatalogue,
    project_guide_pre_submission_capabilities,
    build_pre_submission_checker_catalogue,
    parse_disabled_pre_submission_checker_ids,
)
from app.modules.checkers.pre_submit_execution import (
    DefaultPreSubmissionExecutionError,
    DefaultPreSubmissionExecutionInput,
    EffectivePreSubmissionProcessor,
)


def external_checker_execution_factory(
    *, socket_path: Path, timeout_seconds: float
) -> ExternalServiceAdapterFactory[UnixSocketExternalCheckerAdapter]:
    """Compose the unselected instance-local external checker adapter factory."""
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


def configured_external_checker_execution_factory(settings):
    """Map validated settings into the unselected explicit adapter factory."""
    if (
        settings.external_checker_service_socket is None
        or settings.external_checker_material_root is None
    ):
        raise ValueError("external checker service is not configured")
    return external_checker_execution_factory(
        socket_path=settings.external_checker_service_socket,
        timeout_seconds=float(settings.external_checker_service_timeout_seconds),
    )


class _ExecutionRequest(Protocol):
    plan: Any
    commitment: Any
    inspection: Any
    manifest: Any
    change_gate: Any
    packet: Any
    prepared_generation_id: Any
    storage_scheme: str


class _PublicFactsCheckerProcessor:
    """Project the private CHECKER processor result to public facts."""

    def __init__(self, processor: EffectivePreSubmissionProcessor) -> None:
        self._processor = processor

    def abort(self) -> None:
        self._processor.abort()

    async def process(self, reader: BinaryIO, workspace: Path) -> PreSubmissionExecutionFacts:
        try:
            result = await asyncio.to_thread(self._processor.process_blocking, reader, workspace)
            return result.bounded_facts()
        except DefaultPreSubmissionExecutionError as exc:
            raise PreSubmissionInfrastructureUnavailableError(str(exc)) from exc


class PreSubmitCheckerExecutionAdapter:
    """Build the private CHECKER processor behind dependency-safe facts."""

    def __init__(self, *, catalogue: PreSubmissionCheckerCatalogue, archive_inspector: Any):
        self._catalogue = catalogue
        self._archive_inspector = archive_inspector

    @property
    def catalogue_manifest_sha256(self) -> str:
        return self._catalogue.manifest_sha256

    def build(self, request: _ExecutionRequest) -> _PublicFactsCheckerProcessor:
        return _PublicFactsCheckerProcessor(
            EffectivePreSubmissionProcessor(
                archive_inspector=self._archive_inspector,
                catalogue=self._catalogue,
                execution_input=DefaultPreSubmissionExecutionInput(
                    plan=request.plan,
                    commitment=request.commitment,
                    inspection=request.inspection,
                    manifest=request.manifest,
                    change_gate=request.change_gate,
                    packet=request.packet,
                    prepared_generation_id=request.prepared_generation_id,
                    storage_scheme=request.storage_scheme,
                ),
            )
        )


def project_guide_pre_submission_catalogue() -> PreSubmissionCapabilityProjection:
    """Compose the canonical immutable pre-submit capabilities for guide setup."""
    return project_guide_pre_submission_capabilities(build_pre_submission_checker_catalogue())


def project_guide_approval_compiler(*, disabled_checker_ids: str = "") -> tuple[
    PreSubmissionPolicyCompilationPort, PreSubmissionCapabilityProjection, PostSubmitCatalogue,
]:
    """Compose one canonical planner and its matching pre/post capabilities."""
    from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue

    planner = build_pre_submission_checker_catalogue(
        disabled_entry_ids=parse_disabled_pre_submission_checker_ids(disabled_checker_ids),
    )
    return planner, project_guide_pre_submission_capabilities(planner), current_post_submit_catalogue()


def installed_post_submit_catalogue() -> PostSubmitCatalogue:
    """Resolve catalogue facts only after checking the installed handler registry."""
    from app.modules.checkers.post_submit_catalogue import build_post_submit_catalogue
    from app.modules.checkers.runner import default_checker_registry

    return build_post_submit_catalogue(default_checker_registry())


def checker_history_repository(session) -> CheckerHistoryReadPort:
    """Compose retained CHECKERS reads through TASK's public ownership port."""
    from app.modules.checkers.history import CheckerHistoryRepository
    return CheckerHistoryRepository(session)


def evaluation_coordinator(session) -> EvaluationCoordinationPort:
    """Compose required TASK locking before CHECKERS reservation custody."""
    from app.modules.checkers.execution_coordination import EvaluationCoordinator
    from app.adapters.tasks import evaluation_task_guard

    return EvaluationCoordinator(session, tasks=evaluation_task_guard(session))


def post_submission_executor(*, sessions, materialization):
    """Compose the sole executor with exact fixed-service AUTH at both phases."""
    from app.adapters.outbox import outbox_append
    from app.modules.checkers.execution import PostSubmissionExecutor
    from app.adapters.auth import post_submit_execution_authority
    from app.modules.checkers.runner import default_checker_registry
    return PostSubmissionExecutor(sessions=sessions, materialization=materialization,
        execute_authority=post_submit_execution_authority,
        finalize_authority=post_submit_execution_authority,
        registry=default_checker_registry(), outbox=outbox_append)


def checker_output_reservations(session):
    """Resolve exact active run/lease custody; current catalogue has zero slots."""
    from app.modules.checkers.execution_coordination import CheckerOutputReservations
    return CheckerOutputReservations(session)


def current_post_submit_execution(session):
    """Keep ART currentness checks behind the CHECKERS owner port."""
    from app.modules.checkers.execution_coordination import CurrentExecution
    return CurrentExecution(session)


def submission_evaluation_content(
    task_context: TaskSubmissionContextFacts,
    project_context: ProjectLockedPolicyContextFacts,
    packet: SubmissionPacketView,
    files: tuple[SubmissionBundleFile, ...],
    archive_sha256: str,
) -> PostSubmissionEvaluationContent:
    """Project inspected files and locked policies without executing a checker.

    Before admission, observed context is the locked TASK context. A dispatcher
    must first verify stored Submission lineage against these same facts; this
    projection never proves stored ownership or replaces the evaluation guard.
    """
    from app.adapters.tasks import validate_submission_policy_context

    validate_submission_policy_context(task_context, project_context)
    stamps = task_context.locked_policy
    expected = ExpectedPostSubmitContext(
        guide_version=stamps.locked_guide_version,
        source_id=stamps.locked_guide_source_snapshot_id,
        source_hash=stamps.locked_guide_source_snapshot_hash,
        effective_policy_id=stamps.locked_effective_project_submission_artifact_policy_id,
        effective_policy_hash=stamps.locked_effective_project_submission_artifact_policy_hash,
        pre_policy_id=stamps.locked_pre_submit_checker_policy_id,
        pre_policy_hash=stamps.locked_pre_submit_checker_bundle_hash,
        post_policy_id=stamps.locked_post_submit_checker_policy_id,
        post_policy_version=stamps.locked_post_submit_checker_policy_version,
        post_policy_hash=stamps.locked_post_submit_checker_policy_hash,
        review_policy_id=stamps.locked_review_policy_id,
        review_generation=stamps.locked_review_policy_generation,
        review_hash=stamps.locked_review_policy_hash,
        revision_policy_id=stamps.locked_revision_policy_id,
        revision_generation=stamps.locked_revision_policy_generation,
        revision_hash=stamps.locked_revision_policy_hash,
    )
    effective = json.loads(project_context.effective_policy.value)
    policy_inputs = PostSubmitPolicyInputs(
        required_evidence_keys=tuple(item["key"] for item in effective.get("required_evidence", [])
                                     if item.get("required", True)),
        required_artifact_paths=tuple(item["path"] for item in effective.get("required_artifacts", [])
                                      if item.get("required", True)),
        forbidden_artifact_patterns=tuple(item["pattern"] for item in effective.get("forbidden_artifacts", [])
                                         if item.get("pattern")),
        required_attestation_terms=tuple(term for term in effective.get("attestation_terms", []) if term),
    )
    by_path = {item.normalized_path: item for item in files}
    return PostSubmissionEvaluationContent(
        project_id=project_context.project_id,
        expected_context=expected,
        catalogue=installed_post_submit_catalogue(),
        policy=CompiledPostSubmitPolicy.model_validate_json(project_context.compiled_post_submit_policy.value),
        structural_input=PostSubmissionStructuralInput(
            summary=packet.summary, worker_attestation=packet.contributor_attestation,
            package_hash=archive_sha256, criteria=task_context.acceptance_criteria or "",
            manifest=tuple(PostSubmitManifestEntry(
                artifact=item.normalized_path, hash=item.sha256, size_bytes=item.byte_count,
            ) for item in files),
            evidence=tuple(PostSubmitEvidenceEntry(
                label=key, type="file", key=key, uri=item.normalized_path, hash=item.sha256,
            ) for key in policy_inputs.required_evidence_keys
              for item in (by_path.get(required_evidence_path(key)),) if item is not None),
            policy_inputs=policy_inputs,
            observed_context=ObservedPostSubmitContext(**expected.model_dump()),
        ),
    )


def delivery_bound_post_submission_executor(*, sessions, materialization, envelope, request):
    """Add invocation custody to the existing executor without registering delivery."""
    from app.adapters.auth import post_submit_execution_authority
    from app.adapters.outbox import outbox_append, outbox_invocation_fence
    from app.adapters.tasks import evaluation_task_guard
    from app.modules.checkers.delivery_authority import DeliveryExecutionAuthority
    from app.modules.checkers.execution import PostSubmissionExecutor
    from app.modules.checkers.runner import default_checker_registry

    def authority(session):
        return DeliveryExecutionAuthority(
            authority=post_submit_execution_authority(session), tasks=evaluation_task_guard(session),
            fence=outbox_invocation_fence(session), envelope=envelope, request=request,
        )

    return PostSubmissionExecutor(
        sessions=sessions, execute_authority=authority, finalize_authority=authority,
        materialization=materialization, registry=default_checker_registry(), outbox=outbox_append,
    )
