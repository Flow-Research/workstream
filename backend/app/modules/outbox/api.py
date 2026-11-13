"""Immutable delivery facts; none of these values grant feature authority."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal, NoReturn, Protocol, Self
import re
import json
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, GetCoreSchemaHandler, field_validator, model_validator
from pydantic_core import SchemaValidator, core_schema


class DeliveryUnavailable(Exception):
    """Concealed invalid, stale, denied or unavailable delivery operation."""


class DeliveryPersistenceError(Exception):
    """Sanitized database observation or delivery failure."""


class DeliveryValue(BaseModel):
    """Closed immutable values with strict scalar admission."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)


class OutboxClaim(DeliveryValue):
    """Exact lease facts, not authority or proof of committed invocation."""

    event_id: UUID
    project_id: UUID
    payload_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    claim_generation: int = Field(ge=1, le=2147483647)
    claim_owner: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,120}$")
    claimed_at: datetime
    claim_expires_at: datetime

    @field_validator("event_id", "project_id")
    @classmethod
    def plain_uuid(cls, value: UUID) -> UUID:
        """Detach driver UUID subclasses at the public value boundary."""
        return UUID(str(value))

    @field_validator("claimed_at", "claim_expires_at")
    @classmethod
    def aware_utc(cls, value: datetime) -> datetime:
        """Reject ambiguous leases and normalize exact timestamps."""
        normalized = None
        try:
            if value.utcoffset() is not None:
                normalized = value.astimezone(timezone.utc)
        except Exception:
            pass
        if normalized is None:
            raise ValueError("outbox timestamp requires a valid timezone")
        return normalized

    @model_validator(mode="after")
    def ordered_lease(self) -> Self:
        """Require positive lease duration."""
        if not 0 < (self.claim_expires_at - self.claimed_at).total_seconds() <= 3600:
            raise ValueError("outbox lease must be positive and at most one hour")
        return self


class OutboxEventEnvelope(DeliveryValue):
    """Detached immutable event and canonical payload text for one invocation."""

    claim: OutboxClaim
    event_type: str
    event_version: int
    aggregate_type: str
    aggregate_id: UUID
    correlation_id: str
    causation_event_id: UUID | None
    idempotency_key: str
    occurred_at: datetime
    payload_json: str


class HandlerOutcome(StrEnum):
    """Only RETRY asserts that repeating the feature operation is safe."""

    ACKNOWLEDGE = "acknowledge"
    RETRY = "retry"
    REJECT = "reject"


class FinalizationCause(StrEnum):
    """Closed reasons used to construct database-timed outcomes."""

    ACKNOWLEDGE = "acknowledge"
    RETRY = "retry"
    REJECT = "reject"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class DeliveryReceipt(DeliveryValue):
    """Exact committed outcome including its canonical digest and claim."""

    claim: OutboxClaim
    outcome_json: str
    outcome_digest: str


class CommittedInvocationObservation(DeliveryValue):
    """Point-in-time facts only: no lease extension, authority or feature fence."""

    claim: OutboxClaim
    observed_at: datetime


class CommittedInvocationPort(Protocol):
    """Independent committed observation, never a dispatcher writer session."""

    async def observe_invocation(
        self,
        envelope: OutboxEventEnvelope,
    ) -> CommittedInvocationObservation | None:
        """Return one concealed unavailable result for all noncurrent invocations."""
        ...


class InvocationFencePort(Protocol):
    """Caller-transaction custody lock; not feature authorization or a lease extension."""

    async def fence_invocation(
        self, envelope: OutboxEventEnvelope,
    ) -> CommittedInvocationObservation | None:
        """Lock event then attempt; hold exact current custody through caller commit."""
        ...


class OutboxHandler(Protocol):
    """Feature owner supplies its own AUTH, transaction fence and idempotency."""

    async def __call__(self, envelope: OutboxEventEnvelope) -> HandlerOutcome:
        """Return safe bounded disposition, never provider payload or authority."""
        ...


class DeliveryOptions(DeliveryValue):
    """Explicit bounded composition options; no environment or plugin framework."""

    lease_seconds: int = Field(default=300, ge=1, le=3600)
    handler_timeout_seconds: int = Field(default=240, ge=1, le=3600)
    max_attempts: int = Field(default=5, ge=1, le=100)
    retry_base_seconds: int = Field(default=5, ge=1, le=3600)
    retry_cap_seconds: int = Field(default=300, ge=1, le=86400)

    @model_validator(mode="after")
    def ordered_limits(self) -> Self:
        """Leave a lease margin and bound retry scheduling."""
        if (
            self.handler_timeout_seconds >= self.lease_seconds
            or self.retry_cap_seconds < self.retry_base_seconds
        ):
            raise ValueError("outbox delivery limits are inconsistent")
        return self


class DrainObservation(DeliveryValue):
    """One SQL snapshot; overlapping counts must not be summed as readiness."""

    project_id: UUID
    observed_at: datetime
    pending: int
    claimed: int
    retryable: int
    invoked: int
    unresolved: int
    unsupported: int
    dead_letter: int


