"""Authorized sealed-source reads and one foreground PRE execution."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cancellation import await_cancellation_resistant
from app.interfaces.artifacts import ArtifactStore, ArtifactStoreError
from app.interfaces.external_checker_execution import (
    ExternalPreSubmitSourceGrant, MAXIMUM_PRE_SOURCE_CHUNK_BYTES,
)
from app.modules.artifacts.api.submission_intake import (
    PreSubmitSourceReadFacts, SubmissionIntakePreSourcePort,
)
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.artifacts.intake.repository import IntakeCustodyConflict
from app.modules.tasks.api.submission_context import TaskSubmissionContextUnavailable
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitAuthorityPort, SelectedPreSubmitCompletion,
    SelectedPreSubmitCoordinationPort, SelectedPreSubmitExecutionAuthority,
    SelectedPreSubmitExecutionFacts, SelectedPreSubmitFinalizeFacts,
    SelectedPreSubmitInfrastructureUnavailable, SelectedPreSubmitLeaseFacts,
    SelectedPreSubmitReservationFacts,
)


class PreSubmitSourceReadAuthorization(Protocol):
    """The fixed ART materializer's distinct transaction-bound AUTH boundary."""

    async def prepare(self, *, facts: PreSubmitSourceReadFacts, idempotency_key: UUID) -> object: ...
    async def consume(self, *, prepared_authorization: object, facts: PreSubmitSourceReadFacts) -> None: ...
    def close(self) -> None: ...


class PreSubmitProcessor(Protocol):
    """CHECKERS processor composed through its existing adapter factory."""

    async def process(self, grant: ExternalPreSubmitSourceGrant) -> SelectedPreSubmitExecutionFacts: ...


class PreSubmitExecutionFactory(Protocol):
    """Keep the CHECKERS implementation out of ART's owner imports."""

    def build(self, lease: SelectedPreSubmitLeaseFacts) -> PreSubmitProcessor: ...


def source_read_facts(lease: SelectedPreSubmitLeaseFacts) -> PreSubmitSourceReadFacts:
    """Project the exact committed request and execution fence for ART AUTH."""
    reservation = lease.reservation
    return PreSubmitSourceReadFacts(
        source=reservation.source, project_id=reservation.project_id, task_id=reservation.task_id,
        assignment_id=reservation.assignment_id, actor_profile_id=reservation.actor_profile_id,
        identity_link_id=reservation.identity_link_id, metadata_sha256=reservation.metadata_sha256,
        locked_context_sha256=reservation.locked_context_sha256,
        foreground_lease_id=reservation.foreground_lease_id,
        foreground_lease_generation=reservation.foreground_lease_generation,
        pre_deadline_at=reservation.pre_deadline_at, run_id=reservation.attempt_id,
        request_digest=reservation.request_digest, policy_sha256=reservation.policy_sha256,
        execution_lease_id=lease.lease_id, execution_lease_generation=lease.lease_generation,
        execution_lease_expires_at=lease.lease_expires_at,
    )


class _PreSubmitSourceGrant:
    """One-use, nonserializable read issued only after its AUTH root commits."""

    def __init__(self, *args, **kwargs) -> None:
        raise TypeError("PRE source grants are issuer-owned")

    @classmethod
    def _issued(cls, issuer, lease, expires_at, deadline):
        value = object.__new__(cls)
        value._issuer, value._lease = issuer, lease
        value._expires_at, value._deadline = expires_at, deadline
        value._claimed = False
        value._revoked = False
        value._reader = None
        value._task = asyncio.current_task()
        return value

    def _require_current(self) -> None:
        if (asyncio.current_task() is not self._task
                or self._revoked or self._issuer._session.in_transaction()
                or asyncio.get_running_loop().time() >= self._deadline
                or datetime.now(UTC) >= self._expires_at):
            raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")

    def open_source(self, *, lease: SelectedPreSubmitLeaseFacts) -> AsyncGenerator[bytes, None]:
        """Consume once, then keep every provider read outside DB transactions."""
        self._require_current()
        if self._claimed or lease != self._lease:
            raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
        self._claimed = True
        self._reader = self._read()
        return self._reader

    async def _read(self) -> AsyncGenerator[bytes, None]:
        reader = None
        count = 0
        try:
            self._require_current()
            reader = self._issuer._store.open_source(
                self._lease.reservation.source, maximum_chunk_bytes=MAXIMUM_PRE_SOURCE_CHUNK_BYTES,
            )
            while True:
                self._require_current()
                try:
                    async with asyncio.timeout_at(self._deadline):
                        chunk = await anext(reader)
                except StopAsyncIteration:
                    break
                self._require_current()
                if type(chunk) is not bytes or not 0 < len(chunk) <= MAXIMUM_PRE_SOURCE_CHUNK_BYTES:
                    raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
                count += len(chunk)
                if count > self._lease.reservation.source.raw_byte_count:
                    raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
                yield chunk
            if count != self._lease.reservation.source.raw_byte_count:
                raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
        except (ArtifactStoreError, TimeoutError) as exc:
            raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable") from exc
        finally:
            if reader is not None:
                await await_cancellation_resistant(reader.aclose())


