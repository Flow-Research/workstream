"""ART ownership of sealed bytes and one size-bound trusted intake session."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator, Awaitable
from typing import BinaryIO, Literal

from app.core.cancellation import (
    await_cancellation_resistant,
    await_completion_preserving_cancellation,
)
from app.interfaces.external_services import ExternalServiceAdapterError
from app.interfaces.artifacts import ArtifactScratchIntegrityError
from app.interfaces.trusted_submission_intake import (
    TrustedIntakePreparation,
    TrustedIntakeSession,
    TrustedSubmissionIntakeAdapter,
)
from app.modules.artifacts.preparation import ArtifactPreparationDeadlineError
from app.modules.artifacts.sources import ArtifactCommitment, PreparedArtifact
from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveInspectionResult, SubmissionArchiveRejectedError, SubmissionArchiveFailureCode,
)


class TrustedArchiveInspector:
    """Bind PreparedArtifact's retained reader to its exact server commitment."""

    def __init__(self, intake: TrustedIntakeSession, commitment: ArtifactCommitment) -> None:
        """Retain the session and sealed commitment owned by this preparation."""
        self._intake, self._commitment = intake, commitment

    def inspect(self, reader: BinaryIO) -> SubmissionArchiveInspectionResult:
        """Inspect the retained reader against its server-computed size and digest."""
        return self._intake.inspect(
            reader,
            archive_sha256=self._commitment.sha256,
            archive_byte_count=self._commitment.byte_count,
        )


@asynccontextmanager
async def prepared_trusted_intake(
    adapter: TrustedSubmissionIntakeAdapter,
    prepare_bytes: Awaitable[PreparedArtifact],
    *,
    phase: Literal["pre_submit", "post_submit"],
    policy_sha256: str,
    limits: SubmissionArchiveLimits,
    deadline: float,
) -> AsyncIterator[tuple[PreparedArtifact, TrustedIntakeSession]]:
    """Seal before allocating inspection; preserve the original absolute deadline."""
    prepared: PreparedArtifact | None = None
    pending: asyncio.Task[TrustedIntakeSession] | None = None
    failure: BaseException | None = None
    try:
        try:
            async with asyncio.timeout_at(deadline):
                prepared = await prepare_bytes
                if prepared.commitment.byte_count == 0:
                    raise SubmissionArchiveRejectedError(SubmissionArchiveFailureCode.MALFORMED)
                remaining_ms = int((deadline - asyncio.get_running_loop().time()) * 1000)
                if remaining_ms <= 0:
                    raise ArtifactPreparationDeadlineError("artifact preparation deadline exceeded")
                request = TrustedIntakePreparation(
                    phase=phase, policy_sha256=policy_sha256, limits=limits,
                    deadline_ms=remaining_ms,
                    archive_byte_count=prepared.commitment.byte_count,
                )
                pending = asyncio.create_task(adapter.prepare(request))
                intake = await asyncio.shield(pending)
        except TimeoutError:
            raise ArtifactPreparationDeadlineError("artifact preparation deadline exceeded") from None
        yield prepared, intake
    except BaseException as error:
        failure = error
        raise
    finally:
        try:
            if pending is not None:
                if not pending.done():
                    pending.cancel()
                try:
                    session = await await_cancellation_resistant(pending)
                except (asyncio.CancelledError, ExternalServiceAdapterError):
                    if failure is None:
                        raise
                else:
                    cancelled = isinstance(failure, asyncio.CancelledError)
                    if cancelled:
                        session.abort()
                    try:
                        await await_completion_preserving_cancellation(session.close())
                    except ExternalServiceAdapterError:
                        # Keep unresolved timeout/cancellation distinct from a
                        # work rejection whose runtime cleanup remains unconfirmed.
                        if not cancelled and not isinstance(failure, ArtifactPreparationDeadlineError):
                            raise
        finally:
            if prepared is not None:
                try:
                    # PreparedArtifact owns cancellation-resistant release and lets cleanup
                    # failure win over cancellation; another wrapper would hide it.
                    await prepared.close()
                except Exception as error:
                    raise ArtifactScratchIntegrityError("trusted_intake_source_cleanup_unconfirmed") from error
