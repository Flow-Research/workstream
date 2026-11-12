"""Bounded contribution evidence reads; values convey no disclosure authority."""

from datetime import UTC
from decimal import Decimal
from typing import Literal, Protocol, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_EXPORT_CONTRIBUTIONS = 1_000
MAX_EXPORT_MEMBERS = 100_000
ContributionType = Literal["accepted_submission", "completed_review"]
_STRICT = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")


class ContributionExportUnavailable(RuntimeError):
    """Canonical evidence or exact current read authority cannot be established."""


class ContributionExportTooLarge(ValueError):
    """The complete selection exceeds the snapshot limit; no partial export is valid."""


class InvalidContributionCursor(ValueError):
    """The opaque continuation cannot select an authorized snapshot page."""


class ContributionExportAtCapacity(ValueError):
    """The caller has occupied all five live export allocation slots."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("Contribution export capacity is temporarily unavailable")
        self.retry_after = retry_after


class ContributionReadDenied(RuntimeError):
    """AUTH staged the canonical denial; composition may commit that evidence alone."""


class ContributionReadRequest(BaseModel):
    """Server-bound caller/audience with UTC-aware recorded-time filters."""

    model_config = _STRICT
    audience: Literal["self", "project"]
    actor_profile_id: UUID
    project_id: UUID | None = None
    output_format: Literal["json", "csv"] = "json"
    contribution_type: ContributionType | None = None
    recorded_from: AwareDatetime | None = None
    recorded_before: AwareDatetime | None = None
    limit: int = Field(default=MAX_EXPORT_CONTRIBUTIONS, ge=1, le=MAX_EXPORT_CONTRIBUTIONS)
    cursor: str | None = None

    @field_validator("recorded_from", "recorded_before")
    @classmethod
    def normalized_time(cls, value):
        """Bind equivalent aware filter timestamps to one UTC representation."""
        return None if value is None else value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_scope_and_interval(self) -> Self:
        """Project reads select one project; a half-open time interval cannot invert."""
        if self.audience == "project" and self.project_id is None:
            raise ValueError("project contribution export requires one project")
        if self.recorded_from is not None and self.recorded_before is not None:
            if self.recorded_from >= self.recorded_before:
                raise ValueError("recorded_from must precede recorded_before")
        return self


class ContributionAwardView(BaseModel):
    """Earned immutable terms, without any fulfillment or payment assertion."""

    model_config = _STRICT
    award_id: UUID
    award_definition_id: UUID
    instrument: Literal["money", "project_points"]
    unit: str
    quantity: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+)?$", max_length=40)

    @model_validator(mode="after")
    def validate_exact_quantity(self) -> Self:
        """Retain the positive fixed-point/whole-points bounds of immutable awards."""
        quantity = Decimal(self.quantity)
        scale = -quantity.as_tuple().exponent
        if not 0 < quantity < Decimal("100000000000000000000") or scale > 18 or (
            self.instrument == "project_points" and scale > 0
        ):
            raise ValueError("contribution award quantity exceeds canonical bounds")
        return self


class ContributionRecordView(BaseModel):
    """One recognized record with every applicable award and honest source times."""

    model_config = _STRICT
    contribution_id: UUID
    project_id: UUID
    task_id: UUID
    submission_id: UUID
    contributor_id: UUID
    contributor_display_name: str | None
    contribution_type: ContributionType
    source_review_id: UUID | None
    source_review_lease_id: UUID | None
    source_final_acceptance_id: UUID | None
    source_task_assignment_id: UUID | None
    artifact_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    contribution_policy_version_id: UUID
    policy_version_number: int = Field(gt=0)
    recorded_at: AwareDatetime
    accepted_at: AwareDatetime | None
    acceptance_source: Literal["human_review", "task_post_submit_route"] | None
    acceptance_review_id: UUID | None
    acceptance_routing_manifest_id: UUID | None
    task_title: str
    source_type: str
    source_ref: str | None
    external_task_id: str | None
    awards: tuple[ContributionAwardView, ...] = Field(max_length=1)

    @model_validator(mode="after")
    def validate_source_and_awards(self) -> Self:
        """Keep reviewer acceptance null and forbid duplicate economic identities."""
        accepted = self.contribution_type == "accepted_submission"
        present = (
            self.source_review_id is not None, self.source_review_lease_id is not None,
            self.source_final_acceptance_id is not None, self.source_task_assignment_id is not None,
        )
        if present != (not accepted, not accepted, accepted, accepted):
            raise ValueError("contribution source identity is incomplete")
        if (self.accepted_at is not None) != accepted or (
            self.acceptance_source is not None
        ) != accepted:
            raise ValueError("contribution acceptance time differs from its source")
        source_shape = (self.acceptance_review_id is not None,
                        self.acceptance_routing_manifest_id is not None)
        expected_shape = ((True, False) if self.acceptance_source == "human_review" else
                          (False, True) if accepted else (False, False))
        if source_shape != expected_shape:
            raise ValueError("contribution acceptance source reference differs")
        if len({award.award_id for award in self.awards}) != len(self.awards) or len({
            award.instrument for award in self.awards
        }) != len(self.awards):
            raise ValueError("contribution award identity is duplicated")
        return self


class ContributionExportResponse(BaseModel):
    """One complete bounded page from an authorized contribution selection."""

    model_config = _STRICT
    exported_at: AwareDatetime
    items: tuple[ContributionRecordView, ...] = Field(max_length=MAX_EXPORT_CONTRIBUTIONS)
    next_cursor: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def validate_unique_order(self) -> Self:
        """Stable display order does not claim a cursor or business commit order."""
        keys = [(item.recorded_at, item.contribution_id) for item in self.items]
        if keys != sorted(keys) or len({item.contribution_id for item in self.items}) != len(keys):
            raise ValueError("contribution export order or identity differs")
        award_ids = [award.award_id for item in self.items for award in item.awards]
        if len(set(award_ids)) != len(award_ids):
            raise ValueError("contribution export repeats an award identity")
        return self


class ContributionReadAuthorizationPort(Protocol):
    """Authorize one exact read query in the caller's response transaction."""

    async def authorize(self, request: ContributionReadRequest) -> None:
        """Require human self, covering PM, or exact-project Finance authority."""
        ...


class ContributionExportPort(Protocol):
    """Return only canonical authorized evidence; composition owns commit/isolation."""

    async def read(self, request: ContributionReadRequest) -> ContributionExportResponse:
        """Read and validate every selected owner fact under one database snapshot."""
        ...
