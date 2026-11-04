"""Current TASK response and replay shapes contain no obsolete payment terms."""

from copy import deepcopy
from datetime import UTC, datetime
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.tasks.api.authorization import TaskAuthorityFacts, TaskAuthorityOperation
from app.modules.tasks.command_replay import TaskCommandReplay, TaskReplayConflict
from app.modules.tasks.models import TaskAssignment, TaskCommandReceipt, WorkstreamTask
from app.modules.tasks.schemas import AssignmentResponse, TaskClaimResponse, TaskResponse, TaskWithAssignmentResponse

REMOVED_FIELDS = ("base_amount", "currency", "payout_type", "locked_payment_policy_version")


def _command_receipt(operation, status):
    """Arrange the same immutable internal result for command and HTTP proofs."""
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
    return receipt, facts, task, assignment, response


@pytest.mark.parametrize("operation,status", [
    (TaskAuthorityOperation.CREATE, "draft"),
    (TaskAuthorityOperation.SCREEN, "screening"),
    (TaskAuthorityOperation.RELEASE, "ready"),
    (TaskAuthorityOperation.CLAIM, "in_progress"),
])
def test_current_command_receipts_replay_without_obsolete_payment_fields(operation, status):
    receipt, facts, task, assignment, _ = _command_receipt(operation, status)
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


MANAGEMENT_ONLY = {
    "source_ref", "source_payload_hash", "import_batch_id", "external_task_id", "created_by", "assigned_to",
    "locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash",
    "locked_effective_project_submission_artifact_policy_id", "locked_effective_project_submission_artifact_policy_hash",
    "locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash",
}


@pytest.mark.parametrize("operation,status", [
    (TaskAuthorityOperation.CREATE, "draft"),
    (TaskAuthorityOperation.SCREEN, "screening"),
    (TaskAuthorityOperation.RELEASE, "ready"),
    (TaskAuthorityOperation.CLAIM, "in_progress"),
])
async def test_command_http_nulls_and_claim_privacy_preserve_internal_replay(operation, status):
    """Public JSON is complete without changing stored command result custody."""
    from app.modules.tasks.router import get_task_commands, router

    receipt, facts, task, assignment, fresh = _command_receipt(operation, status)
    original = deepcopy(receipt.response)
    replay = TaskCommandReplay.recover(receipt, receipt.request_digest, facts, task, assignment, reserved=False)
    claim = operation is TaskAuthorityOperation.CLAIM
    if claim:
        # The route's closed audience type must protect even non-null private data.
        fresh = fresh.model_copy(update={"task": fresh.task.model_copy(update={
            key: "PRIVATE_" + key for key in MANAGEMENT_ONLY
        })})
    method = "create_task" if operation is TaskAuthorityOperation.CREATE else operation.value.split(".")[-1]
    commands = SimpleNamespace(**{method: AsyncMock(side_effect=[fresh, replay])})
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_task_commands] = lambda: commands
    create = operation is TaskAuthorityOperation.CREATE
    path = f"/api/v1/projects/{task.project_id}/tasks" if create else f"/api/v1/tasks/{task.id}/{method}"
    payload = {"title": task.title, "description": task.description} if create else {"reason": "Exact request"}
    responses = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        for _ in range(2):
            response = await client.post(path, json=payload, headers={"Idempotency-Key": str(receipt.idempotency_key)})
            assert response.status_code == (201 if create else 200), response.text
            parsed = (TaskClaimResponse if claim else TaskResponse).model_validate_json(response.content)
            responses.append(response.json())
            assert receipt.response == original
            wire = response.json()["task"] if claim else response.json()
            for field in ("task_type", "difficulty", "estimated_time_minutes", "acceptance_criteria", "rejection_criteria", "deadline_at"):
                assert wire[field] is None
            if claim:
                assert set(wire) == set(TaskResponse.model_fields) - MANAGEMENT_ONLY
                assert set(wire).isdisjoint(MANAGEMENT_ONLY)
                assert "PRIVATE_" not in response.text
                assert response.json()["assignment"]["released_at"] is None
                assert parsed.assignment.id == assignment.id
                for changed in ({k: v for k, v in wire.items() if k != "task_type"}, wire | {"source_ref": None}):
                    with pytest.raises(ValidationError):
                        TaskClaimResponse.model_validate_json(json.dumps(response.json() | {"task": changed}))
    assert responses[0] == responses[1]
    definitions = app.openapi()["components"]["schemas"]
    if claim:
        schema = definitions["ContributorClaimTaskResponse"]
        assert schema["additionalProperties"] is False
        assert set(schema["properties"]) == set(TaskResponse.model_fields) - MANAGEMENT_ONLY
        assert "task_type" in schema["required"]
        assert definitions["TaskClaimResponse"]["additionalProperties"] is False
        assert app.openapi()["paths"]["/api/v1/tasks/{task_id}/claim"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/TaskClaimResponse",
        }
