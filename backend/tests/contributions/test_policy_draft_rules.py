"""Complete ContributionPolicy graph validation."""

from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.compensation.api import CompensationInstrumentType
from app.modules.contributions.api import (
    ContributionPolicyConflict,
    PolicyDefinitionInput,
    PolicyRuleInput,
)
from app.modules.contributions.policy_validation import (
    _validate_definition,
    validate_policy_graph,
    validate_policy_name,
)
from tests.contributions.policy_test_support import complete_rules


def test_update_requires_exactly_one_accepted_submission_rule() -> None:
    rules = (complete_rules()[1],)
    with pytest.raises(ContributionPolicyConflict):
        validate_policy_graph(rules)


def test_update_requires_exactly_one_completed_review_rule() -> None:
    rules = (complete_rules()[0],)
    with pytest.raises(ContributionPolicyConflict):
        validate_policy_graph(rules)


def test_update_rejects_duplicate_required_rule_without_effect() -> None:
    rule = complete_rules()[0]
    with pytest.raises(ContributionPolicyConflict):
        validate_policy_graph((rule, rule))


def test_update_rejects_instrument_definition_for_unpaid_rule() -> None:
    paid = complete_rules()[0]
    invalid = replace(paid, compensation_mode="unpaid")
    with pytest.raises(ContributionPolicyConflict):
        validate_policy_graph((invalid, complete_rules()[1]))


def test_update_rejects_duplicate_instrument_definition() -> None:
    paid, review = complete_rules()
    invalid = replace(paid, definitions=(paid.definitions[0], paid.definitions[0]))
    with pytest.raises(ContributionPolicyConflict):
        validate_policy_graph((invalid, review))


@pytest.mark.parametrize("quantity", ("0", "-1", "1e2", "01", "NaN"))
def test_update_rejects_noncanonical_quantity(quantity: str) -> None:
    item = PolicyDefinitionInput(
        instrument_type=CompensationInstrumentType.MONEY,
        unit_code="USD",
        quantity=quantity,
        adapter_binding_id=uuid4(),
    )
    with pytest.raises(ContributionPolicyConflict):
        _validate_definition(item)


def test_update_accepts_one_or_two_unique_compensated_definitions() -> None:
    paid, review = complete_rules()
    points = PolicyDefinitionInput(
        instrument_type=CompensationInstrumentType.PROJECT_POINTS,
        unit_code="POINT",
        quantity="2",
        adapter_binding_id=uuid4(),
    )
    rule = PolicyRuleInput(
        contribution_type="accepted_submission",
        compensation_mode="compensated",
        definitions=(*paid.definitions, points),
    )
    assert validate_policy_graph((rule, review)) == (rule, review)


def test_update_rejects_missing_required_rule_without_effect() -> None:
    with pytest.raises(ContributionPolicyConflict):
        validate_policy_graph((complete_rules()[0],))


@pytest.mark.parametrize("quantity", ("0", "-1"))
def test_update_rejects_non_positive_quantity(quantity: str) -> None:
    item = PolicyDefinitionInput(
        instrument_type=CompensationInstrumentType.MONEY,
        unit_code="USD",
        quantity=quantity,
        adapter_binding_id=uuid4(),
    )
    with pytest.raises(ContributionPolicyConflict):
        _validate_definition(item)


@pytest.mark.parametrize("quantity", ("1e2", "01", "NaN"))
def test_update_rejects_non_canonical_quantity(quantity: str) -> None:
    item = PolicyDefinitionInput(
        instrument_type=CompensationInstrumentType.MONEY,
        unit_code="USD",
        quantity=quantity,
        adapter_binding_id=uuid4(),
    )
    with pytest.raises(ContributionPolicyConflict):
        _validate_definition(item)


def test_create_rejects_noncanonical_policy_name() -> None:
    with pytest.raises(ContributionPolicyConflict):
        validate_policy_name(" padded ")


def test_update_rejects_compensated_rule_without_definitions() -> None:
    paid, review = complete_rules()
    with pytest.raises(ContributionPolicyConflict):
        validate_policy_graph((replace(paid, definitions=()), review))


@pytest.mark.parametrize("quantity", ("1.5", "1.0"))
def test_update_rejects_non_integer_scale_project_points(quantity: str) -> None:
    item = PolicyDefinitionInput(
        instrument_type=CompensationInstrumentType.PROJECT_POINTS,
        unit_code="POINT",
        quantity=quantity,
        adapter_binding_id=uuid4(),
    )
    with pytest.raises(ContributionPolicyConflict):
        _validate_definition(item)


def test_update_conceals_malformed_rule_input() -> None:
    with pytest.raises(ContributionPolicyConflict, match="contribution_policy_conflict"):
        validate_policy_graph((object(), complete_rules()[1]))  # type: ignore[arg-type]


def test_update_rejects_unknown_compensation_mode_before_authorization() -> None:
    paid, review = complete_rules()
    invalid = replace(paid, compensation_mode="unknown")  # type: ignore[arg-type]
    with pytest.raises(ContributionPolicyConflict):
        validate_policy_graph((invalid, review))


def test_update_rejects_noncanonical_instrument_type() -> None:
    item = PolicyDefinitionInput(
        instrument_type="money",  # type: ignore[arg-type]
        unit_code="USD",
        quantity="1.00",
        adapter_binding_id=uuid4(),
    )
    with pytest.raises(ContributionPolicyConflict):
        _validate_definition(item)
