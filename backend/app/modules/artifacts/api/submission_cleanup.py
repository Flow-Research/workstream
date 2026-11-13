"""Exact source cleanup selectors; values alone grant no deletion authority."""
from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SubmissionSourceCleanupAuthorityFacts:
    operation_id: UUID
    project_id: UUID
    task_id: UUID
    source_sha256: str
    claim_id: UUID
    claim_generation: int
    phase: Literal["claim", "confirm"]
