"""FINANCE-owned public obligation decoding; wire validity confers no authority."""

from datetime import datetime, timedelta
import json

from jsonschema import Draft202012Validator

from app.core.financial_wire import (
    canonical_utc_timestamp,
    require_canonical_quantity,
    require_canonical_uuid,
    decode_financial_object,
    require_canonical_obligation_values,
)
from app.core.hashing import canonical_json_hash
from app.modules.finance.api.contract_schema import (
    obligation_schema,
    fulfillment_report_schema,
    fulfillment_exception_schema,
)


SOURCE_AWARD_KEYS = (
    "award_id",
    "project_id",
    "contribution_record_id",
    "contributor_id",
    "contribution_policy_version_id",
    "award_definition_id",
    "adapter_binding_id",
    "instrument_type",
    "unit_code",
    "quantity",
    "awarded_at",
    "correlation_id",
)


def decode_obligation(body: bytes) -> dict:
    """Independently validate raw wire, source shape and both immutable digests."""
    value = decode_financial_object(body)
    errors = Draft202012Validator(obligation_schema()).iter_errors(value)
    if next(errors, None) is not None:
        raise ValueError("invalid obligation shape")
    require_canonical_obligation_values(value)
    source = {key: value[key] for key in SOURCE_AWARD_KEYS}
    if canonical_json_hash(source) != value["source_award_digest"]:
        raise ValueError("source award digest mismatch")
    envelope = {key: item for key, item in value.items() if key != "obligation_digest"}
    if canonical_json_hash(envelope) != value["obligation_digest"]:
        raise ValueError("obligation digest mismatch")
    return value


def decode_fulfillment_report(body: bytes, *, obligation: dict, received_at: datetime) -> dict:
    """Validate a full-award report against exact caller-owned source evidence.

    Pure validation cannot establish source authority, provider finality or a
    stored receipt. The caller must obtain the obligation under its owner guards.
    """
    value = decode_financial_object(body)
    if next(Draft202012Validator(fulfillment_report_schema()).iter_errors(value), None):
        raise ValueError("invalid fulfillment report shape")
    if type(value["contract_version"]) is not int:
        raise ValueError("version must be an integer wire value")
    for key in (
        "source_instance_id",
        "fulfillment_root_id",
        "award_id",
        "project_id",
        "adapter_binding_id",
        "route_key",
        "instrument_type",
        "unit_code",
        "correlation_id",
    ):
        if value[key] != obligation[key]:
            raise ValueError("fulfillment source mismatch")
    require_canonical_uuid(value["external_event_id"], version=7)
    reported = canonical_utc_timestamp(value["reported_at"])
    awarded = canonical_utc_timestamp(obligation["awarded_at"])
    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise ValueError("receiver time must be timezone aware")
    skew = timedelta(seconds=300)
    if reported < awarded - skew or reported > received_at + skew:
        raise ValueError("report time outside evidence bounds")
    if value["reported_status"] == "fulfilled":
        require_canonical_quantity(value["fulfilled_quantity"], value["instrument_type"])
        if value["fulfilled_quantity"] != obligation["quantity"]:
            raise ValueError("partial or changed fulfilled quantity")
        fulfilled = canonical_utc_timestamp(value["fulfilled_at"])
        if (
            fulfilled < awarded - skew
            or fulfilled > received_at + skew
            or reported < fulfilled - skew
        ):
            raise ValueError("fulfillment time outside evidence bounds")
    return value


def decode_fulfillment_exception(
    body: bytes,
    *,
    obligation: dict,
    fulfilled_report: dict,
    received_at: datetime,
) -> dict:
    """Validate a linked post-success observation without authorizing repayment."""
    value = decode_financial_object(body)
    if next(Draft202012Validator(fulfillment_exception_schema()).iter_errors(value), None):
        raise ValueError("invalid fulfillment exception shape")
    if type(value["contract_version"]) is not int:
        raise ValueError("version must be an integer wire value")
    # Revalidate the exact retained successful event, not a caller's bare event ID.
    prior = decode_fulfillment_report(
        json.dumps(fulfilled_report).encode("utf-8"),
        obligation=obligation,
        received_at=received_at,
    )
    if prior["reported_status"] != "fulfilled":
        raise ValueError("exception requires fulfilled receipt")
    for key in (
        "source_instance_id",
        "fulfillment_root_id",
        "award_id",
        "project_id",
        "adapter_binding_id",
        "route_key",
        "correlation_id",
    ):
        if value[key] != obligation[key]:
            raise ValueError("exception source mismatch")
    require_canonical_uuid(value["exception_event_id"], version=7)
    if value["original_fulfillment_event_id"] != prior["external_event_id"]:
        raise ValueError("exception references another fulfillment")
    observed = canonical_utc_timestamp(value["observed_at"])
    reported = canonical_utc_timestamp(value["reported_at"])
    skew = timedelta(seconds=300)
    fulfilled = canonical_utc_timestamp(prior["fulfilled_at"])
    if (
        observed < fulfilled - skew
        or observed > received_at + skew
        or reported < observed - skew
        or reported > received_at + skew
    ):
        raise ValueError("exception time outside evidence bounds")
    return value
