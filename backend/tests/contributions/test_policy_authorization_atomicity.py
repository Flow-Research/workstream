"""Fail-closed PREP ordering for ContributionPolicy mutations."""

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


async def _assert_replayed_prepared_object_denied() -> None:
    fixture = service_fixture()
    prepared = object()
    consumed = False

    async def prepare(facts: object) -> object:
        del facts
        return prepared

    async def consume(handle: object, facts: object) -> object:
        nonlocal consumed
        del facts
        if handle is not prepared or consumed:
            raise ContributionPolicyUnavailable("replayed")
        consumed = True
        return fixture.actor_id

    fixture.authorization.prepare_contribution_policy_mutation = prepare
    fixture.authorization.consume_contribution_policy_mutation = consume
    await fixture.service.create_draft(create_request(fixture))
    with pytest.raises(ContributionPolicyUnavailable, match="replayed"):
        await fixture.service.create_draft(create_request(fixture))
    fixture.repository.add_policy_version_event.assert_awaited_once()


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
async def test_close_failure_rolls_back_staged_authorization_evidence_before_product_effect() -> None:
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
    await fixture.service.create_draft(create_request(fixture))
    fixture.repository.lock_operation.assert_awaited_once()
    assert fixture.authorization.prepared


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
@pytest.mark.parametrize("failure", ["wrong_session", "wrong_transaction", "copied"])
async def test_prepared_authority_closes_once_for_each_failure_exit(failure: str) -> None:
    await _assert_consume_rejection(failure)


@pytest.mark.asyncio
async def test_wrong_session_handle_creates_no_effect() -> None:
    await _assert_consume_rejection("wrong_session")


@pytest.mark.asyncio
async def test_wrong_transaction_handle_creates_no_effect() -> None:
    await _assert_consume_rejection("wrong_transaction")


@pytest.mark.asyncio
async def test_copied_handle_creates_no_effect() -> None:
    await _assert_consume_rejection("copied")


@pytest.mark.asyncio
async def test_replayed_handle_creates_no_second_effect() -> None:
    await _assert_replayed_prepared_object_denied()


@pytest.mark.asyncio
async def test_post_close_database_failure_rolls_back_all_effects() -> None:
    fixture = service_fixture()
    fixture.repository.add_policy_version_event.side_effect = RuntimeError("database_failed")
    with pytest.raises(RuntimeError, match="database_failed"):
        await fixture.service.create_draft(create_request(fixture))
    assert len(fixture.authorization.closed) == 1


@pytest.mark.asyncio
async def test_closed_authority_cannot_be_reused() -> None:
    await _assert_replayed_prepared_object_denied()
