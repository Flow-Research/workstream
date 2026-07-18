"""Auth verifier factory functions."""

from __future__ import annotations

from threading import Lock

from app.adapters.auth.dev import DevelopmentAuthVerifier
from app.adapters.auth.flow import FlowAuthVerifier
from app.core.config import Settings, get_settings
from app.interfaces.auth import AuthVerificationUnavailableError, AuthVerifier
from app.schemas.auth import AuthVerificationResult


class _UnavailableAuthVerifier:
    """Fail-closed verifier returned when production configuration is invalid."""

    def canonical_issuer(self) -> str:
        """Fail closed when trusted issuer configuration is unavailable."""
        raise AuthVerificationUnavailableError("token verification is unavailable")

    async def verify(self, token: str) -> AuthVerificationResult:
        raise AuthVerificationUnavailableError("token verification is unavailable")


_cached_settings: Settings | None = None
_cached_verifier: AuthVerifier | None = None
_auth_cache_lock = Lock()


def build_auth_verifier(settings: Settings) -> AuthVerifier:
    """Build the configured auth verifier.

    Args:
        settings: Application settings selecting the auth provider.

    Returns:
        Auth verifier implementation for the selected provider.
    """
    if settings.auth_provider == "dev":
        return DevelopmentAuthVerifier(settings)
    return FlowAuthVerifier(settings)


def prepare_auth_verifier(settings: Settings) -> tuple[AuthVerifier, bool]:
    """Build a verifier and report whether its configuration is valid."""
    try:
        return build_auth_verifier(settings), True
    except RuntimeError:
        return _UnavailableAuthVerifier(), False


def get_auth_verifier() -> AuthVerifier:
    """Return the process-lifetime auth verifier dependency.

    Returns:
        Auth verifier built from cached application settings.
    """
    global _cached_settings, _cached_verifier

    settings = get_settings()
    with _auth_cache_lock:
        if settings is _cached_settings and _cached_verifier is not None:
            return _cached_verifier
        verifier = prepare_auth_verifier(settings)[0]
        _cached_settings = settings
        _cached_verifier = verifier
        return verifier


def cache_auth_verifier(settings: Settings, verifier: AuthVerifier) -> None:
    """Retain an application-built verifier in the process cache."""
    global _cached_settings, _cached_verifier

    with _auth_cache_lock:
        _cached_settings = settings
        _cached_verifier = verifier


def clear_auth_verifier_cache() -> None:
    """Clear process verifier state for deterministic configuration tests."""
    global _cached_settings, _cached_verifier

    with _auth_cache_lock:
        _cached_settings = None
        _cached_verifier = None
