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
def journey(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "source_audit", SimpleNamespace(audit_accepted_source=None)
    )
    spec = importlib.util.spec_from_file_location("journey_progress_identity", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def progress(journey):
    return journey._progress


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


@pytest.mark.parametrize("different", [False, True])
def test_corrected_bundle_replays_one_mcp_command_in_cli(journey, tmp_path, different):
    archive = tmp_path / "correct.zip"
    archive.write_bytes(b"corrected bytes")
    receipt = {
        "status": "accepted",
        "processing_stage_at_acceptance": "finalization_pending",
        "task_id": "task-1",
        "assignment_id": "assignment-1",
        "operation_id": "operation-1",
        "replayed": False,
        "pre_submission_results": PENDING["pre_submission_results"],
    }
    replay = receipt | {"replayed": True}
    if different:
        replay["operation_id"] = "operation-2"
    cli = Client(replay, PENDING)
    cli.reads.append(PENDING)
    mcp_commands = []

    def mcp_submit(*args):
        mcp_commands.append(args)
        return receipt

    mcp = SimpleNamespace(submit=mcp_submit)
    if different:
        with pytest.raises(AssertionError, match="exact source replay"):
            journey._submit(cli, "token", "task-1", "assignment-1", archive, mcp=mcp)
    else:
        key, actual = journey._submit(
            cli, "token", "task-1", "assignment-1", archive, mcp=mcp
        )
        assert actual == receipt
        assert mcp_commands == [("task-1", "assignment-1", archive, key)]
        assert cli.commands[0] == journey._command(
            "task-1", "assignment-1", archive, key
        )


def test_exact_assignment_read_rejects_mcp_feedback_substitution(journey):
    status = {
        "assignment": {"assignment_id": "assignment-1", "task_id": "task-1"},
        "current_status": "needs_revision",
        "next_action": "revise",
        "feedback_submission_id": "submission-1",
    }
    cli = Client(status, status)

    def mcp_call(name, params):
        assert name == "workstream_task_assignment_get"
        assert params == {"assignment_id": "assignment-1"}
        return status | {"feedback_submission_id": "submission-2"}

    with pytest.raises(AssertionError, match="assignment status differ"):
        journey._assignment_status(
            cli, "token", "task-1", "assignment-1", mcp=SimpleNamespace(call=mcp_call)
        )


def test_mcp_renewal_uses_rotated_grant_and_exact_resource(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "journey_refresh_client", PATH.with_name("client.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    now = 10
    monkeypatch.setattr(module.time, "monotonic", lambda: now)
    grants = []

    def request(path, document, *, form):
        assert path == "/realms/flow/protocol/openid-connect/token" and form
        grants.append(document)
        return {"access_token": "access", "refresh_token": "rotated", "expires_in": 300}

    token = module.RefreshingToken(
        SimpleNamespace(request=request),
        "workstream-mcp-proof",
        "first",
        resource="https://mcp.example/mcp",
    )
    assert token() == token() == "access"
    now += 160
    assert token() == "access"
    assert grants == [
        {
            "grant_type": "refresh_token",
            "client_id": "workstream-mcp-proof",
            "refresh_token": value,
            "resource": "https://mcp.example/mcp",
        }
        for value in ("first", "rotated")
    ]
