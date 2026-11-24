"""The CLI journey keeps one exact guide request after an unknown transport result."""

import importlib.util
from pathlib import Path

import pytest


PATH = Path(__file__).resolve().parents[1] / "journey/public_setup.py"
SPEC = importlib.util.spec_from_file_location("journey_public_setup_recovery", PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

SETUP = {
    "id": "setup-1",
    "project_id": "project-1",
    "guide_id": "guide-1",
    "source_snapshot_id": "source-1",
    "setup_generation": 1,
    "status": "queued",
}
COMMAND = (
    "project",
    "guide",
    "compile-requirements",
    "project-1",
    "guide-1",
    "--idempotency-key",
    "one-fixed-key",
)
SELECTOR = ("project", "guide", "setup", "project-1", "guide-1")


class FakeClient:
    def __init__(self, dispatch, observed=None):
        self.dispatch = list(dispatch)
        self.observed = observed or SETUP
        self.calls = []

    def call(self, _token, *arguments, expected_exit=0):
        self.calls.append((arguments, expected_exit))
        if arguments == SELECTOR:
            return dict(SETUP if len(self.calls) == 1 else self.observed)
        assert arguments == COMMAND
        return self.dispatch.pop(0)


def test_lost_guide_ack_observes_then_replays_identical_key(monkeypatch):
    monkeypatch.setattr(MODULE.time, "sleep", lambda _: None)
    receipt = {
        "operation_id": "operation-1",
        "setup_run_id": "setup-1",
        "setup_generation": 1,
        "status": "queued",
    }
    client = FakeClient(
        [
            {"error": {"code": "service_unavailable", "outcome_unknown": True}},
            receipt,
        ]
    )
    assert (
        MODULE._request_compilation_with_unknown_recovery(
            client, "token", COMMAND, SELECTOR
        )
        == receipt
    )
    assert client.calls == [
        (SELECTOR, 0),
        (COMMAND, None),
        (SELECTOR, 0),
        (COMMAND, None),
    ]


@pytest.mark.parametrize(
    "changed",
    [
        {"id": "other-setup"},
        {"source_snapshot_id": "other-source"},
        {"setup_generation": 2},
        {"status": "compilation_invalid_terminal"},
    ],
)
def test_lost_guide_ack_refuses_changed_or_failed_setup(monkeypatch, changed):
    monkeypatch.setattr(MODULE.time, "sleep", lambda _: None)
    client = FakeClient(
        [{"error": {"code": "service_unavailable", "outcome_unknown": True}}],
        observed=SETUP | changed,
    )
    with pytest.raises(AssertionError):
        MODULE._request_compilation_with_unknown_recovery(
            client, "token", COMMAND, SELECTOR
        )
    assert client.calls == [(SELECTOR, 0), (COMMAND, None), (SELECTOR, 0)]


def test_conclusive_guide_dispatch_error_never_retries():
    client = FakeClient([{"error": {"code": "not_allowed"}}])
    with pytest.raises(AssertionError, match="conclusively"):
        MODULE._request_compilation_with_unknown_recovery(
            client, "token", COMMAND, SELECTOR
        )
    assert client.calls == [(SELECTOR, 0), (COMMAND, None)]


@pytest.mark.parametrize(
    "substitution",
    [
        {"setup_run_id": "foreign-setup"},
        {"setup_generation": 2},
    ],
)
def test_guide_dispatch_refuses_wrong_acknowledged_setup(substitution):
    receipt = {
        "operation_id": "operation-1",
        "setup_run_id": "setup-1",
        "setup_generation": 1,
        "status": "queued",
    }
    client = FakeClient([receipt | substitution])
    with pytest.raises(AssertionError, match="acknowledgement changed setup"):
        MODULE._request_compilation_with_unknown_recovery(
            client, "token", COMMAND, SELECTOR
        )
    assert client.calls == [(SELECTOR, 0), (COMMAND, None)]


def test_review_required_branch_selects_backend_default_by_omission():
    required = MODULE._review_policy_input(human_review_required=True)
    automatic = MODULE._review_policy_input(human_review_required=False)
    assert required == {
        "review_preference_window_seconds": 3600,
        "review_lease_duration_seconds": 1800,
    }
    assert automatic == required | {"human_review_required": False}
