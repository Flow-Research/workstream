"""Shared task-scope authorization helpers."""

from __future__ import annotations

from app.modules.tasks.models import WorkstreamTask
from app.schemas.auth import ActorContext


def can_admin_or_task_creator_manage(actor: ActorContext, task: WorkstreamTask) -> bool:
    """Return whether an actor can manage operator actions for one task."""
    roles = set(actor.roles)
    return "admin" in roles or ("project_manager" in roles and task.created_by == actor.actor_id)
