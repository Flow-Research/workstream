from __future__ import annotations

import asyncio
import json
import typing
from typing import Any

import pytest
from conftest import mcp_call
from starlette.testclient import TestClient

from workstream_mcp.config import Settings
from workstream_mcp.server import create_app
from workstream_mcp.tools.context import TOOL_NAME as CONTEXT_TOOL_NAME
from workstream_mcp.tools.profile import PROFILE_UPDATE_TOOL_NAME


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("unknown", {}),
        ("workstream_profile_get", {"actor_id": "other"}),
        ("workstream_profile_get", {"authorization": "override"}),
        ("workstream_profile_get", {"url": "https://invalid.example"}),
    ],
)
def test_unknown_tools_and_input_injection_do_not_dispatch(
    adapter: tuple[TestClient, list[Any], dict[str, Any]], name: str, arguments: dict[str, Any]
) -> None:
    client, received, _ = adapter
    response = mcp_call(client, name=name, arguments=arguments)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["result"]["isError"] is True
    assert received == []


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({"origin": "https://invalid.example"}, 403),
        ({"content-length": "-1"}, 413),
        ({"content-length": "not-a-number"}, 413),
        ({"x-large": "x" * 17000}, 431),
    ],
)
def test_ingress_rejections_are_not_cached_or_dispatched(
    adapter: tuple[TestClient, list[Any], dict[str, Any]], headers: dict[str, str], status: int
) -> None:
    client, received, _ = adapter
    response = mcp_call(client, extra_headers=headers)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert received == []


def test_duplicate_authorization_does_not_dispatch(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    client, received, _ = adapter
    response = client.post(
        "/mcp",
        headers=[
            ("accept", "application/json, text/event-stream"),
            ("authorization", "Bearer first"),
            ("authorization", "Bearer second"),
        ],
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "workstream_profile_get", "arguments": {}},
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["isError"] is True
    assert received == []


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        (PROFILE_UPDATE_TOOL_NAME, {}),
        (PROFILE_UPDATE_TOOL_NAME, {"display_name": "   "}),
        (PROFILE_UPDATE_TOOL_NAME, {"display_name": 7}),
        (PROFILE_UPDATE_TOOL_NAME, {"display_name": "d" * 201}),
        (PROFILE_UPDATE_TOOL_NAME, {"contact_email": "e" * 321}),
        (
            PROFILE_UPDATE_TOOL_NAME,
            {"display_name": "valid", "contact_email": "   "},
        ),
        (PROFILE_UPDATE_TOOL_NAME, {"display_name": "valid", "extra": "denied"}),
        (PROFILE_UPDATE_TOOL_NAME, {"display_name": "bad\x00value"}),
        (CONTEXT_TOOL_NAME, {}),
        (CONTEXT_TOOL_NAME, {"project_id": ""}),
        (CONTEXT_TOOL_NAME, {"project_id": None}),
        (CONTEXT_TOOL_NAME, {"project_id": 7}),
        (CONTEXT_TOOL_NAME, {"project_id": "bad\x00project"}),
        (CONTEXT_TOOL_NAME, {"project_id": "p" * 101}),
        (CONTEXT_TOOL_NAME, {"project_id": "project", "url": "https://invalid.example"}),
    ],
)
def test_new_tool_invalid_inputs_do_not_dispatch(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
    name: str,
    arguments: dict[str, Any],
) -> None:
    client, received, _ = adapter
    response = mcp_call(client, name=name, arguments=arguments)
    assert response.status_code == 200
    assert response.json()["result"]["isError"] is True
    assert received == []


