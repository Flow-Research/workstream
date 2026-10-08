"""Shared lifecycle fence facts, never an authorization capability."""

from enum import StrEnum
from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class JointLifecyclePhase(StrEnum):
    """REV-owned lifecycle vocabulary; transition semantics require its owner."""

    DISABLED = "disabled"
    SHADOW = "shadow"
    LIVE = "live"
    DRAINING = "draining"


class JointLifecycleUnavailable(RuntimeError):
    """The caller cannot obtain the expected canonical lifecycle fence."""


class JointLifecycleControlFacts(BaseModel):
    """Detached state read while the caller's root transaction holds the fence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    singleton_id: UUID
    phase: JointLifecyclePhase
    generation: int = Field(ge=0, le=9_223_372_036_854_775_807)
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_genesis(self):
        """Reject malformed identities and generation-zero activation claims."""
        if self.singleton_id.version != 7:
            raise ValueError("lifecycle singleton must be UUIDv7")
        if self.generation == 0 and self.phase is not JointLifecyclePhase.DISABLED:
            raise ValueError("lifecycle generation zero must be disabled")
        return self


class JointLifecycleMutationFence(Protocol):
    """Serialize through the caller's active root transaction, without committing.

    Facts are mechanical custody, not AUTH or permission to write. The caller
    must retain the transaction through every protected operation and roll back
    after acquisition fails. PostgreSQL rejects managed and raw-SQL savepoints;
    prior root-level queries remain permitted. The native root check retains a
    discarded export snapshot until transaction end, so keep transactions short.
    PostgreSQL two-phase prepare is unsupported.
    """

    async def acquire(self, expected_generation: int) -> JointLifecycleControlFacts:
        """Lock the canonical controller or deny stale/malformed transaction state."""
        ...


class LifecycleTransitionCommand(BaseModel):
    """Exact Operator request; none of these selectors grants authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")

    operation_id: UUID
    singleton_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    expected_generation: int = Field(ge=0, lt=9_223_372_036_854_775_807)
    current_phase: JointLifecyclePhase
    target_phase: JointLifecyclePhase
    reviewed_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    deadline: AwareDatetime
    reason: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_transition_shape(self):
        if self.current_phase == self.target_phase:
            raise ValueError("lifecycle transition must change phase")
        if self.expected_generation == 0 and self.current_phase != JointLifecyclePhase.DISABLED:
            raise ValueError("generation zero must be disabled")
        return self


class LifecycleTransitionFacts(BaseModel):
    """Server-observed state bound to the exact prepared Operator request."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")

    command: LifecycleTransitionCommand
    observations_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class LifecycleTransitionReceipt(BaseModel):
    """Stored transition identity; consuming this value cannot authorize work."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")

    operation_id: UUID
    singleton_id: UUID
    generation: int = Field(gt=0)
    phase: JointLifecyclePhase
    authorization_decision_event_id: UUID
    created_at: AwareDatetime


class LifecycleAuthorityReceipt(BaseModel):
    """Exact AUTH event identity; database custody must verify its actual event."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    decision_event_id: UUID
    resource_context_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class PreparedLifecycleTransition(Protocol):
    """AUTH-owned live Operator custody held before acquiring REV locks."""

    async def consume_new(self, facts: LifecycleTransitionFacts) -> LifecycleAuthorityReceipt:
        """Append exact authorization evidence in the caller's transaction."""
        ...

    async def validate_replay(self, facts: LifecycleTransitionFacts, decision_id: UUID) -> None:
        """Compare retained evidence using fresh authority without another allow."""
        ...


class LifecycleTransitionAuthorization(Protocol):
    """Explicit same-transaction Operator authorization, never an ambient flag."""

    def lock_scope(
        self, command: LifecycleTransitionCommand,
    ) -> AbstractAsyncContextManager[PreparedLifecycleTransition]:
        """Retain exact live system Operator authority until the transaction ends."""
        ...
