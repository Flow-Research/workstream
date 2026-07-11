"""FastAPI routes for review decision creation and querying."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_registered_actor
from app.db.session import get_db_session
from app.modules.review.schemas import ReviewCreate, ReviewSchema
from app.modules.review.service import ReviewError, ReviewService, ReviewValidationError
from app.schemas.auth import ActorContext

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=ReviewSchema, status_code=status.HTTP_201_CREATED)
async def create_review(
    payload: ReviewCreate,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReviewSchema:
    """Submit a human review decision with structured findings.

    Enforces:
    - Only accept, needs_revision, reject.
    - reject / needs_revision require at least one finding.
    - accept requires evidence references and no blocking checker results.
    """
    try:
        return await ReviewService(session).create_review(payload, actor.actor_id)
    except ReviewValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ReviewError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{submission_id}", response_model=list[ReviewSchema])
async def list_reviews_for_submission(
    submission_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ReviewSchema]:
    """Return all review decisions for a submission, newest first."""
    reviews = await ReviewService(session).get_reviews_for_submission(submission_id)
    return list(reviews)


@router.get("/review/{review_id}", response_model=ReviewSchema)
async def get_review(
    review_id: str,
    actor: Annotated[ActorContext, Depends(get_registered_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReviewSchema:
    """Return one review by its id."""
    review = await ReviewService(session).get_review(review_id)
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    return review
