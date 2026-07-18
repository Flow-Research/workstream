"""PostgreSQL statements for durable API controls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

UPSERT_COUNTER = text(
    """
    with clock as (select statement_timestamp() as db_now)
    insert into api_rate_control_counters as counters (
        control_scope, key_digest, window_started_at, window_expires_at,
        request_count, updated_at
    )
    select :control_scope, :key_digest, db_now,
           db_now + make_interval(secs => :window_seconds), 1, db_now
    from clock
    on conflict (control_scope, key_digest) do update set
        window_started_at = case
            when counters.window_expires_at <= (select db_now from clock)
            then (select db_now from clock) else counters.window_started_at end,
        window_expires_at = case
            when counters.window_expires_at <= (select db_now from clock)
            then (select db_now from clock) + make_interval(secs => :window_seconds)
            else counters.window_expires_at end,
        request_count = case
            when counters.window_expires_at <= (select db_now from clock) then 1
            when counters.request_count = 9223372036854775807
            then counters.request_count else counters.request_count + 1 end,
        updated_at = (select db_now from clock)
    returning (select db_now from clock) as db_now, window_started_at,
              window_expires_at, request_count
    """
)

PRUNE_EXPIRED = text(
    """
    with expired as (
        select control_scope, key_digest
        from api_rate_control_counters
        where window_expires_at <= statement_timestamp()
          and not (control_scope = :control_scope and key_digest = :key_digest)
        order by window_expires_at
        limit :batch_size
        for update skip locked
    )
    delete from api_rate_control_counters as counters
    using expired
    where counters.control_scope = expired.control_scope
      and counters.key_digest = expired.key_digest
    """
)


@dataclass(frozen=True)
class ConsumedCounter:
    """Database-time result of one atomic counter consumption."""

    db_now: datetime
    window_started_at: datetime
    window_expires_at: datetime
    request_count: int


class ApiRateControlRepository:
    """Consume and prune counters inside a caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def consume(
        self, control_scope: str, key_digest: bytes, window_seconds: int
    ) -> ConsumedCounter:
        """Atomically insert, reset, increment, or saturate one counter."""
        row = (
            await self._session.execute(
                UPSERT_COUNTER,
                {
                    "control_scope": control_scope,
                    "key_digest": key_digest,
                    "window_seconds": window_seconds,
                },
            )
        ).one()
        return ConsumedCounter(*row)

    async def prune_expired(
        self, control_scope: str, key_digest: bytes, *, batch_size: int
    ) -> None:
        """Delete a bounded batch of other expired pseudonymous rows."""
        await self._session.execute(
            PRUNE_EXPIRED,
            {
                "control_scope": control_scope,
                "key_digest": key_digest,
                "batch_size": batch_size,
            },
        )
