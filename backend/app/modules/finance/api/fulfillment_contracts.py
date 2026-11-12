"""FINANCE-owned public obligation decoding; wire validity confers no authority."""

from jsonschema import Draft202012Validator

from app.core.financial_wire import decode_financial_object, require_canonical_financial_values
from app.core.hashing import canonical_json_hash
from app.modules.finance.api.contract_schema import obligation_schema


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
    require_canonical_financial_values(value)
    source = {key: value[key] for key in SOURCE_AWARD_KEYS}
    if canonical_json_hash(source) != value["source_award_digest"]:
        raise ValueError("source award digest mismatch")
    envelope = {key: item for key, item in value.items() if key != "obligation_digest"}
    if canonical_json_hash(envelope) != value["obligation_digest"]:
        raise ValueError("obligation digest mismatch")
    return value