class SelectedPreSubmitSourceReads:
    """Authorize current TASK/ART source custody, then issue a committed read."""

    def __init__(
        self, *, session: AsyncSession, sources: SubmissionIntakePreSourcePort,
        authority: PreSubmitSourceReadAuthorization, store: ArtifactStore,
    ) -> None:
        self._session, self._sources, self._authority, self._store = session, sources, authority, store

    @asynccontextmanager
    async def issue(
        self, *, lease: SelectedPreSubmitLeaseFacts, execution_authority: SelectedPreSubmitExecutionAuthority,
    ) -> AsyncIterator[ExternalPreSubmitSourceGrant]:
        """Require committed CHECKERS authority and a fresh, separately authorized ART read."""
        if self._session.in_transaction():
            raise RuntimeError("PRE source issuance requires no transaction")
        checked = execution_authority.consume(run_id=lease.reservation.attempt_id, lease=lease)
        if checked != lease:
            raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
        facts = source_read_facts(lease)
        started = asyncio.get_running_loop().time()
        grant = None
        try:
            async with self._session.begin():
                handle = await self._authority.prepare(facts=facts, idempotency_key=facts.run_id)
                live = await self._sources.lock_pre_source(
                    source=facts.source, lease_id=facts.foreground_lease_id,
                    generation=facts.foreground_lease_generation,
                )
                names = ("source", "project_id", "task_id", "assignment_id", "actor_profile_id",
                         "identity_link_id", "metadata_sha256", "locked_context_sha256", "pre_deadline_at")
                if (any(getattr(live, name) != getattr(facts, name) for name in names)
                        or live.lease_id != facts.foreground_lease_id
                        or live.lease_generation != facts.foreground_lease_generation):
                    raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
                expires_at = min(live.lease_expires_at, lease.lease_expires_at, live.pre_deadline_at)
                now = await self._session.scalar(select(func.clock_timestamp()))
                if now is None or expires_at <= now:
                    raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
                deadline = started + (expires_at - now).total_seconds()
                await self._authority.consume(prepared_authorization=handle, facts=facts)
            # No grant exists if commit fails, including a lost acknowledgement.
            grant = _PreSubmitSourceGrant._issued(self, lease, expires_at, deadline)
            grant._require_current()
            yield grant
        except (ArtifactAuthorityDeniedError, IntakeCustodyConflict, TaskSubmissionContextUnavailable) as exc:
            raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable") from exc
        finally:
            try:
                if grant is not None:
                    grant._revoked = True
                    if grant._reader is not None:
                        await await_cancellation_resistant(grant._reader.aclose())
            finally:
                self._authority.close()


class SelectedPreSubmitExecutionService:
    """Claim, authorize source, execute once and finalize using short roots."""

    def __init__(
        self, *, session: AsyncSession, coordinator: SelectedPreSubmitCoordinationPort,
        authority: SelectedPreSubmitAuthorityPort, source_reads: SelectedPreSubmitSourceReads,
        execution: PreSubmitExecutionFactory,
    ) -> None:
        self._session, self._coordinator, self._authority = session, coordinator, authority
        self._source_reads, self._execution = source_reads, execution

    async def execute(self, *, reservation: SelectedPreSubmitReservationFacts) -> SelectedPreSubmitCompletion:
        """Use fresh fixed-service roots around one foreground source invocation."""
        run_id = reservation.attempt_id
        async with self._session.begin():
            async with self._authority.prepare_execution(reservation) as prepared:
                lease = await self._coordinator.claim(run_id=run_id, facts=reservation, authority=prepared)
        execution = None
        failure = None
        try:
            capability = await self._coordinator.committed_execution(run_id=run_id, lease=lease)
            async with self._source_reads.issue(lease=lease, execution_authority=capability) as grant:
                execution = await self._execution.build(lease).process(grant)
        except SelectedPreSubmitInfrastructureUnavailable as exc:
            failure = exc.code
        facts = SelectedPreSubmitFinalizeFacts(lease=lease, execution=execution, infrastructure_failure_code=failure)
        async with self._session.begin():
            async with self._authority.prepare_finalization(facts) as prepared:
                return await self._coordinator.finalize(
                    run_id=run_id, lease=lease, authority=prepared, execution=execution,
                    infrastructure_failure_code=failure,
                )


__all__ = ("SelectedPreSubmitExecutionService", "SelectedPreSubmitSourceReads", "source_read_facts")
