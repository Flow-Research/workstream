"""Exact ART storage commitments for canonical AUTH preparation."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


_STRICT_FROZEN = ConfigDict(extra="forbid", frozen=True, strict=True)


class ArtifactPutAttemptResourceContext(BaseModel):
    """Exact fenced put-attempt facts composed by ART from locked rows."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["artifact_put_attempt"]
    resource_id: UUID
    operation_identity: str
    namespace_fingerprint: str
    sha256: str
    byte_count: int = Field(ge=0)
    executor_id: UUID
    execution_generation: int = Field(gt=0)


class TaskImportSourceResourceContext(BaseModel):
    """Exact project-bound ART declaration selected under live PM authority."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["task_import_source"] = "task_import_source"
    resource_id: UUID
    scope_project_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=1, le=8388608)
    media_type: Literal["application/json"] = "application/json"
    operation_identity: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    idempotency_key: UUID


class GuideSourceIngestResourceContext(BaseModel):
    """Exact locked guide lineage and server-owned byte facts for ingest."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["project"]
    resource_id: UUID
    scope_project_id: UUID
    guide_id: UUID
    guide_source_snapshot_id: UUID
    guide_source_item_id: UUID
    operation_identity: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=0)
    media_type: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def require_exact_lineage(self):
        """Keep the final resource bound to one concrete project lineage."""
        if self.resource_id != self.scope_project_id:
            raise ValueError("guide ingest project scope must match resource")
        if len({self.guide_source_item_id, self.guide_source_snapshot_id, self.guide_id}) != 3:
            raise ValueError("guide ingest lineage identifiers must be distinct")
        return self


class ArtifactVerificationJobResourceContext(BaseModel):
    """Exact fenced verification-job facts composed by ART from locked rows."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["artifact_verification_job"]
    resource_id: UUID
    replica_id: UUID
    namespace_fingerprint: str
    provider_object_ref: str
    sha256: str
    byte_count: int = Field(ge=0)
    executor_id: UUID
    execution_generation: int = Field(gt=0)


class ArtifactPendingWorkResourceContext(BaseModel):
    """One database-cutoff pending-work page composed only by ART."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["artifact_pending_work"]
    resource_id: Literal["workstream:artifact_pending_work"]
    scanner_kind: Literal["put_resolution_and_verification"]
    database_cutoff_iso: str
    page_size: int = Field(gt=0, le=1000)
    put_attempt_ids: tuple[UUID, ...] = Field(max_length=1000)
    verification_job_ids: tuple[UUID, ...] = Field(max_length=1000)

    @model_validator(mode="after")
    def bind_page_size(self):
        if len(self.put_attempt_ids) + len(self.verification_job_ids) > self.page_size:
            raise ValueError("artifact pending-work page exceeds its bound")
        return self


class GuideSourceReadResourceContext(BaseModel):
    """Exact committed-document facts for one fenced setup-agent provider read."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["guide_source_read"]
    resource_id: UUID
    project_id: UUID
    guide_id: UUID
    guide_source_snapshot_id: UUID
    guide_source_item_id: UUID
    project_setup_run_id: UUID
    setup_generation: int = Field(gt=0)
    compilation_attempt_id: UUID
    manifest_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    document_version_id: UUID
    put_attempt_id: UUID
    content_id: UUID
    replica_id: UUID
    storage_namespace_id: str = Field(min_length=1, max_length=255)
    namespace_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=0)
    media_type: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def bind_source_item(self):
        """Use the exact assigned source item as the prepared resource selector."""
        if self.resource_id != self.guide_source_item_id:
            raise ValueError("guide read resource must match source item")
        return self
