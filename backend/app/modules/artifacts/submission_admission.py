"""Hidden evidence-bound durable put handoff for one checked submission ZIP."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
import json
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.api import (
    SubmissionBundlePreparationRejected,
    SubmissionBundlePreparationRequest,
    SubmissionBundlePreparationResult,
    SubmissionBundlePreparationUnavailable,
)
from app.modules.artifacts.models import (
    ArtifactContent,
    ArtifactOperationReceipt,
    ArtifactPutAttempt,
    ArtifactPutObservationReceipt,
    ArtifactReplica,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
    PreSubmitEvidenceSet,
    SubmissionBundleAdmission,
    SubmissionBundleDurableIntent,
)
from app.modules.artifacts.pre_submit_evidence import (
    PreSubmitEvidenceConflict,
    PreSubmitPassCapability,
)
from app.modules.artifacts.preparation import ArtifactPreparationService
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
from app.modules.artifacts.submission_archive import SubmissionArchiveInspector
from app.modules.artifacts.submission_authorization import (
    SubmissionBundlePreparationAuthorization,
)
from app.modules.artifacts.submission_custody import SubmissionBundlePreparedCustody
from app.modules.artifacts.submission_manifest import (
    SubmissionCanonicalPredecessor,
    build_submission_manifest,
    evaluate_submission_change,
)
from app.modules.artifacts.submission_materialization import (
    PreparedBundleMaterializationRequest,
    PreparedBundleMaterializationService,
    PreparedBundlePreSubmitEvidenceService,
)
from app.modules.checkers.api import (
    EffectivePreSubmissionExecutionPlan,
    EffectivePreSubmissionPlanLineage,
    EffectivePreSubmissionPlanningPort,
    SubmissionPacketView,
)
from app.modules.projects.api import (
    ProjectLockedPolicyContextFacts,
    ProjectLockedPolicyContextPort,
    ProjectLockedPolicyContextRequest,
    ProjectLockedPolicyContextUnavailable,
)
from app.modules.tasks.api import (
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


@dataclass(frozen=True, slots=True)
class SubmissionBundleDurablePutRequest:
    """Exact live custody and opaque authority for one final durable handoff."""

    prepared_authorization: object
    prepared_artifact: PreparedArtifact
    pass_capability: PreSubmitPassCapability
    replay_durable_intent_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SubmissionBundleDurablePutResult:
    """Bounded durable operation result without provider coordinates."""

    put_attempt_id: UUID
    pre_submit_evidence_set_id: UUID
    operation_identity: str
    status: str
    replayed: bool
    admission_id: UUID | None


class SubmissionBundleDurablePutService:
    """Commit final authority and intent before invoking the generic provider path."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        admission: ArtifactAdmissionService,
        storage: ArtifactStorageOrchestrator,
        authorization: SubmissionBundlePreparedAuthorization,
    ) -> None:
        self._session = session
        self._admission = admission
        self._storage = storage
        self._authorization = authorization

    async def admit_in_transaction(
        self,
        request: SubmissionBundleDurablePutRequest,
    ) -> tuple[PreparedArtifact, UUID, ArtifactAdmissionResult]:
        """Consume live custody and persist the complete intent in the caller transaction."""
        if type(request) is not SubmissionBundleDurablePutRequest:
            raise TypeError("invalid submission bundle durable put request")
        transaction = self._session.sync_session.get_transaction()
        prepared = request.prepared_artifact
        if (
            transaction is None
            or not transaction.is_active
            or self._session.in_nested_transaction()
            or type(prepared) is not PreparedArtifact
            or type(request.pass_capability) is not PreSubmitPassCapability
        ):
            if type(prepared) is PreparedArtifact:
                await prepared.close()
            raise RuntimeError("submission bundle durable transaction is unavailable")
        try:
            evidence_set_id = request.pass_capability.evidence_set_id
            custody = SubmissionBundlePreparedCustody._from_live_preparation(
                prepared=prepared,
                capability=request.pass_capability,
            )
            admission = await self._admission.admit(
                SubmissionBundleArtifactAdmissionRequest(
                    pre_submit_evidence_set_id=evidence_set_id,
                    custody=custody,
                    replay_durable_intent_id=request.replay_durable_intent_id,
                ),
                submission_prepared_authorization=self._authorization,
                prepared_authorization=request.prepared_authorization,
                existing_transaction=True,
            )
            return prepared, evidence_set_id, admission
        except BaseException:
            await prepared.close()
            raise

    async def publish_after_commit(
        self,
        prepared: PreparedArtifact,
        evidence_set_id: UUID,
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
                    pre_submit_evidence_set_id=evidence_set_id,
                    operation_identity=admission.operation_identity,
                    status="ready",
                    replayed=True,
                    admission_id=admission_id,
                )
            if admission.replayed and admission.status == "object_confirmed":
                return SubmissionBundleDurablePutResult(
                    put_attempt_id=admission.attempt_id,
                    pre_submit_evidence_set_id=evidence_set_id,
                    operation_identity=admission.operation_identity,
                    status="object_confirmed",
                    replayed=True,
                    admission_id=None,
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
                pre_submit_evidence_set_id=evidence_set_id,
                operation_identity=admission.operation_identity,
                status=status,
                replayed=admission.replayed,
                admission_id=admission_id,
            )
        finally:
            await prepared.close()


