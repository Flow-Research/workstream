"""Complete v2 graph validation, including forged internal owner inputs."""

from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.compensation.api import CompensationInstrumentType
from app.modules.contributions.api import ContributionPolicyConflict
from app.modules.contributions.api.policies import TaskSizeQuantities
from app.modules.contributions.api.policy_http import PolicyUpdateInput
from app.modules.contributions.api.quantities import canonical_award_quantity
from app.modules.contributions.policy_validation import validate_policy_graph, validate_policy_name
from tests.contributions.policy_test_support import complete_rules, service_fixture
from tests.contributions.test_policy_draft_update import install_draft, update_request


def validate(rules, **header):
    values = dict(
        instrument_type=CompensationInstrumentType.MONEY,
        unit_code="USD",
        adapter_binding_id=new_record_id(),
    )
    values.update(header)
    return validate_policy_graph(rules, **values)


@pytest.mark.parametrize(
    "rules", [(complete_rules()[1],), (complete_rules()[0],), (complete_rules()[0],) * 2]
)
def test_update_requires_exactly_one_rule_of_each_type(rules):
    with pytest.raises(ContributionPolicyConflict):
        validate(rules)


def test_update_rejects_quantities_for_unpaid_rule():
    paid, review = complete_rules()
    invalid = paid.model_copy(update={"compensation_mode": "unpaid"})
    with pytest.raises(ContributionPolicyConflict):
        validate((invalid, review))


def test_update_rejects_superseded_dual_instrument_graph():
    with pytest.raises(ValidationError):
        PolicyUpdateInput.model_validate(
            {
                "instrument_type": "money",
                "unit_code": "USD",
                "adapter_binding_id": str(new_record_id()),
                "rules": [
                    {
                        "contribution_type": "accepted_submission",
                        "compensation_mode": "compensated",
                        "definitions": [
                            {"instrument_type": "money", "quantity": "1"},
                            {"instrument_type": "project_points", "quantity": "2"},
                        ],
                    },
                    {"contribution_type": "completed_review", "compensation_mode": "unpaid"},
                ],
            }
        )


@pytest.mark.parametrize(
    "quantity", ("0", "-1", "1e2", "01", "NaN", "100000000000000000000", "1.0000000000000000000")
)
def test_update_rejects_invalid_quantities(quantity):
    with pytest.raises(ValueError):
        canonical_award_quantity(quantity, CompensationInstrumentType.MONEY)


def test_create_rejects_noncanonical_policy_name():
    with pytest.raises(ContributionPolicyConflict):
        validate_policy_name(" padded ")


@pytest.mark.parametrize(
    "tiers",
    [{}, {"small": "1", "medium": "2"}, {"small": "1", "medium": "2", "large": "3", "other": "4"}],
)
def test_update_rejects_incomplete_or_extra_tiers(tiers):
    paid, review = complete_rules()
    invalid = paid.model_copy(update={"quantities": tiers})
    with pytest.raises(ContributionPolicyConflict):
        validate((invalid, review))


@pytest.mark.parametrize("quantity", ("1.5", "1.0"))
def test_update_rejects_non_integer_scale_project_points(quantity):
    with pytest.raises(ValueError):
        canonical_award_quantity(quantity, CompensationInstrumentType.PROJECT_POINTS)


def test_update_conceals_malformed_rule_input():
    with pytest.raises(ContributionPolicyConflict, match="contribution_policy_conflict"):
        validate((object(), complete_rules()[1]))


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", ("100000000000000000000", "1.0000000000000000000"))
async def test_update_rejects_out_of_bounds_quantity_before_authorization(quantity):
    fixture = service_fixture()
    request = update_request(fixture)
    paid, review = request.rules
    tiers = TaskSizeQuantities.model_construct(small=quantity, medium="2", large="3")
    request = replace(request, rules=(paid.model_copy(update={"quantities": tiers}), review))
    install_draft(fixture, request)
    with pytest.raises(ContributionPolicyConflict, match="contribution_policy_conflict"):
        await fixture.service.update_draft(request)
    fixture.repository.get_policy.assert_not_awaited()
    assert fixture.authorization.prepared == []
    assert fixture.authorization.consumed == []
    fixture.repository.replace_graph.assert_not_awaited()


def test_update_rejects_unknown_compensation_mode_before_authorization():
    paid, review = complete_rules()
    with pytest.raises(ContributionPolicyConflict):
        validate((paid.model_copy(update={"compensation_mode": "unknown"}), review))


def test_update_rejects_noncanonical_instrument_type():
    with pytest.raises(ContributionPolicyConflict):
        validate(complete_rules(), instrument_type="money")
