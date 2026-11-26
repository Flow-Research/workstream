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
            MODULE._verify_timeout_replay(first, replay)
    else:
        MODULE._verify_timeout_replay(first, replay)


@pytest.mark.parametrize("exact", [True, False])
def test_runtime_fixture_classifies_only_the_trusted_deadline_line(tmp_path, exact):
    wrapper = tmp_path / "runtime_wrapper.py"
    wrapper.write_bytes(WRAPPER.read_bytes())
    guest = tmp_path / "smol"
    diagnostic = "workstream guest bootstrap failed: project deadline exceeded"
    if not exact:
        diagnostic += " (other diagnostic)"
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
            {"binary": str(guest), "trace": str(trace), "observe_pre_exit": True}
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
        },
    ]
