"""Exact source cleanup selectors; values alone grant no deletion authority."""
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workstream_external_services import ExternalServiceAdapter
from app.core.hashing import canonical_json_hash
from app.modules.artifacts.api.submission_archive import MAXIMUM_SUBMISSION_ZIP_BYTES
from app.modules.artifacts.api.submission_intake import (
    SealedSubmissionSource, SubmissionSourceUpload, SubmissionSourceUploadIntent,
    SubmissionSourceCompletion, SubmissionSourceLocation, Sha256,
)

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


class UnsealedSubmissionSource(BaseModel):
    """Exact unfinished write custody; never a completed-object or read grant."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    kind: Literal["unsealed"] = "unsealed"
    location: SubmissionSourceLocation
    upload_fence: int | None = Field(default=None, ge=1)
    provider_upload_id: str | None = Field(default=None, min_length=1, max_length=2048, repr=False)
    raw_sha256: Sha256 | None = None
    raw_byte_count: int | None = Field(default=None, ge=1, le=MAXIMUM_SUBMISSION_ZIP_BYTES)

    @model_validator(mode="after")
    def receipt_shape(self):
        if self.upload_fence is None and (self.provider_upload_id is not None or self.raw_sha256 is not None):
            raise ValueError("unsealed source requires initiation custody")
        if (self.raw_sha256 is None) != (self.raw_byte_count is None):
            raise ValueError("unsealed EOF identity must be complete")
        if self.raw_sha256 is not None and self.provider_upload_id is None:
            raise ValueError("unsealed EOF requires a recorded upload handle")
        return self

    def source_sha256(self) -> str:
        """Bind the unfinished obligation without inventing a provider generation."""
        return canonical_json_hash({"schema_version": "workstream.unsealed_submission_source.v1",
                                    **self.model_dump(mode="json")})


@dataclass(frozen=True, slots=True)
class UnsealedSourceCleanupInput:
    """Provider input recovered under an exact committed cleanup claim."""

    source: UnsealedSubmissionSource
    intent: SubmissionSourceUploadIntent | None
    upload: SubmissionSourceUpload | None
    completion: SubmissionSourceCompletion | None

    def __post_init__(self):
        if self.source.upload_fence is None:
            if any(value is not None for value in (self.intent, self.upload, self.completion)):
                raise ValueError("uninitiated cleanup has no provider input")
            return
        if (self.intent is None or self.intent.location != self.source.location
                or self.intent.upload_fence != self.source.upload_fence):
            raise ValueError("unsealed cleanup intent differs")
        if self.source.provider_upload_id is None:
            if self.upload is not None:
                raise ValueError("unsealed cleanup handle differs")
        elif (self.upload is None or self.upload.intent != self.intent
              or self.upload.provider_upload_id != self.source.provider_upload_id):
            raise ValueError("unsealed cleanup handle differs")
        if self.source.raw_sha256 is None:
            if self.completion is not None:
                raise ValueError("unsealed cleanup EOF differs")
        elif (self.completion is None or self.completion.upload != self.upload
              or self.completion.raw_sha256 != self.source.raw_sha256
              or self.completion.raw_byte_count != self.source.raw_byte_count):
            raise ValueError("unsealed cleanup EOF differs")


def cleanup_target_sha256(source, observed_source=None) -> str:
    """Bind a later exact version as well as its original unfinished obligation."""
    if observed_source is None:
        return source.source_sha256()
    return canonical_json_hash({
        "schema_version": "workstream.observed_submission_source_cleanup.v1",
        "source": source.model_dump(mode="json"),
        "observed_source": observed_source.model_dump(mode="json"),
    })


@dataclass(frozen=True, slots=True)
class SubmissionSourceRemoval:
    """Trusted provider observations; no field by itself releases a charge."""

    source: SealedSubmissionSource | UnsealedSubmissionSource
    object_absent: bool
    writes_settled: bool
    parts_absent: bool
    observed_source: SealedSubmissionSource | None = None


class SubmissionSourceCleanupProvider(ExternalServiceAdapter, Protocol):
    """Separate deletion capability supplied only to the audited coordinator."""

    async def remove(self, source: SealedSubmissionSource, upload: SubmissionSourceUpload) -> SubmissionSourceRemoval:
        """Remove exact sealed-source bytes and return independent settlement observations."""
        ...

    async def remove_unsealed(self, value: UnsealedSourceCleanupInput) -> SubmissionSourceRemoval:
        """Reclaim exact unfinished obligations; unresolved writes retain their charge."""
        ...

    def close(self) -> None:
        """Release the separately composed cleanup capability resources."""
        ...


# The sweep interval/age are specification policy. Batch/timing values below
# must be supplied explicitly by the deployment, not inferred from scratch work.
SUBMISSION_SOURCE_SWEEP_SECONDS = 12 * 60 * 60
SUBMISSION_SOURCE_CLEANUP_HARD_LIMIT_SECONDS = 360



class SubmissionSourceCleanupProfile(BaseModel):
    """Explicit finite worker envelope; no unqualified operational defaults."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    maximum_candidates: int = Field(ge=1, le=1000)
    run_seconds: int = Field(ge=1, le=300)
    lease_seconds: int = Field(ge=1, le=300)
    upload_principal: str | None = Field(default=None, min_length=1, max_length=512)

    @model_validator(mode="after")
    def ordered_bounds(self):
        if self.lease_seconds > self.run_seconds:
            raise ValueError("cleanup lease exceeds sweep execution envelope")
        return self
