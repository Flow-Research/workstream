"""OpenRouter Chat Completions transport for policy-bound checker model calls."""

from __future__ import annotations

import json

import httpx

from app.adapters.model_usage.openrouter import (
    OPENROUTER_CHAT_COMPLETIONS_URL,
    bounded_response_bytes,
    openrouter_request_options,
    openrouter_usage,
    preflight_openrouter_profile,
    require_direct_openrouter_model,
)
from app.interfaces.checker_model_provider import (
    CHECKER_MODEL_CAPABILITY_KEY,
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
from app.modules.model_usage.api import ModelCallUnavailable, ProjectModelProfile


OPENROUTER_PROVIDER_KEY = "openrouter"
_IDENTITY = ExternalServiceAdapterIdentity(
    CHECKER_MODEL_CAPABILITY_KEY,
    OPENROUTER_PROVIDER_KEY,
)
_FAILED_FINISH_REASONS = frozenset({"content_filter", "error"})


class OpenRouterCheckerModelProvider:
    """Dispatch one bounded direct-model Chat Completions request without retry."""

    __slots__ = ("_client", "_profile")

    def __init__(self, profile: ProjectModelProfile, client: httpx.AsyncClient) -> None:
        """Bind one immutable OpenRouter profile to an injected no-retry client."""
        if type(profile) is not ProjectModelProfile or (
            profile.spec.provider,
            profile.spec.api,
        ) != ("openrouter", "chat_completions"):
            raise ValueError("OpenRouter checker model profile is invalid")
        require_direct_openrouter_model(profile.spec.model_snapshot)
        if not isinstance(client, httpx.AsyncClient):
            raise ValueError("OpenRouter checker model client is invalid")
        self._profile = profile
        self._client = client

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Return the fixed identity checked by the shared typed factory."""
        return _IDENTITY

    async def create(self, request: CheckerModelRequest) -> CheckerModelCreateResult:
        """Preflight current metadata, then dispatch exactly one paid request."""
        if type(request) is not CheckerModelRequest:
            raise ValueError("checker model request is invalid")
        body_json = self._request_json(request.prompt)
        if len(body_json.encode("utf-8")) > self._profile.spec.maximum_request_bytes:
            return CheckerModelCreateResult(
                CheckerModelCreateOutcome.NO_EFFECT,
                failure=CheckerModelCreateFailure.REQUEST_BYTES_EXCEEDED,
            )

        try:
            # Qualify the full provider window; this is not a prompt tokenizer.
            await preflight_openrouter_profile(self._client, self._profile)
        except ModelCallUnavailable:
            return CheckerModelCreateResult(
                CheckerModelCreateOutcome.NO_EFFECT,
                failure=CheckerModelCreateFailure.INPUT_COUNT_UNAVAILABLE,
            )
        try:
            async with self._client.stream(
                "POST",
                OPENROUTER_CHAT_COMPLETIONS_URL,
                content=body_json,
            ) as response:
                status_code = response.status_code
                try:
                    raw = await bounded_response_bytes(
                        response,
                        self._profile.spec.maximum_response_bytes,
                    )
                except (TypeError, ValueError, UnicodeError):
                    return CheckerModelCreateResult(
                        CheckerModelCreateOutcome.UNCERTAIN,
                        failure=CheckerModelCreateFailure.RESPONSE_INVALID,
                    )
        except Exception:
            return CheckerModelCreateResult(
                CheckerModelCreateOutcome.UNCERTAIN,
                failure=CheckerModelCreateFailure.DELIVERY_UNCERTAIN,
            )

        value = _response_object(raw)
        known_response = _known_response(value)
        if not 200 <= status_code < 300:
            return CheckerModelCreateResult(
                CheckerModelCreateOutcome.UNCERTAIN,
                known_response=known_response,
                failure=CheckerModelCreateFailure.DELIVERY_UNCERTAIN,
            )
        try:
            observation = self._observation(value)
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

    async def recover(
        self, reference: CheckerModelResponseReference
    ) -> CheckerModelRecoveryResult:
        """Report retrieval unavailable without issuing any network request."""
        if type(reference) is not CheckerModelResponseReference:
            raise ValueError("checker model response identity is invalid")
        return CheckerModelRecoveryResult(
            CheckerModelRecoveryOutcome.UNAVAILABLE,
            reference,
        )

    async def aclose(self) -> None:
        """Close the exact HTTP client created for this profile adapter."""
        await self._client.aclose()

    def _request_json(self, prompt: str) -> str:
        body = {
            "model": self._profile.spec.model_snapshot,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self._profile.spec.maximum_output_tokens,
            "stream": False,
            "tools": [],
            "tool_choice": "none",
            "usage": {"include": True},
            "reasoning_effort": self._profile.spec.settings.reasoning_effort,
            "verbosity": self._profile.spec.settings.text_verbosity,
            "temperature": 0,
            "top_p": 1,
            "store": False,
            "parallel_tool_calls": False,
            **openrouter_request_options(),
        }
        return json.dumps(
            body,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )

    def _observation(self, value: object) -> CheckerModelObservation:
        if not isinstance(value, dict):
            raise ValueError("provider response is invalid")
        reference = CheckerModelResponseReference(value.get("id"))
        provider_model = value.get("model")
        if provider_model != self._profile.spec.model_snapshot:
            raise ValueError("provider model identity changed")
        choices = value.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("provider output is invalid")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ValueError("provider output is invalid")
        index = choice.get("index")
        if type(index) is not int or index != 0:
            raise ValueError("provider output is invalid")
        message = choice.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise ValueError("provider output is invalid")
        if (
            message.get("tool_calls") not in (None, [])
            or message.get("function_call") is not None
            or message.get("audio") is not None
        ):
            raise ValueError("provider output is not text-only")
        refusal = message.get("refusal")
        output_text = message.get("content")
        finish_reason = choice.get("finish_reason")
        if isinstance(refusal, str) and refusal:
            if output_text is not None and not isinstance(output_text, str):
                raise ValueError("provider output is invalid")
            if finish_reason not in {"stop", "content_filter"}:
                raise ValueError("provider refusal status is invalid")
            if len(refusal.encode("utf-8")) > self._profile.spec.maximum_output_bytes:
                raise ValueError("provider output exceeds profile bound")
            output_text = None
            status = CheckerModelProviderStatus.FAILED
        elif refusal not in (None, ""):
            raise ValueError("provider output is invalid")
        else:
            status = _provider_status(finish_reason)
            if output_text is None:
                if status is CheckerModelProviderStatus.COMPLETED:
                    raise ValueError("completed provider output is missing")
            elif not isinstance(output_text, str):
                raise ValueError("provider output is invalid")
            elif len(output_text.encode("utf-8")) > self._profile.spec.maximum_output_bytes:
                raise ValueError("provider output exceeds profile bound")
        normalized = openrouter_usage(value.get("usage"))
        if normalized.total_tokens is None:
            raise ValueError("provider usage is incomplete")
        usage = CheckerModelUsage(
            input_tokens=normalized.input_tokens,
            cached_input_tokens=normalized.cached_input_tokens,
            output_tokens=normalized.output_tokens,
            reasoning_tokens=normalized.reasoning_tokens,
            total_tokens=normalized.total_tokens,
        )
        if (
            usage.input_tokens > self._profile.spec.maximum_input_tokens
            or usage.output_tokens > self._profile.spec.maximum_output_tokens
        ):
            raise ValueError("provider usage exceeds profile bound")
        return CheckerModelObservation(
            reference=reference,
            provider_model=provider_model,
            status=status,
            output_text=output_text,
            usage=usage,
        )


def _response_object(raw: bytes) -> object:
    try:
        return json.loads(raw, parse_constant=_reject_constant)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return None


def _known_response(value: object) -> CheckerModelResponseReference | None:
    try:
        if not isinstance(value, dict):
            return None
        return CheckerModelResponseReference(value.get("id"))
    except (TypeError, ValueError):
        return None


def _provider_status(value: object) -> CheckerModelProviderStatus:
    if value == "stop":
        return CheckerModelProviderStatus.COMPLETED
    if value == "length":
        return CheckerModelProviderStatus.INCOMPLETE
    if value in _FAILED_FINISH_REASONS:
        return CheckerModelProviderStatus.FAILED
    raise ValueError("provider finish status is invalid")


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite provider number")


__all__ = ("OPENROUTER_PROVIDER_KEY", "OpenRouterCheckerModelProvider")
