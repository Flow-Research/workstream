"""FastAPI application factory for Workstream."""

from __future__ import annotations

import math
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import Settings, get_settings


def _json_safe_validation_value(value: Any) -> Any:
    """Return a JSON-serializable validation error value."""
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
        content={
            "detail": _json_safe_validation_value(exc.errors()),
        },
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
