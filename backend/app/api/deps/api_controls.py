"""Unattached FastAPI dependencies for future protected mutations."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.api.deps.auth import get_auth_verification_result
from app.api.deps.rate_controls import enforce_rate_control, get_rate_control_service
from app.modules.api_controls.service import (
    ADMIN_MUTATION_SCOPE,
    FIRST_ACCESS_SCOPE,
    RateControlService,
)
from app.schemas.auth import AuthVerificationResult


async def enforce_first_access_rate_limit(
    request: Request,
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
    service: Annotated[RateControlService, Depends(get_rate_control_service)],
) -> None:
    """Consume the future first-access mutation allowance."""
    settings = request.app.state.settings
    await enforce_rate_control(
        request=request,
        result=result,
        service=service,
        control_scope=FIRST_ACCESS_SCOPE,
        limit=settings.api_first_access_rate_limit,
        window_seconds=settings.api_first_access_rate_window_seconds,
    )


async def enforce_admin_mutation_rate_limit(
    request: Request,
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
    service: Annotated[RateControlService, Depends(get_rate_control_service)],
) -> None:
    """Consume the future authority-management mutation allowance."""
    settings = request.app.state.settings
    await enforce_rate_control(
        request=request,
        result=result,
        service=service,
        control_scope=ADMIN_MUTATION_SCOPE,
        limit=settings.api_admin_mutation_rate_limit,
        window_seconds=settings.api_admin_mutation_rate_window_seconds,
    )
