"""Both owners reject reports that change an award or misrepresent its outcome."""

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from app.modules.compensation.api import fulfillment_contracts as compensation
from app.modules.finance.api import fulfillment_contracts as finance

FIXTURES = Path(__file__).parents[2] / "app/modules/finance/contracts/fixtures"
NOW = datetime(2026, 11, 12, 5, 3, tzinfo=UTC)


@pytest.fixture(params=[compensation, finance], ids=["compensation", "finance"])
def owner(request):
    return request.param


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def encode(value):
    return json.dumps(value).encode()


def obligation(owner, *, money=False):
    name = "obligation-money-v2.json" if money else "obligation-points-v2.json"
    return owner.decode_obligation((FIXTURES / name).read_bytes())


@pytest.mark.parametrize(
    "name",
    [
        "report-points-fulfilled.json",
        "report-money-fulfilled.json",
        "report-failed.json",
    ],
)
def test_full_report_fixtures(owner, name):
    expected = fixture(name)
    assert (
        owner.decode_fulfillment_report(
            encode(expected),
            obligation=obligation(owner, money="money" in name),
            received_at=NOW,
        )
        == expected
    )


@pytest.mark.parametrize(
    "name",
    [
        "invalid-report-wrong-binding.json",
        "invalid-report-partial-quantity.json",
    ],
)
def test_foreign_and_partial_report_fixtures(owner, name):
    with pytest.raises(ValueError):
        owner.decode_fulfillment_report(
            (FIXTURES / name).read_bytes(),
            obligation=obligation(owner),
            received_at=NOW,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"contract_version": 1.0},
        {"contract_version": True},
        {"reported_status": "pending"},
        {"failure_code": "PROVIDER_TIMEOUT"},
        {"fulfilled_quantity": "10.0"},
        {"fulfilled_quantity": None},
        {"fulfilled_quantity": "11"},
        {"external_reference": "https://provider.example/transfer"},
        {"external_event_id": "019a78b0-0000-4000-8000-000000000070"},
        {"reported_at": "2026-11-12T05:08:00.000001Z"},
        {"reported_at": "2026-11-12T04:54:59.999999Z"},
        {"fulfilled_at": "2026-11-12T04:54:59.999999Z"},
        {"fulfilled_at": "2026-11-12T05:08:00.000001Z"},
        {"reported_at": "2026-11-12T05:01:01Z"},
        {"provider_payload": {}},
    ],
)
def test_invalid_success_report(owner, change):
    with pytest.raises(ValueError):
        owner.decode_fulfillment_report(
            encode(fixture("report-points-fulfilled.json") | change),
            obligation=obligation(owner),
            received_at=NOW,
        )


@pytest.mark.parametrize(
    "field",
    [
        "source_instance_id",
        "fulfillment_root_id",
        "award_id",
        "project_id",
        "adapter_binding_id",
        "correlation_id",
        "route_key",
        "instrument_type",
        "unit_code",
    ],
)
def test_every_report_source_field_matches_immutable_obligation(owner, field):
    value = fixture("report-points-fulfilled.json")
    replacement = (
        "019a78b0-0000-7000-8000-000000000099"
        if field.endswith("_id")
        else {
            "route_key": "finance.other",
            "instrument_type": "money",
            "unit_code": "OTHER",
        }[field]
    )
    value[field] = replacement
    with pytest.raises(ValueError, match="source mismatch"):
        owner.decode_fulfillment_report(
            encode(value), obligation=obligation(owner), received_at=NOW
        )


def test_failed_report_cannot_claim_amount_or_fulfillment(owner):
    value = fixture("report-failed.json") | {"fulfilled_quantity": "10"}
    with pytest.raises(ValueError):
        owner.decode_fulfillment_report(
            encode(value), obligation=obligation(owner), received_at=NOW
        )


def test_arbitrarily_late_reports_and_linked_exceptions_remain_valid(owner):
    later = datetime(2030, 1, 1, tzinfo=UTC)
    report = fixture("report-points-fulfilled.json")
    assert (
        owner.decode_fulfillment_report(
            encode(report),
            obligation=obligation(owner),
            received_at=later,
        )
        == report
    )
    exception = fixture("exception-after-fulfillment.json")
    assert (
        owner.decode_fulfillment_exception(
            encode(exception),
            obligation=obligation(owner),
            fulfilled_report=report,
            received_at=later,
        )
        == exception
    )


@pytest.mark.parametrize(
    "change",
    [
        {"contract_version": 1.0},
        {"kind": "repay"},
        {"provider_payload": {}},
        {"exception_event_id": "019a78b0-0000-4000-8000-000000000080"},
        {"original_fulfillment_event_id": "019a78b0-0000-7000-8000-000000000099"},
        {"project_id": "019a78b0-0000-7000-8000-000000000099"},
        {"observed_at": "2026-11-12T04:55:59.999999Z"},
        {"observed_at": "2026-11-12T05:08:00.000001Z"},
        {"reported_at": "2026-11-12T04:56:59.999999Z"},
        {"reported_at": "2026-11-12T05:08:00.000001Z"},
    ],
)
def test_invalid_exception_linkage_and_times(owner, change):
    with pytest.raises(ValueError):
        owner.decode_fulfillment_exception(
            encode(fixture("exception-after-fulfillment.json") | change),
            obligation=obligation(owner),
            fulfilled_report=fixture("report-points-fulfilled.json"),
            received_at=NOW,
        )


def test_exception_requires_actual_successful_report_shape(owner):
    with pytest.raises(ValueError, match="requires fulfilled"):
        owner.decode_fulfillment_exception(
            encode(fixture("exception-after-fulfillment.json")),
            obligation=obligation(owner),
            fulfilled_report=fixture("report-failed.json"),
            received_at=NOW,
        )
