"""Closed detached wire values; these fixtures establish no stored authority."""

from datetime import timedelta
import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.compensation.api.fulfillment_evidence import (
    FulfillmentExceptionAcknowledgement, FulfillmentRecordedException,
    FulfillmentRecordedReport, FulfillmentReportAcknowledgement, FulfillmentSourceEvidence,
)
from tests.finance.test_fulfillment_contracts import NOW, fixture, clock_step_back_evidence


def report_value(body, *, ordinal=1, received_at=NOW):
    return FulfillmentRecordedReport(
        acknowledgement=FulfillmentReportAcknowledgement(
            receipt_id=new_record_id(), award_id=UUID(body["award_id"]),
            fulfillment_root_id=UUID(body["fulfillment_root_id"]),
            external_event_id=UUID(body["external_event_id"]),
            report_digest=canonical_json_hash(body), replay=True,
        ), report_body=body, received_at=received_at, evidence_ordinal=ordinal,
        recording_lifecycle_generation=2,
    )


def source_value(state):
    latest = fulfilled = exception = None
    last_failure = None
    updated = NOW
    if state != "pending":
        body = fixture("report-points-fulfilled.json")
        if state == "clock_step_back":
            body, exception_body, original_time, exception_time = clock_step_back_evidence()
        else:
            exception_body = fixture("exception-after-fulfillment.json")
            original_time, exception_time = NOW, NOW + timedelta(seconds=1)
        latest = fulfilled = report_value(body, received_at=original_time)
        updated = original_time
        if state in {"exception", "clock_step_back"}:
            exception = FulfillmentRecordedException(
                acknowledgement=FulfillmentExceptionAcknowledgement(
                    exception_id=new_record_id(), award_id=fulfilled.acknowledgement.award_id,
                    fulfillment_root_id=fulfilled.acknowledgement.fulfillment_root_id,
                    original_fulfillment_event_id=fulfilled.acknowledgement.external_event_id,
                    exception_event_id=UUID(exception_body["exception_event_id"]),
                    exception_digest=canonical_json_hash(exception_body), replay=True,
                ), original_receipt_id=fulfilled.acknowledgement.receipt_id,
                exception_body=exception_body, received_at=exception_time,
                evidence_ordinal=2, recording_lifecycle_generation=3,
            )
            updated = exception_time
        if state == "late_failure":
            failed = fixture("report-failed.json") | {"external_event_id": str(new_record_id())}
            latest = report_value(failed, ordinal=2, received_at=NOW + timedelta(seconds=1))
            last_failure, updated = failed["failure_code"], latest.received_at
    obligation = fixture("obligation-points.json")
    return dict(
        contract_version=1, source_instance_id=UUID(obligation["source_instance_id"]),
        obligation=obligation, latest_receipt=latest, fulfilled_receipt=fulfilled,
        latest_exception=exception,
        fulfilled_external_event_id=fulfilled.acknowledgement.external_event_id if fulfilled else None,
        status=dict(delivery_status="acknowledged_by_adapter" if latest else "pending_delivery",
            fulfillment_status="fulfilled" if fulfilled else "pending",
            fulfillment_attention_required=exception is not None,
            latest_receipt_id=latest.acknowledgement.receipt_id if latest else None,
            latest_exception_id=exception.acknowledgement.exception_id if exception else None,
            last_failure_code=last_failure, updated_at=updated),
    )


@pytest.mark.parametrize("state", ("pending", "fulfilled", "late_failure", "exception", "clock_step_back"))
def test_closed_source_and_recorded_evidence_shapes(state):
    value = FulfillmentSourceEvidence(**source_value(state))
    wire = value.model_dump_json()
    assert FulfillmentSourceEvidence.model_validate_json(wire) == value
    decoded = json.loads(wire)
    assert set(decoded) == {"contract_version", "source_instance_id", "obligation", "status",
                            "fulfilled_external_event_id", "latest_receipt", "fulfilled_receipt", "latest_exception"}
    assert decoded["status"]["updated_at"].endswith(".000000Z")
    if state == "clock_step_back":
        assert value.latest_exception.received_at < value.fulfilled_receipt.received_at
        assert value.status.fulfillment_status == "fulfilled"
        assert value.status.fulfillment_attention_required is True


@pytest.mark.parametrize("change", (
    "source", "digest", "parent", "attention", "fulfillment", "latest_id", "ordinal", "update_time", "delivery", "two_successes",
))
def test_source_rejects_crossed_digest_parent_and_status(change):
    data = json.loads(FulfillmentSourceEvidence(**source_value("exception")).model_dump_json())
    if change == "source":
        data["source_instance_id"] = str(new_record_id())
    elif change == "digest":
        data["fulfilled_receipt"]["acknowledgement"]["report_digest"] = "sha256:" + "e" * 64
    elif change == "parent":
        data["latest_exception"]["original_receipt_id"] = str(new_record_id())
    elif change == "attention":
        data["status"]["fulfillment_attention_required"] = False
    elif change == "fulfillment":
        data["status"]["fulfillment_status"] = "failed"
    elif change == "latest_id":
        data["status"]["latest_receipt_id"] = str(new_record_id())
    elif change == "ordinal":
        data["latest_exception"]["evidence_ordinal"] = data["latest_receipt"]["evidence_ordinal"]
    elif change == "delivery":
        data["status"]["delivery_status"] = "pending_delivery"
    elif change == "update_time":
        data["status"]["updated_at"] = "2026-11-12T05:03:02.000000Z"
    else:
        latest = data["latest_receipt"]
        latest["acknowledgement"]["receipt_id"] = str(new_record_id())
        latest["acknowledgement"]["external_event_id"] = str(new_record_id())
        latest["report_body"]["external_event_id"] = latest["acknowledgement"]["external_event_id"]
        latest["acknowledgement"]["report_digest"] = canonical_json_hash(latest["report_body"])
        latest["evidence_ordinal"] = 3
        data["status"]["latest_receipt_id"] = latest["acknowledgement"]["receipt_id"]
        data["status"]["updated_at"] = latest["received_at"]
    with pytest.raises(ValidationError):
        FulfillmentSourceEvidence.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("version", (True, 1.0, "1", 2))
def test_source_contract_version_is_exact_integer(version):
    value = source_value("pending") | {"contract_version": version}
    with pytest.raises(ValidationError):
        FulfillmentSourceEvidence(**value)


def test_source_rejects_omitted_nullable_and_provider_data():
    data = json.loads(FulfillmentSourceEvidence(**source_value("pending")).model_dump_json())
    del data["latest_exception"]
    with pytest.raises(ValidationError):
        FulfillmentSourceEvidence.model_validate_json(json.dumps(data))
    data["latest_exception"] = None
    data["obligation"]["provider_payload"] = "forbidden"
    with pytest.raises(ValidationError):
        FulfillmentSourceEvidence.model_validate_json(json.dumps(data))


def test_recorded_times_serialize_as_canonical_utc():
    value = FulfillmentSourceEvidence(**source_value("fulfilled"))
    data = json.loads(value.model_dump_json())
    assert data["latest_receipt"]["received_at"] == "2026-11-12T05:03:00.000000Z"
    data["latest_receipt"]["received_at"] = "2026-11-12T05:03:00Z"
    with pytest.raises(ValidationError):
        FulfillmentSourceEvidence.model_validate_json(json.dumps(data))
