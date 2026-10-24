"""Bounded multi-call client for the invocation-local model session."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
import socket
import struct
import time


MODEL_PROTOCOL_VERSION = "workstream.model_session.v2"
MODEL_SOCKET_PATH = "/work/model.sock"
MAXIMUM_FRAME_BYTES = 1_048_576
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_HANDLE = re.compile(r"trial_receipt_[0-9a-f]{32}")
# Frozen producer vocabulary inherited by the v2 session. New codes require a
# coordinated protocol revision; images never turn any of them into work facts.
_FAILURE_CODES = frozenset(
    {
        "model_call_unavailable",
        "model_request_invalid",
        "model_request_too_large",
        "model_receipt_unavailable",
        "model_tool_limit_exceeded",
        "model_session_exhausted",
        "model_session_deadline",
        "model_budget_unavailable",
        "model_call_operator_recovery_required",
        "model_provider_delivery_uncertain",
        "model_provider_no_effect",
        "model_provider_usage_unavailable",
        "model_provider_pending",
        "model_provider_recovery_unavailable",
        "model_response_too_large",
        "model_provider_failed",
        "model_transport_unavailable",
    }
)


class ModelSessionError(RuntimeError):
    """The trusted model session cannot yield a usable assessed response."""


class ModelCallUnavailable(ModelSessionError):
    """The trusted service returned a closed infrastructure failure."""

    def __init__(self, failure_code: str) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code


@dataclass(frozen=True, slots=True)
class CompletedModelCall:
    call_index: int
    output: str
    receipt_digest: str
    session_exhausted: bool


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ModelSessionError("invalid_response")
        value[key] = item
    return value


def _invalid_constant(_value: str) -> object:
    raise ModelSessionError("invalid_response")


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ModelSessionError("invalid_request") from exc


def _valid_timeout(value: object) -> bool:
    if type(value) not in {int, float} or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value)) and value > 0
    except (OverflowError, ValueError):
        return False


class ModelSession:
    """One sequential invocation-local connection with a common deadline."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        socket_path: str = MODEL_SOCKET_PATH,
        maximum_frame_bytes: int = MAXIMUM_FRAME_BYTES,
    ) -> None:
        if (
            not _valid_timeout(timeout_seconds)
            or type(socket_path) is not str
            or not socket_path
            or "\x00" in socket_path
            or type(maximum_frame_bytes) is not int
            or maximum_frame_bytes < 1
            or maximum_frame_bytes > MAXIMUM_FRAME_BYTES
        ):
            raise ModelSessionError("invalid_request")
        self._deadline = time.monotonic() + float(timeout_seconds)
        self._socket_path = socket_path
        self._maximum_frame_bytes = maximum_frame_bytes
        self._stream: socket.socket | None = None
        self._next_call_index = 0
        self._exhausted = False
        self._failed = False

    def __enter__(self) -> ModelSession:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def call(
        self, prompt: str, *, required_receipt_handles: tuple[str, ...] = ()
    ) -> CompletedModelCall:
        if (
            self._failed
            or self._exhausted
            or type(prompt) is not str
            or not prompt
            or "\x00" in prompt
            or type(required_receipt_handles) is not tuple
            or any(
                type(item) is not str or _HANDLE.fullmatch(item) is None
                for item in required_receipt_handles
            )
            or len(set(required_receipt_handles)) != len(required_receipt_handles)
        ):
            raise ModelSessionError("invalid_request")
        call_index = self._next_call_index
        request = {
            "protocol_version": MODEL_PROTOCOL_VERSION,
            "operation": "call",
            "call_index": call_index,
            "prompt": prompt,
            "required_receipt_handles": list(required_receipt_handles),
        }
        payload = _canonical(request)
        if len(payload) > self._maximum_frame_bytes:
            raise ModelSessionError("invalid_request")
        try:
            stream = self._connected_stream()
            stream.sendall(struct.pack(">I", len(payload)) + payload)
            length = struct.unpack(">I", self._read_exact(stream, 4))[0]
            if length < 1 or length > self._maximum_frame_bytes:
                raise ModelSessionError("invalid_response")
            response = self._decode(self._read_exact(stream, length))
            completed = self._validate_response(response, call_index)
        except (ModelSessionError, ModelCallUnavailable):
            self._failed = True
            self.close()
            raise
        except (OSError, TimeoutError, struct.error) as exc:
            self._failed = True
            self.close()
            raise ModelSessionError("implementation_unavailable") from exc
        self._next_call_index += 1
        self._exhausted = completed.session_exhausted
        return completed

    def _connected_stream(self) -> socket.socket:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise ModelSessionError("deadline_exceeded")
        if self._stream is None:
            self._stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._stream.settimeout(remaining)
            self._stream.connect(self._socket_path)
        else:
            self._stream.settimeout(remaining)
        return self._stream

    @staticmethod
    def _read_exact(stream: socket.socket, byte_count: int) -> bytes:
        value = bytearray()
        while len(value) < byte_count:
            chunk = stream.recv(byte_count - len(value))
            if not chunk:
                raise ModelSessionError("invalid_response")
            value.extend(chunk)
        return bytes(value)

    @staticmethod
    def _decode(raw: bytes) -> dict[str, object]:
        try:
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_closed_object,
                parse_constant=_invalid_constant,
            )
        except (UnicodeError, json.JSONDecodeError, ModelSessionError) as exc:
            raise ModelSessionError("invalid_response") from exc
        if type(value) is not dict:
            raise ModelSessionError("invalid_response")
        return value

    @staticmethod
    def _validate_response(
        value: dict[str, object], call_index: int
    ) -> CompletedModelCall:
        if (
            set(value)
            != {
                "protocol_version",
                "outcome",
                "call_index",
                "output",
                "receipt_digest",
                "failure_code",
                "session_exhausted",
            }
            or value["protocol_version"] != MODEL_PROTOCOL_VERSION
            or type(value["call_index"]) is not int
            or value["call_index"] != call_index
            or type(value["session_exhausted"]) is not bool
        ):
            raise ModelSessionError("invalid_response")
        if value["outcome"] == "unavailable":
            if (
                value["output"] is not None
                or value["receipt_digest"] is not None
                or type(value["failure_code"]) is not str
                or value["failure_code"] not in _FAILURE_CODES
            ):
                raise ModelSessionError("invalid_response")
            raise ModelCallUnavailable(value["failure_code"])
        if (
            value["outcome"] != "completed"
            or type(value["output"]) is not str
            or not value["output"]
            or "\x00" in value["output"]
            or type(value["receipt_digest"]) is not str
            or _DIGEST.fullmatch(value["receipt_digest"]) is None
            or value["failure_code"] is not None
        ):
            raise ModelSessionError("invalid_response")
        return CompletedModelCall(
            call_index=call_index,
            output=value["output"],
            receipt_digest=value["receipt_digest"],
            session_exhausted=value["session_exhausted"],
        )


__all__ = (
    "CompletedModelCall",
    "ModelCallUnavailable",
    "ModelSession",
    "ModelSessionError",
)
