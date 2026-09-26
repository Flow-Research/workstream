"""HTTP response and real audit storage failures preserve caller atomicity."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError
from pydantic_core import PydanticSerializationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.api.deps import contribution_policies as dependency
from app.api.routes import contribution_policies as routes
from app.db import session as db_session
from app.modules.audit.service import AuditService
from app.modules.contributions.models import ContributionPolicyLifecycleEvent
from app.modules.projects.models import Project
from app.modules.tasks.models import AuditEvent
from tests.authorization.contribution_policies.postgresql_support import snapshot
from .support import UNPAID, draft, mutate, path, published, world


@pytest.mark.parametrize("failure", ("validation", "serialization"))
async def test_response_failure_rolls_back(admin_access, monkeypatch, failure):
    target = await world(admin_access)
    key, observed, failures = uuid4(), [], []
    before = await snapshot(target.project)
    original = routes.commit_policy_response
    async def inspect(request, response, response_type):
        events = (await request.session.scalars(select(ContributionPolicyLifecycleEvent).where(
            ContributionPolicyLifecycleEvent.operation_id == key))).all()
        decisions = (await request.session.scalars(select(AuditEvent).where(
            AuditEvent.project_id == str(target.project), AuditEvent.action_id == "contribution.policy.create_draft"))).all()
        assert len(events) == len(decisions) == 1
        assert decisions[0].after_facts["allowed"] is True
        assert await snapshot(target.project) == before
        observed.append(True)
        adapter = TypeAdapter(response_type)
        def dump(value, **kwargs):
            if failure == "serialization":
                value = replace(value, contribution_policy_id=object())
            return adapter.dump_json(value, **kwargs)
        def validate(value):
            return adapter.validate_json(b"{}" if failure == "validation" else value)
        with monkeypatch.context() as patch:
            patch.setattr(dependency, "TypeAdapter", lambda _: SimpleNamespace(dump_json=dump, validate_json=validate))
            try:
                return await original(request, response, response_type)
            except (ValidationError, PydanticSerializationError) as exc:
                assert isinstance(exc, ValidationError if failure == "validation" else PydanticSerializationError)
                failures.append(type(exc))
                raise
    with monkeypatch.context() as patch:
        patch.setattr(routes, "commit_policy_response", inspect)
        response = await mutate(admin_access, admin_access.target, "POST", path(target.project) + "/drafts", {"name": "Atomic policy"}, key=key)
    assert response.status_code == 500, response.text
    assert observed == [True] and len(failures) == 1
    assert await snapshot(target.project) == before
    retried = await mutate(admin_access, admin_access.target, "POST", path(target.project) + "/drafts", {"name": "Atomic policy"}, key=key)
    assert retried.status_code == 201, retried.text


@pytest.mark.parametrize("denied", (False, True))
async def test_real_audit_insert_failure(admin_access, monkeypatch, denied):
    target = await world(admin_access)
    key, attempted = uuid4(), []
    before = await snapshot(target.project)
    caller = await admin_access.signed.actor("denied-audit-policy") if denied else admin_access.target
    original = AuditService.add_authority_event
    async with db_session.get_session_factory()() as session:
        original_description = (await session.get(Project, str(target.project))).description
    async def fail_insert(service, value):
        assert value.action_id == "contribution.policy.create_draft"
        session = service._repository._session
        project = await session.get(Project, str(target.project))
        project.description = "audit insert rollback marker"
        await session.flush()
        await session.execute(text(
            "ALTER TABLE audit_events ADD CONSTRAINT test_reject_policy_audit_insert "
            "CHECK (action_id <> 'contribution.policy.create_draft') NOT VALID"
        ))
        try:
            return await original(service, value)
        except IntegrityError as exc:
            assert "INSERT INTO audit_events" in exc.statement
            assert exc.orig.sqlstate == "23514"
            assert "test_reject_policy_audit_insert" in str(exc.orig)
            attempted.append(value.event_id)
            raise
    async def no_response(*args):
        raise AssertionError("response after failed audit insert")
    with monkeypatch.context() as patch:
        patch.setattr(AuditService, "add_authority_event", fail_insert)
        patch.setattr(routes, "commit_policy_response", no_response)
        response = await mutate(admin_access, caller, "POST", path(target.project) + "/drafts", {"name": "Audit policy"}, key=key)
    assert response.status_code == 503 and response.json()["error"]["retryable"] is True, response.text
    assert len(attempted) == 1
    assert await snapshot(target.project) == before
    async with db_session.get_session_factory()() as session:
        assert (await session.get(Project, str(target.project))).description == original_description
    # Transaction-local constraint rolled back. Restore permission for the denied
    # caller; no operation was recorded, so the same actor/key can now succeed.
    if denied:
        await admin_access.signed.grant(admin_access.admin, caller, role="finance_authority", project_id=target.project)
    # The unchanged real writer and original command now succeed.
    retried = await mutate(admin_access, caller, "POST", path(target.project) + "/drafts", {"name": "Audit policy"}, key=key)
    assert retried.status_code == 201, retried.text


@pytest.mark.parametrize("operation", ("current", "read", "create_draft", "update_draft", "publish", "retire"))
async def test_denied_decision_is_retained(admin_access, operation):
    actor = await admin_access.signed.actor("policy-denied-evidence")
    receipt = None
    if operation == "create_draft":
        target = await world(admin_access)
    elif operation == "retire":
        target, receipt = await published(admin_access)
    else:
        target, receipt = await draft(admin_access)
        if operation == "publish":
            valid = await mutate(admin_access, admin_access.target, "PUT", path(target.project, receipt), UNPAID)
            assert valid.status_code == 200, valid.text
    await admin_access.signed.grant(admin_access.admin, actor, role="project_manager", project_id=target.project)
    root = path(target.project)
    before = await snapshot(target.project)
    async def request(caller):
        if operation in {"current", "read"}:
            suffix = "/current" if operation == "current" else "/" + receipt["contribution_policy_id"]
            return await admin_access.signed.client.get(root + suffix, headers=caller.headers)
        if operation == "create_draft":
            return await mutate(admin_access, caller, "POST", root + "/drafts", {"name": "Denied policy"})
        suffix = {"update_draft": "", "publish": "/publication", "retire": "/retirement"}[operation]
        return await mutate(admin_access, caller, "PUT" if operation == "update_draft" else "POST",
            path(target.project, receipt) + suffix, UNPAID if operation == "update_draft" else {})
    denied = await request(actor)
    assert denied.status_code == 404, denied.text
    after = await snapshot(target.project)
    assert {k:v for k,v in before.items() if k != "authority"} == {k:v for k,v in after.items() if k != "authority"}
    action = "contribution.policy." + ("read" if operation == "current" else operation)
    async with db_session.get_session_factory()() as session:
        decisions = (await session.scalars(select(AuditEvent).where(
            AuditEvent.actor_id == str(actor.id), AuditEvent.action_id == action,
            AuditEvent.project_id == str(target.project)))).all()
        assert len(decisions) == 1
        assert decisions[0].after_facts["allowed"] is False
        assert decisions[0].denial_code is not None and decisions[0].matched_grant_id is None
    assert len(after["authority"]) == len(before["authority"]) + 1
    positive = await request(admin_access.target)
    assert positive.status_code == (201 if operation == "create_draft" else 200), positive.text


@pytest.mark.parametrize("operation", ("create_draft", "update_draft", "publish", "retire"))
@pytest.mark.parametrize("missing", (False, True))
async def test_scope_denial_targets_requested_project(admin_access, operation, missing):
    # The caller holds Finance authority on the policy's true project, never the
    # URL's requested project. The denial must not imply policy custody there.
    source, receipt = await draft(admin_access)
    if missing:
        requested = uuid4()
    else:
        other = await world(admin_access)
        requested = other.project
        response = await admin_access.signed.revoke(admin_access.admin, other.grant)
        assert response.status_code == 200, response.text
    before = await snapshot(source.project)
    root = path(requested)
    if operation == "create_draft":
        method, url, body = "POST", root + "/drafts", {"name": "Refused policy"}
    else:
        suffix = {"update_draft": "", "publish": "/publication", "retire": "/retirement"}[operation]
        method, url, body = "PUT" if operation == "update_draft" else "POST", path(requested, receipt) + suffix, UNPAID if operation == "update_draft" else {}
    denied = await mutate(admin_access, admin_access.target, method, url, body)
    assert denied.status_code == 404, denied.text
    assert await snapshot(source.project) == before
    async with db_session.get_session_factory()() as session:
        decisions = (await session.scalars(select(AuditEvent).where(
            AuditEvent.actor_id == str(admin_access.target.id),
            AuditEvent.action_id == "contribution.policy." + operation,
            AuditEvent.target_ref_id == str(requested),
        ))).all()
        assert len(decisions) == 1
        event = decisions[0]
        assert event.after_facts["allowed"] is False
        assert event.after_facts["resource_context_digest"].startswith("sha256:")
        assert event.denial_code is not None and event.matched_grant_id is None
        assert event.target_ref_kind == "project"
        assert event.project_id == (None if missing else str(requested))
        assert event.resource_type == (None if missing else "project")
        assert event.resource_id == (None if missing else str(requested))
