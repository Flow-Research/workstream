"""Current audit-schema proof for proposal review-package authority."""

import json
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.modules.authorization.catalogue import ACTION_BY_ID, ActionId
from app.modules.projects.api.guide_proposals import GuideProposalApproval
from .pg_support import proposal_case, read_package
from .test_postgresql import approve


async def test_review_package_audit_requires_catalogue_manager_permission(
    clean_postgres_database,
):
    action = ActionId.PROJECT_GUIDE_COMPILATION_REVIEW_PACKAGE_READ
    permission = ACTION_BY_ID[action].permission_id.value
    assert permission == "project.guide.manage"
    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        receipt = await approve(
            factory,
            command,
            actor,
            grant,
            GuideProposalApproval(
                target=package.target,
                pre_submit_attachments=(), post_submit_attachments=(),
                idempotency_key=uuid4(),
            ),
        )
        async with factory() as session:
            source_event = await session.scalar(
                text(
                    "select authorization_decision_event_id "
                    "from project_guide_proposal_approvals where operation_id=:id"
                ),
                {"id": receipt.operation_id},
            )
        for candidate in (permission, "project.setup_diagnostic.read"):
            event_id = str(new_record_id())
            patch = {
                "id": event_id,
                "entity_id": event_id,
                "permission_id": candidate,
                "action_id": action.value,
                "resource_type": "project_guide_compilation_review_package",
                "resource_id": str(command.compilation_id),
            }
            async with factory() as session, session.begin():
                statement = text(
                    "insert into audit_events select "
                    "(jsonb_populate_record(null::audit_events, "
                    "to_jsonb(source) || cast(:patch as jsonb))).* "
                    "from audit_events source where id=:source"
                )
                if candidate == permission:
                    await session.execute(
                        statement, {"patch": json.dumps(patch), "source": source_event}
                    )
                    assert (
                        await session.scalar(
                            text("select permission_id from audit_events where id=:id"),
                            {"id": event_id},
                        )
                        == permission
                    )
                else:
                    with pytest.raises(
                        DBAPIError,
                        match="ck_audit_events_authorization_action_evidence",
                    ):
                        async with session.begin_nested():
                            await session.execute(
                                statement,
                                {"patch": json.dumps(patch), "source": source_event},
                            )
                    assert (
                        await session.scalar(
                            text("select count(*) from audit_events where id=:id"),
                            {"id": event_id},
                        )
                        == 0
                    )
