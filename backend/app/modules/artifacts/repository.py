"""Database operations for artifact ingest and immutable facts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.models import (
    ArtifactAdmissionCharge,
    ArtifactAdmissionScope,
    ArtifactContent,
    ArtifactOperationReceipt,
    ArtifactPutAttempt,
    ArtifactPutAttemptCharge,
    ArtifactReplica,
    ArtifactStorageNamespace,
    ArtifactUploadItem,
    ArtifactUploadSession,
)
from app.modules.checkers.models import CheckerRun
from app.modules.projects.models import GuideSourceSnapshot, GuideSourceSnapshotItem
from app.modules.tasks.models import Submission, WorkstreamTask


@dataclass(frozen=True, slots=True)
class GuideAdmissionFacts:
    """Authoritative project ownership for one guide source item."""

    guide_source_item_id: str
    project_id: str
    captured_by: str
    content_hash: str
    media_type: str


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
            select(ArtifactUploadItem)
            .where(ArtifactUploadItem.id == item_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

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
                    GuideSourceSnapshot.project_id,
                    GuideSourceSnapshot.captured_by,
                    GuideSourceSnapshotItem.content_hash,
                    GuideSourceSnapshotItem.media_type,
                )
                .join(
                    GuideSourceSnapshot,
                    GuideSourceSnapshot.id == GuideSourceSnapshotItem.source_snapshot_id,
                )
                .where(GuideSourceSnapshotItem.id == guide_source_item_id)
                .with_for_update(
                    of=(GuideSourceSnapshotItem, GuideSourceSnapshot)
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return GuideAdmissionFacts(
            guide_source_item_id=row.id,
            project_id=row.project_id,
            captured_by=row.captured_by,
            content_hash=row.content_hash,
            media_type=row.media_type,
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
                .with_for_update(
                    of=(ArtifactUploadSession, ArtifactUploadItem, WorkstreamTask)
                )
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

    async def get_receipt_for_item(
        self, upload_item_id: str
    ) -> ArtifactOperationReceipt | None:
        """Load the Workstream put receipt for one upload item."""
        result = await self._session.execute(
            select(ArtifactOperationReceipt).where(
                ArtifactOperationReceipt.upload_item_id == upload_item_id,
            )
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
            select(ArtifactStorageNamespace).where(
                ArtifactStorageNamespace.id == namespace.id
            )
        )
        return result.scalar_one()
