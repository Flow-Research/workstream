"""Signed public evidence operations against PostgreSQL and canonical AUTH."""

from datetime import UTC, datetime
import json

from sqlalchemy import text

from app.api.deps.compensation_fulfillment import FulfillmentEvidenceRequest
from app.core.identifiers import new_record_id
from app.modules.compensation.fulfillment.evidence_service import FulfillmentEvidenceService
from app.modules.actors.api import ServiceIdentity
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
    assert changed.json()["error"]["code"] == "FULFILLMENT_REPORT_CONFLICT"
    second = report_for(source.obligation)
    second_success = await source.client.post(prefix + "/fulfillment-reports", json=second,
        headers=source.headers | {"Idempotency-Key": second["external_event_id"]})
    assert second_success.status_code == 409, second_success.text
    assert second_success.json()["error"]["code"] == "FULFILLMENT_REPORT_CONFLICT"
    changed_exception = await source.client.post(prefix + "/fulfillment-exceptions",
        headers=exception_headers, json=exception | {"kind": "provider_status_conflict"})
    assert changed_exception.status_code == 409, changed_exception.text
    assert changed_exception.json()["error"]["code"] == "FULFILLMENT_EXCEPTION_CONFLICT"
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
    assert response.status_code == 404, response.text
    async with source.factory() as session:
        after = (await session.execute(text("SELECT (SELECT count(*) FROM actor_profiles), "
            "(SELECT count(*) FROM actor_identity_links)"))).one()
    assert after == before
    assert await evidence_rows(source) == ([], [], [])


async def test_service_and_missing_resource_refusals_are_concealed(fulfillment_api_source):
    source = fulfillment_api_source
    prefix = f"/api/v1/compensation/awards/{source.obligation['award_id']}"
    report = report_for(source.obligation)
    async with source.factory() as session:
        before = (await session.execute(text("SELECT (SELECT count(*) FROM actor_profiles), "
            "(SELECT count(*) FROM actor_identity_links)"))).one()
    subject = f"unprovisioned-service-{new_record_id()}"
    token = issue_asymmetric_token(source.access.signed.private_key, subject_kind="service",
        scope="workstream:service", claims={"sub": subject, "jti": str(new_record_id())})
    for method, suffix in (("GET", "/finance-evidence"), ("POST", "/fulfillment-reports")):
        response = await source.client.request(method, prefix + suffix, json=report,
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": report["external_event_id"]})
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "fulfillment_evidence_not_found"
    async with source.factory() as session:
        assert (await session.execute(text("SELECT (SELECT count(*) FROM actor_profiles), "
            "(SELECT count(*) FROM actor_identity_links)"))).one() == before
    provisioned = await source.client.post("/api/v1/service-actors",
        headers=source.access.admin.headers | {"Idempotency-Key": str(new_record_id())},
        json={"service_identity": ServiceIdentity.REVIEW_PROJECTION.value, "subject": subject,
              "reason": "Prove fulfillment rejects another provisioned service"})
    assert provisioned.status_code == 201, provisioned.text
    wrong_headers = {"Authorization": f"Bearer {token}"}
    for headers, award in ((wrong_headers, source.obligation["award_id"]),
                           (source.headers, str(new_record_id()))):
        body = report | {"award_id": award}
        base = f"/api/v1/compensation/awards/{award}"
        denied = await source.client.post(base + "/fulfillment-reports", json=body,
            headers=headers | {"Idempotency-Key": body["external_event_id"]})
        assert denied.status_code == 404, denied.text
        for suffix in ("/finance-evidence", "/fulfillment-reports/" + report["external_event_id"]):
            denied = await source.client.get(base + suffix, headers=headers)
            assert denied.status_code == 404, denied.text
    for authorization in ({}, {"Authorization": "Bearer invalid-credentials"}):
        rejected = await source.client.post(prefix + "/fulfillment-reports", json=report,
            headers=authorization | {"Idempotency-Key": report["external_event_id"]})
        assert rejected.status_code == 401, rejected.text
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
    award = source.obligation["award_id"]
    event = report["external_event_id"]
    exception_body = {key: report[key] for key in (
        "source_instance_id", "fulfillment_root_id", "award_id", "project_id",
        "adapter_binding_id", "correlation_id", "contract_version", "route_key",
    )} | {"exception_event_id": str(new_record_id()), "original_fulfillment_event_id": event,
        "kind": "provider_reversal", "observed_at": report["reported_at"],
        "reported_at": report["reported_at"]}
    for alternate_award in (award.upper(), award.replace("-", ""), "{" + award + "}"):
        for suffix, method in (("/finance-evidence", "GET"), ("/fulfillment-reports", "POST"),
                               ("/fulfillment-exceptions", "POST")):
            payload = exception_body if suffix == "/fulfillment-exceptions" else report
            key = exception_body["exception_event_id"] if suffix == "/fulfillment-exceptions" else event
            response = await source.client.request(method,
                f"/api/v1/compensation/awards/{alternate_award}" + suffix,
                headers=source.headers | {"Idempotency-Key": key},
                json=payload if method == "POST" else None)
            assert response.status_code == 422, response.text
    for alternate_event in (event.upper(), event.replace("-", ""), "{" + event + "}"):
        response = await source.client.get(prefix + "/fulfillment-reports/" + alternate_event,
                                           headers=source.headers)
        assert response.status_code == 422, response.text
    assert await evidence_rows(source) == ([], [], [])
