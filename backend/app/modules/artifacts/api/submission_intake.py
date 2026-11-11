"""Immutable intake identities; values never confer storage or submit authority.

The operation owner must generate/persist its UUID before creating a source,
authorize every use and compare these values to locked durable facts. Neither a
well-formed source nor its digest proves that an upload or PRE actually occurred.
Delivery credentials and semantic-manifest evidence are deliberately separate.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.api.submission_archive import MAXIMUM_SUBMISSION_ZIP_BYTES


Sha256 = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class _IntakeValue(BaseModel):
    """Closed, frozen values accepting typed Python or canonical JSON input."""

    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, revalidate_instances="always",
    )


class SubmissionIntakeMetadata(_IntakeValue):
    """Exact original command; actor/key namespace and locked policy are separate.

    These selectors are validated structurally only. TASK still checks current
    assignment, actual predecessor and the required revision acknowledgement.
    Empty summary/attestation retain existing nonblocking warning semantics.
    """

    task_id: UUID
    assignment_id: UUID
    predecessor_submission_id: UUID | None = None
    summary: str = Field(default="", max_length=64 * 1024)
    contributor_attestation: str = Field(default="", max_length=64 * 1024)
    revision_preparation_id: UUID | None = None
    revision_preparation_sha256: Sha256 | None = None

    @field_validator("summary", "contributor_attestation")
    @classmethod
    def packet_text(cls, value: str) -> str:
        """Reject unsupported header text rather than silently rewriting it."""
        if value != value.strip() or any(not 32 <= ord(char) <= 126 for char in value):
            raise ValueError("submission packet must be printable ASCII without edge whitespace")
        return value

    @model_validator(mode="after")
    def revision_pair(self) -> Self:
        """Require complete acknowledgement selectors and a revision predecessor."""
        if (self.revision_preparation_id is None) != (self.revision_preparation_sha256 is None):
            raise ValueError("revision acknowledgement requires both selectors")
        if self.predecessor_submission_id is None and self.revision_preparation_id is not None:
            raise ValueError("initial submission cannot acknowledge a revision")
        return self

    def metadata_sha256(self) -> str:
        """Hash exact metadata using one versioned, domain-separated schema."""
        return canonical_json_hash({
            "schema_version": "workstream.submission_intake_metadata.v1",
            **self.model_dump(mode="json"),
        })


class SubmissionSourceLocation(_IntakeValue):
    """Server-selected source address inside the existing claimed ART namespace.

    The namespace ID references ART's existing immutable namespace record. The
    fingerprint and profile must match that record at every owner boundary.
    The singleton ID alone cannot identify storage across deployments. It is
    not a freely selectable endpoint. The adapter applies its configured prefix.
    """

    operation_id: UUID
    namespace_id: Literal["primary"]
    namespace_fingerprint: Sha256
    provider_profile: str = Field(min_length=1, max_length=100)

    @field_validator("operation_id")
    @classmethod
    def record_identity(cls, value: UUID) -> UUID:
        """Check record shape; only the durable owner proves ID provenance."""
        if value.version != 7:
            raise ValueError("submission source requires UUIDv7 record identities")
        return value

    @field_validator("provider_profile")
    @classmethod
    def profile_name(cls, value: str) -> str:
        """Keep the profile an identifier, never a locator or credential."""
        if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in value):
            raise ValueError("submission source provider profile is invalid")
        return value

    @property
    def object_ref(self) -> str:
        """Return the operation-owned relative key without a caller path field."""
        return f"submission-source/v1/{self.operation_id}/bundle.zip"


class SealedSubmissionSource(_IntakeValue):
    """Exact completed object identity, independent of any expiring read grant.

    SHA/count describe original ZIP bytes, not ETag or semantic manifest. The
    generation is opaque: AWS uses VersionId; other providers must qualify an
    equivalent immutable identity. An EOF-only operation cannot construct this
    value until its owner resolves and records complete-object custody.
    """

    location: SubmissionSourceLocation
    provider_generation: str = Field(min_length=1, repr=False)
    raw_sha256: Sha256
    raw_byte_count: int = Field(ge=1, le=MAXIMUM_SUBMISSION_ZIP_BYTES)
    sealed_upload_fence: int = Field(ge=1)
    media_type: Literal["application/zip"] = "application/zip"

    @model_validator(mode="after")
    def versioned_aws_source(self) -> Self:
        """The qualified AWS profile cannot accept an unversioned null version."""
        if self.location.provider_profile == "aws-s3-v1" and self.provider_generation == "null":
            raise ValueError("AWS submission source requires an immutable version")
        return self

    def source_sha256(self) -> str:
        """Bind every durable source fact; never include delivery credentials."""
        return canonical_json_hash({
            "schema_version": "workstream.sealed_submission_source.v1",
            **self.model_dump(mode="json"),
        })


class SubmissionSourceCapacityLimits(_IntakeValue):
    """Explicit physical source allocation; no deployment defaults or logical dedup."""

    maximum_total_bytes: int = Field(ge=1, le=2**63 - 1)
    maximum_project_bytes: int | None = Field(default=None, ge=1, le=2**63 - 1)
    maximum_producer_bytes: int | None = Field(default=None, ge=1, le=2**63 - 1)
    maximum_task_bytes: int | None = Field(default=None, ge=1, le=2**63 - 1)

    def configuration_sha256(self) -> str:
        """Bind the explicit allocation used by every writer in this namespace."""
        return canonical_json_hash({
            "schema_version": "workstream.submission_source_capacity.v1",
            **self.model_dump(mode="json"),
        })
