"""COMP-owned source/evidence values and opaque authorization collaboration.

Detached facts and stored authorization references do not confer authority. Only
an AUTH-owned live prepared operation may authorize a new append or exact replay.
"""

from contextlib import AbstractAsyncContextManager
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, UUID7

from app.modules.compensation.api.fulfillment import (
    CompensationFulfillmentFence, CompensationFulfillmentLifecycleFacts,
)

Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
FulfillmentFailureCode = Literal[
    "ADAPTER_REJECTED", "DESTINATION_UNAVAILABLE", "PROVIDER_UNAVAILABLE",
    "PROVIDER_TIMEOUT", "UNKNOWN_PROVIDER_FAILURE",
]


class FulfillmentEvidenceDenied(RuntimeError):
    """The request cannot disclose or report this original bound obligation."""


class FulfillmentEvidenceInvalid(ValueError):
    """The closed evidence request is invalid."""


class FulfillmentReportConflict(RuntimeError):
    """An event changed or another successful receipt already owns the award."""


class FulfillmentExceptionConflict(RuntimeError):
    """An exception event changed or references another successful receipt."""


class FulfillmentEvidenceUnavailable(RuntimeError):
    """Current source, custody, authorization or storage cannot be established."""


class _EvidenceValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")


class FulfillmentSourceIdentity(_EvidenceValue):
    """Original immutable source plus the exact request-resolved reporter."""

    source_instance_id: UUID7
    fulfillment_root_id: UUID7
    award_id: UUID7
    project_id: UUID7
    adapter_binding_id: UUID7
    binding_actor_id: UUID7
    reporter_actor_id: UUID7
    reporter_identity_link_id: UUID7
    source_award_digest: Digest
    obligation_digest: Digest
    admission_generation: int = Field(ge=1, le=9_223_372_036_854_775_807)


class FulfillmentReportAuthorityFacts(FulfillmentSourceIdentity):
    """New or retained report identity; replay retains its original generation."""

    external_event_id: UUID7
    report_digest: Digest
    recording_lifecycle_generation: int = Field(ge=1, le=9_223_372_036_854_775_807)


class FulfillmentExceptionAuthorityFacts(FulfillmentSourceIdentity):
    """Exact linked successful receipt and one immutable exception event."""

    exception_event_id: UUID7
    exception_digest: Digest
    original_fulfillment_event_id: UUID7
    recording_lifecycle_generation: int = Field(ge=1, le=9_223_372_036_854_775_807)


class FulfillmentSourceReadAuthorityFacts(FulfillmentSourceIdentity):
    """One authenticated source-evidence disclosure under current REV custody."""

    observed_lifecycle_generation: int = Field(ge=1, le=9_223_372_036_854_775_807)


class FulfillmentReportLookupAuthorityFacts(FulfillmentSourceIdentity):
    """A separate exact-event lookup resource, never a source-read substitute."""

    external_event_id: UUID7
    observed_lifecycle_generation: int = Field(ge=1, le=9_223_372_036_854_775_807)


FulfillmentEvidenceAuthorityFacts = (
    FulfillmentReportAuthorityFacts | FulfillmentExceptionAuthorityFacts
    | FulfillmentSourceReadAuthorityFacts | FulfillmentReportLookupAuthorityFacts
)


class FulfillmentEvidenceCurrentCustodyPort(Protocol):
    """COMP consumer view; composition retains the existing REV custody owner."""

    def hold_current(self) -> AbstractAsyncContextManager[
        tuple[CompensationFulfillmentLifecycleFacts, CompensationFulfillmentFence]
    ]:
        """Yield actual generation and the same held fence before request AUTH."""
        ...


class FulfillmentEvidenceAuthority(_EvidenceValue):
    """Detached references to the exact persisted AUTH allow, not a capability."""

    authorization_decision_id: UUID7
    resource_context_digest: Digest


class PreparedFulfillmentEvidence(Protocol):
    """AUTH retains capability lifetime and exact active request principal locks."""

    async def consume_new(self) -> FulfillmentEvidenceAuthority:
        """Consume the exact prepared resource and persist one canonical allow."""
        ...

    async def validate_replay(self, authorization_decision_id: UUID) -> None:
        """Verify retained allow/resource evidence without appending another allow."""
        ...


class FulfillmentEvidenceAuthorizationPort(Protocol):
    """Prepare only after COMP has acquired current root-bound REV custody."""

    def prepare(
        self, facts: FulfillmentEvidenceAuthorityFacts,
    ) -> AbstractAsyncContextManager[PreparedFulfillmentEvidence]:
        """Lock the request actor/link and bind only this exact action resource."""
        ...


class FulfillmentReportAcknowledgement(_EvidenceValue):
    receipt_id: UUID7
    award_id: UUID7
    fulfillment_root_id: UUID7
    external_event_id: UUID7
    report_digest: Digest
    replay: bool


class FulfillmentExceptionAcknowledgement(_EvidenceValue):
    exception_id: UUID7
    award_id: UUID7
    fulfillment_root_id: UUID7
    original_fulfillment_event_id: UUID7
    exception_event_id: UUID7
    exception_digest: Digest
    replay: bool


class CompensationStatusProjection(_EvidenceValue):
    """Rebuildable current evidence projection; earned facts stay immutable."""

    delivery_status: Literal["pending_delivery", "acknowledged_by_adapter"]
    fulfillment_status: Literal["pending", "failed", "fulfilled"]
    fulfillment_attention_required: bool
    latest_receipt_id: UUID7 | None
    latest_exception_id: UUID7 | None
    last_failure_code: FulfillmentFailureCode | None
    updated_at: AwareDatetime
