"""Inert typed authorization contracts for the planned REV lifecycle boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.actors.service_identities import ServiceIdentity
from app.modules.authorization.catalogue import ActionId

_STRICT_FROZEN = ConfigDict(extra="forbid", frozen=True, strict=True)
_DIGEST = r"^sha256:[0-9a-f]{64}$"


class ReviewContractExecution(StrEnum):
    """Closed integration modes; none makes a planned action executable."""

    REQUEST_READ = "request_read"
    PREPARED_HUMAN = "prepared_human"
    PREPARED_OPERATOR = "prepared_operator"
    PREPARED_SERVICE = "prepared_service"
    UNSUPPORTED_FUTURE_INTENT = "unsupported_future_intent"


class ReviewDecisionValue(StrEnum):
    """Canonical persisted review decisions."""

    ACCEPT = "accept"
    NEEDS_REVISION = "needs_revision"
    REJECT = "reject"


class ReviewLifecyclePhase(StrEnum):
    """Closed phase labels carried as locked REV facts, not AUTH policy."""

    DISABLED = "disabled"
    SHADOW = "shadow"
    DRAINING = "draining"
    LIVE = "live"


class QueueSelectionMode(StrEnum):
    """Concealed current-work result shape."""

    ACTIVE_LEASE = "active_lease"
    OFFER = "offer"
    NONE = "none"


class ServiceExecutionMode(StrEnum):
    """Closed server-derived modes for fixed-service review contracts."""

    AUTHORITY_INVALIDATION = "authority_invalidation"
    GENERAL = "general"
    DUE_LEASE = "due_lease"
    DUE_PREFERENCE = "due_preference"
    ARTIFACT_REFERENCE = "artifact_reference"
    PROJECTION_REBUILD = "projection_rebuild"


class ReviewLeaseStatus(StrEnum):
    """Closed lease states exposed to later authorization adapters."""

    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"
    CONSUMED = "consumed"
    REVOKED = "revoked"


class ReviewPreferenceStatus(StrEnum):
    """Closed preference states exposed to later authorization adapters."""

    ACTIVE = "active"
    DECLINED = "declined"
    EXPIRED = "expired"
    CONSUMED = "consumed"
    REVOKED = "revoked"


class RevisionPreparationOutcome(StrEnum):
    """Canonical immutable revision-context outcomes."""

    KEPT = "kept"
    REBASED = "rebased"
    BLOCKED = "blocked"


class RevisionPreparationDirection(StrEnum):
    """Canonical direction for a rebased revision context."""

    FORWARD = "forward"
    BACKWARD = "backward"


class RevisionClosureCause(StrEnum):
    """Only approved reasons for closing an exhausted revision obligation."""

    LIMIT_REACHED = "revision_limit_reached"
    DEADLINE_EXPIRED = "revision_deadline_expired"


class RoutingMode(StrEnum):
    """Action-specific operator routing modes."""

    OVERRIDE = "override"
    CORRECT = "correct"
    CLOSE = "close"


class _ReviewContract(BaseModel):
    """Facts common to every inert REV authorization resource contract."""

    model_config = _STRICT_FROZEN

    action_id: ActionId
    lifecycle_phase: ReviewLifecyclePhase
    lifecycle_digest: str = Field(pattern=_DIGEST)


class _ProjectContract(_ReviewContract):
    """Common exact-project scope for REV authorization resource contracts."""

    project_id: UUID


class _QueueLineage(_ProjectContract):
    """Canonical queue, work, actor, grant, and policy lineage."""

    queue_entry_id: UUID
    queue_generation: int = Field(ge=1)
    task_id: UUID
    task_assignment_id: UUID
    submission_id: UUID
    checker_run_id: UUID
    reviewer_actor_profile_id: UUID
    contributor_actor_profile_id: UUID
    reviewer_grant_id: UUID
    review_policy_id: UUID
    review_policy_generation: int = Field(ge=1)
    review_policy_digest: str = Field(pattern=_DIGEST)
    queue_state_digest: str = Field(pattern=_DIGEST)
    no_self_review: Literal[True]

    @field_validator("no_self_review", mode="before")
    @classmethod
    def require_no_self_review_proof(cls, value):
        """Require REV's explicit server-owned no-self-review proof."""
        if value is not True:
            raise ValueError("no-self-review proof must be true")
        return value

    @model_validator(mode="after")
    def require_distinct_reviewer(self):
        """Reject a self-review context even before a later evaluator exists."""
        if self.reviewer_actor_profile_id == self.contributor_actor_profile_id:
            raise ValueError("reviewer and contributor must be distinct")
        return self


