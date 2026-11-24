"""Publish retained verified preparation evidence without a new preparation writer."""

from __future__ import annotations

from uuid import UUID
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.api import (
    SubmissionBundlePreparationRejected,
    SubmissionBundlePreparationRequest,
)
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
from app.modules.checkers.api.historical_selected_pre_submit import (
    HistoricalSelectedPreSubmitReservation, HistoricalSelectedPreSubmitTerminal,
)
from app.modules.tasks.api.submission_context import require_revision_acknowledgement
from app.modules.tasks.api import (
    TaskRetainedSubmissionParentsRequest,
    TaskSubmissionContextFacts,
    TaskSubmissionContextPort,
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
    try:
        require_revision_acknowledgement(task, request.revision_preparation_id, request.revision_preparation_sha256)
    except TaskSubmissionContextUnavailable as exc:
        raise SubmissionBundlePreparationRejected(exc.code) from exc


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
            selected = HistoricalSelectedPreSubmitReservation.from_canonical_body(row.selected_request_json)
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
            selected = HistoricalSelectedPreSubmitReservation.from_canonical_body(intent.selected_request_json)
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
        try:
            retained_terminal = HistoricalSelectedPreSubmitTerminal.from_canonical_body(terminal)
        except (TypeError, ValueError) as exc:
            raise SubmissionBundleAdmissionPublicationError(
                "selected PRE terminal snapshot is invalid"
            ) from exc
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
            or retained_terminal.lease.reservation != selected
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
