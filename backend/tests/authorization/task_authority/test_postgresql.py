"""Real grants and transaction-bound task authority, without fake allow ports."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.tasks.api.authorization import (
    TaskAuthorityDenied,
    TaskAuthorityFacts,
    TaskAuthorityOperation,
)
from app.modules.tasks.models import AuditEvent
from tests.authorization.admin_access.support import create_project


async def project_manager(access, project):
    manager = await access.signed.actor("project-manager")
    await access.signed.grant(access.admin, manager, role="project_manager", project_id=project)
    return manager


async def grant(access, manager, project, role="submitter"):
    response = await access.signed.client.post(
        f"/api/v1/projects/{project}/role-grants",
        headers=manager.headers | {"Idempotency-Key": str(uuid4())},
        json={
            "target_actor_profile_id": str(access.target.id),
            "role": role,
            "qualification": {
                "skills_snapshot": {
                    "availability": "unavailable",
                    "reference_ids": [],
                    "unavailable_reason": "no_record",
                },
                "reputation_snapshot": {
                    "availability": "unavailable",
                    "reference_ids": [],
                    "unavailable_reason": "no_record",
                },
                "prior_project_work_refs": [],
                "external_expertise_refs": [],
            },
            "reason": "Assign contributor for exact task authority proof",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def context(access):
    async with db_session.get_session_factory()() as session:
        link = await session.scalar(
            select(ActorIdentityLink).where(
                ActorIdentityLink.actor_profile_id == str(access.target.id),
            )
        )
        return HumanAuthorizationContext(
            actor_profile_id=access.target.id,
            actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus.ACTIVE,
            identity_link_id=UUID(link.id),
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )


def facts(access, project):
    return TaskAuthorityFacts(
        operation=TaskAuthorityOperation.CLAIM,
        task_id=uuid4(),
        project_id=project,
        actor_profile_id=access.target.id,
        task_status="ready",
        assigned_to=None,
        assignment_id=None,
        assignment_contributor_id=None,
        locked_context_hash="sha256:" + "a" * 64,
    )


@pytest.mark.asyncio
async def test_real_project_grant_allows_exact_task_authority(admin_access):
    access = admin_access
    project = await create_project("Task authority")
    manager = await project_manager(access, project)
    grant_id = await grant(access, manager, project)
    request_context = await context(access)
    exact = facts(access, project)
    async with db_session.get_session_factory()() as session:
        authority = PreparedTaskAuthorization(session, request_context)
        async with session.begin():
            handle = await authority.prepare(exact)
            decision = await authority.consume(handle, exact)
        row = await session.get(AuditEvent, str(decision))
        assert row.matched_grant_id == grant_id
        assert row.action_id == "task.claim" and row.permission_id == "task.claim"
        assert row.project_id == str(project)
        assert row.after_facts["allowed"] is True
        assert row.after_facts["resource_context_digest"].startswith("sha256:")


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["absent", "reviewer", "foreign", "revoked"])
async def test_real_inapplicable_grants_deny_and_leave_no_allow_evidence(admin_access, case):
    access = admin_access
    project = await create_project("Task authority denied")
    if case != "absent":
        grant_project = await create_project("Foreign project") if case == "foreign" else project
        manager = await project_manager(access, grant_project)
        grant_id = await grant(
            access, manager, grant_project, "reviewer" if case == "reviewer" else "submitter"
        )
        if case == "revoked":
            response = await access.signed.client.post(
                f"/api/v1/projects/{project}/role-grants/{grant_id}/revoke",
                headers=manager.headers | {"Idempotency-Key": str(uuid4())},
                json={"reason": "Withdraw task authority"},
            )
            assert response.status_code == 200, response.text
    request_context = await context(access)
    async with db_session.get_session_factory()() as session:
        authority = PreparedTaskAuthorization(session, request_context)
        with pytest.raises(TaskAuthorityDenied) as caught:
            async with session.begin():
                await authority.prepare(facts(access, project))
        assert await authority.restage_denial(caught.value)
        await session.commit()
        rows = list(
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.request_id == request_context.request_id,
                )
            )
        )
        assert len(rows) == 1 and rows[0].event_type == "SensitiveAuthorizationDenied"
        assert rows[0].project_id == str(project)
        assert rows[0].after_facts["allowed"] is False