class ReviewQueueReadContract(_QueueLineage):
    """Concealed reviewer current-work facts."""

    action_id: Literal[ActionId.REVIEW_QUEUE_READ]
    selection_mode: Literal[QueueSelectionMode.ACTIVE_LEASE, QueueSelectionMode.OFFER]
    review_lease_id: UUID | None = None

    @model_validator(mode="after")
    def bind_selection(self):
        """An active-lease result alone carries a lease selector."""
        if (self.selection_mode is QueueSelectionMode.ACTIVE_LEASE) != (
            self.review_lease_id is not None
        ):
            raise ValueError("current-work selection and lease are inconsistent")
        return self


class ReviewQueueNoneContract(_ProjectContract):
    """Minimal concealed result when the reviewer has no current work."""

    action_id: Literal[ActionId.REVIEW_QUEUE_READ]
    selection_mode: Literal[QueueSelectionMode.NONE]
    reviewer_actor_profile_id: UUID
    reviewer_grant_id: UUID
    review_policy_id: UUID
    review_policy_generation: int = Field(ge=1)
    review_policy_digest: str = Field(pattern=_DIGEST)
    queue_state_digest: str = Field(pattern=_DIGEST)


class ReviewClaimContract(_QueueLineage):
    """Final claim facts after REV locks its canonical lineage."""

    action_id: Literal[ActionId.REVIEW_CLAIM]
    claim_operation_id: UUID
    active_reviewer_lease_count: int = Field(ge=0, le=1)
    reviewer_contribution_policy_id: UUID
    reviewer_contribution_policy_generation: int = Field(ge=1)
    reviewer_contribution_policy_digest: str = Field(pattern=_DIGEST)
    packet_manifest_id: UUID
    packet_manifest_digest: str = Field(pattern=_DIGEST)


class _LeaseContract(_ProjectContract):
    """Canonical final facts shared by exact lease transitions."""

    queue_entry_id: UUID
    review_lease_id: UUID
    lease_generation: int = Field(ge=1)
    reviewer_actor_profile_id: UUID
    task_id: UUID
    submission_id: UUID
    lease_status: ReviewLeaseStatus
    expires_at: AwareDatetime
    lease_state_digest: str = Field(pattern=_DIGEST)


class ReviewReleaseContract(_LeaseContract):
    """Owning-reviewer release facts for one exact active lease."""

    action_id: Literal[ActionId.REVIEW_RELEASE]
    reason: str = Field(min_length=1, max_length=512)


class ReviewLeaseExpiryContract(_LeaseContract):
    """Fixed-service expiry facts for one exact due lease."""

    action_id: Literal[ActionId.REVIEW_LEASE_EXPIRY_RUN]
    service_identity: Literal[ServiceIdentity.REVIEW_LEASE_EXPIRY]
    execution_mode: Literal[ServiceExecutionMode.DUE_LEASE]
    due_boundary: AwareDatetime
    claimed_ids_digest: str = Field(pattern=_DIGEST)
    cursor: str | None = Field(default=None, max_length=512)


class ReviewLeaseForceReleaseContract(_LeaseContract):
    """Reason-bound Operator force-release facts for one exact lease."""

    action_id: Literal[ActionId.REVIEW_LEASE_FORCE_RELEASE]
    reason: str = Field(min_length=1, max_length=512)


