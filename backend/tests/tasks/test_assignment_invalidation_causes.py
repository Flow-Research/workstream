"""Real AUTH cause controls and substitutions through the actual AUDIT reader."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import select

from app.adapters.audit import committed_authority_invalidation
from app.modules.audit.repository import AuditRepository
from app.modules.outbox.api import HandlerOutcome
from app.modules.tasks.models import AuditEvent
from tests.test_tasks import (
    task_client as task_client,
    task_database_env as task_database_env,
    auth_headers,
    set_dev_actor,
)
from tests.tasks.invalidation_support import setup_assignment, revoke, invoked, snapshot


@pytest.mark.parametrize("kind", ["grant", "suspend", "deactivate", "link"])
async def test_reader_rejects_mixed_and_malformed_real_cause_chain(task_client, monkeypatch, kind):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s, kind)
    reader = committed_authority_invalidation(s.sessions)
    control = await reader.read_invalidation(s.invalidation_id)
    assert control is not None and control.contributor_id == UUID(s.grant["actor_profile_id"])
    assert await reader.read_invalidation(new_record_id()) is None
    assert await reader.read_invalidation("invalid") is None
    async with s.sessions() as session:
        rows = await AuditRepository(session).invalidation_chain(s.invalidation_id)
        originals = [
            {column.key: getattr(row, column.key) for column in AuditEvent.__table__.columns}
            for row in rows
        ]
    replacements = [
        (0, {"event_domain": "legacy_lifecycle"}),
        (1, {"auth_source": "other"}),
        (0, {"event_version": 2}),
        (1, {"is_dev_auth": True}),
        (0, {"invalidation_cause_event_id": str(new_record_id())}),
        (1, {"request_id": str(new_record_id())}),
        (1, {"correlation_id": str(new_record_id())}),
        (0, {"idempotency_reference": None}),
        (1, {"target_actor_ref": str(new_record_id())}),
        (1, {"target_ref_id": str(new_record_id())}),
        (0, {"resource_id": str(new_record_id())}),
        (0, {"invalidation_target_ref": str(new_record_id())}),
        (0, {"after_facts": {**originals[0]["after_facts"], "effective": True}}),
        (1, {"target_actor_ref_kind": None}),
        (1, {"entity_id": str(new_record_id())}),
    ]
    if kind == "grant":
        replacements += [
            (0, {"target_actor_ref": str(new_record_id())}),
            (0, {"target_ref_id": str(new_record_id())}),
            (
                0,
                {
                    "after_facts": {
                        **originals[0]["after_facts"],
                        "future_obligation": "rev_reviewer_obligation",
                    }
                },
            ),
        ]
    for index, changes in replacements:
        altered = deepcopy(originals)
        altered[index].update(changes)

        async def substituted_chain(owner, event_id):
            assert event_id == s.invalidation_id
            return tuple(SimpleNamespace(**row) for row in altered)

        with monkeypatch.context() as patch:
            patch.setattr(AuditRepository, "invalidation_chain", substituted_chain)
            assert await reader.read_invalidation(s.invalidation_id) is None, (
                kind,
                index,
                tuple(changes),
            )
    from app.modules.audit.schemas import PermissionId

    wrong_permission = (
        PermissionId.ACTOR_PROFILE_SUSPEND.value
        if kind == "deactivate"
        else PermissionId.ACTOR_PROFILE_DEACTIVATE.value
    )
    # Corrupt both rows so their equality cannot reject before exact event/permission binding.
    altered = deepcopy(originals)
    for row in altered:
        row["permission_id"] = wrong_permission

    async def wrong_permission_chain(owner, event_id):
        return tuple(SimpleNamespace(**row) for row in altered)

    with monkeypatch.context() as patch:
        patch.setattr(AuditRepository, "invalidation_chain", wrong_permission_chain)
        assert await reader.read_invalidation(s.invalidation_id) is None
    assert control.recorded_at == originals[0]["created_at"]
    assert control.recorded_at.utcoffset() is not None
    assert await reader.read_invalidation(s.invalidation_id) == control


async def test_reviewer_revocation_never_releases_submitter_assignment(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    unavailable = {
        "availability": "unavailable",
        "reference_ids": [],
        "unavailable_reason": "no_record",
    }
    response = await s.client.post(
        f"/api/v1/projects/{s.project['id']}/role-grants",
        headers=auth_headers(),
        json={
            "target_actor_profile_id": s.grant["actor_profile_id"],
            "role": "reviewer",
            "qualification": {
                "skills_snapshot": unavailable,
                "reputation_snapshot": unavailable,
                "prior_project_work_refs": [],
                "external_expertise_refs": [],
            },
            "reason": "Independent reviewer role",
        },
    )
    assert response.status_code == 201, response.text
    grant_id = response.json()["id"]
    revoked = await s.client.post(
        f"/api/v1/projects/{s.project['id']}/role-grants/{grant_id}/revoke",
        headers=auth_headers(),
        json={"reason": "Reviewer authority only"},
    )
    assert revoked.status_code == 200, revoked.text
    async with s.sessions() as session:
        event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "AuthorityInvalidationRequested",
                AuditEvent.invalidation_target_ref == grant_id,
            )
        )
        assert event.after_facts["future_obligation"] == "rev_reviewer_obligation"
        s.invalidation_id = UUID(event.id)
    _, envelope = await invoked(s, synthetic_transport=True)
    before = await snapshot(s)
    assert await s.handler(envelope) is HandlerOutcome.REJECT
    assert await snapshot(s) == before
    assert s.trace == []


async def test_reactivation_event_is_not_a_release_cause(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s, "suspend")
    old_cause = s.invalidation_id
    response = await s.client.post(
        f"/api/v1/actors/{s.grant['actor_profile_id']}/reactivate",
        headers=auth_headers(),
        json={"reason": "Restore authority"},
    )
    assert response.status_code == 200, response.text
    async with s.sessions() as session:
        event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "AuthorityInvalidationRequested",
                AuditEvent.invalidation_target_ref == s.grant["actor_profile_id"],
                AuditEvent.id != str(old_cause),
            )
        )
        assert event.after_facts == {"effective": True}
        s.invalidation_id = UUID(event.id)
    _, envelope = await invoked(s, synthetic_transport=True)
    before = await snapshot(s)
    assert await s.handler(envelope) is HandlerOutcome.REJECT
    assert await snapshot(s) == before and s.trace == []


@pytest.mark.parametrize("mismatch", ["project", "contributor"])
async def test_committed_cause_cannot_target_another_valid_assignment(
    task_client, monkeypatch, mismatch
):
    from app.modules.tasks.api.assignment_invalidation import AssignmentInvalidationTarget
    from tests.test_tasks import (
        create_active_project,
        create_ready_task,
        admit_and_grant_project_submitter,
    )

    s = await setup_assignment(task_client, monkeypatch)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    project = (
        await create_active_project(s.client, slug="other-cause-project")
        if mismatch == "project"
        else s.project
    )
    task = await create_ready_task(s.client, project["id"])
    grant = await admit_and_grant_project_submitter(
        s.client,
        monkeypatch,
        project["id"],
        "invalidation-submitter" if mismatch == "project" else "other-cause-contributor",
    )
    assert grant["grant_id"] != s.grant["grant_id"]
    assert (grant["actor_profile_id"] == s.grant["actor_profile_id"]) is (mismatch == "project")
    claimed = await s.client.post(f"/api/v1/tasks/{task['id']}/claim", headers=auth_headers())
    assert claimed.status_code == 200, claimed.text
    assignment = claimed.json()["assignment"]
    # Both real assignments predate the cause, so chronology cannot mask correlation.
    await revoke(s, "grant" if mismatch == "project" else "suspend")
    target = AssignmentInvalidationTarget(
        project_id=UUID(project["id"]),
        task_id=UUID(task["id"]),
        assignment_id=UUID(assignment["id"]),
        contributor_id=UUID(grant["actor_profile_id"]),
        authority_invalidation_event_id=s.invalidation_id,
    )
    _, envelope = await invoked(s, target=target, synthetic_transport=True)
    foreign = SimpleNamespace(
        **{**vars(s), "task": task, "assignment": assignment, "project": project}
    )
    before, original_before = await snapshot(foreign), await snapshot(s)
    cause = await committed_authority_invalidation(s.sessions).read_invalidation(s.invalidation_id)
    assert cause is not None and before[1][0]["assigned_at"] <= cause.recorded_at
    assert (
        before[0]["status"] == "in_progress" and before[0]["assigned_to"] == grant["actor_profile_id"]
    )
    assert before[1][0]["status"] == "active" and before[1][0]["released_at"] is None
    assert await s.h.delivery.observe_invocation(envelope) is not None
    assert await s.handler(envelope) is HandlerOutcome.REJECT
    assert await snapshot(foreign) == before and await snapshot(s) == original_before
    assert s.trace == []
    _, valid = await invoked(s)
    assert await s.handler(valid) is HandlerOutcome.ACKNOWLEDGE
    assert await snapshot(foreign) == before
