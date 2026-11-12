"""Provider-neutral contracts for immutable artifact byte storage."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
import re
from typing import Protocol
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.core.s3_validation import validate_s3_namespace_descriptor
from app.interfaces.external_services import (
    ExternalServiceAdapter,
    ExternalServiceAdapterIdentity,
)
from app.modules.artifacts.sources import ArtifactCommitment, CommittedArtifactSource
from app.modules.artifacts.api.submission_intake import (
    SealedSubmissionSource,
    MAXIMUM_SUBMISSION_ZIP_BYTES,
    SubmissionSourceLocation,
    SubmissionSourceCompletion,
    SubmissionSourcePart,
    SubmissionSourceUpload,
    SubmissionSourceUploadIntent,
)


ARTIFACT_STORE_CAPABILITY_KEY = "artifact_store"
_MAXIMUM_PROVIDER_OBJECT_REF_LENGTH = 1024
_CANONICAL_PROVIDER_OBJECT_REF = re.compile(
    r"^sha256/([0-9a-f]{2})/([0-9a-f]{62})$"
)
_RESERVED_NAMESPACE_DESCRIPTOR_KEYS = frozenset(
    {"adapter", "backend", "provider_profile"}
)
_NAMESPACE_DESCRIPTOR_KEYS_BY_PROFILE = {
    "local-v2": frozenset({"private_prefix", "private_root_identity"}),
    "minio-v1": frozenset(
        {
            "addressing_style",
            "bucket",
            "endpoint_identity",
            "private_prefix",
            "region",
        }
    ),
    "aws-s3-v1": frozenset(
        {
            "addressing_style",
            "bucket",
            "private_prefix",
            "region",
        }
    ),
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
        if self.provider_profile in {"minio-v1", "aws-s3-v1"}:
            validate_s3_namespace_descriptor(
                self.provider_profile,
                dict(self.descriptor_items),
            )

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


@dataclass(frozen=True, slots=True)
class ArtifactProviderActivationLease:
    """One exact database-time activation admitted for an AWS provider call."""

    activation_id: UUID

    def __post_init__(self) -> None:
        """Keep a lease bound to one native record identifier."""
        if type(self.activation_id) is not UUID:
            raise ValueError("artifact provider activation ID is invalid")


class ArtifactProviderOperationEvidence:
    """Capture the first activation selected for one logical store operation."""

    __slots__ = ("_activation_id",)

    def __init__(self) -> None:
        self._activation_id: UUID | None = None

    @property
    def activation_id(self) -> UUID | None:
        """Return the activation actually used, if this provider requires one."""
        return self._activation_id

    def bind(self, lease: ArtifactProviderActivationLease) -> None:
        """Bind once to the first lease; later calls must retain the same ID."""
        if type(lease) is not ArtifactProviderActivationLease:
            raise ValueError("artifact provider activation lease is invalid")
        if self._activation_id not in {None, lease.activation_id}:
            raise ValueError("artifact provider activation changed within one operation")
        self._activation_id = lease.activation_id


class ArtifactProviderActivationGuard(Protocol):
    """Load one exact fresh AWS activation without exposing ART persistence."""

    async def select_for_call(
        self,
        *,
        namespace_fingerprint: str,
    ) -> ArtifactProviderActivationLease:
        """Select a deterministic activation with sufficient remaining TTL."""

    async def require_for_call(
        self,
        activation_id: UUID,
        *,
        namespace_fingerprint: str,
    ) -> ArtifactProviderActivationLease:
        """Reload one previously selected activation before another AWS call."""


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


class ArtifactScratchIntegrityError(ArtifactIntegrityError):
    """Raised when private scratch state violates its filesystem contract."""

    code = "artifact_scratch_integrity_failure"


class ArtifactRangeInvalidError(ArtifactStoreError):
    """Raised when a requested range starts past the object end."""

    code = "artifact_range_invalid"
    category = "input_mismatch"


class ArtifactOperationConflictError(ArtifactStoreError):
    """Raised when an opaque provider reference is invalid for an operation."""

    code = "artifact_operation_conflict"
    category = "conflict"


def artifact_provider_object_ref(commitment: ArtifactCommitment) -> str:
    """Derive one identity-free provider reference from a commitment."""
    if type(commitment) is not ArtifactCommitment:
        raise ArtifactOperationConflictError("artifact commitment is invalid")
    digest_hex = commitment.sha256[7:]
    return f"sha256/{digest_hex[:2]}/{digest_hex[2:]}"


def parse_artifact_provider_object_ref(provider_object_ref: str) -> tuple[str, str]:
    """Return digest path parts after enforcing the canonical grammar."""
    if not isinstance(provider_object_ref, str):
        raise ArtifactOperationConflictError("artifact provider reference is invalid")
    matched = _CANONICAL_PROVIDER_OBJECT_REF.fullmatch(provider_object_ref)
    if matched is None:
        raise ArtifactOperationConflictError("artifact provider reference is invalid")
    return matched.group(1), matched.group(2)


class ArtifactLimitExceededError(ArtifactStoreError):
    """Raised when bounded artifact input exceeds its hard limit."""

    code = "artifact_limit_exceeded"
    category = "terminal"


class ArtifactConfigurationError(ArtifactStoreError):
    """Raised when artifact adapter construction or selection is invalid."""

    code = "artifact_storage_configuration_invalid"
    category = "configuration"


class ArtifactProviderLiveProofRequiredError(ArtifactConfigurationError):
    """Raised while an AWS profile lacks fresh exact live activation proof."""

    code = "artifact_provider_live_proof_required"


@dataclass(frozen=True)
class SealedSourceObservation:
    """Exact provider metadata, not an independent attestation of content hash."""

    location: SubmissionSourceLocation
    provider_generation: str
    raw_byte_count: int
    sealed_upload_fence: int

    def __post_init__(self) -> None:
        if type(self.location) is not SubmissionSourceLocation:
            raise ValueError("sealed observation location is invalid")
        SubmissionSourceLocation.model_validate(self.location)
        if (type(self.provider_generation) is not str
                or not 1 <= len(self.provider_generation) <= 2048
                or self.provider_generation == "null"
                or type(self.raw_byte_count) is not int
                or not 1 <= self.raw_byte_count <= MAXIMUM_SUBMISSION_ZIP_BYTES
                or type(self.sealed_upload_fence) is not int
                or self.sealed_upload_fence < 1):
            raise ValueError("sealed observation metadata is invalid")


class ArtifactStore(ExternalServiceAdapter, Protocol):
    """Immutable byte-provider capability used only by artifact orchestration."""

    async def begin_source_upload(
        self, intent: SubmissionSourceUploadIntent, *,
        operation_evidence: ArtifactProviderOperationEvidence | None = None,
    ) -> SubmissionSourceUpload:
        """Initiate an owned key; persist returned handle before sending parts."""

    async def upload_source_part(
        self, upload: SubmissionSourceUpload, number: int, data: bytes, *,
        operation_evidence: ArtifactProviderOperationEvidence | None = None,
    ) -> SubmissionSourcePart:
        """Send one bounded part; the owner serializes parts and enforces total."""

    async def complete_source_upload(
        self, completion: SubmissionSourceCompletion, *,
        operation_evidence: ArtifactProviderOperationEvidence | None = None,
    ) -> SealedSubmissionSource:
        """Conditionally complete a previously persisted EOF/completion intent."""

    def open_source(
        self, source: SealedSubmissionSource, *,
        operation_evidence: ArtifactProviderOperationEvidence | None = None,
        maximum_chunk_bytes: int = 64 * 1024,
    ) -> AsyncGenerator[bytes, None]:
        """Yield closable exact-version reads, capped by maximum_chunk_bytes (1..64 KiB)."""

    async def observe_sealed_source(
        self, source: SealedSubmissionSource, *,
        operation_evidence: ArtifactProviderOperationEvidence | None = None,
    ) -> SealedSourceObservation | None:
        """Observe the recorded immutable version without reading its body."""

    async def observe_source_upload(
        self, completion: SubmissionSourceCompletion, *,
        operation_evidence: ArtifactProviderOperationEvidence | None = None,
    ) -> SealedSubmissionSource | None:
        """Resolve a lost completion acknowledgement by exact provenance and bytes."""

    async def discover_source_uploads(
        self, intent: SubmissionSourceUploadIntent, *,
        operation_evidence: ArtifactProviderOperationEvidence | None = None,
    ) -> tuple[SubmissionSourceUpload, ...]:
        """Find unfinished handles only for one already-owned operation key."""

    async def request_source_abort(
        self, upload: SubmissionSourceUpload, *,
        operation_evidence: ArtifactProviderOperationEvidence | None = None,
    ) -> None:
        """Request scoped abort; acknowledgement alone never releases a charge."""

    async def put(
        self,
        source: CommittedArtifactSource,
        *,
        operation_evidence: ArtifactProviderOperationEvidence | None = None,
    ) -> ArtifactPutResult:
        """Publish one sealed committed source or prove an exact replay."""

    async def observe_put_result(
        self,
        commitment: ArtifactCommitment,
        *,
        operation_evidence: ArtifactProviderOperationEvidence | None = None,
    ) -> ArtifactPutObservation:
        """Observe one commitment-derived object without replaying a write."""

    def open(
        self,
        provider_object_ref: str,
        byte_range: ArtifactByteRange | None = None,
        *,
        operation_evidence: ArtifactProviderOperationEvidence | None = None,
    ) -> AsyncIterator[bytes]:
        """Stream one object or bounded range in bounded chunks."""

    async def head(
        self,
        provider_object_ref: str,
        *,
        operation_evidence: ArtifactProviderOperationEvidence | None = None,
    ) -> ArtifactObjectHead:
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