class _PreferenceContract(_ProjectContract):
    """Canonical final facts shared by exact reviewer preferences."""

    queue_entry_id: UUID
    preference_id: UUID
    preference_generation: int = Field(ge=1)
    preferred_reviewer_actor_profile_id: UUID
    source_review_id: UUID
    source_submission_id: UUID
    preference_status: ReviewPreferenceStatus
    expires_at: AwareDatetime
    preference_state_digest: str = Field(pattern=_DIGEST)


class ReviewDeclinePreferenceContract(_PreferenceContract):
    """Offered-reviewer decline facts for one exact preference."""

    action_id: Literal[ActionId.REVIEW_DECLINE_PREFERENCE]
    reason: str = Field(min_length=1, max_length=512)


class ReviewPreferenceExpiryContract(_PreferenceContract):
    """Fixed-service expiry facts for one exact due preference."""

    action_id: Literal[ActionId.REVIEW_PREFERENCE_EXPIRY_RUN]
    service_identity: Literal[ServiceIdentity.REVIEW_PREFERENCE_EXPIRY]
    execution_mode: Literal[ServiceExecutionMode.DUE_PREFERENCE]
    due_boundary: AwareDatetime
    claimed_ids_digest: str = Field(pattern=_DIGEST)
    cursor: str | None = Field(default=None, max_length=512)


class _ReviewerPacketContract(_ProjectContract):
    """Exact active-lease and immutable packet lineage for reviewer reads."""

    task_id: UUID
    task_assignment_id: UUID
    submission_id: UUID
    checker_run_id: UUID
    queue_entry_id: UUID
    review_lease_id: UUID
    reviewer_actor_profile_id: UUID
    packet_manifest_id: UUID
    packet_manifest_generation: int = Field(ge=1)
    packet_manifest_digest: str = Field(pattern=_DIGEST)
    artifact_binding_id: UUID
    chain_digest: str = Field(pattern=_DIGEST)


class ReviewContextReadContract(_ReviewerPacketContract):
    """Lease-bounded context-read facts for one immutable review packet."""

    action_id: Literal[ActionId.REVIEW_CONTEXT_READ]


class ReviewChainReadContract(_ReviewerPacketContract):
    """Metadata-only chain-read facts for one authorized subject and cursor."""

    action_id: Literal[ActionId.REVIEW_CHAIN_READ]
    requested_subject_actor_profile_id: UUID
    chain_head_submission_id: UUID
    cursor: str | None = Field(default=None, max_length=512)
    metadata_only: Literal[True]


class _ReviewDecisionContract(_ReviewerPacketContract):
    """Facts shared by mutually exclusive initial and revision decisions."""

    action_id: Literal[ActionId.REVIEW_DECISION]
    review_operation_id: UUID
    decision: ReviewDecisionValue
    finding_count: int = Field(ge=0)
    blocking_finding_count: int = Field(ge=0)
    findings_resolutions_digest: str = Field(pattern=_DIGEST)
    review_policy_id: UUID
    review_policy_generation: int = Field(ge=1)
    review_policy_digest: str = Field(pattern=_DIGEST)
    reviewer_contribution_policy_id: UUID
    reviewer_contribution_policy_generation: int = Field(ge=1)
    reviewer_contribution_policy_digest: str = Field(pattern=_DIGEST)
    artifact_hash: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def require_decision_shape(self):
        """Keep the approved needs-revision blocking-finding invariant explicit."""
        if self.blocking_finding_count > self.finding_count:
            raise ValueError("blocking finding count exceeds finding count")
        if self.decision is ReviewDecisionValue.NEEDS_REVISION and self.blocking_finding_count < 1:
            raise ValueError("needs_revision requires a blocking finding")
        return self


class ReviewDecisionContract(_ReviewDecisionContract):
    """Exact immutable lineage presented for an initial review decision."""

    decision_shape: Literal["initial"]
    predecessor_review_id: Literal[None] = None


