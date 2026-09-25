from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator, ValidationError  # type: ignore[import-untyped]
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

from workstream_mcp.errors import adapter_failure
from workstream_mcp.http_gateway import WorkstreamGateway
from workstream_mcp.schemas import (
    EMPTY_INPUT_SCHEMA,
    PROFILE_UPDATE_INPUT_SCHEMA,
    profile_output_schema,
    profile_update_output_schema,
)

PROFILE_GET_TOOL_NAME = "workstream_profile_get"
PROFILE_UPDATE_TOOL_NAME = "workstream_profile_update"


def get_definition() -> Tool:
    return Tool(
        name=PROFILE_GET_TOOL_NAME,
        description="Read the authenticated caller's Workstream profile.",
        input_schema=EMPTY_INPUT_SCHEMA,
        output_schema=profile_output_schema(),
        annotations=ToolAnnotations(
            title="Read own Workstream profile",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=True,
        ),
    )


def update_definition() -> Tool:
    return Tool(
        name=PROFILE_UPDATE_TOOL_NAME,
        description="Update the authenticated caller's editable Workstream profile fields.",
        input_schema=PROFILE_UPDATE_INPUT_SCHEMA,
        output_schema=profile_update_output_schema(),
        annotations=ToolAnnotations(
            title="Update own Workstream profile",
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=False,
            open_world_hint=True,
        ),
    )


def normalize_update_input(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        Draft202012Validator(PROFILE_UPDATE_INPUT_SCHEMA).validate(arguments)
    except ValidationError as exc:
        raise ValueError("invalid profile update") from exc

    normalized: dict[str, Any] = {}
    for field, value in arguments.items():
        if value is None:
            normalized[field] = None
            continue
        if "\x00" in value:
            raise ValueError("invalid profile update")
        stripped = value.strip()
        if not stripped:
            raise ValueError("invalid profile update")
        normalized[field] = stripped
    return normalized


def _success(data: dict[str, Any] | None) -> CallToolResult:
    content = data or {}
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(content, separators=(",", ":")))],
        structured_content=content,
    )


async def invoke_get(
    gateway: WorkstreamGateway, bearer: str, correlation_id: str | None
) -> CallToolResult:
    outcome = await gateway.profile_get(bearer, correlation_id)
    if outcome.failure is not None:
        return outcome.failure.result()
    return _success(outcome.data)


async def invoke_update(
    gateway: WorkstreamGateway,
    bearer: str,
    correlation_id: str | None,
    arguments: dict[str, Any],
) -> CallToolResult:
    try:
        payload = normalize_update_input(arguments)
    except ValueError:
        return adapter_failure("invalid_tool_input", status=400)
    outcome = await gateway.profile_update(bearer, payload, correlation_id)
    if outcome.failure is not None:
        return outcome.failure.result()
    return _success(outcome.data)
