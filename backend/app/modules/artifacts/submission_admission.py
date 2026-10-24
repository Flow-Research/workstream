"""Hidden evidence-bound durable put handoff for one checked submission ZIP."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from dataclasses import dataclass, field, replace
import re
from uuid import UUID
from app.core.hashing import canonical_json_hash
from app.interfaces.trusted_submission_intake import TrustedSubmissionIntakeAdapter, TrustedIntakePreparation
from app.interfaces.external_services import ExternalServiceAdapterError
from app.core.identifiers import new_record_id

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.api import (
    SubmissionBundlePreparationCheckFailed,
    SubmissionBundlePreparationRejected,
    SubmissionBundlePreparationInfrastructureUnavailable,
    SubmissionBundlePreparationRequest,
    SubmissionBundlePreparationResult,
    SubmissionBundlePreparationStatus,
    SubmissionBundlePreparationUnavailable,
)
from app.modules.artifacts.api.submission_preparation import public_pre_submission_results
from app.modules.artifacts.models import (
    ArtifactContent,
    ArtifactOperationReceipt,
    ArtifactPutAttempt,
    ArtifactPutObservationReceipt,
    ArtifactReplica,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
    SubmissionBundleAdmission,
    SubmissionBundleDurableIntent,
)
from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactPreparationDeadlineError
from app.modules.artifacts.schemas import (
    ArtifactAdmissionResult,
    ArtifactAuthorityDeniedError,
    SubmissionBundleArtifactAdmissionRequest,
)
from app.modules.artifacts.submission_authorization import (
    SubmissionBundlePreparedAuthorization,
)
from app.modules.artifacts.service import (
    ArtifactAdmissionService,
    ArtifactStorageOrchestrator,
)
from app.modules.artifacts.sources import PreparedArtifact
from app.modules.artifacts.trusted_intake import prepared_trusted_intake, TrustedArchiveInspector, prepare_bytes_with_intake
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveRejectedError,
    SubmissionArchiveLimits,
)
from app.modules.artifacts.submission_authorization import (
    SubmissionBundlePreparationAuthorization,
)
from app.modules.artifacts.submission_custody import SubmissionBundlePreparedCustody
from app.modules.artifacts.submission_manifest import (
    SubmissionCanonicalPredecessor,
    build_submission_manifest,
)
from app.modules.artifacts.submission_materialization import (
    PreparedBundleMaterializationRequest,
    PreparedBundleMaterializationService,
)
from app.modules.artifacts.selected_pre_submit_admission import (
    bind_selected_pre_submit_admission,
    build_selected_pre_submit_reservation,
    selected_pre_submit_attempt_request_digest,
)
from app.modules.artifacts.selected_pre_submit_execution import (
    SelectedPreSubmitExecutionService,
)
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitCompletion,
    SelectedPreSubmitCoordinationPort,
    SelectedPreSubmitCurrentFacts,
    SelectedPreSubmitExecutionFacts,
    SelectedPreSubmitReservationFacts,
    SelectedPreSubmitRequestConflict,
    SelectedPreSubmitUnavailable,
)
from app.modules.checkers.api.external_policy import (
    LockedExternalCheckerPolicies,
    selected_pre_submit_execution_budget_ms,
)
from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
from app.modules.projects.api import (
    ProjectLockedPolicyContextFacts,
    ProjectLockedPolicyContextPort,
    ProjectLockedPolicyContextRequest,
    ProjectLockedPolicyContextUnavailable,
)
from app.modules.projects.api.policy_lineage import RevisionPolicySemantics
from app.modules.tasks.api.submission_context import require_revision_capacity
from app.modules.tasks.api import (
    TaskRetainedSubmissionParentsRequest,
    TaskSubmissionContextFacts,
    TaskSubmissionContextPort,
    TaskSubmissionContextRequest,
    TaskSubmissionContextUnavailable,
)


def validate_submission_packet_headers(summary: str, attestation: str) -> None:
    """Reject lossy header decoding only after contributor preflight succeeds."""
    try:
        summary.encode("ascii")
        attestation.encode("ascii")
    except UnicodeEncodeError as exc:
        raise SubmissionBundlePreparationRejected(
            "submission_bundle_packet_header_encoding_invalid"
        ) from exc


def require_revision_preparation_acknowledgement(
    task: TaskSubmissionContextFacts,
    request: SubmissionBundlePreparationRequest,
) -> None:
    """Compare the contributor's explicit acknowledgement after fresh authority."""
    supplied_id = request.revision_preparation_id
    supplied_sha256 = request.revision_preparation_sha256
    if task.predecessor is None:
        if supplied_id is not None or supplied_sha256 is not None:
            raise SubmissionBundlePreparationRejected("revision_acknowledgement_invalid")
        return
    context = task.revision_context
    if context is None:
        raise SubmissionBundlePreparationRejected("revision_context_changed")
    if supplied_id is None and supplied_sha256 is None:
        raise SubmissionBundlePreparationRejected("revision_acknowledgement_required")
    if not isinstance(supplied_id, str) or not isinstance(supplied_sha256, str):
        raise SubmissionBundlePreparationRejected("revision_acknowledgement_invalid")
    try:
        acknowledged_id = UUID(supplied_id)
    except ValueError as exc:
        raise SubmissionBundlePreparationRejected("revision_acknowledgement_invalid") from exc
    if re.fullmatch(r"sha256:[0-9a-f]{64}", supplied_sha256) is None:
        raise SubmissionBundlePreparationRejected("revision_acknowledgement_invalid")
    if (
        context.source_submission_id != task.predecessor.submission_id
        or context.source_routing_manifest_id != task.checker_remediation_manifest_id
        or acknowledged_id != context.preparation_id
        or supplied_sha256 != context.preparation_sha256
    ):
        raise SubmissionBundlePreparationRejected("revision_context_changed")


