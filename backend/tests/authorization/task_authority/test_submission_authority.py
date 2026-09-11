"""Real grant custody at the hidden AUTH port, not TASK/ART creation proof."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.modules.authorization.submission_creation_authorization import (
    PreparedSubmissionCreationAuthorization,
)
from app.modules.tasks.api import (
    SubmissionCreationAuthorityFacts, SubmissionCreationUnavailable,
    TaskLockedProjectContextReferences, TaskSubmissionContextFacts,
)
from app.modules.tasks.models import AuditEvent
from tests.authorization.admin_access.support import create_project
from tests.authorization.task_authority.test_postgresql import context, grant, project_manager


def authority_facts(actor_id, project_id):
    """Supply TASK-port facts; this fixture does not claim to load or lock TASK rows."""
    task_id, assignment_id = uuid4(), uuid4()
    task_context = TaskSubmissionContextFacts(
        task_id=task_id, assignment_id=assignment_id, contributor_id=actor_id,
        status="in_progress", kind="initial", predecessor=None,
        locked_project_context=TaskLockedProjectContextReferences(
            project_id=project_id, guide_version="1", source_snapshot_id=uuid4(),
            source_snapshot_hash="sha256:" + "1" * 64, effective_policy_id=uuid4(),
            effective_policy_hash="sha256:" + "2" * 64, pre_submit_policy_id=uuid4(),
            pre_submit_policy_bundle_hash="sha256:" + "3" * 64,
        ),
    )
    return SubmissionCreationAuthorityFacts(
        task_id=task_id, assignment_id=assignment_id, contributor_id=actor_id,
        admission_id=uuid4(), predecessor_submission_id=None,
        submission_id=uuid4(), submission_version=1, task_context=task_context,
    )


async def test_submission_authority_consumes_exact_project_grant(admin_access):
    access = admin_access
    project = await create_project("Submission authority")
    manager = await project_manager(access, project)
    grant_id = await grant(access, manager, project)
    human = await context(access)
    facts = authority_facts(access.target.id, project)
    async with db_session.get_session_factory()() as session:
        authority = PreparedSubmissionCreationAuthorization(session, human)
        async with session.begin():
            await authority.authorize(facts)
            handle = await authority.prepare(facts)
            try:
                await authority.consume(handle, facts)
            finally:
                authority.close(handle)
        events = list(await session.scalars(select(AuditEvent).where(
            AuditEvent.request_id == human.request_id,
        )))
        assert len(events) == 1
        assert events[0].event_type == "SensitiveAuthorizationAllowed"
        assert events[0].action_id == "submission.create"
        assert events[0].matched_grant_id == grant_id
        assert events[0].project_id == str(project)


@pytest.mark.parametrize("case", ["absent", "reviewer", "foreign", "revoked", "operator", "project_manager"])
async def test_submission_authority_rejects_inapplicable_grants(admin_access, case):
    access = admin_access
    project = await create_project("Submission authority denied")
    if case in {"operator", "project_manager"}:
        await access.signed.grant(access.admin, access.target, role=case)
    elif case != "absent":
        grant_project = await create_project("Foreign submission project") if case == "foreign" else project
        manager = await project_manager(access, grant_project)
        grant_id = await grant(
            access, manager, grant_project, "reviewer" if case == "reviewer" else "submitter",
        )
        if case == "revoked":
            response = await access.signed.client.post(
                f"/api/v1/projects/{project}/role-grants/{grant_id}/revoke",
                headers=manager.headers | {"Idempotency-Key": str(uuid4())},
                json={"reason": "Withdraw submission authority"},
            )
            assert response.status_code == 200, response.text
    human = await context(access)
    facts = authority_facts(access.target.id, project)
    async with db_session.get_session_factory()() as session:
        authority = PreparedSubmissionCreationAuthorization(session, human)
        with pytest.raises(SubmissionCreationUnavailable):
            async with session.begin():
                await authority.authorize(facts)
                handle = await authority.prepare(facts)
                try:
                    await authority.consume(handle, facts)
                finally:
                    authority.close(handle)
        assert list(await session.scalars(select(AuditEvent).where(
            AuditEvent.request_id == human.request_id,
            AuditEvent.event_type == "SensitiveAuthorizationAllowed",
        ))) == []
