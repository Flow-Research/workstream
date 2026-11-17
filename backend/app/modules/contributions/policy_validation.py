"""Pure validation and digest helpers for ContributionPolicy commands."""

from dataclasses import asdict
from uuid import UUID

from pydantic import BaseModel, ValidationError

from app.core.hashing import canonical_json_hash
from app.modules.compensation.api import CompensationInstrumentType
from app.modules.contributions.api import (
    CompensationUnitAction,
    ContributionPolicyConflict,
    PolicyAction,
    PolicyRuleInput,
)


def _json_value(value: object) -> object:
    """Convert immutable command values into canonical JSON values."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_unset=True)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def policy_request_digest(action: PolicyAction | CompensationUnitAction, request: object) -> str:
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


def validate_policy_graph(
    rules: tuple[PolicyRuleInput, ...],
    *,
    instrument_type: CompensationInstrumentType | None,
    unit_code: str | None,
    adapter_binding_id: UUID | None,
) -> tuple[PolicyRuleInput, ...]:
    """Validate the sole new authoring graph, including untrusted constructed inputs."""
    from app.modules.contributions.api.policy_http import PolicyUpdateInput

    from app.modules.contributions.api.policies import (
        UnpaidPolicyRuleInput,
        AcceptedSubmissionPolicyRuleInput,
        CompletedReviewPolicyRuleInput,
    )

    if (
        type(rules) is not tuple
        or any(
            type(rule)
            not in {
                UnpaidPolicyRuleInput,
                AcceptedSubmissionPolicyRuleInput,
                CompletedReviewPolicyRuleInput,
            }
            for rule in rules
        )
        or (instrument_type is not None and type(instrument_type) is not CompensationInstrumentType)
        or (adapter_binding_id is not None and type(adapter_binding_id) is not UUID)
    ):
        raise ContributionPolicyConflict("contribution_policy_conflict")
    raw_rules = []
    for rule in rules:
        raw = dict(rule)
        if "quantities" in raw and isinstance(raw["quantities"], BaseModel):
            raw["quantities"] = dict(raw["quantities"])
        raw_rules.append(raw)
    try:
        checked = PolicyUpdateInput.model_validate(
            {
                "instrument_type": instrument_type,
                "unit_code": unit_code,
                "adapter_binding_id": adapter_binding_id,
                "rules": raw_rules,
            }
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise ContributionPolicyConflict("contribution_policy_conflict") from exc
    return checked.rules
