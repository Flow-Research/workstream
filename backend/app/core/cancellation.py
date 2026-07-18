"""Cancellation-resistant async ownership handoffs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar


CancellationResult = TypeVar("CancellationResult")
BlockingParameters = ParamSpec("BlockingParameters")


async def await_cancellation_resistant(
    awaitable: Awaitable[CancellationResult],
) -> CancellationResult:
    """Finish an ownership handoff despite repeated caller cancellation."""
    task = asyncio.ensure_future(awaitable)
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.done():
                return task.result()


async def await_completion_preserving_cancellation(
    awaitable: Awaitable[CancellationResult],
) -> CancellationResult:
    """Finish an awaitable but preserve cancellation as the caller result."""
    task = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await await_cancellation_resistant(task)
        except BaseException:
            raise cancellation from None
        raise


async def run_blocking_cancellation_resistant(
    function: Callable[BlockingParameters, CancellationResult],
    *args: BlockingParameters.args,
    **kwargs: BlockingParameters.kwargs,
) -> CancellationResult:
    """Run blocking I/O to completion while preserving caller cancellation."""
    return await await_completion_preserving_cancellation(
        asyncio.to_thread(function, *args, **kwargs)
    )
