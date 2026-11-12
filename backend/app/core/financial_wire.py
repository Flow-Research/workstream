"""Bounded canonical JSON primitives for authenticated financial contracts."""

import json
from datetime import datetime
from decimal import Decimal
import re
from uuid import UUID


def decode_financial_object(body: bytes) -> dict:
    """Reject ambiguous or oversized wire input before ordinary JSON parsing."""
    if not isinstance(body, bytes) or len(body) > 65536:
        raise ValueError("invalid financial envelope")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON member")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise ValueError("nonfinite JSON number")

    try:
        value = json.loads(
            body.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid_constant
        )
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("invalid financial envelope") from exc
    if type(value) is not dict:
        raise ValueError("financial envelope must be an object")
    return value


def require_canonical_obligation_values(value: dict) -> None:
    """Validate canonical UUID, UTC timestamp and exact positive quantity strings."""
    for key in ("contract_version", "reward_model_version"):
        if type(value[key]) is not int:
            raise ValueError("version must be an integer wire value")
    for key, item in value.items():
        if key.endswith("_id") and item is not None:
            require_canonical_uuid(item)
        if key.endswith("_at") and item is not None:
            canonical_utc_timestamp(item)
    require_canonical_quantity(value["quantity"], value["instrument_type"])


def require_canonical_uuid(value: str, *, version: int | None = None) -> None:
    """Reject alternate UUID spellings and, when required, wrong UUID versions."""
    parsed = UUID(value)
    if str(parsed) != value or (version is not None and parsed.version != version):
        raise ValueError("noncanonical UUID")


def canonical_utc_timestamp(value: str) -> datetime:
    """Parse a canonical six-fractional-digit UTC contract timestamp."""
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z", value):
        raise ValueError("noncanonical timestamp")
    return datetime.fromisoformat(value)


def require_canonical_quantity(quantity: str, instrument_type: str) -> None:
    """Require an exact positive canonical award-unit quantity without rounding."""
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,19})(?:\.[0-9]{1,18})?", quantity):
        raise ValueError("invalid quantity")
    amount = Decimal(quantity)
    if amount <= 0 or ("." in quantity and quantity.endswith("0")):
        raise ValueError("noncanonical positive quantity")
    if instrument_type == "project_points" and "." in quantity:
        raise ValueError("points must be whole")
