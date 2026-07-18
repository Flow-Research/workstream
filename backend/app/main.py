"""FastAPI application factory for Workstream."""

from __future__ import annotations

import math
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.adapters.artifacts import (
    cleanup_stale_artifact_scratch,
    create_artifact_store_bootstrap,
)
from app.core.api_controls import (
    ApiErrorResponse,
    RequestContextMiddleware,
    StructuredHTTPException,
    error_response,
    install_api_control_openapi,
)
from app.core.auth import build_auth_verifier, cache_auth_verifier, prepare_auth_verifier
from app.core.config import Settings, get_settings
from app.interfaces.artifacts import ArtifactStoreBootstrap, ArtifactStoreNamespaceClaim

PRODUCTION_LIKE_ENVIRONMENTS = {"staging", "preview", "prod", "production"}
MAX_VALIDATION_ERRORS = 20
MAX_VALIDATION_LOCATION_PARTS = 8
MAX_VALIDATION_CODE_LENGTH = 64
ERROR_RESPONSE_HEADERS = {
    "X-Request-ID": {
        "required": True,
        "schema": {"type": "string", "format": "uuid"},
    },
    "X-Correlation-ID": {
        "required": True,
        "schema": {"type": "string", "format": "uuid"},
    },
}
DEFAULT_ERROR_RESPONSES = {
    status_code: {
        "model": ApiErrorResponse,
        "description": description,
        "headers": dict(ERROR_RESPONSE_HEADERS),
    }
    for status_code, description in {
        400: "Invalid request.",
        500: "Internal server error.",
    }.items()
}


@asynccontextmanager
async def _application_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Reject invalid production authentication configuration before serving."""
    settings: Settings = app.state.settings
    if (
        settings.environment in PRODUCTION_LIKE_ENVIRONMENTS
        and not app.state.auth_configuration_valid
    ):
        build_auth_verifier(settings)
    if settings.artifact_store_backend != "disabled":
        bootstrap = create_artifact_store_bootstrap(settings)
        try:
            claim = await _validate_artifact_storage_namespace_at_startup(
                settings,
                bootstrap,
            )
            bootstrap.initialize_after_namespace_claim(claim)
            await cleanup_stale_artifact_scratch(settings)
        finally:
            bootstrap.close()
    yield


async def _validate_artifact_storage_namespace_at_startup(
    settings: Settings,
    bootstrap: ArtifactStoreBootstrap,
) -> ArtifactStoreNamespaceClaim:
    """Call the artifact owner's exact startup namespace fence."""
    try:
        from app.modules.artifacts.service import (
            validate_artifact_storage_namespace_at_startup,
        )
    except ImportError as exc:
        raise RuntimeError("artifact namespace startup validation is unavailable") from exc

    return await validate_artifact_storage_namespace_at_startup(
        bootstrap,
        settings,
    )


def _validation_error_detail(error: dict[str, Any]) -> dict[str, Any]:
    """Return one validation error without raw request input."""
    safe_error: dict[str, Any] = {}
    for key, value in error.items():
        if key == "input":
            safe_error[key] = "redacted"
            continue
        if key == "ctx":
            safe_error[key] = _safe_validation_context(value)
            continue
        safe_error[key] = _json_safe_validation_value(value)
    return safe_error


def _safe_validation_context(value: Any) -> Any:
    """Return validation context without raw exception objects or input."""
    if isinstance(value, dict):
        safe_context: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"input", "error"}:
                safe_context[key] = (
                    item.__class__.__name__ if isinstance(item, BaseException) else "redacted"
                )
                continue
            safe_context[key] = _json_safe_validation_value(item)
        return safe_context
    return _json_safe_validation_value(value)


def _json_safe_validation_value(value: Any) -> Any:
    """Return a JSON-serializable non-sensitive validation error value."""
    if isinstance(value, float) and not math.isfinite(value):
        return "non_finite_number"
    if isinstance(value, dict):
        return {key: _json_safe_validation_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_validation_value(item) for item in value]
    if isinstance(value, BaseException):
        return value.__class__.__name__
    return value


def _validation_summary(error: dict[str, Any]) -> dict[str, Any]:
    """Return bounded type/location evidence for the canonical error object."""
    raw_type = error.get("type")
    error_type = raw_type if isinstance(raw_type, str) and raw_type.isascii() else "validation_error"
    error_type = error_type[:MAX_VALIDATION_CODE_LENGTH]
    location: list[int | str] = []
    raw_location = error.get("loc")
    if isinstance(raw_location, (list, tuple)):
        for part in raw_location[:MAX_VALIDATION_LOCATION_PARTS]:
            if isinstance(part, int):
                location.append(part)
            elif isinstance(part, str) and part.isascii():
                location.append(part[:MAX_VALIDATION_CODE_LENGTH])
            else:
                location.append("redacted")
    return {"type": error_type, "loc": location}


async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return validation errors without echoing non-finite JSON values."""
    errors = exc.errors()
    compatibility_detail = [
        _validation_error_detail(error) for error in errors[:MAX_VALIDATION_ERRORS]
    ]
    return error_response(
        request,
        status_code=422,
        code="invalid_request",
        message="Request validation failed",
        details={
            "errors": [_validation_summary(error) for error in errors[:MAX_VALIDATION_ERRORS]],
            "truncated": len(errors) > MAX_VALIDATION_ERRORS,
        },
        compatibility={"detail": jsonable_encoder(compatibility_detail)},
    )


def _generic_http_error(status_code: int) -> tuple[str, str, bool]:
    """Return the canonical fallback classification for an HTTP status."""
    return {
        400: ("invalid_request", "Invalid request", False),
        401: ("invalid_token", "Invalid bearer token", False),
        403: ("permission_not_granted", "Permission not granted", False),
        404: ("resource_not_found", "Resource not found", False),
        405: ("method_not_allowed", "Method not allowed", False),
        409: ("conflict", "Request conflict", False),
        422: ("invalid_request", "Invalid request", False),
        429: ("rate_limit_exceeded", "Rate limit exceeded", True),
        503: ("service_unavailable", "Service unavailable", True),
    }.get(status_code, ("http_error", "Request failed", False))


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Add the canonical envelope while retaining FastAPI compatibility fields."""
    if isinstance(exc, StructuredHTTPException):
        code, message, retryable = exc.error_code, exc.error_message, exc.retryable
    else:
        code, message, retryable = _generic_http_error(exc.status_code)
    return error_response(
        request,
        status_code=exc.status_code,
        code=code,
        message=message,
        retryable=retryable,
        compatibility={"detail": exc.detail},
        headers=exc.headers,
    )


async def unhandled_exception_handler(request: Request, _exc: Exception) -> JSONResponse:
    """Return a constant private response for an unhandled application error."""
    return error_response(
        request,
        status_code=500,
        code="internal_error",
        message="Internal server error",
        compatibility={"detail": "Internal server error"},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the Workstream FastAPI application.

    Args:
        settings: Optional settings override for tests or embedded use.

    Returns:
        Configured FastAPI application.
    """
    settings = settings or get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=_application_lifespan,
        responses=DEFAULT_ERROR_RESPONSES,
    )
    app.state.settings = settings
    app.state.auth_verifier, app.state.auth_configuration_valid = prepare_auth_verifier(settings)
    cache_auth_verifier(settings, app.state.auth_verifier)
    app.add_exception_handler(
        RequestValidationError,
        request_validation_exception_handler,
    )
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(api_router)
    install_api_control_openapi(app)
    return app


app = create_app()
