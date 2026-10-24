"""Standalone Terminal Systems POST checker image entrypoint."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import sys
import time

from author_checker import AUTHOR_REQUIREMENT, execute_author_accuracy_check
from checker import ModelCallUnavailable as CheckerModelUnavailable
from checker import execute as execute_model_check
from model_transport import ModelCallUnavailable, ModelSession, ModelSessionError
from result import canonical, infrastructure_result
from revision_checker import (
    REVISION_OBJECTIVE_REQUIREMENT,
    REVISION_RERUN_REQUIREMENT,
    execute_revision_objective_check,
    execute_revision_rerun_check,
)
from rubric import BLOCKED_CHECKS, SUPPORTED_CHECKS
from runtime_checker import RUNTIME_REQUIREMENT, execute_runtime_check
from trial_transport import TrialTransportError, TrialUnavailable, execute_trial


REQUEST_READ_CAPACITY = 2 * 1024 * 1024
MATERIAL_ROOT = Path("/work/input")


class EntrypointError(ValueError):
    """The outer invocation cannot be handled by this image."""


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise EntrypointError("invalid_request")
        value[key] = item
    return value


def _invalid_constant(_value: str) -> object:
    raise EntrypointError("invalid_request")


def decode_request(raw: bytes) -> dict[str, object]:
    if not raw or len(raw) > REQUEST_READ_CAPACITY or b"\x00" in raw:
        raise EntrypointError("invalid_request")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_closed_object,
            parse_constant=_invalid_constant,
        )
    except (UnicodeError, json.JSONDecodeError, EntrypointError) as exc:
        raise EntrypointError("invalid_request") from exc
    if type(value) is not dict:
        raise EntrypointError("invalid_request")
    return value


def evaluate(
    request: dict[str, object],
    *,
    material_root: Path = MATERIAL_ROOT,
    model_session_factory: Callable[..., ModelSession] = ModelSession,
    trial_client: Callable[..., object] = execute_trial,
) -> dict[str, object]:
    """Evaluate one configured member within the invocation's common deadline."""
    try:
        configuration = request["configuration"]
        registry = request["registry"]
        if (
            type(configuration) is not dict
            or type(registry) is not dict
            or type(registry.get("resources")) is not dict
            or type(registry["resources"].get("deadline_ms")) is not int
            or registry["resources"]["deadline_ms"] < 1
            or type(configuration.get("check")) is not str
        ):
            raise EntrypointError("invalid_request")
        deadline = time.monotonic() + registry["resources"]["deadline_ms"] / 1000

        def remaining() -> float:
            value = deadline - time.monotonic()
            if value <= 0:
                raise TrialUnavailable("deadline_exceeded")
            return value

        check = configuration["check"]
        if check == REVISION_RERUN_REQUIREMENT:
            return execute_revision_rerun_check(
                request,
                material_root,
                lambda plan: trial_client(plan, timeout_seconds=remaining()),
            )
        with model_session_factory(timeout_seconds=remaining()) as session:
            if check == RUNTIME_REQUIREMENT:
                return execute_runtime_check(
                    request,
                    material_root,
                    session,
                    lambda plan: trial_client(plan, timeout_seconds=remaining()),
                )
            if check == AUTHOR_REQUIREMENT:
                return execute_author_accuracy_check(
                    request,
                    material_root,
                    session,
                    lambda plan: trial_client(plan, timeout_seconds=remaining()),
                )
            if check == REVISION_OBJECTIVE_REQUIREMENT:
                return execute_revision_objective_check(
                    request,
                    material_root,
                    session,
                )
            if check in SUPPORTED_CHECKS or check in BLOCKED_CHECKS:

                def assess(prompt: str) -> str:
                    try:
                        return session.call(prompt, required_receipt_handles=()).output
                    except (ModelCallUnavailable, ModelSessionError) as exc:
                        raise CheckerModelUnavailable("model_call_unavailable") from exc

                return execute_model_check(request, material_root, assess)
        return infrastructure_result(request, "invalid_output")
    except (KeyError, TypeError, ValueError, EntrypointError):
        return infrastructure_result(request, "invalid_output")
    except TrialUnavailable as exc:
        return infrastructure_result(
            request,
            "deadline_exceeded"
            if exc.failure_code == "deadline_exceeded"
            else "implementation_unavailable",
        )
    except (TrialTransportError, ModelCallUnavailable, ModelSessionError):
        return infrastructure_result(request, "implementation_unavailable")
    except (MemoryError, RecursionError):
        return infrastructure_result(request, "capacity_exceeded")


def main() -> int:
    """Read one bounded request and emit one canonical result without traceback."""
    try:
        raw = sys.stdin.buffer.read(REQUEST_READ_CAPACITY + 1)
        request = decode_request(raw)
        response = evaluate(request)
        sys.stdout.write(canonical(response))
        return 0
    except (EntrypointError, KeyError, TypeError, ValueError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
