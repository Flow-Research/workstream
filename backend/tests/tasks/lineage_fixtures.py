"""Canonical initial stamping for downstream ART arrangements, not claim authority proof."""

from app.core.config import get_settings

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.tasks import task_commands
from app.adapters.audit import task_transition_audit
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.authorization.runtime import ActorKind, ActorStatus, HumanAuthorizationContext, IdentityLinkStatus
from app.modules.actors.models import ActorIdentityLink
from sqlalchemy import select
from uuid import UUID
from app.core.identifiers import new_record_id
from tests.project_create_fixtures import grant_fixture_admin_role
from app.modules.tasks.models import TaskAssignment, WorkstreamTask


async def seed_started_task_for_artifact_test(connection, params):
    """Screen/ready through TASK, then arrange the exact assignment for ART-only tests."""
    async with AsyncSession(bind=connection, expire_on_commit=False) as session:
        task = WorkstreamTask(
            id=params["task"],
            task_size="small",
            project_id=params["project"],
            title="Evidence task",
            description="Complete the work described by the approved guide.",
            acceptance_criteria="The work and evidence satisfy the guide.",
            status="draft",
            created_by=params["actor"],
        )
        session.add(task)
        await session.flush()
        await grant_fixture_admin_role(session, params["actor"], project_id=params["project"])
        link = await session.scalar(select(ActorIdentityLink).where(
            ActorIdentityLink.actor_profile_id == params["actor"], ActorIdentityLink.status == "active"))
        context = HumanAuthorizationContext(
            actor_profile_id=UUID(params["actor"]), actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus.ACTIVE, identity_link_id=UUID(link.id),
            identity_link_status=IdentityLinkStatus.ACTIVE, request_id=new_record_id(), correlation_id=new_record_id(),
        )
        await session.commit()
        commands = task_commands(session, authorization=PreparedTaskAuthorization(session, context),
                                 audit=task_transition_audit(session), actor_profile_id=context.actor_profile_id,
                                 settings=get_settings())
        await commands.screen(UUID(task.id), "ART fixture initial screening", idempotency_key=new_record_id())
        await commands.release(UUID(task.id), "ART fixture ready", idempotency_key=new_record_id())
        session.add(
            TaskAssignment(
                id=params["assignment"],
                task_id=task.id,
                project_id=task.project_id,
                contributor_id=params["actor"],
                assigned_by=params["actor"],
                status="active",
                submitter_contribution_policy_version_id=task.locked_contribution_policy_version_id,
                submitter_task_size=task.task_size,
                submitter_award_definition_id=task.locked_submission_award_definition_id,
            )
        )
        task.assigned_to = params["actor"]
        task.status = "in_progress"
        await session.flush()
