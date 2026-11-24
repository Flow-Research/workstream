"""Public ART contracts for hidden contributor bundle preparation."""

from __future__ import annotations

from enum import StrEnum
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitExecutionFacts


def public_pre_submission_results(
    facts: SelectedPreSubmitExecutionFacts,
) -> list[dict[str, object]]:
    """Project one bounded PRE outcome for its authorized contributor.

    Blocked and admitted preparations share this projection, so nonblocking
    findings (warnings, info, coverage gaps) stay visible when intake passes.
    It is intake feedback only; post-submission evaluation decides outcomes.
    """
    default = facts.workstream_default
    results: list[dict[str, object]] = [
        {
            "source": "workstream_default",
            "check_id": item.check_id,
            "status": item.status,
            "failure_code": item.failure_code,
            "finding_count": item.finding_count,
        }
        for item in default.checks
    ]
    results.extend(
        {
            "source": "workstream_default",
            "status": "warning",
            "warning_code": item.code,
        }
        for item in default.warnings
    )
    results.extend(
        {
            "source": "project_external_checker",
            "requirement_id": member.requirement_id,
            "registry_entry_id": str(member.registry_entry_id),
            "registry_entry_digest": member.registry_entry_digest,
            "status": member.result.verdict,
            "findings": [
                finding.model_dump(mode="json")
                for finding in member.result.findings
            ],
        }
        for member in facts.external_members
    )
    return results


def pre_submission_finding_counts(facts: SelectedPreSubmitExecutionFacts) -> dict[str, int]:
    """Count the same intake findings ``public_pre_submission_results`` shows.

    A failed default check blocks with its findings; external findings count by level.
    """
    levels = [
        finding.level for member in facts.external_members for finding in member.result.findings
    ]
    return {
        "blocking": sum(
            item.finding_count for item in facts.workstream_default.checks if item.status == "failed"
        ) + levels.count("error"),
        "warning": len(facts.workstream_default.warnings) + levels.count("warning"),
        "coverage_incomplete": levels.count("coverage_incomplete"),
    }


class SubmissionBundlePreparationStatus(StrEnum):
    """Closed public state vocabulary for one ART preparation operation."""

    PREPARED = "prepared"
    PUT_IN_FLIGHT = "put_in_flight"
    OBJECT_CONFIRMED = "object_confirmed"
    STORED_PENDING_VERIFICATION = "stored_pending_verification"
    OBSERVED_CONFIRMED = "observed_confirmed"
    ACKNOWLEDGEMENT_UNKNOWN = "acknowledgement_unknown"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    CONFLICT = "conflict"
    INTEGRITY_MISMATCH = "integrity_mismatch"
    MISSING = "missing"
    ABSENT_REPLAY_REQUIRED = "absent_replay_required"
    STALE = "stale"
    READY = "ready"


PreparationOutcome = Literal["pending", "passed", "failed", "infrastructure_failed"]
PreparationState = Literal[
    "checking", "checks_failed", "infrastructure_failed", "storing", "ready", "submitted", "stale",
]
_FROZEN = ConfigDict(extra="forbid", frozen=True)


class PreparationFindingCounts(BaseModel):
    model_config = _FROZEN
    blocking: int = Field(ge=0)
    warning: int = Field(ge=0)
    coverage_incomplete: int = Field(ge=0)


class SubmissionBundlePreparationSummary(BaseModel):
    """One preparation: intake outcome, storage progress and any created Submission."""

    model_config = _FROZEN
    preparation_id: UUID
    task_id: UUID
    assignment_id: UUID
    outcome: PreparationOutcome
    state: PreparationState
    storage_status: SubmissionBundlePreparationStatus | None
    infrastructure_failure_code: str | None
    archive_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    archive_byte_count: int = Field(gt=0)
    finding_counts: PreparationFindingCounts | None
    admission_id: UUID | None
    submission_id: UUID | None
    created_at: AwareDatetime
    completed_at: AwareDatetime | None


class SubmissionBundlePreparationDetail(SubmissionBundlePreparationSummary):
    """A preparation with every contributor-visible intake finding."""

    findings: list[dict[str, Any]]


class SubmissionBundlePreparationPage(BaseModel):
    model_config = _FROZEN
    items: tuple[SubmissionBundlePreparationSummary, ...]
    next_cursor: str | None


class ProjectSubmissionBundlePreparation(SubmissionBundlePreparationSummary):
    """One preparation in a project with its contributor; finding counts only, no findings or files."""

    actor_profile_id: UUID


class ProjectSubmissionBundlePreparationPage(BaseModel):
    """One page of a project's preparations, newest first."""

    model_config = _FROZEN
    items: tuple[ProjectSubmissionBundlePreparation, ...]
    next_cursor: str | None


class SubmissionBundlePreparationReadPort(Protocol):
    """Read preparations newest first; the caller authorizes."""

    async def read(
        self, *, actor_profile_id: UUID, task_id: UUID, preparation_id: UUID | None,
        limit: int, before: tuple[datetime, UUID] | None,
    ) -> tuple[tuple[SubmissionBundlePreparationDetail, ...], bool]:
        """The caller's own preparations for one task, with findings."""
        ...

    async def read_project(
        self, *, project_id: UUID, outcome: PreparationOutcome | None,
        limit: int, before: tuple[datetime, UUID] | None,
    ) -> tuple[tuple[ProjectSubmissionBundlePreparation, ...], bool]:
        """Every contributor's preparations in one project, without findings."""
        ...
