"""Read retained selected PRE runs without leasing or finalizing; the caller owns authority."""

from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitRunStatus, SelectedPreSubmitRunView, SelectedPreSubmitTerminalFacts,
    SelectedPreSubmitUnavailable,
)
from app.modules.checkers.models import SelectedPreSubmitRun


def _view(row: SelectedPreSubmitRun) -> SelectedPreSubmitRunView:
    """Revalidate one stored terminal body against its fixed columns."""
    try:
        terminal = (
            SelectedPreSubmitTerminalFacts.from_canonical_body(row.terminal_json)
            if row.terminal_json is not None else None
        )
    except (TypeError, ValueError):
        raise SelectedPreSubmitUnavailable("selected_pre_submit_stored_facts_invalid") from None
    if terminal is not None and (
        terminal.terminal_digest != row.terminal_digest
        or terminal.lease.reservation.attempt_id != UUID(str(row.id))
        or (terminal.execution is not None and terminal.execution.eligible != row.eligible)
    ):
        raise SelectedPreSubmitUnavailable("selected_pre_submit_stored_facts_invalid")
    return SelectedPreSubmitRunView(
        run_id=UUID(str(row.id)), actor_profile_id=UUID(str(row.actor_profile_id)),
        task_id=UUID(str(row.task_id)), assignment_id=UUID(str(row.assignment_id)), status=row.status,
        archive_sha256=row.archive_sha256, archive_byte_count=row.archive_byte_count,
        queued_at=row.queued_at, completed_at=row.completed_at, terminal=terminal,
    )


class SelectedPreSubmitRunReader:
    """Fixed columns and revalidated terminal bodies, newest first by ``(queued_at, id)``."""

    def __init__(self, session: AsyncSession) -> None:
        """Read in the caller's response transaction."""
        self._session = session

    async def _page(self, statement, limit, before):
        """Apply the descending keyset boundary and return one page plus whether more exist."""
        run = SelectedPreSubmitRun
        if before is not None:
            statement = statement.where(tuple_(run.queued_at, run.id) < (before[0], str(before[1])))
        rows = (await self._session.scalars(
            statement.order_by(run.queued_at.desc(), run.id.desc()).limit(limit + 1),
        )).all()
        return tuple(_view(row) for row in rows[:limit]), len(rows) > limit

    async def read_contributor_runs(self, *, actor_profile_id, task_id, run_id, limit, before):
        """One contributor's runs for one task, optionally one exact run."""
        run = SelectedPreSubmitRun
        statement = select(run).where(
            run.actor_profile_id == str(actor_profile_id), run.task_id == str(task_id),
        )
        if run_id is not None:
            statement = statement.where(run.id == str(run_id))
        return await self._page(statement, limit, before)

    async def read_project_runs(
        self, *, project_id: UUID, statuses: tuple[SelectedPreSubmitRunStatus, ...] | None,
        eligible: bool | None, limit: int, before,
    ):
        """Every contributor's runs in one project, filtered by stored status and eligibility."""
        run = SelectedPreSubmitRun
        statement = select(run).where(run.project_id == str(project_id))
        if statuses is not None:
            statement = statement.where(run.status.in_(statuses))
        if eligible is not None:
            statement = statement.where(run.eligible.is_(eligible))
        return await self._page(statement, limit, before)
