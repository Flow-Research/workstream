"""Fail-closed PREP ordering for ContributionPolicy mutations."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.contributions.api import ContributionPolicyUnavailable
from tests.contributions.policy_test_support import create_request, service_fixture


async def _assert_consume_rejection(reason: str) -> None:
    fixture = service_fixture()

    async def deny(prepared: object, facts: object) -> object:
        del prepared, facts
        raise ContributionPolicyUnavailable(reason)

    fixture.authorization.consume_contribution_policy_mutation = deny
    with pytest.raises(ContributionPolicyUnavailable, match=reason):
        await fixture.service.create_draft(create_request(fixture))
    assert len(fixture.authorization.closed) == 1
    fixture.repository.add_policy_version_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrong_consumed_actor_creates_no_effect() -> None:
    fixture = service_fixture()
    fixture.authorization.actor_id = uuid4()

    with pytest.raises(ContributionPolicyUnavailable):
        await fixture.service.create_draft(create_request(fixture))

    assert len(fixture.authorization.closed) == 1
    fixture.repository.add_policy_version_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_exception_creates_no_effect() -> None:
    await _assert_consume_rejection("consume_exception")


@pytest.mark.asyncio
async def test_close_failure_rolls_back_staged_authorization_evidence_before_product_effect() -> (
    None
):
    fixture = service_fixture()

    def fail(prepared: object) -> None:
        del prepared
        raise ContributionPolicyUnavailable("close_failed")

    fixture.authorization.close_contribution_policy_mutation = fail
    with pytest.raises(ContributionPolicyUnavailable, match="close_failed"):
        await fixture.service.create_draft(create_request(fixture))

    fixture.repository.add_policy_version_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepared_authority_closes_once_on_success() -> None:
    fixture = service_fixture()
    await fixture.service.create_draft(create_request(fixture))
    assert len(fixture.authorization.closed) == 1


@pytest.mark.asyncio
async def test_operation_fence_precedes_owner_locks_and_authorization() -> None:
    fixture = service_fixture()
    order: list[str] = []

    async def operation_lock(operation_id: object) -> None:
        del operation_id
        order.append("operation")

    async def owner_lock(project_id: object) -> object:
        order.append("owner")
        return SimpleNamespace(project_id=project_id)

    async def project_scope(project_id: object) -> None:
        del project_id
        order.append("project_scope")

    async def prepare(facts: object) -> object:
        del facts
        order.append("authorization")
        return object()

    fixture.repository.lock_operation.side_effect = operation_lock
    fixture.service._projects.lock_contribution_policy_project = owner_lock  # noqa: SLF001
    fixture.repository.lock_project_scope.side_effect = project_scope
    fixture.authorization.prepare_contribution_policy_mutation = prepare
    await fixture.service.create_draft(create_request(fixture))
    assert order == ["operation", "owner", "project_scope", "authorization"]


@pytest.mark.asyncio
async def test_prepare_denial_creates_no_effect() -> None:
    fixture = service_fixture()

    async def deny(facts: object) -> object:
        del facts
        raise ContributionPolicyUnavailable("denied")

    fixture.authorization.prepare_contribution_policy_mutation = deny
    with pytest.raises(ContributionPolicyUnavailable):
        await fixture.service.create_draft(create_request(fixture))
    fixture.repository.add_policy_version_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_exception_creates_no_effect() -> None:
    fixture = service_fixture()

    async def fail(facts: object) -> object:
        del facts
        raise RuntimeError("prepare_exception")

    fixture.authorization.prepare_contribution_policy_mutation = fail
    with pytest.raises(RuntimeError, match="prepare_exception"):
        await fixture.service.create_draft(create_request(fixture))
    fixture.repository.add_policy_version_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_denial_creates_no_effect() -> None:
    await _assert_consume_rejection("consume_denied")


@pytest.mark.asyncio
async def test_prepared_authority_closes_once_after_port_rejection() -> None:
    await _assert_consume_rejection("port_rejected")
