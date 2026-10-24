"""Strict invocation-local client for the trusted isolated-trial relay."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
import socket
import struct
from typing import Callable


TRIAL_PROTOCOL_VERSION = "workstream.checker_trial.v1"
OBSERVATION_SCHEMA_VERSION = "workstream.checker_trial_observations.v1"
EXECUTION_SOCKET_PATH = "/work/execution.sock"
MAXIMUM_FRAME_BYTES = 4 * 1024 * 1024
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_HANDLE = re.compile(r"trial_receipt_[0-9a-f]{32}")
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_.-]{0,99}")
_OUTCOMES = frozenset(
    {
        "succeeded",
        "exit_nonzero",
        "signalled",
        "deadline_exceeded",
        "cpu_exceeded",
        "memory_exceeded",
        "pid_exceeded",
        "disk_exceeded",
        "output_exceeded",
        "dependency_skipped",
        "export_invalid",
    }
)
_FAILURE_CODES = frozenset(
    {
        "invalid_request",
        "material_unavailable",
        "implementation_unavailable",
        "capacity_exceeded",
        "deadline_exceeded",
        "cancelled",
        "cleanup_unsettled",
    }
)


class TrialTransportError(RuntimeError):
    """The trusted trial transport returned no usable completed receipt."""


class TrialUnavailable(TrialTransportError):
    """The relay returned a closed infrastructure failure code."""

    def __init__(self, failure_code: str) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code


@dataclass(frozen=True, slots=True)
class CompletedTrial:
    receipt_handle: str
    receipt_digest: str
    observations: dict[str, object]
    canonical_observations: bytes


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise TrialTransportError("invalid_response")
        value[key] = item
    return value


def _invalid_constant(_value: str) -> object:
    raise TrialTransportError("invalid_response")


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
        raise TrialTransportError("invalid_request") from exc


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _valid_timeout(value: object) -> bool:
    if type(value) not in {int, float} or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value)) and value > 0
    except (OverflowError, ValueError):
        return False


def execute_trial(
    plan: dict[str, object],
    *,
    timeout_seconds: float,
    socket_path: str = EXECUTION_SOCKET_PATH,
    maximum_frame_bytes: int = MAXIMUM_FRAME_BYTES,
    socket_factory: Callable[[], socket.socket] | None = None,
) -> CompletedTrial:
    """Execute one closed plan and validate the runner-produced receipt projection."""
    if (
        type(plan) is not dict
        or not _valid_timeout(timeout_seconds)
        or type(maximum_frame_bytes) is not int
        or maximum_frame_bytes < 1
        or maximum_frame_bytes > MAXIMUM_FRAME_BYTES
        or type(socket_path) is not str
        or not socket_path
        or "\x00" in socket_path
    ):
        raise TrialTransportError("invalid_request")
    request = {
        "protocol_version": TRIAL_PROTOCOL_VERSION,
        "operation": "execute_plan",
        "plan": plan,
    }
    payload = _canonical(request)
    if not payload or len(payload) > maximum_frame_bytes:
        raise TrialTransportError("invalid_request")
    factory = socket_factory or (
        lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    )
    stream = factory()
    try:
        stream.settimeout(float(timeout_seconds))
        stream.connect(socket_path)
        stream.sendall(struct.pack(">I", len(payload)) + payload)
        length = struct.unpack(">I", _read_exact(stream, 4))[0]
        if length < 1 or length > maximum_frame_bytes:
            raise TrialTransportError("invalid_response")
        raw = _read_exact(stream, length)
        trailing = stream.recv(1)
        if trailing:
            raise TrialTransportError("invalid_response")
    except TrialTransportError:
        raise
    except (OSError, TimeoutError, struct.error) as exc:
        raise TrialTransportError("implementation_unavailable") from exc
    finally:
        stream.close()
    response = _decode_response(raw)
    if response.get("outcome") == "unavailable":
        _validate_unavailable(response)
        raise TrialUnavailable(response["failure_code"])
    return _validate_completed(response, plan)


def _read_exact(stream: socket.socket, byte_count: int) -> bytes:
    value = bytearray()
    while len(value) < byte_count:
        chunk = stream.recv(byte_count - len(value))
        if not chunk:
            raise TrialTransportError("invalid_response")
        value.extend(chunk)
    return bytes(value)


def _decode_response(raw: bytes) -> dict[str, object]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_closed_object,
            parse_constant=_invalid_constant,
        )
    except (UnicodeError, json.JSONDecodeError, TrialTransportError) as exc:
        raise TrialTransportError("invalid_response") from exc
    if (
        type(value) is not dict
        or value.get("protocol_version") != TRIAL_PROTOCOL_VERSION
    ):
        raise TrialTransportError("invalid_response")
    return value


def _validate_unavailable(value: dict[str, object]) -> None:
    if (
        set(value)
        != {
            "protocol_version",
            "outcome",
            "receipt_handle",
            "receipt_digest",
            "failure_code",
        }
        or value["outcome"] != "unavailable"
        or value["receipt_handle"] is not None
        or value["receipt_digest"] is not None
        or type(value["failure_code"]) is not str
        or value["failure_code"] not in _FAILURE_CODES
    ):
        raise TrialTransportError("invalid_response")


def _validate_completed(
    value: dict[str, object], plan: dict[str, object]
) -> CompletedTrial:
    if (
        set(value)
        != {
            "protocol_version",
            "outcome",
            "receipt_handle",
            "receipt_digest",
            "observations",
            "failure_code",
        }
        or value["outcome"] != "completed"
        or type(value["receipt_handle"]) is not str
        or _HANDLE.fullmatch(value["receipt_handle"]) is None
        or type(value["receipt_digest"]) is not str
        or _DIGEST.fullmatch(value["receipt_digest"]) is None
        or value["failure_code"] is not None
        or type(value["observations"]) is not dict
    ):
        raise TrialTransportError("invalid_response")
    observations = value["observations"]
    _validate_observations(observations, plan)
    canonical = _canonical(observations)
    return CompletedTrial(
        receipt_handle=value["receipt_handle"],
        receipt_digest=value["receipt_digest"],
        observations=json.loads(canonical),
        canonical_observations=canonical,
    )


def _validate_observations(
    observations: dict[str, object], plan: dict[str, object]
) -> None:
    if (
        set(observations)
        != {
            "schema_version",
            "terminal_state",
            "profile_digest",
            "engine_identity_digest",
            "plan_digest",
            "observation_digest",
            "build",
            "steps",
        }
        or observations["schema_version"] != OBSERVATION_SCHEMA_VERSION
        or observations["terminal_state"] != "completed_work"
        or not all(
            type(observations[name]) is str
            and _DIGEST.fullmatch(observations[name]) is not None
            for name in (
                "profile_digest",
                "engine_identity_digest",
                "plan_digest",
                "observation_digest",
            )
        )
        or observations["plan_digest"] != _digest(plan)
        or type(observations["build"]) is not dict
        or type(observations["steps"]) is not list
        or type(plan.get("steps")) is not list
        or len(observations["steps"]) != len(plan["steps"])
    ):
        raise TrialTransportError("invalid_response")
    _validate_operation(observations["build"], build=True)
    for order, (observation, step) in enumerate(
        zip(observations["steps"], plan["steps"], strict=True), start=1
    ):
        if (
            type(observation) is not dict
            or type(step) is not dict
            or observation.get("slot_id") != step.get("slot_id")
            or observation.get("operation_order") != order
        ):
            raise TrialTransportError("invalid_response")
        _validate_operation(observation, build=False)


def _validate_operation(value: dict[str, object], *, build: bool) -> None:
    common = {
        "terminal_state",
        "outcome",
        "exit_code",
        "signal",
        "export_outcome",
        "stdout_sha256",
        "stdout_byte_count",
        "stderr_sha256",
        "stderr_byte_count",
        "measurements_available",
        "elapsed_ms",
        "cpu_time_ms",
        "peak_memory_bytes",
        "peak_pids",
        "written_bytes",
        "written_entries",
        "measurement_method",
    }
    expected = common | (
        {"candidate_image_digest", "candidate_archive_digest"}
        if build
        else {
            "slot_id",
            "operation_order",
            "workspace_before_sha256",
            "workspace_after_sha256",
        }
    )
    outcome = value.get("outcome")
    if (
        set(value) != expected
        or value.get("terminal_state") != "completed_work"
        or type(outcome) is not str
        or outcome not in _OUTCOMES
        or value.get("measurements_available") is not True
        or type(value.get("measurement_method")) is not str
        or _IDENTIFIER.fullmatch(value["measurement_method"]) is None
        or any(
            type(value.get(name)) is not int or value[name] < 0
            for name in (
                "stdout_byte_count",
                "stderr_byte_count",
                "elapsed_ms",
                "cpu_time_ms",
                "peak_memory_bytes",
                "peak_pids",
                "written_bytes",
                "written_entries",
            )
        )
        or any(
            type(value.get(name)) is not str or _DIGEST.fullmatch(value[name]) is None
            for name in ("stdout_sha256", "stderr_sha256")
        )
    ):
        raise TrialTransportError("invalid_response")
    _validate_exit(
        outcome,
        value.get("exit_code"),
        value.get("signal"),
        value.get("export_outcome"),
        build=build,
    )
    if build:
        image = value["candidate_image_digest"]
        archive = value["candidate_archive_digest"]
        if (
            (image is None) != (archive is None)
            or image is not None
            and (
                type(image) is not str
                or _DIGEST.fullmatch(image) is None
                or type(archive) is not str
                or _DIGEST.fullmatch(archive) is None
            )
            or (outcome == "succeeded") != (image is not None)
            or outcome == "dependency_skipped"
        ):
            raise TrialTransportError("invalid_response")
    else:
        if (
            type(value["slot_id"]) is not str
            or _IDENTIFIER.fullmatch(value["slot_id"]) is None
            or type(value["operation_order"]) is not int
            or value["operation_order"] < 1
            or any(
                type(value[name]) is not str or _DIGEST.fullmatch(value[name]) is None
                for name in ("workspace_before_sha256", "workspace_after_sha256")
            )
        ):
            raise TrialTransportError("invalid_response")


def _validate_exit(
    outcome: str,
    exit_code: object,
    signal: object,
    export_outcome: object,
    *,
    build: bool,
) -> None:
    exited = type(exit_code) is int and 0 <= exit_code <= 255 and signal is None
    signalled = exit_code is None and type(signal) is int and 1 <= signal <= 64
    if outcome == "succeeded":
        valid = exited and exit_code == 0 and export_outcome == "exported"
    elif outcome == "exit_nonzero":
        valid = (
            exited
            and exit_code != 0
            and export_outcome == ("not_started" if build else "exported")
        )
    elif outcome == "signalled":
        valid = signalled and export_outcome == ("not_started" if build else "exported")
    elif outcome == "dependency_skipped":
        valid = exit_code is None and signal is None and export_outcome == "not_started"
    elif outcome == "export_invalid":
        valid = (exited or signalled) and export_outcome == "invalid"
    elif outcome == "disk_exceeded" and export_outcome == "capacity_exceeded":
        valid = exited or signalled
    else:
        valid = exit_code is None and signal is None and export_outcome == "unavailable"
    if not valid:
        raise TrialTransportError("invalid_response")


__all__ = (
    "CompletedTrial",
    "TrialTransportError",
    "TrialUnavailable",
    "execute_trial",
)
