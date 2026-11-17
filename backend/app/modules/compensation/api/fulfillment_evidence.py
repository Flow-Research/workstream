"""COMP-owned source/evidence values and opaque authorization collaboration.

Detached facts and stored authorization references do not confer authority. Only
an AUTH-owned live prepared operation may authorize a new append or exact replay.
"""

from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
import json
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import (
    AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, JsonValue,
    PlainSerializer, UUID7, WithJsonSchema, field_validator, model_validator,
)

from app.core.financial_wire import canonical_utc_timestamp
from app.core.hashing import canonical_json_hash
from app.modules.compensation.api.fulfillment_contracts import (
    decode_obligation, decode_fulfillment_report, decode_fulfillment_exception,
    parse_fulfillment_report, parse_fulfillment_exception,
)
from app.modules.finance.api.contract_schema import (
    obligation_schema, fulfillment_report_schema, fulfillment_exception_schema,
)

from app.modules.compensation.api.fulfillment import (
    CompensationFulfillmentFence, CompensationFulfillmentLifecycleFacts,
)

Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
FulfillmentFailureCode = Literal[
    "ADAPTER_REJECTED", "DESTINATION_UNAVAILABLE", "PROVIDER_UNAVAILABLE",
    "PROVIDER_TIMEOUT", "UNKNOWN_PROVIDER_FAILURE",
]


def _evidence_time(value):
    """Validate wire timestamp spelling before parsing; retain typed datetime inputs."""
    return canonical_utc_timestamp(value) if isinstance(value, str) else value


def _evidence_time_json(value: datetime) -> str:
    """Serialize evidence timestamps as UTC with exactly six fractional digits."""
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _wire_bytes(value) -> bytes:
    """Encode a JSON object for the closed financial decoder, refusing nonfinite values."""
    if not isinstance(value, dict):
        raise ValueError("financial evidence body must be an object")
    return json.dumps(value, allow_nan=False).encode("utf-8")


def _obligation_body(value):
    """Validate a detached obligation with the canonical financial contract decoder."""
    return decode_obligation(_wire_bytes(value))


def _report_body(value):
    """Validate report shape without inventing an obligation or receiver timestamp."""
    return parse_fulfillment_report(_wire_bytes(value))


def _exception_body(value):
    """Validate incident shape before contextual parent and obligation checks."""
    return parse_fulfillment_exception(_wire_bytes(value))


_EvidenceTimestamp = Annotated[
    AwareDatetime, BeforeValidator(_evidence_time),
    PlainSerializer(_evidence_time_json, return_type=str, when_used="json"),
    WithJsonSchema(fulfillment_report_schema()["properties"]["reported_at"]),
]
_ObligationBody = Annotated[dict[str, JsonValue], BeforeValidator(_obligation_body),
                           WithJsonSchema(obligation_schema())]
_ReportBody = Annotated[dict[str, JsonValue], BeforeValidator(_report_body),
                       WithJsonSchema(fulfillment_report_schema())]
_ExceptionBody = Annotated[dict[str, JsonValue], BeforeValidator(_exception_body),
                          WithJsonSchema(fulfillment_exception_schema())]
_EvidenceOrdinal = Annotated[int, Field(ge=1, le=9_223_372_036_854_775_807)]


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
    """Reject extra fields and revalidate immutable evidence instances at typed boundaries."""
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
    """Identify the immutable report and distinguish exact replay from a new append."""
    receipt_id: UUID7
    award_id: UUID7
    fulfillment_root_id: UUID7
    external_event_id: UUID7
    report_digest: Digest
    replay: bool


class FulfillmentExceptionAcknowledgement(_EvidenceValue):
    """Identify the linked immutable incident and its exact replay outcome."""
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
    updated_at: _EvidenceTimestamp


class FulfillmentRecordedReport(_EvidenceValue):
    """Operational receipt evidence; its body grants no reporting authority."""

    acknowledgement: FulfillmentReportAcknowledgement
    report_body: _ReportBody
    received_at: _EvidenceTimestamp
    evidence_ordinal: _EvidenceOrdinal
    recording_lifecycle_generation: _EvidenceOrdinal

    @model_validator(mode="after")
    def require_exact_recorded_report(self):
        """Bind the retained report body and digest to its replay acknowledgement."""
        ack, body = self.acknowledgement, self.report_body
        if (not ack.replay or canonical_json_hash(body) != ack.report_digest
                or any(body[key] != str(getattr(ack, key)) for key in (
                    "award_id", "fulfillment_root_id", "external_event_id"))):
            raise ValueError("recorded report identity or digest differs")
        return self