class SubmissionBundleAdmissionPublicationError(RuntimeError):
    """Durable verification lineage cannot publish a trusted ready admission."""


class SubmissionBundleAdmissionPublisher:
    """Project verified submission bytes into one idempotent ready admission."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def publish_verified(
        self, *, verification_job_id: str, verification_receipt_id: str
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
        existing = await self._session.scalar(
            select(SubmissionBundleAdmission)
            .where(SubmissionBundleAdmission.durable_intent_id == intent.id)
            .with_for_update()
        )
        if existing is not None:
            return existing
        evidence = await self._session.scalar(
            select(PreSubmitEvidenceSet)
            .where(PreSubmitEvidenceSet.id == intent.pre_submit_evidence_set_id)
            .with_for_update(key_share=True)
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
        if not self._matches_verified_lineage(evidence, attempt, job, replica, content, receipt):
            raise SubmissionBundleAdmissionPublicationError(
                "verified submission bundle lineage does not match"
            )
        operation_receipt_id, observation_receipt_id = await self._write_receipt_ids(attempt)
        assert evidence is not None and replica is not None and content is not None
        assert receipt is not None
        now = await self._session.scalar(select(func.now()))
        admission = SubmissionBundleAdmission(
            id=str(uuid4()),
            durable_intent_id=intent.id,
            pre_submit_evidence_set_id=evidence.id,
            put_attempt_id=attempt.id,
            artifact_content_id=content.id,
            verified_replica_id=replica.id,
            verification_receipt_id=receipt.id,
            put_operation_receipt_id=operation_receipt_id,
            put_observation_receipt_id=observation_receipt_id,
            actor_profile_id=evidence.actor_profile_id,
            identity_link_id=evidence.identity_link_id,
            project_id=evidence.project_id,
            task_id=evidence.task_id,
            assignment_id=evidence.assignment_id,
            predecessor_submission_id=evidence.predecessor_submission_id,
            predecessor_submission_version=evidence.predecessor_submission_version,
            locked_policy_context_hash=evidence.locked_policy_context_hash,
            semantic_manifest_id=evidence.semantic_manifest_id,
            semantic_manifest_sha256=evidence.semantic_manifest_sha256,
            archive_sha256=evidence.archive_sha256,
            archive_byte_count=evidence.archive_byte_count,
            status="ready",
            ready_at=now,
            consumed_at=None,
            consumed_by_submission_id=None,
            stale_at=None,
            stale_reason=None,
        )
        self._session.add(admission)
        await self._session.flush()
        return admission

    @staticmethod
    def _matches_verified_lineage(evidence, attempt, job, replica, content, receipt) -> bool:
        return bool(
            evidence is not None
            and evidence.terminal_status == "passed"
            and evidence.eligible
            and replica is not None
            and content is not None
            and receipt is not None
            and receipt.verification_job_id == job.id
            and receipt.execution_generation == job.execution_generation
            and receipt.outcome == "verified"
            and receipt.observed_sha256
            == attempt.sha256
            == content.sha256
            == evidence.archive_sha256
            and receipt.observed_byte_count
            == attempt.byte_count
            == content.byte_count
            == evidence.archive_byte_count
            and job.originating_put_attempt_id == attempt.id
            and job.replica_id == replica.id
            and attempt.replica_id == replica.id
            and replica.content_id == content.id
            and replica.verification_state == "verified"
            and replica.availability_state == "available"
            and replica.integrity_state == "valid"
            and attempt.project_id == evidence.project_id
            and attempt.task_id == evidence.task_id
            and attempt.producer_ref == evidence.actor_profile_id
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
        .where(SubmissionBundleDurableIntent.put_attempt_id == str(put_attempt_id))
    )
    return UUID(value) if value is not None else None


@dataclass(frozen=True, slots=True)
class SubmissionBundlePreparationRuntime:
    preparation: ArtifactPreparationService
    inspector: SubmissionArchiveInspector
    catalogue: EffectivePreSubmissionPlanningPort
    materialization: PreparedBundleMaterializationService
    evidence: PreparedBundlePreSubmitEvidenceService
    durable_put: SubmissionBundleDurablePutService


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
        prepared = None
        try:
            await self._authority.preflight(request=request)
            validate_submission_packet_headers(
                request.summary,
                request.contributor_attestation,
            )
            if request.media_type.partition(";")[0].strip().lower() != "application/zip":
                raise SubmissionBundlePreparationRejected("submission_bundle_media_type_invalid")
            async with self._runtime_factory() as runtime:
                async with self._session.begin():
                    task_context, project_context = await self._lock_context(request)
                    plan = self._compile_plan(
                        task_context,
                        project_context,
                        runtime.catalogue,
                    )
                    predecessor = await self._load_predecessor(task_context)
                prepared = await runtime.preparation.prepare(
                    request.byte_source,
                    media_type="application/zip",
                )
                async with self._session.begin():
                    materialization_handle = await runtime.materialization.prepare_authorization(
                        task_id=request.task_id,
                        assignment_id=request.assignment_id,
                        submission_artifact_policy_id=project_context.effective_policy_id,
                        checker_policy_id=project_context.pre_submit_policy_id,
                        prepared_artifact=prepared,
                        effective_plan=plan,
                        idempotency_key=request.idempotency_key,
                    )
                    inspection = await prepared.inspect(runtime.inspector)
                    manifest = build_submission_manifest(inspection)
                    change_gate = evaluate_submission_change(
                        commitment=prepared.commitment,
                        manifest=manifest,
                        predecessor=predecessor,
                        predecessor_exists=request.predecessor_submission_id is not None,
                        current_predecessor=predecessor,
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
                        prepared_artifact=prepared,
                        effective_plan=plan,
                        inspection=inspection,
                        manifest=manifest,
                        change_gate=change_gate,
                        packet=SubmissionPacketView(
                            summary=request.summary,
                            contributor_attestation=request.contributor_attestation,
                        ),
                    )
                    execution = await runtime.evidence.materialize(materialization_request)
                evidence = await runtime.evidence.persist(
                    materialization_request,
                    execution=execution,
                    preparation_request=request,
                )
                if evidence.pass_capability is None:
                    replay = await self._existing_durable_result(evidence.evidence.evidence_set_id)
                    if replay is None:
                        raise SubmissionBundlePreparationRejected(
                            "pre_submission_checked_custody_unavailable"
                        )
                    await prepared.close()
                    prepared = None
                    return replay
                replay_intent_id = await self._matching_replay_intent(
                    evidence.evidence.evidence_set_id
                )
                async with self._authority.transaction():
                    final_handle = await self._authority.prepare_final(request=request)
                    retained, _, durable = await runtime.durable_put.admit_in_transaction(
                        SubmissionBundleDurablePutRequest(
                            prepared_authorization=final_handle,
                            prepared_artifact=prepared,
                            pass_capability=evidence.pass_capability,
                            replay_durable_intent_id=replay_intent_id,
                        )
                    )
                prepared = None
                result = await runtime.durable_put.publish_after_commit(
                    retained,
                    evidence.evidence.evidence_set_id,
                    durable,
                )
                return self._result(result)
        except PreSubmitEvidenceConflict as exc:
            raise SubmissionBundlePreparationRejected(
                self._evidence_conflict_code(exc)
            ) from exc
        except ArtifactAuthorityDeniedError as exc:
            raise SubmissionBundlePreparationUnavailable(
                "submission bundle preparation is unavailable"
            ) from exc
        finally:
            if prepared is not None:
                await prepared.close()
            self._authority.close()

    async def _matching_replay_intent(self, evidence_id: UUID) -> UUID | None:
        """Find an older exact lineage without trusting client replay selectors."""
        async with self._session.begin():
            current = await self._session.get(PreSubmitEvidenceSet, str(evidence_id))
            if current is None:
                raise SubmissionBundlePreparationRejected(
                    "pre_submission_checked_custody_unavailable"
                )
            fields = (
                "actor_profile_id",
                "identity_link_id",
                "project_id",
                "task_id",
                "assignment_id",
                "predecessor_submission_id",
                "predecessor_submission_version",
                "archive_sha256",
                "archive_byte_count",
                "semantic_manifest_sha256",
                "guide_id",
                "guide_version",
                "source_snapshot_id",
                "source_snapshot_sha256",
                "locked_guide_sha256",
                "effective_policy_id",
                "locked_artifact_policy_sha256",
                "pre_submit_policy_id",
                "locked_checker_policy_sha256",
                "effective_plan_sha256",
                "catalogue_id",
                "catalogue_version",
                "catalogue_manifest_sha256",
                "storage_scheme",
                "terminal_status",
                "eligible",
                "result_count",
                "result_manifest_sha256",
            )
            statement = (
                select(SubmissionBundleDurableIntent.id)
                .join(
                    PreSubmitEvidenceSet,
                    PreSubmitEvidenceSet.id
                    == SubmissionBundleDurableIntent.pre_submit_evidence_set_id,
                )
                .join(
                    ArtifactPutAttempt,
                    ArtifactPutAttempt.id == SubmissionBundleDurableIntent.put_attempt_id,
                )
                .where(
                    PreSubmitEvidenceSet.id != current.id,
                    ArtifactPutAttempt.status.in_(
                        (
                            "prepared",
                            "acknowledgement_unknown",
                            "absent_replay_required",
                            "object_confirmed",
                        )
                    ),
                    *(
                        getattr(PreSubmitEvidenceSet, field) == getattr(current, field)
                        for field in fields
                    ),
                )
                .order_by(SubmissionBundleDurableIntent.created_at)
                .limit(1)
            )
            value = await self._session.scalar(statement)
            return UUID(value) if value is not None else None

    @staticmethod
    def _evidence_conflict_code(exc: PreSubmitEvidenceConflict) -> str:
        """Map ART-private evidence failures to the bounded public vocabulary."""
        if str(exc) == "pre_submit_locked_context_changed":
            return "submission_bundle_preparation_context_changed"
        return "pre_submission_checked_custody_unavailable"

    async def _lock_context(
        self,
        request: SubmissionBundlePreparationRequest,
    ) -> tuple[TaskSubmissionContextFacts, ProjectLockedPolicyContextFacts]:
        """Lock exact TASK then PROJECT facts through their public ports."""
        try:
            task_context = await self._task_contexts.lock_submission_context(
                TaskSubmissionContextRequest(
                    task_id=request.task_id,
                    assignment_id=request.assignment_id,
                    contributor_id=request.actor.actor_profile_id,
                    predecessor_submission_id=request.predecessor_submission_id,
                )
            )
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

    @staticmethod
    def _compile_plan(
        task_context: TaskSubmissionContextFacts,
        project_context: ProjectLockedPolicyContextFacts,
        planner: EffectivePreSubmissionPlanningPort,
    ) -> EffectivePreSubmissionExecutionPlan:
        """Compile the sole CHECKER plan from exact public PROJECT facts."""
        guide_version = project_context.guide_version.removeprefix("v")
        try:
            numeric_guide_version = int(guide_version)
            effective_policy = json.loads(project_context.effective_policy.value)
            compiled_bundle = json.loads(
                project_context.compiled_pre_submit_bundle.value
            )
        except (TypeError, ValueError) as exc:
            raise SubmissionBundlePreparationRejected(
                "submission_bundle_preparation_context_changed"
            ) from exc
        if (
            project_context.project_id
            != task_context.locked_project_context.project_id
            or not isinstance(effective_policy, dict)
            or not isinstance(compiled_bundle, dict)
        ):
            raise SubmissionBundlePreparationRejected(
                "submission_bundle_preparation_context_changed"
            )
        return planner.compile_effective_plan(
            lineage=EffectivePreSubmissionPlanLineage(
                project_id=project_context.project_id,
                guide_id=project_context.guide_id,
                guide_version=numeric_guide_version,
                source_snapshot_id=project_context.source_snapshot_id,
                source_snapshot_hash=project_context.source_snapshot_hash,
                effective_policy_id=project_context.effective_policy_id,
                effective_policy_hash=project_context.effective_policy_hash,
                pre_submit_policy_id=project_context.pre_submit_policy_id,
                pre_submit_policy_bundle_hash=(
                    project_context.pre_submit_policy_bundle_hash
                ),
            ),
            effective_policy=effective_policy,
            compiled_bundle=compiled_bundle,
        )

    async def _existing_durable_result(
        self, evidence_id: UUID
    ) -> SubmissionBundlePreparationResult | None:
        async with self._session.begin():
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
                        SubmissionBundleAdmission.durable_intent_id
                        == SubmissionBundleDurableIntent.id,
                    )
                    .where(
                        SubmissionBundleDurableIntent.pre_submit_evidence_set_id == str(evidence_id)
                    )
                )
            ).one_or_none()
            if row is None:
                return None
            _, attempt, admission = row
            return SubmissionBundlePreparationResult(
                put_attempt_id=UUID(attempt.id),
                admission_id=UUID(admission.id) if admission is not None else None,
                status="ready" if admission is not None else attempt.status,
                replayed=True,
            )

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

    @staticmethod
    def _result(result: SubmissionBundleDurablePutResult) -> SubmissionBundlePreparationResult:
        return SubmissionBundlePreparationResult(
            put_attempt_id=result.put_attempt_id,
            admission_id=result.admission_id,
            status=result.status,
            replayed=result.replayed,
        )
