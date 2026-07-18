"""Request context and stable API error primitives."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import logging
from typing import Any
from uuid import RFC_4122, UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = b"x-request-id"
CORRELATION_ID_HEADER = b"x-correlation-id"
REQUEST_ID_STATE_KEY = "request_id"
CORRELATION_ID_STATE_KEY = "correlation_id"
LOGGER = logging.getLogger(__name__)


class ApiError(BaseModel):
    """Canonical machine-readable API error."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any]
    correlation_id: str
    retryable: bool


class ApiErrorResponse(BaseModel):
    """Canonical error plus additive legacy compatibility fields."""

    model_config = ConfigDict(extra="forbid")

    error: ApiError
    detail: Any | None = None


class StructuredHTTPException(HTTPException):
    """HTTP exception carrying an explicit canonical error classification."""

    def __init__(
        self,
        *,
        status_code: int,
        detail: Any,
        error_code: str,
        error_message: str,
        retryable: bool = False,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = error_code
        self.error_message = error_message
        self.retryable = retryable


def request_ids(request: Request) -> tuple[str, str]:
    """Return the request-scoped canonical request and correlation IDs."""
    state = request.scope.setdefault("state", {})
    request_id = state.get(REQUEST_ID_STATE_KEY)
    correlation_id = state.get(CORRELATION_ID_STATE_KEY)
    if not isinstance(request_id, str) or not isinstance(correlation_id, str):
        fallback = str(uuid4())
        state[REQUEST_ID_STATE_KEY] = fallback
        state[CORRELATION_ID_STATE_KEY] = fallback
        return fallback, fallback
    return request_id, correlation_id


def error_payload(
    request: Request,
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
    compatibility: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one canonical error body with optional legacy fields."""
    _, correlation_id = request_ids(request)
    payload: dict[str, Any] = dict(compatibility or {})
    payload["error"] = {
        "code": code,
        "message": message,
        "details": details or {},
        "correlation_id": correlation_id,
        "retryable": retryable,
    }
    return payload


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
    compatibility: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Return a structured JSON error with canonical response IDs."""
    request_id, correlation_id = request_ids(request)
    response_headers = dict(headers or {})
    response_headers["X-Request-ID"] = request_id
    response_headers["X-Correlation-ID"] = correlation_id
    return JSONResponse(
        status_code=status_code,
        content=error_payload(
            request,
            code=code,
            message=message,
            details=details,
            retryable=retryable,
            compatibility=compatibility,
        ),
        headers=response_headers,
    )


def _header_value(scope: Scope, name: bytes) -> bytes | None:
    values = [value for key, value in scope.get("headers", ()) if key.lower() == name]
    if len(values) > 1:
        raise ValueError("duplicate request context header")
    if not values:
        return None
    if b"," in values[0]:
        raise ValueError("combined request context header")
    return values[0]


def _canonical_uuid(value: bytes) -> str:
    if len(value) != 36:
        raise ValueError("invalid request context header")
    try:
        text = value.decode("ascii")
        parsed = UUID(text)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("invalid request context header") from exc
    if (
        parsed.int == 0
        or parsed.variant != RFC_4122
        or parsed.version not in range(1, 9)
        or str(parsed) != text
    ):
        raise ValueError("invalid request context header")
    return text


def _resolve_request_ids(scope: Scope) -> tuple[str, str]:
    raw_request_id = _header_value(scope, REQUEST_ID_HEADER)
    raw_correlation_id = _header_value(scope, CORRELATION_ID_HEADER)
    request_id = str(uuid4()) if raw_request_id is None else _canonical_uuid(raw_request_id)
    correlation_id = (
        request_id if raw_correlation_id is None else _canonical_uuid(raw_correlation_id)
    )
    return request_id, correlation_id


def _response_headers(
    headers: Sequence[tuple[bytes, bytes]], request_id: str, correlation_id: str
) -> list[tuple[bytes, bytes]]:
    retained = [
        (name, value)
        for name, value in headers
        if name.lower() not in {REQUEST_ID_HEADER, CORRELATION_ID_HEADER}
    ]
    retained.extend(
        [
            (REQUEST_ID_HEADER, request_id.encode("ascii")),
            (CORRELATION_ID_HEADER, correlation_id.encode("ascii")),
        ]
    )
    return retained


class RequestContextMiddleware:
    """Validate request context and append canonical IDs without buffering."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        try:
            request_id, correlation_id = _resolve_request_ids(scope)
        except ValueError:
            request_id = correlation_id = str(uuid4())
            state[REQUEST_ID_STATE_KEY] = request_id
            state[CORRELATION_ID_STATE_KEY] = correlation_id
            response = error_response(
                Request(scope, receive),
                status_code=400,
                code="invalid_request",
                message="Invalid request identifier",
                compatibility={"detail": "Invalid request identifier"},
            )
            await response(scope, receive, send)
            return

        state[REQUEST_ID_STATE_KEY] = request_id
        state[CORRELATION_ID_STATE_KEY] = correlation_id
        response_started = False

        async def send_with_context(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                message["headers"] = _response_headers(
                    message.get("headers", ()), request_id, correlation_id
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        except Exception:
            if response_started:
                LOGGER.error(
                    "request_failed_after_response_start",
                    extra={"correlation_id": correlation_id},
                )
                return
            LOGGER.error(
                "request_failed_before_response_start",
                extra={"correlation_id": correlation_id},
            )
            response = error_response(
                Request(scope, receive),
                status_code=500,
                code="internal_error",
                message="Internal server error",
                compatibility={"detail": "Internal server error"},
            )
            await response(scope, receive, send)


def install_api_control_openapi(app: FastAPI) -> None:
    """Document request context headers across the existing route inventory."""
    original_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = original_openapi()
        schemas = schema.setdefault("components", {}).setdefault("schemas", {})
        schemas["HTTPValidationError"] = {
            "type": "object",
            "required": ["detail", "error"],
            "properties": {
                "detail": {"type": "array", "items": {"type": "object"}},
                "error": {"$ref": "#/components/schemas/ApiError"},
            },
            "additionalProperties": False,
        }
        request_parameters = tuple(
            {
                "name": header,
                "in": "header",
                "required": False,
                "schema": {
                    "type": "string",
                    "format": "uuid",
                    "minLength": 36,
                    "maxLength": 36,
                },
            }
            for header in ("X-Request-ID", "X-Correlation-ID")
        )
        response_headers = {
            "X-Request-ID": {
                "required": True,
                "schema": {"type": "string", "format": "uuid"},
            },
            "X-Correlation-ID": {
                "required": True,
                "schema": {"type": "string", "format": "uuid"},
            },
        }
        methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
        for path, path_item in schema.get("paths", {}).items():
            for method, operation in path_item.items():
                if method not in methods:
                    continue
                parameters = operation.setdefault("parameters", [])
                present = {
                    (parameter.get("in"), parameter.get("name", "").lower())
                    for parameter in parameters
                    if isinstance(parameter, dict)
                }
                for parameter in request_parameters:
                    identity = (parameter["in"], parameter["name"].lower())
                    if identity not in present:
                        parameters.append(parameter)
                responses = operation.get("responses", {})
                if path not in {"/health", "/api/v1/health"}:
                    applicable_errors = {
                        "401": "Authentication failed.",
                        "403": "Permission denied.",
                        "503": "Identity verification unavailable.",
                    }
                    if "{" in path:
                        applicable_errors["404"] = "Resource not found."
                    if "{" in path and method in {"post", "put", "patch", "delete"}:
                        applicable_errors["409"] = "Request conflict."
                    for status, description in applicable_errors.items():
                        headers = dict(response_headers)
                        if status == "401":
                            headers["WWW-Authenticate"] = {"schema": {"type": "string"}}
                        responses.setdefault(
                            status,
                            {
                                "description": description,
                                "headers": headers,
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "$ref": "#/components/schemas/ApiErrorResponse"
                                        }
                                    }
                                },
                            },
                        )
                for response in responses.values():
                    headers = response.setdefault("headers", {})
                    for name, header_schema in response_headers.items():
                        headers.setdefault(name, header_schema)
        app.openapi_schema = schema
        return schema

    app.openapi = openapi