class DeliveryCandidate(DeliveryValue):
    """Untrusted delivery selectors, without payload or authority facts."""

    event_id: UUID
    project_id: UUID
    event_type: str


class DeliveryCandidatePage(DeliveryValue):
    """Bounded UUID-keyset discovery; eligibility is rechecked by delivery."""

    items: tuple[DeliveryCandidate, ...]
    next_after: UUID | None


class ReconciliationChildObservation(DeliveryValue):
    """The sole child event linked to one original terminal UNKNOWN attempt."""

    event_id: UUID
    payload_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    payload_json: str
    occurred_at: datetime
    state: Literal["pending", "active", "acknowledged", "unknown", "held"]


class FinalizedUnknownDelivery(DeliveryValue):
    """Exact immutable terminal invocation and optional reconciliation child."""

    envelope: OutboxEventEnvelope
    finalized_at: datetime
    error_code: Literal["INVOKE_OUTCOME_UNKNOWN"]
    child: ReconciliationChildObservation | None = None


class FinalizedUnknownDeliveryPage(DeliveryValue):
    """Stable project-scoped delivery page before feature classification."""

    items: tuple[FinalizedUnknownDelivery, ...]
    has_more: bool


class FinalizedUnknownDeliveryPort(Protocol):
    """OUTBOX-owned terminal UNKNOWN observation and locking boundary."""

    async def list_finalized_unknown(
        self,
        *,
        project_id: UUID,
        event_types: tuple[tuple[str, int], ...],
        child_event_type: str,
        after: tuple[datetime, UUID] | None,
        limit: int,
    ) -> FinalizedUnknownDeliveryPage: ...

    async def read_finalized_unknown(
        self,
        *,
        project_id: UUID,
        event_id: UUID,
        event_types: tuple[tuple[str, int], ...],
        child_event_type: str,
        lock: bool,
    ) -> FinalizedUnknownDelivery | None: ...

    async def fence_reconciliation(
        self,
        *,
        original: OutboxEventEnvelope,
        child: OutboxEventEnvelope,
        event_types: tuple[tuple[str, int], ...],
        child_event_type: str,
    ) -> CommittedInvocationObservation | None:
        """Lock immutable original custody then require the exact live child."""
        ...


_KEY = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_SECRET_KEYS = frozenset(
    {
        "access_token",
        "artifact_bytes",
        "authorization",
        "bearer_token",
        "cookie",
        "credentials",
        "id_token",
        "jwks",
        "password",
        "raw_callback",
        "raw_provider_response",
        "refresh_token",
        "request_body",
        "response_body",
        "secret",
        "signed_url",
    }
)
_SECRET_KEY_PARTS = frozenset(
    {"credential", "credentials", "password", "secret", "token"}
)
_COMPACT_SECRET_LEXEMES = (
    "credential",
    "jwt",
    "passphrase",
    "password",
    "secret",
    "token",
)
_COMPACT_KEY_LEXEMES = (
    "accesskey",
    "apikey",
    "encryptionkey",
    "keymaterial",
    "privatekey",
    "providerkey",
    "secretkey",
    "signingkey",
)
_KEY_QUALIFIERS = frozenset(
    {"access", "api", "encryption", "private", "provider", "secret", "signing"}
)
_KEY_DESCRIPTORS = frozenset({"data", "material", "payload", "value"})
_MAX_DEPTH = 16
_MAX_MEMBERS = 1024
_MAX_NODES = 4096
_MAX_KEY_BYTES = 128
_MAX_STRING_BYTES = 16_384
_MAX_ENCODING_BUDGET = 262_144
_MAX_INTEGER_MAGNITUDE = 10**38 - 1


class OutboxInputError(TypeError):
    """Raised without payload details when append input is invalid."""


class OutboxIdempotencyConflict(RuntimeError):
    """Raised without payload details when either event identity drifts."""


class OutboxPersistenceError(RuntimeError):
    """Raised without statement parameters when database persistence fails."""


class OutboxAppendDisposition(StrEnum):
    """Closed caller-visible outcomes for append or exact replay."""

    CREATED = "created"
    REPLAYED = "replayed"


def _raise_input_error() -> NoReturn:
    """Raise the public input error from a payload-free frame."""
    raise OutboxInputError("outbox_invalid_input")


def _is_sensitive_key(value: str) -> bool:
    """Reject explicit and conventionally secret-bearing JSON field names."""
    normalized = value.casefold().replace("-", "_")
    ordered_parts = tuple(normalized.split("_"))
    parts = frozenset(ordered_parts)
    key_compound = any(
        part == "key"
        and (
            (index > 0 and ordered_parts[index - 1] in _KEY_QUALIFIERS)
            or (
                index + 1 < len(ordered_parts)
                and ordered_parts[index + 1] in _KEY_DESCRIPTORS
            )
        )
        for index, part in enumerate(ordered_parts)
    )
    return (
        normalized in _SECRET_KEYS
        or bool(parts & _SECRET_KEY_PARTS)
        or normalized == "key"
        or normalized.endswith("_key")
        or key_compound
        or any(lexeme in normalized for lexeme in _COMPACT_SECRET_LEXEMES)
        or any(lexeme in normalized for lexeme in _COMPACT_KEY_LEXEMES)
    )


