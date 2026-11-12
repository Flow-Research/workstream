"""Pydantic schemas for task queue and assignment APIs."""

from __future__ import annotations

from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from app.modules.contributions.api import TaskSize
from app.modules.tasks.api.revision import ContributorRevisionContext
from app.modules.tasks.api import ReadyTaskSummary, ManagementTaskSummary, OperationalTaskSummary

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator, model_serializer

from app.modules.projects.api.guide_activation_context import GuidePolicySelection
from app.modules.projects.api.locked_policy import GuideDisplayFacts, ProjectDisplayFacts
from app.modules.tasks.api.task_detail import ContributorTaskDetail, ManagementTaskDetail
from app.modules.tasks.api.guide_documents import ContributorGuideDocument


class ContributorTaskLifecycle(BaseModel):
    """Current assignment and bounded action hints; executing actions reauthorizes."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    assigned_to_current_actor: bool
    next_actions: tuple[Literal["claim"], ...] = Field(max_length=1)


class _TaskWorkContext(BaseModel):
    """Detached display and exact receipt-selected governing policy identities."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    project: ProjectDisplayFacts
    guide: GuideDisplayFacts
    review_policy: GuidePolicySelection
    revision_policy: GuidePolicySelection
    contribution_policy_version_id: UUID

    @model_validator(mode="after")
    def exact_project(self):
        """Reject display facts belonging to different projects."""
        if self.project.id != self.guide.project_id:
            raise ValueError("work context project differs from guide")
        return self


class ContributorTaskWorkContext(_TaskWorkContext):
    """Contributor work instructions without management data or obsolete economics."""

    task: ContributorTaskDetail
    lifecycle: ContributorTaskLifecycle
    guide_documents: tuple[ContributorGuideDocument, ...]
    revision_context: ContributorRevisionContext | None = None

    @model_validator(mode="after")
    def exact_task(self):
        """Keep the task audience and project exact without response redaction."""
        if type(self.task) is not ContributorTaskDetail or self.task.project_id != self.project.id:
            raise ValueError("contributor work context task is invalid")
        return self


class ManagementTaskWorkContext(_TaskWorkContext):
    """Manager work instructions and provenance without contributor action hints."""

    task: ManagementTaskDetail

    @model_validator(mode="after")
    def exact_task(self):
        """Keep management facts scoped to the context project."""
        if type(self.task) is not ManagementTaskDetail or self.task.project_id != self.project.id:
            raise ValueError("management work context task is invalid")
        return self


class TaskCreate(BaseModel):
    """Request schema for creating a draft task."""

    model_config = ConfigDict(extra="forbid")

    title: str
    description: str
    task_size: TaskSize = "small"
    task_type: str | None = None
    difficulty: str | None = None
    skill_tags: list[str] = Field(default_factory=list)
    estimated_time_minutes: int | None = Field(default=None, ge=1)
    source_type: Literal["manual", "markdown_import", "csv_import"] = "manual"
    source_ref: str | None = None
    source_payload_hash: str | None = None
    import_batch_id: str | None = None
    external_task_id: str | None = None
    acceptance_criteria: str | None = None
    rejection_criteria: str | None = None
    deadline_at: datetime | None = None


class ImportedTaskCreate(TaskCreate):
    """Server-stamped JSON creation values; not a public manual-create request."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_type: Literal["json_import"] = "json_import"


class TaskTransitionRequest(BaseModel):
    """Optional request body for task lifecycle transitions."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=1000)