@dataclass(frozen=True, slots=True)
class SubmissionBundleDurablePutRequest:
    """Exact live custody and opaque authority for one final durable handoff."""

    prepared_authorization: object
    prepared_artifact: PreparedArtifact
    replay_durable_intent_id: UUID | None = None
    selected_completion: SelectedPreSubmitCompletion = field(kw_only=True)

    def __post_init__(self) -> None:
        if type(self.selected_completion) is not SelectedPreSubmitCompletion:
            raise ValueError("submission bundle durable PRE custody is invalid")


@dataclass(frozen=True, slots=True)
class SubmissionBundleDurablePutResult:
    """Bounded durable operation result without provider coordinates."""

    put_attempt_id: UUID
    operation_identity: str
    status: str
    replayed: bool
    admission_id: UUID | None
    selected_pre_submit_run_id: UUID


class SubmissionBundleDurablePutService:
    """Commit final authority and intent before invoking the generic provider path."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        admission: ArtifactAdmissionService,
        storage: ArtifactStorageOrchestrator,
        authorization: SubmissionBundlePreparedAuthorization,
        task_contexts: TaskSubmissionContextPort,
        project_contexts: ProjectLockedPolicyContextPort,
    ) -> None:
        self._session = session
        self._admission = admission
        self._storage = storage
        self._authorization = authorization
        self._task_contexts = task_contexts
        self._project_contexts = project_contexts

    async def admit_in_transaction(
        self,
        request: SubmissionBundleDurablePutRequest,
    ) -> tuple[PreparedArtifact, UUID, ArtifactAdmissionResult]:
        """Persist intent after the preparation command locks its authorized context.

        The caller holds TASK, actor, PROJECT and grant locks in that order;
        the admission reads below revalidate those already-locked owner facts.
        """
        if type(request) is not SubmissionBundleDurablePutRequest:
            raise TypeError("invalid submission bundle durable put request")
        transaction = self._session.sync_session.get_transaction()
        prepared = request.prepared_artifact
        if (
            transaction is None
            or not transaction.is_active
            or self._session.in_nested_transaction()
            or type(prepared) is not PreparedArtifact
            or type(request.selected_completion) is not SelectedPreSubmitCompletion
        ):
            if type(prepared) is PreparedArtifact:
                await prepared.close()
            raise RuntimeError("submission bundle durable transaction is unavailable")
        try:
            custody = SubmissionBundlePreparedCustody._from_selected_pre_submit(
                prepared=prepared, completion=request.selected_completion,
            )
            selected_run_id = custody.selected_reservation.attempt_id
            admission = await self._admission.admit(
                SubmissionBundleArtifactAdmissionRequest(
                    pre_submit_evidence_set_id=None,
                    custody=custody,
                    replay_durable_intent_id=request.replay_durable_intent_id,
                    selected_pre_submit_run_id=selected_run_id,
                    selected_terminal_digest=(
                        custody.selected_terminal_digest
                    ),
                ),
                submission_prepared_authorization=self._authorization,
                submission_task_contexts=self._task_contexts,
                submission_project_contexts=self._project_contexts,
                prepared_authorization=request.prepared_authorization,
                existing_transaction=True,
            )
            return prepared, selected_run_id, admission
        except BaseException:
            await prepared.close()
            raise

    async def publish_after_commit(
        self,
        prepared: PreparedArtifact,
        lineage_id: UUID,
        admission: ArtifactAdmissionResult,
    ) -> SubmissionBundleDurablePutResult:
        """Hand the exact ZIP to storage only after the durable transaction ended."""
        if self._session.in_transaction():
            await prepared.close()
            raise RuntimeError("submission bundle durable transaction is still active")
        try:
            admission_id = None
            if admission.replayed:
                async with self._session.begin():
                    admission_id = await current_submission_bundle_admission_id(
                        self._session,
                        put_attempt_id=admission.attempt_id,
                    )
            if admission_id is not None:
                return SubmissionBundleDurablePutResult(
                    put_attempt_id=admission.attempt_id,
                    operation_identity=admission.operation_identity,
                    status="ready",
                    replayed=True,
                    admission_id=admission_id,
                    selected_pre_submit_run_id=lineage_id,
                )
            if admission.replayed and admission.status == "object_confirmed":
                return SubmissionBundleDurablePutResult(
                    put_attempt_id=admission.attempt_id,
                    operation_identity=admission.operation_identity,
                    status="object_confirmed",
                    replayed=True,
                    admission_id=None,
                    selected_pre_submit_run_id=lineage_id,
                )
            if admission.replayed:
                status = await self._storage.resume_committed_put(
                    attempt_id=admission.attempt_id,
                    source=prepared.committed_source,
                )
            else:
                status = await self._storage.execute_committed_put(
                    attempt_id=admission.attempt_id,
                    source=prepared.committed_source,
                )
            async with self._session.begin():
                admission_id = await current_submission_bundle_admission_id(
                    self._session,
                    put_attempt_id=admission.attempt_id,
                )
            return SubmissionBundleDurablePutResult(
                put_attempt_id=admission.attempt_id,
                operation_identity=admission.operation_identity,
                status=status,
                replayed=admission.replayed,
                admission_id=admission_id,
                selected_pre_submit_run_id=lineage_id,
            )
        finally:
            await prepared.close()


class SubmissionBundleAdmissionPublicationError(RuntimeError):
    """Durable verification lineage cannot publish a trusted ready admission."""


class SubmissionBundleAdmissionPublisher:
    """Project verified submission bytes into one idempotent ready admission."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_retained_submission_parents(
        self,
        *,
        verification_job_id: str,
        task_contexts: TaskSubmissionContextPort | None,
    ) -> TaskRetainedSubmissionParentsRequest | None:
        """Take TASK's retained parent locks before any terminal ART lock."""
        with self._session.no_autoflush:
            row = (
                await self._session.execute(
                    select(
                        ArtifactPutAttempt.producer_request_type,
                        SubmissionBundleDurableIntent.selected_request_json,
                    )
                    .select_from(ArtifactVerificationJob)
                    .join(
                        ArtifactPutAttempt,
                        ArtifactPutAttempt.id
                        == ArtifactVerificationJob.originating_put_attempt_id,
                    )
                    .outerjoin(
                        SubmissionBundleDurableIntent,
                        SubmissionBundleDurableIntent.put_attempt_id
                        == ArtifactPutAttempt.id,
                    )
                    .where(ArtifactVerificationJob.id == verification_job_id)
                )
            ).one_or_none()
        if row is None:
            raise SubmissionBundleAdmissionPublicationError(
                "verification job is unavailable"
            )
        if row.producer_request_type != "submission_bundle":
            return None
        if task_contexts is None:
            raise RuntimeError("submission verification TASK composition is unavailable")
        try:
            selected = SelectedPreSubmitReservationFacts.from_canonical_body(
                row.selected_request_json
            )
        except (TypeError, ValueError) as exc:
            raise SubmissionBundleAdmissionPublicationError(
                "selected PRE request snapshot is invalid"
            ) from exc
        request = TaskRetainedSubmissionParentsRequest(
            project_id=selected.project_id,
            task_id=selected.task_id,
            assignment_id=selected.assignment_id,
            contributor_id=selected.actor_profile_id,
        )
        try:
            await task_contexts.lock_retained_submission_parents(request)
        except TaskSubmissionContextUnavailable as exc:
            raise SubmissionBundleAdmissionPublicationError(
                "selected PRE retained TASK identity is invalid"
            ) from exc
        return request

    async def publish_verified(
        self,
        *,
        verification_job_id: str,
        verification_receipt_id: str,
        retained_parents: TaskRetainedSubmissionParentsRequest | None,
    ) -> SubmissionBundleAdmission | None:
        """Publish only submission-bundle lineage; ignore other producer types."""
        job = await self._session.scalar(
            select(ArtifactVerificationJob)
            .where(ArtifactVerificationJob.id == verification_job_id)
            .with_for_update(key_share=True)
        )
        if job is None:
            raise SubmissionBundleAdmissionPublicationError("verification job is unavailable")
        attempt = await self._session.scalar(
            select(ArtifactPutAttempt)
            .where(ArtifactPutAttempt.id == job.originating_put_attempt_id)
            .with_for_update(key_share=True)
        )
        if attempt is None:
            raise SubmissionBundleAdmissionPublicationError("put attempt is unavailable")
        if attempt.producer_request_type != "submission_bundle":
            return None
        intent = await self._session.scalar(
            select(SubmissionBundleDurableIntent)
            .where(SubmissionBundleDurableIntent.put_attempt_id == attempt.id)
            # Serialize publication on the immutable intent.  A weaker key-share
            # lock lets two verifier transactions both miss the admission and
            # race on its uniqueness constraint.
            .with_for_update()
        )
        if intent is None:
            raise SubmissionBundleAdmissionPublicationError("durable intent is unavailable")
        if intent.pre_submit_evidence_set_id is not None or intent.selected_pre_submit_run_id is None:
            raise SubmissionBundleAdmissionPublicationError("external PRE durable intent is unavailable")
        try:
            selected = SelectedPreSubmitReservationFacts.from_canonical_body(
                intent.selected_request_json
            )
        except (TypeError, ValueError) as exc:
            raise SubmissionBundleAdmissionPublicationError(
                "selected PRE request snapshot is invalid"
            ) from exc
        locked_parents = TaskRetainedSubmissionParentsRequest(
            project_id=selected.project_id,
            task_id=selected.task_id,
            assignment_id=selected.assignment_id,
            contributor_id=selected.actor_profile_id,
        )
        if retained_parents is None:
            raise RuntimeError("submission verification TASK composition is unavailable")
        if locked_parents != retained_parents:
            raise SubmissionBundleAdmissionPublicationError(
                "selected PRE retained TASK identity changed"
            )
        existing = await self._session.scalar(
            select(SubmissionBundleAdmission)
            .where(SubmissionBundleAdmission.durable_intent_id == intent.id)
            .with_for_update()
        )
        if existing is not None:
            return existing
        terminal = intent.selected_terminal_json
        if (
            selected.admission_lineage is None
            or selected.attempt_id != UUID(intent.selected_pre_submit_run_id)
            or selected.request_digest != intent.selected_request_digest
            or type(terminal) is not dict
            or canonical_json_hash(terminal) != intent.selected_terminal_digest
            or terminal.get("request_digest") != selected.request_digest
            or terminal.get("outcome") != "completed"
            or type(terminal.get("execution")) is not dict
            or terminal["execution"].get("eligible") is not True
        ):
            raise SubmissionBundleAdmissionPublicationError(
                "selected PRE terminal snapshot is invalid"
            )
        replica = await self._session.scalar(
            select(ArtifactReplica)
            .where(ArtifactReplica.id == job.replica_id)
            .with_for_update(key_share=True)
        )
        receipt = await self._session.scalar(
            select(ArtifactVerificationReceipt)
            .where(ArtifactVerificationReceipt.id == verification_receipt_id)
            .with_for_update(key_share=True)
        )
        content = (
            await self._session.scalar(
                select(ArtifactContent)
                .where(ArtifactContent.id == replica.content_id)
                .with_for_update(key_share=True)
            )
            if replica is not None
            else None
        )
        lineage = selected.admission_lineage
        if not self._matches_verified_bytes(
            attempt, job, replica, content, receipt,
            project_id=str(selected.project_id), task_id=str(selected.task_id),
            actor_profile_id=str(selected.actor_profile_id),
            archive_sha256=selected.archive_sha256,
            archive_byte_count=selected.archive_byte_count,
        ):
            raise SubmissionBundleAdmissionPublicationError(
                "verified submission bundle lineage does not match"
            )
        operation_receipt_id, observation_receipt_id = await self._write_receipt_ids(attempt)
        assert replica is not None and content is not None and receipt is not None
        assert lineage is not None
        now = await self._session.scalar(select(func.now()))
        admission = SubmissionBundleAdmission(
            id=str(new_record_id()), durable_intent_id=intent.id,
            pre_submit_evidence_set_id=None,
            selected_pre_submit_run_id=str(selected.attempt_id),
            put_attempt_id=attempt.id, artifact_content_id=content.id,
            verified_replica_id=replica.id, verification_receipt_id=receipt.id,
            put_operation_receipt_id=operation_receipt_id,
            put_observation_receipt_id=observation_receipt_id,
            actor_profile_id=str(selected.actor_profile_id),
            identity_link_id=str(selected.identity_link_id),
            project_id=str(selected.project_id), task_id=str(selected.task_id),
            assignment_id=str(selected.assignment_id),
            predecessor_submission_id=(
                str(lineage.predecessor_submission_id)
                if lineage.predecessor_submission_id is not None else None
            ),
            predecessor_submission_version=lineage.predecessor_submission_version,
            checker_remediation_manifest_id=(
                str(lineage.checker_remediation_manifest_id)
                if lineage.checker_remediation_manifest_id is not None else None
            ),
            revision_preparation_id=lineage.revision_preparation_id,
            revision_preparation_sha256=lineage.revision_preparation_sha256,
            locked_policy_context_hash=lineage.locked_policy_context_hash,
            guide_id=str(lineage.guide_id), guide_version=lineage.guide_version,
            source_snapshot_id=str(lineage.source_snapshot_id),
            source_snapshot_sha256=lineage.source_snapshot_sha256,
            effective_policy_id=str(lineage.effective_policy_id),
            effective_policy_sha256=lineage.effective_policy_sha256,
            pre_submit_policy_id=str(lineage.pre_submit_policy_id),
            pre_submit_policy_sha256=lineage.pre_submit_policy_sha256,
            effective_plan_sha256=lineage.effective_plan_sha256,
            selected_rules_sha256=lineage.rules_sha256,
            selected_post_submit_policy_sha256=lineage.post_submit_policy_sha256,
            selected_post_submit_policy_body=lineage.post_submit_policy_body,
            packet_sha256=lineage.packet_sha256,
            semantic_manifest_id=str(lineage.semantic_manifest_id),
            semantic_manifest_sha256=selected.semantic_manifest_sha256,
            semantic_manifest_body=lineage.semantic_manifest_body,
            archive_sha256=selected.archive_sha256,
            archive_byte_count=selected.archive_byte_count,
            status="ready", ready_at=now, consumed_at=None,
            consumed_by_submission_id=None, stale_at=None, stale_reason=None,
        )
        self._session.add(admission)
        await self._session.flush()
        return admission

    @staticmethod
    def _matches_verified_bytes(
        attempt,
        job,
        replica,
        content,
        receipt,
        *,
        project_id: str,
        task_id: str,
        actor_profile_id: str,
        archive_sha256: str,
        archive_byte_count: int,
    ) -> bool:
        return bool(
            replica is not None
            and content is not None
            and receipt is not None
            and receipt.verification_job_id == job.id
            and receipt.execution_generation == job.execution_generation
            and receipt.outcome == "verified"
            and receipt.observed_sha256 == attempt.sha256 == content.sha256 == archive_sha256
            and receipt.observed_byte_count
            == attempt.byte_count
            == content.byte_count
            == archive_byte_count
            and job.originating_put_attempt_id == attempt.id
            and job.replica_id == replica.id
            and attempt.replica_id == replica.id
            and replica.content_id == content.id
            and replica.verification_state == "verified"
            and replica.availability_state == "available"
            and replica.integrity_state == "valid"
            and attempt.project_id == project_id
            and attempt.task_id == task_id
            and attempt.producer_ref == actor_profile_id
            and attempt.media_type == "application/zip"
        )


    async def _write_receipt_ids(
        self, attempt: ArtifactPutAttempt
    ) -> tuple[str | None, str | None]:
        if attempt.receipt_id is not None:
            receipt = await self._session.scalar(
                select(ArtifactOperationReceipt).where(
                    ArtifactOperationReceipt.id == attempt.receipt_id,
                    ArtifactOperationReceipt.put_attempt_id == attempt.id,
                    ArtifactOperationReceipt.replica_id == attempt.replica_id,
                    ArtifactOperationReceipt.outcome == "stored_pending_verification",
                )
            )
            if receipt is None:
                raise SubmissionBundleAdmissionPublicationError("put receipt lineage is invalid")
            return receipt.id, None
        observation = await self._session.scalar(
            select(ArtifactPutObservationReceipt)
            .where(
                ArtifactPutObservationReceipt.put_attempt_id == attempt.id,
                ArtifactPutObservationReceipt.outcome == "observed_confirmed",
                ArtifactPutObservationReceipt.observed_sha256 == attempt.sha256,
                ArtifactPutObservationReceipt.observed_byte_count == attempt.byte_count,
            )
            .order_by(ArtifactPutObservationReceipt.execution_generation.desc())
            .limit(1)
        )
        if observation is None:
            raise SubmissionBundleAdmissionPublicationError(
                "put observation receipt lineage is invalid"
            )
        return None, observation.id


