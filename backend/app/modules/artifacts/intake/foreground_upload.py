"""Foreground T2 composition for an already committed, owned intake operation.

This private command grants no contributor authority. The outer T1–T4 lifecycle
owns authorization, heartbeats, failure terminalization and cleanup scheduling.
Failures leave durable write obligations charged; this command never retries PRE,
releases bytes, or resumes a different foreground owner.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
import math
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.interfaces.artifacts import (
    ArtifactIntegrityError, ArtifactProviderOperationEvidence, ArtifactStore,
    ArtifactStoreUnavailableError,
)
from app.modules.artifacts.api.submission_intake import (
    SealedSubmissionSource, SubmissionSourceCompletion,
)
from app.modules.artifacts.intake.repository import SubmissionIntakeRepository
from app.modules.artifacts.intake.streaming import receive_submission_source
from app.modules.tasks.api.intake_custody import IntakeTaskCustodyPort


def _duration(seconds: float) -> timedelta:
    """Validate an explicit finite duration before any provider side effect."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("foreground source duration must be finite and positive")
    try:
        value = timedelta(seconds=seconds)
        datetime.now(UTC) + value  # Validate representation, not deadline authority.
    except OverflowError:
        raise ValueError("foreground source duration is not representable") from None
    if value <= timedelta(0):
        raise ValueError("foreground source duration is below timestamp precision")
    return value


class ForegroundSourceUpload:
    """Commit every durable boundary before its external provider operation."""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession],
        tasks: Callable[[AsyncSession], IntakeTaskCustodyPort], store: ArtifactStore,
    ) -> None:
        self._sessions, self._tasks, self._store = sessions, tasks, store

    def _repository(self, session: AsyncSession) -> SubmissionIntakeRepository:
        return SubmissionIntakeRepository(session, self._tasks(session))

    async def receive(
        self, operation_id: UUID, lease_id: UUID, generation: int,
        chunks: AsyncIterator[bytes], *, part_bytes: int, idle_timeout_seconds: float,
        pre_timeout_seconds: float, pre_lease_seconds: float,
        operation_evidence: ArtifactProviderOperationEvidence | None = None,
    ) -> SealedSubmissionSource:
        """Receive once under the original fence; return only committed source facts."""
        pre_timeout = _duration(pre_timeout_seconds)
        pre_lease = _duration(pre_lease_seconds)
        if pre_lease > pre_timeout:
            raise ValueError("foreground PRE lease exceeds its hard deadline")
        async with self._sessions.begin() as session:
            intent = await self._repository(session).prepare_upload(
                operation_id, lease_id, generation,
                part_bytes=part_bytes, idle_timeout_seconds=idle_timeout_seconds,
            )
        upload = await self._store.begin_source_upload(intent, operation_evidence=operation_evidence)
        async with self._sessions.begin() as session:
            await self._repository(session).record_upload(
                operation_id, lease_id, generation, upload=upload,
            )
        completion = await receive_submission_source(
            self._store, upload, chunks, operation_evidence=operation_evidence,
        )
        async with self._sessions.begin() as session:
            await self._repository(session).record_eof(
                operation_id, lease_id, generation, completion=completion,
            )
        try:
            source = await self._store.complete_source_upload(
                completion, operation_evidence=operation_evidence,
            )
        except ArtifactStoreUnavailableError:
            remaining = (intent.upload_deadline_at - datetime.now(UTC)).total_seconds()
            if remaining <= 0:
                raise
            try:
                async with asyncio.timeout(remaining):
                    source = await self._store.observe_source_upload(
                        completion, operation_evidence=operation_evidence,
                    )
            except TimeoutError:
                raise ArtifactStoreUnavailableError("submission completion observation expired") from None
            if source is None:
                raise
        source = self._bind_source(completion, source)
        async with self._sessions.begin() as session:
            now = await session.scalar(select(func.clock_timestamp()))
            committed = await self._repository(session).seal(
                operation_id, lease_id, generation,
                provider_generation=source.provider_generation,
                pre_deadline_at=now + pre_timeout, lease_expires_at=now + pre_lease,
            )
            if committed != source:
                raise ArtifactIntegrityError("submission source differs from committed intake")
        return committed

    @staticmethod
    def _bind_source(completion: SubmissionSourceCompletion, source: SealedSubmissionSource) -> SealedSubmissionSource:
        """Bind owner-known facts; provider generation truth belongs to the adapter."""
        try:
            source = SealedSubmissionSource.model_validate(source)
        except ValueError:
            raise ArtifactIntegrityError("submission provider returned invalid source") from None
        if (source.location != completion.upload.intent.location
                or source.raw_sha256 != completion.raw_sha256
                or source.raw_byte_count != completion.raw_byte_count
                or source.sealed_upload_fence != completion.upload.intent.upload_fence):
            raise ArtifactIntegrityError("submission provider source identity mismatch")
        return source
