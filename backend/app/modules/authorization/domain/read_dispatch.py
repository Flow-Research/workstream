"""Closed selection of the existing read families and contribution evidence reads."""

from app.modules.authorization.catalogue import (
    ActionId, HISTORY_READ_ACTIONS, CONTRIBUTION_READ_ACTIONS, CONTRIBUTOR_READ_ACTIONS,
    PROJECT_MANAGEMENT_READ_ACTIONS,
)
from app.modules.authorization.domain.contribution_reads import contribution_read_denial
from app.modules.authorization.domain.contributor_reads import contributor_read_denial
from app.modules.authorization.domain.management_reads import management_read_denial
from app.modules.authorization.domain.project_reads import project_read_denial
from app.modules.authorization.domain.submission_history import history_read_denial
from app.modules.authorization.domain.task_queues import TASK_QUEUE_ACTIONS, queue_read_denial

READ_ACTIONS = (
    TASK_QUEUE_ACTIONS | HISTORY_READ_ACTIONS | CONTRIBUTION_READ_ACTIONS | CONTRIBUTOR_READ_ACTIONS
    | PROJECT_MANAGEMENT_READ_ACTIONS | {ActionId.PROJECT_READ}
)


async def read_denial(action, resource, context, repository, refresh, lifecycle, revalidate_self):
    """Evaluate one closed read and return its outcome with the resource the decision records.

    Project reads keep their existing actor revalidation callback. Only the
    management evaluator returns an evaluated resource (the summary's locked
    exact-project Finance disclosure); every other family records the
    resource it was given.
    """
    if action.action_id is ActionId.PROJECT_READ:
        return (*await project_read_denial(
            action, resource, context, repository, revalidate_self, lifecycle), resource)
    if action.action_id in PROJECT_MANAGEMENT_READ_ACTIONS:
        return await management_read_denial(action, resource, context, repository, refresh, lifecycle)
    if action.action_id in HISTORY_READ_ACTIONS:
        evaluator = history_read_denial
    elif action.action_id in TASK_QUEUE_ACTIONS:
        evaluator = queue_read_denial
    elif action.action_id in CONTRIBUTION_READ_ACTIONS:
        evaluator = contribution_read_denial
    elif action.action_id in CONTRIBUTOR_READ_ACTIONS:
        evaluator = contributor_read_denial
    else:
        raise TypeError("unsupported closed read action")
    return (*await evaluator(action, resource, context, repository, refresh, lifecycle), resource)
