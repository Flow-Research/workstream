"""Pure output contracts; these tests claim neither authority nor DB snapshots."""

import csv
from datetime import UTC, datetime, timedelta, timezone
from io import StringIO

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.contributions.api.records import (
    ContributionAwardView, ContributionExportResponse, ContributionReadRequest,
    ContributionRecordView,
)
from app.modules.contributions.records.csv import contribution_csv, formula_safe_text

TIME = datetime(2026, 10, 10, 12, tzinfo=UTC)


def record(*, awards=(), reviewer=False, **changes):
    return ContributionRecordView(**({
        "contribution_id": new_record_id(), "project_id": new_record_id(),
        "task_id": new_record_id(), "submission_id": new_record_id(),
        "task_size": None if reviewer else "medium",
        "contributor_id": new_record_id(), "contributor_display_name": "Ada",
        "contribution_type": "completed_review" if reviewer else "accepted_submission",
        "source_review_id": new_record_id() if reviewer else None,
        "source_review_lease_id": new_record_id() if reviewer else None,
        "source_final_acceptance_id": None if reviewer else new_record_id(),
        "source_task_assignment_id": None if reviewer else new_record_id(),
        "artifact_hash": "sha256:" + "a" * 64,
        "contribution_policy_version_id": new_record_id(), "policy_version_number": 4,
        "recorded_at": TIME, "accepted_at": None if reviewer else TIME - timedelta(seconds=2),
        "acceptance_source": None if reviewer else "task_post_submit_route",
        "acceptance_review_id": None,
        "acceptance_routing_manifest_id": None if reviewer else new_record_id(),
        "task_title": "A task", "source_type": "manual", "source_ref": None,
        "external_task_id": None, "awards": awards,
    } | changes))


def award(*, instrument="money", quantity="99999999999999999999.123456789012345678"):
    return ContributionAwardView(
        award_id=new_record_id(), award_definition_id=new_record_id(),
        instrument=instrument, unit="USD" if instrument == "money" else "FLOW",
        quantity=quantity,
    )


def parse_csv(*items):
    response = ContributionExportResponse(exported_at=TIME, items=items)
    text = contribution_csv(response).decode("utf-8")
    return response, list(csv.DictReader(StringIO(text, newline="")))


def test_empty_and_zero_award_exports_keep_honest_identity():
    _, empty = parse_csv()
    assert empty == []
    item = record()
    response, rows = parse_csv(item)
    assert response.items[0].awards == ()
    assert len(rows) == 1
    assert rows[0]["contribution_id"] == str(item.contribution_id)
    assert rows[0]["award_id"] == rows[0]["quantity"] == ""
    assert "paid" not in rows[0] and "payout_status" not in rows[0]


@pytest.mark.parametrize("instrument,quantity", [
    ("money", "99999999999999999999.123456789012345678"),
    ("project_points", "123456789"),
])
def test_selected_award_preserves_identity_size_and_all_decimal_digits(instrument, quantity):
    value = award(instrument=instrument, quantity=quantity)
    item = record(awards=(value,))
    response, rows = parse_csv(item)
    assert len(response.items) == len(rows) == 1
    assert rows[0]["contribution_id"] == str(item.contribution_id)
    assert rows[0]["award_id"] == str(value.award_id)
    assert rows[0]["quantity"] == quantity
    assert rows[0]["task_size"] == "medium"
    assert response.model_dump(mode="json")["items"][0]["awards"][0]["quantity"] == quantity


@pytest.mark.parametrize("text", ["=HYPERLINK(\"x\")", "+cmd", "-2+3", "@SUM(1)", " \t=1+2", "\tordinary", "\rordinary", "\nordinary", "＝SUM(1)", "＋cmd", "－2+3", "＠SUM(1)"])
def test_formula_like_text_is_neutralized_in_every_untrusted_column(text):
    value = award().model_copy(update={"unit": text})
    item = record(awards=(value,), contributor_display_name=text, task_title=text,
                  source_type=text, source_ref=text, external_task_id=text)
    response, rows = parse_csv(item)
    for column in ("unit", "contributor_display_name", "task_title", "source_type",
                   "source_ref", "external_task_id"):
        assert rows[0][column] == "'" + text
    assert response.items[0].task_title == text


