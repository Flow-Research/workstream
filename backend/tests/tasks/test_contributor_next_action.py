"""The server-computed contributor next action over every claim state combination."""

from itertools import product
from typing import get_args

import pytest

from app.modules.tasks.api.contributor_reads import AssignmentState, RevisionDisposition, TaskStatus
from app.modules.tasks.api.submission_history import SubmissionAttemptStatus
from app.modules.tasks.contributor_reads import next_action

TASK_STATUSES = get_args(TaskStatus)
STATES = get_args(AssignmentState)
LATEST = (None, *get_args(SubmissionAttemptStatus))
REVISIONS = (None, *get_args(RevisionDisposition))


def expected(state, task_status, latest, revision):
    """The issue's rule, written independently as a lookup."""
    if state == "closed":
        return "none"
    return {
        "in_progress": "prepare_submission",
        "submitted": "awaiting_evaluation", "evaluation_pending": "awaiting_evaluation",
        "review_pending": "awaiting_evaluation",
    }.get(task_status, "revise" if (
        task_status == "needs_revision" and latest == "needs_revision" and revision == "ready"
    ) else "none")


@pytest.mark.parametrize(
    ("state", "task_status", "latest", "revision"),
    list(product(STATES, TASK_STATUSES, LATEST, REVISIONS)),
)
def test_next_action_covers_every_combination(state, task_status, latest, revision):
    assert next_action(state, task_status, latest, revision) == expected(state, task_status, latest, revision)


def test_revise_requires_a_ready_revision_of_a_returned_attempt():
    """Only one active combination per blocked reason flips from revise to none."""
    assert next_action("active", "needs_revision", "needs_revision", "ready") == "revise"
    for revision in ("context_blocked", "revision_limit_reached", "revision_deadline_expired", None):
        assert next_action("active", "needs_revision", "needs_revision", revision) == "none"
    assert next_action("active", "needs_revision", "evaluation_pending", "ready") == "none"
    assert next_action("closed", "needs_revision", "needs_revision", "ready") == "none"


def test_stored_task_status_constraint_is_the_api_vocabulary():
    from app.modules.tasks.api.management_queue import TASK_STATUSES as QUEUE_STATUSES
    from app.modules.tasks.models import WorkstreamTask

    [constraint] = [item for item in WorkstreamTask.__table__.constraints if item.name == "ck_workstream_tasks_status"]
    stored = frozenset(value.strip("'") for value in str(constraint.sqltext).split("(", 1)[1].rstrip(")").split(","))
    assert stored == QUEUE_STATUSES == frozenset(TASK_STATUSES)
