"""Runtime safety tests for the Workstream MCP boundary."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from workstream_mcp.auth import RequestContext
from workstream_mcp.auth import WorkstreamForwardingTokenVerifier
from workstream_mcp.config import WorkstreamMCPConfig
from workstream_mcp.observability import LOGGER, observe_operation
from workstream_mcp.server import (
    MAX_HTTP_REQUEST_BODY_BYTES,
    _RequestBodyLimitMiddleware,
    build_fastmcp_server,
    main,
)


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


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("WORKSTREAM_API_BASE_URL", "http://api.example.test", "must use HTTPS"),
        ("WORKSTREAM_API_BASE_URL", "https://user:secret@api.example.test", "credentials"),
        ("WORKSTREAM_MCP_REQUEST_TIMEOUT_SECONDS", "0", "positive and finite"),
        ("WORKSTREAM_MCP_REQUEST_TIMEOUT_SECONDS", "nan", "positive and finite"),
        ("WORKSTREAM_MCP_ALLOWED_HOSTS", " , ", "allowlists must not be empty"),
    ],
)
def test_runtime_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    """Unsafe token destinations, timeouts, and empty transport allowlists are rejected."""
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        WorkstreamMCPConfig.from_environment()


def test_main_rejects_sse_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the WS-MCP-001-supported transports may run the server."""
    monkeypatch.setenv("WORKSTREAM_MCP_TRANSPORT", "sse")

    with pytest.raises(RuntimeError, match="stdio or streamable-http"):
        main()


