"""Invocation-local trial relay client contract tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import unittest


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from trial_transport import (  # noqa: E402
    TrialTransportError,
    TrialUnavailable,
    execute_trial,
)


DIGEST = "sha256:" + "a" * 64


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def plan() -> dict[str, object]:
    return {
        "schema_version": "workstream.checker_trial_plan.v1",
        "environment": {
            "dockerfile": "environment/Dockerfile",
            "context": ".",
            "platform": "linux/amd64",
        },
        "resources": {
            "cpu_quota_millis": 1000,
            "cpu_time_ms": 10_000,
            "memory_bytes": 1024,
            "disk_bytes": 1024,
            "maximum_entries": 100,
            "pids": 16,
        },
        "build_timeout_ms": 1000,
        "steps": [
            {
                "slot_id": "slot_a",
                "slot_kind": "generic_run",
                "operation": "run",
                "state_source": "fresh",
                "visible_roles": [],
                "command": ["true"],
                "working_directory": ".",
                "timeout_ms": 1000,
            }
        ],
    }


def metrics() -> dict[str, object]:
    return {
        "terminal_state": "completed_work",
        "outcome": "succeeded",
        "exit_code": 0,
        "signal": None,
        "export_outcome": "exported",
        "stdout_sha256": DIGEST,
        "stdout_byte_count": 0,
        "stderr_sha256": DIGEST,
        "stderr_byte_count": 0,
        "measurements_available": True,
        "elapsed_ms": 10,
        "cpu_time_ms": 3,
        "peak_memory_bytes": 256,
        "peak_pids": 1,
        "written_bytes": 0,
        "written_entries": 0,
        "measurement_method": "cgroup_v2",
    }


def completed_response(value: dict[str, object]) -> dict[str, object]:
    build = metrics() | {
        "candidate_image_digest": "sha256:" + "b" * 64,
        "candidate_archive_digest": "sha256:" + "c" * 64,
    }
    step = metrics() | {
        "slot_id": "slot_a",
        "operation_order": 1,
        "workspace_before_sha256": "sha256:" + "d" * 64,
        "workspace_after_sha256": "sha256:" + "e" * 64,
    }
    return {
        "protocol_version": "workstream.checker_trial.v1",
        "outcome": "completed",
        "receipt_handle": "trial_receipt_" + "f" * 32,
        "receipt_digest": "sha256:" + "f" * 64,
        "observations": {
            "schema_version": "workstream.checker_trial_observations.v1",
            "terminal_state": "completed_work",
            "profile_digest": DIGEST,
            "engine_identity_digest": DIGEST,
            "plan_digest": digest(value),
            "observation_digest": DIGEST,
            "build": build,
            "steps": [step],
        },
        "failure_code": None,
    }


class RelayServer:
    def __init__(self, response: bytes, *, declared_length: int | None = None) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temporary.name) / "execution.sock")
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(self.path)
        self.listener.listen(1)
        self.response = response
        self.declared_length = declared_length
        self.request: dict[str, object] | None = None
        self.failure: BaseException | None = None
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        try:
            stream, _ = self.listener.accept()
            with stream:
                length = struct.unpack(">I", self._read_exact(stream, 4))[0]
                self.request = json.loads(self._read_exact(stream, length))
                declared = (
                    len(self.response)
                    if self.declared_length is None
                    else self.declared_length
                )
                stream.sendall(struct.pack(">I", declared) + self.response)
        except BaseException as exc:  # test thread reports back to caller
            self.failure = exc
        finally:
            self.listener.close()

    @staticmethod
    def _read_exact(stream: socket.socket, length: int) -> bytes:
        value = bytearray()
        while len(value) < length:
            chunk = stream.recv(length - len(value))
            if not chunk:
                raise EOFError
            value.extend(chunk)
        return bytes(value)

    def finish(self) -> None:
        self.thread.join(timeout=3)
        self.temporary.cleanup()
        if self.failure is not None:
            raise self.failure


class TrialTransportTests(unittest.TestCase):
    def exchange(
        self,
        response: dict[str, object] | bytes,
        *,
        value: dict[str, object] | None = None,
        declared_length: int | None = None,
    ):
        trial_plan = value or plan()
        raw = response if type(response) is bytes else canonical(response)
        server = RelayServer(raw, declared_length=declared_length)
        try:
            result = execute_trial(
                trial_plan,
                timeout_seconds=2,
                socket_path=server.path,
            )
        finally:
            server.finish()
        self.last_request = server.request
        return result

    def test_completed_receipt_is_plan_bound_and_observations_are_canonical(self):
        trial_plan = plan()
        response = completed_response(trial_plan)
        result = self.exchange(response, value=trial_plan)
        self.assertEqual(result.receipt_handle, "trial_receipt_" + "f" * 32)
        self.assertEqual(result.observations, response["observations"])
        self.assertEqual(
            json.loads(result.canonical_observations), response["observations"]
        )
        self.assertEqual(
            self.last_request,
            {
                "protocol_version": "workstream.checker_trial.v1",
                "operation": "execute_plan",
                "plan": trial_plan,
            },
        )

    def test_closed_unavailable_response_never_produces_a_receipt(self):
        response = {
            "protocol_version": "workstream.checker_trial.v1",
            "outcome": "unavailable",
            "receipt_handle": None,
            "receipt_digest": None,
            "failure_code": "cleanup_unsettled",
        }
        with self.assertRaises(TrialUnavailable) as raised:
            self.exchange(response)
        self.assertEqual(raised.exception.failure_code, "cleanup_unsettled")

    def test_duplicate_key_non_json_constant_and_unknown_failure_are_rejected(self):
        response = completed_response(plan())
        raw = canonical(response)
        duplicate = raw.replace(
            b'"outcome":"completed"',
            b'"outcome":"completed","outcome":"completed"',
            1,
        )
        non_json = raw.replace(b'"elapsed_ms":10', b'"elapsed_ms":NaN', 1)
        unavailable = {
            "protocol_version": "workstream.checker_trial.v1",
            "outcome": "unavailable",
            "receipt_handle": None,
            "receipt_digest": None,
            "failure_code": "contributor_failed",
        }
        wrong_typed_failure = dict(unavailable, failure_code=[])
        missing_outcome = {"protocol_version": "workstream.checker_trial.v1"}
        wrong_typed_outcome = completed_response(plan())
        wrong_typed_outcome["observations"]["steps"][0]["outcome"] = []
        for invalid in (
            duplicate,
            non_json,
            unavailable,
            wrong_typed_failure,
            missing_outcome,
            wrong_typed_outcome,
        ):
            with (
                self.subTest(invalid=invalid),
                self.assertRaisesRegex(TrialTransportError, "invalid_response"),
            ):
                self.exchange(invalid)

    def test_nonfinite_or_unrepresentable_timeout_is_rejected_before_connect(self):
        for timeout in (float("nan"), float("inf"), 10**1000):
            with (
                self.subTest(timeout=timeout),
                self.assertRaisesRegex(TrialTransportError, "invalid_request"),
            ):
                execute_trial(
                    plan(),
                    timeout_seconds=timeout,
                    socket_path="/does/not/exist",
                )

    def test_oversize_or_truncated_frame_fails_closed(self):
        with self.assertRaisesRegex(TrialTransportError, "invalid_response"):
            self.exchange(b"", declared_length=4 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(TrialTransportError, "invalid_response"):
            self.exchange(b"{}", declared_length=100)

    def test_substituted_plan_or_step_identity_is_rejected(self):
        wrong_digest = completed_response(plan())
        wrong_digest["observations"]["plan_digest"] = DIGEST
        wrong_slot = completed_response(plan())
        wrong_slot["observations"]["steps"][0]["slot_id"] = "slot_b"
        extra_step = completed_response(plan())
        extra_step["observations"]["steps"].append(
            dict(extra_step["observations"]["steps"][0])
        )
        for response in (wrong_digest, wrong_slot, extra_step):
            with (
                self.subTest(response=response),
                self.assertRaisesRegex(TrialTransportError, "invalid_response"),
            ):
                self.exchange(response)

    def test_contradictory_work_outcomes_are_rejected(self):
        exit_zero_failure = completed_response(plan())
        step = exit_zero_failure["observations"]["steps"][0]
        step["outcome"] = "exit_nonzero"
        missing_candidate = completed_response(plan())
        build = missing_candidate["observations"]["build"]
        build["candidate_image_digest"] = None
        build["candidate_archive_digest"] = None
        unavailable_measurement = completed_response(plan())
        unavailable_measurement["observations"]["steps"][0][
            "measurements_available"
        ] = False
        for response in (
            exit_zero_failure,
            missing_candidate,
            unavailable_measurement,
        ):
            with (
                self.subTest(response=response),
                self.assertRaisesRegex(TrialTransportError, "invalid_response"),
            ):
                self.exchange(response)

    def test_forced_limits_do_not_require_an_invented_signal(self):
        for outcome in (
            "deadline_exceeded",
            "cpu_exceeded",
            "memory_exceeded",
            "pid_exceeded",
            "disk_exceeded",
            "output_exceeded",
        ):
            response = completed_response(plan())
            step = response["observations"]["steps"][0]
            step.update(outcome=outcome, exit_code=None, export_outcome="unavailable")
            with self.subTest(outcome=outcome):
                self.exchange(response)
                step["exit_code"] = 137
                with self.assertRaisesRegex(TrialTransportError, "invalid_response"):
                    self.exchange(response)
                step.update(exit_code=None, signal=9)
                with self.assertRaisesRegex(TrialTransportError, "invalid_response"):
                    self.exchange(response)

    def test_export_failures_preserve_real_child_status(self):
        for build in (False, True):
            for outcome, export in (
                ("disk_exceeded", "capacity_exceeded"),
                ("export_invalid", "invalid"),
            ):
                response = completed_response(plan())
                observation = (
                    response["observations"]["build"]
                    if build
                    else response["observations"]["steps"][0]
                )
                observation.update(outcome=outcome, export_outcome=export)
                if build:
                    observation.update(
                        candidate_image_digest=None, candidate_archive_digest=None
                    )
                with self.subTest(build=build, outcome=outcome):
                    self.exchange(response)
                    observation["export_outcome"] = "exported"
                    with self.assertRaisesRegex(
                        TrialTransportError, "invalid_response"
                    ):
                        self.exchange(response)

    def test_actual_reserved_exit_codes_remain_work_failures(self):
        for build in (False, True):
            for code in (125, 126):
                response = completed_response(plan())
                observation = (
                    response["observations"]["build"]
                    if build
                    else response["observations"]["steps"][0]
                )
                observation.update(
                    outcome="exit_nonzero",
                    exit_code=code,
                    export_outcome="not_started" if build else "exported",
                )
                if build:
                    observation.update(
                        candidate_image_digest=None, candidate_archive_digest=None
                    )
                with self.subTest(build=build, code=code):
                    self.exchange(response)

    def test_invalid_child_status_and_missing_export_fact_are_rejected(self):
        for changes in (
            {"exit_code": True},
            {"exit_code": 256, "outcome": "exit_nonzero"},
            {"exit_code": -1, "outcome": "exit_nonzero"},
            {"exit_code": None, "signal": 65, "outcome": "signalled"},
            {"export_outcome": "unavailable"},
            {"export_outcome": None},
        ):
            response = completed_response(plan())
            response["observations"]["steps"][0].update(changes)
            with (
                self.subTest(changes=changes),
                self.assertRaisesRegex(TrialTransportError, "invalid_response"),
            ):
                self.exchange(response)


if __name__ == "__main__":
    unittest.main()
