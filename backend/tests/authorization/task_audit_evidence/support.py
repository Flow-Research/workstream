"""Public history selectors and real Audit Authority fixtures."""
from tests.authorization.task_locked_context.support import grant_for

ACTION = "audit.task.evidence.read"
FIELDS = {"event_id", "event_type", "from_status", "to_status", "actor_id", "created_at", "assignment_id", "authorization_decision_id"}


def path(project, task):
    return f"/api/v1/audit/projects/{project}/tasks/{task}/evidence"


async def grant_audit(access, project, *, system=False):
    return await grant_for(access, project, "audit", system=system)
