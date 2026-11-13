"""Durable selected PRE reservation and TASK-first lease/finalization custody."""

from __future__ import annotations

import threading
from dataclasses import replace
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.modules.artifacts.api.submission_intake import SubmissionIntakePreSourcePort
from app.modules.checkers.api.selected_pre_submit import (
    PreparedSelectedPreSubmitExecution,
    PreparedSelectedPreSubmitFinalization,
    SelectedPreSubmitCompletion,
    SelectedPreSubmitCurrentFacts,
    SelectedPreSubmitExecuteFacts,
    SelectedPreSubmitExecutionFacts,
    SelectedPreSubmitInvocationReceipt,
    SelectedPreSubmitFinalizeFacts,
    SelectedPreSubmitLeaseFacts,
    SelectedPreSubmitReservationFacts,
    SelectedPreSubmitRequestConflict,
    SelectedPreSubmitTerminalFacts,
    SelectedPreSubmitUnavailable,
)
from app.modules.checkers.models import SelectedPreSubmitRun
from app.modules.checkers.selected_pre_submit_records import matches_source_request, matches_terminal


class SelectedPreSubmitTaskGuard(Protocol):
    """TASK owns current contributor/assignment/policy checks before CHECKERS locks."""

    async def lock_selected_pre_submit_scope(
        self, reservation: SelectedPreSubmitReservationFacts
    ) -> None:
        """Lock and validate exact current TASK scope through caller commit."""


_CAPABILITY_SEAL = object()


class SelectedPreSubmitAdmissionCapability:
    """One-use completed-pass authority minted inside the finalization root."""

    __slots__ = (
        "_consumed",
        "_owner",
        "_seal",
        "_lock",
        "run_id",
        "terminal_digest",
        "attempt_id",
        "prepared_generation_id",
        "archive_sha256",
        "semantic_manifest_sha256",
    )

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("selected PRE admission capabilities are coordinator-issued")

    @classmethod
    def _issued(
        cls,
        *,
        owner: SelectedPreSubmitCoordinator,
        run_id: UUID,
        terminal: SelectedPreSubmitTerminalFacts,
    ) -> SelectedPreSubmitAdmissionCapability:
        reservation = terminal.lease.reservation
        value = object.__new__(cls)
        value._owner = owner
        value._seal = _CAPABILITY_SEAL
        value._lock = threading.Lock()
        value._consumed = False
        value.run_id = run_id
        value.terminal_digest = terminal.terminal_digest
        value.attempt_id = reservation.attempt_id
        value.prepared_generation_id = reservation.prepared_generation_id
        value.archive_sha256 = reservation.archive_sha256
        value.semantic_manifest_sha256 = reservation.semantic_manifest_sha256
        return value

    def consume(
        self,
        *,
        run_id: UUID,
        terminal_digest: str,
        attempt_id: UUID,
        prepared_generation_id: UUID,
        archive_sha256: str,
        semantic_manifest_sha256: str,
    ) -> UUID:
        """Consume only for the exact finalized run and still-live prepared bytes."""
        with self._lock:
            if (
                self._seal is not _CAPABILITY_SEAL
                or self._consumed
                or self._owner._capability is not self
                or (
                    run_id,
                    terminal_digest,
                    attempt_id,
                    prepared_generation_id,
                    archive_sha256,
                    semantic_manifest_sha256,
                )
                != (
                    self.run_id,
                    self.terminal_digest,
                    self.attempt_id,
                    self.prepared_generation_id,
                    self.archive_sha256,
                    self.semantic_manifest_sha256,
                )
            ):
                raise SelectedPreSubmitUnavailable(
                    "selected_pre_submit_admission_unavailable"
                )
            self._consumed = True
            self._owner._capability = None
            return self.run_id


