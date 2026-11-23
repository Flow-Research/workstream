"""One foreground upload/PRE/acceptance invocation under the original lease."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
import logging
import math
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cancellation import await_cancellation_resistant
from app.interfaces.artifacts import ArtifactInputMismatchError, ArtifactLimitExceededError
from app.modules.artifacts.api.submission_intake import SubmissionIntakeFailure, SubmissionIntakeMetadata
from app.modules.artifacts.api.submission_preparation import public_pre_submission_results
from app.modules.artifacts.intake.foreground_admission import (
    ForegroundIntakeAdmission, IntakeCommitUnknown, IntakeReplay, IntakeReservationOwner,
)
from app.modules.artifacts.intake.foreground_lease import ForegroundIntakeLease
from app.modules.artifacts.intake.foreground_upload import ForegroundSourceUpload
from app.modules.artifacts.intake.repository import IntakeCustodyConflict
from app.modules.artifacts.intake.streaming import SubmissionUploadTimeout
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitCompletion, SelectedPreSubmitCoordinationPort,
    SelectedPreSubmitReservationFacts, SelectedPreSubmitRuntimeProfile,
)
from app.modules.outbox.api import OutboxAppendPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SubmissionForegroundLimits:
    """Explicit transport bounds; no production deployment values are inferred."""

    part_bytes: int
    idle_timeout_seconds: float
    pre_lease_seconds: float
    replay_duration: timedelta

    def __post_init__(self) -> None:
        if type(self.part_bytes) is not int or not 5 * 1024**2 <= self.part_bytes <= 16 * 1024**2:
            raise ValueError("submission part size is invalid")
        for value in (self.idle_timeout_seconds, self.pre_lease_seconds):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("submission time limit is invalid")
        if not isinstance(self.replay_duration, timedelta) or self.replay_duration <= timedelta(0):
            raise ValueError("submission replay duration is invalid")


class ForegroundSubmissionCommand:
    """Compose existing owners; provider/runtime lifetime belongs to the root."""

    def __init__(
        self, *, admission: ForegroundIntakeAdmission, upload: ForegroundSourceUpload,
        lease: ForegroundIntakeLease, limits: SubmissionForegroundLimits,
        runtime_profile: SelectedPreSubmitRuntimeProfile,
        execute: Callable[[SelectedPreSubmitReservationFacts], Awaitable[SelectedPreSubmitCompletion]],
        checkers: Callable[[AsyncSession], SelectedPreSubmitCoordinationPort],
        outbox: Callable[[AsyncSession], OutboxAppendPort],
    ) -> None:
        if limits.pre_lease_seconds * 1000 > runtime_profile.aggregate_deadline_ms:
            raise ValueError("submission PRE lease exceeds its aggregate deadline")
        self._admission, self._upload, self._lease = admission, upload, lease
        self._limits, self._profile, self._execute = limits, runtime_profile, execute
        self._checkers, self._outbox = checkers, outbox

    async def submit(
        self, metadata: SubmissionIntakeMetadata, chunks: AsyncIterator[bytes], *,
        actor_id: UUID, identity_link_id: UUID, idempotency_key: UUID,
        declared_raw_bytes: int | None,
    ) -> dict:
        """Return only a positively committed T4 receipt; never wait for T5."""
        owner = await self._admission.admit(
            metadata, actor_id=actor_id, identity_link_id=identity_link_id,
            idempotency_key=idempotency_key, declared_raw_bytes=declared_raw_bytes,
        )
        if isinstance(owner, IntakeReplay):
            try:
                replay = await self._admission.replay(
                    metadata, chunks, actor_id=actor_id, idempotency_key=idempotency_key,
                    declared_raw_bytes=declared_raw_bytes,
                    idle_timeout_seconds=self._limits.idle_timeout_seconds,
                    replay_duration=self._limits.replay_duration,
                )
            except SubmissionUploadTimeout:
                raise SubmissionIntakeFailure("submission_upload_timeout") from None
            if replay.acceptance_receipt is not None:
                return replay.acceptance_receipt
            return await self._admission.replay_failure(
                metadata, actor_id=actor_id, idempotency_key=idempotency_key,
                operation_id=replay.operation_id, checkers=self._checkers,
            )

        async def run(_operation_id, _lease_id, _generation):
            return await self._run(owner, chunks)

        try:
            return await self._lease.run(owner.operation_id, owner.lease_id, owner.generation, run)
        except IntakeCommitUnknown:
            # No failure mutation after an unacknowledged commit. Same-key
            # observation/replay or expiry resolves durable ownership.
            raise
        except BaseException as exc:
            state = "cancelled" if isinstance(exc, asyncio.CancelledError) else "failed"
            code = "submission_cancelled" if state == "cancelled" else "submission_infrastructure_unavailable"
            if isinstance(exc, SubmissionIntakeFailure):
                code = exc.code
                if code == "pre_submission_checker_failed":
                    state = "rejected"
            elif isinstance(exc, ArtifactLimitExceededError):
                code = "submission_archive_limit_exceeded"
            elif isinstance(exc, ArtifactInputMismatchError):
                code = "submission_packet_invalid"
            elif isinstance(exc, SubmissionUploadTimeout):
                code = "submission_upload_timeout"
            try:
                finished = await await_cancellation_resistant(self._admission.finish(owner, state=state, failure_code=code))
            except BaseException:
                logger.exception("Submission foreground terminalization failed", extra={"operation_id": str(owner.operation_id)})
                if not isinstance(exc, asyncio.CancelledError):
                    raise IntakeCommitUnknown("submission terminal outcome is unresolved") from None
            else:
                if not finished and not isinstance(exc, asyncio.CancelledError):
                    release_failure = await self._admission.assignment_release_failure(
                        owner, metadata, actor_id=actor_id, idempotency_key=idempotency_key,
                    )
                    if release_failure is not None:
                        raise SubmissionIntakeFailure(release_failure) from None
                    raise IntakeCommitUnknown("submission foreground ownership has changed") from None
            if isinstance(exc, SubmissionUploadTimeout):
                raise SubmissionIntakeFailure(code) from None
            raise

    async def _run(self, owner: IntakeReservationOwner, chunks: AsyncIterator[bytes]) -> dict:
        source = await self._upload.receive(
            owner.operation_id, owner.lease_id, owner.generation, chunks,
            part_bytes=self._limits.part_bytes,
            idle_timeout_seconds=self._limits.idle_timeout_seconds,
            pre_timeout_seconds=self._profile.aggregate_deadline_ms / 1000,
            pre_lease_seconds=self._limits.pre_lease_seconds,
        )
        reservation = await self._admission.reserve_pre(
            owner, source, runtime_profile=self._profile, checkers=self._checkers,
        )
        completion = await self._execute(reservation)
        terminal = completion.terminal
        if terminal.lease.reservation != reservation:
            raise IntakeCustodyConflict("intake_pre_result_mismatch")
        if terminal.execution is None:
            raise SubmissionIntakeFailure("submission_infrastructure_unavailable")
        if not terminal.execution.eligible:
            raise SubmissionIntakeFailure(
                "pre_submission_checker_failed",
                pre_submission_results=public_pre_submission_results(terminal.execution),
            )
        return await self._admission.accept(
            owner, reservation, terminal.terminal_digest,
            checkers=self._checkers, outbox=self._outbox,
        )
