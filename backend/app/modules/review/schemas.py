"""Pydantic schemas for review decisions and findings."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict

from app.modules.review.models import (
    REVIEW_DECISION_ACCEPT,
    REVIEW_DECISION_NEEDS_REVISION,
    REVIEW_DECISION_REJECT,
    REVIEW_DECISIONS,
    REVIEW_FINDING_SEVERITIES,
)

class ReviewFindingSchema(BaseModel):
    """Schema for a single review finding."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    severity: str = Field(..., description="Severity of the finding (low, medium, high, critical)")
    area: str = Field(..., description="The functional area the finding relates to")
    issue: str = Field(..., description="Detailed description of the issue")
    required_fix: str = Field(..., description="What must be fixed to resolve this finding")
    evidence_ref: str = Field(..., description="Reference to evidence or file location")
    created_at: datetime

class ReviewSchema(BaseModel):
    """Schema for a complete review decision."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    submission_id: str
    reviewer_actor_id: str
    decision: str
    acceptance_evidence_refs: list[str] = Field(default_factory=list)
    comment: str | None = None
    findings: list[ReviewFindingSchema] = []
    created_at: datetime
    updated_at: datetime

class ReviewFindingCreate(BaseModel):
    """Input schema for creating a finding."""
    severity: str = Field(..., pattern="^(low|medium|high|critical)$")
    area: str = Field(..., min_length=1, max_length=100)
    issue: str = Field(..., min_length=1)
    required_fix: str = Field(..., min_length=1)
    evidence_ref: str = Field(..., min_length=1)

class ReviewCreate(BaseModel):
    """Input schema for creating a review."""
    submission_id: str = Field(..., min_length=1)
    decision: str = Field(..., pattern="^(accept|needs_revision|reject)$")
    acceptance_evidence_refs: list[str] = Field(default_factory=list)
    comment: str | None = None
    findings: list[ReviewFindingCreate] = Field(default_factory=list)
