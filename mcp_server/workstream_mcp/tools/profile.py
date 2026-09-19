from __future__ import annotations

import json
from typing import Any

from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

from workstream_mcp.http_gateway import WorkstreamGateway
from workstream_mcp.schemas import INPUT_SCHEMA, profile_output_schema

TOOL_NAME = "workstream_profile_get"


def definition() -> Tool:
    return Tool(
        name=TOOL_NAME,
        description="Read the authenticated caller's Workstream profile.",
        input_schema=INPUT_SCHEMA,
        output_schema=profile_output_schema(),
        annotations=ToolAnnotations(
            title="Read own Workstream profile",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=True,
        ),
    )


async def invoke(
    gateway: WorkstreamGateway, bearer: str, correlation_id: str | None
) -> CallToolResult:
    outcome = await gateway.profile_get(bearer, correlation_id)
    if outcome.failure is not None:
        return outcome.failure.result()
    data: dict[str, Any] = outcome.data or {}
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, separators=(",", ":")))],
        structured_content=data,
    )
