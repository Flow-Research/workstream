"""Project Manager reads of a project's guides, their declared documents and stored policy values."""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from app.modules.projects.api.guide_documents import GuideDocumentMediaType, LabeledGuideOriginal

GuideStatus = Literal["draft", "active", "superseded"]
GuideDocumentIngestState = Literal["awaiting_upload", "uploaded"]
_SHA256 = r"^sha256:[0-9a-f]{64}$"
_FROZEN = ConfigDict(extra="forbid", frozen=True)


class ProjectGuideSummary(BaseModel):
    """One guide version of a project, by creation order."""

    model_config = _FROZEN
    guide_id: UUID
    version: str
    status: GuideStatus
    created_at: datetime
    effective_at: datetime | None


class ProjectGuidePage(BaseModel):
    """One page of a project's guides."""

    model_config = _FROZEN
    items: tuple[ProjectGuideSummary, ...]
    next_cursor: str | None


class ProjectGuideRecord(BaseModel):
    """The stored guide record; task example content is not included, only its commitment."""

    model_config = _FROZEN
    guide_id: UUID
    project_id: UUID
    version: str
    status: GuideStatus
    change_summary: str | None
    task_examples_hash: str | None = Field(pattern=_SHA256)
    contribution_policy_id: UUID | None
    contribution_policy_version_id: UUID | None
    activation_operation_id: UUID | None
    approved_by: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    effective_at: datetime | None
    superseded_at: datetime | None


class ProjectGuideDeclaredDocument(BaseModel):
    """A document declared at guide creation and whether its original has been uploaded."""

    model_config = _FROZEN
    document_id: UUID
    label: str
    media_type: GuideDocumentMediaType
    order: int = Field(ge=0)
    ingest_state: GuideDocumentIngestState
    sha256: str | None = Field(pattern=_SHA256)
    byte_count: int | None = Field(gt=0)

    @model_validator(mode="after")
    def uploaded_has_commitment(self):
        """An uploaded original carries its SHA-256 and size; an awaited one carries neither."""
        values = (self.sha256 is not None, self.byte_count is not None)
        if values != ((True, True) if self.ingest_state == "uploaded" else (False, False)):
            raise ValueError("guide document ingest state disagrees with its commitment")
        return self


class GuideReviewPolicyValues(BaseModel):
    """The review policy version a guide selects."""

    model_config = _FROZEN
    policy_id: UUID
    generation: int = Field(gt=0)
    policy_hash: str = Field(pattern=_SHA256)
    human_review_required: StrictBool
    semantics_format: Literal["v1", "v2"]
    semantics_status: Literal["complete", "legacy_incomplete"]
    supersedes_policy_id: UUID | None
    review_preference_window_seconds: int | None
    review_lease_duration_seconds: int | None
    max_active_review_leases_per_reviewer: int | None
    self_review_allowed: bool | None
    reject_policy: str | None
    finding_evidence_requirement: str | None
    allowed_decisions: tuple[Literal["accept", "needs_revision", "reject"], ...]
    minimum_finding_fields: tuple[str, ...]
    created_at: datetime


class GuideRevisionPolicyValues(BaseModel):
    """The revision policy version a guide selects."""

    model_config = _FROZEN
    policy_id: UUID
    generation: int = Field(gt=0)
    policy_hash: str = Field(pattern=_SHA256)
    semantics_status: Literal["complete", "legacy_incomplete"]
    supersedes_policy_id: UUID | None
    max_revision_rounds: int = Field(ge=0)
    revision_deadline_hours: int = Field(ge=1)
    allowed_resubmission_states: tuple[str, ...]
    reviewer_reassignment_rule: str | None
    created_at: datetime


class ProjectGuideDetail(BaseModel):
    """One guide with its declared documents, selected policies and latest setup lineage.

    ``review_policy`` and ``revision_policy`` are the versions the guide
    selects; a draft that has not selected them has none.
    ``latest_compilation_id`` is the current tip of the guide's compilation
    lineage.
    """

    model_config = _FROZEN
    guide: ProjectGuideRecord
    documents: tuple[ProjectGuideDeclaredDocument, ...] = Field(max_length=100)
    review_policy: GuideReviewPolicyValues | None
    revision_policy: GuideRevisionPolicyValues | None
    latest_setup_run_id: UUID | None
    latest_compilation_id: UUID | None


@dataclass(frozen=True, slots=True)
class GuideDocumentSelection:
    """A declared document of a guide in the project; ``original`` is None until it is uploaded."""

    original: LabeledGuideOriginal | None


class ProjectGuideReadUnavailable(RuntimeError):
    """Stored guide facts failed an integrity check; never includes content."""


class ProjectGuideReadPort(Protocol):
    """Read a project's guides inside the caller's authorized read transaction."""

    async def list_guides(
        self, project_id: UUID, *, status: GuideStatus | None,
        after: tuple[datetime, UUID] | None, limit: int,
    ) -> tuple[tuple[ProjectGuideSummary, ...], bool]:
        """Page guides by ``(created_at, id)``; the flag reports another page."""
        ...

    async def guide_in_project(self, project_id: UUID, guide_id: UUID) -> bool:
        """Whether the guide belongs to the project."""
        ...

    async def read_guide(self, project_id: UUID, guide_id: UUID) -> ProjectGuideDetail | None:
        """One guide of the project, or None when it is not in the project."""
        ...

    async def select_document(
        self, project_id: UUID, guide_id: UUID, document_id: UUID,
    ) -> GuideDocumentSelection | None:
        """A declared document of a guide in the project, or None when it is not there."""
        ...


@dataclass(frozen=True, slots=True)
class VerifiedGuideDocumentRead:
    """Fully verified original bytes, valid only within the opening context."""

    document_id: UUID
    media_type: GuideDocumentMediaType
    byte_count: int
    sha256: str
    stream: AsyncIterator[bytes]


class ProjectGuideDocumentContentPort(Protocol):
    """ART verifies an uploaded original against its committed custody before serving it."""

    def open(
        self, project_id: UUID, original: LabeledGuideOriginal,
    ) -> AbstractAsyncContextManager[VerifiedGuideDocumentRead]:
        """Verify and stage the original; raises ``GuideDocumentUnavailable`` on any fault."""
        ...
