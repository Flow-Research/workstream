"""Hidden shared acceptance values; neither construction nor storage grants authority."""

from contextlib import AbstractAsyncContextManager

from typing import Annotated, Literal, Protocol, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.modules.contributions.api import SubmitterParticipationResult
from app.modules.tasks.api.accepted_effects import TaskAcceptedEffectsRequest, TaskAcceptedEffectsResult

_STRICT = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")


class FinalAcceptanceInput(BaseModel):
    """One exclusive source; retained AUTH and owner validation remain mandatory."""

    model_config = _STRICT

    id: UUID
    project_id: UUID
    task_id: UUID
    submission_id: UUID
    acceptance_source: Literal["human_review", "task_post_submit_route"]
    source_review_id: UUID | None
    source_routing_manifest_id: UUID | None
    accepted_submitter_id: UUID
    recorded_by: UUID
    policy_context_ref: UUID
    source_authorization_decision_id: UUID

    @model_validator(mode="after")
    def exclusive_source(self) -> Self:
        human = self.acceptance_source == "human_review"
        if (self.source_review_id is not None) != human or (
            self.source_routing_manifest_id is not None
        ) == human:
            raise ValueError("acceptance source identity is not exclusive")
        return self


class FinalAcceptanceConflict(RuntimeError):
    """Exact source, lineage, or complete prior effects are unavailable."""


class FinalAcceptanceRequest(BaseModel):
    """Exact proposed effects; values alone grant no source authority."""

    model_config = _STRICT

    acceptance: FinalAcceptanceInput
    task_effects: TaskAcceptedEffectsRequest
    correlation_id: UUID
    expected_generation: Annotated[StrictInt, Field(ge=0, le=9_223_372_036_854_775_807)]

    @model_validator(mode="after")
    def exact_effects(self) -> Self:
        acceptance, task = self.acceptance, self.task_effects
        expected_status = (
            "review_pending" if acceptance.acceptance_source == "human_review"
            else "evaluation_pending"
        )
        if (
            acceptance.id != task.final_acceptance_id
            or acceptance.project_id != task.project_id
            or acceptance.task_id != task.task_id
            or acceptance.submission_id != task.submission_id
            or acceptance.accepted_submitter_id != task.contributor_id
            or task.expected_task_status != expected_status
        ):
            raise ValueError("acceptance effect lineage differs")
        return self


class FinalAcceptanceFacts(FinalAcceptanceInput):
    """Immutable acceptance identity and database-owned timestamp."""

    accepted_at: AwareDatetime


class FinalAcceptanceResult(BaseModel):
    """Exact staged or replayed facts, without a commit or authority claim."""

    model_config = _STRICT

    acceptance: FinalAcceptanceFacts
    task_effects: TaskAcceptedEffectsResult
    participation: SubmitterParticipationResult


class PreparedFinalAcceptance(Protocol):
    """REV-held capability; construction alone grants neither custody nor authority."""

    async def require_new(self) -> None:
        """Require the held generation to admit new effects before AUTH consumption."""
        ...

    async def participate(self, request: FinalAcceptanceRequest) -> FinalAcceptanceResult:
        """Stage exact effects in the caller's fenced root transaction."""
        ...


class FinalAcceptancePort(Protocol):
    """Prepare REV custody before any TASK locks; consume inside the same root."""

    def prepare(
        self, expected_generation: int
    ) -> AbstractAsyncContextManager[PreparedFinalAcceptance]: ...
