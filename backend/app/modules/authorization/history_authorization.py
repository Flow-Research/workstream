"""Translate owner history facts into one canonical AUTH read decision."""

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.submission_history import HistoryReadResourceContext
from app.modules.tasks.api.submission_history import HistoryReadAuthorityFacts


class HistoryReadAuthorization:
    def __init__(self, kernel):
        self._kernel = kernel

    async def require_history(self, facts: HistoryReadAuthorityFacts) -> None:
        target = facts.target
        await self._kernel.require(ActionId(facts.action), HistoryReadResourceContext(
            resource_type=facts.resource_type, resource_id=facts.resource_id,
            scope_project_id=target.project_id, task_id=target.task_id,
            submission_id=target.submission_id, contributor_id=target.contributor_id,
            actor_profile_id=facts.actor_id, request_digest=facts.query_digest,
        ))