class SelectedPreSubmitExecutionCapability:
    """One-use authority for the committed lease's process-local ART callback."""

    __slots__ = ("_consumed", "_owner", "_seal", "_lock", "run_id", "lease")

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("selected PRE execution capabilities are coordinator-issued")

    @classmethod
    def _issued(
        cls,
        *,
        owner: SelectedPreSubmitCoordinator,
        run_id: UUID,
        lease: SelectedPreSubmitLeaseFacts,
    ) -> SelectedPreSubmitExecutionCapability:
        value = object.__new__(cls)
        value._owner = owner
        value._seal = _CAPABILITY_SEAL
        value._lock = threading.Lock()
        value._consumed = False
        value.run_id = run_id
        value.lease = lease
        return value

    def consume(
        self,
        *,
        run_id: UUID,
        lease: SelectedPreSubmitLeaseFacts,
    ) -> SelectedPreSubmitLeaseFacts:
        """Consume only for the exact committed run generation and request facts."""
        with self._lock:
            if (
                self._seal is not _CAPABILITY_SEAL
                or self._consumed
                or self._owner._execution_capability is not self
                or run_id != self.run_id
                or lease != self.lease
            ):
                raise SelectedPreSubmitUnavailable(
                    "selected_pre_submit_execution_unavailable"
                )
            self._consumed = True
            self._owner._execution_capability = None
            return self.lease


def _require_root(session: AsyncSession) -> None:
    transaction = session.sync_session.get_transaction()
    if (
        transaction is None
        or not transaction.is_active
        or session.in_nested_transaction()
    ):
        raise RuntimeError("selected PRE coordination requires one root transaction")




