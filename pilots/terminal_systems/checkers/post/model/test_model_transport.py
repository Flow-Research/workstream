"""Bounded multi-call model-session framing tests."""

from __future__ import annotations

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

from model_transport import (  # noqa: E402
    ModelCallUnavailable,
    ModelSession,
    ModelSessionError,
)


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def completed(index: int, *, exhausted: bool = False) -> dict[str, object]:
    return {
        "protocol_version": "workstream.model_session.v2",
        "outcome": "completed",
        "call_index": index,
        "output": json.dumps({"answer": index}),
        "receipt_digest": "sha256:" + str(index + 1) * 64,
        "failure_code": None,
        "session_exhausted": exhausted,
    }


class SessionServer:
    def __init__(self, responses: list[bytes]) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temporary.name) / "model.sock")
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(self.path)
        self.listener.listen(1)
        self.responses = responses
        self.requests: list[dict[str, object]] = []
        self.failure: BaseException | None = None
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        try:
            stream, _ = self.listener.accept()
            with stream:
                for response in self.responses:
                    length = struct.unpack(">I", self._read_exact(stream, 4))[0]
                    self.requests.append(json.loads(self._read_exact(stream, length)))
                    stream.sendall(struct.pack(">I", len(response)) + response)
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


class ModelTransportTests(unittest.TestCase):
    def test_one_connection_carries_sequential_plan_and_receipt_bound_assessment(self):
        server = SessionServer([canonical(completed(0)), canonical(completed(1))])
        handle = "trial_receipt_" + "a" * 32
        try:
            with ModelSession(timeout_seconds=2, socket_path=server.path) as session:
                first = session.call("plan", required_receipt_handles=())
                second = session.call("assess", required_receipt_handles=(handle,))
        finally:
            server.finish()
        self.assertEqual((first.call_index, second.call_index), (0, 1))
        self.assertEqual(
            server.requests,
            [
                {
                    "protocol_version": "workstream.model_session.v2",
                    "operation": "call",
                    "call_index": 0,
                    "prompt": "plan",
                    "required_receipt_handles": [],
                },
                {
                    "protocol_version": "workstream.model_session.v2",
                    "operation": "call",
                    "call_index": 1,
                    "prompt": "assess",
                    "required_receipt_handles": [handle],
                },
            ],
        )

    def test_session_exhaustion_is_enforced_before_an_extra_frame(self):
        server = SessionServer([canonical(completed(0, exhausted=True))])
        try:
            with ModelSession(timeout_seconds=2, socket_path=server.path) as session:
                result = session.call("only call")
                self.assertTrue(result.session_exhausted)
                with self.assertRaisesRegex(ModelSessionError, "invalid_request"):
                    session.call("forbidden call")
        finally:
            server.finish()
        self.assertEqual(len(server.requests), 1)

    def test_closed_unavailable_code_is_always_infrastructure(self):
        response = {
            "protocol_version": "workstream.model_session.v2",
            "outcome": "unavailable",
            "call_index": 0,
            "output": None,
            "receipt_digest": None,
            "failure_code": "model_receipt_unavailable",
            "session_exhausted": True,
        }
        server = SessionServer([canonical(response)])
        try:
            with ModelSession(timeout_seconds=2, socket_path=server.path) as session:
                with self.assertRaises(ModelCallUnavailable) as raised:
                    session.call("assessment")
        finally:
            server.finish()
        self.assertEqual(raised.exception.failure_code, "model_receipt_unavailable")

    def test_duplicate_wrong_index_and_unknown_failure_fail_closed(self):
        duplicate = canonical(completed(0)).replace(
            b'"outcome":"completed"',
            b'"outcome":"completed","outcome":"completed"',
            1,
        )
        wrong_index = completed(1)
        unknown = {
            "protocol_version": "workstream.model_session.v2",
            "outcome": "unavailable",
            "call_index": 0,
            "output": None,
            "receipt_digest": None,
            "failure_code": "work_failed",
            "session_exhausted": True,
        }
        wrong_typed = dict(unknown, failure_code=[])
        for response in (
            duplicate,
            canonical(wrong_index),
            canonical(unknown),
            canonical(wrong_typed),
        ):
            server = SessionServer([response])
            try:
                with ModelSession(
                    timeout_seconds=2, socket_path=server.path
                ) as session:
                    with self.assertRaisesRegex(ModelSessionError, "invalid_response"):
                        session.call("prompt")
            finally:
                server.finish()

    def test_handles_are_unique_exact_and_prompt_is_bounded_before_connect(self):
        handle = "trial_receipt_" + "a" * 32
        session = ModelSession(timeout_seconds=2, socket_path="/does/not/exist")
        self.addCleanup(session.close)
        for handles in ((handle, handle), ("trial_receipt_BAD",), ([],)):
            with (
                self.subTest(handles=handles),
                self.assertRaisesRegex(ModelSessionError, "invalid_request"),
            ):
                session.call("prompt", required_receipt_handles=handles)
        with self.assertRaisesRegex(ModelSessionError, "invalid_request"):
            session.call("x" * 1_048_576)

    def test_nonfinite_or_unrepresentable_session_timeout_is_rejected(self):
        for timeout in (float("nan"), float("inf"), 10**1000):
            with (
                self.subTest(timeout=timeout),
                self.assertRaisesRegex(ModelSessionError, "invalid_request"),
            ):
                ModelSession(timeout_seconds=timeout)


if __name__ == "__main__":
    unittest.main()
