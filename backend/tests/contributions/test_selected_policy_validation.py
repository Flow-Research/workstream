"""Exact purpose/selection guards with otherwise-valid server-owned policy graphs."""

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.adapters.contributions import contribution_policy_validation_port
from app.modules.compensation.api import CompensationInstrumentType, PolicyAdapterBindingUnavailable
from app.modules.contributions.api import (
    ContributionPolicyUnavailable,
    ContributionPolicyValidationPurpose as Purpose,
    ContributionPolicyValidationRequest as Request,
)
from app.modules.contributions.selected_policy_validation import (
    SelectedContributionPolicyValidation,
)
from app.modules.projects.api import ProjectContributionPolicyUnavailable
from tests.contributions.policy_test_support import service_fixture, AllowProject, AllowBinding
from tests.contributions.test_policy_publish import _install_complete_draft, _request


def selection_fixture():
    """Install a complete published graph; vary only each test's target condition."""
    fixture = service_fixture()
    mutation = _request(fixture)
    policy, version = _install_complete_draft(fixture, mutation)
    policy.status = "active"
    policy.current_published_version_id = version.id
    version.status = "published"
    request = Request(
        project_id=fixture.project_id,
        contribution_policy_id=policy.id,
        contribution_policy_version_id=version.id,
        purpose=Purpose.GUIDE_ACTIVATION,
    )
    service = SelectedContributionPolicyValidation(
        fixture.service._session,
        projects=AllowProject(),
        bindings=AllowBinding(),
    )
    service._repository = fixture.repository
    rules, definitions = fixture.repository.lock_publication_graph.return_value
    return SimpleNamespace(
        service=service,
        repository=fixture.repository,
        request=request,
        policy=policy,
        version=version,
        rules=rules,
        definitions=definitions,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("purpose", list(Purpose))
async def test_exact_selection_returns_immutable_canonical_facts(purpose):
    f = selection_fixture()
    result = await f.service.validate_contribution_policy(replace(f.request, purpose=purpose))
    assert result.project_id == f.request.project_id
    assert result.contribution_policy_id == f.policy.id
    assert result.contribution_policy_version_id == f.version.id
    assert result.purpose is purpose
    assert result.version_number == 1
    assert result.adapter_binding_ids == (f.definitions[0].adapter_binding_id,)
    assert result.rules_and_definitions_digest.startswith("sha256:")
    assert len(result.rules_and_definitions_digest) == 71
    f.repository.get_version.assert_awaited_once_with(
        f.request.project_id,
        f.policy.id,
        f.version.id,
        for_update=True,
    )
    f.repository.get_selected_version.assert_not_awaited()
    with pytest.raises(FrozenInstanceError):
        result.version_number = 2


@pytest.mark.asyncio
async def test_activation_requires_selector_equality_even_when_version_is_published():
    f = selection_fixture()
    f.policy.current_published_version_id = uuid4()
    assert (
        f.version.status == "published"
    )  # The later retired-version guard cannot mask this proof.
    with pytest.raises(ContributionPolicyUnavailable, match="^contribution_policy_unavailable$"):
        await f.service.validate_contribution_policy(f.request)
    f.repository.get_version.assert_not_awaited()
    f.policy.current_published_version_id = f.version.id
    assert (
        await f.service.validate_contribution_policy(f.request)
    ).contribution_policy_version_id == f.version.id


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["published", "retired"])
@pytest.mark.parametrize("policy_status", ["active", "retired"])
async def test_revision_checks_exact_bound_version_without_current_selector(status, policy_status):
    f = selection_fixture()
    f.policy.status = policy_status
    f.policy.current_published_version_id = uuid4()
    f.version.status = status
    result = await f.service.validate_contribution_policy(
        replace(f.request, purpose=Purpose.REVISION_ADOPTION)
    )
    assert result.contribution_policy_version_id == f.version.id
    assert result.contribution_policy_version_id != f.policy.current_published_version_id
    assert f.version.status == status
    f.repository.get_selected_version.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "missing_policy",
        "draft_policy",
        "retired_policy",
        "missing_selector",
        "missing_version",
        "draft_version",
        "retired_version",
    ],
)
async def test_activation_rejects_ineligible_selection(failure):
    f = selection_fixture()
    if failure == "missing_policy":
        f.repository.get_policy.return_value = None
    elif failure.endswith("policy"):
        f.policy.status = failure.split("_")[0]
    elif failure == "missing_selector":
        f.policy.current_published_version_id = None
    elif failure == "missing_version":
        f.repository.get_version.return_value = None
    else:
        f.version.status = failure.split("_")[0]
    with pytest.raises(ContributionPolicyUnavailable):
        await f.service.validate_contribution_policy(f.request)
    f.repository.lock_publication_graph.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field", ["project_id", "contribution_policy_id", "contribution_policy_version_id", "purpose"]
)
@pytest.mark.parametrize("value", [None, "invalid"])
async def test_malformed_request_denies_before_owner_reads(field, value):
    f = selection_fixture()
    with pytest.raises(ContributionPolicyUnavailable):
        await f.service.validate_contribution_policy(replace(f.request, **{field: value}))
    f.repository.lock_project_scope.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("root,nested", [(False, False), (True, True)])
