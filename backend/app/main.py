"""FastAPI application factory for Workstream."""

from __future__ import annotations

import math
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import Settings, get_settings


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
                safe_context[key] = item.__class__.__name__ if isinstance(item, BaseException) else "redacted"
                continue
            safe_context[key] = _json_safe_validation_value(item)
        return safe_context
    return _json_safe_validation_value(value)


def _json_safe_validation_value(value: Any) -> Any:
    """Return a JSON-serializable non-sensitive validation error value."""
    if isinstance(value, float) and not math.isfinite(value):
        return "non_finite_number"
    if isinstance(value, dict):
        return {
            key: _json_safe_validation_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_json_safe_validation_value(item) for item in value]
    if isinstance(value, BaseException):
        return value.__class__.__name__
    return value


async def request_validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return validation errors without echoing non-finite JSON values."""
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({
            "detail": [
                _validation_error_detail(error)
                for error in exc.errors()
            ],
        }),
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
    )
    app.add_exception_handler(
        RequestValidationError,
        request_validation_exception_handler,
    )
    app.include_router(api_router)
    return app


app = create_app()
