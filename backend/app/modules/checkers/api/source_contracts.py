"""Consumer contracts for ART-owned PRE source and archive validation.

Views describe existing immutable owner values; they grant no read authority.
The injected validator must enforce the concrete owner's exact type and schema.
"""

from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from pydantic_core import core_schema

from app.modules.checkers.api.material import SubmissionMaterialEntry


class SubmissionSourceLocationView(Protocol):
    @property
    def operation_id(self) -> UUID: ...

    @property
    def namespace_id(self) -> str: ...

    @property
    def namespace_fingerprint(self) -> str: ...

    @property
    def provider_profile(self) -> str: ...

    @property
    def object_ref(self) -> str: ...


@runtime_checkable
class SealedSubmissionSourceView(Protocol):
    """Read-only access to the owner's exact sealed source identity."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        def validate(value, info):
            contracts = source_contracts_from_context(info.context)
            return contracts.parse_source(value) if type(value) is dict else contracts.require_source(value)
        return core_schema.with_info_plain_validator_function(validate)

    @property
    def location(self) -> SubmissionSourceLocationView: ...

    @property
    def provider_generation(self) -> str: ...

    @property
    def raw_sha256(self) -> str: ...

    @property
    def raw_byte_count(self) -> int: ...

    @property
    def sealed_upload_fence(self) -> int: ...

    @property
    def media_type(self) -> str: ...

    def model_dump(self, *, mode: Literal["json"]) -> dict[str, object]: ...

    def source_sha256(self) -> str: ...


@runtime_checkable
class SubmissionArchiveLimitsView(Protocol):
    """Exact configured inspection bounds, validated by their owner."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        def validate(value, info):
            contracts = source_contracts_from_context(info.context)
            return contracts.parse_limits(value) if type(value) is dict else contracts.require_limits(value)
        return core_schema.with_info_plain_validator_function(validate)

    @property
    def maximum_entries(self) -> int: ...

    @property
    def maximum_path_bytes(self) -> int: ...

    @property
    def maximum_path_depth(self) -> int: ...

    @property
    def maximum_central_directory_bytes(self) -> int: ...

    @property
    def maximum_entry_bytes(self) -> int: ...

    @property
    def maximum_expanded_bytes(self) -> int: ...

    @property
    def maximum_compression_ratio(self) -> int: ...

    @property
    def maximum_inspection_seconds(self) -> float: ...

    def canonical_body(self) -> dict[str, int | float]: ...


@runtime_checkable
class SelectedPreSubmitSourceContracts(Protocol):
    """Pure owner validation; separate from transaction-bound live custody."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.is_instance_schema(cls)

    def parse_source(self, body: object) -> SealedSubmissionSourceView: ...

    def require_source(self, source: object) -> SealedSubmissionSourceView: ...

    def parse_limits(self, body: object) -> SubmissionArchiveLimitsView: ...

    def require_limits(self, limits: object) -> SubmissionArchiveLimitsView: ...

    def validate_manifest(
        self, body: object, *, sha256: str, limits: SubmissionArchiveLimitsView,
    ) -> tuple[SubmissionMaterialEntry, ...]: ...


def source_contracts_context(contracts: SelectedPreSubmitSourceContracts) -> dict[str, object]:
    """Explicit context for nested Pydantic parsing, never a global registry."""
    return {"submission_source_contracts": contracts}


def source_contracts_from_context(context: object) -> SelectedPreSubmitSourceContracts:
    """Refuse decoding without the owner validator selected by composition."""
    contracts = context.get("submission_source_contracts") if type(context) is dict else None
    if not isinstance(contracts, SelectedPreSubmitSourceContracts):
        raise ValueError("selected PRE source contracts are required")
    return contracts
