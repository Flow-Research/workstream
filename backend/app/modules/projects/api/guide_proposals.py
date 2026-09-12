"""Exact, bounded contracts for hidden unified proposal review and decisions."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.projects.api.compilation_identity import CompilationComponentHashes

Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class GuideProposalSelection(BaseModel):
    """Select a compilation explicitly; never silently substitute the latest one."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    project_id: UUID
    guide_id: UUID
    compilation_id: UUID


class GuideProposalTarget(GuideProposalSelection):
    """The exact displayed source and all independently approved components."""

    guide_version: str = Field(min_length=1, max_length=50)
    source_snapshot_id: UUID
    source_snapshot_hash: Digest
    setup_run_id: UUID
    setup_generation: Annotated[int, Field(strict=True, gt=0)]
    finalization_id: UUID
    finalization_facts_digest: Digest
    result_hash: Digest
    component_hashes: CompilationComponentHashes
    pre_catalogue_id: str = Field(min_length=1, max_length=160)
    pre_catalogue_version: str = Field(min_length=1, max_length=100)
    pre_catalogue_schema_version: str = Field(min_length=1, max_length=160)
    pre_catalogue_manifest_hash: Digest
    post_catalogue_id: str = Field(min_length=1, max_length=160)
    post_catalogue_version: str = Field(min_length=1, max_length=100)
    post_catalogue_schema_version: str = Field(min_length=1, max_length=160)
    post_catalogue_manifest_hash: Digest
    artifact_policy_id: UUID | None
    artifact_policy_hash: Digest | None
    artifact_projection_operation_id: UUID | None
    artifact_projection_output_digest: Digest | None

    @model_validator(mode="after")
    def complete_policy_identity(self):
        """A blocked proposal has no policy; a ready one has the complete tuple."""
        values = (
            self.artifact_policy_id,
            self.artifact_policy_hash,
            self.artifact_projection_operation_id,
            self.artifact_projection_output_digest,
        )
        if any(value is None for value in values) and not all(value is None for value in values):
            raise ValueError("artifact policy identity must be complete or absent")
        return self

    @property
    def digest(self) -> str:
        """Bind the complete displayed identity with one canonical digest."""
        return canonical_json_hash(self.model_dump(mode="json"))


class GuideProposalApproval(BaseModel):
    """Approve only the displayed target, with an exact warning acknowledgment."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    target: GuideProposalTarget
    idempotency_key: UUID
    acknowledged_warning_hashes: tuple[Digest, ...] = Field(default=(), max_length=200)
    expected_previous_approval_operation_id: UUID | None = None
    expected_previous_approval_output_digest: Digest | None = None

    @model_validator(mode="after")
    def complete_previous_approval(self):
        """Bind replacement to both the prior operation and its immutable output."""
        if (self.expected_previous_approval_operation_id is None) != (
            self.expected_previous_approval_output_digest is None
        ):
            raise ValueError("previous approval identity must be complete or absent")
        if len(set(self.acknowledged_warning_hashes)) != len(self.acknowledged_warning_hashes):
            raise ValueError("warning acknowledgments must be unique")
        return self


class GuideProposalCorrection(BaseModel):
    """Request correction of a known finalized result, not an uncertain attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    target: GuideProposalTarget
    idempotency_key: UUID
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        """Normalize feedback while rejecting controls and unrepresentable text."""
        normalized = unicodedata.normalize("NFC", value).strip()
        if not normalized or any(
            unicodedata.category(char) in {"Cc", "Cs"} and char not in "\n\t" for char in normalized
        ):
            raise ValueError("correction reason must be bounded meaningful text")
        if len(normalized.encode("utf-8")) > 16000:
            raise ValueError("correction reason exceeds its byte limit")
        return normalized


class GuideProposalApprovalReceipt(BaseModel):
    """Immutable approval output identity; product rows keep their lifecycle."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    target_digest: Digest
    artifact_policy_id: UUID
    effective_policy_id: UUID
    effective_policy_hash: Digest
    pre_submit_policy_id: UUID
    pre_submit_bundle_hash: Digest
    effective_pre_submit_plan_hash: Digest
    acknowledged_warning_hashes: tuple[Digest, ...] = Field(max_length=200)


class GuideProposalCorrectionReceipt(BaseModel):
    """One successor allocated for an exact known predecessor."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    target_digest: Digest
    successor_setup_run_id: UUID
    successor_setup_generation: Annotated[int, Field(strict=True, gt=0)]
    feedback_hash: Digest
    status: Literal["correction_requested"] = "correction_requested"


class GuideProposalError(RuntimeError):
    """Bounded failure; the caller must roll back its root transaction."""

    def __init__(
        self,
        code: Literal[
            "authority_unavailable",
            "proposal_unavailable",
            "proposal_stale",
            "approval_blocked",
            "operation_conflict",
            "storage_unavailable",
        ],
    ) -> None:
        self.code = code
        super().__init__(code)
