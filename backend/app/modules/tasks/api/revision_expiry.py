"""Exact scheduled revision-expiry target and TASK-owned effect authority."""

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.core.hashing import canonical_json_hash


REVISION_EXPIRY_EVENT = "TaskRevisionExpiryRequested"
REVISION_EXPIRED_EVENT = "TaskRevisionExpired"
REVISION_CONTEXT_BLOCKED_EVENT = "TaskRevisionContextBlocked"


class TaskRevisionExpiryUnavailable(RuntimeError):
    """Concealed invalid, stale, or denied expiry invocation."""


class TaskRevisionExpiryTarget(BaseModel):
    """The original committed failure; a repair may only change its current head."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    source_submission_id: UUID
    routing_manifest_id: UUID
    root_preparation_id: UUID
    root_preparation_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    deadline_at: AwareDatetime


class TaskRevisionExpiryAuthorityFacts(BaseModel):
    """Locked current head and one exact OUTBOX invocation at DB deadline."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    target: TaskRevisionExpiryTarget
    head_preparation_id: UUID
    head_preparation_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    delivery_event_id: UUID
    delivery_generation: int = Field(ge=1, le=2147483647)
    invocation_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    task_status: str
    assignment_status: str

def revision_expiry_resource_digest(facts: TaskRevisionExpiryAuthorityFacts) -> str:
    """Hash the exact validated invocation and TASK scope consumed by AUTH."""
    facts = TaskRevisionExpiryAuthorityFacts.model_validate_json(facts.model_dump_json())
    return canonical_json_hash({"resource_context": {
        "resource_type": "task_authority", "resource_id": str(facts.target.task_id),
        "scope_project_id": str(facts.target.project_id), "facts": facts.model_dump(mode="json"),
    }})


@dataclass(frozen=True, slots=True)
class TaskRevisionExpiryAuthority:
    """Consumed fixed-service decision bound to one expiry resource digest."""
    actor_profile_id: UUID
    decision_id: UUID
    resource_context_digest: str


class PreparedTaskRevisionExpiry(ABC):
    """Process-local authority that must be consumed against the locked facts."""
    def __reduce_ex__(self, _protocol):
        """Prevent serialization of a live authorization capability."""
        raise TypeError("prepared revision-expiry authority is process-local")

    @abstractmethod
    async def consume(self, facts: TaskRevisionExpiryAuthorityFacts) -> TaskRevisionExpiryAuthority:
        """Consume fresh authority for the identical locked expiry facts."""
        ...


class TaskRevisionExpiryIntakePort(Protocol):
    """Caller-authorized participant in the same fenced TASK expiry transaction."""
    async def expire_revision(self, operation_id: UUID, target: TaskRevisionExpiryTarget) -> None:
        """Fence only this assignment's unaccepted intake and retain source charges."""
        ...


class TaskRevisionExpiryAuthorizationPort(Protocol):
    """Prepare fixed-service authority within the caller-owned transaction."""
    def prepare_revision_expiry(
        self, facts: TaskRevisionExpiryAuthorityFacts,
    ) -> AbstractAsyncContextManager[PreparedTaskRevisionExpiry]:
        """Bind one delivery generation and its immutable scheduled deadline."""
        ...


@dataclass(frozen=True, slots=True)
class TaskRevisionExpiryEvidence:
    """Atomic audit facts for the retained rejection and assignment release."""
    facts: TaskRevisionExpiryAuthorityFacts
    authority: TaskRevisionExpiryAuthority
    receipt_id: UUID
    audit_event_id: UUID
    expired_at: AwareDatetime


@dataclass(frozen=True, slots=True)
class TaskRevisionExpiryReceiptSnapshot:
    """TASK-owned immutable receipt facts supplied to AUDIT for replay validation."""

    receipt_id: UUID
    audit_event_id: UUID
    authorization_decision_id: UUID
    routing_manifest_id: UUID
    source_submission_id: UUID
    head_preparation_id: UUID
    expired_at: AwareDatetime
    authority_context: dict[str, object]


class TaskRevisionExpiryAuditPort(Protocol):
    """Record and verify expiry evidence without reading private TASK models."""
    async def read_expiry(self, receipt: TaskRevisionExpiryReceiptSnapshot) -> TaskRevisionExpiryEvidence | None:
        """Verify retained audit evidence against the immutable TASK receipt."""
        ...
    async def record_expiry(self, evidence: TaskRevisionExpiryEvidence) -> UUID:
        """Append the expiry audit in the same transaction as the TASK effect."""
        ...
