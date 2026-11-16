"""Original-bound service evidence; no payment execution or earning mutations."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BeforeValidator, UUID7

from app.api.deps.compensation_fulfillment import (
    FulfillmentEvidenceRequest, fulfillment_body, fulfillment_http_error,
    get_fulfillment_request, require_fulfillment_key,
    canonical_fulfillment_uuid,
)
from app.core.api_controls import ApiErrorResponse, error_payload
from app.modules.compensation.api.fulfillment_contracts import (
    parse_fulfillment_exception, parse_fulfillment_report,
)
from app.modules.compensation.api.fulfillment_evidence import (
    FulfillmentExceptionAcknowledgement, FulfillmentRecordedReport,
    FulfillmentReportAcknowledgement, FulfillmentSourceEvidence,
)
from app.modules.finance.api.contract_schema import (
    fulfillment_exception_schema, fulfillment_report_schema,
)

router = APIRouter(prefix="/compensation/awards/{award_id}", tags=["compensation-fulfillment"],
    responses={code: {"model": ApiErrorResponse} for code in (401, 404, 409, 413, 422, 503)})
Owner = Annotated[FulfillmentEvidenceRequest, Depends(get_fulfillment_request)]
EventKey = Annotated[UUID, Depends(require_fulfillment_key)]
FulfillmentPathId = Annotated[UUID7, BeforeValidator(canonical_fulfillment_uuid)]
_KEY_PARAMETER = {"name": "Idempotency-Key", "in": "header", "required": True,
                  "schema": {"type": "string", "format": "uuid", "description": "Canonical UUIDv7 event ID"}}


@router.post("/fulfillment-reports", response_model=FulfillmentReportAcknowledgement,
    status_code=201, responses={200: {"model": FulfillmentReportAcknowledgement}},
    dependencies=[Depends(require_fulfillment_key)],
    openapi_extra={"x-workstream-action-id": "compensation.fulfillment.report",
        "parameters": [_KEY_PARAMETER], "requestBody": {"required": True,
            "description": "Closed JSON report; actual streamed body must be at most 65536 bytes.",
            "content": {"application/json": {"schema": fulfillment_report_schema()}}}})
async def report(award_id: FulfillmentPathId, key: EventKey, request: Request, owner: Owner):
    body = await fulfillment_body(request)
    try:
        value = parse_fulfillment_report(body)
    except ValueError as exc:
        raise fulfillment_http_error(422) from exc
    result = await owner.service.report(award_id, key, body)
    return await owner.finish(result, FulfillmentReportAcknowledgement, award_id=award_id,
        event_id=key, request_body=value, status_code=200 if result.replay else 201)


@router.get("/fulfillment-reports/{external_event_id}", response_model=FulfillmentRecordedReport,
    openapi_extra={"x-workstream-action-id": "compensation.fulfillment.source.read"})
async def lookup(award_id: FulfillmentPathId, external_event_id: FulfillmentPathId, request: Request, owner: Owner):
    result = await owner.service.lookup(award_id, external_event_id)
    if result is None:
        return await owner.finish(ApiErrorResponse.model_validate(error_payload(request,
            code="fulfillment_evidence_not_found", message="Fulfillment evidence not found")),
            ApiErrorResponse, award_id=award_id, event_id=external_event_id, status_code=404)
    return await owner.finish(result, FulfillmentRecordedReport, award_id=award_id,
                              event_id=external_event_id)


@router.get("/finance-evidence", response_model=FulfillmentSourceEvidence,
    openapi_extra={"x-workstream-action-id": "compensation.fulfillment.source.read"})
async def source_evidence(award_id: FulfillmentPathId, owner: Owner):
    result = await owner.service.source_evidence(award_id)
    return await owner.finish(result, FulfillmentSourceEvidence, award_id=award_id)


@router.post("/fulfillment-exceptions", response_model=FulfillmentExceptionAcknowledgement,
    status_code=201, responses={200: {"model": FulfillmentExceptionAcknowledgement}},
    dependencies=[Depends(require_fulfillment_key)],
    openapi_extra={"x-workstream-action-id": "compensation.fulfillment.exception.report",
        "parameters": [_KEY_PARAMETER], "requestBody": {"required": True,
            "description": "Closed JSON exception; actual streamed body must be at most 65536 bytes.",
            "content": {"application/json": {"schema": fulfillment_exception_schema()}}}})
async def exception(award_id: FulfillmentPathId, key: EventKey, request: Request, owner: Owner):
    body = await fulfillment_body(request)
    try:
        value = parse_fulfillment_exception(body)
    except ValueError as exc:
        raise fulfillment_http_error(422) from exc
    result = await owner.service.exception(award_id, key, body)
    return await owner.finish(result, FulfillmentExceptionAcknowledgement, award_id=award_id,
        event_id=key, request_body=value, status_code=200 if result.replay else 201)
