"""Shared async runner helpers for synchronous Celery task boundaries."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")


def run_async_task(coro_factory: Callable[[], Awaitable[T]]) -> T:
    """Run an async task body from a synchronous Celery task boundary.

    Celery workers normally execute with no running event loop. Eager test
    execution can happen inside an async API request, so that case runs the
    coroutine on a short-lived thread instead of nesting event loops.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(coro_factory())).result()
