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
    """Stored contributor ownership, resolved before current-task eligibility."""
    operation_id: UUID
    project_id: UUID
    task_id: UUID
    actor_profile_id: UUID


@dataclass(frozen=True, slots=True)
class IntakeOperationReadAccess:
    """Current read projection facts; TASK still owns all submission eligibility."""
    decision_id: UUID
    management: bool
    own_submitter: bool


class IntakeAuthorityDenied(RuntimeError):
    """Concealed intake authorization failure."""


class IntakeOperationReadDenied(IntakeAuthorityDenied):
    """A current operation-read AUTH decision denied and staged its audit evidence."""


class IntakeAuthorizationPort(Protocol):
    """The caller owns root transactions, product locks and original provenance."""
    async def lock_actor(self, actor_id: UUID, identity_link_id: UUID) -> None:
        """Lock the exact actor and identity link before consuming authority."""
        ...
    async def preflight(self, facts: IntakeReservationPreflightFacts) -> None:
        """Check current reservation authority before resolving task eligibility."""
        ...
    async def prepare(self, facts: IntakeReservationAuthorityFacts) -> object:
        """Prepare reservation authority for the exact locked operation facts."""
        ...
    async def consume(self, handle: object, facts: IntakeReservationAuthorityFacts) -> UUID:
        """Consume a prepared reservation decision against unchanged facts."""
        ...
    async def prepare_acceptance(self, facts: IntakeAcceptanceAuthorityFacts) -> object:
        """Prepare operation-scoped T4 authority over the exact PRE result."""
        ...
    async def consume_acceptance(self, handle: object, facts: IntakeAcceptanceAuthorityFacts) -> UUID:
        """Consume T4 authority and return its recorded decision identity."""
        ...
    async def validate_acceptance_receipt(self, facts: IntakeAcceptanceAuthorityFacts, decision_id: UUID) -> None:
        """Validate the stored decision against immutable accepted facts."""
        ...
    async def authorize_read(self, facts: IntakeOperationReadFacts, *, manager: bool = False) -> UUID:
        """Authorize the requested contributor or management operation view."""
        ...
    async def authorize_operation_read(self, facts: IntakeOperationReadFacts) -> IntakeOperationReadAccess:
        """Resolve current operation-read authority and projection visibility."""
        ...
    async def restage_denial(self, error: IntakeAuthorityDenied) -> bool:
        """Restore matching denial evidence after the caller rolls back its root."""
        ...
    def close(self) -> None:
        """Invalidate authority handles when the owning transaction scope ends."""
        ...
