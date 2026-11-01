"""Current TASK response and replay shapes contain no obsolete payment terms."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.core.identifiers import new_record_id
from app.modules.tasks.api.authorization import TaskAuthorityFacts, TaskAuthorityOperation
from app.modules.tasks.command_replay import TaskCommandReplay, TaskReplayConflict
from app.modules.tasks.models import TaskAssignment, TaskCommandReceipt, WorkstreamTask
from app.modules.tasks.schemas import AssignmentResponse, TaskResponse, TaskWithAssignmentResponse

REMOVED_FIELDS = ("base_amount", "currency", "payout_type", "locked_payment_policy_version")


@pytest.mark.parametrize("operation,status", [
    (TaskAuthorityOperation.CREATE, "draft"),
    (TaskAuthorityOperation.SCREEN, "screening"),
    (TaskAuthorityOperation.RELEASE, "ready"),
    (TaskAuthorityOperation.CLAIM, "in_progress"),
])
def test_current_command_receipts_replay_without_obsolete_payment_fields(operation, status):
    actor, contributor, task_id, project_id = [new_record_id() for _ in range(4)]
    now = datetime.now(UTC)
    task = WorkstreamTask(id=str(task_id), project_id=str(project_id), title="Task", description="Work",
                         source_type="manual", skill_tags=[], status=status, created_at=now, updated_at=now)
    uses_assignment = operation is TaskAuthorityOperation.CLAIM
    assignment = None
    if uses_assignment:
        task.assigned_to = str(contributor)
        assignment = TaskAssignment(id=str(new_record_id()), task_id=task.id, project_id=task.project_id,
            contributor_id=str(contributor), assigned_by=str(actor), assigned_at=now, status="active",
            submitter_contribution_policy_version_id=new_record_id())
    facts = TaskAuthorityFacts(operation, task_id, project_id, actor, status,
        contributor if assignment else None, UUID(assignment.id) if assignment else None,
        contributor if assignment else None, "sha256:" + "a" * 64)
    captured_task = TaskResponse.model_validate(task).model_copy(update={"assigned_to": None})
    response = (TaskWithAssignmentResponse(task=captured_task, assignment=AssignmentResponse.model_validate(assignment))
                if operation is TaskAuthorityOperation.CLAIM else captured_task)
    receipt = TaskCommandReceipt(id=new_record_id(), actor_profile_id=str(actor), action_id=operation.value,
        idempotency_key=new_record_id(), request_digest="sha256:" + "b" * 64, task_id=task.id, status="pending")
    TaskCommandReplay.complete(receipt, assignment, facts, response)
    stored = receipt.response["task"] if operation is TaskAuthorityOperation.CLAIM else receipt.response
    assert set(REMOVED_FIELDS).isdisjoint(stored)
    original = deepcopy(receipt.response)
    replay = TaskCommandReplay.recover(receipt, receipt.request_digest, facts, task, assignment, reserved=False)
    assert replay.model_dump(mode="json") == original

    # Independently exercise direct, claim-wrapper and nested task rejection.
    for field in REMOVED_FIELDS:
        for nested in ((False, True) if operation is TaskAuthorityOperation.CLAIM else (False,)):
            receipt.response = deepcopy(original)
            target = receipt.response["task"] if nested else receipt.response
            target[field] = None
            with pytest.raises(TaskReplayConflict) as rejected:
                TaskCommandReplay.recover(receipt, receipt.request_digest, facts, task, assignment, reserved=False)
            assert rejected.value.code == "task_replay_state_changed"
    receipt.response = original
    assert TaskCommandReplay.recover(receipt, receipt.request_digest, facts, task, assignment,
                                    reserved=False).model_dump(mode="json") == original
