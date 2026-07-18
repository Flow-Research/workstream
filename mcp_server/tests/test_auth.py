"""Token handling tests for the Workstream MCP boundary."""

from __future__ import annotations

import pytest

from workstream_mcp.auth import (
    RequestContext,
    WorkstreamForwardingTokenVerifier,
    authorization_headers,
    contains_secret,
    context_from_authorization_header,
    redact_secrets,
)
from workstream_mcp.errors import MCPErrorCode, WorkstreamMCPError


def test_context_from_authorization_header_requires_bearer_token() -> None:
    """Missing or malformed auth fails before protected work is attempted."""
    with pytest.raises(WorkstreamMCPError) as missing:
        context_from_authorization_header(None, correlation_id="corr-1")
    with pytest.raises(WorkstreamMCPError) as malformed:
        context_from_authorization_header("Basic secret", correlation_id="corr-1")

    assert missing.value.code == MCPErrorCode.AUTHENTICATION_REQUIRED
    assert malformed.value.code == MCPErrorCode.INVALID_TOKEN


@pytest.mark.parametrize("token", ["", "two words", "line\nbreak", "x" * 8193])
def test_context_rejects_malformed_bearer_material(token: str) -> None:
    """Opaque tokens are still bounded by bearer syntax and a safe header size."""
    with pytest.raises(WorkstreamMCPError) as malformed:
        context_from_authorization_header(f"Bearer {token}", correlation_id="corr-1")

    assert malformed.value.code == MCPErrorCode.INVALID_TOKEN


def test_authorization_headers_forward_token_without_tool_schema_exposure() -> None:
    """The gateway receives auth headers, not token tool parameters."""
    context = context_from_authorization_header("Bearer issuer-token", correlation_id="corr-1")

    headers = authorization_headers(context, request_id="11111111-1111-4111-8111-111111111111")

    assert headers["Authorization"] == "Bearer issuer-token"
    assert headers["X-Correlation-ID"] == "corr-1"
    assert headers["X-Request-ID"] == "11111111-1111-4111-8111-111111111111"
    assert headers["Idempotency-Key"] == "11111111-1111-4111-8111-111111111111"


def test_bearer_scheme_is_case_insensitive() -> None:
    """HTTP authentication scheme matching follows case-insensitive semantics."""
    context = context_from_authorization_header("bearer issuer-token", correlation_id="corr-1")

    assert context.bearer_token == "issuer-token"


def test_request_context_repr_omits_bearer_token() -> None:
    """Debug representation must not expose bearer material."""
    context = RequestContext("issuer-token", "corr-1", "test")

    assert "issuer-token" not in repr(context)


def test_redaction_removes_known_secret_from_structured_values() -> None:
    """Known raw secrets are removed from nested values."""
    payload = {"message": "Bearer issuer-token", "items": ["issuer-token", "safe"]}

    redacted = redact_secrets(payload, ("issuer-token",))

    assert not contains_secret(redacted, "issuer-token")
    assert redacted == {"message": "Bearer [REDACTED]", "items": ["[REDACTED]", "safe"]}


@pytest.mark.asyncio
async def test_forwarding_token_verifier_requires_non_empty_token() -> None:
    """The MCP HTTP auth shim only accepts present bearer material."""
    verifier = WorkstreamForwardingTokenVerifier()

    accepted = await verifier.verify_token("issuer-token")
    rejected = await verifier.verify_token("   ")

    assert accepted is not None
    assert accepted.token == "issuer-token"
    assert rejected is None