class ReviewRevisionDecisionContract(_ReviewDecisionContract):
    """Decision facts for a revised Submission with exact response lineage."""

    decision_shape: Literal["revision"]
    predecessor_review_id: UUID
    predecessor_submission_id: UUID
    revision_episode_id: UUID
    preparation_head_id: UUID
    preparation_head_generation: int = Field(ge=1)
    preparation_head_digest: str = Field(pattern=_DIGEST)
    finding_response_count: int = Field(ge=0)
    finding_response_lineage_digest: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def require_distinct_predecessor(self):
        """Reject a Submission that claims itself as its own predecessor."""
        if self.predecessor_submission_id == self.submission_id:
            raise ValueError("revision predecessor must differ from current submission")
        return self


class ReviewQueueInspectContract(_ProjectContract):
    """Bounded redacted Operator queue-inspection facts."""

    action_id: Literal[ActionId.REVIEW_QUEUE_INSPECT]
    shard: str = Field(min_length=1, max_length=128)
    filter_digest: str = Field(pattern=_DIGEST)
    cursor: str | None = Field(default=None, max_length=512)
    redacted: Literal[True]


class _QueueOperatorContract(_ProjectContract):
    """Canonical queue lineage shared by reason-bound Operator mutations."""

    queue_entry_id: UUID
    queue_generation: int = Field(ge=1)
    task_id: UUID
    submission_id: UUID
    current_routing_digest: str = Field(pattern=_DIGEST)
    current_lease_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=512)


class ReviewQueueRoutingOverrideContract(_QueueOperatorContract):
    """Operator override facts for one exact queue routing generation."""

    action_id: Literal[ActionId.REVIEW_QUEUE_ROUTING_OVERRIDE]
    routing_mode: Literal[RoutingMode.OVERRIDE]
    requested_reviewer_actor_profile_id: UUID


class ReviewQueueRoutingCorrectContract(_QueueOperatorContract):
    """Operator correction facts for one exact invalid routing state."""

    action_id: Literal[ActionId.REVIEW_QUEUE_ROUTING_CORRECT]
    routing_mode: Literal[RoutingMode.CORRECT]
    corrected_routing_digest: str = Field(pattern=_DIGEST)


class ReviewQueueCloseContract(_QueueOperatorContract):
    """Operator closure facts for one exact stale queue entry."""

    action_id: Literal[ActionId.REVIEW_QUEUE_CLOSE]
    routing_mode: Literal[RoutingMode.CLOSE]
    terminal_reason: str = Field(min_length=1, max_length=128)


class _ReconcileContract(_ProjectContract):
    """Bounded shard, trigger, finding, time, and cursor reconciliation facts."""

    action_id: Literal[ActionId.REVIEW_RECONCILE_RUN]
    shard: str = Field(min_length=1, max_length=128)
    trigger: str = Field(min_length=1, max_length=128)
    finding_ids_digest: str = Field(pattern=_DIGEST)
    observed_at: AwareDatetime
    watermark: str = Field(min_length=1, max_length=512)
    cursor: str | None = Field(default=None, max_length=512)


class ReviewAuthorityInvalidationReconcileContract(_ReconcileContract):
    """Authority-invalidation mode bound to its exact fixed service."""

    service_identity: Literal[ServiceIdentity.REVIEW_AUTHORITY_INVALIDATION_RECONCILIATION]
    execution_mode: Literal[ServiceExecutionMode.AUTHORITY_INVALIDATION]


class ReviewGeneralReconcileContract(_ReconcileContract):
    """General reconciliation mode bound to its exact fixed service."""

    service_identity: Literal[ServiceIdentity.REVIEW_RECONCILIATION]
    execution_mode: Literal[ServiceExecutionMode.GENERAL]
    reason: str = Field(min_length=1, max_length=512)


