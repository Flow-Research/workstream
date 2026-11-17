"""Installed SQL body checks independently enforce closed source and time bounds.

These invoke pure native validators with explicit evidence times. They do not
insert a receipt, override the insertion clock or claim authorization custody.
"""

import json

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.db.session import get_session_factory
from tests.finance.test_fulfillment_contracts import NOW, fixture, clock_step_back_evidence


@pytest.mark.parametrize("change,valid", [
    ({}, True),
    ({"reported_at": "2026-11-12T05:08:00.000000Z"}, True),
    ({"reported_at": "2026-11-12T05:08:00.000001Z"}, False),
    ({"reported_at": "2026-11-12T04:55:00.000000Z", "fulfilled_at": "2026-11-12T04:55:00.000000Z"}, True),
    ({"fulfilled_at": "2026-11-12T04:54:59.999999Z"}, False),
    ({"reported_at": "2026-11-12T05:01:01Z"}, False),
    ({"fulfilled_quantity": "2000.010"}, False),
    ({"fulfilled_quantity": "2000.00"}, False),
    ({"contract_version": 1.0}, False),
    ({"contract_version": True}, False),
    ({"adapter_binding_id": "019a78b0-0000-7000-8000-000000000099"}, False),
    ({"external_reference": "https://provider.example/transfer"}, False),
    ({"provider_payload": {}}, False),
])
async def test_native_report_body_requires_exact_source_quantity_and_closed_skew(
    isolated_database_env, change, valid,
):
    body = fixture("report-money-fulfilled.json") | change
    async with get_session_factory()() as session:
        observed = await session.scalar(text(
            "SELECT public.compensation_fulfillment_report_valid("
            "CAST(:body AS jsonb),CAST(:obligation AS jsonb),:received_at)"
        ), {"body": json.dumps(body), "obligation": json.dumps(fixture("obligation-money.json")),
            "received_at": NOW})
    assert observed is valid


@pytest.mark.parametrize("change,original_status,valid", [
    ({}, "fulfilled", True),
    ({"kind": "provider_status_conflict"}, "fulfilled", True),
    ({"observed_at": "2026-11-12T04:56:00.000000Z", "reported_at": "2026-11-12T04:56:00.000000Z"}, "fulfilled", True),
    ({"observed_at": "2026-11-12T04:55:59.999999Z"}, "fulfilled", False),
    ({"reported_at": "2026-11-12T05:08:00.000000Z"}, "fulfilled", True),
    ({"reported_at": "2026-11-12T05:08:00.000001Z"}, "fulfilled", False),
    ({"kind": "repayment"}, "fulfilled", False),
    ({"original_fulfillment_event_id": "019a78b0-0000-7000-8000-000000000099"}, "fulfilled", False),
    ({"project_id": "019a78b0-0000-7000-8000-000000000099"}, "fulfilled", False),
    ({"quantity": "1"}, "fulfilled", False),
    ({}, "failed", False),
])
async def test_native_exception_body_requires_original_success_and_exact_bounds(
    isolated_database_env, change, original_status, valid,
):
    original = fixture("report-money-fulfilled.json")
    retained = {"reported_status": original_status,
                "external_event_id": original["external_event_id"], "report_body": original}
    async with get_session_factory()() as session:
        observed = await session.scalar(text(
            "SELECT public.compensation_fulfillment_exception_valid("
            "CAST(:body AS jsonb),CAST(:obligation AS jsonb),"
            "jsonb_populate_record(NULL::public.compensation_fulfillment_receipts,"
            "CAST(:original AS jsonb)),:received_at)"
        ), {"body": json.dumps(fixture("exception-after-fulfillment.json") | change),
            "obligation": json.dumps(fixture("obligation-money.json")),
            "original": json.dumps(retained), "received_at": NOW})
    assert observed is valid


async def test_native_exception_keeps_valid_retained_success_after_clock_step_back(isolated_database_env):
    report, exception, original_received_at, exception_received_at = clock_step_back_evidence()
    obligation = fixture("obligation-points.json")
    original = {"reported_status": "fulfilled", "external_event_id": report["external_event_id"],
                "report_body": report, "received_at": original_received_at.isoformat()}
    engine = create_async_engine(isolated_database_env, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text(
                "SELECT public.compensation_fulfillment_report_valid("
                "CAST(:body AS jsonb),CAST(:obligation AS jsonb),:received_at)"
            ), {"body": json.dumps(report), "obligation": json.dumps(obligation),
                "received_at": original_received_at}) is True
            assert await connection.scalar(text(
                "SELECT public.compensation_fulfillment_exception_valid("
                "CAST(:body AS jsonb),CAST(:obligation AS jsonb),"
                "jsonb_populate_record(NULL::public.compensation_fulfillment_receipts,"
                "CAST(:original AS jsonb)),:received_at)"
            ), {"body": json.dumps(exception), "obligation": json.dumps(obligation),
                "original": json.dumps(original), "received_at": exception_received_at}) is True
    finally:
        await engine.dispose()
