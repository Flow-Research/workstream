"""Token propagation and redaction helpers for the Workstream MCP boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
from typing import Any
from uuid import UUID, uuid4

import httpx

from workstream_mcp.errors import MCPErrorCode, WorkstreamMCPError

try:  # pragma: no cover - exercised when the MCP SDK is installed.
    from mcp.server.auth.provider import AccessToken
except ImportError:  # pragma: no cover
    AccessToken = None  # type: ignore[assignment]


STDIO_TOKEN_ENV = "WORKSTREAM_MCP_ISSUER_TOKEN"
STDIO_SCENARIO_ACTOR_ID_ENV = "WORKSTREAM_MCP_SCENARIO_ACTOR_ID"
MAX_BEARER_TOKEN_LENGTH = 8192
UUID_TEXT_PATTERN = re.compile(
    r"(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{32})"
)


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Per-request contributor identity context."""

    bearer_token: str = field(repr=False)
    correlation_id: str
    transport: str
    actor_id: str | None = None


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
    actor_id = os.environ.get(STDIO_SCENARIO_ACTOR_ID_ENV, "").strip() or None
    return RequestContext(token, correlation_id, "stdio", actor_id)


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


def context_for_transport(
    access_token: Any,
    *,
    correlation_id: str,
    transport: str,
) -> RequestContext:
    """Build identity context without crossing HTTP and STDIO credential sources."""
    if access_token is not None:
        return context_from_mcp_access_token(access_token, correlation_id=correlation_id)
    if transport == "stdio":
        return context_from_stdio_environment(correlation_id=correlation_id)
    raise WorkstreamMCPError(
        MCPErrorCode.AUTHENTICATION_REQUIRED,
        "Authorization bearer token is required.",
        correlation_id=correlation_id,
    )


class WorkstreamForwardingTokenVerifier:
    """MCP token verifier backed by Workstream's existing Auth service."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Configure the authoritative identity check without owning sessions."""
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def verify_token(self, token: str) -> Any:
        """Return an MCP access token only after Workstream Auth accepts it."""
        if AccessToken is None or not _is_valid_bearer_token(token.strip()):
            return None
        normalized_token = token.strip()
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._transport,
                trust_env=False,
            ) as client:
                response = await client.get(
                    "/api/v1/auth/me",
                    headers={
                        "Authorization": f"Bearer {normalized_token}",
                        "X-Correlation-ID": str(uuid4()),
                    },
                )
        except httpx.HTTPError:
            return None
        if not response.is_success:
            return None
        return AccessToken(
            token=normalized_token,
            client_id="workstream-forwarded-actor",
            scopes=[],
        )


def authorization_headers(
    context: RequestContext, *, request_id: str | None = None
) -> dict[str, str]:
    """Return Workstream HTTP headers without exposing tokens to tool schemas."""
    if request_id is not None and contains_context_secret(request_id, context):
        raise WorkstreamMCPError(
            MCPErrorCode.INVALID_TOKEN,
            "Bearer material cannot be reused as a request identifier.",
            correlation_id=context.correlation_id,
        )
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
    if isinstance(value, set):
        return {redact_secrets(item, filtered) for item in value}
    if isinstance(value, dict):
        return {
            redact_secrets(key, filtered): redact_secrets(item, filtered)
            for key, item in value.items()
        }
    return value


def redact_context_secrets(value: Any, context: RequestContext) -> Any:
    """Redact per-request bearer material from MCP-boundary outputs."""
    redacted = redact_secrets(value, (context.bearer_token,))
    token_uuid = _as_uuid(context.bearer_token)
    if token_uuid is None:
        return redacted
    return _redact_equivalent_uuid(redacted, token_uuid)


def contains_context_secret(value: Any, context: RequestContext) -> bool:
    """Detect raw or canonically equivalent bearer material in structured input."""
    if contains_secret(value, context.bearer_token):
        return True
    token_uuid = _as_uuid(context.bearer_token)
    return token_uuid is not None and _contains_equivalent_uuid(value, token_uuid)


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


def _as_uuid(value: str) -> UUID | None:
    """Parse a UUID-shaped value without exposing it."""
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        return None


def _contains_equivalent_uuid(value: Any, secret_uuid: UUID) -> bool:
    """Find UUID strings equal to a bearer after canonicalization."""
    if isinstance(value, str):
        return any(
            _as_uuid(match.group(0)) == secret_uuid
            for match in UUID_TEXT_PATTERN.finditer(value)
        )
    if isinstance(value, dict):
        return any(
            _contains_equivalent_uuid(key, secret_uuid)
            or _contains_equivalent_uuid(item, secret_uuid)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return any(_contains_equivalent_uuid(item, secret_uuid) for item in value)
    return False


def _redact_equivalent_uuid(value: Any, secret_uuid: UUID) -> Any:
    """Redact complete UUID strings canonically equal to the bearer."""
    if isinstance(value, str):
        return UUID_TEXT_PATTERN.sub(
            lambda match: (
                "[REDACTED]"
                if _as_uuid(match.group(0)) == secret_uuid
                else match.group(0)
            ),
            value,
        )
    if isinstance(value, list):
        return [_redact_equivalent_uuid(item, secret_uuid) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_equivalent_uuid(item, secret_uuid) for item in value)
    if isinstance(value, set):
        return {_redact_equivalent_uuid(item, secret_uuid) for item in value}
    if isinstance(value, dict):
        return {
            _redact_equivalent_uuid(key, secret_uuid): _redact_equivalent_uuid(
                item, secret_uuid
            )
            for key, item in value.items()
        }
    return value


def _is_valid_bearer_token(token: str) -> bool:
    """Apply syntax and size bounds before forwarding opaque bearer material."""
    return bool(token) and len(token) <= MAX_BEARER_TOKEN_LENGTH and not any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in token
    )
