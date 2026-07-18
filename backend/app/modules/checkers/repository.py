"""Database access methods for checker runs and checker results."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.checkers.models import CheckerResult, CheckerRun


@dataclass(frozen=True)
class CheckerRunClaimState:
    """Minimal state used to fence an automatic checker-run claim."""

    status: str
    is_current_for_submission: bool
    trigger_source: str | None
    triggered_by: str | None
    triggered_by_subject: str | None
    triggered_by_issuer: str | None
    trigger_auth_source: str | None


class CheckerRepository:
    """Wraps SQLAlchemy persistence for checker records."""

    def __init__(self, session: AsyncSession) -> None:
        """Create a repository bound to one database session.

        Args:
            session: Async SQLAlchemy session for the current unit of work.
        """
        self._session = session

    async def add_run(self, checker_run: CheckerRun) -> CheckerRun:
        """Persist a checker run and its result rows.

        Args:
            checker_run: Checker run model with result rows attached.

        Returns:
            Persisted checker run with generated database fields refreshed.
        """
        self._session.add(checker_run)
        await self._session.flush()
        await self._session.refresh(checker_run)
        return checker_run

    async def get_run(self, checker_run_id: str) -> CheckerRun | None:
        """Load one checker run with result rows.

        Args:
            checker_run_id: Checker run id to load.

        Returns:
            Checker run when found; otherwise ``None``.
        """
        result = await self._session.execute(
            select(CheckerRun)
            .options(selectinload(CheckerRun.results))
            .where(CheckerRun.id == checker_run_id)
        )
        return result.scalar_one_or_none()

    async def mark_automatic_gate_enqueue_failed(
        self,
        *,
        checker_run_id: str,
        trigger_source: str,
        system_actor_id: str,
        system_issuer: str,
        auth_source: str,
        failure_code: str,
        failure_message: str,
        completed_at: datetime,
    ) -> bool:
        """Fail a queued current automatic gate after broker enqueue failure."""
        result = await self._session.execute(
            update(CheckerRun)
            .where(
                CheckerRun.id == checker_run_id,
                CheckerRun.status == "queued",
                CheckerRun.is_current_for_submission.is_(True),
                *self._automatic_gate_filters(
                    trigger_source=trigger_source,
                    system_actor_id=system_actor_id,
                    system_issuer=system_issuer,
                    auth_source=auth_source,
                ),
            )
            .values(
                status="failed",
                failure_code=failure_code,
                failure_message=failure_message,
                completed_at=completed_at,
            )
            .returning(CheckerRun.id)
        )
        return result.scalar_one_or_none() is not None

    async def requeue_failed_automatic_gate(
        self,
        *,
        checker_run_id: str,
        retryable_failure_codes: set[str],
        trigger_source: str,
        system_actor_id: str,
        system_issuer: str,
        auth_source: str,
        reset_trigger_reason: str,
    ) -> bool:
        """Move a failed current automatic gate back to queued."""
        result = await self._session.execute(
            update(CheckerRun)
            .where(
                CheckerRun.id == checker_run_id,
                CheckerRun.status == "failed",
                CheckerRun.is_current_for_submission.is_(True),
                CheckerRun.failure_code.in_(retryable_failure_codes),
                *self._automatic_gate_filters(
                    trigger_source=trigger_source,
                    system_actor_id=system_actor_id,
                    system_issuer=system_issuer,
                    auth_source=auth_source,
                ),
            )
            .values(
                status="queued",
                failure_code=None,
                failure_message=None,
                started_at=None,
                completed_at=None,
                trigger_reason=reset_trigger_reason,
            )
            .returning(CheckerRun.id)
        )
        return result.scalar_one_or_none() is not None

    async def replace_stale_running_automatic_gate(
        self,
        *,
        checker_run_id: str,
        replacement: CheckerRun,
        trigger_source: str,
        system_actor_id: str,
        system_issuer: str,
        auth_source: str,
        failure_code: str,
        failure_message: str,
        completed_at: datetime,
    ) -> bool:
        """Retire a stale running automatic gate and add its replacement."""
        result = await self._session.execute(
            update(CheckerRun)
            .where(
                CheckerRun.id == checker_run_id,
                CheckerRun.status == "running",
                CheckerRun.is_current_for_submission.is_(True),
                *self._automatic_gate_filters(
                    trigger_source=trigger_source,
                    system_actor_id=system_actor_id,
                    system_issuer=system_issuer,
                    auth_source=auth_source,
                ),
            )
            .values(
                status="failed",
                failure_code=failure_code,
                failure_message=failure_message,
                completed_at=completed_at,
                is_current_for_submission=False,
            )
            .returning(CheckerRun.id)
        )
        if result.scalar_one_or_none() is None:
            return False
        self._session.add(replacement)
        await self._session.flush()
        return True

    async def claim_queued_automatic_gate(
        self,
        *,
        checker_run_id: str,
        trigger_source: str,
        system_actor_id: str,
        system_issuer: str,
        auth_source: str,
        started_at: datetime,
    ) -> bool:
        """Atomically claim a queued current automatic gate."""
        result = await self._session.execute(
            update(CheckerRun)
            .where(
                CheckerRun.id == checker_run_id,
                CheckerRun.status == "queued",
                CheckerRun.is_current_for_submission.is_(True),
                *self._automatic_gate_filters(
                    trigger_source=trigger_source,
                    system_actor_id=system_actor_id,
                    system_issuer=system_issuer,
                    auth_source=auth_source,
                ),
            )
            .values(status="running", started_at=started_at)
            .returning(CheckerRun.id)
        )
        return result.scalar_one_or_none() is not None

    async def claim_queued_automatic_gate_repair_dispatch(
        self,
        *,
        checker_run_id: str,
        trigger_source: str,
        system_actor_id: str,
        system_issuer: str,
        auth_source: str,
        unclaimed_trigger_reason: str,
        claimed_trigger_reason: str,
    ) -> bool:
        """Atomically claim redispatch rights for a still-queued automatic gate."""
        result = await self._session.execute(
            update(CheckerRun)
            .where(
                CheckerRun.id == checker_run_id,
                CheckerRun.status == "queued",
                CheckerRun.is_current_for_submission.is_(True),
                CheckerRun.trigger_reason == unclaimed_trigger_reason,
                *self._automatic_gate_filters(
                    trigger_source=trigger_source,
                    system_actor_id=system_actor_id,
                    system_issuer=system_issuer,
                    auth_source=auth_source,
                ),
            )
            .values(
                trigger_reason=claimed_trigger_reason,
            )
            .returning(CheckerRun.id)
        )
        return result.scalar_one_or_none() is not None

    async def fail_running_automatic_gate(
        self,
        *,
        checker_run_id: str,
        trigger_source: str,
        system_actor_id: str,
        system_issuer: str,
        auth_source: str,
        failure_code: str,
        failure_message: str,
        completed_at: datetime,
    ) -> bool:
        """Fail a running current automatic gate after execution failure."""
        result = await self._session.execute(
            update(CheckerRun)
            .where(
                CheckerRun.id == checker_run_id,
                CheckerRun.status == "running",
                CheckerRun.is_current_for_submission.is_(True),
                *self._automatic_gate_filters(
                    trigger_source=trigger_source,
                    system_actor_id=system_actor_id,
                    system_issuer=system_issuer,
                    auth_source=auth_source,
                ),
            )
            .values(
                status="failed",
                failure_code=failure_code,
                failure_message=failure_message[:1000],
                completed_at=completed_at,
            )
            .returning(CheckerRun.id)
        )
        return result.scalar_one_or_none() is not None

    async def complete_running_automatic_gate(
        self,
        *,
        checker_run: CheckerRun,
        trigger_source: str,
        system_actor_id: str,
        system_issuer: str,
        auth_source: str,
        routing_recommendation: str,
        outcome_source: str,
        audit_event_id: str,
        artifact_manifest_hash: str,
        passed_count: int,
        warning_count: int,
        failed_count: int,
        blocking_count: int,
        completed_at: datetime,
        results: Sequence[CheckerResult],
    ) -> bool:
        """Complete a running automatic gate if its claim is still current."""
        claim = await self._session.execute(
            update(CheckerRun)
            .where(
                CheckerRun.id == checker_run.id,
                CheckerRun.status == "running",
                CheckerRun.is_current_for_submission.is_(True),
                *self._automatic_gate_filters(
                    trigger_source=trigger_source,
                    system_actor_id=system_actor_id,
                    system_issuer=system_issuer,
                    auth_source=auth_source,
                ),
            )
            .values(
                status="completed",
                routing_recommendation=routing_recommendation,
                outcome_source=outcome_source,
                audit_event_id=audit_event_id,
                artifact_manifest_hash=artifact_manifest_hash,
                passed_count=passed_count,
                warning_count=warning_count,
                failed_count=failed_count,
                blocking_count=blocking_count,
                completed_at=completed_at,
                failure_code=None,
                failure_message=None,
            )
            .returning(CheckerRun.id)
        )
        if claim.scalar_one_or_none() is None:
            return False
        self._session.add_all(list(results))
        await self._session.flush()
        await self._session.refresh(checker_run)
        return True

    async def get_run_claim_state(self, checker_run_id: str) -> CheckerRunClaimState | None:
        """Load only the fields required to fence an automatic gate claim."""
        result = await self._session.execute(
            select(
                CheckerRun.status,
                CheckerRun.is_current_for_submission,
                CheckerRun.trigger_source,
                CheckerRun.triggered_by,
                CheckerRun.triggered_by_subject,
                CheckerRun.triggered_by_issuer,
                CheckerRun.trigger_auth_source,
            ).where(CheckerRun.id == checker_run_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return CheckerRunClaimState(
            status=row.status,
            is_current_for_submission=row.is_current_for_submission,
            trigger_source=row.trigger_source,
            triggered_by=row.triggered_by,
            triggered_by_subject=row.triggered_by_subject,
            triggered_by_issuer=row.triggered_by_issuer,
            trigger_auth_source=row.trigger_auth_source,
        )

    @staticmethod
    def _automatic_gate_filters(
        *,
        trigger_source: str,
        system_actor_id: str,
        system_issuer: str,
        auth_source: str,
    ) -> tuple[object, ...]:
        """Return common predicates for server-owned automatic gate rows."""
        return (
            CheckerRun.trigger_source == trigger_source,
            CheckerRun.triggered_by == system_actor_id,
            CheckerRun.triggered_by_subject == system_actor_id,
            CheckerRun.triggered_by_issuer == system_issuer,
            CheckerRun.trigger_auth_source == auth_source,
        )

    async def list_runs_for_submission(self, submission_id: str) -> Sequence[CheckerRun]:
        """List checker runs for one submission.

        Args:
            submission_id: Submission id whose checker runs should be listed.

        Returns:
            Checker runs ordered by attempt number.
        """
        result = await self._session.execute(
            select(CheckerRun)
            .options(selectinload(CheckerRun.results))
            .where(CheckerRun.submission_id == submission_id)
            .order_by(CheckerRun.attempt_number.asc())
        )
        return result.scalars().all()

    async def get_current_run_for_submission(self, submission_id: str) -> CheckerRun | None:
        """Load the current checker run for one submission.

        Args:
            submission_id: Submission id whose current checker run should be loaded.

        Returns:
            Current checker run when present; otherwise ``None``.
        """
        result = await self._session.execute(
            select(CheckerRun)
            .options(selectinload(CheckerRun.results))
            .where(
                CheckerRun.submission_id == submission_id,
                CheckerRun.is_current_for_submission.is_(True),
            )
        )
        return result.scalar_one_or_none()
