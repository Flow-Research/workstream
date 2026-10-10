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
from workstream_mcp.schemas import (
    ADMIN_GRANT_INPUT_SCHEMAS,
    admin_grant_output_schema,
)

TOOL_NAMES = (
    "workstream_admin_grants_issue",
    "workstream_admin_grants_revoke",
)
_CONTRACT_NAMES = {
    "workstream_admin_grants_issue": "admin_grants_issue",
    "workstream_admin_grants_revoke": "admin_grants_revoke",
}
_DESCRIPTIONS = {
    "admin_grants_issue": (
        "Issue another actor an administrative grant. Requires Access Administrator; "
        "self-grant is forbidden."
    ),
    "admin_grants_revoke": (
        "Revoke another actor administrative grant while preserving history. "
        "Self-revocation and removal of the final effective administrator are guarded."
    ),
}
_TITLES = {
    "admin_grants_issue": "Issue administrative grant",
    "admin_grants_revoke": "Revoke administrative grant",
}
_FORMAT_CHECKER = FormatChecker()


def definitions() -> list[Tool]:
    return [
        Tool(
            name=tool_name,
            description=_DESCRIPTIONS[contract_name],
            input_schema=ADMIN_GRANT_INPUT_SCHEMAS[contract_name],
            output_schema=admin_grant_output_schema(contract_name),
            annotations=ToolAnnotations(
                title=_TITLES[contract_name],
                read_only_hint=False,
                destructive_hint=True,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        )
        for tool_name, contract_name in _CONTRACT_NAMES.items()
    ]


def _valid_arguments(contract_name: str, arguments: dict[str, Any]) -> bool:
    try:
        Draft202012Validator(
            ADMIN_GRANT_INPUT_SCHEMAS[contract_name],
            format_checker=_FORMAT_CHECKER,
        ).validate(arguments)
    except ValidationError:
        return False
    reason = arguments["body"]["reason"]
    return 1 <= len(reason.encode("utf-8")) <= 500


async def invoke(
    gateway: WorkstreamGateway,
    tool_name: str,
    bearer: str,
    correlation_id: str | None,
    arguments: dict[str, Any],
) -> CallToolResult:
    contract_name = _CONTRACT_NAMES[tool_name]
    if not _valid_arguments(contract_name, arguments):
        return adapter_failure("invalid_tool_input", status=400)
    outcome = await gateway.admin_grant_mutation(contract_name, bearer, arguments, correlation_id)
    if outcome.failure is not None:
        return outcome.failure.result()
    data = outcome.data or {}
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, separators=(",", ":")))],
        structured_content=data,
    )
