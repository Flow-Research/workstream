"""Exact hidden assignment reconciliation and scoped feature authority."""

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.core.hashing import canonical_json_hash

ASSIGNMENT_INVALIDATION_EVENT = "TaskAssignmentAuthorityInvalidationRequested"


class AssignmentInvalidationUnavailable(RuntimeError):
    """Concealed unavailable, stale or denied reconciliation."""


class AssignmentInvalidationTarget(BaseModel):
    """Original assignment identity captured by the atomic AUTH producer."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    authority_invalidation_event_id: UUID


class AssignmentInvalidationIntakePort(Protocol):
    """Caller-authorized participant in the fenced assignment release transaction."""

    async def cancel_assignment(self, operation_id: UUID, target: AssignmentInvalidationTarget) -> None:
        """End only this assignment's unaccepted intake and retain source charges."""
        ...


class AssignmentInvalidationAuthorityFacts(BaseModel):
    """Complete effect target consumed under TASK and exact-assignment locks."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    target: AssignmentInvalidationTarget
    cause_event_id: UUID
    delivery_event_id: UUID
    delivery_generation: int = Field(ge=1, le=2147483647)
    cause_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    invocation_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    task_status: str
    locked_context_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


def assignment_invalidation_resource_digest(facts: AssignmentInvalidationAuthorityFacts) -> str:
    """One canonical commitment shared by authorization and immutable receipts."""
    facts = AssignmentInvalidationAuthorityFacts.model_validate(facts.model_dump())
    return canonical_json_hash({"resource_context": {
        "resource_type": "task_authority", "resource_id": str(facts.target.task_id),
        "scope_project_id": str(facts.target.project_id), "facts": facts.model_dump(mode="json"),
    }})


@dataclass(frozen=True, slots=True)
class AssignmentInvalidationAuthority:
    """Exact canonical decision and its complete resource commitment."""

    actor_profile_id: UUID
    decision_id: UUID
    resource_context_digest: str


class PreparedAssignmentInvalidation(ABC):
    """Single-use authority whose lifetime is owned by canonical AUTH/PREP."""

    def __reduce_ex__(self, _protocol):
        raise TypeError("prepared assignment authority is process-local")

    @abstractmethod
    async def consume(
        self, facts: AssignmentInvalidationAuthorityFacts,
    ) -> AssignmentInvalidationAuthority: ...


class AssignmentInvalidationAuthorizationPort(Protocol):
    def prepare_assignment_invalidation(
        self, facts: AssignmentInvalidationAuthorityFacts,
    ) -> AbstractAsyncContextManager[PreparedAssignmentInvalidation]: ...


@dataclass(frozen=True, slots=True)
class AssignmentInvalidationEvidence:
    facts: AssignmentInvalidationAuthorityFacts
    authority: AssignmentInvalidationAuthority


class AssignmentInvalidationAuditPort(Protocol):
    async def read_release(
        self, target: AssignmentInvalidationTarget
    ) -> AssignmentInvalidationEvidence | None:
        """Validate an exact immutable release receipt; never select current work."""
        ...

    async def record_release(self, evidence: AssignmentInvalidationEvidence) -> None: ...


class AssignmentInvalidationTargetsRequest(BaseModel):
    """Fixed bounded keyset projection under originating AUTH serialization."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    contributor_id: UUID
    project_id: UUID | None
    invalidation_event_id: UUID
    invalidated_at: AwareDatetime
    after: UUID | None = None


class AssignmentInvalidationTargetsPage(BaseModel):
    """Detached exact original assignments and the next stable position."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    items: tuple[AssignmentInvalidationTarget, ...]
    next_after: UUID | None


class AssignmentInvalidationTargetsPort(Protocol):
    async def read_assignment_invalidation_targets_page(
        self, request: AssignmentInvalidationTargetsRequest,
    ) -> AssignmentInvalidationTargetsPage: ...
