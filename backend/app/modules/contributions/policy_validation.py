"""Pure validation and digest helpers for ContributionPolicy commands."""

from dataclasses import asdict
from decimal import Decimal, InvalidOperation
import re
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.compensation.api import CompensationInstrumentType
from app.modules.contributions.api import (
    ContributionPolicyConflict,
    PolicyAction,
    PolicyDefinitionInput,
    PolicyRuleInput,
)


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


def _json_value(value: object) -> object:
    """Convert immutable command values into canonical JSON values."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def policy_request_digest(action: PolicyAction, request: object) -> str:
    """Hash one immutable command without leaking Python-only value types."""
    return canonical_json_hash(
        {
            "domain": "workstream.contribution.policy.operation.v1",
            "action": action,
            "request": _json_value(asdict(request)),  # type: ignore[arg-type]
        }
    )


def validate_policy_name(name: str) -> None:
    """Require one canonical, bounded display name."""
    if not isinstance(name, str) or name != name.strip() or not 1 <= len(name) <= 200:
        raise ContributionPolicyConflict("contribution_policy_conflict")


def validate_policy_graph(rules: tuple[PolicyRuleInput, ...]) -> tuple[PolicyRuleInput, ...]:
    """Validate one complete replacement graph."""
    if (
        type(rules) is not tuple
        or len(rules) != 2
        or any(type(rule) is not PolicyRuleInput for rule in rules)
        or {rule.contribution_type for rule in rules}
        != {"accepted_submission", "completed_review"}
    ):
        raise ContributionPolicyConflict("contribution_policy_conflict")
    for rule in rules:
        _validate_rule(rule)
    return rules


def _validate_rule(rule: PolicyRuleInput) -> None:
    """Validate one contribution rule and its closed definition set."""
    if type(rule) is not PolicyRuleInput or type(rule.definitions) is not tuple:
        raise ContributionPolicyConflict("contribution_policy_conflict")
    if rule.compensation_mode not in {"unpaid", "compensated"}:
        raise ContributionPolicyConflict("contribution_policy_conflict")
    instruments = [item.instrument_type for item in rule.definitions]
    if rule.compensation_mode == "unpaid" and rule.definitions:
        raise ContributionPolicyConflict("contribution_policy_conflict")
    if rule.compensation_mode == "compensated" and not 1 <= len(rule.definitions) <= 2:
        raise ContributionPolicyConflict("contribution_policy_conflict")
    if len(set(instruments)) != len(instruments):
        raise ContributionPolicyConflict("contribution_policy_conflict")
    for item in rule.definitions:
        _validate_definition(item)


def _validate_definition(item: PolicyDefinitionInput) -> None:
    """Validate one canonical award definition without coercion."""
    if (
        type(item) is not PolicyDefinitionInput
        or type(item.instrument_type) is not CompensationInstrumentType
        or type(item.adapter_binding_id) is not UUID
    ):
        raise ContributionPolicyConflict("contribution_policy_conflict")
    try:
        canonical_award_quantity(item.quantity, item.instrument_type)
    except ValueError:
        raise ContributionPolicyConflict("contribution_policy_conflict") from None
