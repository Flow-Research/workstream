"""Runtime safety tests for the Workstream MCP boundary."""

from __future__ import annotations

import logging

import pytest

from workstream_mcp.auth import RequestContext
from workstream_mcp.config import WorkstreamMCPConfig
from workstream_mcp.observability import LOGGER, observe_operation
from workstream_mcp.server import main


def test_streamable_http_allowlists_are_explicitly_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Host and browser-origin policy is configured outside MCP tool inputs."""
    monkeypatch.setenv("WORKSTREAM_MCP_ALLOWED_HOSTS", "mcp.example.test, localhost:9000")
    monkeypatch.setenv("WORKSTREAM_MCP_ALLOWED_ORIGINS", "https://app.example.test")

    config = WorkstreamMCPConfig.from_environment()

    assert config.allowed_hosts == ("mcp.example.test", "localhost:9000")
    assert config.allowed_origins == ("https://app.example.test",)


def test_streamable_http_defaults_are_limited_to_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default HTTP transport access allows local development, not arbitrary origins."""
    monkeypatch.delenv("WORKSTREAM_MCP_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("WORKSTREAM_MCP_ALLOWED_ORIGINS", raising=False)

    config = WorkstreamMCPConfig.from_environment()

    assert config.allowed_hosts == ("127.0.0.1:*", "localhost:*", "[::1]:*")
    assert config.allowed_origins == (
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    )


def test_main_rejects_sse_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the WS-MCP-001-supported transports may run the server."""
    monkeypatch.setenv("WORKSTREAM_MCP_TRANSPORT", "sse")

    with pytest.raises(RuntimeError, match="stdio or streamable-http"):
        main()


@pytest.mark.asyncio
async def test_observability_never_logs_bearer_tokens(caplog: pytest.LogCaptureFixture) -> None:
    """Operation logs contain correlation metadata but never the forwarding token."""
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    context = RequestContext("issuer-token", "corr-1", "stdio")

    result = await observe_operation(
        context,
        kind="tool",
        identifier="claim_task",
        request_id="11111111-1111-4111-8111-111111111111",
        action=lambda: _successful_action(),
    )

    assert result == {"outcome": "claimed"}
    assert "issuer-token" not in caplog.text
    assert caplog.records[0].correlation_id == "corr-1"
    assert caplog.records[0].request_id == "11111111-1111-4111-8111-111111111111"


async def _successful_action() -> dict[str, str]:
    """Return a deterministic operation result for logging tests."""
    return {"outcome": "claimed"}
