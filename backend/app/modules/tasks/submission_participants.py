"""Private TASK composition ports; public TASK facts remain dependency-independent."""

from dataclasses import dataclass, field as dataclass_field
from typing import Protocol
from uuid import UUID

from app.modules.checkers.api.pre_submit_material import SubmissionPacketView
from app.modules.checkers.api.external_policy import LockedExternalPostSubmitPolicy
from app.modules.checkers.api.selected_post_submit import SelectedPostSubmissionContent
from app.modules.projects.api import ProjectLockedPolicyContextFacts
from app.modules.tasks.api import TaskSubmissionContextFacts


@dataclass(frozen=True, slots=True)
class SubmissionArtifactAdmissionRequest:
    admission_id: UUID
    submission_id: UUID
    submission_version: int
    task_context: TaskSubmissionContextFacts
    project_context: ProjectLockedPolicyContextFacts
    packet: SubmissionPacketView
    accepted_operation_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SubmissionArtifactBindingFacts:
    binding_id: UUID
    content_id: UUID
    binding_decision_id: UUID
    archive_sha256: str
    byte_count: int
    selected_evaluation_content: SelectedPostSubmissionContent


@dataclass(frozen=True, slots=True)
class SubmissionArtifactAdmissionResult(SubmissionArtifactBindingFacts):
    selected_post_submit_policy: LockedExternalPostSubmitPolicy = dataclass_field(kw_only=True)
    selected_evaluation_content: SelectedPostSubmissionContent

    def __post_init__(self) -> None:
        """Bind the sole POST contract to the policy admitted by ART."""
        if (
            type(self.selected_evaluation_content) is not SelectedPostSubmissionContent
            or self.selected_evaluation_content.policy != self.selected_post_submit_policy
        ):
            raise ValueError("external POST admission policy differs")


@dataclass(frozen=True, slots=True)
class SubmissionArtifactReplayRequest:
    admission_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    submission_id: UUID
    submission_version: int
    packet_sha256: str
    task_context: TaskSubmissionContextFacts


class SubmissionArtifactAdmissionPort(Protocol):
    async def consume(self, request: SubmissionArtifactAdmissionRequest) -> SubmissionArtifactAdmissionResult:
        """Consume once and project real material using already-locked policy facts."""

    async def read_consumed(self, request: SubmissionArtifactReplayRequest) -> SubmissionArtifactBindingFacts:
        """Select and reauthorize retained binding custody without new consumption."""
