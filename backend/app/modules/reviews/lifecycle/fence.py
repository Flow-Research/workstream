"""The one REV mutation lock, retained until the caller ends its root transaction."""

import hashlib
from contextlib import asynccontextmanager
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import literal_column, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reviews.api.lifecycle import (
    JointLifecycleControlFacts,
    JointLifecyclePhase,
    JointLifecycleUnavailable,
)
from app.modules.reviews.lifecycle.models import JointLifecycleReleaseControl

# Stable across processes and future transition writers; not derived from requests.
JOINT_LIFECYCLE_LOCK_KEY = int.from_bytes(
    hashlib.sha256(b"workstream.review.joint_lifecycle_mutation").digest()[:8],
    "big",
    signed=True,
)


class PostgresJointLifecycleMutationFence:
    """Acquire advisory then controller-row locks without owning commit or AUTH."""

    def __init__(self, session: AsyncSession) -> None:
        """Use the caller's session for all fence and later participant work."""
        self._session = session

    async def observe_generation(self) -> int:
        """Read only the current generation, including stopped and genesis states."""
        with self._session.no_autoflush:
            generation = await self._session.scalar(
                select(JointLifecycleReleaseControl.generation).where(
                    JointLifecycleReleaseControl.singleton.is_(True)
                )
            )
        if type(generation) is not int or not 0 <= generation <= 9_223_372_036_854_775_807:
            raise JointLifecycleUnavailable("lifecycle controller missing or malformed")
        return generation

    @asynccontextmanager
    async def hold(self, expected_generation: int):
        """Issue a root-bound view after the sole controller lock acquisition."""
        facts = await self.acquire(expected_generation)
        async with _held_fence(self._session, facts) as held:
            yield held

    @asynccontextmanager
    async def hold_current(self):
        """Read the actual generation under REV custody before caller AUTH locks."""
        facts = await self.lock_controller()
        async with _held_fence(self._session, facts) as held:
            yield facts, held

    async def acquire(self, expected_generation: int) -> JointLifecycleControlFacts:
        """Return current locked scalar facts only for the expected generation."""
        if type(expected_generation) is not int or not 0 <= expected_generation <= 9_223_372_036_854_775_807:
            raise JointLifecycleUnavailable("lifecycle requires an exact generation")
        facts = await self.lock_controller()
        if facts.generation != expected_generation:
            raise JointLifecycleUnavailable("lifecycle controller missing or generation changed")
        return facts

    async def require_fulfillment_source(self, expected_generation: int, source_instance_id: UUID) -> None:
        """Match the configured source under the caller's canonical root fence."""
        facts = await self.acquire(expected_generation)
        await _require_fulfillment_source(self._session, facts, source_instance_id)

    async def lock_controller(self) -> JointLifecycleControlFacts:
        """Lock before transition history lookup; this never admits a mutation."""
        transaction = self._session.get_transaction()
        if (
            transaction is None
            or not transaction.is_active
            or self._session.in_nested_transaction()
        ):
            raise JointLifecycleUnavailable(
                "lifecycle requires a root transaction and exact generation"
            )
        connection = await self._session.connection()
        if connection.in_nested_transaction():
            raise JointLifecycleUnavailable("lifecycle requires a root database transaction")
        # SQLAlchemy cannot observe raw-SQL savepoints. PostgreSQL only exports
        # snapshots at the root, even after prior AUTH/idempotency queries.
        # Discard the token; PostgreSQL owns cleanup at caller transaction end.
        try:
            await self._session.execute(text("SELECT pg_catalog.pg_export_snapshot()"))
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) != "25001":
                raise
            raise JointLifecycleUnavailable("lifecycle requires a root database transaction") from exc
        await self._session.execute(
            text("SELECT pg_catalog.pg_advisory_xact_lock(:key)"),
            {"key": JOINT_LIFECYCLE_LOCK_KEY},
        )
        # Scalar selection cannot reuse a stale ORM identity-map instance.
        row = (
            await self._session.execute(
                select(
                    JointLifecycleReleaseControl.id,
                    JointLifecycleReleaseControl.phase,
                    JointLifecycleReleaseControl.generation,
                    literal_column(
                        "public.joint_lifecycle_new_effects_enabled("
                        "joint_lifecycle_release_control)"
                    ).label("new_effects_enabled"),
                    JointLifecycleReleaseControl.created_at,
                )
                .where(JointLifecycleReleaseControl.singleton.is_(True))
                .with_for_update()
            )
        ).one_or_none()
        if row is None:
            raise JointLifecycleUnavailable("lifecycle controller missing or generation changed")
        try:
            return JointLifecycleControlFacts(
                singleton_id=row.id,
                phase=JointLifecyclePhase(row.phase),
                generation=row.generation,
                new_effects_enabled=row.new_effects_enabled,
                created_at=row.created_at,
            )
        except (ValueError, ValidationError) as exc:
            raise JointLifecycleUnavailable("lifecycle controller malformed") from exc


@asynccontextmanager
async def _held_fence(session: AsyncSession, facts: JointLifecycleControlFacts):
    """One capability lifetime for current and expected-generation acquisition."""
    held = _HeldLifecycleFence(session, facts)
    try:
        yield held
    finally:
        held.close()


class _HeldLifecycleFence:
    """REV-owned custody view; checking it never acquires a controller lock."""

    def __init__(self, session: AsyncSession, facts: JointLifecycleControlFacts):
        """Bind retained lifecycle facts to the exact session and root transaction."""
        self._session = session
        self._transaction = session.sync_session.get_transaction()
        self._facts = facts
        self._closed = False

    def close(self) -> None:
        """Invalidate the view when the owning fence context exits."""
        self._closed = True

    async def require_fulfillment_source(self, expected_generation: int, source_instance_id: UUID) -> None:
        """Retain closed/nested/replaced-root denial before reading the anchor."""
        facts = await self.acquire(expected_generation)
        await _require_fulfillment_source(self._session, facts, source_instance_id)

    async def acquire(self, expected_generation: int) -> JointLifecycleControlFacts:
        """Validate original root custody without reacquiring the controller lock."""
        if (
            self._closed
            or type(expected_generation) is not int
            or expected_generation != self._facts.generation
            or self._session.sync_session.get_transaction() is not self._transaction
            or self._transaction is None
            or not self._transaction.is_active
            or self._session.in_nested_transaction()
        ):
            raise JointLifecycleUnavailable("held lifecycle custody is unavailable")
        connection = await self._session.connection()
        if connection.in_nested_transaction():
            raise JointLifecycleUnavailable("held lifecycle requires a root transaction")
        try:
            # Raw SAVEPOINT is invisible to SQLAlchemy; this adds no row lock.
            await self._session.execute(text("SELECT pg_catalog.pg_export_snapshot()"))
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) != "25001":
                raise
            self.close()
            raise JointLifecycleUnavailable("held lifecycle requires a root transaction") from exc
        return self._facts


async def _require_fulfillment_source(
    session: AsyncSession, facts: JointLifecycleControlFacts, source_instance_id: UUID,
) -> None:
    bound = await session.scalar(select(
        JointLifecycleReleaseControl.fulfillment_source_instance_id,
    ).where(JointLifecycleReleaseControl.id == facts.singleton_id))
    if not isinstance(source_instance_id, UUID) or source_instance_id.version != 7 or bound != source_instance_id:
        raise JointLifecycleUnavailable("fulfillment source differs from lifecycle activation")
