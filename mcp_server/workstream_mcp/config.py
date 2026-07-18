"""Runtime configuration for the Workstream MCP server."""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from urllib.parse import urlsplit


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_ALLOWED_HOSTS = ("127.0.0.1:*", "localhost:*", "[::1]:*")
DEFAULT_ALLOWED_ORIGINS = (
    "http://127.0.0.1:*",
    "http://localhost:*",
    "http://[::1]:*",
)
INSECURE_AUTH_ISSUER_ENV = "WORKSTREAM_MCP_ALLOW_INSECURE_AUTH_ISSUER"


@dataclass(frozen=True, slots=True)
class WorkstreamMCPConfig:
    """Configuration for gateway construction."""

    workstream_api_base_url: str = DEFAULT_API_BASE_URL
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS
    allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS
    auth_issuer_url: str | None = None
    allow_insecure_auth_issuer: bool = False

    def __post_init__(self) -> None:
        """Reject configuration that could leak bearer tokens or disable timeouts."""
        parsed = urlsplit(self.workstream_api_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("WORKSTREAM_API_BASE_URL must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("WORKSTREAM_API_BASE_URL must not contain credentials, query, or fragment")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("WORKSTREAM_API_BASE_URL must use HTTPS outside the local machine")
        if not math.isfinite(self.request_timeout_seconds) or self.request_timeout_seconds <= 0:
            raise ValueError("WORKSTREAM_MCP_REQUEST_TIMEOUT_SECONDS must be positive and finite")
        if not self.allowed_hosts or not self.allowed_origins:
            raise ValueError("MCP HTTP host and origin allowlists must not be empty")

    @classmethod
    def from_environment(cls) -> "WorkstreamMCPConfig":
        """Create configuration from environment variables."""
        return cls(
            workstream_api_base_url=os.environ.get(
                "WORKSTREAM_API_BASE_URL",
                DEFAULT_API_BASE_URL,
            ).rstrip("/"),
            request_timeout_seconds=float(
                os.environ.get(
                    "WORKSTREAM_MCP_REQUEST_TIMEOUT_SECONDS",
                    str(DEFAULT_REQUEST_TIMEOUT_SECONDS),
                )
            ),
            allowed_hosts=_split_values("WORKSTREAM_MCP_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS),
            allowed_origins=_split_values(
                "WORKSTREAM_MCP_ALLOWED_ORIGINS",
                DEFAULT_ALLOWED_ORIGINS,
            ),
            auth_issuer_url=_optional_url("WORKSTREAM_MCP_AUTH_ISSUER_URL"),
            allow_insecure_auth_issuer=_parse_boolean(INSECURE_AUTH_ISSUER_ENV),
        )

    def streamable_http_auth_issuer_url(self) -> str:
        """Return an explicitly trusted issuer URL for Streamable HTTP."""
        if self.auth_issuer_url is None:
            raise ValueError(
                "WORKSTREAM_MCP_AUTH_ISSUER_URL is required for streamable-http transport"
            )
        parsed = urlsplit(self.auth_issuer_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("WORKSTREAM_MCP_AUTH_ISSUER_URL must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(
                "WORKSTREAM_MCP_AUTH_ISSUER_URL must not contain credentials, query, or fragment"
            )
        if parsed.scheme == "https":
            return self.auth_issuer_url
        if (
            self.allow_insecure_auth_issuer
            and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        ):
            return self.auth_issuer_url
        raise ValueError(
            "WORKSTREAM_MCP_AUTH_ISSUER_URL must use HTTPS; local HTTP requires "
            f"{INSECURE_AUTH_ISSUER_ENV}=true"
        )


def _split_values(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Parse a comma-separated allowlist without accepting blank entries."""
    value = os.environ.get(name)
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _optional_url(name: str) -> str | None:
    """Read an optional URL without treating blank configuration as present."""
    value = os.environ.get(name, "").strip().rstrip("/")
    return value or None


def _parse_boolean(name: str) -> bool:
    """Parse one explicit development-only boolean setting."""
    value = os.environ.get(name, "false").strip().casefold()
    if value in {"true", "1"}:
        return True
    if value in {"false", "0"}:
        return False
    raise ValueError(f"{name} must be true or false")