class ReviewArtifactReferenceReconcileContract(_ProjectContract):
    """Exact artifact-reference set facts for the fixed reconciler."""

    action_id: Literal[ActionId.REVIEW_ARTIFACT_REFERENCE_RECONCILE]
    service_identity: Literal[ServiceIdentity.REVIEW_ARTIFACT_REFERENCE_RECONCILIATION]
    execution_mode: Literal[ServiceExecutionMode.ARTIFACT_REFERENCE]
    shard: str = Field(min_length=1, max_length=128)
    review_reference_set_digest: str = Field(pattern=_DIGEST)
    observed_at: AwareDatetime
    watermark: str = Field(min_length=1, max_length=512)
    cursor: str | None = Field(default=None, max_length=512)
    reason: str = Field(min_length=1, max_length=512)


class ReviewProjectionRebuildContract(_ProjectContract):
    """Bounded source-event and watermark facts for projection rebuild."""

    action_id: Literal[ActionId.REVIEW_PROJECTION_REBUILD]
    service_identity: Literal[ServiceIdentity.REVIEW_PROJECTION]
    execution_mode: Literal[ServiceExecutionMode.PROJECTION_REBUILD]
    projection_name: str = Field(min_length=1, max_length=128)
    shard: str = Field(min_length=1, max_length=128)
    source_watermark: str = Field(min_length=1, max_length=512)
    source_event_digest: str = Field(pattern=_DIGEST)
    cursor: str | None = Field(default=None, max_length=512)


class _RevisionEpisodeContract(_ProjectContract):
    """Exact Review-rooted preparation episode and current-head lineage."""

    task_id: UUID
    task_assignment_id: UUID
    source_task_assignment_id: UUID
    prior_submission_id: UUID
    needs_revision_review_id: UUID
    revision_episode_id: UUID
    preparation_head_id: UUID
    preparation_head_generation: int = Field(ge=1)
    preparation_head_digest: str = Field(pattern=_DIGEST)


class ReviewRevisionContextRepairContract(_RevisionEpisodeContract):
    """Covered-project repair facts for one exact repairable preparation head."""

    action_id: Literal[ActionId.REVIEW_REVISION_CONTEXT_REPAIR]
    preparation_head_outcome: RevisionPreparationOutcome
    preparation_head_direction: RevisionPreparationDirection | None = None
    preparation_head_repairable: Literal[True]
    guide_id: UUID
    guide_activation_sequence: int = Field(ge=1)
    review_policy_id: UUID
    review_policy_generation: int = Field(ge=1)
    review_policy_digest: str = Field(pattern=_DIGEST)
    revision_policy_id: UUID
    revision_policy_generation: int = Field(ge=1)
    revision_policy_digest: str = Field(pattern=_DIGEST)
    replacement_task_assignment_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def require_canonical_direction(self):
        """Only rebased preparations carry a forward/backward direction."""
        if (self.preparation_head_outcome is RevisionPreparationOutcome.REBASED) != (
            self.preparation_head_direction is not None
        ):
            raise ValueError("revision preparation outcome and direction are inconsistent")
        return self


class ReviewRevisionObligationCloseContract(_RevisionEpisodeContract):
    """Covered-project closure facts for one proven exhausted obligation."""

    action_id: Literal[ActionId.REVIEW_REVISION_OBLIGATION_CLOSE]
    revision_policy_id: UUID
    revision_policy_generation: int = Field(ge=1)
    revision_policy_digest: str = Field(pattern=_DIGEST)
    revision_round: int = Field(ge=1)
    revision_limit: int | None = Field(default=None, ge=1)
    revision_deadline: AwareDatetime | None = None
    observed_at: AwareDatetime
    reached_cause: RevisionClosureCause

    @model_validator(mode="after")
    def require_reached_boundary(self):
        """Bind the selected closure cause to its frozen server-owned boundary."""
        if self.reached_cause is RevisionClosureCause.LIMIT_REACHED:
            if self.revision_limit is None or self.revision_round < self.revision_limit:
                raise ValueError("revision limit is not reached")
        elif self.revision_deadline is None or self.observed_at < self.revision_deadline:
            raise ValueError("revision deadline is not reached")
        return self


