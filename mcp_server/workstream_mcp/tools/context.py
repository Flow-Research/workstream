from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator, ValidationError  # type: ignore[import-untyped]
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

from workstream_mcp.errors import adapter_failure
from workstream_mcp.http_gateway import WorkstreamGateway
from workstream_mcp.schemas import (
    AUTHORIZATION_CONTEXT_INPUT_SCHEMA,
    authorization_context_output_schema,
)

TOOL_NAME = "workstream_authorization_context_get"


def definition() -> Tool:
    return Tool(
        name=TOOL_NAME,
        description="Read the authenticated caller's authority for one Workstream project.",
        input_schema=AUTHORIZATION_CONTEXT_INPUT_SCHEMA,
        output_schema=authorization_context_output_schema(),
        annotations=ToolAnnotations(
            title="Read own project authorization context",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=True,
        ),
    )


async def invoke(
    gateway: WorkstreamGateway,
    bearer: str,
    correlation_id: str | None,
    arguments: dict[str, Any],
) -> CallToolResult:
    try:
        Draft202012Validator(AUTHORIZATION_CONTEXT_INPUT_SCHEMA).validate(arguments)
    except ValidationError:
        return adapter_failure("invalid_tool_input", status=400)
    outcome = await gateway.authorization_context_get(
        bearer, arguments["project_id"], correlation_id
    )
    if outcome.failure is not None:
        return outcome.failure.result()
    data = outcome.data or {}
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, separators=(",", ":")))],
        structured_content=data,
    )
