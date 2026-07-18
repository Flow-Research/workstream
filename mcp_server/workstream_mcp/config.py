"""Runtime configuration for the Workstream MCP server."""

from __future__ import annotations

from dataclasses import dataclass
import os


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_ALLOWED_HOSTS = ("127.0.0.1:*", "localhost:*", "[::1]:*")
DEFAULT_ALLOWED_ORIGINS = (
    "http://127.0.0.1:*",
    "http://localhost:*",
    "http://[::1]:*",
)


@dataclass(frozen=True, slots=True)
class WorkstreamMCPConfig:
    """Configuration for gateway construction."""

    workstream_api_base_url: str = DEFAULT_API_BASE_URL
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS
    allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS

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
        )


def _split_values(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Parse a comma-separated allowlist without accepting blank entries."""
    value = os.environ.get(name)
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())
