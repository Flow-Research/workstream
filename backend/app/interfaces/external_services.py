"""Shared construction contracts for external service adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re
from typing import Generic, Protocol, TypeVar


_ADAPTER_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ExternalServiceAdapterError(Exception):
    """Base class for stable, secret-safe external service failures."""

    code = "external_service_error"
    category = "external_service"
    retryable = False

    def __init__(self, identity: ExternalServiceAdapterIdentity | None = None) -> None:
        """Create an error containing only bounded adapter identity."""
        self.identity = identity if type(identity) is ExternalServiceAdapterIdentity else None
        super().__init__(self.code)


class ExternalServiceConfigurationError(ExternalServiceAdapterError):
    """Raised when adapter selection or construction is invalid."""

    code = "external_service_configuration_invalid"
    category = "configuration"


class ExternalServiceUnavailableError(ExternalServiceAdapterError):
    """Raised when a configured external service is temporarily unavailable."""

    code = "external_service_unavailable"
    category = "availability"
    retryable = True


class ExternalServiceProtocolError(ExternalServiceAdapterError):
    """Raised when an external service violates its capability protocol."""

    code = "external_service_protocol_invalid"
    category = "protocol"


class DuplicateExternalServiceProviderError(ExternalServiceConfigurationError):
    """Raised when one factory receives the same provider more than once."""

    code = "external_service_provider_duplicate"


class UnknownExternalServiceProviderError(ExternalServiceConfigurationError):
    """Raised when a factory has no constructor for the selected provider."""

    code = "external_service_provider_unknown"


class ExternalServiceAdapterIdentityMismatchError(ExternalServiceConfigurationError):
    """Raised when a constructor returns an adapter under another identity."""

    code = "external_service_adapter_identity_mismatch"


@dataclass(frozen=True, slots=True)
class ExternalServiceAdapterIdentity:
    """Immutable canonical identity for one capability provider."""

    capability_key: str
    provider_key: str

    def __post_init__(self) -> None:
        """Reject empty, noncanonical, or unbounded adapter keys."""
        if not _is_adapter_key(self.capability_key) or not _is_adapter_key(self.provider_key):
            raise ExternalServiceConfigurationError()


class ExternalServiceAdapter(Protocol):
    """Small common protocol implemented by typed external capabilities."""

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Return this adapter's immutable capability and provider identity."""


AdapterT = TypeVar("AdapterT", bound=ExternalServiceAdapter)
AdapterConstructor = Callable[[], AdapterT]


class ExternalServiceAdapterFactory(Generic[AdapterT]):
    """Explicit per-capability registry and constructor for typed adapters."""

    __slots__ = ("_capability_key", "_constructors")

    def __init__(self, capability_key: str) -> None:
        """Create one empty, instance-local capability factory."""
        if not _is_adapter_key(capability_key):
            raise ExternalServiceConfigurationError()
        self._capability_key = capability_key
        self._constructors: dict[str, AdapterConstructor[AdapterT]] = {}

    @property
    def capability_key(self) -> str:
        """Return the immutable capability key owned by this factory."""
        return self._capability_key

    def register(self, provider_key: str, constructor: AdapterConstructor[AdapterT]) -> None:
        """Register one provider constructor explicitly at a composition root."""
        if not _is_adapter_key(provider_key) or not callable(constructor):
            raise ExternalServiceConfigurationError()
        identity = ExternalServiceAdapterIdentity(self._capability_key, provider_key)
        if provider_key in self._constructors:
            raise DuplicateExternalServiceProviderError(identity)
        self._constructors[provider_key] = constructor

    def create(self, provider_key: str) -> AdapterT:
        """Construct the selected typed adapter and verify its identity."""
        if not _is_adapter_key(provider_key):
            raise ExternalServiceConfigurationError()
        expected_identity = ExternalServiceAdapterIdentity(self._capability_key, provider_key)
        constructor = self._constructors.get(provider_key)
        if constructor is None:
            raise UnknownExternalServiceProviderError(expected_identity)

        sanitized_error: ExternalServiceAdapterError | None = None
        construction_validation_failed = False
        try:
            adapter = constructor()
            actual_identity = getattr(adapter, "identity", None)
            identity_matches = (
                type(actual_identity) is ExternalServiceAdapterIdentity
                and actual_identity == expected_identity
            )
        except ExternalServiceUnavailableError:
            sanitized_error = ExternalServiceUnavailableError(expected_identity)
        except ExternalServiceProtocolError:
            sanitized_error = ExternalServiceProtocolError(expected_identity)
        except ExternalServiceConfigurationError:
            sanitized_error = ExternalServiceConfigurationError(expected_identity)
        except ExternalServiceAdapterError:
            sanitized_error = ExternalServiceAdapterError(expected_identity)
        except Exception:
            construction_validation_failed = True
        if sanitized_error is not None:
            raise sanitized_error from None
        if construction_validation_failed:
            raise ExternalServiceConfigurationError(expected_identity) from None

        if not identity_matches:
            raise ExternalServiceAdapterIdentityMismatchError(expected_identity)
        return adapter


def _is_adapter_key(value: object) -> bool:
    """Return whether a value is one bounded lowercase adapter key."""
    return isinstance(value, str) and _ADAPTER_KEY_PATTERN.fullmatch(value) is not None