def _encoding_budget(value: object, *, depth: int, nodes: list[int]) -> int:
    """Return a conservative canonical UTF-8 size bound while validating JSON."""
    nodes[0] += 1
    if nodes[0] > _MAX_NODES:
        raise ValueError("payload_nodes")
    if type(value) is dict:
        if depth > _MAX_DEPTH or len(value) > _MAX_MEMBERS:
            raise ValueError("payload_container")
        budget = 2 + max(0, len(value) - 1)
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("payload_key")
            if _is_sensitive_key(key):
                raise ValueError("payload_sensitive")
            key_bytes = key.encode("utf-8")
            if len(key_bytes) > _MAX_KEY_BYTES or _KEY.fullmatch(key) is None:
                raise ValueError("payload_key")
            budget += (6 * len(key_bytes)) + 3
            budget += _encoding_budget(item, depth=depth + 1, nodes=nodes)
        return budget
    if type(value) is list:
        if depth > _MAX_DEPTH or len(value) > _MAX_MEMBERS:
            raise ValueError("payload_container")
        return 2 + max(0, len(value) - 1) + sum(
            _encoding_budget(item, depth=depth + 1, nodes=nodes) for item in value
        )
    if type(value) is str:
        encoded = value.encode("utf-8")
        if len(encoded) > _MAX_STRING_BYTES:
            raise ValueError("payload_string")
        return (6 * len(encoded)) + 2
    if value is None:
        return 4
    if type(value) is bool:
        return 5
    if type(value) is int:
        if abs(value) > _MAX_INTEGER_MAGNITUDE:
            raise ValueError("payload_integer")
        return len(str(value))
    raise ValueError("payload_type")


def validate_outbox_payload(value: object) -> dict[str, Any]:
    """Validate generic structure, privacy, and resource bounds without encoding."""
    if type(value) is not dict:
        raise ValueError("payload_object")
    if _encoding_budget(value, depth=1, nodes=[0]) > _MAX_ENCODING_BUDGET:
        raise ValueError("payload_size")
    return value


class OutboxAppendInput(BaseModel):
    """Immutable logical event facts accepted by the append participant."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        strict=True,
    )

    event_type: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9._:-]{0,127}$")
    event_version: int = Field(ge=1, le=32767)
    aggregate_type: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    aggregate_id: UUID
    project_id: UUID
    correlation_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,200}$")
    causation_event_id: UUID | None = None
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,200}$")
    payload: dict[str, Any]
    not_before_at: AwareDatetime | None = None

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload_object(cls, value: object) -> object:
        """Reject mapping subclasses before Pydantic traverses their overrides."""
        if type(value) is not dict:
            raise ValueError("payload_object")
        return value

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        """Apply payload-free failure translation at the Pydantic core boundary."""
        inner_schema = handler(source_type)
        string_validator = SchemaValidator(inner_schema)

        def admit(
            value: object,
            validator: core_schema.ValidatorFunctionWrapHandler,
            info: core_schema.ValidationInfo,
        ) -> object:
            """Preserve validation mode while detaching every rejected input."""
            admitted = None
            try:
                if info.mode == "string":
                    admitted = string_validator.validate_strings(value)
                elif info.mode == "json":
                    # Preserve JSON datetime/UUID semantics through the privacy
                    # wrapper instead of revalidating decoded JSON as Python.
                    admitted = string_validator.validate_json(json.dumps(value))
                else:
                    admitted = validator(value)
            except Exception:  # noqa: BLE001 - rejected input must not escape diagnostics
                admitted = None
            if admitted is None:
                value = None
                validator = None
                _raise_input_error()
            return admitted

        return core_schema.with_info_wrap_validator_function(admit, inner_schema)

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        """Reject noncanonical, sensitive, or unbounded generic payloads."""
        validate_outbox_payload(self.payload)
        return self


class OutboxAppendResult(BaseModel):
    """Minimal immutable append result; operational state is not exposed."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    event_id: UUID
    disposition: OutboxAppendDisposition
    payload_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    occurred_at: datetime


class OutboxDeliveryObservation(DeliveryValue):
    """Detached operational facts for an exactly matched feature-owned event."""

    event_id: UUID
    state: Literal["pending", "claimed", "retryable", "acknowledged", "dead_letter", "cancelled"]
    attempt_count: int = Field(ge=0)
    next_attempt_at: datetime | None
    finalized_at: datetime | None
    error_code: str | None = Field(pattern=r"^[A-Z][A-Z0-9_]{0,79}$")


class OutboxAppendPort(Protocol):
    async def require_existing(self, event_id: UUID | None, value: OutboxAppendInput) -> UUID:
        """Require exact retained custody by logical key and optional record ID."""
        ...

    async def observe_delivery(self, event_id: UUID, value: OutboxAppendInput) -> OutboxDeliveryObservation:
        """Read delivery facts only after exact immutable feature custody matches."""
        ...

    async def append(self, value: OutboxAppendInput) -> OutboxAppendResult:
        """Flush an exact event in the caller transaction without committing."""
        ...
