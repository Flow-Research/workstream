"""Token propagation and redaction helpers for the Workstream MCP boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any

from workstream_mcp.errors import MCPErrorCode, WorkstreamMCPError

try:  # pragma: no cover - exercised when the MCP SDK is installed.
    from mcp.server.auth.provider import AccessToken
except ImportError:  # pragma: no cover
    AccessToken = None  # type: ignore[assignment]


STDIO_TOKEN_ENV = "WORKSTREAM_MCP_ISSUER_TOKEN"
MAX_BEARER_TOKEN_LENGTH = 8192


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Per-request contributor identity context."""

    bearer_token: str = field(repr=False)
    correlation_id: str
    transport: str


def context_from_authorization_header(
    authorization: str | None,
    *,
    correlation_id: str,
    transport: str = "streamable_http",
) -> RequestContext:
    """Build context from a Streamable HTTP Authorization header."""
    if not authorization:
        raise WorkstreamMCPError(
            MCPErrorCode.AUTHENTICATION_REQUIRED,
            "Authorization bearer token is required.",
            correlation_id=correlation_id,
        )
    scheme, separator, supplied_token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer":
        raise WorkstreamMCPError(
            MCPErrorCode.INVALID_TOKEN,
            "Authorization header must use bearer authentication.",
            correlation_id=correlation_id,
        )
    token = supplied_token.strip()
    if not _is_valid_bearer_token(token):
        raise WorkstreamMCPError(
            MCPErrorCode.INVALID_TOKEN,
            "Bearer token is malformed.",
            correlation_id=correlation_id,
        )
    return RequestContext(token, correlation_id, transport)


def context_from_stdio_environment(*, correlation_id: str) -> RequestContext:
    """Build local STDIO context from a secure process/session environment value."""
    token = os.environ.get(STDIO_TOKEN_ENV, "").strip()
    if not _is_valid_bearer_token(token):
        raise WorkstreamMCPError(
            MCPErrorCode.AUTHENTICATION_REQUIRED,
            "STDIO token configuration is missing.",
            correlation_id=correlation_id,
        )
    return RequestContext(token, correlation_id, "stdio")


def context_from_mcp_access_token(access_token: Any, *, correlation_id: str) -> RequestContext:
    """Build context from the MCP SDK authenticated request context."""
    token = getattr(access_token, "token", "")
    if not isinstance(token, str) or not _is_valid_bearer_token(token.strip()):
        raise WorkstreamMCPError(
            MCPErrorCode.AUTHENTICATION_REQUIRED,
            "Authorization bearer token is required.",
            correlation_id=correlation_id,
        )
    return RequestContext(token.strip(), correlation_id, "streamable_http")


class WorkstreamForwardingTokenVerifier:
    """MCP token verifier that preserves Workstream as the authority.

    The verifier accepts a syntactically present bearer token only so MCP HTTP
    middleware can require authentication and expose the raw token to handlers.
    Workstream API calls still perform the authoritative identity and grant
    checks.
    """

    async def verify_token(self, token: str) -> Any:
        """Return an MCP access token wrapper for a non-empty bearer token."""
        if AccessToken is None or not _is_valid_bearer_token(token.strip()):
            return None
        return AccessToken(
            token=token.strip(),
            client_id="workstream-forwarded-actor",
            scopes=[],
        )


def authorization_headers(
    context: RequestContext, *, request_id: str | None = None
) -> dict[str, str]:
    """Return Workstream HTTP headers without exposing tokens to tool schemas."""
    headers = {
        "Authorization": f"Bearer {context.bearer_token}",
        "X-Correlation-ID": context.correlation_id,
    }
    if request_id is not None:
        headers["X-Request-ID"] = request_id
        headers["Idempotency-Key"] = request_id
    return headers


def redact_secrets(value: Any, secrets: tuple[str, ...]) -> Any:
    """Recursively redact known secrets from structured values."""
    filtered = tuple(secret for secret in secrets if secret)
    if isinstance(value, str):
        result = value
        for secret in filtered:
            result = result.replace(secret, "[REDACTED]")
        return result
    if isinstance(value, list):
        return [redact_secrets(item, filtered) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item, filtered) for item in value)
    if isinstance(value, dict):
        return {
            redact_secrets(key, filtered): redact_secrets(item, filtered)
            for key, item in value.items()
        }
    return value


def redact_context_secrets(value: Any, context: RequestContext) -> Any:
    """Redact per-request bearer material from MCP-boundary outputs."""
    return redact_secrets(value, (context.bearer_token,))


def contains_secret(value: Any, secret: str) -> bool:
    """Return whether a structured value contains a raw secret string."""
    if not secret:
        return False
    if isinstance(value, str):
        return secret in value
    if isinstance(value, dict):
        return any(
            contains_secret(key, secret) or contains_secret(item, secret)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return any(contains_secret(item, secret) for item in value)
    return False


def _is_valid_bearer_token(token: str) -> bool:
    """Apply syntax and size bounds before forwarding opaque bearer material."""
    return bool(token) and len(token) <= MAX_BEARER_TOKEN_LENGTH and not any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in token
    )
