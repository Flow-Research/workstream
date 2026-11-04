"""Display-only unified findings; document runtime selectors never cross this API."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    CompilationFinding,
    MAXIMUM_COMPILATION_FINDINGS,
    MAXIMUM_COMPILATION_REQUIREMENTS,
    MAXIMUM_EVIDENCE_REFS,
    ProjectGuideCompilationResult,
)
from app.modules.projects.api.guide_proposals import Digest, GuideProposalTarget


class GuideProposalEvidenceLocation(BaseModel):
    """Human-readable attribution, not a document retrieval capability."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    document_number: Annotated[int, Field(strict=True, ge=1)]
    start_page: int | None
    end_page: int | None
    section: str | None


class GuideProposalFinding(CompilationFinding):
    """Keep canonical finding validation with a display-only source location."""

    evidence_refs: tuple[GuideProposalEvidenceLocation, ...] = Field(
        default=(),
        max_length=MAXIMUM_EVIDENCE_REFS,
    )


class GuideProposalRequirement(AtomicGuideRequirement):
    """Keep requirement semantics without returning runtime document selectors."""

    evidence_refs: tuple[GuideProposalEvidenceLocation, ...] = Field(
        default=(),
        max_length=MAXIMUM_EVIDENCE_REFS,
    )


class GuideProposalDisplayResult(ProjectGuideCompilationResult):
    """The complete validated proposal with only source handles projected away."""

    findings: tuple[GuideProposalFinding, ...] = Field(
        default=(),
        max_length=MAXIMUM_COMPILATION_FINDINGS,
    )
    requirements: tuple[GuideProposalRequirement, ...] = Field(
        default=(),
        max_length=MAXIMUM_COMPILATION_REQUIREMENTS,
    )


class GuideProposalReviewPackage(BaseModel):
    """Exact full proposal and target; currentness grants no mutation authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    target: GuideProposalTarget
    target_digest: Digest
    result: GuideProposalDisplayResult
    current: bool
    artifact_policy_status: Literal["draft", "approved", "superseded"] | None
    warning_hashes: tuple[Digest, ...]
    current_approval_operation_id: UUID | None = None
    current_approval_output_digest: Digest | None = None
    post_submit_policy_id: UUID | None = None
