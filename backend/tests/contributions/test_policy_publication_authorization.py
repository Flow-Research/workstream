"""Fail-closed opaque authorization ordering for policy publication."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.modules.contributions.api import (
    ContributionPolicyConflict,
    ContributionPolicyRetireRequest,
    ContributionPolicyUnavailable,
)
from app.modules.contributions.models import ContributionPolicy, ContributionPolicyVersion
from tests.contributions.policy_test_support import service_fixture
from tests.contributions.test_policy_publish import _install_complete_draft, _request


def _install_active_policy(fixture):
    policy_id, version_id = uuid4(), uuid4()
    request = ContributionPolicyRetireRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=policy_id,
        contribution_policy_version_id=version_id,
    )
    policy = ContributionPolicy(
        id=policy_id,
        project_id=str(fixture.project_id),
        name="Policy",
        status="active",
        current_published_version_id=version_id,
        created_by=str(fixture.actor_id),
    )
    version = ContributionPolicyVersion(
        id=version_id,
        contribution_policy_id=policy_id,
        project_id=str(fixture.project_id),
        version_number=1,
        status="published",
        created_by=str(fixture.actor_id),
        published_by=str(fixture.actor_id),
        published_at=datetime.now(UTC),
    )
    fixture.repository.get_policy.return_value = policy
    fixture.repository.get_version.return_value = version
    return request, policy, version


class _FailureAuthorization:
    def __init__(self, actor, *, phase: str) -> None:
        self.actor = actor
        self.phase = phase
        self.closed = 0

    async def prepare_contribution_policy_mutation(self, facts):
        if self.phase == "prepare":
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
        return object()

    async def consume_contribution_policy_mutation(self, prepared, facts):
        del prepared, facts
        if self.phase == "consume":
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")
        return uuid4() if self.phase == "actor" else self.actor

    def close_contribution_policy_mutation(self, prepared) -> None:
        del prepared
        self.closed += 1
        if self.phase == "close":
            raise ContributionPolicyUnavailable("contribution_policy_unavailable")


async def _assert_failure_has_no_effect(phase: str) -> _FailureAuthorization:
    fixture = service_fixture()
    request = _request(fixture)
    policy, version = _install_complete_draft(fixture, request)
    authorization = _FailureAuthorization(fixture.actor_id, phase=phase)
    fixture.service._publication._mutation_authorization = authorization  # noqa: SLF001
    with pytest.raises(ContributionPolicyUnavailable):
        await fixture.service.publish(request)
    assert policy.status == "draft" and version.status == "draft"
    fixture.repository.create_transition_custody.assert_not_awaited()
    fixture.repository.flush_transition_event.assert_not_awaited()
    return authorization


@pytest.mark.asyncio
async def test_publish_prepare_denial_has_no_product_effect() -> None:
    authorization = await _assert_failure_has_no_effect("prepare")
    assert authorization.closed == 0


@pytest.mark.asyncio
async def test_publish_denies_without_composed_authority() -> None:
    fixture = service_fixture(use_default_mutation_authority=True)
    request = _request(fixture)
    policy, version = _install_complete_draft(fixture, request)
    prior_policy_status = policy.status
    prior_selected_version = policy.current_published_version_id
    with pytest.raises(
        ContributionPolicyUnavailable, match="^contribution_policy_unavailable$"
    ):
        await fixture.service.publish(request)
    assert policy.status == prior_policy_status
    assert policy.current_published_version_id == prior_selected_version
    assert version.status == "draft"
    fixture.repository.create_transition_custody.assert_not_awaited()
    fixture.repository.flush_transition_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_consume_exception_has_no_product_effect() -> None:
    authorization = await _assert_failure_has_no_effect("consume")
    assert authorization.closed == 1


@pytest.mark.asyncio
async def test_publish_wrong_consumed_actor_has_no_product_effect() -> None:
    authorization = await _assert_failure_has_no_effect("actor")
    assert authorization.closed == 1


@pytest.mark.asyncio
async def test_publish_close_failure_has_no_product_effect() -> None:
    authorization = await _assert_failure_has_no_effect("close")
    assert authorization.closed == 1


@pytest.mark.asyncio
async def test_publish_closes_prepared_authority_exactly_once() -> None:
    fixture = service_fixture()
    request = _request(fixture)
    _install_complete_draft(fixture, request)
    await fixture.service.publish(request)
    assert len(fixture.authorization.closed) == 1


@pytest.mark.asyncio
async def test_publish_consume_observes_no_staged_product_state() -> None:
    fixture = service_fixture()
    request = _request(fixture)
    policy, version = _install_complete_draft(fixture, request)

    async def consume(prepared, facts):
        del prepared, facts
        assert policy.status == "draft" and version.status == "draft"
        fixture.repository.create_transition_custody.assert_not_awaited()
        return fixture.actor_id

    fixture.authorization.consume_contribution_policy_mutation = consume
    await fixture.service.publish(request)


@pytest.mark.asyncio
async def test_cross_project_policy_publish_is_concealed_without_effect() -> None:
    fixture = service_fixture()
    request = _request(fixture)
    fixture.repository.get_policy.return_value = None
    with pytest.raises(ContributionPolicyConflict, match="not_found"):
        await fixture.service.publish(request)
    assert fixture.authorization.prepared == []


@pytest.mark.asyncio
async def test_cross_project_version_publish_is_concealed_without_effect() -> None:
    fixture = service_fixture()
    request = _request(fixture)
    policy, _ = _install_complete_draft(fixture, request)
    fixture.repository.get_policy.return_value = policy
    fixture.repository.get_version.return_value = None
    with pytest.raises(ContributionPolicyConflict, match="not_found"):
        await fixture.service.publish(request)
    assert fixture.authorization.prepared == []


@pytest.mark.asyncio
async def test_cross_project_unit_publish_is_concealed_without_effect() -> None:
    fixture = service_fixture()
    request = _request(fixture)
    _install_complete_draft(fixture, request)
    fixture.repository.lock_unit.return_value = None
    with pytest.raises(ContributionPolicyConflict, match="not_found"):
        await fixture.service.publish(request)
    assert fixture.authorization.prepared == []


@pytest.mark.asyncio
async def test_cross_project_binding_publish_is_concealed_without_effect() -> None:
    fixture = service_fixture()
    request = _request(fixture)
    _install_complete_draft(fixture, request)
    original = fixture.service._bindings.lock_policy_adapter_binding  # noqa: SLF001

    async def wrong_binding(**kwargs):
        result = await original(**kwargs)
        return type(result)(
            project_id=uuid4(),
            adapter_binding_id=result.adapter_binding_id,
            instrument_type=result.instrument_type,
            binding_lifecycle_version=1,
        )

    fixture.service._publication._bindings.lock_policy_adapter_binding = wrong_binding  # type: ignore[method-assign]  # noqa: SLF001
    with pytest.raises(ContributionPolicyConflict, match="not_found"):
        await fixture.service.publish(request)
    assert fixture.authorization.prepared == []


@pytest.mark.asyncio
async def test_retire_denies_without_composed_authority() -> None:
    fixture = service_fixture(use_default_mutation_authority=True)
    request, policy, version = _install_active_policy(fixture)
    with pytest.raises(
        ContributionPolicyUnavailable, match="^contribution_policy_unavailable$"
    ):
        await fixture.service.retire(request)
    assert policy.status == "active"
    assert policy.current_published_version_id == version.id
    assert version.status == "published"
    fixture.repository.create_transition_custody.assert_not_awaited()
    fixture.repository.flush_transition_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_retire_closes_prepared_authority_exactly_once() -> None:
    fixture = service_fixture()
    request, _, _ = _install_active_policy(fixture)
    await fixture.service.retire(request)
    assert len(fixture.authorization.closed) == 1


@pytest.mark.asyncio
async def test_retire_consume_observes_no_staged_product_state() -> None:
    fixture = service_fixture()
    request, policy, version = _install_active_policy(fixture)

    async def consume(prepared, facts):
        del prepared, facts
        assert policy.status == "active" and version.status == "published"
        fixture.repository.create_transition_custody.assert_not_awaited()
        return fixture.actor_id

    fixture.authorization.consume_contribution_policy_mutation = consume
    await fixture.service.retire(request)


@pytest.mark.asyncio
async def test_cross_project_policy_retire_is_concealed_without_effect() -> None:
    fixture = service_fixture()
    from app.modules.contributions.api import ContributionPolicyRetireRequest

    request = ContributionPolicyRetireRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=uuid4(),
        contribution_policy_version_id=uuid4(),
    )
    fixture.repository.get_policy.return_value = None
    with pytest.raises(ContributionPolicyConflict, match="not_found"):
        await fixture.service.retire(request)
    assert fixture.authorization.prepared == []


@pytest.mark.asyncio
async def test_cross_project_current_version_retire_is_concealed_without_effect() -> None:
    fixture = service_fixture()
    from app.modules.contributions.api import ContributionPolicyRetireRequest

    policy_id, version_id = uuid4(), uuid4()
    request = ContributionPolicyRetireRequest(
        operation_id=uuid4(),
        actor_profile_id=fixture.actor_id,
        project_id=fixture.project_id,
        contribution_policy_id=policy_id,
        contribution_policy_version_id=version_id,
    )
    fixture.repository.get_policy.return_value = ContributionPolicy(
        id=policy_id,
        project_id=str(fixture.project_id),
        name="Policy",
        status="active",
        current_published_version_id=uuid4(),
        created_by=str(fixture.actor_id),
    )
    fixture.repository.get_version.return_value = ContributionPolicyVersion(
        id=version_id,
        contribution_policy_id=policy_id,
        project_id=str(fixture.project_id),
        version_number=1,
        status="published",
        created_by=str(fixture.actor_id),
        published_by=str(fixture.actor_id),
        published_at=datetime.now(UTC),
    )
    with pytest.raises(ContributionPolicyConflict, match="not_found"):
        await fixture.service.retire(request)
    assert fixture.authorization.prepared == []


@pytest.mark.asyncio
async def test_post_close_database_failure_rolls_back_all_effects() -> None:
    fixture = service_fixture()
    request = _request(fixture)
    policy, version = _install_complete_draft(fixture, request)
    fixture.repository.create_transition_custody.side_effect = RuntimeError("late_database")
    with pytest.raises(RuntimeError, match="late_database"):
        await fixture.service.publish(request)
    assert len(fixture.authorization.closed) == 1
    assert policy.status == "draft" and version.status == "draft"


@pytest.mark.asyncio
async def test_closed_publication_authority_cannot_be_reused() -> None:
    fixture = service_fixture()
    request = _request(fixture)
    _install_complete_draft(fixture, request)
    await fixture.service.publish(request)
    assert fixture.authorization.prepared_handles == fixture.authorization.consumed_handles
    assert fixture.authorization.closed == fixture.authorization.prepared_handles
    assert len({id(item) for item in fixture.authorization.closed}) == 1
