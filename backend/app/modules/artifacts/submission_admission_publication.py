"""Verified-only publication of immutable ready submission-bundle admissions."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
