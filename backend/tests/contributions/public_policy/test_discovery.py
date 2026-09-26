"""Current discovery never locks before AUTH or discloses a replacement aggregate."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import delete, event

from app.adapters.auth.contribution_policies import ContributionPolicyAuthorization
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.contributions.models import ContributionPolicy, ContributionPolicyVersion
from app.modules.contributions.repository import ContributionPolicyRepository
from .support import UNPAID, draft, mutate, path, published, world


async def test_current_selectors(admin_access):
    target, approved = await published(admin_access)
    response = await mutate(admin_access, admin_access.target, "POST", path(target.project) + "/drafts", {"name": "Next draft"})
    assert response.status_code == 201, response.text
    read = await admin_access.signed.client.get(path(target.project) + "/current", headers=admin_access.target.headers)
    assert read.status_code == 200, read.text
    assert read.json() == {
        "project_id": str(target.project), "contribution_policy_id": approved["contribution_policy_id"],
        "current_published_version_id": approved["contribution_policy_version_id"],
        "open_draft_version_id": response.json()["contribution_policy_version_id"],
    }


async def discovery_race(access, monkeypatch, *, replace):
    target, approved = await published(access)
    second = await access.signed.actor("concurrent-finance")
    await access.signed.grant(access.admin, second, role="finance_authority", project_id=target.project)
    selected, proceed = asyncio.Event(), asyncio.Event()
    original = ContributionPolicyRepository.current_policy_candidates
    async def pause(repository, project_id):
        result = await original(repository, project_id)
        selected.set()
        await proceed.wait()
        return result
    with monkeypatch.context() as patch:
        patch.setattr(ContributionPolicyRepository, "current_policy_candidates", pause)
        pending = asyncio.create_task(access.signed.client.get(path(target.project) + "/current", headers=access.target.headers))
        try:
            await asyncio.wait_for(selected.wait(), 10)
            if replace:
                retired = await mutate(access, second, "POST", path(target.project, approved) + "/retirement", {})
                assert retired.status_code == 200, retired.text
            created = await mutate(access, second, "POST", path(target.project) + "/drafts", {"name": "New draft"})
            assert created.status_code == 201, created.text
        finally:
            proceed.set()
            result = await asyncio.wait_for(pending, 10)
    return target, approved, created.json(), result


async def test_discovery_rechecks_after_authorization(admin_access, monkeypatch):
    target, original, replacement, response = await discovery_race(admin_access, monkeypatch, replace=True)
    assert replacement["contribution_policy_id"] != original["contribution_policy_id"]
    assert response.status_code == 404, response.text
    fresh = await admin_access.signed.client.get(path(target.project) + "/current", headers=admin_access.target.headers)
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["contribution_policy_id"] == replacement["contribution_policy_id"]


async def test_discovery_refreshes_same_policy(admin_access, monkeypatch):
    _, original, replacement, response = await discovery_race(admin_access, monkeypatch, replace=False)
    assert replacement["contribution_policy_id"] == original["contribution_policy_id"]
    assert response.status_code == 200, response.text
    assert response.json()["current_published_version_id"] == original["contribution_policy_version_id"]
    assert response.json()["open_draft_version_id"] == replacement["contribution_policy_version_id"]


async def test_ambiguous_current_policy_is_concealed(admin_access):
    target, receipt = await draft(admin_access)
    factory = db_session.get_session_factory()
    duplicate = new_record_id()
    async with factory() as session, session.begin():
        session.add(ContributionPolicy(id=duplicate, project_id=str(target.project), name="Faulty duplicate",
            status="draft", created_by=str(admin_access.target.id)))
    response = await admin_access.signed.client.get(path(target.project) + "/current", headers=admin_access.target.headers)
    assert response.status_code == 404, response.text
    # Remove only the intentionally corrupt isolated-test row, with no lifecycle evidence.
    async with factory() as session, session.begin():
        await session.execute(delete(ContributionPolicy).where(ContributionPolicy.id == duplicate))
    positive = await admin_access.signed.client.get(path(target.project) + "/current", headers=admin_access.target.headers)
    assert positive.status_code == 200 and positive.json()["contribution_policy_id"] == receipt["contribution_policy_id"]


async def test_discovery_does_not_take_product_locks(admin_access, monkeypatch):
    target, receipt = await draft(admin_access)
    factory = db_session.get_session_factory()
    engine = factory.kw["bind"].sync_engine
    statements, observed = [], []
    def sql(connection, cursor, statement, parameters, context, many):
        if "contribution_policies" in statement.lower():
            statements.append(statement.lower())
    original = ContributionPolicyAuthorization.authorize_contribution_policy_read
    async def inspect(authority, request):
        assert len(statements) == 1
        assert "for update" not in statements[0] and "current_published_version_id" not in statements[0]
        assert "contribution_policies.id" in statements[0]
        observed.append(True)
        return await original(authority, request)
    async with factory() as holder, holder.begin():
        await holder.get(ContributionPolicy, UUID(receipt["contribution_policy_id"]), with_for_update=True)
        event.listen(engine, "before_cursor_execute", sql)
        monkeypatch.setattr(ContributionPolicyAuthorization, "authorize_contribution_policy_read", inspect)
        try:
            response = await asyncio.wait_for(admin_access.signed.client.get(path(target.project) + "/current", headers=admin_access.target.headers), 10)
        finally:
            event.remove(engine, "before_cursor_execute", sql)
    assert response.status_code == 200 and observed == [True], response.text
    assert all("for update" not in statement for statement in statements)


@pytest.mark.parametrize("operation", ("read", "update", "publish", "retire"))
async def test_foreign_policy_selector_does_not_wait(admin_access, operation):
    foreign, receipt = await published(admin_access) if operation in {"read", "retire"} else await draft(admin_access)
    if operation == "publish":
        updated = await mutate(admin_access, admin_access.target, "PUT", path(foreign.project, receipt), UNPAID)
        assert updated.status_code == 200, updated.text
    requested = await world(admin_access)
    suffix = {"update": "", "publish": "/publication", "retire": "/retirement"}.get(operation, "")
    async def request(project):
        if operation == "read":
            return await admin_access.signed.client.get(path(project) + "/" + receipt["contribution_policy_id"], headers=admin_access.target.headers)
        return await mutate(admin_access, admin_access.target, "PUT" if operation == "update" else "POST",
                            path(project, receipt) + suffix, UNPAID if operation == "update" else {})
    async with db_session.get_session_factory()() as holder, holder.begin():
        await holder.get(ContributionPolicy, UUID(receipt["contribution_policy_id"]), with_for_update=True)
        await holder.get(ContributionPolicyVersion, UUID(receipt["contribution_policy_version_id"]), with_for_update=True)
        response = await asyncio.wait_for(request(requested.project), 10)
        assert response.status_code == 404, response.text
    positive = await request(foreign.project)
    assert positive.status_code == 200, positive.text
