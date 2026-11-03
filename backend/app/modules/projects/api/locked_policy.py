"""Public PROJECT contracts for exact task-locked policy lineage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import TYPE_CHECKING, Literal, Mapping, Protocol, get_args
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.projects.api.guide_activation import GuideContributionPolicyFacts
from app.modules.projects.api.guide_activation_context import GuidePolicySelection
from app.modules.projects.api.guide_proposals import GuideProposalApprovalReceipt
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


class _RetainedValue(BaseModel):
    """Closed read shape for pre-specification activation evidence only."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class _RetainedComponentHashes(_RetainedValue):
    sufficiency_hash: str
    artifact_policy_hash: str
    requirement_inventory_hash: str
    pre_submit_hash: str
    post_submit_hash: str
    capability_suggestions_hash: str
    setup_notes_hash: str

    @model_validator(mode="after")
    def exact_digests(self):
        if not all(_is_sha256_digest(value) for value in self.model_dump().values()):
            raise ValueError("retained component hash is invalid")
        return self


class _RetainedProposalTarget(_RetainedValue):
    project_id: UUID
    guide_id: UUID
    compilation_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str
    setup_run_id: UUID
    setup_generation: int
    finalization_id: UUID
    finalization_facts_digest: str
    result_hash: str
    component_hashes: _RetainedComponentHashes
    pre_catalogue_id: str
    pre_catalogue_version: str
    pre_catalogue_schema_version: str
    pre_catalogue_manifest_hash: str
    post_catalogue_id: str
    post_catalogue_version: str
    post_catalogue_schema_version: str
    post_catalogue_manifest_hash: str
    artifact_policy_id: UUID
    artifact_policy_hash: str
    artifact_projection_operation_id: UUID
    artifact_projection_output_digest: str

    @model_validator(mode="after")
    def exact_identity(self):
        if self.setup_generation <= 0 or not all(
            _is_sha256_digest(value)
            for value in (
                self.source_snapshot_hash,
                self.finalization_facts_digest,
                self.result_hash,
                self.pre_catalogue_manifest_hash,
                self.post_catalogue_manifest_hash,
                self.artifact_policy_hash,
                self.artifact_projection_output_digest,
            )
        ):
            raise ValueError("retained proposal identity is invalid")
        return self

    @property
    def digest(self) -> str:
        return canonical_json_hash(self.model_dump(mode="json"))


class _RetainedPostTarget(_RetainedValue):
    proposal: _RetainedProposalTarget
    upstream: GuideProposalApprovalReceipt
    upstream_output_digest: str
    policy_id: UUID
    projection_operation_id: UUID
    policy_hash: str
    predecessor_policy_id: UUID | None

    @model_validator(mode="after")
    def exact_upstream(self):
        if (
            self.upstream.target_digest != self.proposal.digest
            or self.upstream.artifact_policy_id != self.proposal.artifact_policy_id
            or canonical_json_hash(self.upstream.model_dump(mode="json"))
            != self.upstream_output_digest
            or not _is_sha256_digest(self.policy_hash)
        ):
            raise ValueError("retained POST upstream differs")
        return self

    @property
    def digest(self) -> str:
        return canonical_json_hash(self.model_dump(mode="json"))


class _RetainedActivationCommand(_RetainedValue):
    target: _RetainedPostTarget
    post_approval_operation_id: UUID
    post_approval_output_digest: str
    guide_mutation_generation: int
    review: GuidePolicySelection
    revision: GuidePolicySelection
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID
    expected_previous_active_guide_id: UUID | None
    expected_previous_active_guide_generation: int | None
    idempotency_key: UUID

    @model_validator(mode="after")
    def exact_selection(self):
        if (
            self.guide_mutation_generation <= 0
            or not _is_sha256_digest(self.post_approval_output_digest)
            or (self.expected_previous_active_guide_id is None)
            != (self.expected_previous_active_guide_generation is None)
            or (
                self.expected_previous_active_guide_generation is not None
                and self.expected_previous_active_guide_generation <= 0
            )
        ):
            raise ValueError("retained activation selection is invalid")
        return self

    @property
    def digest(self) -> str:
        return canonical_json_hash(self.model_dump(mode="json"))


class RetainedActivationEvidence(_RetainedValue):
    """Original locked activation receipt, valid for evidence reads only."""

    operation_id: UUID
    command: _RetainedActivationCommand
    contribution: GuideContributionPolicyFacts
    activation_generation: int
    effective_at: datetime
    prior_project_status: Literal["draft", "active"]

    @model_validator(mode="after")
    def exact_receipt(self):
        if (
            self.operation_id.version != 7
            or self.activation_generation != self.command.guide_mutation_generation + 1
            or self.effective_at.utcoffset() is None
            or self.contribution.project_id != self.command.target.proposal.project_id
            or self.contribution.contribution_policy_id != self.command.contribution_policy_id
            or self.contribution.contribution_policy_version_id
            != self.command.contribution_policy_version_id
        ):
            raise ValueError("retained activation receipt differs")
        return self


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
    activation_receipt: GuideActivationReceipt | RetainedActivationEvidence
    artifact_policy: CanonicalJsonObject
    compiled_post_submit_policy: CanonicalJsonObject
    external_checker_policies: CanonicalJsonObject
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
                self.external_checker_policies,
                self.review_policy,
                self.revision_policy,
            )
        ):
            raise ValueError("project locked policy bodies must be canonical immutable values")
        from .guide_activation import GuideActivationReceipt

        if isinstance(self.activation_receipt, RetainedActivationEvidence):
            receipt = RetainedActivationEvidence.model_validate(
                self.activation_receipt.model_dump(mode="json")
            )
        else:
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
        from app.modules.checkers.api.external_policy import (
            validate_stored_external_checker_policies,
        )

        external_policies = validate_stored_external_checker_policies(
            json.loads(self.external_checker_policies.value)
        )
        pre_body = json.loads(self.compiled_pre_submit_bundle.value)
        post_body = json.loads(self.compiled_post_submit_policy.value)
        external_hashes_match = (
            external_policies.policies_sha256
            == receipt.command.target.upstream.effective_pre_submit_plan_hash
            and external_policies.pre_submit.model_dump(mode="json") == pre_body
            and external_policies.pre_submit.policy_sha256 == self.pre_submit_policy_bundle_hash
            and external_policies.post_submit.model_dump(mode="json") == post_body
            and external_policies.post_submit.policy_sha256 == receipt.command.target.policy_hash
        )
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
            or not external_hashes_match
            or self.artifact_policy.sha256 != target.artifact_policy_hash
        ):
            raise ValueError("project locked policy facts differ from activation")
        require_complete_policy(
            kind="review",
            status="complete",
            policy_hash=receipt.command.review.policy_hash,
            semantic_values=json.loads(self.review_policy.value),
            review_semantics_format=self.review_semantics_format,
        )
        require_complete_policy(
            kind="revision",
            status="complete",
            policy_hash=receipt.command.revision.policy_hash,
            semantic_values=json.loads(self.revision_policy.value),
        )
        object.__setattr__(self, "activation_receipt", receipt)


class ProjectLockedPolicyContextPort(Protocol):
    """Transaction-bound PROJECT capability for exact locked policy facts."""

    async def observe_review_mode(self, project_id: UUID, review_policy_id: UUID) -> bool | None:
        """Nonlocking branch hint only; mutation must revalidate the complete context."""
        ...

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
