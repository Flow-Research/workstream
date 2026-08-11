"""TASK-owned composition adapters."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.api import TaskSubmissionContextPort
from app.modules.tasks.repository import TaskRepository


def task_submission_context_port(session: AsyncSession) -> TaskSubmissionContextPort:
    """Bind the public TASK submission-context port to its repository."""
    return TaskRepository(session)