def test_embedded_cell_delimiters_cannot_start_an_extra_formula_cell():
    text = 'normal\",=HYPERLINK(\"x\")\n@SUM(1)'
    item = record(task_title=text)
    _, rows = parse_csv(item)
    assert len(rows) == 1 and rows[0]["task_title"] == text
    assert None not in rows[0]


def test_complete_response_accepts_1000_and_refuses_1001_without_truncation():
    first = record()
    items = tuple(first.model_copy(update={"contribution_id": new_record_id()}) for _ in range(1001))
    items = tuple(sorted(items, key=lambda item: (item.recorded_at, item.contribution_id)))
    response = ContributionExportResponse(exported_at=TIME, items=items[:1000])
    assert len(list(csv.DictReader(StringIO(contribution_csv(response).decode("utf-8"))))) == 1000
    with pytest.raises(ValidationError):
        ContributionExportResponse(exported_at=TIME, items=items)


def test_one_award_identity_cannot_appear_under_two_contributions():
    shared = award()
    items = tuple(sorted((record(awards=(shared,)), record(awards=(shared,))),
                         key=lambda item: (item.recorded_at, item.contribution_id)))
    with pytest.raises(ValidationError, match="repeats an award"):
        ContributionExportResponse(exported_at=TIME, items=items)


def test_unicode_quoting_and_multiline_text_round_trip_without_false_formula_marker():
    text = 'Résumé, "quote"\nsecond line'
    _, rows = parse_csv(record(task_title=text))
    assert rows[0]["task_title"] == text
    assert formula_safe_text("ordinary") == "ordinary"


def test_recorded_interval_normalizes_utc_and_review_acceptance_stays_null():
    offset = TIME.astimezone(timezone(timedelta(hours=3)))
    request = ContributionReadRequest(audience="self", actor_profile_id=new_record_id(),
                                      recorded_from=offset, recorded_before=offset + timedelta(days=1))
    assert request.recorded_from == TIME and request.recorded_from.tzinfo is UTC
    _, rows = parse_csv(record(reviewer=True))
    assert rows[0]["recorded_at"] == "2026-10-10T12:00:00.000000Z"
    assert rows[0]["accepted_at"] == rows[0]["acceptance_source"] == ""
    with pytest.raises(ValidationError, match="acceptance time"):
        record(reviewer=True, accepted_at=TIME)
    with pytest.raises(ValidationError, match="timezone"):
        ContributionReadRequest(audience="self", actor_profile_id=new_record_id(),
                                recorded_from=datetime(2026, 10, 10))
    with pytest.raises(ValidationError, match="precede"):
        ContributionReadRequest(audience="self", actor_profile_id=new_record_id(),
                                recorded_from=TIME, recorded_before=TIME)


def test_copied_values_cannot_bypass_quantity_or_source_validation():
    item = record(awards=(award(),))
    response = ContributionExportResponse(exported_at=TIME, items=(item,))
    invalid_award = item.awards[0].model_copy(update={"quantity": "1e2"})
    invalid = response.model_copy(update={"items": (item.model_copy(update={"awards": (invalid_award,)}),)})
    with pytest.raises(ValidationError):
        contribution_csv(invalid)
    invalid = response.model_copy(update={"items": (item.model_copy(update={"source_final_acceptance_id": None}),)})
    with pytest.raises(ValidationError, match="source identity"):
        contribution_csv(invalid)


def test_duplicate_contribution_or_award_rows_are_not_exportable():
    item = record()
    with pytest.raises(ValidationError, match="identity"):
        ContributionExportResponse(exported_at=TIME, items=(item, item))
    value = award()
    with pytest.raises(ValidationError, match="at most 1"):
        record(awards=(value, value))


@pytest.mark.parametrize("instrument,quantity", [("money", "0"), ("money", "100000000000000000000"), ("money", "0.1234567890123456789"), ("project_points", "1.0")])
def test_quantity_contract_rejects_rounding_and_noncanonical_points(instrument, quantity):
    with pytest.raises(ValidationError, match="quantity"):
        award(instrument=instrument, quantity=quantity)
