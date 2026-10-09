"""Project-bound canonical JSON source capabilities, without provider coordinates."""

from collections.abc import AsyncIterable, AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskImportSourceAction(StrEnum):
    DECLARE = "artifact.task_import_source.declare"
    UPLOAD = "artifact.task_import_source.upload"
    READ = "artifact.task_import_source.read"


class TaskImportSourceDeclare(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=1, le=8388608)


class TaskImportSourceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    source_id: UUID
    project_id: UUID
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=1, le=8388608)
    media_type: Literal["application/json"] = "application/json"
    status: Literal["declared", "prepared", "put_in_flight", "acknowledgement_unknown", "object_confirmed",
                    "absent_replay_required", "integrity_mismatch", "provider_unavailable", "conflict", "verified", "missing"]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TaskImportSourceAuthorityFacts:
    source_id: UUID
    project_id: UUID
    actor_profile_id: UUID
    sha256: str
    byte_count: int
    operation_identity: str
    idempotency_key: UUID


class TaskImportSourceAuthorityDenied(RuntimeError):
    """Source authority is absent or no longer current."""


class TaskImportSourceAuthorizationPort(Protocol):
    async def authorize(self, action: TaskImportSourceAction, facts: TaskImportSourceAuthorityFacts) -> UUID: ...
    async def restage_denial(self, error: TaskImportSourceAuthorityDenied) -> None: ...


@dataclass(frozen=True, slots=True)
class VerifiedTaskImportSourceRead:
    source: TaskImportSourceResponse
    stream: AsyncIterator[bytes]


class TaskImportSourceCommandPort(Protocol):
    async def declare(self, project_id: UUID, payload: TaskImportSourceDeclare, key: UUID) -> TaskImportSourceResponse: ...
    async def upload(self, project_id: UUID, source_id: UUID, byte_source: AsyncIterable[bytes]) -> TaskImportSourceResponse: ...
    async def status(self, project_id: UUID, source_id: UUID) -> TaskImportSourceResponse: ...
    def open(self, project_id: UUID, source_id: UUID) -> AbstractAsyncContextManager[VerifiedTaskImportSourceRead]: ...
