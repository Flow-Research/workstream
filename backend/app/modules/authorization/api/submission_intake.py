"""Operation-scoped intake authority; these facts are not a grant or acceptance."""
from dataclasses import dataclass
from datetime import datetime
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
class IntakeAcceptanceAuthorityFacts(IntakeReservationAuthorityFacts):
    """Exact T4 command acceptance; no formal Submission or continuation authority."""
    foreground_lease_id: UUID
    foreground_lease_generation: int
    selected_pre_submit_run_id: UUID
    selected_pre_submit_request_sha256: str
    selected_pre_submit_terminal_sha256: str
    source_sha256: str
    semantic_manifest_sha256: str
    accepted_context_sha256: str
    receipt_sha256: str
    accepted_at: datetime
    predecessor_submission_id: UUID | None
    predecessor_submission_version: int | None
    checker_remediation_manifest_id: UUID | None


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
    async def prepare_acceptance(self, facts: IntakeAcceptanceAuthorityFacts) -> object: ...
    async def consume_acceptance(self, handle: object, facts: IntakeAcceptanceAuthorityFacts) -> UUID: ...
    async def validate_acceptance_receipt(self, facts: IntakeAcceptanceAuthorityFacts, decision_id: UUID) -> None: ...
    async def authorize_read(self, facts: IntakeOperationReadFacts) -> UUID: ...
    async def restage_denial(self, error: IntakeAuthorityDenied) -> bool: ...
    def close(self) -> None: ...