async def current_submission_bundle_admission_id(
    session: AsyncSession, *, put_attempt_id: UUID
) -> UUID | None:
    """Return bounded current state for hidden exact request replay."""
    value = await session.scalar(
        select(SubmissionBundleAdmission.id)
        .join(
            SubmissionBundleDurableIntent,
            SubmissionBundleDurableIntent.id == SubmissionBundleAdmission.durable_intent_id,
        )
        .where(
            SubmissionBundleDurableIntent.put_attempt_id == str(put_attempt_id),
            SubmissionBundleAdmission.status == "ready",
        )
    )
    return UUID(value) if value is not None else None


@dataclass(frozen=True, slots=True)
class SubmissionBundlePreparationRuntime:
    preparation: ArtifactPreparationService
    intake: TrustedSubmissionIntakeAdapter
    archive_limits: SubmissionArchiveLimits
    materialization: PreparedBundleMaterializationService
    durable_put: SubmissionBundleDurablePutService
    selected_coordinator: SelectedPreSubmitCoordinationPort | None = None
    selected_execution: SelectedPreSubmitExecutionService | None = None
    storage_scheme: str | None = None
    artifact_deadline_ms: int = 0


class PreparedSubmissionBundlePreparationCommand:
    """Keep every process-local capability within one hidden request."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        authority: SubmissionBundlePreparationAuthorization,
        task_contexts: TaskSubmissionContextPort,
        project_contexts: ProjectLockedPolicyContextPort,
        runtime_factory: Callable[
            [], AbstractAsyncContextManager[SubmissionBundlePreparationRuntime]
        ],
    ) -> None:
        self._session = session
        self._authority = authority
        self._task_contexts = task_contexts
        self._project_contexts = project_contexts
        self._runtime_factory = runtime_factory

    async def prepare(
        self, request: SubmissionBundlePreparationRequest
    ) -> SubmissionBundlePreparationResult:
        if type(request) is not SubmissionBundlePreparationRequest:
            raise TypeError("invalid submission bundle preparation request")
        try:
            await self._authority.preflight(request=request)
            validate_submission_packet_headers(
                request.summary,
                request.contributor_attestation,
            )
            if request.media_type.partition(";")[0].strip().lower() != "application/zip":
                raise SubmissionBundlePreparationRejected("submission_bundle_media_type_invalid")
            async with self._runtime_factory() as runtime, AsyncExitStack() as scratch_cleanup:
                if (
                    runtime.selected_coordinator is None
                    or runtime.selected_execution is None
                    or runtime.storage_scheme is None
                ):
                    raise RuntimeError("selected PRE runtime is unavailable")
                async with self._session.begin():
                    task_context, project_context = await self._lock_authorized_context(request)
                    predecessor = await self._load_predecessor(task_context)
                    predecessor_rules_sha256 = await self._load_predecessor_rules(task_context)
                    remediation_manifest_id = task_context.checker_remediation_manifest_id
                early_policy = LockedExternalCheckerPolicies.model_validate_json(
                    project_context.external_checker_policies.value
                ).pre_submit
                pending_intake = await scratch_cleanup.enter_async_context(prepared_trusted_intake(
                    runtime.intake, TrustedIntakePreparation(
                        phase="pre_submit", policy_sha256=early_policy.policy_sha256,
                        limits=runtime.archive_limits, deadline_ms=runtime.artifact_deadline_ms,
                    ),
                ))
                prepared, intake = await prepare_bytes_with_intake(pending_intake,
                    runtime.preparation.prepare(request.byte_source, media_type="application/zip"),
                )
                scratch_cleanup.push_async_callback(prepared.close)
                async with self._session.begin():
                    task_context, project_context = await self._lock_authorized_context(request)
                    if task_context.checker_remediation_manifest_id != remediation_manifest_id:
                        raise SubmissionBundlePreparationRejected(
                            "submission_bundle_preparation_context_changed"
                        )
                    policies = LockedExternalCheckerPolicies.model_validate_json(
                        project_context.external_checker_policies.value
                    )
                    if policies.pre_submit.policy_sha256 != early_policy.policy_sha256:
                        raise SubmissionBundlePreparationRejected("submission_bundle_preparation_context_changed")
                    materialization_handle = (
                        await runtime.materialization.prepare_selected_authorization(
                            task=task_context,
                            project=project_context,
                            prepared_artifact=prepared,
                            external_policy=policies.pre_submit,
                            idempotency_key=request.idempotency_key,
                        )
                    )
                    try:
                        inspection = await prepared.inspect(
                            TrustedArchiveInspector(intake, prepared.commitment), on_cancel=intake.abort,
                        )
                    except SubmissionArchiveRejectedError as exc:
                        raise SubmissionBundlePreparationRejected(exc.code.value) from exc
                    manifest = build_submission_manifest(inspection)
                    packet = SubmissionPacketView(
                        summary=request.summary,
                        contributor_attestation=request.contributor_attestation,
                    )
                    selected = bind_selected_pre_submit_admission(
                        task=task_context,
                        project=project_context,
                        commitment=prepared.commitment,
                        manifest=manifest,
                        predecessor=predecessor,
                        predecessor_rules_sha256=predecessor_rules_sha256,
                        predecessor_exists=(request.predecessor_submission_id is not None),
                        packet=packet,
                    )
                    attempt_id = new_record_id()
                    reservation = build_selected_pre_submit_reservation(
                        actor_profile_id=request.actor.actor_profile_id,
                        identity_link_id=request.actor.identity_link_id,
                        task=task_context,
                        project=project_context,
                        prepared_generation_id=prepared.generation_id,
                        attempt_id=attempt_id,
                        idempotency_key=request.idempotency_key,
                        attempt_request_digest=(
                            selected_pre_submit_attempt_request_digest(
                                actor_profile_id=request.actor.actor_profile_id,
                                identity_link_id=request.actor.identity_link_id,
                                task_id=request.task_id,
                                assignment_id=request.assignment_id,
                                predecessor_submission_id=(request.predecessor_submission_id),
                                idempotency_key=request.idempotency_key,
                                archive_sha256=prepared.commitment.sha256,
                                archive_byte_count=prepared.commitment.byte_count,
                                packet_sha256=packet.sha256,
                                revision_preparation_id=(
                                    task_context.revision_context.preparation_id
                                    if task_context.revision_context is not None else None
                                ),
                                revision_preparation_sha256=(
                                    task_context.revision_context.preparation_sha256
                                    if task_context.revision_context is not None else None
                                ),
                            )
                        ),
                        commitment=prepared.commitment,
                        manifest=manifest,
                        packet=packet,
                        selected=selected,
                        storage_scheme=runtime.storage_scheme,
                        execution_budget_ms=selected_pre_submit_execution_budget_ms(
                            selected.policy,
                            artifact_deadline_ms=runtime.artifact_deadline_ms,
                        ),
                    )
                    materialization_request = PreparedBundleMaterializationRequest(
                        prepared_authorization=materialization_handle,
                        task_id=request.task_id,
                        assignment_id=request.assignment_id,
                        submission_artifact_policy_id=project_context.effective_policy_id,
                        checker_policy_id=project_context.pre_submit_policy_id,
                        predecessor_submission_version=(
                            task_context.predecessor.version
                            if task_context.predecessor is not None
                            else None
                        ),
                        checker_remediation_manifest_id=remediation_manifest_id,
                        prepared_artifact=prepared,
                        inspection=inspection,
                        manifest=manifest,
                        change_gate=selected.change_gate,
                        packet=packet,
                        external_policy=selected.policy,
                        default_checker_input=selected.default_input,
                        selected_reservation=reservation,
                        intake=intake,
                    )
                    current = await runtime.selected_coordinator.read_current(reservation)
                    if current is None:
                        await runtime.materialization.authorize_inspected(materialization_request)
                        reserved_id = await runtime.selected_coordinator.reserve(reservation)
                        if reserved_id != reservation.attempt_id:
                            raise RuntimeError("selected PRE reservation identity changed")
                if current is not None:
                    if current.status == "running":
                        try:
                            recovered = await runtime.selected_execution.recover_expired(
                                run_id=current.run_id,
                                reservation=current.reservation,
                            )
                        except SelectedPreSubmitUnavailable:
                            pass
                        else:
                            current = SelectedPreSubmitCurrentFacts(
                                run_id=current.run_id,
                                reservation=current.reservation,
                                status="infrastructure_failed",
                                terminal=recovered.terminal,
                            )
                    return await self._selected_replay_result(current)
                completion = await runtime.selected_execution.execute(
                    reservation=reservation,
                    materialization=replace(
                        materialization_request,
                        prepared_authorization=None,
                    ),
                )
                terminal = completion.terminal
                if terminal.outcome == "infrastructure_failed":
                    raise SubmissionBundlePreparationInfrastructureUnavailable(
                        terminal.infrastructure_failure_code
                        or "pre_submission_checked_custody_unavailable"
                    )
                if terminal.execution is None:
                    raise SubmissionBundlePreparationInfrastructureUnavailable(
                        "pre_submission_checked_custody_unavailable"
                    )
                if not terminal.execution.eligible:
                    raise SubmissionBundlePreparationCheckFailed(terminal.execution)
                if completion.capability is None:
                    raise SubmissionBundlePreparationInfrastructureUnavailable(
                        "pre_submission_checked_custody_unavailable"
                    )
                async with self._authority.transaction():
                    await self._lock_authorized_context(request)
                    retained, _, durable = await runtime.durable_put.admit_in_transaction(
                        SubmissionBundleDurablePutRequest(
                            prepared_authorization=None,
                            prepared_artifact=prepared,
                            selected_completion=completion,
                        )
                    )
                result = await runtime.durable_put.publish_after_commit(
                    retained,
                    reservation.attempt_id,
                    durable,
                )
                return self._result(result, terminal.execution)
        except ArtifactPreparationDeadlineError as exc:
            # No terminal claim is made when intake cleanup was not confirmed.
            # The existing lease recovery owner resolves an already reserved run.
            raise SubmissionBundlePreparationInfrastructureUnavailable(
                "pre_submission_attempt_outcome_unresolved"
            ) from exc
        except ExternalServiceAdapterError as exc:
            raise SubmissionBundlePreparationInfrastructureUnavailable("implementation_unavailable") from exc
        except SelectedPreSubmitRequestConflict as exc:
            raise SubmissionBundlePreparationRejected(
                "submission_bundle_preparation_request_conflict"
            ) from exc
        except ArtifactAuthorityDeniedError as exc:
            raise SubmissionBundlePreparationUnavailable(
                "submission bundle preparation is unavailable"
            ) from exc
        finally:
            self._authority.close()

    async def _selected_replay_result(
        self, current: SelectedPreSubmitCurrentFacts
    ) -> SubmissionBundlePreparationResult:
        """Replay exact work facts or an already durable pass without execution."""
        terminal = current.terminal
        if current.status in {"queued", "running"} or terminal is None:
            raise SubmissionBundlePreparationInfrastructureUnavailable(
                "pre_submission_attempt_outcome_unresolved"
            )
        if terminal.outcome == "infrastructure_failed":
            raise SubmissionBundlePreparationInfrastructureUnavailable(
                terminal.infrastructure_failure_code or "pre_submission_checked_custody_unavailable"
            )
        execution = terminal.execution
        if execution is None:
            raise SubmissionBundlePreparationInfrastructureUnavailable(
                "pre_submission_checked_custody_unavailable"
            )
        if not execution.eligible:
            raise SubmissionBundlePreparationCheckFailed(execution)
        row = (
            await self._session.execute(
                select(
                    SubmissionBundleDurableIntent,
                    ArtifactPutAttempt,
                    SubmissionBundleAdmission,
                )
                .join(
                    ArtifactPutAttempt,
                    ArtifactPutAttempt.id == SubmissionBundleDurableIntent.put_attempt_id,
                )
                .outerjoin(
                    SubmissionBundleAdmission,
                    SubmissionBundleAdmission.durable_intent_id == SubmissionBundleDurableIntent.id,
                )
                .where(
                    SubmissionBundleDurableIntent.selected_pre_submit_run_id == str(current.run_id)
                )
            )
        ).one_or_none()
        if row is None:
            raise SubmissionBundlePreparationInfrastructureUnavailable(
                "pre_submission_checked_custody_unavailable"
            )
        _, attempt, admission = row
        status = attempt.status
        admission_id = None
        if admission is not None:
            if admission.status == "ready":
                status, admission_id = "ready", UUID(admission.id)
            elif admission.status == "stale":
                status = "stale"
            else:
                status = "conflict"
        return SubmissionBundlePreparationResult(
            put_attempt_id=UUID(attempt.id),
            admission_id=admission_id,
            submission_bundle_preparation_status=SubmissionBundlePreparationStatus(status),
            replayed=True,
            pre_submission_results=tuple(public_pre_submission_results(execution)),
        )

    async def _lock_authorized_context(
        self,
        request: SubmissionBundlePreparationRequest,
    ) -> tuple[TaskSubmissionContextFacts, ProjectLockedPolicyContextFacts]:
        """Lock TASK, actor identity, PROJECT, then the current submitter grant."""
        task, project = await self._lock_context(request)
        await self._authority.revalidate(
            request=request,
            project_id=task.locked_project_context.project_id,
        )
        try:
            if task.predecessor is not None:
                selected_revision = project.activation_receipt.command.revision
                require_revision_capacity(
                    task, project_id=project.project_id,
                    policy_id=selected_revision.policy_id,
                    policy_generation=selected_revision.generation,
                    policy_hash=selected_revision.policy_hash,
                    max_revision_rounds=RevisionPolicySemantics.model_validate_json(
                        project.revision_policy.value,
                    ).max_revision_rounds,
                )
        except TaskSubmissionContextUnavailable as exc:
            raise SubmissionBundlePreparationRejected(exc.code) from exc
        require_revision_preparation_acknowledgement(task, request)
        return task, project

    async def _lock_context(
        self,
        request: SubmissionBundlePreparationRequest,
    ) -> tuple[TaskSubmissionContextFacts, ProjectLockedPolicyContextFacts]:
        """Lock actor identity between the exact TASK and PROJECT context phases."""
        try:
            task_context = await self._task_contexts.lock_submission_context(
                TaskSubmissionContextRequest(
                    task_id=request.task_id,
                    assignment_id=request.assignment_id,
                    contributor_id=request.actor.actor_profile_id,
                    predecessor_submission_id=request.predecessor_submission_id,
                )
            )
            await self._authority.lock_actor(request=request)
            references = task_context.locked_project_context
            project_context = await self._project_contexts.lock_locked_policy_context(
                ProjectLockedPolicyContextRequest(
                    project_id=references.project_id,
                    guide_version=references.guide_version,
                    source_snapshot_id=references.source_snapshot_id,
                    source_snapshot_hash=references.source_snapshot_hash,
                    effective_policy_id=references.effective_policy_id,
                    effective_policy_hash=references.effective_policy_hash,
                    pre_submit_policy_id=references.pre_submit_policy_id,
                    pre_submit_policy_bundle_hash=references.pre_submit_policy_bundle_hash,
                )
            )
        except (TaskSubmissionContextUnavailable, ProjectLockedPolicyContextUnavailable) as exc:
            raise SubmissionBundlePreparationRejected(
                "submission_bundle_preparation_context_changed"
            ) from exc
        return task_context, project_context


    async def _load_predecessor(
        self,
        task_context: TaskSubmissionContextFacts,
    ) -> SubmissionCanonicalPredecessor | None:
        predecessor = task_context.predecessor
        if predecessor is None:
            return None
        admission = await self._session.scalar(
            select(SubmissionBundleAdmission).where(
                SubmissionBundleAdmission.consumed_by_submission_id
                == str(predecessor.submission_id),
                SubmissionBundleAdmission.status == "consumed",
            )
        )
        if admission is None:
            raise SubmissionBundlePreparationRejected(
                "submission_canonical_predecessor_unavailable"
            )
        return SubmissionCanonicalPredecessor(
            submission_id=predecessor.submission_id,
            submission_version=predecessor.version,
            archive_sha256=admission.archive_sha256,
            semantic_manifest_sha256=admission.semantic_manifest_sha256,
        )

    async def _load_predecessor_rules(
        self,
        task_context: TaskSubmissionContextFacts,
    ) -> str | None:
        """Require the predecessor's exact selected rules commitment."""
        predecessor = task_context.predecessor
        if predecessor is None:
            return None
        admission = await self._session.scalar(
            select(SubmissionBundleAdmission).where(
                SubmissionBundleAdmission.consumed_by_submission_id
                == str(predecessor.submission_id),
                SubmissionBundleAdmission.status == "consumed",
            )
        )
        if (
            admission is None
            or admission.selected_pre_submit_run_id is None
            or admission.pre_submit_evidence_set_id is not None
            or admission.selected_rules_sha256 is None
        ):
            raise SubmissionBundlePreparationRejected(
                "submission_canonical_predecessor_unavailable"
            )
        return admission.selected_rules_sha256

    @staticmethod
    def _result(
        result: SubmissionBundleDurablePutResult,
        execution: SelectedPreSubmitExecutionFacts,
    ) -> SubmissionBundlePreparationResult:
        return SubmissionBundlePreparationResult(
            put_attempt_id=result.put_attempt_id,
            admission_id=result.admission_id,
            submission_bundle_preparation_status=SubmissionBundlePreparationStatus(result.status),
            replayed=result.replayed,
            pre_submission_results=tuple(public_pre_submission_results(execution)),
        )
