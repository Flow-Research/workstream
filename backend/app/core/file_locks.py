"""Bounded cross-process file-lock primitives."""

from __future__ import annotations

import fcntl
import math
import time


DEFAULT_FILE_LOCK_POLL_SECONDS = 0.01


def acquire_exclusive_file_lock(
    descriptor: int,
    *,
    timeout_seconds: float,
    poll_seconds: float = DEFAULT_FILE_LOCK_POLL_SECONDS,
) -> None:
    """Acquire one exclusive flock or fail when its monotonic deadline expires."""
    durations = (timeout_seconds, poll_seconds)
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or value <= 0
        or not math.isfinite(value)
        for value in durations
    ):
        raise ValueError("file lock durations are invalid")
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("file lock deadline exceeded") from None
            time.sleep(min(poll_seconds, remaining))
