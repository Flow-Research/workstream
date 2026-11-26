"""Bounded public observation of the same setup run, without redispatch."""

import asyncio


async def wait_for_guide_read(client, path, token, predicate, call):
    for _ in range(120):
        value = await call(client, "GET", path, token, 200)
        if predicate(value):
            return value
        # The dispatch fence precedes inference. Unresolved can still be in flight;
        # observe the same run, never turn uncertainty into success or a retry.
        if value.get("error_code") not in {None, "provider_outcome_unresolved"}:
            raise AssertionError("guide worker failed: " + str(value["error_code"]))
        await asyncio.sleep(1)
    raise AssertionError(
        "public guide setup did not reach the expected state "
        f"(status={value.get('status')!r}, step={value.get('current_step')!r}, "
        f"error_code={value.get('error_code')!r}, generation={value.get('setup_generation')!r})"
    )
