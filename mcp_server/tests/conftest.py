from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import httpx2 as httpx
import pytest
from starlette.testclient import TestClient

from workstream_mcp.config import Settings
from workstream_mcp.server import create_app


def profile_fixture(**overrides: Any) -> dict[str, Any]:
    profile = {
        "actor_profile_id": "profile-1",
        "actor_kind": "human",
        "status": "active",
        "domains": ["contributor"],
        "admin_roles": [],
        "project_role_grants": [],
        "display_name": None,
        "contact_email": None,
        "created_at": "2026-09-15T10:00:00Z",
        "updated_at": "2026-09-15T10:00:00Z",
        "last_seen_at": None,
    }
    profile.update(overrides)
    return profile


def authorization_context_fixture(**overrides: Any) -> dict[str, Any]:
    context = {
        "actor_profile_id": "caa1b82d-ef2d-43fd-a1dd-c65981940796",
        "status": "active",
        "project_id": "0cd81e1e-0844-4a1b-9cb9-9d4cb2c99418",
        "admin_roles": [],
        "project_roles": ["submitter"],
        "effective_action_ids": ["task.claim"],
    }
    context.update(overrides)
    return context


@pytest.fixture
def adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, list[httpx.Request], dict[str, Any]]]:
    received: list[httpx.Request] = []
    upstream: dict[str, Any] = {
        "status": 200,
        "json": profile_fixture(),
        "headers": {"content-type": "application/json"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(
            upstream["status"], json=upstream["json"], headers=upstream["headers"], request=request
        )

    def fake_client(_: Settings) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url="http://workstream.test",
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
            trust_env=False,
        )

    monkeypatch.setattr("workstream_mcp.server.create_http_client", fake_client)
    settings = Settings(api_url="http://127.0.0.1:8000")
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8080") as client:
        yield client, received, upstream


def mcp_call(
    client: TestClient,
    *,
    token: str | None = "fixture-token",
    name: str = "workstream_profile_get",
    arguments: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> httpx.Response:
    headers = {"accept": "application/json, text/event-stream"}
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    headers.update(extra_headers or {})
    return client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        },
    )


@pytest.fixture
def call() -> Callable[..., httpx.Response]:
    return mcp_call
