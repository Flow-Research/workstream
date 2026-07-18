"""Shared FastAPI rate-control dependency and error mapping."""

from fastapi import Request, status

from app.core.api_controls import StructuredHTTPException
from app.modules.api_controls.service import (
    RateControlService,
    RateControlUnavailableError,
)
from app.schemas.auth import AuthVerificationResult


def get_rate_control_service() -> RateControlService:
    """Return a limiter whose consumption owns a dedicated database session."""
    return RateControlService()


def service_unavailable_error(detail: str = "Service unavailable") -> StructuredHTTPException:
    """Build the canonical retryable service-unavailable response."""
    return StructuredHTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=detail,
        error_code="service_unavailable",
        error_message="Service unavailable",
        retryable=True,
    )


async def enforce_rate_control(
    *,
    request: Request,
    result: AuthVerificationResult,
    service: RateControlService,
    control_scope: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Consume one configured allowance and map bounded HTTP failures."""
    try:
        decision = await service.consume(
            control_scope=control_scope,
            issuer=result.token.issuer,
            subject=result.token.subject,
            limit=limit,
            window_seconds=window_seconds,
            secret=request.app.state.settings.api_rate_limit_key_secret,
        )
    except RateControlUnavailableError as exc:
        raise service_unavailable_error() from exc
    if not decision.allowed:
        raise StructuredHTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            error_code="rate_limit_exceeded",
            error_message="Rate limit exceeded",
            retryable=True,
            headers={"Retry-After": str(decision.retry_after)},
        )
