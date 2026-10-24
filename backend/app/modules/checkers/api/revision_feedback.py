"""Bounded retained checker feedback for an authorized revision evaluation."""

from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from app.modules.checkers.api.canonical_values import (
    CheckerValue,
    ResourceId,
    Sha256,
    VersionNumber,
    canonical_checker_bytes,
)
from app.modules.checkers.api.external import ExternalCheckerFinding
from app.modules.checkers.api.selected_post_submit import SelectedPostSubmitCurrentResultReference

# Leave room for current task/material facts inside the one-MiB external input.
MAX_REVISION_FEEDBACK_BYTES = 524_288


class RevisionFeedbackRequest(CheckerValue):
    """Exact historical completion selector supplied by TASK composition; no authority."""

    project_id: ResourceId
    task_id: ResourceId
    assignment_id: ResourceId
    submission_id: ResourceId
    submission_version: VersionNumber
    completion_event_id: ResourceId
    result: SelectedPostSubmitCurrentResultReference


class RevisionFeedbackMember(CheckerValue):
    """Complete normalized findings and their immutable policy/image provenance."""

    order: Annotated[int, Field(strict=True, ge=0)]
    requirement_id: Annotated[str, Field(strict=True, min_length=1, max_length=100)]
    registry_entry_id: ResourceId
    registry_entry_digest: Sha256
    configuration_sha256: Sha256
    request_digest: Sha256
    result_digest: Sha256
    verdict: Literal["passed", "failed"]
    findings: tuple[ExternalCheckerFinding, ...] = Field(max_length=256)


class RevisionFeedback(CheckerValue):
    """An all-or-nothing retained result projection, not a new work verdict."""

    source: RevisionFeedbackRequest
    policy_sha256: Sha256
    members: tuple[RevisionFeedbackMember, ...]

    @model_validator(mode="after")
    def complete_bounded_feedback(self) -> Self:
        """Reject oversized or internally inconsistent feedback without truncating it."""
        if (
            tuple(member.order for member in self.members) != tuple(range(len(self.members)))
            or len({member.requirement_id for member in self.members}) != len(self.members)
            or any(
                (member.verdict == "failed")
                != any(finding.level == "error" for finding in member.findings)
                for member in self.members
            )
            or len(canonical_checker_bytes(self)) > MAX_REVISION_FEEDBACK_BYTES
        ):
            raise ValueError("revision feedback is incomplete or exceeds its bound")
        return self


class RevisionFeedbackPort(Protocol):
    """Read historical CHECKERS facts after caller authority and TASK custody."""

    async def read(self, request: RevisionFeedbackRequest) -> RevisionFeedback:
        """Resolve exact retained evidence without following today's submission fence."""
        ...
