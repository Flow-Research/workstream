"""Public PROJECT contracts for exact task-locked policy lineage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import TYPE_CHECKING, Literal, Mapping, Protocol, get_args
from uuid import UUID

from app.modules.projects.api.policy_lineage import ReviewSemanticsFormat, require_complete_policy

if TYPE_CHECKING:
    from .guide_activation import GuideActivationReceipt

ProjectLockedPolicyGuideStatus = Literal["active", "superseded"]
ProjectLockedPolicyEffectiveStatus = Literal["approved", "superseded"]
ProjectLockedPolicyPreSubmitStatus = Literal["compiled", "superseded"]
ProjectLockedPolicyFailure = Literal["project_locked_policy_context_changed"]


def _is_sha256_digest(value: str) -> bool:
    """Return whether one value is a canonical Workstream SHA-256 token."""
    return (
        len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _canonical_json(value: Mapping[str, object]) -> str:
    """Return the Workstream canonical JSON representation of one object."""
    if not isinstance(value, Mapping):
        raise ValueError("canonical JSON object is invalid")
    return json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


@dataclass(frozen=True, slots=True)
class CanonicalJsonObject:
    """Deeply immutable canonical JSON object encoded as text."""

    value: str

    def __post_init__(self) -> None:
        """Reject invalid or non-canonical JSON object text."""
        try:
            decoded = json.loads(self.value)
        except (TypeError, ValueError) as exc:
            raise ValueError("canonical JSON object is invalid") from exc
        if not isinstance(decoded, dict) or _canonical_json(decoded) != self.value:
            raise ValueError("canonical JSON object is invalid")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> CanonicalJsonObject:
        """Copy a mapping into an immutable canonical representation."""
        return cls(_canonical_json(value))

    @property
    def sha256(self) -> str:
        """Return the SHA-256 identity of the canonical UTF-8 bytes."""
        return f"sha256:{hashlib.sha256(self.value.encode('utf-8')).hexdigest()}"


class ProjectLockedPolicyContextUnavailable(RuntimeError):
    """Report a stable failure without exposing PROJECT persistence."""

    def __init__(self, code: ProjectLockedPolicyFailure) -> None:
        """Validate and retain one failure from the public closed set."""
        if code not in get_args(ProjectLockedPolicyFailure):
            raise ValueError("project locked policy failure code is invalid")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ProjectLockedPolicyContextRequest:
    """Exact TASK-stamped PROJECT selectors for locked-context resolution."""

    project_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str
    effective_policy_id: UUID
    effective_policy_hash: str
    pre_submit_policy_id: UUID
    pre_submit_policy_bundle_hash: str

    def __post_init__(self) -> None:
        """Reject empty versions and malformed SHA-256 selectors."""
        if not self.guide_version.strip():
            raise ValueError("project locked policy guide version is empty")
        for value in (
            self.source_snapshot_hash,
            self.effective_policy_hash,
            self.pre_submit_policy_bundle_hash,
        ):
            if not _is_sha256_digest(value):
                raise ValueError("project locked policy hash is invalid")


@dataclass(frozen=True, slots=True)
class ProjectDisplayFacts:
    """Detached current project description; not a policy or authority input."""

    id: UUID
    name: str
    slug: str
    description: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, UUID)
            or not isinstance(self.name, str)
            or not isinstance(self.slug, str)
            or (self.description is not None and not isinstance(self.description, str))
        ):
            raise ValueError("project display facts are invalid")


@dataclass(frozen=True, slots=True)
class GuideDisplayFacts:
    """Detached description of the exact activated historical guide."""

    id: UUID
    project_id: UUID
    version: str
    change_summary: str | None
    effective_at: datetime

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, UUID)
            or not isinstance(self.project_id, UUID)
            or not isinstance(self.version, str)
            or not self.version.strip()
            or (self.change_summary is not None and not isinstance(self.change_summary, str))
            or not isinstance(self.effective_at, datetime)
            or self.effective_at.utcoffset() is None
        ):
            raise ValueError("guide display facts are invalid")


@dataclass(frozen=True, slots=True)
class ProjectLockedPolicyContextFacts:
    """Canonical PROJECT lineage resolved from exact historical locked rows."""

    project_id: UUID
    guide_id: UUID
    guide_version: str
    guide_status: ProjectLockedPolicyGuideStatus
    source_snapshot_id: UUID
    source_snapshot_hash: str
    effective_policy_id: UUID
    effective_policy_hash: str
    effective_policy_status: ProjectLockedPolicyEffectiveStatus
    effective_policy: CanonicalJsonObject
    pre_submit_policy_id: UUID
    pre_submit_policy_bundle_hash: str
    pre_submit_policy_status: ProjectLockedPolicyPreSubmitStatus
    pre_submit_compiler_version: str
    compiled_pre_submit_bundle: CanonicalJsonObject
    activation_receipt: GuideActivationReceipt
    artifact_policy: CanonicalJsonObject
    compiled_post_submit_policy: CanonicalJsonObject
    review_policy: CanonicalJsonObject
    review_semantics_format: ReviewSemanticsFormat
    revision_policy: CanonicalJsonObject
    project: ProjectDisplayFacts
    guide: GuideDisplayFacts

    def __post_init__(self) -> None:
        """Reject lifecycle values outside the closed historical sets."""
        if (
            not self.guide_version.strip()
            or not all(
                _is_sha256_digest(value)
                for value in (
                    self.source_snapshot_hash,
                    self.effective_policy_hash,
                    self.pre_submit_policy_bundle_hash,
                )
            )
            or self.guide_status not in get_args(ProjectLockedPolicyGuideStatus)
            or self.effective_policy_status not in get_args(ProjectLockedPolicyEffectiveStatus)
            or self.pre_submit_policy_status not in get_args(ProjectLockedPolicyPreSubmitStatus)
            or not self.pre_submit_compiler_version.strip()
        ):
            raise ValueError("project locked policy facts are invalid")
        if not all(
            isinstance(value, CanonicalJsonObject)
            for value in (
                self.effective_policy,
                self.compiled_pre_submit_bundle,
                self.artifact_policy,
                self.compiled_post_submit_policy,
                self.review_policy,
                self.revision_policy,
            )
        ):
            raise ValueError("project locked policy bodies must be canonical immutable values")
        from .guide_activation import GuideActivationReceipt

        receipt = GuideActivationReceipt.model_validate(
            self.activation_receipt.model_dump(mode="json")
        )
        if (
            not isinstance(self.project, ProjectDisplayFacts)
            or not isinstance(self.guide, GuideDisplayFacts)
            or self.project.id != self.project_id
            or (self.guide.project_id, self.guide.id, self.guide.version)
            != (self.project_id, self.guide_id, self.guide_version)
            or self.guide.effective_at != receipt.effective_at
        ):
            raise ValueError("project display facts differ from locked context")
        target, upstream = receipt.command.target.proposal, receipt.command.target.upstream
        if (
            (
                self.project_id,
                self.guide_id,
                self.guide_version,
                self.source_snapshot_id,
                self.source_snapshot_hash,
            )
            != (
                target.project_id,
                target.guide_id,
                target.guide_version,
                target.source_snapshot_id,
                target.source_snapshot_hash,
            )
            or (
                self.effective_policy_id,
                self.effective_policy_hash,
                self.pre_submit_policy_id,
                self.pre_submit_policy_bundle_hash,
            )
            != (
                upstream.effective_policy_id,
                upstream.effective_policy_hash,
                upstream.pre_submit_policy_id,
                upstream.pre_submit_bundle_hash,
            )
            or self.effective_policy.sha256 != self.effective_policy_hash
            or self.compiled_pre_submit_bundle.sha256 != self.pre_submit_policy_bundle_hash
            or self.artifact_policy.sha256 != target.artifact_policy_hash
            or self.compiled_post_submit_policy.sha256 != receipt.command.target.policy_hash
        ):
            raise ValueError("project locked policy facts differ from activation")
        require_complete_policy(
            kind="review", status="complete", policy_hash=receipt.command.review.policy_hash,
            semantic_values=json.loads(self.review_policy.value),
            review_semantics_format=self.review_semantics_format,
        )
        require_complete_policy(
            kind="revision", status="complete", policy_hash=receipt.command.revision.policy_hash,
            semantic_values=json.loads(self.revision_policy.value),
        )
        object.__setattr__(self, "activation_receipt", receipt)


class ProjectLockedPolicyContextPort(Protocol):
    """Transaction-bound PROJECT capability for exact locked policy facts."""

    async def read_project_display(self, project_id: UUID) -> ProjectDisplayFacts | None:
        """Read existence and display only, without readiness, flush, commit or row locks."""
        ...

    async def lock_active_policy_context(
        self,
        project_id: UUID,
    ) -> ProjectLockedPolicyContextFacts:
        """Lock the sole active complete guide for a new task context."""

    async def lock_locked_policy_context(
        self,
        request: ProjectLockedPolicyContextRequest,
    ) -> ProjectLockedPolicyContextFacts:
        """Lock, validate, and return exact historical PROJECT facts."""
