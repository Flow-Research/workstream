"""Closed internal contracts for durable artifact admission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias, final
from uuid import UUID

from app.modules.artifacts.sources import CommittedArtifactSource
from app.modules.authorization.runtime import AuthorizationContext


@final
@dataclass(frozen=True, slots=True)
class GuideArtifactAdmissionRequest:
    """One prepared guide source item admitted under its canonical project."""

    authorization_context: AuthorizationContext
    guide_source_item_id: UUID
    source: CommittedArtifactSource


@final
@dataclass(frozen=True, slots=True)
class ContributorArtifactAdmissionRequest:
    """One prepared contributor item admitted under its upload session."""

    authorization_context: AuthorizationContext
    upload_item_id: UUID
    source: CommittedArtifactSource


@final
@dataclass(frozen=True, slots=True)
class CheckerOutputArtifactAdmissionRequest:
    """One prepared checker output admitted under its exact checker run."""

    authorization_context: AuthorizationContext
    checker_run_id: UUID
    logical_role: str
    source: CommittedArtifactSource


ArtifactAdmissionRequest: TypeAlias = (
    GuideArtifactAdmissionRequest
    | ContributorArtifactAdmissionRequest
    | CheckerOutputArtifactAdmissionRequest
)


@final
@dataclass(frozen=True, slots=True)
class ArtifactAdmissionResult:
    """Committed pre-I/O attempt and its complete admission-charge set."""

    attempt_id: UUID
    status: str
    operation_identity: str
    request_digest: str
    charge_ids: tuple[UUID, ...]
    replayed: bool