class TaskRevisionRepairRequest(BaseModel):
    """Exact frozen parent and PM explanation for one controlled repair."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    parent_preparation_id: UUID | None = None
    parent_preparation_sha256: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    routing_manifest_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def meaningful_reason(self):
        if not self.reason.strip() or len(self.reason.strip().encode("utf-8")) > 1000:
            raise ValueError("revision repair reason is required")
        if not (
            (self.parent_preparation_id is not None and self.parent_preparation_sha256 is not None
             and self.routing_manifest_id is None)
            or (self.parent_preparation_id is None and self.parent_preparation_sha256 is None
                and self.routing_manifest_id is not None)
        ):
            raise ValueError("revision repair requires one exact parent or missing-root source")
        return self


class AdmissionBackedSubmissionCreate(BaseModel):
    """Contributor packet and selectors for the canonical ready-admission POST."""

    model_config = ConfigDict(extra="forbid")

    admission_id: UUID
    assignment_id: UUID
    predecessor_submission_id: UUID | None = None
    summary: str | None = None
    contributor_attestation: str | None = None


class AdmissionBackedSubmissionResponse(BaseModel):
    """Stable Workstream result without provider or scratch coordinates."""

    model_config = ConfigDict(extra="forbid")

    submission_id: UUID
    submission_version: int
    admission_id: UUID
    evaluation_request_id: UUID


class TaskResponse(BaseModel):
    """Response schema for task records."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    project_id: str
    task_size: TaskSize | None = None
    locked_contribution_policy_version_id: UUID | None
    locked_guide_version: str | None
    locked_review_policy_id: str | None
    locked_review_policy_generation: int | None
    locked_review_policy_hash: str | None
    locked_revision_policy_id: str | None
    locked_revision_policy_generation: int | None
    locked_revision_policy_hash: str | None
    locked_guide_source_snapshot_id: str | None
    locked_guide_source_snapshot_hash: str | None
    locked_effective_project_submission_artifact_policy_id: str | None
    locked_effective_project_submission_artifact_policy_hash: str | None
    locked_pre_submit_checker_policy_id: str | None
    locked_pre_submit_checker_bundle_hash: str | None
    source_type: str
    source_ref: str | None
    source_payload_hash: str | None
    import_batch_id: str | None
    external_task_id: str | None
    title: str
    description: str
    task_type: str | None
    difficulty: str | None
    skill_tags: list[str]
    estimated_time_minutes: int | None
    status: str
    acceptance_criteria: str | None
    rejection_criteria: str | None
    deadline_at: datetime | None
    created_by: str | None
    assigned_to: str | None
    created_at: datetime
    updated_at: datetime

    @model_serializer(mode="wrap")
    def recorded_fields(self, handler):
        """Preserve an old saved response's absent size without rewriting its JSON."""
        result = handler(self)
        if "task_size" not in self.model_fields_set:
            result.pop("task_size", None)
        return result