async def test_validation_requires_caller_root_transaction(root, nested):
    f = selection_fixture()
    f.service._session = SimpleNamespace(
        in_transaction=lambda: root, in_nested_transaction=lambda: nested
    )
    with pytest.raises(ContributionPolicyUnavailable):
        await f.service.validate_contribution_policy(f.request)
    f.repository.lock_project_scope.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "missing_rule",
        "duplicate_rule",
        "invalid_mode",
        "unpaid_definitions",
        "no_definitions",
        "duplicate_instrument",
        "zero_quantity",
        "unknown_instrument",
        "foreign_rule",
        "foreign_definition",
        "unattached_definition",
    ],
)
async def test_selected_graph_uses_canonical_complete_rule_validation(failure):
    f = selection_fixture()
    if failure == "missing_rule":
        f.rules.pop()
    elif failure == "duplicate_rule":
        f.rules[1].contribution_type = f.rules[0].contribution_type
    elif failure == "invalid_mode":
        f.rules[1].compensation_mode = "anything"
    elif failure == "unpaid_definitions":
        f.rules[0].compensation_mode = "unpaid"
    elif failure == "no_definitions":
        f.rules[0].award_definitions = []
        f.definitions.clear()
    elif failure == "duplicate_instrument":
        f.rules[0].award_definitions.append(f.definitions[0])
        f.definitions.append(f.definitions[0])
    elif failure == "zero_quantity":
        f.definitions[0].quantity = Decimal("0")
    elif failure == "unknown_instrument":
        f.definitions[0].instrument_type = "unknown"
    elif failure == "foreign_rule":
        f.rules[0].project_id = str(uuid4())
    elif failure == "foreign_definition":
        f.definitions[0].project_id = str(uuid4())
    else:
        f.definitions.clear()
    with pytest.raises(ContributionPolicyUnavailable):
        await f.service.validate_contribution_policy(f.request)
    f.repository.lock_unit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("purpose", list(Purpose))
@pytest.mark.parametrize(
    "resource",
    [
        "missing_unit",
        "retired_unit",
        "unavailable_binding",
        "wrong_binding",
        "wrong_project",
        "wrong_instrument",
    ],
)
async def test_both_purposes_require_current_resource_eligibility(purpose, resource):
    f = selection_fixture()
    if resource == "missing_unit":
        f.repository.lock_unit.return_value = None
    elif resource == "retired_unit":
        f.repository.lock_unit.return_value.status = "retired"
    elif resource == "unavailable_binding":
        f.service._bindings = SimpleNamespace(
            lock_policy_adapter_binding=AsyncMock(side_effect=PolicyAdapterBindingUnavailable)
        )
    else:
        original = await f.service._bindings.lock_policy_adapter_binding(
            project_id=f.request.project_id,
            adapter_binding_id=f.definitions[0].adapter_binding_id,
            instrument_type=CompensationInstrumentType.MONEY,
        )
        changes = {
            "wrong_binding": {"adapter_binding_id": uuid4()},
            "wrong_project": {"project_id": uuid4()},
            "wrong_instrument": {"instrument_type": type(original.instrument_type).PROJECT_POINTS},
        }
        f.service._bindings = SimpleNamespace(
            lock_policy_adapter_binding=AsyncMock(
                return_value=replace(original, **changes[resource])
            )
        )
    with pytest.raises(ContributionPolicyUnavailable):
        await f.service.validate_contribution_policy(replace(f.request, purpose=purpose))


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unavailable", "foreign"])
async def test_project_eligibility_fails_before_policy_disclosure(failure):
    f = selection_fixture()
    f.service._projects = SimpleNamespace(
        lock_contribution_policy_project=AsyncMock(
            side_effect=ProjectContributionPolicyUnavailable if failure == "unavailable" else None,
            return_value=SimpleNamespace(project_id=uuid4()),
        )
    )
    with pytest.raises(ContributionPolicyUnavailable):
        await f.service.validate_contribution_policy(f.request)
    f.repository.get_policy.assert_not_awaited()


def test_composition_and_public_contract_have_no_compatibility_alias():
    from app.modules.contributions import api

    assert {purpose.value for purpose in Purpose} == {"guide_activation", "revision_adoption"}
    assert not hasattr(api, "ContributionPolicyProjectEligibilityPort")
    port = contribution_policy_validation_port(SimpleNamespace())
    assert isinstance(port, SelectedContributionPolicyValidation)


@pytest.mark.asyncio
async def test_foreign_request_shape_is_not_coerced():
    f = selection_fixture()
    with pytest.raises(ContributionPolicyUnavailable):
        await f.service.validate_contribution_policy({"project_id": f.request.project_id})
    f.repository.lock_project_scope.assert_not_awaited()


@pytest.mark.asyncio
async def test_one_binding_cannot_supply_two_instruments():
    from app.modules.contributions.models import ContributionAwardDefinition

    f = selection_fixture()
    rule = f.rules[0]
    definition = ContributionAwardDefinition(
        id=uuid4(),
        contribution_rule_id=rule.id,
        contribution_policy_version_id=f.version.id,
        project_id=str(f.request.project_id),
        contribution_type=rule.contribution_type,
        instrument_type="project_points",
        unit_code="POINTS",
        quantity=Decimal("1"),
        adapter_binding_id=f.definitions[0].adapter_binding_id,
    )
    rule.award_definitions.append(definition)
    f.definitions.append(definition)
    with pytest.raises(ContributionPolicyUnavailable):
        await f.service.validate_contribution_policy(f.request)
