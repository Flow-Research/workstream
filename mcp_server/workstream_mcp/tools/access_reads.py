"""Fixed administrative projections; Workstream remains the authority."""

from __future__ import annotations

import json
from typing import Any

from jsonschema import (  # type: ignore[import-untyped]
    Draft202012Validator,
    FormatChecker,
    ValidationError,
)
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

from workstream_mcp.errors import adapter_failure
from workstream_mcp.http_gateway import WorkstreamGateway
from workstream_mcp.schemas import ACCESS_READ_INPUT_SCHEMAS, access_read_output_schema

_DESCRIPTIONS = {
    "permissions_list": "Read Workstream permission definitions, not the caller's permissions.",
    "admin_roles_list": "Read administrative role definitions, not the caller's grants.",
    "admin_grants_list": "List administrative grants for one scope with an opaque page cursor.",
    "actor_admin_grants_list": "Read one actor's administrative grant history for one scope.",
    "actor_get": "Read the authorized administrative projection of one actor.",
    "actor_identity_link_get": "Read an actor's identity-link summary, without its subject.",
}
TOOL_NAMES = tuple(f"workstream_{name}" for name in _DESCRIPTIONS)
_INPUT_VALIDATORS = {
    name: Draft202012Validator(schema, format_checker=FormatChecker())
    for name, schema in ACCESS_READ_INPUT_SCHEMAS.items()
}


def definitions() -> list[Tool]:
    """Publish the six closed contracts without inferring caller authority."""
    return [
        Tool(
            name=f"workstream_{name}",
            description=description,
            input_schema=ACCESS_READ_INPUT_SCHEMAS[name],
            output_schema=access_read_output_schema(name),
            annotations=ToolAnnotations(
                read_only_hint=False,
                destructive_hint=False,
                idempotent_hint=False,
                open_world_hint=True,
            ),
        )
        for name, description in _DESCRIPTIONS.items()
    ]


async def invoke(
    gateway: WorkstreamGateway,
    tool_name: str,
    bearer: str,
    correlation_id: str | None,
    arguments: dict[str, Any],
) -> CallToolResult:
    """Validate syntax before one API read, preserving query omission and cursors."""
    if tool_name not in TOOL_NAMES:
        return adapter_failure("unknown_tool", status=404)
    name = tool_name.removeprefix("workstream_")
    try:
        _INPUT_VALIDATORS[name].validate(arguments)
    except ValidationError:
        return adapter_failure("invalid_tool_input", status=400)
    if "limit" in arguments:
        # JSON Schema integers include integral floats; serialize a canonical query value.
        arguments = {**arguments, "limit": int(arguments["limit"])}
    outcome = await gateway.access_read(name, bearer, arguments, correlation_id)
    if outcome.failure is not None:
        return outcome.failure.result()
    content = outcome.data or {}
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(content, separators=(",", ":")))],
        structured_content=content,
    )
