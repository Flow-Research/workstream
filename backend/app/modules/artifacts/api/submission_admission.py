"""Public ART capability for consuming one verified submission admission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, get_args
from uuid import UUID
import re

from app.core.hashing import canonical_json_hash

from app.modules.tasks.api import TaskSubmissionContextFacts

SubmissionAdmissionConsumptionStatus = Literal["consumed", "stale"]
SubmissionAdmissionConsumptionFailure = Literal[
    "submission_bundle_admission_unavailable",
    "submission_bundle_admission_already_consumed",
    "submission_bundle_admission_context_changed",
    "submission_bundle_admission_stale",
]


class SubmissionAdmissionConsumptionError(RuntimeError):
    """Return one stable ART-owned failure without persistence details."""

    def __init__(self, code: SubmissionAdmissionConsumptionFailure) -> None:
        if code not in get_args(SubmissionAdmissionConsumptionFailure):
            raise ValueError("submission admission failure code is invalid")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SubmissionAdmissionConsumptionRequest:
    """Exact TASK identity and locked lineage supplied to ART for consumption."""

    admission_id: UUID
    submission_id: UUID
    submission_version: int
    task_context: TaskSubmissionContextFacts
    packet_sha256: str
    accepted_operation_id: UUID | None = None

    def __post_init__(self) -> None:
        if type(self.submission_version) is not int or self.submission_version < 1:
            raise ValueError("submission version is invalid")
        if type(self.packet_sha256) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", self.packet_sha256):
            raise ValueError("submission packet digest is invalid")


@dataclass(frozen=True, slots=True)
class ConsumedSubmissionAdmissionRequest:
    """Exact historical ownership selectors, never a current pre-submit context."""

    admission_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    submission_id: UUID
    submission_version: int
    packet_sha256: str

    def __post_init__(self) -> None:
        if any(not isinstance(getattr(self, field), UUID) for field in (
            "admission_id", "project_id", "task_id", "assignment_id", "contributor_id", "submission_id",
        )):
            raise ValueError("consumed admission identity is invalid")
        if type(self.submission_version) is not int or self.submission_version < 1:
            raise ValueError("submission version is invalid")
        if type(self.packet_sha256) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", self.packet_sha256):
            raise ValueError("submission packet digest is invalid")


@dataclass(frozen=True, slots=True)
class SubmissionBundleFile:
    """Detached inspected file metadata, without bytes or storage coordinates."""

    normalized_path: str
    sha256: str
    byte_count: int

    def __post_init__(self) -> None:
        if (
            type(self.normalized_path) is not str or not self.normalized_path
            or len(self.normalized_path.encode("utf-8")) > 4096
            or type(self.sha256) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", self.sha256)
            or type(self.byte_count) is not int or not 0 <= self.byte_count <= 512 * 1024 * 1024
        ):
            raise ValueError("submission file metadata is invalid")


@dataclass(frozen=True, slots=True)
class SubmissionAdmissionMaterial:
    """Verified admission metadata; values alone confer no dispatch authority."""

    archive_sha256: str
    archive_byte_count: int
    semantic_manifest_sha256: str
    files: tuple[SubmissionBundleFile, ...]

    def __post_init__(self) -> None:
        if (
            any(type(value) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", value)
                for value in (self.archive_sha256, self.semantic_manifest_sha256))
            or type(self.archive_byte_count) is not int or self.archive_byte_count < 0
            or type(self.files) is not tuple or len(self.files) > 100_000
            or any(type(item) is not SubmissionBundleFile for item in self.files)
        ):
            raise ValueError("submission admission material is invalid")
        paths = tuple(item.normalized_path for item in self.files)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("submission admission files are not canonical")


@dataclass(frozen=True, slots=True)
class SubmissionAdmissionConsumptionResult:
    """Bounded terminal ART facts returned to transaction composition."""

    admission_id: UUID
    binding_id: UUID | None
    content_id: UUID
    submission_id: UUID
    submission_version: int
    status: SubmissionAdmissionConsumptionStatus
    replayed: bool
    material: SubmissionAdmissionMaterial | None
    binding_decision_id: UUID | None
    selected_post_submit_policy_sha256: str | None = None
    selected_post_submit_policy_body: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if self.status == "consumed":
            if not isinstance(self.binding_decision_id, UUID) or not isinstance(self.binding_id, UUID) or type(self.material) is not SubmissionAdmissionMaterial:
                raise ValueError("consumed admission requires verified material")
        elif self.status != "stale" or self.material is not None or self.binding_id is not None:
            raise ValueError("stale admission has no material")
        if (self.selected_post_submit_policy_sha256 is None) != (
            self.selected_post_submit_policy_body is None
        ):
            raise ValueError("selected POST policy custody is incomplete")
        if self.selected_post_submit_policy_body is not None and (
            self.selected_post_submit_policy_body.get("policy_sha256")
            != self.selected_post_submit_policy_sha256
            or canonical_json_hash(
                {
                    key: value
                    for key, value in self.selected_post_submit_policy_body.items()
                    if key != "policy_sha256"
                }
            )
            != self.selected_post_submit_policy_sha256
        ):
            raise ValueError("selected POST policy custody is invalid")


class SubmissionAdmissionConsumptionPort(Protocol):
    """Consume or stale one locked admission in the caller's root transaction."""

    async def consume(
        self,
        request: SubmissionAdmissionConsumptionRequest,
    ) -> SubmissionAdmissionConsumptionResult:
        """Apply one terminal admission transition without provider I/O."""

    async def read_consumed(
        self, request: ConsumedSubmissionAdmissionRequest,
    ) -> SubmissionAdmissionConsumptionResult:
        """Read scoped retained material and freshly validate its original binding allow."""
