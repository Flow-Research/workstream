"""Current contribution-policy audit privacy and vocabulary proof."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from app.modules.tasks.models import AuditEvent
from .postgresql_support import world, snapshot
from .audit_schema_support import clone_decision


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tamper,constraint",
    (
        ("resource", "ck_audit_events_authority_privacy_bounds"),
        ("private_fact", "ck_audit_events_fact_bounds"),
        ("digest", "ck_audit_events_fact_bounds"),
        ("unknown_action", "ck_audit_events_authorization_action_evidence"),
        ("wrong_permission", "ck_audit_events_authorization_action_evidence"),
        ("wrong_action", "ck_audit_events_authorization_action_evidence"),
        ("crossed_route", "routing authority requires its complete governed outcome"),
    ),
)
async def test_policy_audit_sql_retains_resource_and_private_fact_guards(
    admin_access, tamper, constraint
):
    target = await world(admin_access)
    await target.execute("create_draft", target.request("create_draft"))
    async with db_session.get_session_factory()() as session:
        event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.project_id == str(target.project),
                AuditEvent.action_id == "contribution.policy.create_draft",
            )
        )
    control = await clone_decision(event, {})
    async with db_session.get_session_factory()() as session:
        assert (await session.get(AuditEvent, control)).resource_type == "contribution_policy"
    changes = {
        "crossed_route": {
            "action_id": "task.post_submit.route",
            "permission_id": "task.post_submit.route",
        },
        "resource": {"resource_type": "unregistered_policy_resource"},
        "private_fact": {
            "after_facts": {**event.after_facts, "private_material": "must-not-persist"}
        },
        "digest": {"after_facts": {**event.after_facts, "resource_context_digest": "bad"}},
        "unknown_action": {"action_id": "contribution.policy.unregistered"},
        "wrong_permission": {"permission_id": "project.read"},
        "wrong_action": {"action_id": "project.read"},
    }[tamper]
    before = await snapshot(target.project)
    with pytest.raises(DBAPIError, match=constraint):
        await clone_decision(event, changes)
    assert await snapshot(target.project) == before
