"""Reject missing or foreign native evidence for the source-first PRE probes."""

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


JOURNEY = Path(__file__).resolve().parents[1] / "journey/pre_qualification.py"
WRAPPER = (
    JOURNEY.parents[3]
    / "external_checkers/workstream-checker-service/tests/smol_fixture/runtime_wrapper.py"
)
SPEC = importlib.util.spec_from_file_location("journey_pre_qualification", JOURNEY)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_failure_cleanup_requires_the_owned_post_delivery_pause(monkeypatch):
    pause = object()
    monkeypatch.setattr(MODULE, "_qualify_failure_cleanup", lambda *args: args[-1])
    environment = {"WORKSTREAM_CLI_JOURNEY_PRE_QUALIFICATION_MODE": "failure_cleanup"}
    with pytest.raises(RuntimeError, match="owned POST pause"):
        MODULE.qualify(None, None, None, None, environment)
    assert (
        MODULE.qualify(None, None, None, None, environment, post_delivery_pause=pause)
        is pause
    )


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "wrong_lease",
        "aggregate_timeout",
        "duplicate_exec",
        "no_delete",
        "pending_cleanup",
        "wrong_runtime",
        "extra_pre",
        "leaked_timeout_vm",
        "unclassified_exec",
    ],
)
def test_native_trace_requires_exact_project_stage_and_cleanup(fault):
    evidence = {}
    trace = []
    wrapper_digest = "sha256:" + sha256(WRAPPER.read_bytes()).hexdigest()
    for name, outcome, exit_code in (
        ("timeout", "infrastructure_failure", 125),
        ("isolation", "completed", 0),
    ):
        evidence[name] = {
            "invocation": {
                "provider_invocation_id": name,
                "operation": "execute_pre",
                "outcome": outcome,
                "cleanup": {"obligation_id": name, "disposition": "destroyed"},
                "runtime": {"binary_sha256": wrapper_digest},
            }
        }
        trace.extend(
            [
                {"name": name, "operation": "create", "prior_resources": []},
                {"name": name, "operation": "start"},
                {"name": name, "operation": "exec", "source_pre": True},
                {
                    "name": name,
                    "operation": "pre_exit",
                    "exit_code": exit_code,
                    "project_deadline_exceeded": name == "timeout",
                },
                {"name": name, "operation": "delete"},
            ]
        )
    trace.append({"name": "post", "operation": "exec", "source_pre": False})
    if fault == "wrong_lease":
        trace[3]["name"] = "foreign"
    if fault == "aggregate_timeout":
        trace[3]["project_deadline_exceeded"] = False
    if fault == "duplicate_exec":
        trace.insert(2, trace[2].copy())
    if fault == "no_delete":
        trace.pop(4)
    if fault == "pending_cleanup":
        evidence["timeout"]["invocation"]["cleanup"]["disposition"] = "pending"
    if fault == "wrong_runtime":
        evidence["timeout"]["invocation"]["runtime"]["binary_sha256"] = "foreign"
    if fault == "extra_pre":
        trace.append({"name": "extra", "operation": "exec", "source_pre": True})
    if fault == "leaked_timeout_vm":
        trace[5]["prior_resources"] = ["timeout"]
    if fault == "unclassified_exec":
        trace[-1].pop("source_pre")
    if fault:
        with pytest.raises(AssertionError):
            MODULE.verify_native_trace(evidence, trace)
    else:
        MODULE.verify_native_trace(evidence, trace)


@pytest.mark.parametrize(
    "change", [{}, {"code": "submission_unavailable"}, {"status": 409}]
)
def test_timeout_replay_compares_stable_business_fields(change):
    failure = {"code": "submission_infrastructure_unavailable", "status": 503}
    first = {"error": failure | {"correlation_id": "first-request"}}
    replay = {"error": failure | {"correlation_id": "second-request"} | change}
    if change:
        with pytest.raises(AssertionError):
            MODULE._verify_failure_replay(first, replay)
    else:
        MODULE._verify_failure_replay(first, replay)


