from __future__ import annotations

import pytest

from workstream_mcp.config import ConfigurationError, Settings


@pytest.mark.parametrize(
    "url",
    [
        "https://workstream.example",
        "https://workstream.example/",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
)
def test_valid_api_origins_are_normalized(url: str) -> None:
    expected = url.rstrip("/")
    assert Settings(api_url=url).api_url == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://workstream.example",
        "http://workstream.example",
        "https://user:password@workstream.example",
        "https://workstream.example/path",
        "https://workstream.example?query=1",
        "https://workstream.example#fragment",
        "https://workstream.example:bad",
    ],
)
def test_unsafe_api_origins_fail_closed(url: str) -> None:
    with pytest.raises(ConfigurationError):
        Settings(api_url=url)


@pytest.mark.parametrize(
    "changes",
    [
        {"port": 0},
        {"max_request_bytes": True},
        {"max_response_bytes": 1},
        {"max_header_bytes": 1_048_577},
        {"max_request_frames": 0},
        {"max_in_flight": 0},
        {"keep_alive_seconds": 31},
        {"connect_timeout_seconds": True},
        {"read_timeout_seconds": 0.01},
        {"total_timeout_seconds": 0.01},
        {"ingress_timeout_seconds": 181},
        {"connect_timeout_seconds": 5, "read_timeout_seconds": 6, "total_timeout_seconds": 5},
        {"allowed_hosts": ()},
        {"allowed_hosts": ("",)},
        {"allowed_hosts": ("*.example.com:*",)},
        {"allowed_hosts": (".example.com:*",)},
        {"allowed_hosts": ("example.com:70000",)},
    ],
)
def test_invalid_limits_and_allowed_hosts_fail_closed(changes: dict[str, object]) -> None:
    with pytest.raises(ConfigurationError):
        Settings(api_url="https://workstream.example", **changes)  # type: ignore[arg-type]


def test_environment_requires_origin_and_parses_all_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WORKSTREAM_API_URL", raising=False)
    with pytest.raises(ConfigurationError):
        Settings.from_env()

    monkeypatch.setenv("WORKSTREAM_API_URL", "http://127.0.0.1:9000/")
    monkeypatch.setenv("WORKSTREAM_MCP_PORT", "9001")
    monkeypatch.setenv("WORKSTREAM_MCP_ALLOWED_HOSTS", "example.test:443, localhost:*")
    monkeypatch.setenv("WORKSTREAM_MCP_MAX_REQUEST_BYTES", "2048")
    monkeypatch.setenv("WORKSTREAM_MCP_MAX_RESPONSE_BYTES", "3072")
    monkeypatch.setenv("WORKSTREAM_MCP_MAX_HEADER_BYTES", "4096")
    monkeypatch.setenv("WORKSTREAM_MCP_MAX_REQUEST_FRAMES", "64")
    monkeypatch.setenv("WORKSTREAM_MCP_MAX_IN_FLIGHT", "2")
    monkeypatch.setenv("WORKSTREAM_MCP_INGRESS_TIMEOUT_SECONDS", "14")
    monkeypatch.setenv("WORKSTREAM_MCP_CONNECT_TIMEOUT_SECONDS", "2")
    monkeypatch.setenv("WORKSTREAM_MCP_READ_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("WORKSTREAM_MCP_TOTAL_TIMEOUT_SECONDS", "4")
    monkeypatch.setenv("WORKSTREAM_MCP_KEEP_ALIVE_SECONDS", "4")
    settings = Settings.from_env()
    assert settings.api_url == "http://127.0.0.1:9000"
    assert settings.port == 9001
    assert settings.allowed_hosts == ("example.test:443", "localhost:*")
    assert settings.max_request_frames == 64


@pytest.mark.parametrize(
    "name,value",
    [("WORKSTREAM_MCP_PORT", "NaN"), ("WORKSTREAM_MCP_CONNECT_TIMEOUT_SECONDS", "NaN")],
)
def test_invalid_environment_values_fail_closed(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv("WORKSTREAM_API_URL", "https://workstream.example")
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigurationError):
        Settings.from_env()
