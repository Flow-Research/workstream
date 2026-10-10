"""Pre-0029 acceptance storage for migration preservation only."""

from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import insert, text

from app.core.identifiers import new_record_id
from app.modules.reviews.acceptance.models import FinalAcceptance
from pydantic import BaseModel
from typing import Literal
from tests.reviews.decision.support import finding, insert_review, review_source


class HistoricalAcceptanceInput(BaseModel):
    id: UUID
    project_id: UUID
    task_id: UUID
    submission_id: UUID
    acceptance_source: Literal["human_review"]
    source_review_id: UUID
    source_routing_manifest_id: None
    accepted_submitter_id: UUID
    recorded_by: UUID
    policy_context_ref: UUID


@asynccontextmanager
async def historical_acceptance_source(tmp_path, database_url, *, decision="accept", **options):
    async with review_source(tmp_path, database_url, **options) as h:
        h.review = h.review.model_copy(
            update={
                "decision": decision,
                "findings": (finding(),) if decision == "needs_revision" else (),
            }
        )
        async with h.factory() as session:
            await insert_review(session, h.review)
            await session.commit()
        await attach_historical_acceptance(h)
        yield h


async def attach_historical_acceptance(h):
    async with h.factory() as session:
        revision = await session.scalar(text("SELECT version_num FROM public.alembic_version"))
        assert 13 <= int(revision[:4]) <= 28, "historical acceptance is not current authority"
        contributor = await session.scalar(
            text("SELECT contributor_id FROM public.submissions WHERE id=:id"),
            {"id": h.review.submission_id},
        )
    h.acceptance = HistoricalAcceptanceInput(
        id=new_record_id(),
        project_id=h.review.project_id,
        task_id=h.review.task_id,
        submission_id=h.review.submission_id,
        acceptance_source="human_review",
        source_review_id=h.review.id,
        source_routing_manifest_id=None,
        accepted_submitter_id=UUID(str(contributor)),
        recorded_by=h.review.reviewer_id,
        policy_context_ref=h.review.locked_review_policy_id,
    )


async def insert_historical_acceptance(session, source, **overrides):
    revision = await session.scalar(text("SELECT version_num FROM public.alembic_version"))
    assert 14 <= int(revision[:4]) <= 28, "historical acceptance cannot write the current schema"
    values = source.model_dump()
    values.update(overrides)
    for field in (
        "project_id",
        "task_id",
        "submission_id",
        "accepted_submitter_id",
        "recorded_by",
        "policy_context_ref",
    ):
        if values[field] is not None:
            values[field] = str(values[field])
    await session.execute(insert(FinalAcceptance).values(**values))
