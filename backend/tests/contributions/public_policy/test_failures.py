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
from .support import mutate, path, world


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


async def test_real_audit_insert_failure(admin_access, monkeypatch):
    target = await world(admin_access)
    key, attempted = uuid4(), []
    before = await snapshot(target.project)
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
        response = await mutate(admin_access, admin_access.target, "POST", path(target.project) + "/drafts", {"name": "Audit policy"}, key=key)
    assert response.status_code == 404, response.text
    assert len(attempted) == 1
    assert await snapshot(target.project) == before
    async with db_session.get_session_factory()() as session:
        assert (await session.get(Project, str(target.project))).description == original_description
    # Transaction-local failure constraint has rolled back; the same command succeeds.
    retried = await mutate(admin_access, admin_access.target, "POST", path(target.project) + "/drafts", {"name": "Audit policy"}, key=key)
    assert retried.status_code == 201, retried.text
