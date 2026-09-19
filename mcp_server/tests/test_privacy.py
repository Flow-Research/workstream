from __future__ import annotations

from typing import Any

from conftest import mcp_call
from starlette.testclient import TestClient


def test_upstream_sensitive_error_body_is_not_exposed(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    client, _, upstream = adapter
    upstream.update(
        status=503,
        json={
            "error": {
                "code": "service_unavailable",
                "message": "Bearer secret-token",
                "details": {"email": "person@example.com"},
            }
        },
    )
    response = mcp_call(client, token="real-token")
    assert response.status_code == 200
    payload = response.json()["result"]["structuredContent"]
    assert payload["error"] == "workstream_request_failed"
    assert payload["status"] == 503
    assert payload["code"] == "service_unavailable"
    assert "real-token" not in response.text
    assert "secret-token" not in response.text
    assert "person@example.com" not in response.text


def test_authorized_profile_fields_are_not_blanket_filtered(
    adapter: tuple[TestClient, list[Any], dict[str, Any]],
) -> None:
    client, _, upstream = adapter
    upstream["json"].update(display_name="A name", contact_email="person@example.com")
    response = mcp_call(client)
    result = response.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["display_name"] == "A name"
    assert result["structuredContent"]["contact_email"] == "person@example.com"
