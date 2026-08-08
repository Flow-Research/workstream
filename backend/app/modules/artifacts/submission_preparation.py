"""Hidden continuous contributor ZIP preparation orchestration."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.artifact_operations import (
    PreparedBundleMaterializationRequest,
    SubmissionBundlePreparationPort,
    SubmissionBundlePreparationRequest,
)
from app.modules.artifacts.models import (
    ArtifactPutAttempt,
    PreSubmitEvidenceSet,
    SubmissionBundleAdmission,
    SubmissionBundleDurableIntent,
)
from app.modules.artifacts.preparation import ArtifactPreparationService
from app.modules.artifacts.submission_admission import (
    SubmissionBundleDurablePutRequest,
    SubmissionBundleDurablePutResult,
    SubmissionBundleDurablePutService,
)
from app.modules.artifacts.submission_archive import SubmissionArchiveInspector
from app.modules.artifacts.submission_authorization import (
    SubmissionBundlePreparationAuthorization,
)
from app.modules.artifacts.submission_manifest import (
    SubmissionCanonicalPredecessor,
    build_submission_manifest,
    evaluate_submission_change,
)
from app.modules.artifacts.submission_materialization import (
    PreparedBundleMaterializationService,
    PreparedBundlePreSubmitEvidenceService,
)
from app.modules.checkers.catalogue import PreSubmissionCheckerCatalogue
from app.modules.checkers.pre_submit_execution import SubmissionPacketView
from app.modules.tasks.pre_submit_context import (
    compile_locked_pre_submit_plan,
    load_canonical_submission_version,
    load_locked_pre_submit_context,
)


class SubmissionBundlePreparationRejected(RuntimeError):
    """The complete effective pre-submit execution did not produce passing custody."""


@dataclass(frozen=True, slots=True)
class SubmissionBundlePreparationResult:
    put_attempt_id: UUID
    admission_id: UUID | None
    status: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class SubmissionBundlePreparationRuntime:
    preparation: ArtifactPreparationService
    inspector: SubmissionArchiveInspector
    catalogue: PreSubmissionCheckerCatalogue
    materialization: PreparedBundleMaterializationService
    evidence: PreparedBundlePreSubmitEvidenceService
    durable_put: SubmissionBundleDurablePutService


class SubmissionBundlePreparationCommand(SubmissionBundlePreparationPort, Protocol):
    async def prepare(
        self, request: SubmissionBundlePreparationRequest
    ) -> SubmissionBundlePreparationResult: ...


class PreparedSubmissionBundlePreparationCommand:
    """Keep every process-local capability within one hidden request."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        authority: SubmissionBundlePreparationAuthorization,
        runtime_factory: Callable[
            [], AbstractAsyncContextManager[SubmissionBundlePreparationRuntime]
        ],
    ) -> None:
        self._session = session
        self._authority = authority
        self._runtime_factory = runtime_factory

    async def prepare(
        self, request: SubmissionBundlePreparationRequest
    ) -> SubmissionBundlePreparationResult:
        if type(request) is not SubmissionBundlePreparationRequest:
            raise TypeError("invalid submission bundle preparation request")
        prepared = None
        try:
            await self._authority.preflight(
                authorization_context=request.authorization_context,
                task_id=request.task_id,
                assignment_id=request.assignment_id,
                predecessor_submission_id=request.predecessor_submission_id,
                idempotency_key=request.idempotency_key,
            )
            if request.media_type.partition(";")[0].strip().lower() != "application/zip":
                raise SubmissionBundlePreparationRejected("submission_bundle_media_type_invalid")
            async with self._runtime_factory() as runtime:
                async with self._session.begin():
                    locked = await load_locked_pre_submit_context(
                        self._session,
                        actor_profile_id=request.authorization_context.actor_profile_id,
                        identity_link_id=request.authorization_context.identity_link_id,
                        task_id=request.task_id,
                        assignment_id=request.assignment_id,
                        predecessor_submission_id=request.predecessor_submission_id,
                        include_actor_identity_locks=False,
                    )
                    plan = compile_locked_pre_submit_plan(locked, runtime.catalogue)
                    predecessor = await self._load_predecessor(request.predecessor_submission_id)
                prepared = await runtime.preparation.prepare(
                    request.byte_source,
                    media_type="application/zip",
                )
                async with self._session.begin():
                    materialization_handle = await runtime.materialization.prepare_authorization(
                        task_id=request.task_id,
                        assignment_id=request.assignment_id,
                        submission_artifact_policy_id=locked.effective_policy_id,
                        checker_policy_id=locked.pre_submit_policy_id,
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
                        submission_artifact_policy_id=locked.effective_policy_id,
                        checker_policy_id=locked.pre_submit_policy_id,
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
                    actor_profile_id=request.authorization_context.actor_profile_id,
                    identity_link_id=request.authorization_context.identity_link_id,
                    predecessor_submission_id=request.predecessor_submission_id,
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
                    final_handle = await self._authority.prepare_final(
                        authorization_context=request.authorization_context,
                        task_id=request.task_id,
                        assignment_id=request.assignment_id,
                        predecessor_submission_id=request.predecessor_submission_id,
                        idempotency_key=request.idempotency_key,
                    )
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
        self, submission_id: UUID | None
    ) -> SubmissionCanonicalPredecessor | None:
        if submission_id is None:
            return None
        admission = await self._session.scalar(
            select(SubmissionBundleAdmission).where(
                SubmissionBundleAdmission.consumed_by_submission_id == str(submission_id),
                SubmissionBundleAdmission.status == "consumed",
            )
        )
        version = await load_canonical_submission_version(
            self._session, submission_id=submission_id
        )
        if admission is None or version is None:
            raise SubmissionBundlePreparationRejected(
                "submission_canonical_predecessor_unavailable"
            )
        return SubmissionCanonicalPredecessor(
            submission_id=submission_id,
            submission_version=version,
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
