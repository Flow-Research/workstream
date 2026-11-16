"""Consumer contracts for ART-owned PRE source and archive validation.

Views describe existing immutable owner values; they grant no read authority.
The injected validator must enforce the concrete owner's exact type and schema.
"""

from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from pydantic_core import core_schema

from app.modules.checkers.api.material import SubmissionMaterialEntry


class SubmissionSourceLocationView(Protocol):
    """Provider-neutral location facts; reading them does not authorize access."""
    @property
    def operation_id(self) -> UUID:
        """Identify the intake operation that owns this physical source."""
        ...

    @property
    def namespace_id(self) -> str:
        """Identify the configured artifact namespace."""
        ...

    @property
    def namespace_fingerprint(self) -> str:
        """Bind the location to the exact namespace configuration."""
        ...

    @property
    def provider_profile(self) -> str:
        """Name the storage profile that interprets the object reference."""
        ...

    @property
    def object_ref(self) -> str:
        """Return the opaque provider reference for the operation-owned object."""
        ...


@runtime_checkable
class SealedSubmissionSourceView(Protocol):
    """Read-only access to the owner's exact sealed source identity."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        """Provide Pydantic validation for this owner-bound protocol."""
        def validate(value, info):
            """Parse serialized source facts or require the concrete owner value."""
            contracts = source_contracts_from_context(info.context)
            return contracts.parse_source(value) if type(value) is dict else contracts.require_source(value)
        return core_schema.with_info_plain_validator_function(validate)

    @property
    def location(self) -> SubmissionSourceLocationView:
        """Return the immutable operation and namespace location."""
        ...

    @property
    def provider_generation(self) -> str:
        """Identify the exact sealed provider generation, not merely its key."""
        ...

    @property
    def raw_sha256(self) -> str:
        """Return the digest of the uploaded ZIP bytes."""
        ...

    @property
    def raw_byte_count(self) -> int:
        """Return the verified length of the uploaded ZIP."""
        ...

    @property
    def sealed_upload_fence(self) -> int:
        """Bind the sealed source to the upload ownership generation."""
        ...

    @property
    def media_type(self) -> str:
        """Return the source archive media type."""
        ...

    def model_dump(self, *, mode: Literal["json"]) -> dict[str, object]:
        """Serialize the complete sealed-source identity for persisted evidence."""
        ...

    def source_sha256(self) -> str:
        """Digest the canonical source identity, including provider custody."""
        ...


@runtime_checkable
class SubmissionArchiveLimitsView(Protocol):
    """Exact configured inspection bounds, validated by their owner."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        """Provide Pydantic validation for this owner-bound protocol."""
        def validate(value, info):
            """Parse serialized bounds or require the concrete owner limits."""
            contracts = source_contracts_from_context(info.context)
            return contracts.parse_limits(value) if type(value) is dict else contracts.require_limits(value)
        return core_schema.with_info_plain_validator_function(validate)

    @property
    def maximum_entries(self) -> int:
        """Bound the number of archive entries inspected."""
        ...

    @property
    def maximum_path_bytes(self) -> int:
        """Bound each archive path in encoded bytes."""
        ...

    @property
    def maximum_path_depth(self) -> int:
        """Bound the number of path components in an archive entry."""
        ...

    @property
    def maximum_central_directory_bytes(self) -> int:
        """Bound ZIP directory metadata before entry processing."""
        ...

    @property
    def maximum_entry_bytes(self) -> int:
        """Bound the expanded size of an individual entry."""
        ...

    @property
    def maximum_expanded_bytes(self) -> int:
        """Bound the aggregate expanded archive size."""
        ...

    @property
    def maximum_compression_ratio(self) -> int:
        """Bound expansion relative to compressed archive content."""
        ...

    @property
    def maximum_inspection_seconds(self) -> float:
        """Bound the archive inspection duration."""
        ...

    def canonical_body(self) -> dict[str, int | float]:
        """Serialize exact configured limits for request hashing."""
        ...


@runtime_checkable
class SelectedPreSubmitSourceContracts(Protocol):
    """Pure owner validation; separate from transaction-bound live custody."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        """Provide Pydantic validation for this owner-bound protocol."""
        return core_schema.is_instance_schema(cls)

    def parse_source(self, body: object) -> SealedSubmissionSourceView:
        """Decode source facts using the concrete ART schema."""
        ...

    def require_source(self, source: object) -> SealedSubmissionSourceView:
        """Reject values that are not the concrete ART source type."""
        ...

    def parse_limits(self, body: object) -> SubmissionArchiveLimitsView:
        """Decode inspection limits using the concrete ART schema."""
        ...

    def require_limits(self, limits: object) -> SubmissionArchiveLimitsView:
        """Reject values that are not the concrete ART limits type."""
        ...

    def validate_manifest(
        self, body: object, *, sha256: str, limits: SubmissionArchiveLimitsView,
    ) -> tuple[SubmissionMaterialEntry, ...]:
        """Validate manifest digest and bounds, then expose material entries."""
        ...


def source_contracts_context(contracts: SelectedPreSubmitSourceContracts) -> dict[str, object]:
    """Explicit context for nested Pydantic parsing, never a global registry."""
    return {"submission_source_contracts": contracts}


def source_contracts_from_context(context: object) -> SelectedPreSubmitSourceContracts:
    """Refuse decoding without the owner validator selected by composition."""
    contracts = context.get("submission_source_contracts") if type(context) is dict else None
    if not isinstance(contracts, SelectedPreSubmitSourceContracts):
        raise ValueError("selected PRE source contracts are required")
    return contracts
