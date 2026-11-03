"""Read-only contract for original activated-guide evidence."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.projects.api.guide_activation import GuideContributionPolicyFacts
from app.modules.projects.api.guide_activation_context import GuidePolicySelection
from app.modules.projects.api.guide_proposals import GuideProposalApprovalReceipt


def _is_sha256_digest(value: str) -> bool:
    return (
        len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


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