def test_streamable_http_requires_explicit_https_auth_issuer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP transport cannot start with missing or implicit cleartext auth trust."""
    monkeypatch.delenv("WORKSTREAM_MCP_AUTH_ISSUER_URL", raising=False)
    monkeypatch.delenv("WORKSTREAM_MCP_ALLOW_INSECURE_AUTH_ISSUER", raising=False)

    with pytest.raises(ValueError, match="AUTH_ISSUER_URL is required"):
        build_fastmcp_server(gateway=object(), transport="streamable-http")  # type: ignore[arg-type]

    monkeypatch.setenv("WORKSTREAM_MCP_AUTH_ISSUER_URL", "http://issuer.example.test")
    with pytest.raises(ValueError, match="must use HTTPS"):
        build_fastmcp_server(gateway=object(), transport="streamable-http")  # type: ignore[arg-type]


def test_streamable_http_allows_https_or_explicit_local_development_issuer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only HTTPS or deliberate loopback development issuers configure HTTP auth."""
    monkeypatch.setenv("WORKSTREAM_MCP_AUTH_ISSUER_URL", "https://issuer.example.test")
    https_server = build_fastmcp_server(
        gateway=object(),  # type: ignore[arg-type]
        transport="streamable-http",
    )

    monkeypatch.setenv("WORKSTREAM_MCP_AUTH_ISSUER_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("WORKSTREAM_MCP_ALLOW_INSECURE_AUTH_ISSUER", "true")
    local_server = build_fastmcp_server(
        gateway=object(),  # type: ignore[arg-type]
        transport="streamable-http",
    )

    assert https_server is not None
    assert local_server is not None
    assert str(https_server.settings.auth.issuer_url).rstrip("/") == (
        "https://issuer.example.test"
    )
    assert isinstance(https_server._token_verifier, WorkstreamForwardingTokenVerifier)  # noqa: SLF001

    stdio_server = build_fastmcp_server(
        gateway=object(),  # type: ignore[arg-type]
        transport="stdio",
    )
    assert stdio_server.settings.auth is None
    assert stdio_server._token_verifier is None  # noqa: SLF001


def test_insecure_auth_issuer_override_is_strict_and_loopback_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The development override cannot enable remote cleartext issuer trust."""
    monkeypatch.setenv("WORKSTREAM_MCP_ALLOW_INSECURE_AUTH_ISSUER", "sometimes")
    with pytest.raises(ValueError, match="must be true or false"):
        WorkstreamMCPConfig.from_environment()

    monkeypatch.setenv("WORKSTREAM_MCP_ALLOW_INSECURE_AUTH_ISSUER", "true")
    monkeypatch.setenv("WORKSTREAM_MCP_AUTH_ISSUER_URL", "http://issuer.example.test")
    config = WorkstreamMCPConfig.from_environment()
    with pytest.raises(ValueError, match="must use HTTPS"):
        config.streamable_http_auth_issuer_url()


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
    assert caplog.records[0].started_at.endswith("+00:00")
    assert caplog.records[0].outcome_class == "success"
    assert caplog.records[0].retryable is False
    assert caplog.records[0].idempotent_replay is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "expected_class"),
    [
        ("workstream_temporarily_unavailable", "infrastructure_error"),
        ("invalid_token", "authentication_error"),
        ("capability_not_granted", "authorization_error"),
        ("task_not_claimable", "domain_error"),
    ],
)
async def test_observability_classifies_safe_error_results(
    caplog: pytest.LogCaptureFixture,
    code: str,
    expected_class: str,
) -> None:
    """Operation telemetry classifies only stable error metadata."""
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    request_context = RequestContext("issuer-token", "corr-1", "stdio")

    async def result() -> dict[str, object]:
        return {"error": {"code": code, "retryable": True}}

    await observe_operation(
        request_context,
        kind="tool",
        identifier="test_tool",
        action=result,
    )

    assert caplog.records[-1].outcome_class == expected_class
    assert caplog.records[-1].retryable is True


@pytest.mark.asyncio
async def test_observability_marks_nested_replays_and_reraises_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Replay telemetry is recursive and unexpected exceptions are not swallowed."""
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    request_context = RequestContext("issuer-token", "corr-1", "stdio")

    async def replayed() -> dict[str, object]:
        return {"data": [{"idempotent_replay": True}]}

    async def failed() -> dict[str, object]:
        raise RuntimeError("boom")

    await observe_operation(
        request_context,
        kind="tool",
        identifier="replayed_tool",
        action=replayed,
    )
    assert caplog.records[-1].idempotent_replay is True

    with pytest.raises(RuntimeError, match="boom"):
        await observe_operation(
            request_context,
            kind="tool",
            identifier="failed_tool",
            action=failed,
        )
    assert caplog.records[-1].outcome_class == "infrastructure_error"


@pytest.mark.asyncio
async def test_streamable_http_rejects_oversized_body_before_mcp_app() -> None:
    """The HTTP adapter rejects oversized bodies before downstream JSON parsing."""
    app_called = False
    sent: list[dict[str, object]] = []

    async def app(scope: object, receive: object, send: object) -> None:
        nonlocal app_called
        app_called = True

    async def receive() -> dict[str, object]:
        return {
            "type": "http.request",
            "body": b"x" * (MAX_HTTP_REQUEST_BODY_BYTES + 1),
            "more_body": False,
        }

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    middleware = _RequestBodyLimitMiddleware(app, max_bytes=MAX_HTTP_REQUEST_BODY_BYTES)
    await middleware(
        {"type": "http", "method": "POST", "headers": []},
        receive,
        send,
    )

    assert app_called is False
    assert sent[0]["status"] == 413


@pytest.mark.asyncio
async def test_streamable_http_body_limit_replays_bounded_request() -> None:
    """A bounded HTTP body reaches the MCP app unchanged."""
    received_by_app: list[dict[str, object]] = []
    sent: list[dict[str, object]] = []

    async def app(scope: object, receive: Any, send: Any) -> None:
        received_by_app.append(await receive())
        await send({"type": "http.response.start", "status": 200, "headers": []})

    messages = [
        {"type": "http.request", "body": b"bounded", "more_body": False},
    ]

    async def receive() -> dict[str, object]:
        return messages.pop(0)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    middleware = _RequestBodyLimitMiddleware(app, max_bytes=MAX_HTTP_REQUEST_BODY_BYTES)
    await middleware(
        {
            "type": "http",
            "method": "POST",
            "headers": [(b"content-length", b"invalid")],
        },
        receive,
        send,
    )

    assert received_by_app == [
        {"type": "http.request", "body": b"bounded", "more_body": False}
    ]
    assert sent[0]["status"] == 200


@pytest.mark.asyncio
async def test_streamable_http_body_limit_short_circuits_by_method_and_length() -> None:
    """Non-body methods pass through and oversized content length fails immediately."""
    app_calls = 0
    sent: list[dict[str, object]] = []

    async def app(scope: object, receive: Any, send: Any) -> None:
        nonlocal app_calls
        app_calls += 1

    async def receive() -> dict[str, object]:
        raise AssertionError("oversized declared bodies must not be read")

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    middleware = _RequestBodyLimitMiddleware(app, max_bytes=MAX_HTTP_REQUEST_BODY_BYTES)
    await middleware({"type": "http", "method": "GET", "headers": []}, receive, send)
    await middleware(
        {
            "type": "http",
            "method": "POST",
            "headers": [
                (b"content-length", str(MAX_HTTP_REQUEST_BODY_BYTES + 1).encode("ascii"))
            ],
        },
        receive,
        send,
    )

    assert app_calls == 1
    assert sent[0]["status"] == 413


@pytest.mark.asyncio
async def test_streamable_http_body_limit_bounds_empty_continuation_frames() -> None:
    """Zero-length continuation chunks cannot grow buffered ASGI state."""
    app_called = False
    sent: list[dict[str, object]] = []
    frames = [
        {"type": "http.request", "body": b"", "more_body": True},
        {"type": "http.request", "body": b"", "more_body": True},
        {"type": "http.request", "body": b"", "more_body": True},
    ]

    async def app(scope: object, receive: Any, send: Any) -> None:
        nonlocal app_called
        app_called = True

    async def receive() -> dict[str, object]:
        return frames.pop(0)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    middleware = _RequestBodyLimitMiddleware(
        app,
        max_bytes=MAX_HTTP_REQUEST_BODY_BYTES,
        max_frames=2,
    )
    await middleware(
        {"type": "http", "method": "POST", "headers": []},
        receive,
        send,
    )

    assert app_called is False
    assert sent[0]["status"] == 413
    assert frames == []


@pytest.mark.asyncio
async def test_streamable_http_body_limit_preserves_disconnect_order() -> None:
    """A mid-body disconnect follows the coalesced partial request downstream."""
    replayed: list[dict[str, object]] = []
    frames = [
        {"type": "http.request", "body": b"partial", "more_body": True},
        {"type": "http.disconnect"},
    ]

    async def app(scope: object, receive: Any, send: Any) -> None:
        replayed.append(await receive())
        replayed.append(await receive())

    async def receive() -> dict[str, object]:
        return frames.pop(0)

    async def send(message: dict[str, object]) -> None:
        return None

    middleware = _RequestBodyLimitMiddleware(
        app,
        max_bytes=MAX_HTTP_REQUEST_BODY_BYTES,
    )
    await middleware(
        {"type": "http", "method": "POST", "headers": []},
        receive,
        send,
    )

    assert replayed == [
        {"type": "http.request", "body": b"partial", "more_body": True},
        {"type": "http.disconnect"},
    ]


@pytest.mark.asyncio
async def test_streamable_http_body_limit_delegates_after_replay() -> None:
    """Response listeners receive the real client disconnect after body replay."""
    replayed: list[dict[str, object]] = []
    frames = [
        {"type": "http.request", "body": b"complete", "more_body": False},
        {"type": "http.disconnect", "reason": "client_closed"},
    ]

    async def app(scope: object, receive: Any, send: Any) -> None:
        replayed.append(await receive())
        replayed.append(await receive())

    async def receive() -> dict[str, object]:
        return frames.pop(0)

    async def send(message: dict[str, object]) -> None:
        return None

    middleware = _RequestBodyLimitMiddleware(
        app,
        max_bytes=MAX_HTTP_REQUEST_BODY_BYTES,
    )
    await middleware(
        {"type": "http", "method": "POST", "headers": []},
        receive,
        send,
    )

    assert replayed == [
        {"type": "http.request", "body": b"complete", "more_body": False},
        {"type": "http.disconnect", "reason": "client_closed"},
    ]


@pytest.mark.asyncio
async def test_streamable_http_body_limit_times_out_stalled_upload() -> None:
    """An incomplete request body cannot hold the MCP receiver indefinitely."""
    app_called = False
    sent: list[dict[str, object]] = []

    async def app(scope: object, receive: Any, send: Any) -> None:
        nonlocal app_called
        app_called = True

    async def receive() -> dict[str, object]:
        await asyncio.sleep(1)
        return {"type": "http.request", "body": b"", "more_body": True}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    middleware = _RequestBodyLimitMiddleware(
        app,
        max_bytes=MAX_HTTP_REQUEST_BODY_BYTES,
        receive_timeout_seconds=0.001,
    )
    await middleware(
        {"type": "http", "method": "POST", "headers": []},
        receive,
        send,
    )

    assert app_called is False
    assert sent[0]["status"] == 408


def test_streamable_http_authentication_precedes_body_buffering() -> None:
    """Unauthenticated requests are rejected before request-body buffering."""
    server = build_fastmcp_server(
        gateway=object(),  # type: ignore[arg-type]
        config=WorkstreamMCPConfig(
            workstream_api_base_url="https://api.example.test",
            request_timeout_seconds=1,
            allowed_hosts=("mcp.example.test",),
            allowed_origins=("https://client.example.test",),
            auth_issuer_url="https://auth.example.test",
        ),
        transport="streamable-http",
    )

    middleware_names = [entry.cls.__name__ for entry in server.streamable_http_app().user_middleware]

    assert middleware_names.index("AuthenticationMiddleware") < middleware_names.index(
        "_RequestBodyLimitMiddleware"
    )


async def _successful_action() -> dict[str, str]:
    """Return a deterministic operation result for logging tests."""
    return {"outcome": "claimed"}
