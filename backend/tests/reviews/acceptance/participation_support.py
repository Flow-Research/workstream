"""Real human-source composition for hidden shared-acceptance integration proof."""

from uuid import UUID

from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.modules.compensation.awards.participant import CompensationAwardParticipant
from app.modules.contributions.records.participant import SubmitterContributionParticipant
from app.modules.reviews.acceptance.participant import FinalAcceptanceParticipant
from app.modules.reviews.api.acceptance import FinalAcceptanceRequest
from app.modules.reviews.lifecycle.fence import PostgresJointLifecycleMutationFence
from app.modules.tasks.accepted_effects import TaskAcceptedEffectsParticipant
from app.modules.tasks.api.accepted_effects import TaskAcceptedEffectsRequest


async def prepare_review_pending(h) -> None:
    """Arrange the retained human-review prestate without claiming runtime authority."""
    async with h.factory() as session, session.begin():
        result = await session.execute(
            text(
                "UPDATE public.workstream_tasks SET status='review_pending' "
                "WHERE id=:task_id AND project_id=:project_id"
            ),
            {"task_id": h.acceptance.task_id, "project_id": h.acceptance.project_id},
        )
        assert result.rowcount == 1
        result = await session.execute(
            text(
                "UPDATE public.task_assignments "
                "SET accepted_at=coalesce(accepted_at, clock_timestamp()) "
                "WHERE id=:assignment_id AND status='active' AND released_at IS NULL"
            ),
            {"assignment_id": h.review.task_assignment_id},
        )
        assert result.rowcount == 1
        state = (
            await session.execute(
                text(
                    "SELECT task.status AS task_status, assignment.status AS assignment_status, "
                    "assignment.accepted_at, assignment.released_at "
                    "FROM public.workstream_tasks task "
                    "JOIN public.task_assignments assignment ON assignment.id=:assignment_id "
                    "WHERE task.id=:task_id"
                ),
                {
                    "task_id": h.acceptance.task_id,
                    "assignment_id": h.review.task_assignment_id,
                },
            )
        ).mappings().one()
        assert state["task_status"] == "review_pending"
        assert state["assignment_status"] == "active"
        assert state["accepted_at"] is not None
        assert state["released_at"] is None


async def request_for(h, **changes) -> FinalAcceptanceRequest:
    async with h.factory() as session:
        source = (
            await session.execute(
                text(
                    "SELECT s.version, s.task_assignment_id, s.contributor_id, "
                    "s.contribution_policy_version_id, s.artifact_content_id, content.sha256 "
                    "FROM public.submissions s "
                    "JOIN public.artifact_contents content ON content.id=s.artifact_content_id "
                    "WHERE s.id=:submission_id"
                ),
                {"submission_id": h.acceptance.submission_id},
            )
        ).mappings().one()
    values = {
        "acceptance": h.acceptance,
        "task_effects": TaskAcceptedEffectsRequest(
            project_id=h.acceptance.project_id,
            task_id=h.acceptance.task_id,
            assignment_id=UUID(str(source["task_assignment_id"])),
            submission_id=h.acceptance.submission_id,
            submission_version=source["version"],
            contributor_id=UUID(str(source["contributor_id"])),
            contribution_policy_version_id=source["contribution_policy_version_id"],
            content_id=UUID(str(source["artifact_content_id"])),
            content_sha256=source["sha256"],
            final_acceptance_id=h.acceptance.id,
            expected_task_status="review_pending",
        ),
        "correlation_id": new_record_id(),
        "expected_generation": 2,
    }
    values.update(changes)
    return FinalAcceptanceRequest(**values)


def participant(session) -> FinalAcceptanceParticipant:
    fence = PostgresJointLifecycleMutationFence(session)
    tasks = TaskAcceptedEffectsParticipant(session, fence=fence)
    contributions = SubmitterContributionParticipant(
        session,
        fence=fence,
        awards=CompensationAwardParticipant(session),
    )
    return FinalAcceptanceParticipant(
        session,
        fence=fence,
        tasks=tasks,
        contributions=contributions,
    )


async def stored_effects(session, task_id) -> dict[str, object]:
    row = (
        await session.execute(
            text(
                "SELECT task.status AS task_status, assignment.status AS assignment_status, "
                "(SELECT count(*) FROM public.final_acceptances) AS acceptances, "
                "(SELECT count(*) FROM public.contribution_records "
                " WHERE contribution_type='accepted_submission') AS contributions, "
                "(SELECT count(*) FROM public.contribution_records "
                " WHERE contribution_type='completed_review') AS reviewer_contributions, "
                "(SELECT count(*) FROM public.compensation_awards) AS awards "
                "FROM public.workstream_tasks task "
                "JOIN public.task_assignments assignment ON assignment.task_id=task.id "
                "WHERE task.id=:task_id"
            ),
            {"task_id": task_id},
        )
    ).mappings().one()
    return dict(row)


async def stage_terminal_task(session, request: FinalAcceptanceRequest) -> None:
    await session.execute(
        text("UPDATE public.workstream_tasks SET status='accepted' WHERE id=:id"),
        {"id": request.task_effects.task_id},
    )
    await session.execute(
        text("UPDATE public.task_assignments SET status='completed' WHERE id=:id"),
        {"id": request.task_effects.assignment_id},
    )
