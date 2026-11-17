"""Typed provider boundary for one policy-authorized checker model call."""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from enum import StrEnum
import re
from typing import Protocol

from workstream_external_services import ExternalServiceAdapter


CHECKER_MODEL_CAPABILITY_KEY = "checker_model_generation"
MAX_CHECKER_MODEL_PROMPT_BYTES = 1 * 1024 * 1024
MAX_CHECKER_MODEL_OUTPUT_BYTES = 1 * 1024 * 1024
MAX_CHECKER_MODEL_PROVIDER_ID_LENGTH = 256
MAX_CHECKER_MODEL_NAME_LENGTH = 160
MAX_CHECKER_MODEL_TOKEN_COUNT = 2**63 - 1

_PROVIDER_RESPONSE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_PROVIDER_MODEL_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")


class CheckerModelProviderStatus(StrEnum):
    """Provider-owned state for one accepted response effect."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INCOMPLETE = "incomplete"


class CheckerModelCreateOutcome(StrEnum):
    """Effect classification for exactly one authorized create dispatch."""

    ACCEPTED = "accepted"
    NO_EFFECT = "no_effect"
    UNCERTAIN = "uncertain"


class CheckerModelCreateFailure(StrEnum):
    """Secret-safe reason for a create operation without an accepted observation."""

    REQUEST_BYTES_EXCEEDED = "request_bytes_exceeded"
    INPUT_COUNT_UNAVAILABLE = "input_count_unavailable"
    INPUT_LIMIT_EXCEEDED = "input_limit_exceeded"
    DELIVERY_UNCERTAIN = "delivery_uncertain"
    RESPONSE_INVALID = "response_invalid"


class CheckerModelRecoveryOutcome(StrEnum):
    """Observation classification for retrieval of one known provider response."""

    OBSERVED = "observed"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class CheckerModelRequest:
    """Bounded image-authored prompt without provider-controlled settings."""

    prompt: str = dataclass_field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.prompt, str) or not self.prompt:
            raise ValueError("checker model prompt is invalid")
        try:
            encoded = self.prompt.encode("utf-8")
        except UnicodeError:
            raise ValueError("checker model prompt is invalid") from None
        if len(encoded) > MAX_CHECKER_MODEL_PROMPT_BYTES:
            raise ValueError("checker model prompt is invalid")


@dataclass(frozen=True, slots=True)
class CheckerModelResponseReference:
    """One bounded provider response identity already known to Workstream."""

    provider_response_id: str

    def __post_init__(self) -> None:
        _require_provider_identifier(
            self.provider_response_id,
            maximum_length=MAX_CHECKER_MODEL_PROVIDER_ID_LENGTH,
            label="checker model response identity",
            pattern=_PROVIDER_RESPONSE_IDENTIFIER,
        )


@dataclass(frozen=True, slots=True)
class CheckerModelUsage:
    """Authenticated token facts; reasoning tokens remain part of output tokens."""

    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int

    def __post_init__(self) -> None:
        values = (
            self.input_tokens,
            self.cached_input_tokens,
            self.output_tokens,
            self.reasoning_tokens,
            self.total_tokens,
        )
        if any(
            type(value) is not int or not 0 <= value <= MAX_CHECKER_MODEL_TOKEN_COUNT
            for value in values
        ):
            raise ValueError("checker model usage is invalid")
        if (
            self.cached_input_tokens > self.input_tokens
            or self.reasoning_tokens > self.output_tokens
            or self.total_tokens != self.input_tokens + self.output_tokens
        ):
            raise ValueError("checker model usage is invalid")


@dataclass(frozen=True, slots=True)
class CheckerModelObservation:
    """Bounded provider response facts suitable for private ART evidence."""

    reference: CheckerModelResponseReference
    provider_model: str
    status: CheckerModelProviderStatus
    output_text: str | None = dataclass_field(default=None, repr=False)
    usage: CheckerModelUsage | None = None

    def __post_init__(self) -> None:
        if type(self.reference) is not CheckerModelResponseReference:
            raise ValueError("checker model observation is invalid")
        _require_provider_identifier(
            self.provider_model,
            maximum_length=MAX_CHECKER_MODEL_NAME_LENGTH,
            label="checker model provider identity",
            pattern=_PROVIDER_MODEL_IDENTIFIER,
        )
        if type(self.status) is not CheckerModelProviderStatus:
            raise ValueError("checker model observation is invalid")
        if self.output_text is not None:
            if not isinstance(self.output_text, str):
                raise ValueError("checker model observation is invalid")
            try:
                output_bytes = self.output_text.encode("utf-8")
            except UnicodeError:
                raise ValueError("checker model observation is invalid") from None
            if len(output_bytes) > MAX_CHECKER_MODEL_OUTPUT_BYTES:
                raise ValueError("checker model observation is invalid")
        if self.usage is not None and type(self.usage) is not CheckerModelUsage:
            raise ValueError("checker model observation is invalid")
        if self.status in {
            CheckerModelProviderStatus.QUEUED,
            CheckerModelProviderStatus.IN_PROGRESS,
        } and (self.output_text is not None or self.usage is not None):
            raise ValueError("checker model observation is invalid")
        if self.status is CheckerModelProviderStatus.COMPLETED and (
            self.output_text is None or self.usage is None
        ):
            raise ValueError("checker model observation is invalid")


@dataclass(frozen=True, slots=True)
class CheckerModelCreateResult:
    """Sanitized result of one create attempt, including exact effect certainty."""

    outcome: CheckerModelCreateOutcome
    observation: CheckerModelObservation | None = None
    known_response: CheckerModelResponseReference | None = None
    failure: CheckerModelCreateFailure | None = None

    def __post_init__(self) -> None:
        if type(self.outcome) is not CheckerModelCreateOutcome:
            raise ValueError("checker model create result is invalid")
        if self.outcome is CheckerModelCreateOutcome.ACCEPTED:
            if (
                type(self.observation) is not CheckerModelObservation
                or self.known_response != self.observation.reference
                or self.failure is not None
            ):
                raise ValueError("checker model create result is invalid")
            return
        if self.observation is not None or type(self.failure) is not CheckerModelCreateFailure:
            raise ValueError("checker model create result is invalid")
        if self.outcome is CheckerModelCreateOutcome.NO_EFFECT:
            if self.known_response is not None or self.failure not in {
                CheckerModelCreateFailure.REQUEST_BYTES_EXCEEDED,
                CheckerModelCreateFailure.INPUT_COUNT_UNAVAILABLE,
                CheckerModelCreateFailure.INPUT_LIMIT_EXCEEDED,
            }:
                raise ValueError("checker model create result is invalid")
        elif self.failure not in {
            CheckerModelCreateFailure.DELIVERY_UNCERTAIN,
            CheckerModelCreateFailure.RESPONSE_INVALID,
        }:
            raise ValueError("checker model create result is invalid")


@dataclass(frozen=True, slots=True)
class CheckerModelRecoveryResult:
    """Sanitized result of retrieving one previously accepted provider response."""

    outcome: CheckerModelRecoveryOutcome
    reference: CheckerModelResponseReference
    observation: CheckerModelObservation | None = None

    def __post_init__(self) -> None:
        if (
            type(self.outcome) is not CheckerModelRecoveryOutcome
            or type(self.reference) is not CheckerModelResponseReference
        ):
            raise ValueError("checker model recovery result is invalid")
        if self.outcome is CheckerModelRecoveryOutcome.OBSERVED:
            if (
                type(self.observation) is not CheckerModelObservation
                or self.observation.reference != self.reference
            ):
                raise ValueError("checker model recovery result is invalid")
        elif self.observation is not None:
            raise ValueError("checker model recovery result is invalid")


class CheckerModelProvider(ExternalServiceAdapter, Protocol):
    """Provider-specific transport behind durable Workstream call custody."""

    async def create(self, request: CheckerModelRequest) -> CheckerModelCreateResult:
        """Dispatch one authorized effect exactly once."""

    async def recover(self, reference: CheckerModelResponseReference) -> CheckerModelRecoveryResult:
        """Inspect one known effect without creating another."""

    async def aclose(self) -> None:
        """Close provider transport resources owned by this adapter."""


def _require_provider_identifier(
    value: object,
    *,
    maximum_length: int,
    label: str,
    pattern: re.Pattern[str],
) -> None:
    if (
        not isinstance(value, str)
        or len(value) > maximum_length
        or pattern.fullmatch(value) is None
    ):
        raise ValueError(f"{label} is invalid")
