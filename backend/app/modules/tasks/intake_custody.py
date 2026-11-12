"""TASK-owned pointer participation using the existing submission context port."""

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.api.intake_custody import IntakeTaskSnapshot
from app.modules.tasks.api.submission_context import (
    TaskSubmissionContextPort, TaskSubmissionContextRequest, TaskSubmissionContextUnavailable,
)
from app.modules.tasks.repository import TaskRepository


class IntakeTaskCustody:
    """Flush-only TASK participant; no new route or authorization capability."""

    def __init__(self, session: AsyncSession, contexts: TaskSubmissionContextPort) -> None:
        self._session = session
        self._tasks = TaskRepository(session)
        self._contexts = contexts

    async def lock(self, task_id: UUID) -> UUID:
        """Lock TASK first and require a root transaction owned by the caller."""
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise TaskSubmissionContextUnavailable("task_submission_context_invalid")
        task = await self._tasks.get_task(str(task_id), for_update=True)
        if task is None:
            raise TaskSubmissionContextUnavailable("task_submission_context_invalid")
        return UUID(task.project_id)

    async def claim(self, request: TaskSubmissionContextRequest, operation_id: UUID) -> IntakeTaskSnapshot:
        """Use canonical eligibility/currentness before installing a new pointer."""
        await self.lock(request.task_id)
        task = await self._tasks.get_task(str(request.task_id), for_update=True)
        if task.active_submission_operation_id is not None:
            raise TaskSubmissionContextUnavailable("task_submission_operation_in_progress")
        context = await self._contexts.lock_submission_context(request)
        snapshot = await self._session.scalar(text(
            "SELECT public.submission_intake_task_snapshot(t) "
            "FROM public.workstream_tasks t WHERE id=:id"
        ), {"id": request.task_id})
        task.active_submission_operation_id = str(operation_id)
        await self._session.flush()
        return IntakeTaskSnapshot(
            context.locked_project_context.project_id, context.status,
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
        )

    async def require_active(self, task_id: UUID, operation_id: UUID) -> UUID:
        """Retain TASK custody while refusing a foreign or cleared operation."""
        project_id = await self.lock(task_id)
        task = await self._tasks.get_task(str(task_id), for_update=True)
        if task.active_submission_operation_id != str(operation_id):
            raise TaskSubmissionContextUnavailable("task_submission_context_invalid")
        return project_id

    async def release(self, task_id: UUID, operation_id: UUID) -> None:
        """Never clear a different operation's ownership."""
        await self.lock(task_id)
        task = await self._tasks.get_task(str(task_id), for_update=True)
        if task.active_submission_operation_id != str(operation_id):
            raise TaskSubmissionContextUnavailable("task_submission_context_invalid")
        task.active_submission_operation_id = None
        await self._session.flush()

    async def accept(self, task_id: UUID, operation_id: UUID, expected_status: str) -> None:
        """Keep the pointer while accepted source work awaits formal finalization.

        The deferred acceptance/custody constraints require the same transaction's
        exact ART, AUTH, PRE and event records. This is not a generic transition.
        """
        await self.require_active(task_id, operation_id)
        task = await self._tasks.get_task(str(task_id), for_update=True)
        if expected_status not in {"in_progress", "needs_revision"} or task.status != expected_status:
            raise TaskSubmissionContextUnavailable("task_submission_context_invalid")
        task.status = "evaluation_pending"
        await self._session.flush()
