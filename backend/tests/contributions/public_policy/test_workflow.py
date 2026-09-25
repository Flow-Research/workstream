"""Signed Finance workflows, recovery, and immutable operation replay."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.modules.contributions.models import ContributionPolicy, ContributionPolicyLifecycleEvent
from app.modules.tasks.models import AuditEvent
from tests.authorization.contribution_policies.postgresql_support import snapshot
from .support import UNPAID, draft, mutate, path, published, world


@pytest.mark.parametrize("scope", ("project", "system"))
async def test_public_policy_lifecycle(admin_access, scope):
    target, receipt = await draft(admin_access, scope=scope)
    root = path(target.project)
    client, actor = admin_access.signed.client, admin_access.target
    current = await client.get(root + "/current", headers=actor.headers)
    assert current.status_code == 200, current.text
    assert current.json() == {
        "project_id": str(target.project), "contribution_policy_id": receipt["contribution_policy_id"],
        "current_published_version_id": None, "open_draft_version_id": receipt["contribution_policy_version_id"],
    }
    updated = await mutate(admin_access, actor, "PUT", path(target.project, receipt), UNPAID)
    assert updated.status_code == 200, updated.text
    approved = await mutate(admin_access, actor, "POST", path(target.project, receipt) + "/publication", {})
    assert approved.status_code == 200, approved.text
    exact = root + "/" + receipt["contribution_policy_id"]
    view = await client.get(exact, headers=actor.headers)
    assert view.status_code == 200, view.text
    assert view.json()["version_status"] == "published"
    assert view.json()["contribution_policy_version_id"] == receipt["contribution_policy_version_id"]
    assert {r["contribution_type"] for r in view.json()["rules"]} == {"accepted_submission", "completed_review"}
    assert all(r["compensation_mode"] == "unpaid" and r["definitions"] == [] for r in view.json()["rules"])
    retired = await mutate(admin_access, actor, "POST", path(target.project, receipt) + "/retirement", {})
    assert retired.status_code == 200, retired.text
    assert (await client.get(root + "/current", headers=actor.headers)).status_code == 404
    historical = await client.get(exact, params={"version_id": receipt["contribution_policy_version_id"]}, headers=actor.headers)
    assert historical.status_code == 200, historical.text
    assert historical.json()["version_status"] == "retired"
    async with db_session.get_session_factory()() as session:
        events = (await session.scalars(select(AuditEvent).where(
            AuditEvent.project_id == str(target.project), AuditEvent.action_id.like("contribution.policy.%"),
        ))).all()
        assert {e.action_id for e in events} == {"contribution.policy." + op for op in (
            "read", "create_draft", "update_draft", "publish", "retire",
        )}
        assert all(e.matched_grant_id == target.grant for e in events)


async def test_second_finance_recovers_draft(admin_access):
    target, created = await draft(admin_access)
    second = await admin_access.signed.actor("replacement-finance")
    grant = await admin_access.signed.grant(admin_access.admin, second, role="finance_authority", project_id=target.project)
    revoked = await admin_access.signed.revoke(admin_access.admin, target.grant)
    assert revoked.status_code == 200, revoked.text
    root = path(target.project)
    assert (await admin_access.signed.client.get(root + "/current", headers=admin_access.target.headers)).status_code == 404
    # B uses only the project URL, not A's response or replay key.
    discovered = await admin_access.signed.client.get(root + "/current", headers=second.headers)
    assert discovered.status_code == 200, discovered.text
    selection = discovered.json()
    url = root + f"/{selection['contribution_policy_id']}/versions/{selection['open_draft_version_id']}"
    edited = await mutate(admin_access, second, "PUT", url, UNPAID)
    assert edited.status_code == 200, edited.text
    approved = await mutate(admin_access, second, "POST", url + "/publication", {})
    assert approved.status_code == 200, approved.text
    async with db_session.get_session_factory()() as session:
        policy = await session.get(ContributionPolicy, UUID(selection["contribution_policy_id"]))
        assert policy.created_by == str(admin_access.target.id)
        events = (await session.scalars(select(ContributionPolicyLifecycleEvent).where(
            ContributionPolicyLifecycleEvent.contribution_policy_id == policy.id,
        ))).all()
        assert {e.actor_profile_id for e in events if e.event_type != "draft_created"} == {str(second.id)}
        decisions = (await session.scalars(select(AuditEvent).where(
            AuditEvent.project_id == str(target.project), AuditEvent.actor_id == str(second.id),
            AuditEvent.action_id.like("contribution.policy.%"),
        ))).all()
        assert decisions and all(e.matched_grant_id == grant for e in decisions)
        assert str(policy.id) == created["contribution_policy_id"]


async def test_policy_replay_after_publication(admin_access):
    target = await world(admin_access)
    key = uuid4()
    root = path(target.project)
    created = await mutate(admin_access, admin_access.target, "POST", root + "/drafts", {"name": "Replay policy"}, key=key)
    assert created.status_code == 201, created.text
    receipt = created.json()
    edited = await mutate(admin_access, admin_access.target, "PUT", path(target.project, receipt), UNPAID)
    assert edited.status_code == 200, edited.text
    approved = await mutate(admin_access, admin_access.target, "POST", path(target.project, receipt) + "/publication", {})
    assert approved.status_code == 200, approved.text
    before = await snapshot(target.project)
    replayed = await mutate(admin_access, admin_access.target, "POST", root + "/drafts", {"name": "Replay policy"}, key=key)
    assert replayed.status_code == 201 and replayed.json() == receipt, replayed.text
    after = await snapshot(target.project)
    assert {k: v for k, v in before.items() if k != "authority"} == {k: v for k, v in after.items() if k != "authority"}


@pytest.mark.parametrize("changed", ("actor", "project", "body"))
async def test_policy_replay_conflicts(admin_access, changed):
    target = await world(admin_access)
    key = uuid4()
    body = {"name": "Original policy"}
    url = path(target.project) + "/drafts"
    original = await mutate(admin_access, admin_access.target, "POST", url, body, key=key)
    assert original.status_code == 201, original.text
    actor, other_url, other_body = admin_access.target, url, body
    if changed == "actor":
        actor = await admin_access.signed.actor("other-authorized-finance")
        await admin_access.signed.grant(admin_access.admin, actor, role="finance_authority", project_id=target.project)
    elif changed == "project":
        other = await world(admin_access)
        other_url = path(other.project) + "/drafts"
    else:
        other_body = {"name": "Different policy"}
    response = await mutate(admin_access, actor, "POST", other_url, other_body, key=key)
    assert response.status_code == 409, response.text
    replay = await mutate(admin_access, admin_access.target, "POST", url, body, key=key)
    assert replay.status_code == 201 and replay.json() == original.json()


async def test_new_operation_rejects_stale_version(admin_access):
    target, first = await published(admin_access)
    second = await mutate(admin_access, admin_access.target, "POST", path(target.project) + "/drafts", {"name": "Next version"})
    assert second.status_code == 201, second.text
    before = await snapshot(target.project)
    response = await mutate(admin_access, admin_access.target, "PUT", path(target.project, first), UNPAID)
    assert response.status_code == 404, response.text
    assert await snapshot(target.project) == before


async def test_public_policy_denials(admin_access):
    from dataclasses import replace
    from tests.authorization.task_queues.support import grant_queue_role
    target, receipt = await draft(admin_access)
    foreign = await world(admin_access)
    for role in ("project_manager", "operator", "submitter", "foreign_finance"):
        actor = await admin_access.signed.actor("policy-denied-" + role)
        if role == "submitter":
            await grant_queue_role(replace(admin_access, target=actor), target.project, role)
        else:
            await admin_access.signed.grant(admin_access.admin, actor,
                role="finance_authority" if role == "foreign_finance" else role,
                project_id=None if role == "operator" else foreign.project if role == "foreign_finance" else target.project)
        for url in (path(target.project) + "/current", path(target.project) + "/" + receipt["contribution_policy_id"]):
            response = await admin_access.signed.client.get(url, headers=actor.headers)
            assert response.status_code == 404, (role, response.text)
        response = await mutate(admin_access, actor, "PUT", path(target.project, receipt), UNPAID)
        assert response.status_code == 404, (role, response.text)
    assert (await mutate(admin_access, admin_access.target, "PUT", path(target.project, receipt), UNPAID)).status_code == 200


@pytest.mark.parametrize("kind", ("grant", "profile", "link"))
async def test_public_policy_revocation(admin_access, kind):
    from app.modules.actors.models import ActorIdentityLink, ActorProfile
    target, receipt = await draft(admin_access)
    actor = admin_access.target
    async with db_session.get_session_factory()() as session:
        profile = await session.get(ActorProfile, str(actor.id))
        link = await session.scalar(select(ActorIdentityLink).where(ActorIdentityLink.actor_profile_id == str(actor.id)))
        assert profile.status == link.status == "active"
        link_id = link.id
    current = path(target.project) + "/current"
    assert (await admin_access.signed.client.get(current, headers=actor.headers)).status_code == 200
    if kind == "grant":
        revoked = await admin_access.signed.revoke(admin_access.admin, target.grant)
    else:
        url = f"/api/v1/actors/{actor.id}/suspend" if kind == "profile" else f"/api/v1/actor-identity-links/{link_id}/revoke"
        revoked = await mutate(admin_access, admin_access.admin, "POST", url, {"reason": "Withdraw policy access"})
    assert revoked.status_code == 200, revoked.text
    assert (await admin_access.signed.client.get(current, headers=actor.headers)).status_code == 404
    response = await mutate(admin_access, actor, "PUT", path(target.project, receipt), UNPAID)
    assert response.status_code == 404, response.text
    if kind == "grant":
        replacement = await admin_access.signed.grant(admin_access.admin, actor, role="finance_authority", project_id=target.project)
        assert replacement != target.grant
    else:
        url = f"/api/v1/actors/{actor.id}/reactivate" if kind == "profile" else f"/api/v1/actor-identity-links/{link_id}/reactivate"
        restored = await mutate(admin_access, admin_access.admin, "POST", url, {"reason": "Restore policy access"})
        assert restored.status_code == 200, restored.text
    assert (await admin_access.signed.client.get(current, headers=actor.headers)).status_code == 200
    assert (await mutate(admin_access, actor, "PUT", path(target.project, receipt), UNPAID)).status_code == 200


@pytest.mark.parametrize("invalid", ("rules", "foreign", "capability", "suspended"))
async def test_invalid_policy_graph(admin_access, monkeypatch, invalid):
    from copy import deepcopy
    from app.adapters.auth import compensation_adapter_binding_authorization
    from app.modules.compensation.api import AdapterBindingSuspendRequest, PolicyAdapterBindingUnavailable
    from app.modules.compensation.models import ProjectCompensationAdapterBinding
    from app.modules.compensation.policy_binding_service import PolicyAdapterBindingLookup
    from app.modules.compensation.service import AdapterBindingService
    from tests.authorization.contribution_policies.postgresql_support import world as compensated_world
    target = await compensated_world(admin_access)
    created = await mutate(admin_access, admin_access.target, "POST", path(target.project) + "/drafts", {"name": "Compensated policy"})
    assert created.status_code == 201, created.text
    url = path(target.project, created.json())
    valid = deepcopy(UNPAID)
    valid["rules"][0].update(compensation_mode="compensated", definitions=[{
        "instrument_type": "money", "unit_code": "USD", "quantity": "2", "adapter_binding_id": str(target.binding),
    }])
    positive = await mutate(admin_access, admin_access.target, "PUT", url, valid)
    assert positive.status_code == 200, positive.text
    bad = deepcopy(valid)
    if invalid == "rules":
        bad["rules"][1] = deepcopy(bad["rules"][0])
    elif invalid == "foreign":
        from tests.authorization.contribution_policies.foreign_fixtures import foreign_project
        _, foreign_binding = await foreign_project(target, with_binding=True)
        bad["rules"][0]["definitions"][0]["adapter_binding_id"] = str(foreign_binding)
    elif invalid == "capability":
        async with db_session.get_session_factory()() as session:
            binding = await session.scalar(select(ProjectCompensationAdapterBinding).where(
                ProjectCompensationAdapterBinding.project_id == str(target.project),
                ProjectCompensationAdapterBinding.instrument_type == "project_points"))
            assert binding.status == "active"
            bad["rules"][0]["definitions"][0]["adapter_binding_id"] = str(binding.id)
    else:
        async with db_session.get_session_factory()() as session, session.begin():
            authority = compensation_adapter_binding_authorization(session, target.context)
            await AdapterBindingService(session, read_authorization=authority, mutation_authorization=authority).suspend(
                AdapterBindingSuspendRequest(operation_id=uuid4(), actor_profile_id=admin_access.target.id,
                    project_id=target.project, adapter_binding_id=target.binding, expected_lifecycle_version=1))
    before = await snapshot(target.project)
    observed = []
    original = PolicyAdapterBindingLookup.lock_policy_adapter_binding
    async def observe(lookup, **kwargs):
        try:
            return await original(lookup, **kwargs)
        except PolicyAdapterBindingUnavailable:
            observed.append(kwargs)
            raise
    with monkeypatch.context() as patch:
        patch.setattr(PolicyAdapterBindingLookup, "lock_policy_adapter_binding", observe)
        rejected = await mutate(admin_access, admin_access.target, "PUT", url, bad)
    assert rejected.status_code == (409 if invalid == "rules" else 404), rejected.text
    assert len(observed) == (0 if invalid == "rules" else 1)
    if observed:
        assert observed[0]["project_id"] == target.project
        assert str(observed[0]["adapter_binding_id"]) == bad["rules"][0]["definitions"][0]["adapter_binding_id"]
    assert await snapshot(target.project) == before
