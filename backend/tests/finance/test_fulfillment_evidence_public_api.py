"""Signed public evidence operations against PostgreSQL and canonical AUTH."""

from datetime import UTC, datetime
import json

from sqlalchemy import text

from app.api.deps.compensation_fulfillment import FulfillmentEvidenceRequest
from app.core.identifiers import new_record_id
from app.modules.compensation.fulfillment.evidence_service import FulfillmentEvidenceService
from tests.authentication.support import issue_asymmetric_token


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
    committed = []

    async def lose_response(owner, *args, **kwargs):
        await original_finish(owner, *args, **kwargs)
        committed.append(True)
        raise RuntimeError("controlled response loss after commit")

    with monkeypatch.context() as patch:
        patch.setattr(FulfillmentEvidenceRequest, "finish", lose_response)
        lost = await source.client.post(prefix + "/fulfillment-reports", headers=headers, json=report)
        assert committed == [True], lost.text
        # The actual request-control middleware turns an unstarted response
        # failure into500. It cannot undo the already committed evidence pair.
        assert lost.status_code == 500, lost.text
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


async def test_human_rejected_before_actor_provisioning(fulfillment_api_source):
    source = fulfillment_api_source
    async with source.factory() as session:
        before = (await session.execute(text("SELECT (SELECT count(*) FROM actor_profiles), "
            "(SELECT count(*) FROM actor_identity_links)"))).one()
    token = issue_asymmetric_token(source.access.signed.private_key,
        claims={"sub": f"unregistered-human-{new_record_id()}", "jti": str(new_record_id())})
    response = await source.client.get(
        f"/api/v1/compensation/awards/{source.obligation['award_id']}/finance-evidence",
        headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403, response.text
    async with source.factory() as session:
        after = (await session.execute(text("SELECT (SELECT count(*) FROM actor_profiles), "
            "(SELECT count(*) FROM actor_identity_links)"))).one()
    assert after == before
    assert await evidence_rows(source) == ([], [], [])


async def test_streamed_budget_and_identity_rejection_before_locator_or_auth(fulfillment_api_source, monkeypatch):
    source = fulfillment_api_source
    report = report_for(source.obligation)
    prefix = f"/api/v1/compensation/awards/{source.obligation['award_id']}"

    async def forbidden(*args, **kwargs):
        raise AssertionError("invalid wire reached the source locator")

    monkeypatch.setattr(FulfillmentEvidenceService, "_locate", forbidden)
    headers = source.headers | {"Idempotency-Key": report["external_event_id"]}
    for key_headers, body, award, expected in (
        (headers, b"x" * 65_537, source.obligation["award_id"], 413),
        (headers, b'{"award_id":"duplicate","award_id":"duplicate"}', source.obligation["award_id"], 422),
        (source.headers, json.dumps(report).encode(), source.obligation["award_id"], 422),
        (headers | {"Idempotency-Key": str(new_record_id())}, json.dumps(report).encode(), source.obligation["award_id"], 422),
        (headers, json.dumps(report).encode(), str(new_record_id()), 422),
    ):
        response = await source.client.post(f"/api/v1/compensation/awards/{award}/fulfillment-reports",
            content=body, headers=key_headers)
        assert response.status_code == expected, response.text
    duplicate = list(headers.items()) + [("Idempotency-Key", report["external_event_id"])]
    response = await source.client.post(prefix + "/fulfillment-reports", json=report, headers=duplicate)
    assert response.status_code == 422, response.text
    for length_header in ({}, {"Content-Length": "1"}):
        async def chunks():
            yield b"x" * 32_768
            yield b"x" * 32_769
        response = await source.client.post(prefix + "/fulfillment-reports", content=chunks(),
            headers=headers | length_header)
        assert response.status_code == 413, response.text
    assert await evidence_rows(source) == ([], [], [])
