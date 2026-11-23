"""Commit cleanup authority before provider I/O, then confirm exact settlement."""
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from app.core.cancellation import await_completion_preserving_cancellation
from app.modules.artifacts.api.submission_cleanup import (
    SubmissionSourceCleanupProvider, SubmissionSourceRemoval, UnsealedSubmissionSource,
)
from app.modules.artifacts.intake.cleanup import MAXIMUM_CLEANUP_LEASE, SubmissionSourceCleanupOwner
from app.modules.artifacts.intake.repository import IntakeCustodyConflict


class SubmissionSourceCleanupExecution:
    """One operation per invocation; uncertain outcomes retain durable charges."""

    def __init__(self, sessions, *, tasks, authorization,
                 provider: SubmissionSourceCleanupProvider, lease_duration: timedelta):
        if type(lease_duration) is not timedelta or not timedelta(0) < lease_duration <= MAXIMUM_CLEANUP_LEASE:
            raise ValueError("source cleanup lease is invalid")
        self._sessions, self._tasks, self._authorization = sessions, tasks, authorization
        self._provider, self._duration = provider, lease_duration

    @asynccontextmanager
    async def _root(self):
        session = self._sessions()
        authority = self._authorization(session)
        try:
            await session.begin()
            yield SubmissionSourceCleanupOwner(session, self._tasks(session), authority)
            # If acknowledgement is lost, propagate uncertainty and retain the
            # same claim ID for replay. Never proceed to deletion on that path.
            await await_completion_preserving_cancellation(session.commit())
        finally:
            authority.close()
            await await_completion_preserving_cancellation(session.close())

    async def run(self, operation_id: UUID, claim_id: UUID) -> None:
        async with self._root() as owner:
            claim = await owner.claim(operation_id, claim_id, lease_duration=self._duration)
            upload = None if claim.confirmed else await owner.upload_for_claim(claim)
        if claim.confirmed:
            return
        expected = claim.observed_source or claim.source
        if claim.observed_source is not None:
            observed = await self._provider.remove(claim.observed_source, upload.upload)
        elif isinstance(claim.source, UnsealedSubmissionSource):
            # No initiation receipt means no provider call was ever authorized.
            observed = (SubmissionSourceRemoval(claim.source, True, True, True)
                        if claim.source.upload_fence is None else await self._provider.remove_unsealed(upload))
        else:
            observed = await self._provider.remove(claim.source, upload)
        if type(observed) is not SubmissionSourceRemoval or observed.source != expected:
            raise IntakeCustodyConflict("source_cleanup_observation_mismatch")
        if observed.observed_source is not None:
            if claim.observed_source is not None or not isinstance(claim.source, UnsealedSubmissionSource):
                raise IntakeCustodyConflict("source_cleanup_observation_mismatch")
            async with self._root() as owner:
                await owner.record_completion_observation(claim, observed.observed_source)
            raise IntakeCustodyConflict("source_cleanup_recent_completion")
        async with self._root() as owner:
            await owner.confirm(claim, object_absent=observed.object_absent,
                                writes_settled=observed.writes_settled,
                                parts_absent=observed.parts_absent)