def test_profile_update_normalizes_text_and_preserves_omission_and_null(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    client, received, upstream = adapter
    upstream["json"] = {**upstream["json"], "display_name": "Victor", "contact_email": None}

    first = mcp_call(
        client,
        name=PROFILE_UPDATE_TOOL_NAME,
        arguments={"display_name": "  Victor  "},
    )
    second = mcp_call(
        client,
        name=PROFILE_UPDATE_TOOL_NAME,
        arguments={"contact_email": None},
    )

    assert first.json()["result"].get("isError", False) is False
    assert second.json()["result"].get("isError", False) is False
    assert json.loads(received[0].content) == {"display_name": "Victor"}
    assert json.loads(received[1].content) == {"contact_email": None}
    assert all(request.method == "PATCH" for request in received)


def test_new_tools_accept_exact_maximum_input_lengths(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    client, received, upstream = adapter
    display_name = "d" * 200
    contact_email = "e" * 320
    project_id = "p" * 100

    profile_response = mcp_call(
        client,
        name=PROFILE_UPDATE_TOOL_NAME,
        arguments={"display_name": display_name, "contact_email": contact_email},
    )
    assert profile_response.json()["result"].get("isError", False) is False
    assert json.loads(received[0].content) == {
        "display_name": display_name,
        "contact_email": contact_email,
    }

    from conftest import authorization_context_fixture

    upstream["json"] = authorization_context_fixture()
    context_response = mcp_call(
        client,
        name=CONTEXT_TOOL_NAME,
        arguments={"project_id": project_id},
    )
    assert context_response.json()["result"].get("isError", False) is False
    assert received[1].url.params["project_id"] == project_id


def test_authorization_context_forwards_caller_and_exact_project(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    from conftest import authorization_context_fixture

    client, received, upstream = adapter
    upstream["json"] = authorization_context_fixture()
    response = mcp_call(
        client,
        token="context-caller",
        name=CONTEXT_TOOL_NAME,
        arguments={"project_id": "project/one"},
    )

    assert response.json()["result"].get("isError", False) is False
    assert len(received) == 1
    assert received[0].headers["authorization"] == "Bearer context-caller"
    assert received[0].url.params["project_id"] == "project/one"


def test_authorization_context_concealment_returns_no_stale_authority(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    client, received, upstream = adapter
    upstream["status"] = 404
    upstream["json"] = {
        "error": {
            "code": "project_authorization_resource_not_found",
            "message": "private project detail",
            "details": {"project_roles": ["submitter"], "effective_action_ids": ["task.claim"]},
        }
    }
    response = mcp_call(
        client,
        name=CONTEXT_TOOL_NAME,
        arguments={"project_id": "project/one"},
    )

    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["status"] == 404
    assert result["structuredContent"]["code"] == "project_authorization_resource_not_found"
    serialized = json.dumps(result)
    assert "private project detail" not in serialized
    assert "project_roles" not in serialized
    assert "effective_action_ids" not in serialized
    assert len(received) == 1


def test_every_response_is_no_store_and_profile_is_not_cross_caller_cached(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    client, received, upstream = adapter
    upstream["json"]["actor_profile_id"] = "alice"
    alice = mcp_call(client, token="alice")
    upstream["json"] = {**upstream["json"], "actor_profile_id": "bob"}
    bob = mcp_call(client, token="bob")
    assert alice.headers["cache-control"] == bob.headers["cache-control"] == "no-store"
    assert alice.json()["result"]["structuredContent"]["actor_profile_id"] == "alice"
    assert bob.json()["result"]["structuredContent"]["actor_profile_id"] == "bob"
    assert [request.headers["authorization"] for request in received] == [
        "Bearer alice",
        "Bearer bob",
    ]


@pytest.mark.asyncio
async def test_cancellation_reaches_running_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    from workstream_mcp.http_gateway import GatewayResult

    tool_call_started = asyncio.Event()
    tool_call_cancelled = asyncio.Event()

    async def hanging_profile_get(*args: typing.Any, **kwargs: typing.Any) -> GatewayResult:
        tool_call_started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            tool_call_cancelled.set()
            raise
        return GatewayResult(data={"actor_profile_id": "profile-1"})

    monkeypatch.setattr(
        "workstream_mcp.http_gateway.WorkstreamGateway.profile_get", hanging_profile_get
    )
    settings = Settings(api_url="http://127.0.0.1:8000")
    app = create_app(settings)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": [
            (b"host", b"127.0.0.1:8080"),
            (b"accept", b"application/json, text/event-stream"),
            (b"authorization", b"Bearer token"),
            (b"content-type", b"application/json"),
        ],
    }

    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "workstream_profile_get", "arguments": {}},
        }
    ).encode("utf-8")

    receive_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    await receive_queue.put({"type": "http.request", "body": body, "more_body": False})

    async def receive() -> dict[str, Any]:
        return await receive_queue.get()

    async def send(message: typing.MutableMapping[str, typing.Any]) -> None:
        pass

    async with app.router.lifespan_context(app):
        # Start the ASGI app in the background
        app_task = asyncio.create_task(app(scope, receive, send))

        # Wait for profile_get to start
        await asyncio.wait_for(tool_call_started.wait(), timeout=1.0)

        # Simulate client disconnect (this is how stateless mode cancels)
        await receive_queue.put({"type": "http.disconnect"})

        # Verify the cancellation reaches the running tool call
        await asyncio.wait_for(tool_call_cancelled.wait(), timeout=1.0)

        # Cleanup
        app_task.cancel()
        try:
            await app_task
        except asyncio.CancelledError:
            pass




@pytest.mark.asyncio
async def test_asgi_ingress_limits() -> None:
    settings = Settings(
        api_url="http://127.0.0.1:8000",
        max_request_frames=2,
        max_request_bytes=1024,
        ingress_timeout_seconds=0.1,
    )
    app = create_app(settings)
    scope = {"type": "http", "method": "POST", "path": "/mcp", "headers": [(b"host", b"127.0.0.1")]}
    
    # 1. Test Frame Limit
    from collections.abc import MutableMapping
    receive_queue: asyncio.Queue[MutableMapping[str, Any]] = asyncio.Queue()
    for _ in range(5):
        receive_queue.put_nowait({"type": "http.request", "body": b" ", "more_body": True})
    receive_queue.put_nowait({"type": "http.request", "body": b"{}", "more_body": False})
    
    send_queue: asyncio.Queue[MutableMapping[str, Any]] = asyncio.Queue()
    await app(scope, receive_queue.get, send_queue.put)
    resp = await send_queue.get()
    assert resp["status"] == 400
    body = await send_queue.get()
    assert isinstance(body["body"], bytes)
    assert json.loads(body["body"])["error"] == "request_ingress_limit"
    
    # 2. Test Timeout
    async def slow_receive() -> MutableMapping[str, Any]:
        await asyncio.sleep(0.2)
        return {"type": "http.request", "body": b"{}", "more_body": False}
        
    send_queue = asyncio.Queue()
    await app(scope, slow_receive, send_queue.put)
    resp = await send_queue.get()
    assert resp["status"] == 408
    
    # 3. Test Payload Size Limit
    receive_queue = asyncio.Queue()
    receive_queue.put_nowait({"type": "http.request", "body": b" " * 1025, "more_body": False})
    send_queue = asyncio.Queue()
    await app(scope, receive_queue.get, send_queue.put)
    resp = await send_queue.get()
    assert resp["status"] == 413