class FulfillmentRecordedException(_EvidenceValue):
    """One immutable linked incident; never an adjustment or repayment."""

    acknowledgement: FulfillmentExceptionAcknowledgement
    original_receipt_id: UUID7
    exception_body: _ExceptionBody
    received_at: _EvidenceTimestamp
    evidence_ordinal: _EvidenceOrdinal
    recording_lifecycle_generation: _EvidenceOrdinal

    @model_validator(mode="after")
    def require_exact_recorded_exception(self):
        """Bind the retained incident body and digest to its replay acknowledgement."""
        ack, body = self.acknowledgement, self.exception_body
        if (not ack.replay or canonical_json_hash(body) != ack.exception_digest
                or any(body[key] != str(getattr(ack, key)) for key in (
                    "award_id", "fulfillment_root_id", "original_fulfillment_event_id", "exception_event_id"))):
            raise ValueError("recorded exception identity or digest differs")
        return self


class FulfillmentSourceEvidence(_EvidenceValue):
    """Bounded authenticated source read, subject to fresh owner currentness."""

    contract_version: Literal[1]
    source_instance_id: UUID7
    obligation: _ObligationBody
    status: CompensationStatusProjection
    fulfilled_external_event_id: UUID7 | None
    latest_receipt: FulfillmentRecordedReport | None
    fulfilled_receipt: FulfillmentRecordedReport | None
    latest_exception: FulfillmentRecordedException | None

    @field_validator("contract_version", mode="before")
    @classmethod
    def require_integer_version(cls, value):
        """Reject boolean and coerced contract versions before literal validation."""
        if type(value) is not int or value != 1:
            raise ValueError("contract version must be integer one")
        return value

    @model_validator(mode="after")
    def require_source_and_receipt_consistency(self):
        """Reconcile source, parent, ordinal and status facts against canonical evidence."""
        if str(self.source_instance_id) != self.obligation["source_instance_id"]:
            raise ValueError("source instance differs")
        latest, fulfilled, exception = self.latest_receipt, self.fulfilled_receipt, self.latest_exception
        for report in (latest, fulfilled):
            if report is not None:
                decode_fulfillment_report(_wire_bytes(report.report_body), obligation=self.obligation,
                                          received_at=report.received_at)
        if fulfilled is not None:
            if (fulfilled.report_body["reported_status"] != "fulfilled" or latest is None
                    or latest.evidence_ordinal < fulfilled.evidence_ordinal
                    or self.fulfilled_external_event_id != fulfilled.acknowledgement.external_event_id):
                raise ValueError("fulfilled receipt differs")
            if latest.acknowledgement.receipt_id == fulfilled.acknowledgement.receipt_id:
                if latest != fulfilled:
                    raise ValueError("same receipt has changed evidence")
            elif latest.evidence_ordinal == fulfilled.evidence_ordinal:
                raise ValueError("receipt ordinals collide")
        elif self.fulfilled_external_event_id is not None:
            raise ValueError("fulfilled event lacks receipt")
        if exception is not None:
            if (fulfilled is None or exception.original_receipt_id != fulfilled.acknowledgement.receipt_id
                    or exception.evidence_ordinal <= fulfilled.evidence_ordinal
                    or (latest is not None and exception.evidence_ordinal == latest.evidence_ordinal)):
                raise ValueError("exception parent or ordinal differs")
            decode_fulfillment_exception(_wire_bytes(exception.exception_body), obligation=self.obligation,
                fulfilled_report=fulfilled.report_body, fulfilled_received_at=fulfilled.received_at,
                received_at=exception.received_at)
        if latest is not None:
            if self.status.delivery_status != "acknowledged_by_adapter":
                raise ValueError("recorded callback lacks adapter acknowledgement")
            if (latest.report_body["reported_status"] == "fulfilled"
                    and (fulfilled is None or latest.acknowledgement.receipt_id != fulfilled.acknowledgement.receipt_id)):
                raise ValueError("multiple successful receipts differ")
        expected = "fulfilled" if fulfilled is not None else "failed" if latest is not None else "pending"
        if (self.status.fulfillment_status != expected
                or (latest is not None and latest.report_body["reported_status"] == "fulfilled" and fulfilled is None)
                or self.status.fulfillment_attention_required != (exception is not None)
                or self.status.latest_receipt_id != (latest.acknowledgement.receipt_id if latest else None)
                or self.status.latest_exception_id != (exception.acknowledgement.exception_id if exception else None)):
            raise ValueError("source status differs from retained evidence")
        if latest is not None and latest.report_body["reported_status"] == "failed":
            if self.status.last_failure_code != latest.report_body["failure_code"]:
                raise ValueError("latest failure differs")
        elif latest is None and self.status.last_failure_code is not None:
            raise ValueError("failure lacks evidence")
        newest = max((row for row in (latest, exception) if row is not None),
                     key=lambda row: row.evidence_ordinal, default=None)
        if newest is not None and self.status.updated_at != newest.received_at:
            raise ValueError("updated time differs from latest ordinal")
        return self