class ReviewRevisionContextLegacyCloseContract(_ProjectContract):
    """Evidence-linked Operator closure facts for unrecoverable legacy context."""

    action_id: Literal[ActionId.REVIEW_REVISION_CONTEXT_LEGACY_CLOSE]
    reconciliation_finding_id: UUID
    task_id: UUID
    task_assignment_id: UUID
    queue_entry_id: UUID | None = None
    recoverable_root_absence_digest: str = Field(pattern=_DIGEST)
    checker_remediation_excluded: Literal[True]
    reason: Literal["legacy_revision_context_unrecoverable"]


class ReviewLifecycleActivationContract(_ReviewContract):
    """Generation-bound adjacent lifecycle-control transition facts."""

    action_id: Literal[ActionId.REVIEW_LIFECYCLE_ACTIVATION_MANAGE]
    singleton_id: UUID
    operation_id: UUID
    expected_generation: int = Field(ge=1)
    current_phase: ReviewLifecyclePhase
    target_phase: ReviewLifecyclePhase
    adjacent_transition_confirmed: Literal[True]
    reviewed_manifest_digest: str = Field(pattern=_DIGEST)
    drain_observations_digest: str = Field(pattern=_DIGEST)
    batch_limit: int = Field(ge=1, le=10_000)
    deadline: AwareDatetime
    reason: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def require_phase_change(self):
        """Reject same-phase requests; legal adjacency remains REV-owned."""
        if self.current_phase is self.target_phase:
            raise ValueError("lifecycle activation must change phase")
        return self


ReviewAuthorizationResourceContract = (
    ReviewQueueReadContract
    | ReviewQueueNoneContract
    | ReviewClaimContract
    | ReviewReleaseContract
    | ReviewLeaseExpiryContract
    | ReviewLeaseForceReleaseContract
    | ReviewDeclinePreferenceContract
    | ReviewPreferenceExpiryContract
    | ReviewContextReadContract
    | ReviewChainReadContract
    | ReviewDecisionContract
    | ReviewRevisionDecisionContract
    | ReviewQueueInspectContract
    | ReviewQueueRoutingOverrideContract
    | ReviewQueueRoutingCorrectContract
    | ReviewQueueCloseContract
    | ReviewAuthorityInvalidationReconcileContract
    | ReviewGeneralReconcileContract
    | ReviewArtifactReferenceReconcileContract
    | ReviewProjectionRebuildContract
    | ReviewRevisionContextRepairContract
    | ReviewRevisionObligationCloseContract
    | ReviewRevisionContextLegacyCloseContract
    | ReviewLifecycleActivationContract
)


@dataclass(frozen=True, slots=True)
class ReviewAuthorizationContractSpec:
    """One closed manifest row; it is metadata, not runtime authority."""

    execution: ReviewContractExecution
    resource_models: tuple[type[BaseModel], ...]