class ContributorClaimTaskResponse(BaseModel):
    """Claim task facts without management-only source or policy coordinates."""

    model_config = ConfigDict(from_attributes=True, extra="forbid", frozen=True)

    id: str
    project_id: str
    locked_contribution_policy_version_id: UUID | None
    locked_guide_version: str | None
    locked_review_policy_id: str | None
    locked_review_policy_generation: int | None
    locked_review_policy_hash: str | None
    locked_revision_policy_id: str | None
    locked_revision_policy_generation: int | None
    locked_revision_policy_hash: str | None
    source_type: str
    title: str
    description: str
    task_type: str | None
    difficulty: str | None
    skill_tags: list[str]
    estimated_time_minutes: int | None
    status: str
    acceptance_criteria: str | None
    rejection_criteria: str | None
    deadline_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskImportBatchRequest(BaseModel):
    """Select one native verified source; all Task provenance is server-stamped."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID


class TaskImportBatchResponse(BaseModel):
    """Immutable original ordered creation facts, also returned after Tasks advance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    batch_id: UUID
    project_id: UUID
    source_id: UUID
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(ge=1, le=8388608)
    schema_version: Literal["workstream.task_import.v1"]
    mapping_version: Literal["workstream.task_import.draft_mapping.v1"]
    label: str | None = Field(default=None, min_length=1, max_length=255)
    row_count: int = Field(ge=1, le=500)
    created_at: datetime
    tasks: tuple[TaskResponse, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def original_creation_custody(self):
        """Reject foreign, duplicate or relabelled original Task creation responses."""
        if len(self.tasks) != self.row_count or len({task.id for task in self.tasks}) != self.row_count:
            raise ValueError("batch creation result has invalid membership")
        external_ids = {task.external_task_id for task in self.tasks}
        if None in external_ids or len(external_ids) != self.row_count:
            raise ValueError("batch creation result has invalid external IDs")
        for task in self.tasks:
            if (task.project_id != str(self.project_id) or task.status != "draft"
                    or task.source_type != "json_import"
                    or task.source_ref != f"task-import-source:{self.source_id}"
                    or task.source_payload_hash != self.sha256 or task.import_batch_id != str(self.batch_id)):
                raise ValueError("batch creation result differs from original custody")
        return self


class TaskImportBatchCurrentTask(BaseModel):
    """Current lifecycle state selected solely by immutable native membership."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: UUID
    row_index: int = Field(ge=0, le=499)
    status: str = Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")


class TaskImportBatchStatus(BaseModel):
    """Separate original creation facts from the current member lifecycle states."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    creation: TaskImportBatchResponse
    current_tasks: tuple[TaskImportBatchCurrentTask, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def exact_current_membership(self):
        """Keep the current projection in the same original document row order."""
        if (len(self.current_tasks) != self.creation.row_count
                or any(row.row_index != index or str(row.task_id) != self.creation.tasks[index].id
                       for index, row in enumerate(self.current_tasks))):
            raise ValueError("current Task projection differs from native membership")
        return self


class RequiredArtifactRequirement(BaseModel):
    """Contributor-facing required artifact rule from the locked effective policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    key: str
    path: str
    hash_required: bool
    required: bool
    description: str | None = None


class RequiredEvidenceRequirement(BaseModel):
    """Contributor-facing required evidence rule from the locked effective policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    key: str
    label: str
    hash_required: bool
    required: bool
    description: str | None = None


class ForbiddenArtifactRequirement(BaseModel):
    """Contributor-facing forbidden artifact rule from the locked effective policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    pattern: str
    reason: str | None = None
    worker_facing_fix: str | None = None
    severity: str | None = None


class StorageReferenceRules(BaseModel):
    """Contributor-facing storage-reference constraints for staged artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    allowed_storage_schemes: tuple[str, ...]
    allowed_uri_prefixes: tuple[str, ...]
    credentials_allowed: bool
    query_strings_allowed: bool
    fragments_allowed: bool
    path_traversal_allowed: bool


class SubmissionPackagingRequirements(BaseModel):
    """Fixed packaging requirements from the historical effective policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    package_required: bool
    allowed_package_formats: tuple[Literal["zip", "tar", "tar.gz", "tar.zst"], ...] | None = None


class _TaskSubmissionRequirements(BaseModel):
    """Contributor-safe exact submission requirements for a locked task."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    task_id: UUID
    project_id: UUID
    guide_version: str = Field(pattern=r"\S")
    policy_schema_version: str | None
    merge_algorithm_version: str | None
    required_packet_fields: tuple[str, ...]
    required_artifacts: tuple[RequiredArtifactRequirement, ...]
    required_evidence: tuple[RequiredEvidenceRequirement, ...]
    forbidden_artifacts: tuple[ForbiddenArtifactRequirement, ...]
    attestation_terms: tuple[str, ...]
    manifest_required: bool
    artifact_hash_required: bool
    artifact_hash_algorithm: Literal["sha256"]
    allowed_storage_schemes: tuple[str, ...]
    storage_reference_rules: StorageReferenceRules
    maximum_file_size_bytes: int | None
    maximum_package_size_bytes: int | None
    maximum_archive_entries: int | None
    maximum_archive_size_bytes: int | None
    packaging: SubmissionPackagingRequirements


class ContributorTaskSubmissionRequirements(_TaskSubmissionRequirements):
    """Contributor-safe intake requirements without policy internals or actors."""


class ManagementTaskSubmissionRequirements(_TaskSubmissionRequirements):
    """Separate management requirements; no additional private fields are needed."""


class PostSubmitPolicyBodySummary(BaseModel):
    """Detached immutable summary of the exact locked post-submit policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: str | None
    default_checkers: tuple[str, ...]
    required_checkers: tuple[str, ...]
    warning_checkers: tuple[str, ...]
    execution_checkers: tuple[str, ...]
    blocking_severities: tuple[str, ...]


class _TaskLockedContextReferences(TaskPolicyLineage):
    """Exact TASK/project selectors alongside the shared immutable policy lineage."""

    task_id: UUID
    project_id: UUID


class ManagementTaskLockedContext(_TaskLockedContextReferences):
    """Management provenance plus the bounded historical checker summary."""

    locked_post_submit_checker_policy_body_summary: PostSubmitPolicyBodySummary


class OperationalTaskLockedContext(_TaskLockedContextReferences):
    """Operational provenance references; no policy body or private task details."""


class AuditTaskLockedContext(_TaskLockedContextReferences):
    """Audit provenance references; evidence and policy-body reads are separate."""


class AssignmentResponse(BaseModel):
    """Response schema for task assignments."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    project_id: str
    submitter_contribution_policy_version_id: UUID
    contributor_id: str
    assigned_by: str
    assigned_at: datetime
    accepted_at: datetime | None
    released_at: datetime | None
    status: str


class TaskWithAssignmentResponse(BaseModel):
    """Response schema for a task operation that creates or uses an assignment."""

    model_config = ConfigDict(extra="forbid")

    task: TaskResponse
    assignment: AssignmentResponse


class TaskClaimResponse(BaseModel):
    """Public claim projection; internal command receipts keep their full shape."""

    model_config = ConfigDict(from_attributes=True, extra="forbid", frozen=True)

    task: ContributorClaimTaskResponse
    assignment: AssignmentResponse


class ContributorTaskQueueResponse(BaseModel):
    """A live ready page; its cursor neither reserves work nor conveys authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    project_id: UUID
    items: tuple[ReadyTaskSummary, ...]
    next_cursor: str | None


class ManagementTaskQueueResponse(BaseModel):
    """Project planning facts with a bounded continuation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    project_id: UUID
    items: tuple[ManagementTaskSummary, ...]
    next_cursor: str | None


class OperationalTaskQueueResponse(BaseModel):
    """Status-only project discovery, excluding management and work content."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    project_id: UUID
    items: tuple[OperationalTaskSummary, ...]
    next_cursor: str | None
