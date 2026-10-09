"""REV-owned source validation and mode-specific acceptance persistence."""

from typing import Literal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reviews.acceptance.models import FinalAcceptance
from app.modules.reviews.api.acceptance import FinalAcceptanceInput
from app.modules.reviews.api.acceptance import (
    FinalAcceptanceConflict,
    FinalAcceptanceFacts,
)

_STRING_IDS = frozenset({
    "project_id", "task_id", "submission_id", "accepted_submitter_id",
    "recorded_by", "policy_context_ref",
})


class FinalAcceptanceRepository:
    """The caller holds TASK locks before any acceptance foreign-key write."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def persist(
        self, source: FinalAcceptanceInput, *, disposition: Literal["new", "replay"]
    ) -> FinalAcceptanceFacts:
        """New must win its insert; replay only reads an exact complete identity."""
        values = {
            name: str(value) if name in _STRING_IDS else value
            for name, value in source.model_dump().items()
        }
        if disposition == "new":
            inserted = await self._session.scalar(
                insert(FinalAcceptance).values(**values)
                .on_conflict_do_nothing().returning(FinalAcceptance.id)
            )
            if inserted != source.id:
                raise FinalAcceptanceConflict("final_acceptance_conflict")
        elif disposition != "replay":
            raise FinalAcceptanceConflict("final_acceptance_conflict")

        source_predicate = (
            FinalAcceptance.source_review_id == source.source_review_id
            if source.source_review_id is not None
            else FinalAcceptance.source_routing_manifest_id == source.source_routing_manifest_id
        )
        candidates = (await self._session.scalars(
            select(FinalAcceptance).where(or_(
                FinalAcceptance.id == source.id,
                FinalAcceptance.task_id == str(source.task_id),
                FinalAcceptance.submission_id == str(source.submission_id),
                source_predicate,
            )).execution_options(populate_existing=True)
        )).all()
        if len(candidates) != 1 or any(
            getattr(candidates[0], name) != value for name, value in values.items()
        ):
            raise FinalAcceptanceConflict("final_acceptance_conflict")
        row = candidates[0]
        return FinalAcceptanceFacts(
            **{
                name: UUID(getattr(row, name)) if name in _STRING_IDS else getattr(row, name)
                for name in FinalAcceptanceInput.model_fields
            },
            accepted_at=row.accepted_at,
        )
