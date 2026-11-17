"""The sole new policy authoring shape selects exact tiers under one header."""

from copy import deepcopy
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.compensation.api import CompensationInstrumentType
from app.modules.contributions.api.policy_http import PolicyUpdateInput
from app.modules.contributions.api import ContributionPolicyConflict
from app.modules.contributions.policy_validation import validate_policy_graph

BINDING = "019a78b0-0000-7000-8000-000000000010"


def policy():
    return {
        "instrument_type": "project_points",
        "unit_code": "FLOW",
        "adapter_binding_id": BINDING,
        "rules": [
            {
                "contribution_type": "accepted_submission",
                "compensation_mode": "compensated",
                "quantities": {"small": "10", "medium": "20", "large": "100"},
            },
            {"contribution_type": "completed_review", "compensation_mode": "unpaid"},
        ],
    }


def test_three_tiers_and_fixed_reviewer_share_one_header():
    value = policy()
    value["rules"][1] = {
        "contribution_type": "completed_review",
        "compensation_mode": "compensated",
        "quantity": "3",
    }
    parsed = PolicyUpdateInput.model_validate(value)
    assert parsed.instrument_type is CompensationInstrumentType.PROJECT_POINTS
    assert parsed.rules[0].quantities.medium == "20"
    assert parsed.rules[1].quantity == "3"
    assert parsed.adapter_binding_id == UUID(BINDING)
    assert (
        validate_policy_graph(
            parsed.rules,
            instrument_type=parsed.instrument_type,
            unit_code=parsed.unit_code,
            adapter_binding_id=parsed.adapter_binding_id,
        )
        == parsed.rules
    )


def test_wholly_unpaid_requires_explicit_null_header_and_no_financial_setup():
    value = policy() | {"instrument_type": None, "unit_code": None, "adapter_binding_id": None}
    value["rules"][0] = {"contribution_type": "accepted_submission", "compensation_mode": "unpaid"}
    parsed = PolicyUpdateInput.model_validate(value)
    assert parsed.instrument_type is None and all(
        rule.compensation_mode == "unpaid" for rule in parsed.rules
    )
    del value["unit_code"]
    with pytest.raises(ValidationError):
        PolicyUpdateInput.model_validate(value)


@pytest.mark.parametrize(
    "quantities",
    [
        {"small": "10", "medium": "20"},
        {"small": "10", "medium": "20", "large": "100", "extra": "200"},
        {"small": "0", "medium": "20", "large": "100"},
        {"small": 10, "medium": "20", "large": "100"},
        {"small": "1e1", "medium": "20", "large": "100"},
        {"small": "10.0", "medium": "20", "large": "100"},
        {"small": "10", "medium": "1.5", "large": "100"},
    ],
)
def test_tier_alternatives_are_complete_exact_and_whole_for_points(quantities):
    value = policy()
    value["rules"][0]["quantities"] = quantities
    with pytest.raises(ValidationError):
        PolicyUpdateInput.model_validate(value)


@pytest.mark.parametrize(
    "change",
    [
        {"definitions": []},
        {"quantity": "10"},
        {"instrument_type": "money"},
        {"unit_code": "NGN"},
        {"adapter_binding_id": BINDING},
    ],
)
def test_per_rule_overrides_and_superseded_definition_input_are_rejected(change):
    value = policy()
    value["rules"][0].update(change)
    with pytest.raises(ValidationError):
        PolicyUpdateInput.model_validate(value)


@pytest.mark.parametrize(
    "change",
    [
        {"quantity": None},
        {"quantities": None},
        {"quantity": "3"},
    ],
)
def test_unpaid_rule_forbids_even_explicit_null_amount_fields(change):
    value = policy()
    value["rules"][1].update(change)
    with pytest.raises(ValidationError):
        PolicyUpdateInput.model_validate(value)


def test_money_keeps_exact_policy_precision_without_provider_rounding():
    value = policy() | {"instrument_type": "money", "unit_code": "NGN"}
    value["rules"][0]["quantities"]["medium"] = "2.125000000000000001"
    assert (
        PolicyUpdateInput.model_validate(value).rules[0].quantities.medium == "2.125000000000000001"
    )


def test_equal_and_non_monotonic_sizes_are_valid_explicit_policy_choices():
    value = policy()
    value["rules"][0]["quantities"] = {"small": "20", "medium": "10", "large": "10"}
    assert PolicyUpdateInput.model_validate(value).rules[0].quantities.large == "10"


def test_duplicate_rule_type_is_not_a_complete_policy():
    value = policy()
    value["rules"][1] = deepcopy(value["rules"][0])
    with pytest.raises(ValidationError):
        PolicyUpdateInput.model_validate(value)


def test_forged_internal_compensated_rule_cannot_omit_its_header():
    parsed = PolicyUpdateInput.model_validate(policy())
    with pytest.raises(ContributionPolicyConflict):
        validate_policy_graph(
            parsed.rules, instrument_type=None, unit_code=None, adapter_binding_id=None
        )


def test_portable_policy_schema_preserves_cross_field_rules():
    from jsonschema import Draft202012Validator, FormatChecker

    validator = Draft202012Validator(
        PolicyUpdateInput.model_json_schema(), format_checker=FormatChecker()
    )
    good = policy()
    assert not list(validator.iter_errors(good))
    unpaid = deepcopy(good)
    unpaid.update(instrument_type=None, unit_code=None, adapter_binding_id=None)
    unpaid["rules"][0] = {"contribution_type": "accepted_submission", "compensation_mode": "unpaid"}
    assert not list(validator.iter_errors(unpaid))
    invalid = []
    for field in ("instrument_type", "unit_code", "adapter_binding_id"):
        invalid.append(deepcopy(good))
        invalid[-1][field] = None
    invalid.append(deepcopy(unpaid) | {"unit_code": "FLOW"})
    invalid.append(deepcopy(good))
    invalid[-1]["rules"][1] = deepcopy(invalid[-1]["rules"][0])
    invalid.append(deepcopy(good))
    invalid[-1]["rules"][0]["quantities"]["medium"] = "1.0"
    invalid.append(deepcopy(good) | {"instrument_type": "money", "unit_code": "usd"})
    invalid.append(deepcopy(good) | {"unit_code": "FLOW\n"})
    for value in invalid:
        assert list(validator.iter_errors(value)), value
        with pytest.raises(ValidationError):
            PolicyUpdateInput.model_validate(value)
