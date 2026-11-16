"""Signed public evidence operations against PostgreSQL and canonical AUTH."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.api.deps.compensation_fulfillment import FulfillmentEvidenceRequest
from app.core.identifiers import new_record_id


def report_for(obligation):
    now = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    value = {key: obligation[key] for key in (
        "source_instance_id", "fulfillment_root_id", "award_id", "project_id",
        "adapter_binding_id", "correlation_id", "contract_version", "route_key",
        "instrument_type", "unit_code",
    )}
    return value | {"external_event_id": str(new_record_id()), "reported_status": "fulfilled",
        "fulfilled_quantity": obligation["quantity"], "fulfilled_at": now,
        "external_reference": f"fin_{new_record_id().hex}", "failure_code": None,
        "reported_at": now}


async def evidence_rows(source):
    async with source.factory() as session:
        return (await session.execute(text("""SELECT
            (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY evidence_ordinal), '[]'::jsonb)
                FROM public.compensation_fulfillment_receipts r),
            (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY evidence_ordinal), '[]'::jsonb)
                FROM public.compensation_fulfillment_exceptions r),
            (SELECT coalesce(jsonb_agg(to_jsonb(a) ORDER BY id), '[]'::jsonb)
                FROM public.audit_events a WHERE action_id LIKE 'compensation.fulfillment.%')
        """))).one()


async def test_signed_source_report_exception_and_response_loss_journey(fulfillment_api_source, monkeypatch):
    source = fulfillment_api_source
    prefix = f"/api/v1/compensation/awards/{source.obligation['award_id']}"
    pending = await source.client.get(prefix + "/finance-evidence", headers=source.headers)
    assert pending.status_code == 200, pending.text
    assert pending.json()["obligation"] == source.obligation
    assert pending.json()["status"]["fulfillment_status"] == "pending"
    report = report_for(source.obligation)
    headers = source.headers | {"Idempotency-Key": report["external_event_id"]}
    original_finish = FulfillmentEvidenceRequest.finish

    async def lose_response(owner, *args, **kwargs):
        await original_finish(owner, *args, **kwargs)
        raise RuntimeError("controlled response loss after commit")

    with monkeypatch.context() as patch:
        patch.setattr(FulfillmentEvidenceRequest, "finish", lose_response)
        with pytest.raises(RuntimeError, match="controlled response loss after commit"):
            await source.client.post(prefix + "/fulfillment-reports", headers=headers, json=report)
    before_replay = await evidence_rows(source)
    assert len(before_replay[0]) == 1 and before_replay[1] == []
    replay = await source.client.post(prefix + "/fulfillment-reports", headers=headers, json=report)
    assert replay.status_code == 200, replay.text
    assert replay.json()["replay"] is True
    assert await evidence_rows(source) == before_replay
    lookup = await source.client.get(prefix + "/fulfillment-reports/" + report["external_event_id"],
                                     headers=source.headers)
    assert lookup.status_code == 200, lookup.text
    assert lookup.json()["acknowledgement"] == replay.json()
    assert lookup.json()["report_body"] == report
    exception = {key: report[key] for key in (
        "source_instance_id", "fulfillment_root_id", "award_id", "project_id",
        "adapter_binding_id", "correlation_id", "contract_version", "route_key",
    )} | {"original_fulfillment_event_id": report["external_event_id"],
        "exception_event_id": str(new_record_id()), "kind": "provider_reversal",
        "observed_at": report["reported_at"], "reported_at": report["reported_at"]}
    exception_headers = source.headers | {"Idempotency-Key": exception["exception_event_id"]}
    incident = await source.client.post(prefix + "/fulfillment-exceptions",
        headers=exception_headers, json=exception)
    assert incident.status_code == 201, incident.text
    before_exception_replay = await evidence_rows(source)
    incident_replay = await source.client.post(prefix + "/fulfillment-exceptions",
        headers=exception_headers, json=exception)
    assert incident_replay.status_code == 200, incident_replay.text
    assert incident_replay.json() == incident.json() | {"replay": True}
    assert await evidence_rows(source) == before_exception_replay
    observed = await source.client.get(prefix + "/finance-evidence", headers=source.headers)
    assert observed.status_code == 200, observed.text
    assert observed.json()["status"]["fulfillment_status"] == "fulfilled"
    assert observed.json()["status"]["fulfillment_attention_required"] is True
    assert observed.json()["fulfilled_receipt"] == lookup.json()
    assert observed.json()["latest_exception"]["acknowledgement"] == incident_replay.json()
    changed = await source.client.post(prefix + "/fulfillment-reports", headers=headers,
        json=report | {"external_reference": f"fin_{new_record_id().hex}"})
    assert changed.status_code == 409, changed.text
    receipts, exceptions, decisions = await evidence_rows(source)
    assert [r["evidence_ordinal"] for r in receipts + exceptions] == [1, 2]
    for row in receipts + exceptions:
        decision = next(d for d in decisions if d["id"] == row["authorization_decision_id"])
        assert decision["event_type"] == "SensitiveAuthorizationAllowed"
        assert decision["after_facts"]["resource_context_digest"] == row["authorization_resource_digest"]
        assert decision["actor_id"] == row["reporter_actor_id"]
    assert sum(d["action_id"] == "compensation.fulfillment.report" for d in decisions) == 1
    assert sum(d["action_id"] == "compensation.fulfillment.exception.report" for d in decisions) == 1
