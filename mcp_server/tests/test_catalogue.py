from __future__ import annotations

from typing import Any

from starlette.testclient import TestClient

from workstream_mcp.schemas import INPUT_SCHEMA, profile_output_schema
from workstream_mcp.tools.profile import TOOL_NAME, definition


def test_only_profile_tool_has_closed_empty_input_and_selected_output() -> None:
    tool = definition()
    assert tool.name == TOOL_NAME
    assert (
        tool.input_schema
        == INPUT_SCHEMA
        == {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
    )
    assert tool.output_schema == profile_output_schema()
    assert tool.annotations is not None
    # First admission can create an actor/link, so this must not be advertised as side-effect-free.
    assert tool.annotations.read_only_hint is False


def test_mcp_tool_listing_exposes_exactly_one_tool(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    client, _, _ = adapter
    response = client.post(
        "/mcp",
        headers={"accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200
    listed = response.json()["result"]["tools"]
    assert [item["name"] for item in listed] == [TOOL_NAME]
    assert listed[0]["inputSchema"] == INPUT_SCHEMA
    assert listed[0]["outputSchema"] == profile_output_schema()


def test_capabilities_expose_tools_but_no_resources_or_prompts_legacy(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    client, _, _ = adapter
    response = client.post(
        "/mcp",
        headers={"accept": "application/json, text/event-stream"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "catalogue-test", "version": "0"},
            },
        },
    )
    assert response.status_code == 200
    capabilities = response.json()["result"]["capabilities"]
    assert "tools" in capabilities
    assert "resources" not in capabilities
    assert "prompts" not in capabilities


def test_discover_exposes_capabilities_on_modern_2026_path(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    client, _, _ = adapter
    response = client.post(
        "/mcp",
        headers={
            "accept": "application/json, text/event-stream",
            "mcp-protocol-version": "2026-07-28",
            "mcp-method": "server/discover",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "server/discover",
            "params": {
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientInfo": {
                        "name": "catalogue-test",
                        "version": "0",
                    },
                    "io.modelcontextprotocol/clientCapabilities": {},
                }
            },
        },
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert "2026-07-28" in result["supportedVersions"]
    assert "tools" in result["capabilities"]
    assert "resources" not in result["capabilities"]
    assert "prompts" not in result["capabilities"]
