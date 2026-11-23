"""Authorized submission-source cleanup custody; provider I/O stays outside this owner.

The composition root must supply current authority and act only on a committed claim.
This owner retains uncertain targets and releases charges only with both exact
object absence and settled upload-part obligations supplied by that coordinator.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select, text

from app.modules.artifacts.api.submission_intake import (
    SealedSubmissionSource, SubmissionSourceUpload, SubmissionSourceLocation, SubmissionSourceCompletion,
)
from app.modules.artifacts.api.submission_cleanup import (
    SubmissionSourceCleanupAuthorityFacts, UnsealedSubmissionSource, UnsealedSourceCleanupInput, cleanup_target_sha256,
)
from app.modules.artifacts.intake.capacity import SubmissionSourceCapacity
from app.modules.artifacts.intake.models import (
    SubmissionIntakeOperation, SubmissionSourceCharge, SubmissionSourceCleanupClaim, SubmissionSourceUploadReceipt,
)
from app.modules.artifacts.models import ArtifactStorageNamespace, ArtifactReplica, SubmissionBundleAdmission
from app.modules.artifacts.intake.repository import IntakeCustodyConflict, SubmissionIntakeRepository

# Match the existing bounded durable finalization delivery lease, not a default.
MAXIMUM_CLEANUP_LEASE = timedelta(seconds=300)


@dataclass(frozen=True, slots=True)
class SourceCleanupClaim:
    """Exact durable deletion target; a copied value grants no deletion authority."""

    claim_id: UUID
    generation: int
    source: SealedSubmissionSource | UnsealedSubmissionSource
    lease_expires_at: datetime
    confirmed: bool
    observed_source: SealedSubmissionSource | None = None


def _claim_value(row: SubmissionSourceCleanupClaim) -> SourceCleanupClaim:
    """Recover typed source facts from persisted canonical JSON."""
    import json
    return SourceCleanupClaim(
        UUID(row.claim_id), row.generation,
        (UnsealedSubmissionSource if row.source.get("kind") == "unsealed" else SealedSubmissionSource)
        .model_validate_json(json.dumps(row.source)),
        row.lease_expires_at, row.confirmed_at is not None,
        SealedSubmissionSource.model_validate_json(json.dumps(row.observed_source)) if row.observed_source is not None else None,
    )


class SubmissionSourceCleanupOwner:
    """Flush-only ownership: caller supplies current authority and root commits."""

    def __init__(self, session, tasks, authorization):
        self._session = session
        self._authorization = authorization
        self._intake = SubmissionIntakeRepository(session, tasks)

    async def _require_namespace(self, namespace):
        persisted = await self._session.get(ArtifactStorageNamespace, "primary")
        if persisted is None or any(getattr(persisted, key) != value for key, value in asdict(namespace).items()):
            raise IntakeCustodyConflict("source_cleanup_namespace_unavailable")

    async def expired_foreground(self, namespace, *, limit: int) -> tuple[UUID, ...]:
        """Discover expired pre-handoff owners; discovery cannot change custody."""
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("source cleanup candidate bound is invalid")
        await self._authorization.authorize()
        await self._authorization.revalidate()
        await self._require_namespace(namespace)
        operation = SubmissionIntakeOperation
        now = await self._session.scalar(select(func.clock_timestamp()))
        identifiers = await self._session.scalars(select(operation.id).where(
            operation.namespace_id == "primary",
            operation.namespace_fingerprint == namespace.namespace_fingerprint,
            operation.state.in_(("receiving", "pre_checking")),
            operation.lease_expires_at <= now,
        ).order_by(operation.lease_expires_at, operation.id).limit(limit))
        return tuple(UUID(identifier) for identifier in identifiers)

    async def abandon_expired(self, operation_id: UUID, namespace) -> bool:
        """Fence a dead foreground owner without deleting bytes or releasing charges."""
        await self._authorization.authorize()
        operation = await self._intake._lock(operation_id)
        await self._authorization.revalidate()
        await self._require_namespace(namespace)
        if (operation.namespace_id != "primary"
                or operation.namespace_fingerprint != namespace.namespace_fingerprint):
            raise IntakeCustodyConflict("source_cleanup_namespace_unavailable")
        return await self._intake.abandon_expired(operation_id)

    async def candidates(self, namespace, *, limit: int) -> tuple[UUID, ...]:
        """Discover a bounded page; every result still requires an exact claim."""
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("source cleanup candidate bound is invalid")
        await self._authorization.authorize()
        await self._authorization.revalidate()
        await self._require_namespace(namespace)
        operation, claim, charge = SubmissionIntakeOperation, SubmissionSourceCleanupClaim, SubmissionSourceCharge
        now = await self._session.scalar(select(func.clock_timestamp()))
        retained = select(ArtifactReplica.id).where(or_(
            ArtifactReplica.source_operation_id == operation.id,
            (ArtifactReplica.storage_namespace_id == operation.namespace_id)
            & (ArtifactReplica.namespace_fingerprint == operation.namespace_fingerprint)
            & (ArtifactReplica.provider_object_ref == operation.object_ref),
        )).exists()
        admitted = select(SubmissionBundleAdmission.id).where(
            SubmissionBundleAdmission.source_operation_id == operation.id).exists()
        identifiers = await self._session.scalars(select(operation.id)
            .join(charge, charge.operation_id == operation.id)
            .outerjoin(claim, claim.operation_id == operation.id)
            .where(operation.namespace_id == "primary",
                   operation.namespace_fingerprint == namespace.namespace_fingerprint,
                   operation.state.in_(("rejected", "failed", "abandoned", "cancelled")),
                   operation.accepted_at.is_(None),
                   func.greatest(operation.terminal_at, operation.sealed_at, claim.observed_at) <= now - timedelta(hours=2),
                   charge.state.in_(("reserved", "sealed")),
                   claim.confirmed_at.is_(None),
                   or_(claim.operation_id.is_(None), claim.lease_expires_at <= now),
                   ~retained, ~admitted)
            .order_by(func.coalesce(claim.claimed_at, operation.terminal_at), operation.id).limit(limit))
        return tuple(UUID(identifier) for identifier in identifiers)

    async def _locked(self, operation_id):
        await self._authorization.authorize()
        operation = await self._intake._lock(operation_id)
        await self._authorization.revalidate()
        row = await self._session.scalar(select(SubmissionSourceCleanupClaim).where(
            SubmissionSourceCleanupClaim.operation_id == operation.id,
        ).with_for_update().execution_options(populate_existing=True))
        now = await self._session.scalar(select(func.clock_timestamp()))
        if row is not None and row.observed_at is not None and row.observed_at > now - timedelta(hours=2):
            raise IntakeCustodyConflict("source_cleanup_recent_completion")
        await self._session.execute(text(
            "SELECT public.require_submission_source_cleanup(o) "
            "FROM public.submission_intake_operations o WHERE id=:id"
        ), {"id": operation.id})
        return operation, row

    async def _target(self, operation):
        if operation.sealed_at is not None:
            return self._intake._sealed_source(operation)
        receipt = await self._session.get(SubmissionSourceUploadReceipt, operation.id)
        return UnsealedSubmissionSource(
            location=SubmissionSourceLocation(operation_id=UUID(operation.id), namespace_id=operation.namespace_id,
                namespace_fingerprint=operation.namespace_fingerprint, provider_profile=operation.provider_profile),
            upload_fence=receipt.upload_fence if receipt is not None else None,
            provider_upload_id=receipt.provider_upload_id if receipt is not None else None,
            raw_sha256=operation.raw_sha256, raw_byte_count=operation.raw_byte_count,
        )

    async def _decision(self, operation, claim_id, generation, phase):
        source = await self._target(operation)
        row = await self._session.get(SubmissionSourceCleanupClaim, operation.id)
        observed = _claim_value(row).observed_source if row is not None else None
        facts = SubmissionSourceCleanupAuthorityFacts(
            operation_id=UUID(operation.id), project_id=UUID(operation.project_id),
            task_id=UUID(operation.task_id), source_sha256=cleanup_target_sha256(source, observed),
            claim_id=claim_id, claim_generation=generation, phase=phase,
        )
        handle = await self._authorization.prepare(facts=facts, idempotency_key=facts.claim_id)
        decision = await self._authorization.consume(prepared_authorization=handle, facts=facts)
        if type(decision) is not UUID:
            raise IntakeCustodyConflict("source_cleanup_authority_unavailable")
        return str(decision)

    async def _require_claim_authority(self, operation_id):
        valid = await self._session.scalar(text(
            "SELECT public.source_cleanup_authority_valid(c,'claim') "
            "FROM public.submission_source_cleanup_claims c WHERE operation_id=:id"
        ), {"id": operation_id})
        if valid is not True:
            raise IntakeCustodyConflict("source_cleanup_authority_unavailable")

    async def claim(self, operation_id: UUID, claim_id: UUID, *, lease_duration: timedelta) -> SourceCleanupClaim:
        """Claim only a stable eligible source; never resume foreground work."""
        if (type(claim_id) is not UUID or claim_id.version != 7
                or type(lease_duration) is not timedelta
                or not timedelta(0) < lease_duration <= MAXIMUM_CLEANUP_LEASE):
            raise ValueError("source cleanup lease is invalid")
        operation, row = await self._locked(operation_id)
        now = await self._session.scalar(select(func.clock_timestamp()))
        if row is not None:
            if row.confirmed_at is not None:
                return _claim_value(row)
            if row.claim_id == str(claim_id):
                if row.lease_expires_at <= now:
                    raise IntakeCustodyConflict("source_cleanup_stale")
                await self._require_claim_authority(operation.id)
                return _claim_value(row)
            if row.lease_expires_at > now:
                raise IntakeCustodyConflict("source_cleanup_busy")
        generation = row.generation + 1 if row is not None else 1
        decision = await self._decision(operation, claim_id, generation, "claim")
        if row is not None:
            row.claim_id, row.generation = str(claim_id), generation
            row.claimed_at, row.lease_expires_at = now, now + lease_duration
        else:
            row = SubmissionSourceCleanupClaim(
                operation_id=operation.id, claim_id=str(claim_id), generation=1,
                source=(await self._target(operation)).model_dump(mode="json"),
                claimed_at=now, lease_expires_at=now + lease_duration,
            )
            self._session.add(row)
        row.claim_decision_id = decision
        await self._session.flush()
        await self._session.refresh(row)
        return _claim_value(row)

    async def record_completion_observation(self, claim: SourceCleanupClaim, source: SealedSubmissionSource) -> None:
        """Retain late completion without granting deletion under the old claim."""
        source = SealedSubmissionSource.model_validate(source)
        operation, row = await self._locked(claim.source.location.operation_id)
        now = await self._session.scalar(select(func.clock_timestamp()))
        if (not isinstance(claim.source, UnsealedSubmissionSource) or row is None
                or row.claim_id != str(claim.claim_id) or row.generation != claim.generation
                or row.confirmed_at is not None or row.lease_expires_at <= now
                or row.source != claim.source.model_dump(mode="json") or row.observed_source is not None
                or source.location != claim.source.location or source.raw_sha256 != operation.raw_sha256
                or source.raw_byte_count != operation.raw_byte_count
                or source.sealed_upload_fence != claim.source.upload_fence):
            raise IntakeCustodyConflict("source_cleanup_observation_mismatch")
        await self._require_claim_authority(operation.id)
        row.observed_source, row.observed_at = source.model_dump(mode="json"), now
        await self._session.flush()

    async def confirm(self, claim: SourceCleanupClaim, *, object_absent: bool,
                      writes_settled: bool, parts_absent: bool) -> None:
        """Commit exact absence and charge release together, never on an ACK."""
        if object_absent is not True or writes_settled is not True or parts_absent is not True:
            raise IntakeCustodyConflict("source_cleanup_unresolved")
        operation, row = await self._locked(claim.source.location.operation_id)
        if (row is None or row.claim_id != str(claim.claim_id) or row.generation != claim.generation
                or row.source != claim.source.model_dump(mode="json")
                or row.observed_source != (claim.observed_source.model_dump(mode="json") if claim.observed_source is not None else None)):
            raise IntakeCustodyConflict("source_cleanup_stale")
        if row.confirmed_at is not None:
            return
        now = await self._session.scalar(select(func.clock_timestamp()))
        if row.lease_expires_at <= now:
            raise IntakeCustodyConflict("source_cleanup_stale")
        await self._require_claim_authority(operation.id)
        row.confirmation_decision_id = await self._decision(operation, claim.claim_id, claim.generation, "confirm")
        row.confirmed_at = now
        await self._session.flush()
        await SubmissionSourceCapacity(self._session).release_confirmed(operation)

    async def upload_for_claim(self, claim: SourceCleanupClaim) -> SubmissionSourceUpload | UnsealedSourceCleanupInput:
        """Recover the exact upload under the same live audited deletion claim."""
        operation, row = await self._locked(claim.source.location.operation_id)
        now = await self._session.scalar(select(func.clock_timestamp()))
        if (row is None or row.claim_id != str(claim.claim_id) or row.generation != claim.generation
                or row.source != claim.source.model_dump(mode="json")
                or row.confirmed_at is not None or row.lease_expires_at <= now):
            raise IntakeCustodyConflict("source_cleanup_stale")
        await self._require_claim_authority(operation.id)
        receipt = await self._session.get(SubmissionSourceUploadReceipt, operation.id)
        if isinstance(claim.source, UnsealedSubmissionSource):
            intent = await self._intake._upload_intent(operation, receipt) if receipt is not None else None
            upload = (SubmissionSourceUpload(intent=intent, provider_upload_id=receipt.provider_upload_id)
                      if receipt is not None and receipt.provider_upload_id is not None else None)
            completion = None
            if receipt is not None and receipt.completion_parts is not None:
                import json
                completion = SubmissionSourceCompletion.model_validate_json(json.dumps({
                    "upload": upload.model_dump(mode="json"), "raw_sha256": operation.raw_sha256,
                    "raw_byte_count": operation.raw_byte_count, "parts": receipt.completion_parts}))
            return UnsealedSourceCleanupInput(claim.source, intent, upload, completion)
        if receipt is None or receipt.provider_upload_id is None or receipt.completion_parts is None:
            raise IntakeCustodyConflict("source_cleanup_unresolved")
        return SubmissionSourceUpload(
            intent=await self._intake._upload_intent(operation, receipt),
            provider_upload_id=receipt.provider_upload_id,
        )
