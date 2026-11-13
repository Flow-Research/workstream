"""Read retained selected PRE runs without leasing or finalizing; the caller owns authority."""

from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitRunStatus, SelectedPreSubmitRunView,
    SelectedPreSubmitUnavailable, SelectedPreSubmitReservationFacts,
    SelectedPreSubmitTerminalFacts, HistoricalSourcePreSubmitTerminal, SelectedPreSubmitLeaseFacts,
)
from app.modules.checkers.api.historical_selected_pre_submit import (
    HistoricalSelectedPreSubmitReservation, HistoricalSelectedPreSubmitTerminal,
)
from app.modules.checkers.models import SelectedPreSubmitRun
from app.modules.checkers.selected_pre_submit_records import matches_source_request, matches_terminal


def _request_matches(row: SelectedPreSubmitRun, request: HistoricalSelectedPreSubmitReservation) -> bool:
    """Bind every v1 indexed identity to the retained canonical request."""
    identifiers = {
        "id": request.attempt_id, "actor_profile_id": request.actor_profile_id,
        "identity_link_id": request.identity_link_id, "project_id": request.project_id,
        "task_id": request.task_id, "assignment_id": request.assignment_id,
        "idempotency_key": request.idempotency_key,
        "prepared_generation_id": request.prepared_generation_id,
    }
    return (
        row.request_json == request.canonical_body()
        and row.request_digest == request.request_digest
        and all(UUID(str(getattr(row, key))) == value for key, value in identifiers.items())
        and all(getattr(row, key) == getattr(request, key) for key in (
            "policy_sha256", "default_behavior_sha256", "default_input_sha256",
            "archive_sha256", "archive_byte_count", "semantic_manifest_sha256",
            "execution_budget_ms",
        ))
    )


def _view(row: SelectedPreSubmitRun) -> SelectedPreSubmitRunView:
    """Decode each retained schema and bind it to the indexed row without issuing authority."""
    try:
        if (type(row.request_json) is not dict
                or (row.terminal_json is not None and type(row.terminal_json) is not dict)):
            raise ValueError("retained PRE body is invalid")
        if row.request_json.get("schema_version") == "workstream.selected_pre_submit_reservation.v1":
            request = HistoricalSelectedPreSubmitReservation.from_canonical_body(row.request_json)
            terminal = HistoricalSelectedPreSubmitTerminal.from_canonical_body(row.terminal_json) if row.terminal_json is not None else None
            request_matches = _request_matches(row, request)
        else:
            request = SelectedPreSubmitReservationFacts.from_canonical_body(row.request_json)
            if row.terminal_json is None:
                terminal = None
            elif row.terminal_json.get("schema_version") == "workstream.selected_pre_submit_terminal.v2":
                terminal = HistoricalSourcePreSubmitTerminal.from_canonical_body(row.terminal_json)
            else:
                terminal = SelectedPreSubmitTerminalFacts.from_canonical_body(row.terminal_json)
            request_matches = matches_source_request(row, request)
        if not request_matches or not matches_terminal(row, request, terminal):
            raise ValueError("retained PRE columns differ")
    except (KeyError, TypeError, ValueError):
        raise SelectedPreSubmitUnavailable("selected_pre_submit_stored_facts_invalid") from None
    return SelectedPreSubmitRunView(
        run_id=request.attempt_id, actor_profile_id=request.actor_profile_id,
        task_id=request.task_id, assignment_id=request.assignment_id, status=row.status,
        archive_sha256=request.archive_sha256, archive_byte_count=request.archive_byte_count,
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
