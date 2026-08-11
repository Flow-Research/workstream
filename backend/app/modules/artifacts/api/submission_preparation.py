"""Public ART contracts for hidden contributor bundle preparation."""

from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.authorization.api import ActorIdentityFacts


class SubmissionBundlePreparationRejected(RuntimeError):
    """Reject preparation with one stable ART-owned failure code."""


class SubmissionBundlePreparationUnavailable(RuntimeError):
    """Conceal unavailable or denied preparation authority."""


@dataclass(frozen=True, slots=True)
class SubmissionBundlePreparationRequest:
    """One continuous contributor ZIP request with server-owned actor facts."""

    actor: ActorIdentityFacts
    request_id: UUID
    correlation_id: UUID
    task_id: UUID
    assignment_id: UUID
    predecessor_submission_id: UUID | None
    idempotency_key: UUID
    summary: str
    contributor_attestation: str
    media_type: str
    byte_source: AsyncIterable[bytes]


@dataclass(frozen=True, slots=True)
class SubmissionBundlePreparationResult:
    """Bounded preparation result without custody or provider coordinates."""

    put_attempt_id: UUID
    admission_id: UUID | None
    status: str
    replayed: bool


class SubmissionBundlePreparationCommand(Protocol):
    """Prepare one hidden contributor bundle through the sole ART command."""

    async def prepare(
        self, request: SubmissionBundlePreparationRequest
    ) -> SubmissionBundlePreparationResult:
        """Run the continuous fail-closed preparation workflow."""
