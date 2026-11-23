"""Exact source cleanup selectors; values alone grant no deletion authority."""
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from workstream_external_services import ExternalServiceAdapter
from app.modules.artifacts.api.submission_intake import SealedSubmissionSource, SubmissionSourceUpload

SUBMISSION_SOURCE_CLEANUP_CAPABILITY = "submission_source_cleanup"


@dataclass(frozen=True, slots=True)
class SubmissionSourceCleanupAuthorityFacts:
    """Bind cleanup claim or confirmation to an exact operation and source digest."""
    operation_id: UUID
    project_id: UUID
    task_id: UUID
    source_sha256: str
    claim_id: UUID
    claim_generation: int
    phase: Literal["claim", "confirm"]


@dataclass(frozen=True, slots=True)
class SubmissionSourceRemoval:
    """Trusted provider observations; no field by itself releases a charge."""

    source: SealedSubmissionSource
    object_absent: bool
    writes_settled: bool
    parts_absent: bool


class SubmissionSourceCleanupProvider(ExternalServiceAdapter, Protocol):
    """Separate deletion capability supplied only to the audited coordinator."""

    async def remove(self, source: SealedSubmissionSource, upload: SubmissionSourceUpload) -> SubmissionSourceRemoval:
        """Remove exact sealed-source bytes and return independent settlement observations."""
        ...

    def close(self) -> None:
        """Release the separately composed cleanup capability resources."""
        ...
