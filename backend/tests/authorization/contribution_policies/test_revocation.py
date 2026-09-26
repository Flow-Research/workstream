"""Production lifecycle revocation ordered against real policy authorization."""

from uuid import uuid4

import pytest

from app.modules.contributions.api import ContributionPolicyAuthorizationDenied
from tests.authorization.admin_access.concurrency_support import ordered_owner_calls
from .postgresql_support import world, snapshot


async def revoke(target, kind):
    """Use production grant, profile and identity-link lifecycle services via HTTP."""
    access = target.admin_access
    if kind == "grant":
        return await access.signed.revoke(access.admin, target.grant)
    path = (
        f"/api/v1/actors/{target.context.actor_profile_id}/suspend"
        if kind == "actor"
        else f"/api/v1/actor-identity-links/{target.context.identity_link_id}/revoke"
    )
    return await access.signed.client.post(
        path,
        headers=access.admin.headers | {"Idempotency-Key": str(uuid4())},
        json={"reason": "End assigned policy authority"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ("grant", "actor", "link"))
@pytest.mark.parametrize("first", ("policy", "revocation"))
async def test_policy_revocation_obeys_real_prepare_lock_order(
    admin_access, auth_database_env, monkeypatch, kind, first
):
    target = await world(admin_access)
    create = target.request("create_draft")
    prior = await target.execute("create_draft", create)
    request = target.request("update_draft", prior)

    async def mutate():
        try:
            return await target.execute("update_draft", request)
        except ContributionPolicyAuthorizationDenied:
            return "denied"

    async def disable():
        result = await revoke(target, kind)
        assert result.status_code == 200, result.text
        return result

    calls = (mutate, disable) if first == "policy" else (disable, mutate)
    a, b, observed = await ordered_owner_calls(
        *calls, boundary="control", database_url=auth_database_env, monkeypatch=monkeypatch
    )
    assert observed.observed
    if first == "policy":
        assert a.operation_id == request.operation_id
    else:
        assert b == "denied"
    before = await snapshot(target.project)
    assert await mutate() == "denied"
    with pytest.raises(ContributionPolicyAuthorizationDenied, match="^contribution_policy_unavailable$"):
        await target.execute("create_draft", create)
    assert await snapshot(target.project) == before
