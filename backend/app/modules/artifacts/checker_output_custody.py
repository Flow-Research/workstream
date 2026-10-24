"""Exact ART-owned output selection shared by storage recovery and binding."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.api.checker_output_authority import CheckerOutputStoredFacts
from app.modules.artifacts.models import (
    ArtifactContent,
    ArtifactPutAttempt,
    ArtifactReplica,
    ArtifactStorageNamespace,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
)
from app.modules.checkers.api.output_custody import (
    GeneratedOutputReservation,
    GeneratedOutputSelector,
    generated_output_subject,
    CheckerOutputUnavailable,
)


async def select_checker_output(
    session: AsyncSession,
    *,
    selector: GeneratedOutputSelector,
    reservation: GeneratedOutputReservation,
    namespace_fingerprint: str,
    put_attempt_id: UUID | None = None,
    verification_receipt_id: UUID | None = None,
    lock_verified: bool = False,
) -> CheckerOutputStoredFacts | None:
    """Match immutable request and verified ancestry; never read foreign owners."""
    slot = reservation.select(selector)
    owner = generated_output_subject(reservation)
    expected_digest = canonical_json_hash(owner.request_digest_facts)
    attempt = await session.scalar(
        select(ArtifactPutAttempt)
        .where(
            ArtifactPutAttempt.operation_identity == owner.operation_identity,
        )
        .execution_options(populate_existing=True)
    )
    if attempt is None:
        return None
    if (
        (
            attempt.producer_request_type,
            attempt.project_id,
            attempt.task_id,
            attempt.submission_id,
            attempt.submission_version,
            attempt.model_call_attempt_id,
            attempt.checker_trial_evidence_id,
            attempt.logical_role,
            attempt.checker_request_digest,
            attempt.media_type,
            attempt.namespace_fingerprint,
        )
        != (
            owner.producer_request_type,
            str(owner.project_id),
            str(owner.task_id) if owner.task_id else None,
            str(owner.submission_id) if owner.submission_id else None,
            owner.submission_version,
            str(owner.model_call_attempt_id) if owner.model_call_attempt_id else None,
            str(owner.checker_trial_evidence_id) if owner.checker_trial_evidence_id else None,
            slot.key,
            expected_digest,
            slot.media_type,
            namespace_fingerprint,
        )
        or attempt.byte_count > slot.maximum_bytes
        or attempt.checker_run_id is not None
        or attempt.sha256 != selector.content_sha256
        or (put_attempt_id is not None and attempt.id != str(put_attempt_id))
    ):
        raise CheckerOutputUnavailable("checker_output_identity_mismatch")
    facts = CheckerOutputStoredFacts(
        UUID(attempt.id),
        expected_digest,
        attempt.sha256,
        attempt.byte_count,
        attempt.media_type,
        attempt.status,
        None,
        None,
        None,
    )
    if attempt.status != "object_confirmed":
        return facts
    return await _verified_output_facts(
        session,
        attempt=attempt,
        facts=facts,
        namespace_fingerprint=namespace_fingerprint,
        verification_receipt_id=verification_receipt_id,
        lock_verified=lock_verified,
    )


async def _verified_output_facts(
    session: AsyncSession,
    *,
    attempt: ArtifactPutAttempt,
    facts: CheckerOutputStoredFacts,
    namespace_fingerprint: str,
    verification_receipt_id: UUID | None,
    lock_verified: bool,
) -> CheckerOutputStoredFacts:
    """Resolve and, for publication, lock the exact independent verification chain."""
    query = (
        select(
            ArtifactVerificationReceipt,
            ArtifactVerificationJob,
            ArtifactReplica,
            ArtifactContent,
            ArtifactStorageNamespace,
        )
        .select_from(ArtifactVerificationReceipt)
        .join(
            ArtifactVerificationJob,
            ArtifactVerificationJob.id == ArtifactVerificationReceipt.verification_job_id,
        )
        .join(ArtifactReplica, ArtifactReplica.id == ArtifactVerificationJob.replica_id)
        .join(ArtifactContent, ArtifactContent.id == ArtifactReplica.content_id)
        .join(
            ArtifactStorageNamespace,
            ArtifactStorageNamespace.id == ArtifactReplica.storage_namespace_id,
        )
        .where(
            ArtifactVerificationJob.originating_put_attempt_id == attempt.id,
            ArtifactVerificationReceipt.outcome == "verified",
        )
        .order_by(ArtifactVerificationReceipt.id)
        .execution_options(populate_existing=True)
    )
    if verification_receipt_id is not None:
        query = query.where(ArtifactVerificationReceipt.id == str(verification_receipt_id))
    row = (await session.execute(query.limit(1))).one_or_none()
    if row is None:
        return facts
    receipt, job, replica, content, namespace = row
    if lock_verified:
        # Match verifier completion's lock order; CHECKERS/authority are already held.
        for model, record_id in (
            (ArtifactVerificationJob, job.id),
            (ArtifactReplica, replica.id),
            (ArtifactPutAttempt, attempt.id),
            (ArtifactContent, content.id),
        ):
            await session.scalar(
                select(model)
                .where(model.id == record_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
    if not (
        attempt.status == "object_confirmed"
        and job.status == "verified"
        and receipt.execution_generation == job.execution_generation
        and job.replica_id == replica.id == attempt.replica_id
        and (replica.verification_state, replica.availability_state, replica.integrity_state)
        == ("verified", "available", "valid")
        and receipt.observed_sha256 == content.sha256 == attempt.sha256
        and receipt.observed_byte_count == content.byte_count == attempt.byte_count
        and content.media_type == attempt.media_type
        and replica.storage_namespace_id == attempt.storage_namespace_id
        and replica.namespace_fingerprint
        == namespace.namespace_fingerprint
        == namespace_fingerprint
        and replica.provider_object_ref == attempt.canonical_target
    ):
        raise CheckerOutputUnavailable("checker_output_verification_unavailable")
    return CheckerOutputStoredFacts(
        UUID(attempt.id),
        facts.checker_request_digest,
        attempt.sha256,
        attempt.byte_count,
        attempt.media_type,
        "verified",
        UUID(content.id),
        UUID(replica.id),
        UUID(receipt.id),
    )
