"""Signed concurrent callbacks must use actual current database custody."""

import asyncio
from datetime import datetime

import pytest
from sqlalchemy import text

from app.modules.compensation.fulfillment.evidence_service import FulfillmentEvidenceService
from tests.finance.test_fulfillment_evidence_public_api import evidence_rows, report_for
from tests.reviews.lifecycle.test_fence import observe_advisory_wait


async def earning_facts(source):
    async with source.factory() as session:
        return (await session.execute(text("""SELECT
            (SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM contribution_records c),
            (SELECT jsonb_agg(to_jsonb(a) ORDER BY id) FROM compensation_awards a),
            (SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM compensation_fulfillment_roots r)
        """))).one()


@pytest.mark.parametrize("first_family", ("report", "exception"))
async def test_rc_late_failure_and_exception_serialize_ordinals(fulfillment_api_source, monkeypatch, first_family):
    source = fulfillment_api_source
    prefix = f"/api/v1/compensation/awards/{source.obligation['award_id']}"
    fulfilled = report_for(source.obligation)
    response = await source.client.post(prefix + "/fulfillment-reports", json=fulfilled,
        headers=source.headers | {"Idempotency-Key": fulfilled["external_event_id"]})
    assert response.status_code == 201, response.text
    before = await earning_facts(source)
    failure = report_for(source.obligation) | {
        "reported_status": "failed", "fulfilled_quantity": None, "fulfilled_at": None,
        "external_reference": None, "failure_code": "PROVIDER_TIMEOUT",
    }
    incident = {key: failure[key] for key in (
        "source_instance_id", "fulfillment_root_id", "award_id", "project_id",
        "adapter_binding_id", "correlation_id", "contract_version", "route_key",
    )} | {"exception_event_id": failure["external_event_id"],
        "original_fulfillment_event_id": fulfilled["external_event_id"],
        "kind": "provider_status_conflict", "observed_at": fulfilled["reported_at"],
        "reported_at": failure["reported_at"]}
    requests = {"report": ("/fulfillment-reports", failure, "external_event_id"),
                "exception": ("/fulfillment-exceptions", incident, "exception_event_id")}
    # Each table has its own binding/event identity; shared values still cannot
    # collapse two distinct evidence types or assign the same root ordinal.
    locked, release, located = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids, flushed = [], []
    original_locate = FulfillmentEvidenceService._locate
    original_flush = FulfillmentEvidenceService._flush_evidence

    async def locate(owner, award_id):
        result = await original_locate(owner, award_id)
        pids.append(await owner._session.scalar(text("SELECT pg_backend_pid()")))
        if len(pids) == 2:
            located.set()
        return result

    async def flush(owner):
        await original_flush(owner)
        flushed.append(await owner._session.scalar(text("SELECT pg_backend_pid()")))
        if len(flushed) == 1:
            locked.set()
            await release.wait()

    async def send(family):
        suffix, body, key = requests[family]
        return await source.client.post(prefix + suffix, json=body,
            headers=source.headers | {"Idempotency-Key": body[key]})

    pending = []
    with monkeypatch.context() as patch:
        patch.setattr(FulfillmentEvidenceService, "_locate", locate)
        patch.setattr(FulfillmentEvidenceService, "_flush_evidence", flush)
        try:
            pending.append(asyncio.create_task(send(first_family)))
            await asyncio.wait_for(locked.wait(), 30)
            second = "exception" if first_family == "report" else "report"
            pending.append(asyncio.create_task(send(second)))
            await asyncio.wait_for(located.wait(), 30)
            assert pids[0] != pids[1]
            await observe_advisory_wait(source.factory, pids[1], pending[1])
            async with source.factory() as observer:
                before_release = await observer.scalar(text("SELECT clock_timestamp()"))
            release.set()
            results = await asyncio.wait_for(asyncio.gather(*pending), 30)
        finally:
            release.set()
            for running in pending:
                if not running.done():
                    running.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
    assert all(r.status_code == 201 for r in results), [r.text for r in results]
    receipts, exceptions, _ = await evidence_rows(source)
    assert len(receipts) == 2 and len(exceptions) == 1
    failed, exception = receipts[1], exceptions[0]
    assert [receipts[0]["evidence_ordinal"], *sorted((failed["evidence_ordinal"], exception["evidence_ordinal"]))] == [1, 2, 3]
    first, last = (failed, exception) if first_family == "report" else (exception, failed)
    assert (first["evidence_ordinal"], last["evidence_ordinal"]) == (2, 3)
    assert datetime.fromisoformat(last["received_at"]) >= before_release
    observed = await source.client.get(prefix + "/finance-evidence", headers=source.headers)
    assert observed.status_code == 200, observed.text
    status = observed.json()["status"]
    assert status["fulfillment_status"] == "fulfilled" and status["fulfillment_attention_required"] is True
    assert status["latest_receipt_id"] == failed["id"]
    assert status["latest_exception_id"] == exception["id"]
    assert status["last_failure_code"] == "PROVIDER_TIMEOUT"
    assert datetime.fromisoformat(status["updated_at"]) == datetime.fromisoformat(last["received_at"])
    before_replay = await evidence_rows(source)
    for family in ("report", "exception"):
        replay = await send(family)
        assert replay.status_code == 200 and replay.json()["replay"] is True, replay.text
    assert await evidence_rows(source) == before_replay
    assert await earning_facts(source) == before
