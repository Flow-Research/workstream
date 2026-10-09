"""TASK-consumer contract for locked guide originals; no provider coordinates."""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True, slots=True)
class TaskGuideSelection:
    """TASK's locked selectors, translated at the owner boundary by its consumer."""

    project_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str


class ContributorGuideDocument(BaseModel):
    """Public original identity and task-scoped authorized read reference."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    document_id: UUID
    order: int = Field(ge=0)
    label: str
    media_type: Literal[
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/markdown",
    ]
    byte_count: int = Field(gt=0)
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    read_reference: str


@dataclass(frozen=True, slots=True)
class VerifiedTaskGuideRead:
    """Fully verified immutable bytes, valid only within the owning context."""

    document: ContributorGuideDocument
    stream: AsyncIterator[bytes]


class TaskGuideUnavailable(RuntimeError):
    """Bounded original integrity/unavailability failure without storage details."""


class TaskGuideDocumentNotFound(RuntimeError):
    """The document is not a member of the exact authorized task snapshot."""


class TaskGuideDocumentsPort(Protocol):
    async def list(
        self, task_id: UUID, request: TaskGuideSelection
    ) -> tuple[ContributorGuideDocument, ...]: ...

    def open(
        self, task_id: UUID, document_id: UUID, request: TaskGuideSelection
    ) -> AbstractAsyncContextManager[VerifiedTaskGuideRead]: ...
