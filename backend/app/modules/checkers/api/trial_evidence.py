"""Exact durable trial subjects shared by CHECKERS, ART and the trusted relay."""

from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

from pydantic import AwareDatetime, Field, StrictInt, model_validator

from app.modules.checkers.api.canonical_values import (
    CheckerValue,
    ResourceId,
    Sha256,
    VersionNumber,
)
from app.modules.checkers.api.external import Identifier, external_checker_json_hash


class TrialEvidenceUnavailable(RuntimeError):
    """Conceal absent, foreign, stale or substituted trial custody."""


class TrialEvidenceStableSubject(CheckerValue):
    """Immutable trial facts independent of the worker that executes or retries."""

    project_id: ResourceId
    task_id: ResourceId
    assignment_id: ResourceId
    submission_id: ResourceId
    submission_version: VersionNumber
    requirement_id: Identifier
    registry_entry_id: ResourceId
    registry_entry_digest: Sha256
    configuration_sha256: Sha256
    trial_kind: Identifier
    slot_index: Annotated[StrictInt, Field(ge=0, le=0)]
    plan_sha256: Sha256
    input_digest: Sha256
    materials_digest: Sha256

    @property
    def address_digest(self) -> str:
        """A changed plan cannot allocate a second row for the same trial slot."""
        return external_checker_json_hash(
            self.model_dump(
                mode="json",
                exclude={"plan_sha256", "input_digest", "materials_digest"},
            )
        )


class TrialEvidenceOrigin(CheckerValue):
    """Original execution provenance, never a reusable lease grant."""

    checker_run_id: ResourceId
    worker_lease_id: ResourceId
    worker_lease_generation: VersionNumber
    worker_lease_expires_at: AwareDatetime
    external_request_digest: Sha256


class TrialEvidenceSelector(CheckerValue):
    """Select the first authorized content at a server-allocated trial address."""

    trial_evidence_id: ResourceId
    project_id: ResourceId
    content_sha256: Sha256


class TrialEvidenceSlot(CheckerValue):
    """One finite private canonical receipt, without provider coordinates."""

    key: Literal["trial_receipt"] = "trial_receipt"
    media_type: Literal["application/json"] = "application/json"
    maximum_bytes: Annotated[StrictInt, Field(ge=1, le=1_048_576)]


class TrialEvidenceReservation(CheckerValue):
    """Detached owner facts; ART independently checks current action authority."""

    selector: TrialEvidenceSelector
    subject: TrialEvidenceStableSubject
    origin: TrialEvidenceOrigin
    slot: TrialEvidenceSlot

    @model_validator(mode="after")
    def exact_project(self):
        """The supplied AUTH scope must match the immutable owner subject."""
        if self.selector.project_id != self.subject.project_id:
            raise ValueError("trial evidence project differs")
        return self

    @property
    def owner_digest(self) -> str:
        """Bind immutable content and bounds without a transient worker lease."""
        return external_checker_json_hash(
            {
                "subject": self.subject.model_dump(mode="json"),
                "slot": self.slot.model_dump(mode="json"),
                "content_sha256": self.selector.content_sha256,
            }
        )

    def select(self, selector: TrialEvidenceSelector) -> TrialEvidenceSlot:
        """Reject changed content or a different owner evidence record."""
        current = TrialEvidenceReservation.model_validate(self)
        if current.selector != TrialEvidenceSelector.model_validate(selector):
            raise TrialEvidenceUnavailable("trial_evidence_reservation_unavailable")
        return current.slot


class TrialEvidenceReservationPort(Protocol):
    """Resolve current owner custody in TASK-before-CHECKERS lock order."""

    async def resolve(self, selector: TrialEvidenceSelector) -> TrialEvidenceReservation:
        """Return exact facts only under fresh trusted invocation authority."""

    async def pin_content(self, selector: TrialEvidenceSelector) -> TrialEvidenceReservation:
        """Pin first content in the same caller transaction as its ART put intent."""


class TrialEvidenceTicket(CheckerValue):
    """Pre-execution address; a pinned receipt must be recovered, never regenerated."""

    trial_evidence_id: ResourceId
    subject: TrialEvidenceStableSubject
    origin: TrialEvidenceOrigin
    slot: TrialEvidenceSlot
    content_sha256: Sha256 | None
    replayed: bool = Field(strict=True)


class TrialEvidenceCustodyAck(CheckerValue):
    """Exact verified ART custody used to recover original receipt bytes."""

    trial_evidence_id: ResourceId
    owner_digest: Sha256
    content_sha256: Sha256
    byte_count: Annotated[StrictInt, Field(ge=1, le=1_048_576)]
    binding_id: ResourceId
    content_id: ResourceId
    put_attempt_id: ResourceId
    verification_receipt_id: ResourceId
    replayed: bool = Field(strict=True)


@dataclass(frozen=True, slots=True)
class TrialEvidenceArtifactRequest:
    """Generated bytes streamed through the existing bounded ART write path."""

    selector: TrialEvidenceSelector
    byte_source: AsyncIterable[bytes]


@dataclass(frozen=True, slots=True)
class TrialEvidenceBindingRequest:
    """Select exact independently verified content for immutable binding."""

    selector: TrialEvidenceSelector
    put_attempt_id: ResourceId
    verification_receipt_id: ResourceId


class TrialEvidenceBindingPort(Protocol):
    """Publish trial evidence inside the caller-owned transaction."""

    async def bind_trial_evidence(
        self,
        request: TrialEvidenceBindingRequest,
    ) -> TrialEvidenceCustodyAck:
        """Bind exact verified content without committing the caller transaction."""
