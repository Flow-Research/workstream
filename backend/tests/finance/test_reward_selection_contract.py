"""Exact size selection packets preserve complete terms without implicit fallback."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.compensation.api import CompensationInstrumentType
from app.modules.contributions.api import RewardSelectionFacts, RewardSelectionRequest

POLICY = UUID("019a78b0-0000-7000-8000-000000000004")
DEFINITION = UUID("019a78b0-0000-7000-8000-000000000005")
BINDING = UUID("019a78b0-0000-7000-8000-000000000010")
PROJECT = UUID("019a78b0-0000-7000-8000-000000000001")


def compensated(**changes):
    return (
        dict(
            policy_version_id=POLICY,
            task_size="medium",
            compensation_mode="compensated",
            award_definition_id=DEFINITION,
            instrument_type=CompensationInstrumentType.PROJECT_POINTS,
            unit_code="FLOW",
            quantity="20",
            adapter_binding_id=BINDING,
        )
        | changes
    )


@pytest.mark.parametrize("size", ["small", "medium", "large"])
def test_exact_selection_packet_is_immutable_and_complete(size):
    selected = RewardSelectionFacts(**compensated(task_size=size))
    assert selected.task_size == size
    assert selected.award_definition_id == DEFINITION
    assert selected.quantity == "20"
    assert RewardSelectionFacts.model_validate_json(selected.model_dump_json()) == selected
    with pytest.raises(ValidationError):
        selected.quantity = "999"


@pytest.mark.parametrize("size", [None, "Small", "unknown", "", 1])
def test_unknown_or_null_size_cannot_fall_back_to_small(size):
    with pytest.raises(ValidationError):
        RewardSelectionRequest(project_id=PROJECT, policy_version_id=POLICY, task_size=size)


@pytest.mark.parametrize(
    "field",
    [
        "award_definition_id",
        "instrument_type",
        "unit_code",
        "quantity",
        "adapter_binding_id",
    ],
)
def test_compensated_selection_cannot_defer_a_financial_fact(field):
    with pytest.raises(ValidationError):
        RewardSelectionFacts(**compensated(**{field: None}))


def test_unpaid_requires_explicit_nulls_instead_of_a_later_policy_lookup():
    unpaid = dict(
        policy_version_id=POLICY,
        task_size="large",
        compensation_mode="unpaid",
        award_definition_id=None,
        instrument_type=None,
        unit_code=None,
        quantity=None,
        adapter_binding_id=None,
    )
    assert RewardSelectionFacts(**unpaid).quantity is None
    with pytest.raises(ValidationError):
        RewardSelectionFacts(**(unpaid | {"quantity": "20"}))
    del unpaid["award_definition_id"]
    with pytest.raises(ValidationError):
        RewardSelectionFacts(**unpaid)


@pytest.mark.parametrize("quantity", ["0", "20.0", "1.5", "1e1", 20, " 20", "-1"])
def test_points_selection_preserves_only_canonical_whole_quantities(quantity):
    with pytest.raises(ValidationError):
        RewardSelectionFacts(**compensated(quantity=quantity))


def test_money_selection_keeps_exact_precision_without_provider_rounding():
    selected = RewardSelectionFacts(
        **compensated(
            instrument_type=CompensationInstrumentType.MONEY,
            unit_code="NGN",
            quantity="2.125000000000000001",
        )
    )
    assert selected.quantity == "2.125000000000000001"


def test_forged_copy_revalidates_shape_at_the_owner_boundary():
    selected = RewardSelectionFacts(**compensated())
    forged = selected.model_copy(update={"compensation_mode": "unpaid"})
    with pytest.raises(ValidationError):
        RewardSelectionFacts.model_validate(forged)
