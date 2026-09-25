from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx2 as httpx
from jsonschema import Draft202012Validator, ValidationError  # type: ignore[import-untyped]

from workstream_mcp.config import Settings
from workstream_mcp.errors import SafeFailure
from workstream_mcp.schemas import (
    authorization_context_output_validator,
    profile_output_validator,
    profile_update_output_validator,
)

_SAFE_VALUE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
    re.ASCII,
)
_CORRELATION_HEADERS = ("x-request-id", "x-correlation-id")
_PUBLIC_ERROR_CODES = frozenset(
    {
        "actor_deactivated",
        "actor_suspended",
        "identity_link_revoked",
        "identity_verification_unavailable",
        "internal_error",
        "invalid_request",
        "invalid_token",
        "missing_token",
        "permission_not_granted",
        "project_authorization_resource_not_found",
        "rate_limit_exceeded",
        "service_unavailable",
        "unsupported_subject_kind",
        "validation_error",
    }
)


@dataclass(frozen=True, slots=True)
class GatewayResult:
    data: dict[str, Any] | None = None
    failure: SafeFailure | None = None


class ResponseTooLarge(Exception):
    """The upstream response exceeded the configured byte bound."""


class WorkstreamGateway:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client
        self._slots = asyncio.Semaphore(settings.max_in_flight)

    async def profile_get(self, bearer: str, correlation_id: str | None = None) -> GatewayResult:
        return await self._request(
            "GET",
            "/api/v1/actors/me",
            bearer,
            profile_output_validator(),
            correlation_id,
        )

    async def profile_update(
        self,
        bearer: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> GatewayResult:
        return await self._request(
            "PATCH",
            "/api/v1/actors/me",
            bearer,
            profile_update_output_validator(),
            correlation_id,
            json_body=payload,
            mutation=True,
        )

    async def authorization_context_get(
        self,
        bearer: str,
        project_id: str,
        correlation_id: str | None = None,
    ) -> GatewayResult:
        return await self._request(
            "GET",
            "/api/v1/actors/me/authorization-context",
            bearer,
            authorization_context_output_validator(),
            correlation_id,
            params={"project_id": project_id},
        )

    async def _request(
        self,
        method: str,
        path: str,
        bearer: str,
        output_validator: Draft202012Validator,
        correlation_id: str | None,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        mutation: bool = False,
    ) -> GatewayResult:
        request_id = correlation_id or str(uuid4())
        try:
            async with asyncio.timeout(self._settings.total_timeout_seconds):
                async with self._slots:
                    async with self._client.stream(
                        method,
                        path,
                        headers={
                            "Authorization": bearer,
                            "Accept": "application/json",
                            "Accept-Encoding": "identity",
                            "X-Request-ID": request_id,
                        },
                        json=json_body,
                        params=params,
                    ) as response:
                        body = await self._bounded_body(response)
                        correlation_id = self._correlation_id(response, request_id)
                        if response.status_code != 200:
                            failure = self._api_failure(response.status_code, body, correlation_id)
                            # Proxy errors and unexpected successes cannot prove rollback.
                            if mutation and (
                                response.status_code < 400 or response.status_code >= 500
                            ):
                                failure = SafeFailure(
                                    "workstream_execution_uncertain",
                                    status=response.status_code,
                                    code=failure.code,
                                    correlation_id=correlation_id,
                                )
                            return GatewayResult(failure=failure)
                        media_type = (
                            response.headers.get("content-type", "")
                            .split(";", 1)[0]
                            .strip()
                            .lower()
                        )
                        if media_type != "application/json":
                            return GatewayResult(
                                failure=SafeFailure(
                                    (
                                        "workstream_execution_uncertain"
                                        if mutation
                                        else "invalid_api_response"
                                    ),
                                    status=502,
                                    correlation_id=correlation_id,
                                )
                            )
                        try:
                            payload = json.loads(body)
                            if not isinstance(payload, dict):
                                raise ValueError
                            output_validator.validate(payload)
                        except (ValueError, RecursionError, ValidationError):
                            return GatewayResult(
                                failure=SafeFailure(
                                    (
                                        "workstream_execution_uncertain"
                                        if mutation
                                        else "invalid_api_response"
                                    ),
                                    status=502,
                                    correlation_id=correlation_id,
                                )
                            )
                        return GatewayResult(data=payload)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            if mutation:
                return GatewayResult(
                    failure=SafeFailure(
                        "workstream_execution_uncertain",
                        status=504,
                        correlation_id=request_id,
                    )
                )
            return GatewayResult(
                failure=SafeFailure("workstream_timeout", status=504, retryable=True)
            )
        except httpx.TimeoutException:
            if mutation:
                return GatewayResult(
                    failure=SafeFailure(
                        "workstream_execution_uncertain",
                        status=504,
                        correlation_id=request_id,
                    )
                )
            return GatewayResult(
                failure=SafeFailure("workstream_timeout", status=504, retryable=True)
            )
        except ResponseTooLarge:
            if mutation:
                return GatewayResult(
                    failure=SafeFailure(
                        "workstream_execution_uncertain",
                        status=502,
                        correlation_id=request_id,
                    )
                )
            return GatewayResult(failure=SafeFailure("workstream_response_too_large", status=502))
        except httpx.HTTPError:
            if mutation:
                return GatewayResult(
                    failure=SafeFailure(
                        "workstream_execution_uncertain",
                        status=502,
                        correlation_id=request_id,
                    )
                )
            return GatewayResult(
                failure=SafeFailure("workstream_unavailable", status=502, retryable=True)
            )
        except Exception:  # pragma: no cover
            return GatewayResult(failure=SafeFailure("adapter_internal_error", status=500))

    async def _bounded_body(self, response: httpx.Response) -> bytes:
        content_encoding = response.headers.get("content-encoding", "identity").lower()
        if content_encoding != "identity":
            raise ResponseTooLarge
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self._settings.max_response_bytes:
                    raise ResponseTooLarge
            except ValueError:
                pass
        if response.is_stream_consumed:
            if len(response.content) > self._settings.max_response_bytes:
                raise ResponseTooLarge
            return response.content
        body = bytearray()
        async for chunk in response.aiter_raw():
            body.extend(chunk)
            if len(body) > self._settings.max_response_bytes:
                raise ResponseTooLarge
        return bytes(body)

    @staticmethod
    def _correlation_id(response: httpx.Response, fallback: str) -> str:
        for name in _CORRELATION_HEADERS:
            value = response.headers.get(name)
            if value and _SAFE_VALUE.fullmatch(value):
                return str(value)
        return fallback

    @staticmethod
    def _api_failure(status: int, body: bytes, correlation_id: str) -> SafeFailure:
        code = None
        if len(body) <= 8_192:
            try:
                payload = json.loads(body)
                error = payload.get("error") if isinstance(payload, dict) else None
                candidate = error.get("code") if isinstance(error, dict) else None
                if isinstance(candidate, str) and candidate in _PUBLIC_ERROR_CODES:
                    code = candidate
            except (ValueError, RecursionError):
                pass
        return SafeFailure(
            "workstream_request_failed",
            status=status,
            code=code,
            correlation_id=correlation_id,
            retryable=status in {429, 502, 503, 504},
        )


def create_http_client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.api_url,
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(
            connect=settings.connect_timeout_seconds,
            read=settings.read_timeout_seconds,
            write=settings.connect_timeout_seconds,
            pool=settings.connect_timeout_seconds,
        ),
        limits=httpx.Limits(
            max_connections=settings.max_in_flight,
            max_keepalive_connections=settings.max_in_flight,
        ),
    )
