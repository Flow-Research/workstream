"""Service for managing structured review decisions and findings."""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import AuditEvent
from app.modules.checkers.models import CheckerResult
from app.modules.review.models import (
    REVIEW_DECISION_ACCEPT,
    REVIEW_DECISION_NEEDS_REVISION,
    REVIEW_DECISION_REJECT,
    Review,
    ReviewFinding,
)
from app.modules.review.schemas import ReviewCreate, ReviewSchema
from app.modules.tasks.models import Submission


class ReviewError(Exception):
    """Base exception for review operations."""
    pass


class ReviewValidationError(ReviewError):
    """Raised when a review decision fails validation rules."""
    pass


class ReviewService:
    """Creates and queries structured review decisions with findings."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_review(self, review_in: ReviewCreate, actor_id: str) -> ReviewSchema:
        """Create a review decision with full validation.

        Enforcement:
        - needs_revision / reject require at least one finding.
        - accept requires acceptance_evidence_refs and no blocking checker results.
        """
        # 1. Verify submission exists
        submission = await self.session.get(Submission, review_in.submission_id)
        if not submission:
            raise ReviewError(f"Submission {review_in.submission_id} not found")

        # 2. Validate decision rules
        self._validate_decision_requirements(review_in)

        # 3. Check for blocking checker results (accept only)
        if review_in.decision == REVIEW_DECISION_ACCEPT:
            await self._verify_no_blocking_results(submission.id)

        # 4. Create Review
        review_id = str(uuid.uuid4())
        review = Review(
            id=review_id,
            submission_id=review_in.submission_id,
            reviewer_actor_id=actor_id,
            decision=review_in.decision,
            acceptance_evidence_refs=review_in.acceptance_evidence_refs,
            comment=review_in.comment,
        )
        self.session.add(review)

        # 5. Create findings
        for f in review_in.findings:
            finding = ReviewFinding(
                id=str(uuid.uuid4()),
                review_id=review_id,
                severity=f.severity,
                area=f.area,
                issue=f.issue,
                required_fix=f.required_fix,
                evidence_ref=f.evidence_ref,
            )
            self.session.add(finding)

        # 6. Audit event
        audit = AuditEvent(
            id=str(uuid.uuid4()),
            entity_type="review",
            entity_id=review_id,
            event_type="review_decision_created",
            actor_id=actor_id,
            external_subject=review_in.submission_id,
            external_issuer="workstream-backend",
            actor_roles=["reviewer"],
            claim_snapshot={},
            auth_source="internal",
            is_dev_auth=False,
            reason=f"Review decision {review_in.decision} created",
            event_payload={
                "decision": review_in.decision,
                "finding_count": len(review_in.findings),
            },
        )
        self.session.add(audit)

        await self.session.flush()
        # Eager-load findings before returning
        result = await self.session.get(Review, review_id, options=[selectinload(Review.findings)])
        return ReviewSchema.model_validate(result)

    def _validate_decision_requirements(self, review_in: ReviewCreate) -> None:
        """Enforce findings for reject / needs_revision and evidence for accept."""
        if review_in.decision in (REVIEW_DECISION_REJECT, REVIEW_DECISION_NEEDS_REVISION):
            if not review_in.findings:
                raise ReviewValidationError(
                    f"Decision '{review_in.decision}' requires at least one structured finding.",
                )
        elif review_in.decision == REVIEW_DECISION_ACCEPT:
            if not review_in.acceptance_evidence_refs:
                raise ReviewValidationError(
                    "Decision 'accept' requires at least one acceptance evidence reference.",
                )

    async def _verify_no_blocking_results(self, submission_id: str) -> None:
        """Ensure no CheckerResult has blocks_review=True for this submission."""
        stmt = select(CheckerResult).where(
            CheckerResult.submission_id == submission_id,
            CheckerResult.blocks_review == True,
        )
        res = await self.session.execute(stmt)
        blockers = res.scalars().all()
        if blockers:
            raise ReviewValidationError(
                f"Submission cannot be accepted while {len(blockers)} blocking checker result(s) exist.",
            )

    async def get_review(self, review_id: str) -> ReviewSchema | None:
        stmt = (
            select(Review)
            .options(selectinload(Review.findings))
            .where(Review.id == review_id)
        )
        res = await self.session.execute(stmt)
        review = res.scalar_one_or_none()
        if not review:
            return None
        return ReviewSchema.model_validate(review)

    async def get_reviews_for_submission(
        self, submission_id: str,
    ) -> Sequence[ReviewSchema]:
        stmt = (
            select(Review)
            .options(selectinload(Review.findings))
            .where(Review.submission_id == submission_id)
            .order_by(Review.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return [ReviewSchema.model_validate(r) for r in res.scalars().all()]
