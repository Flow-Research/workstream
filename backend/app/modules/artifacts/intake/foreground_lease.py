"""Keep one foreground command owned; never resume, accept or release its source."""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import timedelta
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.cancellation import await_completion_preserving_cancellation
from app.modules.artifacts.intake.repository import IntakeCustodyConflict, SubmissionIntakeRepository
from app.modules.tasks.api.intake_custody import IntakeTaskCustodyPort

Result = TypeVar("Result")


class ForegroundIntakeLease:
    """Renew the pinned owner in short transactions beside its foreground work."""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession],
        tasks: Callable[[AsyncSession], IntakeTaskCustodyPort], *,
        lease_duration: timedelta, heartbeat_interval: timedelta,
    ) -> None:
        if (not isinstance(lease_duration, timedelta)
                or not isinstance(heartbeat_interval, timedelta)
                or not timedelta(0) < heartbeat_interval < lease_duration):
            raise ValueError("foreground heartbeat interval must be positive and shorter than lease duration")
        self._sessions, self._tasks = sessions, tasks
        self._duration = lease_duration
        self._interval = heartbeat_interval.total_seconds()

    async def _renew(self, operation_id: UUID, lease_id: UUID, generation: int) -> float:
        loop = asyncio.get_running_loop()
        started = loop.time()
        async with self._sessions.begin() as session:
            remaining = await SubmissionIntakeRepository(session, self._tasks(session)).heartbeat(
                operation_id, lease_id, generation, lease_duration=self._duration,
            )
        # Conservative: includes lock wait, flush and commit response, not host wall time.
        budget = remaining - (loop.time() - started)
        if budget <= 0:
            raise IntakeCustodyConflict("intake_owner_renewal_expired")
        return budget

    async def run(
        self, operation_id: UUID, lease_id: UUID, generation: int,
        command_factory: Callable[[UUID, UUID, int], Coroutine[Any, Any, Result]],
    ) -> Result:
        """Invoke once after committed renewal; drain all work before returning."""
        budget = await self._renew(operation_id, lease_id, generation)

        async def pulse() -> None:
            remaining = budget
            while True:
                await asyncio.sleep(min(self._interval, remaining / 2))
                remaining = await self._renew(operation_id, lease_id, generation)

        command = asyncio.create_task(command_factory(operation_id, lease_id, generation),
                                      name=f"submission-foreground:{operation_id}")
        renewal = asyncio.create_task(pulse(), name=f"submission-lease:{operation_id}")
        try:
            await asyncio.wait((command, renewal), return_when=asyncio.FIRST_COMPLETED)
            if command.done():
                return command.result()
            renewal.result()
            raise AssertionError("foreground renewal unexpectedly returned")
        finally:
            command.cancel()
            renewal.cancel()
            await await_completion_preserving_cancellation(
                asyncio.gather(command, renewal, return_exceptions=True),
            )
