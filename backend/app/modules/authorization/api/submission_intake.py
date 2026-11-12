"""Operation-scoped intake authority; these facts are not a grant or acceptance."""
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class IntakeReservationPreflightFacts:
    """Exact selectors before task eligibility; no final context or grant."""
    operation_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    idempotency_key: UUID
    metadata_sha256: str


@dataclass(frozen=True, slots=True)
class IntakeReservationAuthorityFacts(IntakeReservationPreflightFacts):
    """Canonical locked facts required for the final reservation decision."""
    locked_context_sha256: str
    task_status: Literal["in_progress", "needs_revision"]


@dataclass(frozen=True, slots=True)
class IntakeOperationReadFacts:
    """An actor-owned stored operation, resolved before current-task eligibility."""
    operation_id: UUID
    project_id: UUID
    task_id: UUID
    actor_profile_id: UUID


class IntakeAuthorityDenied(RuntimeError):
    """Concealed intake authorization failure."""


class IntakeAuthorizationPort(Protocol):
    """The caller owns root transactions, product locks and original provenance."""
    async def lock_actor(self, actor_id: UUID, identity_link_id: UUID) -> None: ...
    async def preflight(self, facts: IntakeReservationPreflightFacts) -> None: ...
    async def prepare(self, facts: IntakeReservationAuthorityFacts) -> object: ...
    async def consume(self, handle: object, facts: IntakeReservationAuthorityFacts) -> UUID: ...
    async def authorize_read(self, facts: IntakeOperationReadFacts) -> UUID: ...
    async def restage_denial(self, error: IntakeAuthorityDenied) -> bool: ...
    def close(self) -> None: ...
