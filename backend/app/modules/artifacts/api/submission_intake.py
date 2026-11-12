"""Immutable intake identities; values never confer storage or submit authority.

The operation owner must generate/persist its UUID before creating a source,
authorize every use and compare these values to locked durable facts. Neither a
well-formed source nor its digest proves that an upload or PRE actually occurred.
Delivery credentials and semantic-manifest evidence are deliberately separate.
"""

from __future__ import annotations

from typing import Annotated, Literal, Protocol, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

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
    provider_generation: str = Field(min_length=1, max_length=2048, repr=False)
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


class SubmissionIntakePreSourceFacts(_IntakeValue):
    """Detached current T3 custody, not AUTH or a provider read capability.

    Valid only for comparisons in the caller's still-open root transaction.
    Copying this value cannot extend its lease or authorize later source access.
    """

    source: SealedSubmissionSource
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    metadata_sha256: Sha256
    locked_context_sha256: Sha256
    lease_id: UUID
    lease_generation: int = Field(ge=1)
    lease_expires_at: AwareDatetime
    pre_deadline_at: AwareDatetime

    @model_validator(mode="after")
    def bounded_lease(self) -> Self:
        """Reject structurally contradictory lease and immutable upload facts."""
        if (self.lease_expires_at > self.pre_deadline_at
                or self.lease_generation < self.source.sealed_upload_fence):
            raise ValueError("PRE source lease bounds differ")
        return self


class SubmissionIntakePreSourcePort(Protocol):
    """ART exact source participation in an authorized, caller-owned T3 root."""

    async def lock_pre_source(
        self, *, source: SealedSubmissionSource, lease_id: UUID, generation: int,
    ) -> SubmissionIntakePreSourceFacts:
        """Check TASK pointer and live ART source/fence before CHECKERS locks."""
        ...


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


class SubmissionSourceUploadIntent(_IntakeValue):
    """Durably owned bounds before provider initiation; not write authority.

    The implementation supports one in-flight part of at most 16 MiB, separately
    from the 1 MiB ingress/read ceiling and bounded SDK transport overhead.
    Deployment must select a part size and deadline; neither has a default.
    """

    location: SubmissionSourceLocation
    upload_fence: int = Field(ge=1)
    maximum_raw_bytes: int = Field(ge=1, le=MAXIMUM_SUBMISSION_ZIP_BYTES)
    declared_raw_bytes: int | None = Field(default=None, ge=1)
    part_bytes: int = Field(ge=5 * 1024 * 1024, le=16 * 1024 * 1024)
    idle_timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    upload_deadline_at: AwareDatetime

    @model_validator(mode="after")
    def bounded_declaration(self) -> Self:
        """Reject an impossible declaration before sending provider requests."""
        if self.declared_raw_bytes is not None and self.declared_raw_bytes > self.maximum_raw_bytes:
            raise ValueError("declared source length exceeds upload limit")
        return self


class SubmissionSourceUpload(_IntakeValue):
    """Opaque provider handle that the owner persists before sending parts."""

    intent: SubmissionSourceUploadIntent
    provider_upload_id: str = Field(min_length=1, max_length=2048, repr=False)


class SubmissionSourcePart(_IntakeValue):
    """One bounded part receipt; ETag is a completion token, never raw SHA."""

    number: int = Field(ge=1, le=100)
    byte_count: int = Field(ge=1, le=16 * 1024 * 1024)
    provider_etag: str = Field(min_length=1, max_length=1024, repr=False)


class SubmissionSourceCompletion(_IntakeValue):
    """Exact EOF and ordered receipts committed before provider completion."""

    upload: SubmissionSourceUpload
    parts: tuple[SubmissionSourcePart, ...] = Field(min_length=1, max_length=100)
    raw_sha256: Sha256
    raw_byte_count: int = Field(ge=1, le=MAXIMUM_SUBMISSION_ZIP_BYTES)

    @model_validator(mode="after")
    def complete_receipt(self) -> Self:
        """Require a contiguous, bounded multipart sequence and exact EOF count."""
        intent = self.upload.intent
        if (
            self.raw_byte_count > intent.maximum_raw_bytes
            or (intent.declared_raw_bytes is not None
                and self.raw_byte_count != intent.declared_raw_bytes)
            or sum(part.byte_count for part in self.parts) != self.raw_byte_count
            or any(part.number != number for number, part in enumerate(self.parts, 1))
            or any(part.byte_count != intent.part_bytes for part in self.parts[:-1])
            or self.parts[-1].byte_count > intent.part_bytes
        ):
            raise ValueError("source completion does not match bounded EOF")
        return self
