"""Runtime configuration for the Workstream MCP server."""

from __future__ import annotations

from dataclasses import dataclass
import os


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_GATEWAY_MODE = "http"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class WorkstreamMCPConfig:
    """Configuration for gateway construction."""

    workstream_api_base_url: str = DEFAULT_API_BASE_URL
    gateway_mode: str = DEFAULT_GATEWAY_MODE
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS

    @classmethod
    def from_environment(cls) -> "WorkstreamMCPConfig":
        """Create configuration from environment variables."""
        return cls(
            workstream_api_base_url=os.environ.get(
                "WORKSTREAM_API_BASE_URL",
                DEFAULT_API_BASE_URL,
            ).rstrip("/"),
            gateway_mode=os.environ.get("WORKSTREAM_MCP_GATEWAY_MODE", DEFAULT_GATEWAY_MODE),
            request_timeout_seconds=float(
                os.environ.get(
                    "WORKSTREAM_MCP_REQUEST_TIMEOUT_SECONDS",
                    str(DEFAULT_REQUEST_TIMEOUT_SECONDS),
                )
            ),
        )
