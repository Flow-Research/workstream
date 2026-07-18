"""Catalogue closure tests for the Workstream MCP server."""

from __future__ import annotations

import pytest
from mcp.server.lowlevel.server import NotificationOptions

from workstream_mcp.schemas import MCP_PROMPTS, RESOURCE_DEFINITIONS, TOOL_DEFINITIONS
from workstream_mcp.server import build_fastmcp_server, create_mcp_application


def test_catalogue_exposes_exact_resource_types_and_tools() -> None:
    """The v0.1 MCP surface is closed to the approved catalogue."""
    app = create_mcp_application(gateway=object())  # type: ignore[arg-type]

    assert [resource.name for resource in app.resources] == [
        "my_projects",
        "my_contributions",
        "tasks",
        "task_context",
        "task_status",
        "current_review",
        "review_context",
    ]
    assert [tool.name for tool in app.tools] == [
        "claim_task",
        "release_task",
        "run_pre_submit_check",
        "submit_task",
        "claim_review",
        "release_review",
        "submit_review",
    ]
    assert app.prompts == ()


def test_catalogue_contains_no_token_inputs_or_mutating_resources() -> None:
    """Identity is transport-provided and resources stay read-only."""
    all_resource_templates = [
        template for resource in RESOURCE_DEFINITIONS for template in resource.uri_templates
    ]
    all_tool_fields = [field for tool in TOOL_DEFINITIONS for field in tool.input_fields]

    assert MCP_PROMPTS == ()
    assert len(RESOURCE_DEFINITIONS) == 7
    assert len(TOOL_DEFINITIONS) == 7
    assert all(resource.mutating is False for resource in RESOURCE_DEFINITIONS)
    assert all(tool.mutating is True for tool in TOOL_DEFINITIONS)
    assert not any("token" in template.lower() for template in all_resource_templates)
    assert "bearer_token" not in all_tool_fields
    assert "authorization" not in all_tool_fields


@pytest.mark.asyncio
async def test_fastmcp_runtime_registration_matches_closed_catalogue() -> None:
    """Runtime registration must match the static WS-MCP-001 catalogue."""
    server = build_fastmcp_server(gateway=object())  # type: ignore[arg-type]

    tools = await server.list_tools()
    resources = await server.list_resources()
    resource_templates = await server.list_resource_templates()
    prompts = await server.list_prompts()

    tool_names = [tool.name for tool in tools]
    tool_schemas = {tool.name: tool.inputSchema for tool in tools}
    resource_uris = [str(resource.uri) for resource in resources]
    template_uris = [str(template.uriTemplate) for template in resource_templates]

    assert tool_names == [tool.name for tool in TOOL_DEFINITIONS]
    assert prompts == []
    assert len(resources) + len(resource_templates) == sum(
        len(resource.uri_templates) for resource in RESOURCE_DEFINITIONS
    )
    assert set(resource_uris + template_uris) == {
        template for resource in RESOURCE_DEFINITIONS for template in resource.uri_templates
    }
    for tool in TOOL_DEFINITIONS:
        schema = tool_schemas[tool.name]
        assert set(schema["properties"]) == set(tool.input_fields)
        assert "bearer_token" not in schema["properties"]
        assert "authorization" not in schema["properties"]
    assert tool_schemas["claim_task"]["required"] == ["task_id", "request_id"]
    assert tool_schemas["claim_task"]["properties"]["request_id"]["format"] == "uuid"
    assert "summary" in tool_schemas["submit_task"]["$defs"]["SubmissionInput"]["properties"]
    assert tool_schemas["submit_review"]["properties"]["decision"]["enum"] == [
        "accept",
        "needs_revision",
        "reject",
    ]
    assert tool_schemas["submit_review"]["required"] == [
        "review_ref",
        "decision",
        "findings",
        "request_id",
    ]


def test_runtime_does_not_advertise_resource_subscriptions_or_list_events() -> None:
    """The v0.1 server is pull-based and exposes no subscription/event channel."""
    server = build_fastmcp_server(gateway=object())  # type: ignore[arg-type]

    capabilities = server._mcp_server.get_capabilities(  # noqa: SLF001
        NotificationOptions(),
        {},
    )

    assert capabilities.resources is not None
    assert capabilities.resources.subscribe is False
    assert capabilities.resources.listChanged is False
    assert capabilities.tools is not None
    assert capabilities.tools.listChanged is False
    assert capabilities.experimental == {}
    assert capabilities.tasks is None