class SelectedPreSubmitCoordinator:
    """Reserve, lease and finalize one selected PRE run in caller-owned roots."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        tasks: SelectedPreSubmitTaskGuard,
        sources: SubmissionIntakePreSourcePort,
    ) -> None:
        self._session = session
        self._tasks = tasks
        self._sources = sources
        self._capability: SelectedPreSubmitAdmissionCapability | None = None
        self._execution_capability: SelectedPreSubmitExecutionCapability | None = None

    async def read_current(
        self, facts: SelectedPreSubmitReservationFacts
    ) -> SelectedPreSubmitCurrentFacts | None:
        """Lock TASK before reading and validating one actor/key CHECKERS row."""
        _require_root(self._session)
        if type(facts) is not SelectedPreSubmitReservationFacts:
            raise TypeError("selected PRE reservation facts are invalid")
        await self._lock_source(facts)
        row = await self._session.scalar(
            select(SelectedPreSubmitRun)
            .where(
                SelectedPreSubmitRun.actor_profile_id
                == str(facts.actor_profile_id),
                SelectedPreSubmitRun.idempotency_key
                == str(facts.idempotency_key),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            return None
        if row.request_json.get("schema_version") != "workstream.selected_pre_submit_reservation.v2":
            raise SelectedPreSubmitRequestConflict("selected_pre_submit_request_conflict")
        if row.terminal_json is not None and row.terminal_json.get("schema_version") != "workstream.selected_pre_submit_terminal.v3":
            raise SelectedPreSubmitRequestConflict("selected_pre_submit_request_conflict")
        try:
            stored = SelectedPreSubmitReservationFacts.from_canonical_body(
                row.request_json
            )
            normalized = replace(
                facts,
                attempt_id=stored.attempt_id,
            )
            terminal = (
                SelectedPreSubmitTerminalFacts.from_canonical_body(row.terminal_json)
                if row.terminal_json is not None
                else None
            )
            terminal_matches = matches_terminal(row, stored, terminal)
        except (TypeError, ValueError):
            raise SelectedPreSubmitUnavailable(
                "selected_pre_submit_stored_facts_invalid"
            ) from None
        if (
            normalized != stored
            or not matches_source_request(row, stored)
            or row.request_digest != stored.request_digest
            or not terminal_matches
        ):
            raise SelectedPreSubmitRequestConflict(
                "selected_pre_submit_request_conflict"
            )
        return SelectedPreSubmitCurrentFacts(
            run_id=UUID(row.id),
            reservation=stored,
            status=row.status,
            terminal=terminal,
        )

    async def read_accepted_terminal(self, *, run_id: UUID, source_operation_id: UUID,
                                     terminal_digest: str) -> SelectedPreSubmitTerminalFacts:
        """Read exact retained v3 evidence; ART independently owns accepted custody."""
        _require_root(self._session)
        row = await self._session.get(SelectedPreSubmitRun, str(run_id))
        if (row is None or row.source_operation_id != str(source_operation_id)
                or row.status != "completed" or row.eligible is not True
                or row.terminal_digest != terminal_digest or row.execute_evidence_id is None
                or row.finalize_evidence_id is None
                or row.request_json.get("schema_version") != "workstream.selected_pre_submit_reservation.v2"
                or row.terminal_json.get("schema_version") != "workstream.selected_pre_submit_terminal.v3"):
            raise SelectedPreSubmitUnavailable("selected_pre_submit_stored_facts_invalid")
        try:
            request = SelectedPreSubmitReservationFacts.from_canonical_body(row.request_json)
            terminal = SelectedPreSubmitTerminalFacts.from_canonical_body(row.terminal_json)
            if not matches_source_request(row, request) or not matches_terminal(row, request, terminal):
                raise ValueError("retained PRE differs")
        except (TypeError, ValueError):
            raise SelectedPreSubmitUnavailable("selected_pre_submit_stored_facts_invalid") from None
        await self._session.execute(text("SELECT public.require_selected_pre_invocation(r) "
            "FROM public.selected_pre_submit_runs r WHERE id=:id"), {"id": row.id})
        return terminal

    async def lock_acceptance(
        self, *, run_id: UUID, facts: SelectedPreSubmitReservationFacts, terminal_digest: str,
    ) -> SelectedPreSubmitTerminalFacts:
        """Lock an exact current eligible terminal for the caller's T4 transaction.

        Unlike ordinary actor/key replay, acceptance cannot normalize another run
        identity. The ART accepted reference consumes this evidence atomically;
        this read neither mutates immutable PRE facts nor issues a capability.
        """
        if type(facts) is not SelectedPreSubmitReservationFacts or facts.attempt_id != run_id:
            raise SelectedPreSubmitRequestConflict("selected_pre_submit_request_conflict")
        current = await self.read_current(facts)
        if (current is None or current.run_id != run_id or current.reservation != facts
                or current.status != "completed" or current.terminal is None
                or current.terminal.terminal_digest != terminal_digest
                or current.terminal.execution is None or current.terminal.execution.eligible is not True
                or current.terminal.invocation_receipt is None):
            raise SelectedPreSubmitUnavailable("selected_pre_submit_acceptance_unavailable")
        row = await self._session.get(SelectedPreSubmitRun, str(run_id))
        if row.execute_evidence_id is None or row.finalize_evidence_id is None:
            raise SelectedPreSubmitUnavailable("selected_pre_submit_acceptance_unavailable")
        return current.terminal

    async def reserve(self, facts: SelectedPreSubmitReservationFacts) -> UUID:
        """Acquire TASK custody before the CHECKERS key and exact request row."""
        _require_root(self._session)
        if type(facts) is not SelectedPreSubmitReservationFacts:
            raise TypeError("selected PRE reservation facts are invalid")
        await self._lock_source(facts)
        await self._session.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {
                "key": (
                    "checkers:selected-pre:"
                    + str(facts.actor_profile_id)
                    + ":"
                    + str(facts.idempotency_key)
                )
            },
        )
        row = await self._session.scalar(
            select(SelectedPreSubmitRun)
            .where(
                SelectedPreSubmitRun.actor_profile_id
                == str(facts.actor_profile_id),
                SelectedPreSubmitRun.idempotency_key
                == str(facts.idempotency_key),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is not None:
            if not matches_source_request(row, facts):
                raise SelectedPreSubmitUnavailable("selected_pre_submit_request_conflict")
            return UUID(row.id)
        row = SelectedPreSubmitRun(
            id=str(facts.attempt_id),
            actor_profile_id=str(facts.actor_profile_id),
            identity_link_id=str(facts.identity_link_id),
            project_id=str(facts.project_id),
            task_id=str(facts.task_id),
            assignment_id=str(facts.assignment_id),
            idempotency_key=str(facts.idempotency_key),
            source_operation_id=str(facts.source.location.operation_id),
            prepared_generation_id=None,
            request_json=facts.canonical_body(),
            request_digest=facts.request_digest,
            policy_sha256=facts.policy_sha256,
            default_behavior_sha256=facts.default_behavior_sha256,
            default_input_sha256=None,
            archive_sha256=facts.archive_sha256,
            archive_byte_count=facts.archive_byte_count,
            semantic_manifest_sha256=None,
            execution_budget_ms=facts.execution_budget_ms,
            status="queued",
            lease_generation=0,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError:
            raise SelectedPreSubmitUnavailable("selected_pre_submit_request_conflict") from None
        return facts.attempt_id

    async def claim(
        self,
        *,
        run_id: UUID,
        facts: SelectedPreSubmitReservationFacts,
        authority: PreparedSelectedPreSubmitExecution,
    ) -> SelectedPreSubmitLeaseFacts:
        """Issue one database-timed lease after fresh TASK and execute authority."""
        row = await self._lock(run_id=run_id, facts=facts)
        if row.status != "queued":
            raise SelectedPreSubmitUnavailable("selected_pre_submit_lease_unavailable")
        now = await self._session.scalar(select(func.clock_timestamp()))
        assert now is not None
        if now >= facts.pre_deadline_at:
            raise SelectedPreSubmitUnavailable("selected_pre_submit_deadline_expired")
        lease = SelectedPreSubmitLeaseFacts(
            reservation=facts,
            lease_id=new_record_id(),
            lease_generation=row.lease_generation + 1,
            lease_expires_at=min(
                facts.pre_deadline_at, now + timedelta(milliseconds=facts.execution_budget_ms)
            ),
        )
        execute_facts = SelectedPreSubmitExecuteFacts(lease)
        evidence = await authority.consume(execute_facts)
        if evidence.facts_digest != execute_facts.facts_digest:
            raise SelectedPreSubmitUnavailable("selected_pre_submit_execute_evidence_invalid")
        row.lease_id = str(lease.lease_id)
        row.lease_generation = lease.lease_generation
        row.lease_expires_at = lease.lease_expires_at
        row.execute_evidence_id = str(evidence.evidence_id)
        row.started_at = now
        row.status = "running"
        await self._session.flush()
        return lease

    async def committed_execution(
        self,
        *,
        run_id: UUID,
        lease: SelectedPreSubmitLeaseFacts,
    ) -> SelectedPreSubmitExecutionCapability:
        """Mint execution authority only after a fresh root observes the committed lease."""
        if self._session.in_transaction():
            raise RuntimeError("selected PRE execution requires a committed lease")
        async with self._session.begin():
            row = await self._lock(run_id=run_id, facts=lease.reservation)
            if (
                row.status != "running"
                or row.lease_id != str(lease.lease_id)
                or row.lease_generation != lease.lease_generation
                or row.lease_expires_at != lease.lease_expires_at
            ):
                raise SelectedPreSubmitUnavailable(
                    "selected_pre_submit_execution_unavailable"
                )
        capability = SelectedPreSubmitExecutionCapability._issued(
            owner=self,
            run_id=run_id,
            lease=lease,
        )
        self._execution_capability = capability
        return capability

    async def read_expired_lease(
        self, *, run_id: UUID, facts: SelectedPreSubmitReservationFacts
    ) -> SelectedPreSubmitLeaseFacts:
        """Discover an expired lease without reconstructing its ART capability."""
        row = await self._lock(run_id=run_id, facts=facts)
        now = await self._session.scalar(select(func.clock_timestamp()))
        if (
            now is None
            or row.status != "running"
            or row.lease_id is None
            or row.lease_expires_at is None
            or row.lease_expires_at >= now
        ):
            raise SelectedPreSubmitUnavailable(
                "selected_pre_submit_expired_lease_unavailable"
            )
        return SelectedPreSubmitLeaseFacts(
            reservation=facts,
            lease_id=UUID(row.lease_id),
            lease_generation=row.lease_generation,
            lease_expires_at=row.lease_expires_at,
        )

    async def finalize(
        self,
        *,
        run_id: UUID,
        lease: SelectedPreSubmitLeaseFacts,
        authority: PreparedSelectedPreSubmitFinalization,
        execution: SelectedPreSubmitExecutionFacts | None,
        invocation_receipt: SelectedPreSubmitInvocationReceipt | None,
        infrastructure_failure_code: str | None,
    ) -> SelectedPreSubmitCompletion:
        """Fence the lease and persist one exact terminal value under fresh TASK custody."""
        facts = lease.reservation
        row = await self._lock(run_id=run_id, facts=facts)
        if (
            row.status != "running"
            or row.lease_id != str(lease.lease_id)
            or row.lease_generation != lease.lease_generation
            or row.lease_expires_at != lease.lease_expires_at
        ):
            raise SelectedPreSubmitUnavailable("selected_pre_submit_finalization_unavailable")
        completed_at = await self._session.scalar(select(func.clock_timestamp()))
        assert completed_at is not None and row.started_at is not None
        if execution is not None and completed_at > lease.lease_expires_at:
            raise SelectedPreSubmitUnavailable("selected_pre_submit_lease_expired")
        outcome = "completed" if execution is not None else "infrastructure_failed"
        finalize_facts = SelectedPreSubmitFinalizeFacts(
            lease=lease,
            execution=execution,
            invocation_receipt=invocation_receipt,
            infrastructure_failure_code=infrastructure_failure_code,
        )
        evidence = await authority.consume(finalize_facts)
        if evidence.facts_digest != finalize_facts.facts_digest:
            raise SelectedPreSubmitUnavailable("selected_pre_submit_finalize_evidence_invalid")
        terminal = SelectedPreSubmitTerminalFacts(
            lease=lease,
            outcome=outcome,
            execution=execution,
            invocation_receipt=invocation_receipt,
            infrastructure_failure_code=infrastructure_failure_code,
            queued_at=row.queued_at,
            started_at=row.started_at,
            completed_at=completed_at,
        )
        row.status = outcome
        row.terminal_json = terminal.canonical_body()
        row.terminal_digest = terminal.terminal_digest
        row.eligible = execution.eligible if execution is not None else None
        row.finalize_evidence_id = str(evidence.evidence_id)
        row.completed_at = completed_at
        await self._session.flush()
        # Source-bound evidence cannot mint the removed prepared-bundle handoff.
        # Acceptance is the separate fresh-fenced T4 transaction.
        return SelectedPreSubmitCompletion(terminal=terminal, capability=None)

    async def _lock_source(self, facts: SelectedPreSubmitReservationFacts) -> None:
        """Hold TASK then exact live ART custody before any CHECKERS row lock."""
        await self._tasks.lock_selected_pre_submit_scope(facts)
        current = await self._sources.lock_pre_source(
            source=facts.source, lease_id=facts.foreground_lease_id,
            generation=facts.foreground_lease_generation,
        )
        if (
            current.source != facts.source
            or current.project_id != facts.project_id
            or current.task_id != facts.task_id
            or current.assignment_id != facts.assignment_id
            or current.actor_profile_id != facts.actor_profile_id
            or current.identity_link_id != facts.identity_link_id
            or current.metadata_sha256 != facts.metadata_sha256
            or current.locked_context_sha256 != facts.locked_context_sha256
            or current.lease_id != facts.foreground_lease_id
            or current.lease_generation != facts.foreground_lease_generation
            or current.pre_deadline_at != facts.pre_deadline_at
        ):
            raise SelectedPreSubmitUnavailable("selected_pre_submit_source_changed")

    async def _lock(
        self, *, run_id: UUID, facts: SelectedPreSubmitReservationFacts
    ) -> SelectedPreSubmitRun:
        _require_root(self._session)
        if not isinstance(run_id, UUID) or type(facts) is not SelectedPreSubmitReservationFacts:
            raise SelectedPreSubmitUnavailable("selected_pre_submit_run_unavailable")
        await self._lock_source(facts)
        row = await self._session.scalar(
            select(SelectedPreSubmitRun)
            .where(
                SelectedPreSubmitRun.id == str(run_id),
                SelectedPreSubmitRun.project_id == str(facts.project_id),
                SelectedPreSubmitRun.task_id == str(facts.task_id),
                SelectedPreSubmitRun.assignment_id == str(facts.assignment_id),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None or not matches_source_request(row, facts):
            raise SelectedPreSubmitUnavailable("selected_pre_submit_run_unavailable")
        return row


__all__ = (
    "SelectedPreSubmitAdmissionCapability",
    "SelectedPreSubmitCompletion",
    "SelectedPreSubmitCoordinator",
    "SelectedPreSubmitExecutionCapability",
    "SelectedPreSubmitTaskGuard",
)
