"""Provider-neutral contracts for immutable artifact byte storage."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from app.core.hashing import canonical_json_hash
from app.interfaces.external_services import (
    ExternalServiceAdapter,
    ExternalServiceAdapterIdentity,
)
from app.modules.artifacts.sources import ArtifactCommitment, CommittedArtifactSource


ARTIFACT_STORE_CAPABILITY_KEY = "artifact_store"
_MAXIMUM_PROVIDER_OBJECT_REF_LENGTH = 1024
_RESERVED_NAMESPACE_DESCRIPTOR_KEYS = frozenset(
    {"adapter", "backend", "provider_profile"}
)
_NAMESPACE_DESCRIPTOR_KEYS_BY_PROFILE = {
    "local-v2": frozenset({"private_prefix", "private_root_identity"}),
}


def _validate_provider_object_ref(provider_object_ref: str) -> None:
    """Require one bounded opaque provider reference without control characters."""
    if (
        not isinstance(provider_object_ref, str)
        or not provider_object_ref
        or len(provider_object_ref) > _MAXIMUM_PROVIDER_OBJECT_REF_LENGTH
        or any(ord(character) < 32 or ord(character) == 127 for character in provider_object_ref)
    ):
        raise ValueError("artifact provider object reference is invalid")


@dataclass(frozen=True, slots=True)
class ArtifactByteRange:
    """Zero-based byte range whose optional length defines an exclusive end."""

    offset: int = 0
    length: int | None = None

    def __post_init__(self) -> None:
        """Reject negative, boolean, and non-integer range values."""
        if type(self.offset) is not int or self.offset < 0:
            raise ValueError("artifact byte range offset is invalid")
        if self.length is not None and (type(self.length) is not int or self.length < 0):
            raise ValueError("artifact byte range length is invalid")


@dataclass(frozen=True, slots=True)
class ArtifactPutResult:
    """Provider-neutral result of immutable publication or an exact replay."""

    provider_object_ref: str
    replayed: bool

    def __post_init__(self) -> None:
        """Validate the bounded provider result."""
        _validate_provider_object_ref(self.provider_object_ref)
        if type(self.replayed) is not bool:
            raise ValueError("artifact put replay observation is invalid")


@dataclass(frozen=True, slots=True)
class ArtifactPutObservation:
    """Read-only exact observation of one commitment-derived provider object."""

    provider_object_ref: str
    committed: bool

    def __post_init__(self) -> None:
        """Validate the bounded provider observation."""
        _validate_provider_object_ref(self.provider_object_ref)
        if type(self.committed) is not bool:
            raise ValueError("artifact put observation is invalid")


@dataclass(frozen=True, slots=True)
class ArtifactObjectHead:
    """Safe provider observation for an existing or missing immutable object."""

    provider_object_ref: str
    exists: bool
    byte_count: int | None = None
    media_type: str | None = None

    def __post_init__(self) -> None:
        """Keep missing and existing head observations unambiguous."""
        _validate_provider_object_ref(self.provider_object_ref)
        if type(self.exists) is not bool:
            raise ValueError("artifact head existence observation is invalid")
        if self.exists:
            if type(self.byte_count) is not int or self.byte_count < 0:
                raise ValueError("existing artifact head requires an exact byte count")
        elif self.byte_count is not None or self.media_type is not None:
            raise ValueError("missing artifact head cannot contain object metadata")
        if self.media_type is not None:
            ArtifactCommitment.validate_media_type(self.media_type)


@dataclass(frozen=True, slots=True)
class ArtifactStoreNamespaceIdentity:
    """Provider-owned, non-secret identity for one immutable byte namespace."""

    provider_profile: str
    descriptor_items: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        """Require a canonical closed descriptor without duplicate keys."""
        if not self.provider_profile or len(self.provider_profile) > 100:
            raise ValueError("artifact provider profile is invalid")
        if type(self.descriptor_items) is not tuple:
            raise ValueError("artifact namespace descriptor is not immutable")
        expected_keys = _NAMESPACE_DESCRIPTOR_KEYS_BY_PROFILE.get(self.provider_profile)
        if expected_keys is None:
            raise ValueError("artifact provider profile is unsupported")
        keys: list[str] = []
        for item in self.descriptor_items:
            if (
                type(item) is not tuple
                or len(item) != 2
                or not all(isinstance(value, str) and value for value in item)
            ):
                raise ValueError("artifact namespace descriptor is invalid")
            keys.append(item[0])
        if (
            keys != sorted(keys)
            or len(keys) != len(set(keys))
            or not _RESERVED_NAMESPACE_DESCRIPTOR_KEYS.isdisjoint(keys)
            or set(keys) != expected_keys
        ):
            raise ValueError("artifact namespace descriptor is not canonical")

    def as_dict(self) -> dict[str, str]:
        """Return a fresh JSON-compatible descriptor projection."""
        return dict(self.descriptor_items)


def artifact_store_namespace_material(
    *,
    backend: str,
    adapter_identity: ExternalServiceAdapterIdentity,
    namespace_identity: ArtifactStoreNamespaceIdentity,
) -> tuple[dict[str, object], str]:
    """Build one canonical namespace descriptor and its matching fingerprint."""
    descriptor: dict[str, object] = {
        "backend": backend,
        "adapter": adapter_identity.provider_key,
        "provider_profile": namespace_identity.provider_profile,
        **namespace_identity.as_dict(),
    }
    return descriptor, canonical_json_hash(descriptor)


@dataclass(frozen=True, slots=True)
class ArtifactStoreNamespaceClaim:
    """Proof that PostgreSQL accepted one exact adapter namespace identity."""

    adapter_identity: ExternalServiceAdapterIdentity
    namespace_identity: ArtifactStoreNamespaceIdentity
    namespace_fingerprint: str

    def __post_init__(self) -> None:
        """Reject malformed or mismatched startup proof values."""
        if type(self.adapter_identity) is not ExternalServiceAdapterIdentity:
            raise ValueError("artifact namespace adapter identity is invalid")
        if type(self.namespace_identity) is not ArtifactStoreNamespaceIdentity:
            raise ValueError("artifact namespace identity is invalid")
        if (
            not isinstance(self.namespace_fingerprint, str)
            or not self.namespace_fingerprint.startswith("sha256:")
            or len(self.namespace_fingerprint) != 71
            or any(
                character not in "0123456789abcdef"
                for character in self.namespace_fingerprint[7:]
            )
        ):
            raise ValueError("artifact namespace fingerprint is invalid")


class ArtifactStoreError(Exception):
    """Base class for stable, provider-secret-safe artifact failures."""

    code = "artifact_storage_error"
    category = "terminal"
    retryable = False


class ArtifactStoreUnavailableError(ArtifactStoreError):
    """Raised when provider availability prevents an exact result."""

    code = "artifact_storage_unavailable"
    category = "retryable"
    retryable = True


class ArtifactObjectMissingError(ArtifactStoreError):
    """Raised when an operation requires an object that does not exist."""

    code = "artifact_object_missing"
    category = "not_found"


class ArtifactPreconditionFailedError(ArtifactStoreError):
    """Raised when immutable provider publication loses its condition."""

    code = "artifact_precondition_failed"
    category = "conflict"


class ArtifactInputMismatchError(ArtifactStoreError):
    """Raised when supplied bytes violate their server-owned commitment."""

    code = "artifact_input_mismatch"
    category = "input_mismatch"


class ArtifactIntegrityError(ArtifactStoreError):
    """Raised when provider or prepared bytes violate immutable facts."""

    code = "artifact_integrity_failure"
    category = "integrity"


class ArtifactRangeInvalidError(ArtifactStoreError):
    """Raised when a requested range starts past the object end."""

    code = "artifact_range_invalid"
    category = "input_mismatch"


class ArtifactOperationConflictError(ArtifactStoreError):
    """Raised when an opaque provider reference is invalid for an operation."""

    code = "artifact_operation_conflict"
    category = "conflict"


class ArtifactLimitExceededError(ArtifactStoreError):
    """Raised when bounded artifact input exceeds its hard limit."""

    code = "artifact_limit_exceeded"
    category = "terminal"


class ArtifactConfigurationError(ArtifactStoreError):
    """Raised when artifact adapter construction or selection is invalid."""

    code = "artifact_storage_configuration_invalid"
    category = "configuration"


class ArtifactStore(ExternalServiceAdapter, Protocol):
    """Immutable byte-provider capability used only by artifact orchestration."""

    async def put(self, source: CommittedArtifactSource) -> ArtifactPutResult:
        """Publish one sealed committed source or prove an exact replay."""

    async def observe_put_result(
        self,
        commitment: ArtifactCommitment,
    ) -> ArtifactPutObservation:
        """Observe one commitment-derived object without replaying a write."""

    def open(
        self,
        provider_object_ref: str,
        byte_range: ArtifactByteRange | None = None,
    ) -> AsyncIterator[bytes]:
        """Stream one object or bounded range in bounded chunks."""

    async def head(self, provider_object_ref: str) -> ArtifactObjectHead:
        """Return a safe existing or missing object observation."""


class ArtifactStoreBootstrap(ExternalServiceAdapter, Protocol):
    """Composition-only lifecycle that cannot publish bytes before DB claim."""

    @property
    def namespace_identity(self) -> ArtifactStoreNamespaceIdentity:
        """Return the identity of the already-open provider namespace."""

    def initialize_after_namespace_claim(
        self,
        claim: ArtifactStoreNamespaceClaim,
    ) -> ArtifactStore:
        """Initialize provider layout only after accepting the exact DB claim."""

    def close(self) -> None:
        """Release provider startup and operation resources."""