@pytest.mark.parametrize("exact", [True, False])
@pytest.mark.parametrize("limit", [None, "memory", "output"])
def test_runtime_fixture_classifies_only_the_trusted_deadline_line(
    tmp_path, exact, limit
):
    wrapper = tmp_path / "runtime_wrapper.py"
    wrapper.write_bytes(WRAPPER.read_bytes())
    guest = tmp_path / "smol"
    diagnostic = "workstream guest bootstrap failed: project deadline exceeded"
    if not exact:
        diagnostic += " (other diagnostic)"
    if limit is not None:
        diagnostic += f"\nAssertionError: guest {limit} ceiling was not enforced"
    guest.write_text(
        f"#!{sys.executable}\n"
        "import os\n"
        "assert os.environ['WORKSTREAM_PRE_QUALIFICATION_PRIVATE_CANARY'] == 'test-only'\n"
        f"message = {diagnostic.encode()!r}\n"
        "os.write(2, message[:20])\n"
        "os.write(2, message[20:] + b'\\n')\n"
        "raise SystemExit(125)\n",
        encoding="utf-8",
    )
    guest.chmod(0o700)
    trace = tmp_path / "trace.jsonl"
    wrapper.with_suffix(".json").write_text(
        json.dumps(
            {
                "binary": str(guest),
                "trace": str(trace),
                "observe_pre_exit": True,
            }
        ),
        encoding="utf-8",
    )
    invocation = subprocess.run(
        [
            sys.executable,
            str(wrapper),
            "machine",
            "exec",
            "--name",
            "owned",
            "--",
            "/.workstream-guest",
            "--pre-limits",
            "{}",
        ],
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert invocation.returncode == 125
    assert invocation.stderr.decode().rstrip() == diagnostic
    assert [json.loads(line) for line in trace.read_text().splitlines()] == [
        {"name": "owned", "operation": "exec", "source_pre": True},
        {
            "name": "owned",
            "operation": "pre_exit",
            "exit_code": 125,
            "project_deadline_exceeded": exact,
            "guest_limit_unenforced": limit is not None,
        },
    ]


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "limit_unenforced",
        "wrong_cleanup",
        "no_delete",
        "leaked_guest",
        "extra_pre",
        "completed_failure",
    ],
)
def test_remaining_native_trace_binds_each_failure_and_pending_lease(fault):
    wrapper_digest = "sha256:" + sha256(WRAPPER.read_bytes()).hexdigest()
    evidence = {"mode": "failure_cleanup", "failures": {}}
    trace = []
    for name in ("memory", "crash", "output", "pending"):
        invocation = {
            "provider_invocation_id": name,
            "operation": "execute_pre",
            "outcome": "completed" if name == "pending" else "infrastructure_failure",
            "cleanup": {
                "obligation_id": name,
                "disposition": "pending" if name == "pending" else "destroyed",
            },
            "runtime": {"binary_sha256": wrapper_digest},
        }
        item = {"invocation": invocation}
        if name == "pending":
            evidence["pending"] = item
        else:
            evidence["failures"][name] = item
        trace.extend(
            [
                {"name": name, "operation": "create", "prior_resources": []},
                {"name": name, "operation": "start"},
                {"name": name, "operation": "exec", "source_pre": True},
                {
                    "name": name,
                    "operation": "pre_exit",
                    "exit_code": 0 if name == "pending" else 37,
                    "project_deadline_exceeded": False,
                    "guest_limit_unenforced": False,
                },
                {"name": name, "operation": "delete"},
            ]
        )
    if fault == "limit_unenforced":
        trace[3]["guest_limit_unenforced"] = True
    elif fault == "wrong_cleanup":
        evidence["pending"]["invocation"]["cleanup"]["disposition"] = "destroyed"
    elif fault == "no_delete":
        trace.pop()
    elif fault == "leaked_guest":
        trace[15]["prior_resources"] = ["memory"]
    elif fault == "extra_pre":
        trace.append({"name": "extra", "operation": "exec", "source_pre": True})
    elif fault == "completed_failure":
        trace[8]["exit_code"] = 0
    if fault:
        with pytest.raises(AssertionError):
            MODULE.verify_native_trace(evidence, trace)
    else:
        MODULE.verify_native_trace(evidence, trace)