REVIEW_AUTHORIZATION_CONTRACT_BY_ACTION = MappingProxyType(
    {
        ActionId.REVIEW_QUEUE_READ: ReviewAuthorizationContractSpec(
            ReviewContractExecution.REQUEST_READ,
            (ReviewQueueReadContract, ReviewQueueNoneContract),
        ),
        ActionId.REVIEW_CLAIM: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_HUMAN, (ReviewClaimContract,)
        ),
        ActionId.REVIEW_RELEASE: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_HUMAN, (ReviewReleaseContract,)
        ),
        ActionId.REVIEW_DECLINE_PREFERENCE: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_HUMAN, (ReviewDeclinePreferenceContract,)
        ),
        ActionId.REVIEW_PREFERENCE_EXPIRY_RUN: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_SERVICE, (ReviewPreferenceExpiryContract,)
        ),
        ActionId.REVIEW_LEASE_EXPIRY_RUN: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_SERVICE, (ReviewLeaseExpiryContract,)
        ),
        ActionId.REVIEW_CONTEXT_READ: ReviewAuthorizationContractSpec(
            ReviewContractExecution.REQUEST_READ, (ReviewContextReadContract,)
        ),
        ActionId.REVIEW_CHAIN_READ: ReviewAuthorizationContractSpec(
            ReviewContractExecution.REQUEST_READ, (ReviewChainReadContract,)
        ),
        ActionId.REVIEW_FINDING_EVIDENCE_INGEST: ReviewAuthorizationContractSpec(
            ReviewContractExecution.UNSUPPORTED_FUTURE_INTENT, ()
        ),
        ActionId.REVIEW_DECISION: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_HUMAN,
            (ReviewDecisionContract, ReviewRevisionDecisionContract),
        ),
        ActionId.REVIEW_FINDING_RESPONSE_EVIDENCE_INGEST: ReviewAuthorizationContractSpec(
            ReviewContractExecution.UNSUPPORTED_FUTURE_INTENT, ()
        ),
        ActionId.REVIEW_QUEUE_INSPECT: ReviewAuthorizationContractSpec(
            ReviewContractExecution.REQUEST_READ, (ReviewQueueInspectContract,)
        ),
        ActionId.REVIEW_LEASE_FORCE_RELEASE: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_OPERATOR, (ReviewLeaseForceReleaseContract,)
        ),
        ActionId.REVIEW_QUEUE_ROUTING_OVERRIDE: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_OPERATOR, (ReviewQueueRoutingOverrideContract,)
        ),
        ActionId.REVIEW_QUEUE_ROUTING_CORRECT: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_OPERATOR, (ReviewQueueRoutingCorrectContract,)
        ),
        ActionId.REVIEW_QUEUE_CLOSE: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_OPERATOR, (ReviewQueueCloseContract,)
        ),
        ActionId.REVIEW_RECONCILE_RUN: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_SERVICE,
            (ReviewAuthorityInvalidationReconcileContract, ReviewGeneralReconcileContract),
        ),
        ActionId.REVIEW_ARTIFACT_REFERENCE_RECONCILE: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_SERVICE,
            (ReviewArtifactReferenceReconcileContract,),
        ),
        ActionId.REVIEW_PROJECTION_REBUILD: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_SERVICE, (ReviewProjectionRebuildContract,)
        ),
        ActionId.REVIEW_REVISION_CONTEXT_REPAIR: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_HUMAN, (ReviewRevisionContextRepairContract,)
        ),
        ActionId.REVIEW_REVISION_OBLIGATION_CLOSE: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_HUMAN,
            (ReviewRevisionObligationCloseContract,),
        ),
        ActionId.REVIEW_REVISION_CONTEXT_LEGACY_CLOSE: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_OPERATOR,
            (ReviewRevisionContextLegacyCloseContract,),
        ),
        ActionId.REVIEW_LIFECYCLE_ACTIVATION_MANAGE: ReviewAuthorizationContractSpec(
            ReviewContractExecution.PREPARED_OPERATOR, (ReviewLifecycleActivationContract,)
        ),
    }
)


EXTERNAL_REVIEW_AUTHORIZATION_HANDOFFS = MappingProxyType(
    {
        ActionId.ARTIFACT_REVIEW_PACKET_MATERIALIZE: "WS-XINT-002-07A",
        ActionId.ARTIFACT_REVIEW_EVIDENCE_BINDING_CREATE: "future REV-owned intent",
        ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE: "WS-XINT-002-05D",
        ActionId.SUBMISSION_CREATE: "WS-XINT-002-05D",
    }
)


EXISTING_REVIEW_SETUP_CONTRACTS = MappingProxyType(
    {
        ActionId.PROJECT_REVIEW_POLICY_UPDATE: "ProjectReviewPolicyMutationResourceContext",
        ActionId.PROJECT_REVISION_POLICY_UPDATE: "ProjectRevisionPolicyMutationResourceContext",
    }
)
