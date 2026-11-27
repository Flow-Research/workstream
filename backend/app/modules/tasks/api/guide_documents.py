"""TASK-consumer contract for locked guide originals; no provider coordinates."""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.projects.api.guide_reads import ContributorGuideDocument


@dataclass(frozen=True, slots=True)
class TaskGuideSelection:
    """TASK's locked selectors, translated at the owner boundary by its consumer."""

    project_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str


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
