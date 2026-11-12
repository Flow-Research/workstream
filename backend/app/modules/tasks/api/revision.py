"""Frozen revision context and bounded contributor change-summary contracts."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_serializer, model_validator

from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from app.modules.contributions.api.reward_selection import RewardSelectionFacts


class RevisionContextSnapshot(BaseModel):
    """One complete activated context, independent of the task's mutable locks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    guide_id: UUID
    activation_operation_id: UUID
    activation_generation: int = Field(gt=0)
    activated_at: AwareDatetime
    lineage: TaskPolicyLineage


class RevisionCandidate(BaseModel):
    """Server-selected context under PROJECT custody; not mutation authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prior: RevisionContextSnapshot
    target: RevisionContextSnapshot | None
    prior_reward_selection: RewardSelectionFacts
    target_reward_selection: RewardSelectionFacts | None
    target_post_policy_json: str | None = Field(default=None, max_length=262144)
    max_revision_rounds: int = Field(ge=0)
    revision_deadline_hours: int = Field(gt=0)
    target_max_revision_rounds: int | None = Field(default=None, ge=0)


    @model_validator(mode="after")
    def exact_reward_context(self) -> Self:
        """Keep each reward under its activation policy and the immutable size."""
        if self.prior_reward_selection.policy_version_id != self.prior.lineage.locked_contribution_policy_version_id:
            raise ValueError("revision prior reward policy differs")
        if (self.target is None) != (self.target_reward_selection is None):
            raise ValueError("revision target reward context is incomplete")
        if self.target is not None and (
            self.target_reward_selection.policy_version_id != self.target.lineage.locked_contribution_policy_version_id
            or self.target_reward_selection.task_size != self.prior_reward_selection.task_size
        ):
            raise ValueError("revision target reward selection differs")
        return self


class RevisionContextChange(BaseModel):
    """One bounded policy identity change, without provider or finance internals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    component: Literal["guide", "source", "artifact", "pre_submit", "post_submit", "review", "revision", "contribution"]
    before: str = Field(min_length=1, max_length=200)
    after: str = Field(min_length=1, max_length=200)


class ContributorRewardSelection(BaseModel):
    """Exact earned terms for revision acknowledgement, without internal bindings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    compensation_mode: Literal["unpaid", "compensated"]
    task_size: Literal["small", "medium", "large"]
    instrument: Literal["money", "project_points"] | None
    unit: str | None
    quantity: str | None


    @model_validator(mode="after")
    def exact_financial_shape(self) -> Self:
        from app.core.financial_wire import require_canonical_quantity

        financial = (self.instrument, self.unit, self.quantity)
        if self.compensation_mode == "unpaid":
            if any(value is not None for value in financial):
                raise ValueError("unpaid revision terms contain financial facts")
        elif any(value is None for value in financial):
            raise ValueError("compensated revision terms are incomplete")
        else:
            require_canonical_quantity(self.quantity, self.instrument)
        return self


    @model_serializer(mode="wrap")
    def serialize_terms(self, handler):
        """Unpaid terms explicitly contain null financial fields on every surface."""
        values = handler(self)
        for field in ("instrument", "unit", "quantity"):
            values.setdefault(field, None)
        return values


class ContributorRevisionContext(BaseModel):
    """Frozen preparation plus an eligibility projection evaluated at database time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    preparation_id: UUID
    preparation_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    predecessor_preparation_id: UUID | None
    source_submission_id: UUID
    source_routing_manifest_id: UUID
    sequence: int = Field(gt=0)
    next_revision_round: int = Field(ge=0)
    max_revision_rounds: int = Field(ge=0)
    requested_at: AwareDatetime
    deadline_at: AwareDatetime | None
    clock_state: Literal["running", "paused"]
    remaining_microseconds: int | None = Field(ge=0)
    outcome: Literal["kept", "rebased", "blocked"]
    disposition: Literal["ready", "context_blocked", "revision_limit_reached", "revision_deadline_expired"]
    direction: Literal["kept", "forward", "backward"] | None
    prior: RevisionContextSnapshot
    target: RevisionContextSnapshot | None
    prior_reward_selection: ContributorRewardSelection
    target_reward_selection: ContributorRewardSelection | None
    changes: tuple[RevisionContextChange, ...] = Field(max_length=8)

    @model_validator(mode="after")
    def clock_shape(self) -> Self:
        """Expose one running deadline or one frozen paused allowance."""
        if self.clock_state == "running":
            if self.deadline_at is None or self.remaining_microseconds is not None:
                raise ValueError("running revision requires a deadline")
        elif (self.deadline_at is not None or self.remaining_microseconds is None
              or self.remaining_microseconds <= 0 or self.outcome != "blocked"
              or self.disposition != "context_blocked"):
            raise ValueError("paused revision requires blocked context and allowance")
        return self

    @model_serializer(mode="wrap")
    def serialize_clock(self, handler):
        """Keep nullable clock facts explicit in routes that omit other nulls."""
        values = handler(self)
        values.setdefault("deadline_at", None)
        values.setdefault("remaining_microseconds", None)
        values.setdefault("target", None)
        values.setdefault("target_reward_selection", None)
        return values
