"""Database operations for artifact ingest and immutable facts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, case, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.models import (
    ArtifactAdmissionCharge,
    ArtifactAdmissionScope,
    ArtifactBinding,
    ArtifactContent,
    ArtifactOperationReceipt,
    ArtifactPutAttempt,
    ArtifactPutAttemptCharge,
    ArtifactPutObservationReceipt,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
    ArtifactReplica,
    ArtifactRecoveryAttempt,
    ArtifactStorageNamespace,
    ArtifactUploadItem,
    ArtifactUploadSession,
)
from app.modules.checkers.models import CheckerRun
from app.modules.projects.models import (
    GuideSourceArtifactIngest,
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
)
from app.modules.tasks.models import Submission, WorkstreamTask


@dataclass(frozen=True, slots=True)
class GuideAdmissionFacts:
    """Authoritative project ownership for one guide source item."""

    guide_source_item_id: str
    guide_source_snapshot_id: str
    guide_id: str
    project_id: str
    captured_by: str
    content_hash: str
    byte_count: int
    media_type: str


@dataclass(frozen=True, slots=True)
class GuideLineageFacts:
    """Locked canonical ownership for a not-yet-staged guide item."""

    guide_source_item_id: str
    guide_source_snapshot_id: str
    guide_id: str
    project_id: str


@dataclass(frozen=True, slots=True)
class ContributorAdmissionFacts:
    """Authoritative upload-item ownership and state."""

    upload_item_id: str
    project_id: str
    task_id: str | None
    actor_profile_id: str
    session_state: str
    item_state: str
    expected_sha256: str | None
    expected_size: int | None
    media_type: str | None


@dataclass(frozen=True, slots=True)
class CheckerOutputAdmissionFacts:
    """Authoritative project/task ownership for one checker run."""

    checker_run_id: str
    project_id: str
    task_id: str


class ArtifactRepository:
    """Persist artifact state transitions under caller-owned transactions."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the repository to one async database session."""
        self._session = session

    async def database_now(self) -> datetime:
        """Return the PostgreSQL clock for admission timestamps."""
        value = await self._session.scalar(select(func.clock_timestamp()))
        if value is None:
            raise RuntimeError("PostgreSQL clock did not return a timestamp")
        return value

    async def lock_upload_item(self, item_id: str) -> ArtifactUploadItem | None:
        """Load one upload item with a row lock."""
        result = await self._session.execute(
            select(ArtifactUploadItem).where(ArtifactUploadItem.id == item_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def lock_checker_run(self, checker_run_id: str) -> CheckerRun | None:
        """Lock one checker run for canonical recovery resource derivation."""
        return await self._session.scalar(
            select(CheckerRun).where(CheckerRun.id == checker_run_id).with_for_update()
        )

    async def lock_upload_session(self, session_id: str) -> ArtifactUploadSession | None:
        """Load one upload session with a row lock."""
        result = await self._session.execute(
            select(ArtifactUploadSession)
            .where(ArtifactUploadSession.id == session_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_guide_admission_facts(
        self, guide_source_item_id: str
    ) -> GuideAdmissionFacts | None:
        """Load canonical project ownership for one guide source item."""
        row = (
            await self._session.execute(
                select(
                    GuideSourceSnapshotItem.id,
                    GuideSourceSnapshotItem.source_snapshot_id,
                    GuideSourceSnapshot.guide_id,
                    GuideSourceSnapshot.project_id,
                    GuideSourceArtifactIngest.actor_profile_id,
                    GuideSourceArtifactIngest.sha256,
                    GuideSourceArtifactIngest.byte_count,
                    GuideSourceArtifactIngest.media_type,
                )
                .join(
                    GuideSourceSnapshot,
                    GuideSourceSnapshot.id == GuideSourceSnapshotItem.source_snapshot_id,
                )
                .join(
                    GuideSourceArtifactIngest,
                    GuideSourceArtifactIngest.source_item_id == GuideSourceSnapshotItem.id,
                )
                .where(GuideSourceSnapshotItem.id == guide_source_item_id)
                .with_for_update(of=(GuideSourceSnapshotItem, GuideSourceSnapshot))
            )
        ).one_or_none()
        if row is None:
            return None
        return GuideAdmissionFacts(
            guide_source_item_id=row.id,
            guide_source_snapshot_id=row.source_snapshot_id,
            guide_id=row.guide_id,
            project_id=row.project_id,
            captured_by=row.actor_profile_id,
            content_hash=row.sha256,
            byte_count=row.byte_count,
            media_type=row.media_type,
        )

    async def stage_guide_source_ingest(
        self,
        *,
        project_id: UUID | None,
        guide_id: UUID | None,
        guide_source_snapshot_id: UUID | None,
        guide_source_item_id: UUID,
        actor_profile_id: UUID,
        sha256: str,
        byte_count: int,
        media_type: str,
    ) -> GuideSourceArtifactIngest:
        """Persist server-prepared facts after locking exact legacy descriptor lineage."""
        lineage = await self.get_guide_lineage(str(guide_source_item_id))
        if (
            lineage is None
            or (
                guide_source_snapshot_id is not None
                and lineage.guide_source_snapshot_id != str(guide_source_snapshot_id)
            )
            or (guide_id is not None and lineage.guide_id != str(guide_id))
            or (project_id is not None and lineage.project_id != str(project_id))
        ):
            raise ValueError("guide source lineage is unavailable")
        existing = await self._session.scalar(
            select(GuideSourceArtifactIngest)
            .where(GuideSourceArtifactIngest.source_item_id == str(guide_source_item_id))
            .with_for_update()
        )
        if existing is not None:
            if (
                existing.actor_profile_id != str(actor_profile_id)
                or existing.sha256 != sha256
                or existing.byte_count != byte_count
                or existing.media_type != media_type
            ):
                raise ValueError("guide source ingest conflicts with prepared bytes")
            return existing
        ingest = GuideSourceArtifactIngest(
            id=str(uuid4()),
            source_item_id=str(guide_source_item_id),
            actor_profile_id=str(actor_profile_id),
            sha256=sha256,
            byte_count=byte_count,
            media_type=media_type,
        )
        self._session.add(ingest)
        await self._session.flush()
        return ingest

    async def get_guide_lineage(self, guide_source_item_id: str) -> GuideLineageFacts | None:
        """Lock and return canonical snapshot lineage without trusting caller hashes."""
        lineage = (
            await self._session.execute(
                select(
                    GuideSourceSnapshotItem.id,
                    GuideSourceSnapshotItem.source_snapshot_id,
                    GuideSourceSnapshot.guide_id,
                    GuideSourceSnapshot.project_id,
                )
                .join(
                    GuideSourceSnapshot,
                    GuideSourceSnapshot.id == GuideSourceSnapshotItem.source_snapshot_id,
                )
                .where(GuideSourceSnapshotItem.id == guide_source_item_id)
                .with_for_update(of=(GuideSourceSnapshotItem, GuideSourceSnapshot))
            )
        ).one_or_none()
        if lineage is None:
            return None
        return GuideLineageFacts(
            guide_source_item_id=lineage.id,
            guide_source_snapshot_id=lineage.source_snapshot_id,
            guide_id=lineage.guide_id,
            project_id=lineage.project_id,
        )

    async def get_contributor_admission_facts(
        self, upload_item_id: str
    ) -> ContributorAdmissionFacts | None:
        """Load canonical contributor upload ownership and state."""
        row = (
            await self._session.execute(
                select(
                    ArtifactUploadItem.id,
                    WorkstreamTask.project_id,
                    WorkstreamTask.id.label("task_id"),
                    ArtifactUploadSession.actor_id,
                    ArtifactUploadSession.state.label("session_state"),
                    ArtifactUploadItem.state.label("item_state"),
                    ArtifactUploadItem.expected_sha256,
                    ArtifactUploadItem.expected_size,
                    ArtifactUploadItem.media_type,
                )
                .join(
                    ArtifactUploadSession,
                    ArtifactUploadSession.id == ArtifactUploadItem.session_id,
                )
                .join(
                    WorkstreamTask,
                    (WorkstreamTask.id == ArtifactUploadSession.task_id)
                    & (WorkstreamTask.project_id == ArtifactUploadSession.project_id),
                )
                .where(ArtifactUploadItem.id == upload_item_id)
                .with_for_update(of=(ArtifactUploadSession, ArtifactUploadItem, WorkstreamTask))
            )
        ).one_or_none()
        if row is None:
            return None
        return ContributorAdmissionFacts(
            upload_item_id=row.id,
            project_id=row.project_id,
            task_id=row.task_id,
            actor_profile_id=row.actor_id,
            session_state=row.session_state,
            item_state=row.item_state,
            expected_sha256=row.expected_sha256,
            expected_size=row.expected_size,
            media_type=row.media_type,
        )

    async def get_checker_output_admission_facts(
        self, checker_run_id: str
    ) -> CheckerOutputAdmissionFacts | None:
        """Load canonical project/task ownership for one checker run."""
        row = (
            await self._session.execute(
                select(CheckerRun.id, Submission.task_id, WorkstreamTask.project_id)
                .join(
                    Submission,
                    (Submission.id == CheckerRun.submission_id)
                    & (Submission.version == CheckerRun.submission_version)
                    & (Submission.task_id == CheckerRun.task_id),
                )
                .join(WorkstreamTask, WorkstreamTask.id == Submission.task_id)
                .where(CheckerRun.id == checker_run_id)
                .with_for_update(of=(CheckerRun, Submission, WorkstreamTask))
            )
        ).one_or_none()
        if row is None:
            return None
        return CheckerOutputAdmissionFacts(
            checker_run_id=row.id,
            project_id=row.project_id,
            task_id=row.task_id,
        )

    async def ensure_and_lock_admission_scopes(
        self,
        scopes: Sequence[tuple[str, str, int]],
    ) -> tuple[ArtifactAdmissionScope, ...]:
        """Create missing counters, then lock every scope in canonical order."""
        values = [
            {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "limit_bytes": limit_bytes,
                "counted_bytes": 0,
                "cas_version": 0,
            }
            for scope_type, scope_id, limit_bytes in scopes
        ]
        await self._session.execute(
            insert(ArtifactAdmissionScope)
            .values(values)
            .on_conflict_do_nothing(
                index_elements=[
                    ArtifactAdmissionScope.scope_type,
                    ArtifactAdmissionScope.scope_id,
                ]
            )
        )
        keys = [(scope_type, scope_id) for scope_type, scope_id, _ in scopes]
        result = await self._session.execute(
            select(ArtifactAdmissionScope)
            .where(
                tuple_(
                    ArtifactAdmissionScope.scope_type,
                    ArtifactAdmissionScope.scope_id,
                ).in_(keys)
            )
            .order_by(ArtifactAdmissionScope.scope_type, ArtifactAdmissionScope.scope_id)
            .with_for_update()
        )
        return tuple(result.scalars().all())

    async def get_admission_charge(
        self,
        *,
        scope_type: str,
        scope_id: str,
        sha256: str,
        byte_count: int,
    ) -> ArtifactAdmissionCharge | None:
        """Load one exact scope/content charge while its scope is locked."""
        return await self._session.scalar(
            select(ArtifactAdmissionCharge).where(
                ArtifactAdmissionCharge.scope_type == scope_type,
                ArtifactAdmissionCharge.scope_id == scope_id,
                ArtifactAdmissionCharge.sha256 == sha256,
                ArtifactAdmissionCharge.byte_count == byte_count,
            )
        )

    async def add_admission_charge(
        self, charge: ArtifactAdmissionCharge
    ) -> ArtifactAdmissionCharge:
        """Flush one new charge under its locked scope counter."""
        self._session.add(charge)
        await self._session.flush()
        return charge

    async def get_put_attempt_by_operation(
        self, operation_identity: str
    ) -> ArtifactPutAttempt | None:
        """Load the durable attempt for one canonical operation identity."""
        return await self._session.scalar(
            select(ArtifactPutAttempt).where(
                ArtifactPutAttempt.operation_identity == operation_identity
            )
        )

    async def lock_put_attempt(self, attempt_id: str) -> ArtifactPutAttempt | None:
        """Lock one exact attempt and refresh its current fence."""
        return await self._session.scalar(
            select(ArtifactPutAttempt)
            .where(ArtifactPutAttempt.id == attempt_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def claim_put_attempt(
        self,
        *,
        attempt_id: UUID,
        executor_id: UUID,
        lease_seconds: float,
        mode: str,
        expected_generation: int,
    ) -> ArtifactPutAttempt | None:
        """Claim caller put or read-only observation using PostgreSQL time."""
        if mode == "caller_put":
            eligible = ArtifactPutAttempt.status.in_(("prepared", "absent_replay_required"))
        elif mode == "observation":
            eligible = or_(
                ArtifactPutAttempt.status.in_(("prepared", "acknowledgement_unknown")),
                and_(
                    ArtifactPutAttempt.status == "put_in_flight",
                    ArtifactPutAttempt.lease_expires_at < func.clock_timestamp(),
                ),
            )
        else:
            raise ValueError("artifact put execution mode is invalid")
        statement = (
            update(ArtifactPutAttempt)
            .where(
                ArtifactPutAttempt.id == str(attempt_id),
                ArtifactPutAttempt.execution_generation == expected_generation,
                eligible,
            )
            .values(
                status="put_in_flight",
                executor_id=str(executor_id),
                lease_expires_at=func.clock_timestamp() + timedelta(seconds=lease_seconds),
                execution_generation=ArtifactPutAttempt.execution_generation + 1,
                execution_mode=mode,
                observation_count=ArtifactPutAttempt.observation_count
                + (1 if mode == "observation" else 0),
                next_run_at=None,
                cas_version=ArtifactPutAttempt.cas_version + 1,
            )
            .returning(ArtifactPutAttempt)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_due_put_attempt_ids(self, *, cutoff: datetime, limit: int) -> tuple[str, ...]:
        """List one stable bounded scanner page without claiming work."""
        result = await self._session.execute(
            select(ArtifactPutAttempt.id)
            .where(
                or_(
                    ArtifactPutAttempt.status == "prepared",
                    and_(
                        ArtifactPutAttempt.status == "acknowledgement_unknown",
                        ArtifactPutAttempt.next_run_at <= cutoff,
                    ),
                    and_(
                        ArtifactPutAttempt.status == "put_in_flight",
                        ArtifactPutAttempt.lease_expires_at <= cutoff,
                    ),
                )
            )
            .order_by(
                case(
                    (
                        ArtifactPutAttempt.status == "acknowledgement_unknown",
                        ArtifactPutAttempt.next_run_at,
                    ),
                    (
                        ArtifactPutAttempt.status == "put_in_flight",
                        ArtifactPutAttempt.lease_expires_at,
                    ),
                    else_=ArtifactPutAttempt.prepared_at,
                ),
                ArtifactPutAttempt.id,
            )
            .limit(limit)
        )
        return tuple(result.scalars().all())

    async def add_put_observation_receipt(
        self, receipt: ArtifactPutObservationReceipt
    ) -> ArtifactPutObservationReceipt:
        self._session.add(receipt)
        await self._session.flush()
        return receipt

    async def add_verification_job(self, job: ArtifactVerificationJob) -> ArtifactVerificationJob:
        self._session.add(job)
        await self._session.flush()
        return job

    async def add_recovery_attempt(
        self, attempt: ArtifactRecoveryAttempt
    ) -> ArtifactRecoveryAttempt:
        """Persist one recovery envelope inside the caller-owned transaction."""
        self._session.add(attempt)
        await self._session.flush()
        return attempt

    async def lock_recovery_by_source(self, source_job_id: str) -> ArtifactRecoveryAttempt | None:
        """Lock the lifetime recovery owner for one source verification job."""
        return await self._session.scalar(
            select(ArtifactRecoveryAttempt)
            .where(ArtifactRecoveryAttempt.source_verification_job_id == source_job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def lock_recovery_by_retry(self, retry_job_id: str) -> ArtifactRecoveryAttempt | None:
        """Lock the envelope finalized by one retry verification job."""
        return await self._session.scalar(
            select(ArtifactRecoveryAttempt)
            .where(ArtifactRecoveryAttempt.retry_verification_job_id == retry_job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def lock_verification_job(self, job_id: str) -> ArtifactVerificationJob | None:
        return await self._session.scalar(
            select(ArtifactVerificationJob)
            .where(ArtifactVerificationJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def claim_verification_job(
        self,
        *,
        job_id: UUID,
        executor_id: UUID,
        lease_seconds: float,
        expected_generation: int,
    ) -> ArtifactVerificationJob | None:
        eligible = or_(
            ArtifactVerificationJob.status == "pending",
            and_(
                ArtifactVerificationJob.status == "provider_unavailable",
                ArtifactVerificationJob.next_run_at <= func.clock_timestamp(),
                ArtifactVerificationJob.terminal_at.is_(None),
            ),
            and_(
                ArtifactVerificationJob.status == "running",
                ArtifactVerificationJob.lease_expires_at < func.clock_timestamp(),
            ),
        )
        statement = (
            update(ArtifactVerificationJob)
            .where(
                ArtifactVerificationJob.id == str(job_id),
                ArtifactVerificationJob.execution_generation == expected_generation,
                eligible,
            )
            .values(
                status="running",
                executor_id=str(executor_id),
                lease_expires_at=func.clock_timestamp() + timedelta(seconds=lease_seconds),
                execution_generation=ArtifactVerificationJob.execution_generation + 1,
                attempt_count=ArtifactVerificationJob.attempt_count + 1,
                next_run_at=None,
                cas_version=ArtifactVerificationJob.cas_version + 1,
            )
            .returning(ArtifactVerificationJob)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_due_verification_job_ids(
        self, *, cutoff: datetime, limit: int
    ) -> tuple[str, ...]:
        result = await self._session.execute(
            select(ArtifactVerificationJob.id)
            .where(
                or_(
                    ArtifactVerificationJob.status == "pending",
                    and_(
                        ArtifactVerificationJob.status == "provider_unavailable",
                        ArtifactVerificationJob.next_run_at <= cutoff,
                        ArtifactVerificationJob.terminal_at.is_(None),
                    ),
                    and_(
                        ArtifactVerificationJob.status == "running",
                        ArtifactVerificationJob.lease_expires_at <= cutoff,
                    ),
                )
            )
            .order_by(
                case(
                    (
                        ArtifactVerificationJob.status == "provider_unavailable",
                        ArtifactVerificationJob.next_run_at,
                    ),
                    (
                        ArtifactVerificationJob.status == "running",
                        ArtifactVerificationJob.lease_expires_at,
                    ),
                    else_=ArtifactVerificationJob.created_at,
                ),
                ArtifactVerificationJob.id,
            )
            .limit(limit)
        )
        return tuple(result.scalars().all())

    async def add_verification_receipt(
        self, receipt: ArtifactVerificationReceipt
    ) -> ArtifactVerificationReceipt:
        self._session.add(receipt)
        await self._session.flush()
        return receipt

    async def add_put_attempt(
        self,
        attempt: ArtifactPutAttempt,
        charges: Sequence[ArtifactAdmissionCharge],
    ) -> ArtifactPutAttempt:
        """Flush one attempt and its complete charge links in this transaction."""
        self._session.add(attempt)
        await self._session.flush()
        self._session.add_all(
            ArtifactPutAttemptCharge(attempt_id=attempt.id, charge_id=charge.id)
            for charge in charges
        )
        await self._session.flush()
        return attempt

    async def list_put_attempt_charge_ids(self, attempt_id: str) -> tuple[str, ...]:
        """Return one attempt's charge IDs in stable order."""
        result = await self._session.execute(
            select(ArtifactPutAttemptCharge.charge_id)
            .where(ArtifactPutAttemptCharge.attempt_id == attempt_id)
            .order_by(ArtifactPutAttemptCharge.charge_id)
        )
        return tuple(result.scalars().all())

    async def lock_attempt_charges(self, attempt_id: str) -> tuple[ArtifactAdmissionCharge, ...]:
        """Lock linked charges in canonical scope order."""
        result = await self._session.execute(
            select(ArtifactAdmissionCharge)
            .join(
                ArtifactPutAttemptCharge,
                ArtifactPutAttemptCharge.charge_id == ArtifactAdmissionCharge.id,
            )
            .where(ArtifactPutAttemptCharge.attempt_id == attempt_id)
            .order_by(ArtifactAdmissionCharge.scope_type, ArtifactAdmissionCharge.scope_id)
            .with_for_update(of=ArtifactAdmissionCharge)
        )
        return tuple(result.scalars().all())

    async def lock_charge_scopes(
        self, charges: Sequence[ArtifactAdmissionCharge]
    ) -> tuple[ArtifactAdmissionScope, ...]:
        keys = sorted({(charge.scope_type, charge.scope_id) for charge in charges})
        result = await self._session.execute(
            select(ArtifactAdmissionScope)
            .where(
                tuple_(ArtifactAdmissionScope.scope_type, ArtifactAdmissionScope.scope_id).in_(keys)
            )
            .order_by(ArtifactAdmissionScope.scope_type, ArtifactAdmissionScope.scope_id)
            .with_for_update()
        )
        return tuple(result.scalars().all())

    async def lock_replica(self, replica_id: str) -> ArtifactReplica | None:
        return await self._session.scalar(
            select(ArtifactReplica)
            .where(ArtifactReplica.id == replica_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def lock_content(self, content_id: str) -> ArtifactContent | None:
        """Serialize binding creation and unbound lifecycle transitions."""
        return await self._session.scalar(
            select(ArtifactContent)
            .where(ArtifactContent.id == content_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def lock_binding_for_content(self, content_id: str) -> ArtifactBinding | None:
        """Lock one binding proving that content has entered an immutable lifecycle."""
        return await self._session.scalar(
            select(ArtifactBinding)
            .where(ArtifactBinding.content_id == content_id)
            .order_by(ArtifactBinding.id)
            .limit(1)
            .with_for_update()
        )

    async def get_or_create_content(self, content: ArtifactContent) -> ArtifactContent:
        """Return the immutable content fact for one digest and size."""
        await self._session.execute(
            insert(ArtifactContent)
            .values(
                id=content.id,
                sha256=content.sha256,
                byte_count=content.byte_count,
                media_type=content.media_type,
                normalized_display_name=content.normalized_display_name,
            )
            .on_conflict_do_nothing(constraint="uq_artifact_content_digest_size")
        )
        result = await self._session.execute(
            select(ArtifactContent).where(
                ArtifactContent.sha256 == content.sha256,
                ArtifactContent.byte_count == content.byte_count,
            )
        )
        return result.scalar_one()

    async def get_or_create_replica(self, replica: ArtifactReplica) -> ArtifactReplica:
        """Atomically return one replica for a namespace and provider object."""
        await self._session.execute(
            insert(ArtifactReplica)
            .values(
                id=replica.id,
                content_id=replica.content_id,
                storage_namespace_id=replica.storage_namespace_id,
                namespace_fingerprint=replica.namespace_fingerprint,
                adapter=replica.adapter,
                provider_profile=replica.provider_profile,
                provider_object_ref=replica.provider_object_ref,
                verification_state=replica.verification_state,
                availability_state=replica.availability_state,
                integrity_state=replica.integrity_state,
            )
            .on_conflict_do_nothing(constraint="uq_artifact_replica_provider_object")
        )
        result = await self._session.execute(
            select(ArtifactReplica).where(
                ArtifactReplica.storage_namespace_id == replica.storage_namespace_id,
                ArtifactReplica.provider_object_ref == replica.provider_object_ref,
            )
        )
        return result.scalar_one()

    async def add_receipt(self, receipt: ArtifactOperationReceipt) -> ArtifactOperationReceipt:
        """Persist one append-only Workstream put receipt."""
        self._session.add(receipt)
        await self._session.flush()
        return receipt

    async def get_receipt_for_item(self, upload_item_id: str) -> ArtifactOperationReceipt | None:
        """Load the Workstream put receipt for one upload item."""
        result = await self._session.execute(
            select(ArtifactOperationReceipt)
            .where(ArtifactOperationReceipt.upload_item_id == upload_item_id)
            .order_by(
                ArtifactOperationReceipt.created_at.desc(),
                ArtifactOperationReceipt.id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def claim_storage_namespace(
        self, namespace: ArtifactStorageNamespace
    ) -> ArtifactStorageNamespace:
        """Atomically claim or load the immutable deployment namespace."""
        await self._session.execute(
            insert(ArtifactStorageNamespace)
            .values(
                id=namespace.id,
                backend=namespace.backend,
                adapter=namespace.adapter,
                provider_profile=namespace.provider_profile,
                namespace_descriptor=namespace.namespace_descriptor,
                namespace_fingerprint=namespace.namespace_fingerprint,
            )
            .on_conflict_do_nothing(index_elements=[ArtifactStorageNamespace.id])
        )
        result = await self._session.execute(
            select(ArtifactStorageNamespace).where(ArtifactStorageNamespace.id == namespace.id)
        )
        return result.scalar_one()
