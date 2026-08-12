"""TASK-owned composition adapters."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.api import TaskSubmissionContextPort
from app.modules.tasks.repository import TaskRepository
from app.adapters.tasks.submission_composition import (
    DenySubmissionCreationAuthorization,
    TransactionalSubmissionCreationCommand,
)

__all__ = (
    "DenySubmissionCreationAuthorization",
    "TransactionalSubmissionCreationCommand",
    "task_submission_context_port",
)


def task_submission_context_port(session: AsyncSession) -> TaskSubmissionContextPort:
    """Bind the public TASK submission-context port to its repository."""
    return TaskRepository(session)