def test_completed_pre_delete_fault_targets_only_its_traced_lease(tmp_path):
    wrapper = tmp_path / "runtime_wrapper.py"
    wrapper.write_bytes(WRAPPER.read_bytes())
    guest = tmp_path / "smol"
    guest.write_text(f"#!{sys.executable}\nraise SystemExit(0)\n")
    guest.chmod(0o700)
    trace = tmp_path / "trace.jsonl"
    wrapper.with_suffix(".json").write_text(
        json.dumps(
            {
                "binary": str(guest),
                "trace": str(trace),
                "delete_fault": str(tmp_path / "absent-fault"),
                "observe_pre_exit": True,
                "fault_completed_pre_delete": True,
            }
        )
    )
    base = [sys.executable, str(wrapper), "machine"]
    exec_result = subprocess.run(
        [
            *base,
            "exec",
            "--name",
            "owned",
            "--",
            "/.workstream-guest",
            "--pre-limits",
            "{}",
        ],
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert exec_result.returncode == 0
    second = subprocess.run(
        [
            *base,
            "exec",
            "--name",
            "other",
            "--",
            "/.workstream-guest",
            "--pre-limits",
            "{}",
        ],
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert second.returncode == 0
    owned = subprocess.run(
        [*base, "delete", "--name", "owned"],
        capture_output=True,
        check=False,
        timeout=10,
    )
    foreign = subprocess.run(
        [*base, "delete", "--name", "other"],
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert owned.returncode == 93 and foreign.returncode == 0
    assert [
        row["operation"] for row in map(json.loads, trace.read_text().splitlines())
    ] == ["exec", "pre_exit", "exec", "pre_exit", "delete", "delete"]


@pytest.mark.parametrize("case", ["exact", "wrong_lease", "wrong_nonce", "symlink"])
def test_pending_pre_reconciliation_requires_one_private_matching_receipt(
    tmp_path, case
):
    handoff = {
        "schema_version": "workstream.pre_qualification_restore.v1",
        "nonce": "fresh-nonce",
        "source_operation_id": "source",
        "submission_id": "submission",
        "provider_invocation_id": "lease",
        "terminal_sha256": "sha256:" + "a" * 64,
    }
    receipt = handoff | {"owned_resources_empty": True, "test_service_ready": True}
    if case == "wrong_lease":
        receipt["provider_invocation_id"] = "other-lease"
    if case == "wrong_nonce":
        receipt["nonce"] = "old-nonce"
    path = tmp_path / "pre-qualification-reconciled.json"
    if case == "symlink":
        destination = tmp_path / "foreign.json"
        destination.write_text(json.dumps(receipt))
        destination.chmod(0o600)
        path.symlink_to(destination)
    else:
        path.write_text(json.dumps(receipt))
        path.chmod(0o600)
    if case == "exact":
        MODULE._await_reconciled(tmp_path, handoff)
    else:
        with pytest.raises((AssertionError, OSError)):
            MODULE._await_reconciled(tmp_path, handoff)


def test_pending_pre_reconciliation_has_finite_deadline(tmp_path, monkeypatch):
    clock = iter((0.0, 301.0))
    monkeypatch.setattr(MODULE.time, "monotonic", lambda: next(clock))
    with pytest.raises(AssertionError, match="not acknowledged"):
        MODULE._await_reconciled(tmp_path, {"nonce": "fresh"})
