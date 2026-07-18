"""Auth interface contracts used by verifier adapters."""

from __future__ import annotations

from typing import Protocol

import httpx

from app.schemas.auth import AuthVerificationResult


class AuthVerificationError(Exception):
    """Raised when a bearer token cannot be verified."""


class AuthVerificationUnavailableError(AuthVerificationError):
    """Raised when trusted verification infrastructure is unavailable."""


class AuthVerifier(Protocol):
    """Protocol implemented by external auth verifier adapters."""

    def canonical_issuer(self) -> str:
        """Return the exact configured issuer used for successful verification."""

    async def verify(self, token: str) -> AuthVerificationResult:
        """Verify a bearer token and return canonical and compatibility views."""


class AuthHttpClientFactory(Protocol):
    """Build one policy-configured HTTP client for a verifier operation."""

    def __call__(
        self,
        *,
        timeout: httpx.Timeout,
        limits: httpx.Limits,
        follow_redirects: bool,
        trust_env: bool,
    ) -> httpx.AsyncClient:
        """Return a client whose lifecycle is owned by the caller."""
