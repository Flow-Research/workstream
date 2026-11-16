"""Real flushed evidence must survive only with its exact committed authority."""

from uuid import UUID

from sqlalchemy import text

from app.api.deps.compensation_fulfillment import FulfillmentEvidenceRequest
from app.core.identifiers import new_record_id
from app.modules.compensation.api.fulfillment_evidence import (
    FulfillmentExceptionAcknowledgement, FulfillmentReportAcknowledgement,
)
from tests.finance.test_fulfillment_evidence_public_api import evidence_rows, report_for


async def test_response_failure_rolls_back_flushed_evidence_and_allow(fulfillment_api_source, monkeypatch):
    source = fulfillment_api_source
    prefix = f"/api/v1/compensation/awards/{source.obligation['award_id']}"
    fulfilled = report_for(source.obligation)
    accepted = await source.client.post(prefix + "/fulfillment-reports", json=fulfilled,
        headers=source.headers | {"Idempotency-Key": fulfilled["external_event_id"]})
    assert accepted.status_code == 201, accepted.text
    original_finish = FulfillmentEvidenceRequest.finish
    for family, model, table in (
        ("report", FulfillmentReportAcknowledgement, "compensation_fulfillment_receipts"),
        ("exception", FulfillmentExceptionAcknowledgement, "compensation_fulfillment_exceptions"),
    ):
        for failure in ("serialization", "detached_validation", "award", "event", "root", "digest"):
            before = await evidence_rows(source)
            body = report_for(source.obligation)
            if family == "report":
                body.update(reported_status="failed", fulfilled_quantity=None, fulfilled_at=None,
                            external_reference=None, failure_code="PROVIDER_UNAVAILABLE")
                event_key, suffix = "external_event_id", "/fulfillment-reports"
            else:
                body = {key: body[key] for key in (
                    "source_instance_id", "fulfillment_root_id", "award_id", "project_id",
                    "adapter_binding_id", "correlation_id", "contract_version", "route_key",
                )} | {"exception_event_id": str(new_record_id()),
                    "original_fulfillment_event_id": fulfilled["external_event_id"],
                    "kind": "provider_status_conflict", "observed_at": fulfilled["reported_at"],
                    "reported_at": fulfilled["reported_at"]}
                event_key, suffix = "exception_event_id", "/fulfillment-exceptions"
            flushed = []

            async def failing_finish(owner, value, response_model, **kwargs):
                row_id = value.receipt_id if family == "report" else value.exception_id
                row = (await owner.session.execute(text(
                    f"SELECT authorization_decision_id FROM public.{table} WHERE id=:id"
                ), {"id": row_id})).one()
                assert await owner.session.scalar(text(
                    "SELECT count(*) FROM public.audit_events WHERE id=:id "
                    "AND event_type='SensitiveAuthorizationAllowed'"
                ), {"id": row.authorization_decision_id}) == 1
                flushed.append(row_id)
                with monkeypatch.context() as patch:
                    if failure in {"serialization", "detached_validation"}:
                        def fail(*args, **kwargs):
                            raise ValueError("controlled precommit response failure")
                        method = "model_dump_json" if failure == "serialization" else "model_validate_json"
                        patch.setattr(model, method, fail)
                    else:
                        field = {"award": "award_id", "event": event_key,
                                 "root": "fulfillment_root_id",
                                 "digest": "report_digest" if family == "report" else "exception_digest"}[failure]
                        value = value.model_copy(update={field: "sha256:" + "0" * 64
                            if failure == "digest" else new_record_id()})
                    return await original_finish(owner, value, response_model, **kwargs)

            with monkeypatch.context() as patch:
                patch.setattr(FulfillmentEvidenceRequest, "finish", failing_finish)
                response = await source.client.post(prefix + suffix, json=body,
                    headers=source.headers | {"Idempotency-Key": body[event_key]})
            assert len(flushed) == 1, (family, failure, response.text)
            assert response.status_code == (500 if failure in {"serialization", "detached_validation"} else 503)
            assert await evidence_rows(source) == before, (family, failure)


async def test_lookup_miss_commits_only_source_read_allow(fulfillment_api_source):
    source = fulfillment_api_source
    prefix = f"/api/v1/compensation/awards/{source.obligation['award_id']}"
    event = new_record_id()
    response = await source.client.get(prefix + f"/fulfillment-reports/{event}", headers=source.headers)
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "fulfillment_evidence_not_found"
    receipts, exceptions, decisions = await evidence_rows(source)
    assert receipts == [] and exceptions == [] and len(decisions) == 1
    decision = decisions[0]
    assert decision["event_type"] == "SensitiveAuthorizationAllowed"
    assert decision["action_id"] == "compensation.fulfillment.source.read"
    assert decision["resource_type"] == "compensation_fulfillment_report_lookup"
    assert UUID(decision["resource_id"]) == event
    assert decision["project_id"] == source.obligation["project_id"]
    assert decision["after_facts"]["resource_context_digest"].startswith("sha256:")
