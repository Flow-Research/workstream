"""Mechanical TASK participant inputs; no FinalAcceptance or fabricated source authority."""

from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text

from app.modules.reviews.lifecycle.fence import PostgresJointLifecycleMutationFence
from app.modules.tasks.accepted_effects import TaskAcceptedEffectsParticipant
from app.modules.tasks.api import TaskAcceptedEffectsRequest
from tests.reviews.decision.support import review_source
from app.core.identifiers import new_record_id


@asynccontextmanager
async def accepted_effects_source(tmp_path, database_url):
    """Yield exact persisted TASK facts in the human acceptance prestate."""
    async with review_source(tmp_path, database_url) as h:
        async with h.factory() as session, session.begin():
            row = (
                await session.execute(
                    text(
                        """
                        SELECT s.task_assignment_id, s.contributor_id,
                               s.contribution_policy_version_id, s.artifact_content_id,
                               c.sha256, t.locked_review_policy_id
                        FROM public.submissions s
                        JOIN public.workstream_tasks t ON t.id=s.task_id
                        JOIN public.artifact_contents c ON c.id=s.artifact_content_id
                        WHERE s.id=:submission_id
                        """
                    ),
                    {"submission_id": h.review.submission_id},
                )
            ).mappings().one()
            await session.execute(
                text(
                    "UPDATE public.workstream_tasks SET status='review_pending' "
                    "WHERE id=:task_id"
                ),
                {"task_id": h.review.task_id},
            )
            await session.execute(
                text(
                    "UPDATE public.task_assignments "
                    "SET accepted_at=coalesce(accepted_at, clock_timestamp()) "
                    "WHERE id=:assignment_id AND status='active' AND released_at IS NULL"
                ),
                {"assignment_id": row["task_assignment_id"]},
            )
        h.effects_request = TaskAcceptedEffectsRequest(
            project_id=h.review.project_id,
            task_id=h.review.task_id,
            assignment_id=UUID(str(row["task_assignment_id"])),
            submission_id=h.review.submission_id,
            submission_version=h.review.submission_version,
            contributor_id=UUID(str(row["contributor_id"])),
            contribution_policy_version_id=row["contribution_policy_version_id"],
            content_id=UUID(str(row["artifact_content_id"])),
            content_sha256=row["sha256"],
            final_acceptance_id=new_record_id(),
            expected_task_status="review_pending",
        )
        h.locked_review_policy_id = UUID(str(row["locked_review_policy_id"]))
        yield h


def participant(session):
    return TaskAcceptedEffectsParticipant(
        session,
        fence=PostgresJointLifecycleMutationFence(session),
    )
