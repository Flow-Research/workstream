"""Two public operation reads may straddle the T5 commit."""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


PATH = Path(__file__).resolve().parents[1] / "journey/submission_work.py"
PENDING = {
    "operation_id": "operation-1",
    "task_id": "task-1",
    "assignment_id": "assignment-1",
    "idempotency_key": "key-1",
    "accepted_at": "accepted-once",
    "task_status_at_acceptance": "evaluation_pending",
    "pre_submission_results": [{"checker_name": "pilot-pre", "status": "passed"}],
    "operation_state": "finalization_pending",
    "processing_stage": "finalization_pending",
    "submission_id": None,
    "submission_version": None,
    "evaluation_request_id": None,
}
FINALIZED = PENDING | {
    "operation_state": "finalized",
    "processing_stage": "evaluation_pending",
    "submission_id": "submission-1",
    "submission_version": 1,
    "evaluation_request_id": "evaluation-1",
}


@pytest.fixture
def progress(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "task_work", SimpleNamespace(create_claimed_task=None)
    )
    monkeypatch.setitem(
        sys.modules, "source_audit", SimpleNamespace(audit_accepted_source=None)
    )
    spec = importlib.util.spec_from_file_location("journey_progress_identity", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._progress


class Client:
    def __init__(self, by_key, by_id):
        self.reads = [by_key, by_id]
        self.commands = []

    def call(self, _token, *arguments):
        self.commands.append(arguments)
        return self.reads.pop(0)


def test_key_then_id_read_may_straddle_finalization_commit(progress):
    client = Client(PENDING, FINALIZED)
    assert progress(client, "token", "task-1", "key-1", "operation-1") == PENDING
    assert client.commands[0][-2:] == ("--idempotency-key", "key-1")
    assert client.commands[1][-2:] == ("--operation-id", "operation-1")


@pytest.mark.parametrize(
    "field,value",
    [
        ("operation_id", "other-operation"),
        ("task_id", "other-task"),
        ("assignment_id", "other-assignment"),
        ("idempotency_key", "other-key"),
        ("pre_submission_results", []),
        ("submission_id", "other-submission"),
    ],
)
def test_key_and_id_reads_reject_identity_substitution(progress, field, value):
    client = Client(FINALIZED, FINALIZED | {field: value})
    with pytest.raises(AssertionError, match="durable identity"):
        progress(client, "token", "task-1", "key-1", "operation-1")


def test_key_and_id_reads_reject_state_regression(progress):
    client = Client(FINALIZED, PENDING)
    with pytest.raises(AssertionError, match="durable identity"):
        progress(client, "token", "task-1", "key-1", "operation-1")
