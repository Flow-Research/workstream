"""Request-local fulfillment composition and validation-before-commit responses."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request, Response
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth import fulfillment_evidence_authorization
from app.adapters.compensation import fulfillment_evidence_service
from app.adapters.reviews import fulfillment_current_custody
from app.api.deps.auth import get_auth_verification_result
from app.api.deps.authorization import _authorization_context, resolve_authorization_actor
from app.api.deps.rate_controls import get_rate_control_service
from app.core.api_controls import ApiErrorResponse, StructuredHTTPException, request_ids
from app.core.hashing import canonical_json_hash
from app.core.financial_wire import require_canonical_uuid
from app.db.session import get_db_session
from app.modules.compensation.api.fulfillment_evidence import (
    FulfillmentEvidenceDenied, FulfillmentEvidenceInvalid, FulfillmentEvidenceUnavailable,
    FulfillmentExceptionAcknowledgement, FulfillmentExceptionConflict,
    FulfillmentRecordedReport, FulfillmentReportAcknowledgement, FulfillmentReportConflict,
    FulfillmentSourceEvidence,
)
from app.schemas.auth import AuthVerificationResult


def fulfillment_http_error(status: int) -> StructuredHTTPException:
    """Build the concealed or retryable fulfillment error for the HTTP boundary."""
    code = {404: "fulfillment_evidence_not_found", 413: "fulfillment_body_too_large",
            422: "invalid_fulfillment_evidence", 503: "fulfillment_evidence_unavailable"}[status]
    return StructuredHTTPException(status_code=status, detail=code, error_code=code,
        error_message=code.replace("_", " "), retryable=status == 503)


def canonical_fulfillment_uuid(value: str) -> str:
    """Use the financial wire owner before HTTP UUID coercion can normalize aliases."""
    require_canonical_uuid(value, version=7)
    return value


def require_fulfillment_key(request: Request) -> UUID:
    """Require one canonical UUIDv7 event header before owner operations."""
    values = request.headers.getlist("Idempotency-Key")
    try:
        value = values[0] if len(values) == 1 else ""
        return UUID(canonical_fulfillment_uuid(value))
    except ValueError as exc:
        raise fulfillment_http_error(422) from exc


async def fulfillment_body(request: Request) -> bytes:
    """Bound actual streamed bytes even when Content-Length is absent or false."""
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 65_536:
            raise fulfillment_http_error(413)
        body.extend(chunk)
    return bytes(body)


@dataclass(frozen=True)
class FulfillmentEvidenceRequest:
    """Own the request transaction and validate detached response bytes before commit."""
    session: AsyncSession
    service: object
    source_instance_id: UUID
    correlation_id: UUID

    async def finish(self, value, model: type[BaseModel], *, award_id: UUID,
                     event_id: UUID | None = None, request_body: dict | None = None,
                     status_code: int = 200) -> Response:
        """Construct detached validated bytes before committing the sole root."""
        checked = model.model_validate(value, strict=True)
        if isinstance(checked, FulfillmentSourceEvidence):
            if (checked.source_instance_id != self.source_instance_id
                    or checked.obligation["award_id"] != str(award_id)):
                raise FulfillmentEvidenceUnavailable("fulfillment response source differs")
        elif isinstance(checked, ApiErrorResponse):
            if (status_code != 404 or checked.error.code != "fulfillment_evidence_not_found"
                    or checked.error.correlation_id != str(self.correlation_id)):
                raise FulfillmentEvidenceUnavailable("fulfillment lookup error differs")
        else:
            ack = checked.acknowledgement if isinstance(checked, FulfillmentRecordedReport) else checked
            if isinstance(ack, (FulfillmentReportAcknowledgement, FulfillmentExceptionAcknowledgement)):
                actual_event = (ack.external_event_id if isinstance(ack, FulfillmentReportAcknowledgement)
                                else ack.exception_event_id)
                if ack.award_id != award_id or actual_event != event_id:
                    raise FulfillmentEvidenceUnavailable("fulfillment response identity differs")
                if request_body is not None:
                    actual_digest = (ack.report_digest if isinstance(ack, FulfillmentReportAcknowledgement)
                                     else ack.exception_digest)
                    if (actual_digest != canonical_json_hash(request_body)
                            or str(ack.fulfillment_root_id) != request_body["fulfillment_root_id"]):
                        raise FulfillmentEvidenceUnavailable("fulfillment response digest differs")
        payload = checked.model_dump_json(warnings="error")
        detached = model.model_validate_json(payload, strict=True)
        if detached != checked:
            raise FulfillmentEvidenceUnavailable("fulfillment response changed during serialization")
        response = Response(content=payload, status_code=status_code, media_type="application/json")
        await self.session.commit()
        return response


async def get_fulfillment_request(
    request: Request,
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    rate_control: Annotated[Any, Depends(get_rate_control_service)],
) -> AsyncIterator[FulfillmentEvidenceRequest]:
    """Reject humans before provisioning and keep actual service principal custody."""
    if result.token.subject_kind != "service":
        raise fulfillment_http_error(404)
    try:
        resolved = await resolve_authorization_actor(request, result, session, rate_control)
    except StructuredHTTPException as exc:
        if exc.status_code in {403, 404}:
            raise fulfillment_http_error(404) from exc
        raise
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    context = _authorization_context(resolved, request_id, correlation_id)
    await session.rollback()
    authority = fulfillment_evidence_authorization(session, context)
    source = request.app.state.settings.source_instance_id
    try:
        await session.begin()
        yield FulfillmentEvidenceRequest(session, fulfillment_evidence_service(
            session, context=context, authorization=authority,
            lifecycle=fulfillment_current_custody(session), source_instance_id=source,
        ), source, correlation_id)
    except FulfillmentEvidenceDenied as exc:
        await session.rollback()
        try:
            if await authority.restage_denial(exc):
                await session.commit()
        except (FulfillmentEvidenceUnavailable, SQLAlchemyError) as evidence_error:
            await session.rollback()
            raise fulfillment_http_error(503) from evidence_error
        raise fulfillment_http_error(404) from exc
    except (FulfillmentReportConflict, FulfillmentExceptionConflict) as exc:
        code = ("FULFILLMENT_REPORT_CONFLICT" if isinstance(exc, FulfillmentReportConflict)
                else "FULFILLMENT_EXCEPTION_CONFLICT")
        raise StructuredHTTPException(status_code=409, detail=code, error_code=code,
            error_message="Fulfillment evidence conflicts with the recorded event") from exc
    except FulfillmentEvidenceInvalid as exc:
        raise fulfillment_http_error(422) from exc
    except (FulfillmentEvidenceUnavailable, SQLAlchemyError,
            ValidationError) as exc:
        raise fulfillment_http_error(503) from exc
    finally:
        if session.in_transaction():
            await session.rollback()
