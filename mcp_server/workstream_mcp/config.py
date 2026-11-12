from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from workstream_mcp.limits import GUIDE_DOCUMENT_MAX_BYTES, MCP_MAX_REQUEST_BYTES
from workstream_mcp.oauth import OAuthSettings


class ConfigurationError(ValueError):
    """Raised when deployment configuration is unsafe or inconsistent."""


def _integer(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _seconds(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _api_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        _port = parsed.port
    except ValueError as exc:
        raise ConfigurationError("WORKSTREAM_API_URL has an invalid port") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ConfigurationError("WORKSTREAM_API_URL must be an origin without credentials")
    try:
        is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        is_loopback = parsed.hostname == "localhost"
    if parsed.scheme != "https" and not is_loopback:
        raise ConfigurationError("WORKSTREAM_API_URL must use HTTPS outside loopback")
    return value.rstrip("/")


@dataclass(frozen=True, slots=True)
class Settings:
    api_url: str
    oauth: OAuthSettings = field(
        default_factory=lambda: OAuthSettings(
            issuer="https://identity.flowresearch.tech/realms/flow",
            resource="https://workstream.flowresearch.tech/mcp",
            secret_file=Path("/run/secrets/mcp-exchange-secret"),
        )
    )
    host: str = "127.0.0.1"
    port: int = 8080
    allowed_hosts: tuple[str, ...] = ("127.0.0.1:*", "localhost:*")
    max_request_bytes: int = MCP_MAX_REQUEST_BYTES
    max_response_bytes: int = 65_536
    max_document_bytes: int = GUIDE_DOCUMENT_MAX_BYTES
    max_header_bytes: int = 16_384
    max_request_frames: int = 128
    max_in_flight: int = 8
    ingress_timeout_seconds: float = 15.0
    connect_timeout_seconds: float = 3.0
    read_timeout_seconds: float = 10.0
    total_timeout_seconds: float = 12.0
    document_timeout_seconds: float = 120.0
    keep_alive_seconds: int = 5

    def __post_init__(self) -> None:
        object.__setattr__(self, "api_url", _api_url(self.api_url))
        bounds: tuple[tuple[str, int, int, int], ...] = (
            ("port", self.port, 1, 65_535),
            ("max_request_bytes", self.max_request_bytes, 1_024, MCP_MAX_REQUEST_BYTES),
            (
                "max_response_bytes",
                self.max_response_bytes,
                1_024,
                1_048_576,
            ),
            (
                "max_document_bytes",
                self.max_document_bytes,
                1_024,
                GUIDE_DOCUMENT_MAX_BYTES,
            ),
            ("max_header_bytes", self.max_header_bytes, 1_024, 65_536),
            ("max_request_frames", self.max_request_frames, 1, 4_096),
            ("max_in_flight", self.max_in_flight, 1, 256),
            ("keep_alive_seconds", self.keep_alive_seconds, 1, 30),
        )
        for name, value, minimum, maximum in bounds:
            if isinstance(value, bool) or not minimum <= value <= maximum:
                raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
        timeout_bounds: tuple[tuple[str, float, float, float], ...] = (
            ("connect_timeout_seconds", self.connect_timeout_seconds, 0.1, 60),
            ("read_timeout_seconds", self.read_timeout_seconds, 0.1, 120),
            ("total_timeout_seconds", self.total_timeout_seconds, 0.1, 180),
            ("document_timeout_seconds", self.document_timeout_seconds, 1, 600),
            ("ingress_timeout_seconds", self.ingress_timeout_seconds, 0.1, 180),
        )
        for timeout_name, timeout_value, timeout_minimum, timeout_maximum in timeout_bounds:
            if (
                isinstance(timeout_value, bool)
                or not timeout_minimum <= timeout_value <= timeout_maximum
            ):
                raise ConfigurationError(
                    f"{timeout_name} must be between {timeout_minimum} and {timeout_maximum}"
                )
        if self.total_timeout_seconds < max(
            self.connect_timeout_seconds, self.read_timeout_seconds
        ):
            raise ConfigurationError("total timeout cannot be shorter than operation timeouts")
        if self.document_timeout_seconds < self.connect_timeout_seconds:
            raise ConfigurationError("document timeout cannot be shorter than connect timeout")
        if not self.allowed_hosts or any(not item.strip() for item in self.allowed_hosts):
            raise ConfigurationError("at least one non-empty allowed host is required")
        for allowed_host in self.allowed_hosts:
            if ":" in allowed_host:
                host, _, port = allowed_host.rpartition(":")
                if not host or (port != "*" and not port.isdigit()):
                    raise ConfigurationError(
                        "allowed hosts with colon must include a valid port or :*"
                    )
                if port.isdigit() and not 1 <= int(port) <= 65_535:
                    raise ConfigurationError("allowed host port is invalid")
            else:
                host = allowed_host

            if "*" in host or host.startswith(".") or host.endswith("."):
                raise ConfigurationError("wildcard hostnames are not allowed")

    @classmethod
    def from_env(cls) -> Settings:
        api_url = os.getenv("WORKSTREAM_API_URL")
        if not api_url:
            raise ConfigurationError("WORKSTREAM_API_URL is required")
        allowed_hosts = tuple(
            item.strip()
            for item in os.getenv("WORKSTREAM_MCP_ALLOWED_HOSTS", "127.0.0.1:*,localhost:*").split(
                ","
            )
        )
        return cls(
            api_url=api_url,
            oauth=OAuthSettings(
                issuer=os.getenv(
                    "WORKSTREAM_MCP_TOKEN_ISSUER", "https://identity.flowresearch.tech/realms/flow"
                ),
                resource=os.getenv(
                    "WORKSTREAM_MCP_RESOURCE_URL", "https://workstream.flowresearch.tech/mcp"
                ),
                secret_file=Path(
                    os.getenv(
                        "WORKSTREAM_MCP_EXCHANGE_SECRET_FILE", "/run/secrets/mcp-exchange-secret"
                    )
                ),
                client_id=os.getenv("WORKSTREAM_MCP_EXCHANGE_CLIENT_ID", "workstream-mcp"),
                api_audience=os.getenv("WORKSTREAM_MCP_API_AUDIENCE", "workstream-api"),
            ),
            host=os.getenv("WORKSTREAM_MCP_HOST", "127.0.0.1"),
            port=_integer("WORKSTREAM_MCP_PORT", 8080, minimum=1, maximum=65_535),
            allowed_hosts=allowed_hosts,
            max_request_bytes=_integer(
                "WORKSTREAM_MCP_MAX_REQUEST_BYTES",
                MCP_MAX_REQUEST_BYTES,
                minimum=1_024,
                maximum=MCP_MAX_REQUEST_BYTES,
            ),
            max_response_bytes=_integer(
                "WORKSTREAM_MCP_MAX_RESPONSE_BYTES",
                65_536,
                minimum=1_024,
                maximum=1_048_576,
            ),
            max_document_bytes=_integer(
                "WORKSTREAM_MCP_MAX_DOCUMENT_BYTES",
                GUIDE_DOCUMENT_MAX_BYTES,
                minimum=1_024,
                maximum=GUIDE_DOCUMENT_MAX_BYTES,
            ),
            max_header_bytes=_integer(
                "WORKSTREAM_MCP_MAX_HEADER_BYTES", 16_384, minimum=1_024, maximum=65_536
            ),
            max_request_frames=_integer(
                "WORKSTREAM_MCP_MAX_REQUEST_FRAMES", 128, minimum=1, maximum=4_096
            ),
            max_in_flight=_integer("WORKSTREAM_MCP_MAX_IN_FLIGHT", 8, minimum=1, maximum=256),
            ingress_timeout_seconds=_seconds(
                "WORKSTREAM_MCP_INGRESS_TIMEOUT_SECONDS", 15, minimum=0.1, maximum=180
            ),
            connect_timeout_seconds=_seconds(
                "WORKSTREAM_MCP_CONNECT_TIMEOUT_SECONDS", 3, minimum=0.1, maximum=60
            ),
            read_timeout_seconds=_seconds(
                "WORKSTREAM_MCP_READ_TIMEOUT_SECONDS", 10, minimum=0.1, maximum=120
            ),
            total_timeout_seconds=_seconds(
                "WORKSTREAM_MCP_TOTAL_TIMEOUT_SECONDS", 12, minimum=0.1, maximum=180
            ),
            document_timeout_seconds=_seconds(
                "WORKSTREAM_MCP_DOCUMENT_TIMEOUT_SECONDS", 120, minimum=1, maximum=600
            ),
            keep_alive_seconds=_integer(
                "WORKSTREAM_MCP_KEEP_ALIVE_SECONDS", 5, minimum=1, maximum=30
            ),
        )
