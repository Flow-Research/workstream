"""Exact policy-quantity parsing shared by authoring and stored-fact validation."""

from decimal import Decimal, InvalidOperation
import re
from typing import Annotated

from pydantic import AfterValidator, Field, StrictStr

from app.modules.compensation.api.instruments import CompensationInstrumentType


_QUANTITY_PATTERN = re.compile(r"^(?:0|[1-9][0-9]{0,19})(?:\.[0-9]{1,18})?$")


def canonical_award_quantity(
    value: object, instrument_type: CompensationInstrumentType | None = None
) -> Decimal:
    """Return one bounded canonical quantity shared by schema and behavior."""
    if not isinstance(value, str) or _QUANTITY_PATTERN.fullmatch(value) is None:
        raise ValueError("quantity must be a canonical positive decimal string")
    try:
        quantity = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("quantity must be a canonical positive decimal string") from exc
    if not quantity.is_finite() or quantity <= 0:
        raise ValueError("quantity must be greater than zero")
    if (
        instrument_type is CompensationInstrumentType.PROJECT_POINTS
        and quantity.as_tuple().exponent < 0
    ):
        raise ValueError("project_points quantity must be a whole-number string")
    return quantity


def _policy_quantity_string(value: str) -> str:
    """Keep author-entered exact decimal notation until canonical fact emission."""
    canonical_award_quantity(value)
    return value


PolicyQuantity = Annotated[
    StrictStr,
    Field(
        pattern=_QUANTITY_PATTERN.pattern,
        json_schema_extra={
            "not": {
                "anyOf": [
                    {"pattern": r"^0(?:\.0+)?$"},
                    {"pattern": r"[^0-9.]"},
                ]
            }
        },
    ),
    AfterValidator(_policy_quantity_string),
]
