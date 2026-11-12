"""OpenAI Responses transport for policy-bound checker model calls."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any, Literal, Protocol

from app.interfaces.checker_model_provider import (
    CHECKER_MODEL_CAPABILITY_KEY,
    MAX_CHECKER_MODEL_NAME_LENGTH,
    MAX_CHECKER_MODEL_OUTPUT_BYTES,
    MAX_CHECKER_MODEL_PROMPT_BYTES,
    MAX_CHECKER_MODEL_TOKEN_COUNT,
    CheckerModelCreateFailure,
    CheckerModelCreateOutcome,
    CheckerModelCreateResult,
    CheckerModelObservation,
    CheckerModelProviderStatus,
    CheckerModelRecoveryOutcome,
    CheckerModelRecoveryResult,
    CheckerModelRequest,
    CheckerModelResponseReference,
    CheckerModelUsage,
)
from workstream_external_services import ExternalServiceAdapterIdentity


OPENAI_RESPONSES_PROVIDER_KEY = "openai_responses"
_IDENTITY = ExternalServiceAdapterIdentity(
    CHECKER_MODEL_CAPABILITY_KEY,
    OPENAI_RESPONSES_PROVIDER_KEY,
)

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
TextVerbosity = Literal["low", "medium", "high"]
_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
_TEXT_VERBOSITIES = {"low", "medium", "high"}
_MODEL_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


@dataclass(frozen=True, slots=True)
class OpenAIResponsesSettings:
    """Trusted profile settings that an image cannot select or override."""

    api_key: str = field(repr=False, compare=False)
    model: str
    maximum_request_bytes: int
    maximum_input_tokens: int
    maximum_output_tokens: int
    maximum_output_bytes: int
    request_timeout_seconds: float
    reasoning_effort: ReasoningEffort
    text_verbosity: TextVerbosity

    def __post_init__(self) -> None:
        """Reject credentials, model identity, or limits outside the closed profile bounds."""
        if (
            not isinstance(self.api_key, str)
            or not self.api_key
            or len(self.api_key) > 8_192
            or not isinstance(self.model, str)
            or not self.model
            or len(self.model) > MAX_CHECKER_MODEL_NAME_LENGTH
            or _MODEL_IDENTIFIER.fullmatch(self.model) is None
            or type(self.maximum_request_bytes) is not int
            or not 1 <= self.maximum_request_bytes <= MAX_CHECKER_MODEL_PROMPT_BYTES
            or type(self.maximum_input_tokens) is not int
            or not 1 <= self.maximum_input_tokens <= MAX_CHECKER_MODEL_TOKEN_COUNT
            or type(self.maximum_output_tokens) is not int
            or not 1 <= self.maximum_output_tokens <= MAX_CHECKER_MODEL_TOKEN_COUNT
            or type(self.maximum_output_bytes) is not int
            or not 1 <= self.maximum_output_bytes <= MAX_CHECKER_MODEL_OUTPUT_BYTES
            or type(self.request_timeout_seconds) is not float
            or not math.isfinite(self.request_timeout_seconds)
            or not 0.1 <= self.request_timeout_seconds <= 3_600.0
            or self.reasoning_effort not in _REASONING_EFFORTS
            or self.text_verbosity not in _TEXT_VERBOSITIES
        ):
            raise ValueError("OpenAI checker model settings are invalid")


class _InputTokenResource(Protocol):
    """Describe the provider endpoint that counts input without creating an effect."""

    async def count(self, **kwargs: Any) -> object:
        """Count the exact request input without creating a response."""


class _ResponsesResource(Protocol):
    """Describe the exact stored-response operations used by this adapter."""

    input_tokens: _InputTokenResource

    async def create(self, **kwargs: Any) -> object:
        """Create one stored background response."""

    async def retrieve(self, response_id: str, **kwargs: Any) -> object:
        """Retrieve one already known response."""


class _OpenAIClient(Protocol):
    """Describe the bounded client surface owned by one profile adapter."""

    responses: _ResponsesResource

    async def close(self) -> None:
        """Close client transport resources."""


class OpenAIResponsesCheckerModelProvider:
    """Translate one fixed profile to stored OpenAI background Responses calls."""

    __slots__ = ("_client", "_settings")

    def __init__(self, settings: OpenAIResponsesSettings, client: _OpenAIClient) -> None:
        """Bind validated trusted settings to one structurally valid SDK client."""
        if type(settings) is not OpenAIResponsesSettings:
            raise ValueError("OpenAI checker model settings are invalid")
        if not hasattr(client, "responses") or not callable(getattr(client, "close", None)):
            raise ValueError("OpenAI checker model client is invalid")
        self._settings = settings
        self._client = client

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Return the fixed identity checked by the shared typed factory."""
        return _IDENTITY

    async def create(self, request: CheckerModelRequest) -> CheckerModelCreateResult:
        """Count first, then dispatch one create without any adapter retry."""
        if type(request) is not CheckerModelRequest:
            raise ValueError("checker model request is invalid")
        if len(request.prompt.encode("utf-8")) > self._settings.maximum_request_bytes:
            return CheckerModelCreateResult(
                CheckerModelCreateOutcome.NO_EFFECT,
                failure=CheckerModelCreateFailure.REQUEST_BYTES_EXCEEDED,
            )
        try:
            counted = await self._client.responses.input_tokens.count(
                **self._request_parameters(request.prompt)
            )
            input_tokens = getattr(counted, "input_tokens", None)
            if (
                type(input_tokens) is not int
                or not 0 <= input_tokens <= MAX_CHECKER_MODEL_TOKEN_COUNT
            ):
                raise ValueError("provider input count is invalid")
        except Exception:
            return CheckerModelCreateResult(
                CheckerModelCreateOutcome.NO_EFFECT,
                failure=CheckerModelCreateFailure.INPUT_COUNT_UNAVAILABLE,
            )
        if input_tokens > self._settings.maximum_input_tokens:
            return CheckerModelCreateResult(
                CheckerModelCreateOutcome.NO_EFFECT,
                failure=CheckerModelCreateFailure.INPUT_LIMIT_EXCEEDED,
            )

        try:
            response = await self._client.responses.create(
                **self._request_parameters(request.prompt),
                background=True,
                store=True,
                service_tier="default",
                max_output_tokens=self._settings.maximum_output_tokens,
            )
        except Exception:
            return CheckerModelCreateResult(
                CheckerModelCreateOutcome.UNCERTAIN,
                failure=CheckerModelCreateFailure.DELIVERY_UNCERTAIN,
            )

        known_response = _known_response(response)
        try:
            observation = self._observation(response)
        except (TypeError, ValueError, UnicodeError):
            return CheckerModelCreateResult(
                CheckerModelCreateOutcome.UNCERTAIN,
                known_response=known_response,
                failure=CheckerModelCreateFailure.RESPONSE_INVALID,
            )
        return CheckerModelCreateResult(
            CheckerModelCreateOutcome.ACCEPTED,
            observation=observation,
            known_response=observation.reference,
        )

    async def recover(self, reference: CheckerModelResponseReference) -> CheckerModelRecoveryResult:
        """Retrieve the known provider ID once and never issue create."""
        if type(reference) is not CheckerModelResponseReference:
            raise ValueError("checker model response identity is invalid")
        try:
            response = await self._client.responses.retrieve(
                reference.provider_response_id,
            )
        except Exception:
            return CheckerModelRecoveryResult(
                CheckerModelRecoveryOutcome.UNAVAILABLE,
                reference,
            )
        try:
            observation = self._observation(response)
            if observation.reference != reference:
                raise ValueError("provider response identity changed")
        except (TypeError, ValueError, UnicodeError):
            return CheckerModelRecoveryResult(
                CheckerModelRecoveryOutcome.INVALID,
                reference,
            )
        return CheckerModelRecoveryResult(
            CheckerModelRecoveryOutcome.OBSERVED,
            reference,
            observation,
        )

    async def aclose(self) -> None:
        """Close the exact SDK client created for this profile adapter."""
        await self._client.close()

    def _request_parameters(self, prompt: str) -> dict[str, object]:
        """Build provider parameters solely from the locked profile and supplied prompt."""
        return {
            "model": self._settings.model,
            "input": prompt,
            "reasoning": {"effort": self._settings.reasoning_effort},
            "text": {"verbosity": self._settings.text_verbosity},
            "parallel_tool_calls": False,
            "tools": [],
            "truncation": "disabled",
            "timeout": self._settings.request_timeout_seconds,
        }

    def _observation(self, response: object) -> CheckerModelObservation:
        """Validate provider identity, bounds, status, output, and usage as one observation."""
        reference = CheckerModelResponseReference(getattr(response, "id", None))
        if getattr(response, "service_tier", None) != "default":
            raise ValueError("provider pricing tier differs from the locked standard rates")
        provider_model = getattr(response, "model", None)
        if provider_model != self._settings.model:
            raise ValueError("provider model identity changed")
        status = CheckerModelProviderStatus(getattr(response, "status", None))
        output = getattr(response, "output", None)
        if type(output) is not list:
            raise ValueError("provider output is invalid")
        output_text = None if not output else getattr(response, "output_text", None)
        if output_text is not None:
            if not isinstance(output_text, str):
                raise ValueError("provider output is invalid")
            if len(output_text.encode("utf-8")) > self._settings.maximum_output_bytes:
                raise ValueError("provider output exceeds profile bound")
        usage_value = getattr(response, "usage", None)
        usage = None if usage_value is None else _usage(usage_value)
        if usage is not None and (
            usage.input_tokens > self._settings.maximum_input_tokens
            or usage.output_tokens > self._settings.maximum_output_tokens
        ):
            raise ValueError("provider usage exceeds profile bound")
        return CheckerModelObservation(
            reference=reference,
            provider_model=provider_model,
            status=status,
            output_text=output_text,
            usage=usage,
        )


def _known_response(response: object) -> CheckerModelResponseReference | None:
    """Recover a valid provider response identity without trusting other response fields."""
    try:
        return CheckerModelResponseReference(getattr(response, "id", None))
    except (TypeError, ValueError):
        return None


def _usage(value: object) -> CheckerModelUsage:
    """Normalize the provider's nested token counters through the strict usage contract."""
    input_details = getattr(value, "input_tokens_details", None)
    output_details = getattr(value, "output_tokens_details", None)
    return CheckerModelUsage(
        input_tokens=getattr(value, "input_tokens", None),
        cached_input_tokens=getattr(input_details, "cached_tokens", None),
        output_tokens=getattr(value, "output_tokens", None),
        reasoning_tokens=getattr(output_details, "reasoning_tokens", None),
        total_tokens=getattr(value, "total_tokens", None),
    )
