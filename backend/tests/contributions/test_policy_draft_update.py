"""Update-draft replacement behavior."""

from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.contributions.api import (
    ContributionPolicyConflict,
    ContributionPolicyUnavailable,
    ContributionPolicyUpdateDraftRequest,
)
from app.modules.contributions.models import ContributionPolicy, ContributionPolicyVersion
from tests.contributions.policy_test_support import complete_rules, service_fixture


def update_request(fixture: object) -> ContributionPolicyUpdateDraftRequest:
    return ContributionPolicyUpdateDraftRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,  # type: ignore[attr-defined]
        project_id=fixture.project_id,  # type: ignore[attr-defined]
        contribution_policy_id=uuid4(),
        contribution_policy_version_id=uuid4(),
        rules=complete_rules(),
    )


def install_draft(fixture: object, request: ContributionPolicyUpdateDraftRequest) -> None:
    policy = ContributionPolicy(
        id=request.contribution_policy_id,
        project_id=str(request.project_id),
        name="Policy",
        status="draft",
        current_published_version_id=None,
        created_by=str(request.actor_profile_id),
    )
    version = ContributionPolicyVersion(
        id=request.contribution_policy_version_id,
        contribution_policy_id=request.contribution_policy_id,
        project_id=str(request.project_id),
        version_number=1,
        status="draft",
        created_by=str(request.actor_profile_id),
    )
    fixture.repository.get_policy.return_value = policy  # type: ignore[attr-defined]
    fixture.repository.get_version.return_value = version  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_update_draft_replaces_entire_rule_definition_graph() -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    install_draft(fixture, request)

    result = await fixture.service.update_draft(request)

    assert result.event_type == "draft_updated"
    call = fixture.repository.replace_graph.await_args
    assert len(call.args[1]) == 2
    assert len(call.args[2]) == 1
    assert len(fixture.authorization.closed) == 1


@pytest.mark.asyncio
async def test_update_draft_locks_exact_project_policy_version() -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    install_draft(fixture, request)

    await fixture.service.update_draft(request)

    fixture.repository.get_policy.assert_awaited_once_with(
        request.project_id, request.contribution_policy_id, for_update=True
    )
    fixture.repository.get_version.assert_any_await(
        request.project_id,
        request.contribution_policy_id,
        request.contribution_policy_version_id,
        for_update=True,
    )


@pytest.mark.asyncio
async def test_update_draft_rejects_non_uuid_required_version_selector() -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    object.__setattr__(request, "contribution_policy_version_id", "not-a-uuid")

    with pytest.raises(ContributionPolicyUnavailable):
        await fixture.service.update_draft(request)

    fixture.repository.lock_operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_conceals_cross_project_policy_before_authorization() -> None:
    fixture = service_fixture()
    request = update_request(fixture)

    with pytest.raises(ContributionPolicyConflict, match="not_found"):
        await fixture.service.update_draft(request)

    assert fixture.authorization.prepared == []
    fixture.repository.replace_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_rejects_retired_policy_before_authorization() -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    install_draft(fixture, request)
    fixture.repository.get_policy.return_value.status = "retired"

    with pytest.raises(ContributionPolicyConflict, match="not_found"):
        await fixture.service.update_draft(request)

    assert fixture.authorization.prepared == []
    assert fixture.authorization.consumed == []
    fixture.repository.replace_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_draft_denies_without_composed_authority() -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    install_draft(fixture, request)
    fixture.service._mutation_authorization = fixture.service.__class__(  # noqa: SLF001
        fixture.service._session  # noqa: SLF001
    )._mutation_authorization  # noqa: SLF001
    with pytest.raises(RuntimeError, match="contribution_policy_unavailable"):
        await fixture.service.update_draft(request)
    fixture.repository.replace_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_draft_leaves_no_stale_or_orphan_child() -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    install_draft(fixture, request)
    await fixture.service.update_draft(request)
    call = fixture.repository.replace_graph.await_args
    assert {rule.contribution_type for rule in call.args[1]} == {
        "accepted_submission",
        "completed_review",
    }


@pytest.mark.asyncio
async def test_invalid_compensation_mode_denies_before_authorization() -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    request = replace(
        request,
        rules=(
            replace(request.rules[0], compensation_mode="invalid"),  # type: ignore[arg-type]
            request.rules[1],
        ),
    )
    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.update_draft(request)
    assert fixture.authorization.prepared == []
    assert fixture.authorization.consumed == []
    fixture.repository.replace_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_noncanonical_instrument_denies_before_authorization() -> None:
    fixture = service_fixture()
    request = update_request(fixture)
    definition = replace(
        request.rules[0].definitions[0],
        instrument_type="money",  # type: ignore[arg-type]
    )
    request = replace(
        request,
        rules=(
            replace(request.rules[0], definitions=(definition,)),
            request.rules[1],
        ),
    )
    with pytest.raises(ContributionPolicyConflict):
        await fixture.service.update_draft(request)
    assert fixture.authorization.prepared == []
    assert fixture.authorization.consumed == []
    fixture.repository.replace_graph.assert_not_awaited()
