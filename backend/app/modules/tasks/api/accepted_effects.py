"""Source-neutral TASK participant contract for future final acceptance."""

from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

_Sha256 = Annotated[StrictStr, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
_PositiveVersion = Annotated[StrictInt, Field(ge=1, le=2_147_483_647)]
_Generation = Annotated[StrictInt, Field(ge=0, le=9_223_372_036_854_775_807)]
_STRICT_FROZEN = ConfigDict(
    extra="forbid", frozen=True, strict=True, revalidate_instances="always"
)


class TaskAcceptedEffectsUnavailable(RuntimeError):
    """Conceal absent, foreign, stale, or invalid TASK acceptance state."""


class TaskAcceptedEffectsRequest(BaseModel):
    """Exact TASK identity and lineage selected by the acceptance owner."""

    model_config = _STRICT_FROZEN

    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    submission_id: UUID
    submission_version: _PositiveVersion
    contributor_id: UUID
    contribution_policy_version_id: UUID
    content_id: UUID
    content_sha256: _Sha256
    final_acceptance_id: UUID
    expected_task_status: Literal["evaluation_pending", "review_pending"]


class TaskAcceptedPreparation(BaseModel):
    """Observed TASK disposition and exact locked ReviewPolicy identity."""

    model_config = _STRICT_FROZEN

    disposition: Literal["new", "replay"]
    locked_review_policy_id: UUID


class TaskAcceptedEffectsResult(BaseModel):
    """Exact accepted request identity and the two TASK-owned terminal states."""

    model_config = _STRICT_FROZEN

    request: TaskAcceptedEffectsRequest
    task_status: Literal["accepted"]
    assignment_status: Literal["completed"]


class TaskLifecycleFacts(Protocol):
    """Read-only scalar phase facts from the externally owned canonical fence."""

    @property
    def phase(self) -> str:
        ...

    @property
    def generation(self) -> int:
        ...


class TaskAcceptedEffectsFence(Protocol):
    """Acquire the canonical externally owned lifecycle fence."""

    async def acquire(self, expected_generation: _Generation) -> TaskLifecycleFacts:
        """Retain the expected generation through the caller's transaction."""
        ...


class TaskAcceptedEffectsPort(Protocol):
    """Prepare and apply flush-only TASK effects in one caller transaction.

    The participant never commits, authorizes, creates REV or CON facts, or calls
    back into routing.
    """

    async def lock_accepted_effects(
        self,
        request: TaskAcceptedEffectsRequest,
        *,
        expected_generation: _Generation,
    ) -> TaskAcceptedPreparation:
        """Fence, lock, and report exact new or terminal-replay TASK state."""
        ...

    async def apply_accepted_effects(
        self,
        request: TaskAcceptedEffectsRequest,
        *,
        disposition: Literal["new", "replay"],
        expected_generation: _Generation,
    ) -> TaskAcceptedEffectsResult:
        """Revalidate the observed disposition, then flush terminal effects."""
        ...

    async def require_routing_source(
        self,
        request: TaskAcceptedEffectsRequest,
        manifest_id: UUID,
        *,
        source_authorization_decision_id: UUID,
        recorded_by: UUID,
        locked_review_policy_id: UUID,
        expected_generation: int,
        disposition: Literal["new", "replay"],
    ) -> None:
        """Require an exact stored false-policy TASK routing manifest."""
        ...


__all__ = (
    "TaskAcceptedEffectsPort",
    "TaskAcceptedEffectsFence",
    "TaskAcceptedPreparation",
    "TaskAcceptedEffectsRequest",
    "TaskAcceptedEffectsResult",
    "TaskAcceptedEffectsUnavailable",
)
