"""Typed, privacy-bounded authority audit inputs."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
import json
import re
from typing import Annotated, Any, Literal, Self

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.authorization.catalogue import (
    ACTION_BY_ID,
    ACTION_IDS,
    NEW_PERMISSION_IDS,
    PERMISSION_IDS,
    ActionAvailability,
    ActionId,
    PermissionId,
)

_ENTITY_TYPES = frozenset(
    {
        "actor_profile",
        "actor_identity_link",
        "admin_role_grant",
        "qualification_snapshot",
        "project_role_grant",
        "authorization_decision",
        "authority_invalidation",
    }
)
_RESOURCE_TYPES = frozenset(
    """task_post_submit_routing_manifest joint_lifecycle_control checker_run outbox_event actor_profile actor_identity_link admin_role_grant project qualification_snapshot project_role_grant task
    submission submission_creation submission_binding review contribution compensation_award compensation_delivery compensation_adapter_binding contribution_policy operations
    audit_event project_create_operation project_submission_artifact_policy_mutation
    project_guide_activation pre_submit_checker_input project_guide_compilation_request
    project_guide_compilation_attempt project_guide_sufficiency_projection
    project_submission_artifact_policy_projection project_guide_setup_finalization
    project_guide_compilation_review_package project_guide_compilation_correction
    project_post_submit_checker_policy_mutation""".split()
)
_UUID_TARGET_KINDS = frozenset(
    {
        "joint_lifecycle_control",
        "actor_profile",
        "actor_identity_link",
        "admin_role_grant",
        "qualification_snapshot",
        "project_role_grant",
    }
)
_TARGET_REF_KINDS = _UUID_TARGET_KINDS | {"project"}
_DENIAL_CODES = frozenset(
    """required_scope_missing unsupported_subject_kind service_actor_not_provisioned
    identity_link_revoked actor_suspended actor_deactivated permission_not_granted
    scope_not_authorized self_grant_forbidden self_role_revoke_forbidden resource_guard_denied
    actor_not_found grant_not_found resource_not_found actor_already_suspended actor_not_suspended
    actor_deactivated_terminal last_access_administrator admin_role_grant_exists
    project_role_grant_exists project_role_grant_already_revoked
    project_role_grant_replay_state_changed identity_link_conflict identity_link_already_revoked
    identity_link_not_revoked resource_project_mismatch idempotency_mismatch
    invalid_role_scope invalid_project_role qualification_snapshot_invalid""".split()
)
_ADMIN_ROLES = frozenset(
    {"access_administrator", "operator", "project_manager", "finance_authority", "audit_authority"}
)
_PROJECT_ROLES = frozenset({"submitter", "reviewer"})
_FACT_VALUES: dict[str, frozenset[str]] = {
    "status": frozenset({"active", "suspended", "deactivated", "revoked", "captured"}),
    "subject_kind": frozenset({"human", "service"}),
    "provisioning_method": frozenset({"automatic_first_access", "manual_service_provisioning"}),
    "role": _ADMIN_ROLES | _PROJECT_ROLES,
    "scope_type": frozenset({"system", "project"}),
    "future_obligation": frozenset({"auth13_assignment", "rev_reviewer_obligation", "none"}),
}


def _task_policy_lineage(value: Mapping[str, object]) -> dict[str, object]:
    """AUDIT owns the exact serialized evidence shape independently of TASK."""
    uuid_fields = {
        "locked_guide_source_snapshot_id", "locked_effective_project_submission_artifact_policy_id",
        "locked_pre_submit_checker_policy_id", "locked_post_submit_checker_policy_id",
        "locked_review_policy_id", "locked_revision_policy_id", "locked_contribution_policy_version_id",
    }
    hash_fields = {
        "locked_guide_source_snapshot_hash", "locked_effective_project_submission_artifact_policy_hash",
        "locked_pre_submit_checker_bundle_hash", "locked_post_submit_checker_policy_hash",
        "locked_review_policy_hash", "locked_revision_policy_hash",
    }
    generation_fields = {"locked_review_policy_generation", "locked_revision_policy_generation"}
    version_fields = {"locked_guide_version", "locked_post_submit_checker_policy_version"}
    if set(value) != uuid_fields | hash_fields | generation_fields | version_fields:
        raise ValueError("task policy lineage requires exact fields")
    for key, item in value.items():
        if key in generation_fields:
            valid = type(item) is int and item > 0
        elif not isinstance(item, str):
            valid = False
        elif key in uuid_fields:
            valid = bool(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", item))
        elif key in hash_fields:
            valid = bool(re.fullmatch(r"sha256:[0-9a-f]{64}", item))
        else:
            valid = bool(item.strip())
        if not valid:
            raise ValueError("task policy lineage value is invalid")
    encoded = json.dumps(dict(value), allow_nan=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode()) > 8192:
        raise ValueError("task policy lineage exceeds audit bound")
    return json.loads(encoded)


def _manager_authority_facts(event: LifecycleAuditEventInput) -> dict[str, object]:
    """Validate AUDIT's bounded serialized copy of the consumed pre-write facts."""
    from app.core.hashing import canonical_json_hash

    facts = dict(event.manager_authority_facts or {})
    required = {'resource_type', 'resource_id', 'scope_project_id', 'actor_profile_id',
                'identity_link_id', 'task_status', 'assigned_to', 'assignment_id',
                'assignment_contributor_id', 'locked_context_hash', 'reason',
                'idempotency_key', 'replay_assignment_id', 'request_digest', 'replay_command_id'}
    if set(facts) != required or len(json.dumps(facts).encode()) > 4096:
        raise ValueError('invalid bounded manager authority facts')
    for key in ('resource_id', 'scope_project_id', 'actor_profile_id', 'identity_link_id', 'idempotency_key'):
        value = facts[key]
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError('invalid manager authority identity')
    for key in ('locked_context_hash', 'request_digest'):
        if not isinstance(facts[key], str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', facts[key]):
            raise ValueError('invalid manager authority digest')
    if (facts['resource_type'] != 'task_authority'
            or facts['resource_id'] != str(event.entity_id)
            or facts['scope_project_id'] != str(event.references.get(LifecycleAuditReferenceKind.PROJECT))
            or facts['actor_profile_id'] != str(event.actor_id)
            or facts['task_status'] != (event.from_status or 'draft')
            or any(facts[key] is not None for key in ('assigned_to', 'assignment_id',
                   'assignment_contributor_id', 'replay_assignment_id', 'replay_command_id'))
            or (facts['reason'] is not None and not isinstance(facts['reason'], str))
            or (facts['reason'] if facts['reason'] and facts['reason'].strip() else None) != event.task_reason):
        raise ValueError('manager authority does not match event')
    digest = canonical_json_hash({'resource_context': {key: value for key, value in facts.items() if value is not None}})
    if digest != event.authorization_resource_digest:
        raise ValueError('manager authority digest mismatch')
    return json.loads(json.dumps(facts))


class LifecycleAuditEntityType(StrEnum):
    """Closed product-fact namespaces admitted by the shared participant."""

    TASK = "task"
    REVIEW_QUEUE_ENTRY = "review_queue_entry"
    REVIEW_LEASE = "review_lease"
    REVIEW = "review"
    REVIEW_FINDING = "review_finding"
    FINDING_RESOLUTION = "finding_resolution"
    SUBMISSION_FINDING_RESPONSE = "submission_finding_response"
    CONTRIBUTION = "contribution"
    COMPENSATION_AWARD = "compensation_award"


class LifecycleAuditEventType(StrEnum):
    """Canonical REV/CON lifecycle facts admitted by the shared participant."""

    TASK_POST_SUBMIT_ROUTED = "TaskPostSubmitRouted"
    TASK_CREATED = "TaskCreated"
    TASK_SCREENED = "TaskScreened"
    TASK_RELEASED = "TaskReleased"
    TASK_CLAIMED = "TaskClaimed"
    TASK_STARTED = "TaskStarted"
    TASK_START_OVERRIDDEN = "TaskStartOverridden"
    TASK_ASSIGNMENT_AUTHORITY_REVOKED = "TaskAssignmentAuthorityRevoked"
    REVIEW_QUEUE_ENTRY_CREATED = "ReviewQueueEntryCreated"
    REVIEW_ROUTED_TO_PREFERRED_REVIEWER = "ReviewRoutedToPreferredReviewer"
    REVIEWER_PREFERENCE_EXPIRED = "ReviewerPreferenceExpired"
    REVIEWER_PREFERENCE_INVALIDATED = "ReviewerPreferenceInvalidated"
    REVIEWER_DECLINED_PREFERENCE = "ReviewerDeclinedPreference"
    REVIEW_QUEUE_ENTRY_OPENED = "ReviewQueueEntryOpened"
    REVIEW_QUEUE_ENTRY_CLOSED = "ReviewQueueEntryClosed"
    REVIEWER_CLAIMED_TASK = "ReviewerClaimedTask"
    REVIEWER_RELEASED_TASK = "ReviewerReleasedTask"
    REVIEWER_LEASE_EXPIRED = "ReviewerLeaseExpired"
    REVIEWER_LEASE_REVOKED = "ReviewerLeaseRevoked"
    REVIEWER_LEASE_CONSUMED = "ReviewerLeaseConsumed"
    REVIEWER_LEASE_FORCE_RELEASED = "ReviewerLeaseForceReleased"
    REVIEW_RECORDED = "ReviewRecorded"
    REVIEW_ACCEPTED = "ReviewAccepted"
    REVIEW_NEEDS_REVISION = "ReviewNeedsRevision"
    REVIEW_REJECTED = "ReviewRejected"
    REVIEW_FINDING_CREATED = "ReviewFindingCreated"
    FINDING_RESOLUTION_RECORDED = "FindingResolutionRecorded"
    SUBMISSION_FINDING_RESPONSE_CREATED = "SubmissionFindingResponseCreated"
    REVIEW_EVIDENCE_ACCESSED = "ReviewEvidenceAccessed"
    REVIEW_EVIDENCE_UNAVAILABLE = "ReviewEvidenceUnavailable"
    REVIEW_EVIDENCE_INTEGRITY_MISMATCH = "ReviewEvidenceIntegrityMismatch"
    REVIEW_FINDING_EVIDENCE_BOUND = "ReviewFindingEvidenceBound"
    SUBMISSION_FINDING_RESPONSE_EVIDENCE_BOUND = "SubmissionFindingResponseEvidenceBound"
    REVIEW_SNAPSHOT_PROJECTION_REQUESTED = "ReviewSnapshotProjectionRequested"
    REVIEWER_CONTRIBUTION_RECORDED = "ReviewerContributionRecorded"
    SUBMITTER_CONTRIBUTION_RECORDED = "SubmitterContributionRecorded"
    COMPENSATION_AWARD_CREATED = "CompensationAwardCreated"


class LifecycleAuditReason(StrEnum):
    """Feature-neutral reasons for durable lifecycle evidence."""

    STATE_CHANGED = "lifecycle_state_changed"
    FACT_RECORDED = "lifecycle_fact_recorded"


class LifecycleAuditReferenceKind(StrEnum):
    """Closed UUID reference keys allowed in lifecycle audit payloads."""

    AUTHORIZATION_DECISION = "authorization_decision_id"
    AUTHORITY_INVALIDATION = "authority_invalidation_event_id"
    PROJECT = "project_id"
    TASK = "task_id"
    ASSIGNMENT = "assignment_id"
    SUBMISSION = "submission_id"
    REVIEW = "review_id"
    REVIEW_QUEUE_ENTRY = "review_queue_entry_id"
    REVIEW_LEASE = "review_lease_id"
    REVIEW_FINDING = "review_finding_id"
    FINDING_RESOLUTION = "finding_resolution_id"
    SUBMISSION_FINDING_RESPONSE = "submission_finding_response_id"
    ROUTING_MANIFEST = "routing_manifest_id"
    FINAL_ACCEPTANCE = "final_acceptance_id"
    CONTRIBUTION_RECORD = "contribution_record_id"
    COMPENSATION_AWARD = "compensation_award_id"


_LIFECYCLE_EVENT_ENTITY = {
    **dict.fromkeys(
        (
            LifecycleAuditEventType.TASK_POST_SUBMIT_ROUTED,
            LifecycleAuditEventType.TASK_CREATED,
            LifecycleAuditEventType.TASK_SCREENED,
            LifecycleAuditEventType.TASK_RELEASED,
            LifecycleAuditEventType.TASK_CLAIMED,
            LifecycleAuditEventType.TASK_STARTED,
            LifecycleAuditEventType.TASK_START_OVERRIDDEN,
            LifecycleAuditEventType.TASK_ASSIGNMENT_AUTHORITY_REVOKED,
        ),
        LifecycleAuditEntityType.TASK,
    ),
    **dict.fromkeys(
        (
            LifecycleAuditEventType.REVIEW_QUEUE_ENTRY_CREATED,
            LifecycleAuditEventType.REVIEW_ROUTED_TO_PREFERRED_REVIEWER,
            LifecycleAuditEventType.REVIEWER_PREFERENCE_EXPIRED,
            LifecycleAuditEventType.REVIEWER_PREFERENCE_INVALIDATED,
            LifecycleAuditEventType.REVIEWER_DECLINED_PREFERENCE,
            LifecycleAuditEventType.REVIEW_QUEUE_ENTRY_OPENED,
            LifecycleAuditEventType.REVIEW_QUEUE_ENTRY_CLOSED,
        ),
        LifecycleAuditEntityType.REVIEW_QUEUE_ENTRY,
    ),
    **dict.fromkeys(
        (
            LifecycleAuditEventType.REVIEWER_CLAIMED_TASK,
            LifecycleAuditEventType.REVIEWER_RELEASED_TASK,
            LifecycleAuditEventType.REVIEWER_LEASE_EXPIRED,
            LifecycleAuditEventType.REVIEWER_LEASE_REVOKED,
            LifecycleAuditEventType.REVIEWER_LEASE_CONSUMED,
            LifecycleAuditEventType.REVIEWER_LEASE_FORCE_RELEASED,
        ),
        LifecycleAuditEntityType.REVIEW_LEASE,
    ),
    **dict.fromkeys(
        (
            LifecycleAuditEventType.REVIEW_RECORDED,
            LifecycleAuditEventType.REVIEW_ACCEPTED,
            LifecycleAuditEventType.REVIEW_NEEDS_REVISION,
            LifecycleAuditEventType.REVIEW_REJECTED,
            LifecycleAuditEventType.REVIEW_EVIDENCE_ACCESSED,
            LifecycleAuditEventType.REVIEW_EVIDENCE_UNAVAILABLE,
            LifecycleAuditEventType.REVIEW_EVIDENCE_INTEGRITY_MISMATCH,
            LifecycleAuditEventType.REVIEW_SNAPSHOT_PROJECTION_REQUESTED,
        ),
        LifecycleAuditEntityType.REVIEW,
    ),
    LifecycleAuditEventType.REVIEW_FINDING_CREATED: LifecycleAuditEntityType.REVIEW_FINDING,
    LifecycleAuditEventType.REVIEW_FINDING_EVIDENCE_BOUND: LifecycleAuditEntityType.REVIEW_FINDING,
    LifecycleAuditEventType.FINDING_RESOLUTION_RECORDED: LifecycleAuditEntityType.FINDING_RESOLUTION,
    LifecycleAuditEventType.SUBMISSION_FINDING_RESPONSE_CREATED: LifecycleAuditEntityType.SUBMISSION_FINDING_RESPONSE,
    LifecycleAuditEventType.SUBMISSION_FINDING_RESPONSE_EVIDENCE_BOUND: LifecycleAuditEntityType.SUBMISSION_FINDING_RESPONSE,
    LifecycleAuditEventType.REVIEWER_CONTRIBUTION_RECORDED: LifecycleAuditEntityType.CONTRIBUTION,
    LifecycleAuditEventType.SUBMITTER_CONTRIBUTION_RECORDED: LifecycleAuditEntityType.CONTRIBUTION,
    LifecycleAuditEventType.COMPENSATION_AWARD_CREATED: LifecycleAuditEntityType.COMPENSATION_AWARD,
}

_LIFECYCLE_EVENT_REQUIRED_REFERENCES = {
    LifecycleAuditEventType.TASK_POST_SUBMIT_ROUTED: frozenset(
        {
            LifecycleAuditReferenceKind.ASSIGNMENT,
            LifecycleAuditReferenceKind.SUBMISSION,
            LifecycleAuditReferenceKind.AUTHORIZATION_DECISION,
            LifecycleAuditReferenceKind.ROUTING_MANIFEST,
        }
    ),
    **dict.fromkeys(
        (
            LifecycleAuditEventType.TASK_CREATED,
            LifecycleAuditEventType.TASK_SCREENED,
            LifecycleAuditEventType.TASK_RELEASED,
        ),
        frozenset({LifecycleAuditReferenceKind.AUTHORIZATION_DECISION}),
    ),
    LifecycleAuditEventType.TASK_ASSIGNMENT_AUTHORITY_REVOKED: frozenset(
        {
            LifecycleAuditReferenceKind.ASSIGNMENT,
            LifecycleAuditReferenceKind.AUTHORIZATION_DECISION,
            LifecycleAuditReferenceKind.AUTHORITY_INVALIDATION,
        }
    ),
    **dict.fromkeys(
        (
            LifecycleAuditEventType.TASK_CLAIMED,
            LifecycleAuditEventType.TASK_STARTED,
            LifecycleAuditEventType.TASK_START_OVERRIDDEN,
        ),
        frozenset(
            {
                LifecycleAuditReferenceKind.ASSIGNMENT,
                LifecycleAuditReferenceKind.AUTHORIZATION_DECISION,
            }
        ),
    ),
    LifecycleAuditEventType.REVIEW_ACCEPTED: frozenset(
        {LifecycleAuditReferenceKind.FINAL_ACCEPTANCE}
    ),
    LifecycleAuditEventType.REVIEWER_CONTRIBUTION_RECORDED: frozenset(
        {
            LifecycleAuditReferenceKind.TASK,
            LifecycleAuditReferenceKind.SUBMISSION,
            LifecycleAuditReferenceKind.REVIEW,
            LifecycleAuditReferenceKind.REVIEW_LEASE,
        }
    ),
    LifecycleAuditEventType.SUBMITTER_CONTRIBUTION_RECORDED: frozenset(
        {
            LifecycleAuditReferenceKind.TASK,
            LifecycleAuditReferenceKind.ASSIGNMENT,
            LifecycleAuditReferenceKind.SUBMISSION,
            LifecycleAuditReferenceKind.FINAL_ACCEPTANCE,
        }
    ),
    LifecycleAuditEventType.COMPENSATION_AWARD_CREATED: frozenset(
        {LifecycleAuditReferenceKind.CONTRIBUTION_RECORD}
    ),
}


class LifecycleAuditEventInput(BaseModel):
    """Admit one bounded lifecycle fact without claims or arbitrary metadata."""

    model_config = ConfigDict(extra="forbid", strict=True)

    event_id: UUID
    entity_type: LifecycleAuditEntityType
    entity_id: UUID
    event_type: LifecycleAuditEventType
    actor_id: UUID
    reason: LifecycleAuditReason
    source_type: Literal["manual", "markdown_import", "csv_import"] | None = None
    locked_lineage: dict[str, object] | None = None
    task_reason: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    from_status: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")] | None = None
    to_status: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")] | None = None
    references: dict[LifecycleAuditReferenceKind, UUID] = Field(default_factory=dict)
    manager_authority_facts: dict[str, object] | None = None
    assignment_invalidation_facts: dict[str, object] | None = None
    authorization_resource_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")] | None = None

    @model_validator(mode="before")
    @classmethod
    def admit_closed_input(cls, value: object) -> object:
        """Copy only the closed input shape before Pydantic retains values."""
        try:
            if not isinstance(value, Mapping):
                raise TypeError
            data = dict(value)
            if set(data) - cls.model_fields.keys():
                raise TypeError
            references = data.get("references", {})
            if not isinstance(references, Mapping) or len(references) > len(
                LifecycleAuditReferenceKind
            ):
                raise TypeError
            data["references"] = dict(references)
            return data
        except Exception as exc:  # noqa: BLE001 - hostile Mapping methods are untrusted
            raise TypeError("invalid lifecycle audit input") from exc

    @model_validator(mode="after")
    def validate_lifecycle_shape(self) -> Self:
        """Keep state transitions distinct from immutable fact creation."""
        manager = self.event_type in {LifecycleAuditEventType.TASK_CREATED, LifecycleAuditEventType.TASK_SCREENED, LifecycleAuditEventType.TASK_RELEASED}
        if manager != (self.manager_authority_facts is not None):
            raise ValueError("manager event requires exact authority facts")
        if manager:
            self.manager_authority_facts = _manager_authority_facts(self)
        if (manager or self.event_type is LifecycleAuditEventType.TASK_ASSIGNMENT_AUTHORITY_REVOKED) != (self.authorization_resource_digest is not None):
            raise ValueError("release requires its exact authorization digest")
        if (self.event_type is LifecycleAuditEventType.TASK_ASSIGNMENT_AUTHORITY_REVOKED) != (self.assignment_invalidation_facts is not None):
            raise ValueError("assignment facts restricted to release")
        if self.assignment_invalidation_facts is not None:
            try:
                encoded = json.dumps(self.assignment_invalidation_facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
                if len(encoded.encode("utf-8")) > 4096:
                    raise ValueError("oversized assignment facts")
                self.assignment_invalidation_facts = json.loads(encoded)
            except (TypeError, ValueError):
                raise ValueError("invalid bounded assignment facts") from None
        if (self.event_type is LifecycleAuditEventType.TASK_CREATED) != (self.source_type is not None):
            raise ValueError("source type is required only for task creation")
        if (self.event_type in {LifecycleAuditEventType.TASK_SCREENED, LifecycleAuditEventType.TASK_RELEASED}) != (self.locked_lineage is not None):
            raise ValueError("manager transition requires complete policy lineage")
        if self.locked_lineage is not None:
            self.locked_lineage = _task_policy_lineage(self.locked_lineage)
        if self.entity_type is LifecycleAuditEntityType.TASK:
            expected = {
                LifecycleAuditEventType.TASK_CREATED: (None, "draft"),
                LifecycleAuditEventType.TASK_SCREENED: ("draft", "screening"),
                LifecycleAuditEventType.TASK_RELEASED: ("screening", "ready"),
                LifecycleAuditEventType.TASK_CLAIMED: ("ready", "claimed"),
                LifecycleAuditEventType.TASK_STARTED: ("claimed", "in_progress"),
                LifecycleAuditEventType.TASK_START_OVERRIDDEN: ("claimed", "in_progress"),
            }.get(self.event_type)
            if self.event_type is LifecycleAuditEventType.TASK_POST_SUBMIT_ROUTED:
                expected = (
                    ("evaluation_pending", self.to_status)
                    if self.to_status in {"review_pending", "accepted"}
                    else None
                )
            if self.event_type is LifecycleAuditEventType.TASK_ASSIGNMENT_AUTHORITY_REVOKED:
                expected = (self.from_status, "ready") if self.from_status in {"claimed", "in_progress"} else None
            if expected != (self.from_status, self.to_status):
                raise ValueError("task event requires its exact transition")
            if self.task_reason is not None and not self.task_reason.strip():
                raise ValueError("task reason must not be blank")
            if self.event_type in {LifecycleAuditEventType.TASK_START_OVERRIDDEN, LifecycleAuditEventType.TASK_RELEASED} and self.task_reason is None:
                raise ValueError("task start override requires a reason")
        elif self.task_reason is not None:
            raise ValueError("task reason is restricted to task transitions")
        if self.reason is LifecycleAuditReason.STATE_CHANGED:
            if (
                (self.from_status is None and self.event_type is not LifecycleAuditEventType.TASK_CREATED)
                or self.to_status is None
                or self.from_status == self.to_status
            ):
                raise ValueError("state change requires distinct lifecycle states")
        elif self.from_status is not None or self.to_status is not None:
            raise ValueError("fact recording cannot carry lifecycle states")
        entity_reference = {
            LifecycleAuditEntityType.TASK: LifecycleAuditReferenceKind.TASK,
            LifecycleAuditEntityType.REVIEW_QUEUE_ENTRY: LifecycleAuditReferenceKind.REVIEW_QUEUE_ENTRY,
            LifecycleAuditEntityType.REVIEW_LEASE: LifecycleAuditReferenceKind.REVIEW_LEASE,
            LifecycleAuditEntityType.REVIEW: LifecycleAuditReferenceKind.REVIEW,
            LifecycleAuditEntityType.REVIEW_FINDING: LifecycleAuditReferenceKind.REVIEW_FINDING,
            LifecycleAuditEntityType.FINDING_RESOLUTION: LifecycleAuditReferenceKind.FINDING_RESOLUTION,
            LifecycleAuditEntityType.SUBMISSION_FINDING_RESPONSE: LifecycleAuditReferenceKind.SUBMISSION_FINDING_RESPONSE,
            LifecycleAuditEntityType.CONTRIBUTION: (
                LifecycleAuditReferenceKind.CONTRIBUTION_RECORD
            ),
            LifecycleAuditEntityType.COMPENSATION_AWARD: (
                LifecycleAuditReferenceKind.COMPENSATION_AWARD
            ),
        }[self.entity_type]
        if LifecycleAuditReferenceKind.PROJECT not in self.references:
            raise ValueError("lifecycle audit requires project reference")
        if self.references.get(entity_reference) != self.entity_id:
            raise ValueError("entity reference must match lifecycle entity")
        if _LIFECYCLE_EVENT_ENTITY[self.event_type] is not self.entity_type:
            raise ValueError("event type must match lifecycle entity")
        required_references = _LIFECYCLE_EVENT_REQUIRED_REFERENCES.get(self.event_type, frozenset())
        allowed_references = {
            LifecycleAuditReferenceKind.PROJECT,
            entity_reference,
            *required_references,
        }
        if set(self.references) != allowed_references:
            raise ValueError("lifecycle event requires exact canonical references")
        return self


class AuthorityEventType(StrEnum):
    """Closed authority event tokens from the adopted specification."""

    ACTOR_PROFILE_PROVISIONED = "ActorProfileProvisioned"
    SERVICE_ACTOR_PROVISIONED = "ServiceActorProvisioned"
    ACTOR_IDENTITY_LINKED = "ActorIdentityLinked"
    ACTOR_IDENTITY_LINK_REVOKED = "ActorIdentityLinkRevoked"
    ACTOR_IDENTITY_LINK_REACTIVATED = "ActorIdentityLinkReactivated"
    ACTOR_PROFILE_SUSPENDED = "ActorProfileSuspended"
    ACTOR_PROFILE_REACTIVATED = "ActorProfileReactivated"
    ACTOR_PROFILE_DEACTIVATED = "ActorProfileDeactivated"
    INITIAL_ACCESS_ADMIN_BOOTSTRAPPED = "InitialAccessAdministratorBootstrapped"
    ADMIN_ROLE_GRANT_ISSUED = "AdminRoleGrantIssued"
    ADMIN_ROLE_GRANT_REVOKED = "AdminRoleGrantRevoked"
    ADMIN_ROLE_GRANT_ISSUE_DENIED = "AdminRoleGrantIssueDenied"
    LAST_ACCESS_ADMIN_OPERATION_DENIED = "LastAccessAdministratorOperationDenied"
    PROJECT_ROLE_QUALIFICATION_CAPTURED = "ProjectRoleQualificationSnapshotCaptured"
    PROJECT_ROLE_GRANT_ISSUED = "ProjectRoleGrantIssued"
    PROJECT_ROLE_GRANT_REVOKED = "ProjectRoleGrantRevoked"
    SENSITIVE_AUTHORIZATION_ALLOWED = "SensitiveAuthorizationAllowed"
    SENSITIVE_AUTHORIZATION_DENIED = "SensitiveAuthorizationDenied"
    AUTHORITY_INVALIDATION_REQUESTED = "AuthorityInvalidationRequested"


class ActorReferenceKind(StrEnum):
    """Stable namespaces usable before and after canonical actor migration."""

    LEGACY_ACTOR = "legacy_actor"
    ACTOR_PROFILE = "actor_profile"
    SYSTEM_PRINCIPAL = "system_principal"


_REASONS = {
    AuthorityEventType.ACTOR_PROFILE_PROVISIONED: {"automatic_first_access"},
    AuthorityEventType.SERVICE_ACTOR_PROVISIONED: {"manual_service_provisioning"},
    **dict.fromkeys(
        (
            AuthorityEventType.ACTOR_IDENTITY_LINKED,
            AuthorityEventType.ACTOR_IDENTITY_LINK_REVOKED,
            AuthorityEventType.ACTOR_IDENTITY_LINK_REACTIVATED,
        ),
        {"identity_lifecycle_change"},
    ),
    AuthorityEventType.ACTOR_PROFILE_SUSPENDED: {"security_response", "administrative_correction"},
    AuthorityEventType.ACTOR_PROFILE_REACTIVATED: {"administrative_correction"},
    AuthorityEventType.ACTOR_PROFILE_DEACTIVATED: {
        "security_response",
        "administrative_correction",
    },
    AuthorityEventType.INITIAL_ACCESS_ADMIN_BOOTSTRAPPED: {"initial_access_bootstrap"},
    AuthorityEventType.ADMIN_ROLE_GRANT_ISSUED: {"authority_assignment"},
    AuthorityEventType.ADMIN_ROLE_GRANT_REVOKED: {"authority_revocation"},
    AuthorityEventType.ADMIN_ROLE_GRANT_ISSUE_DENIED: {"authorization_policy_denial"},
    AuthorityEventType.LAST_ACCESS_ADMIN_OPERATION_DENIED: {"authorization_policy_denial"},
    AuthorityEventType.PROJECT_ROLE_QUALIFICATION_CAPTURED: {"qualification_evidence_captured"},
    AuthorityEventType.PROJECT_ROLE_GRANT_ISSUED: {"authority_assignment"},
    AuthorityEventType.PROJECT_ROLE_GRANT_REVOKED: {"authority_revocation"},
    AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED: {"authorization_evaluation"},
    AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED: {"authorization_evaluation"},
    AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED: {"authority_state_changed"},
}


def _enum_value(value: object, enum: type[StrEnum]) -> str | None:
    raw = value.value if isinstance(value, enum) else value
    return raw if isinstance(raw, str) and raw in {item.value for item in enum} else None


def _uuid(value: object) -> str | None:
    raw = str(value) if isinstance(value, UUID) else value
    try:
        return raw if isinstance(raw, str) and str(UUID(raw)) == raw else None
    except ValueError:
        return None


def _registered(value: object, values: frozenset[str] | set[str]) -> bool:
    return isinstance(value, str) and value in values


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ValueError
    return value


def _facts(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return None
    data = dict(value)
    if len(data) > 8 or not set(data).issubset(
        frozenset(_FACT_VALUES) | {"effective", "allowed", "resource_context_digest", "scope_id"}
    ):
        return None
    for key, item in data.items():
        if key in {"effective", "allowed"} and type(item) is not bool:
            return None
        if key == "scope_id" and _uuid(item) is None:
            return None
        if key == "resource_context_digest" and (
            not isinstance(item, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", item) is None
        ):
            return None
        if key in _FACT_VALUES and (not isinstance(item, str) or item not in _FACT_VALUES[key]):
            return None
    if len(json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()) > 4096:
        return None
    return data


def _grant_facts(
    facts: dict[str, object] | None, roles: frozenset[str], status: str, effective: bool
) -> bool:
    if facts is None or facts.get("role") not in roles:
        return False
    scope = facts.get("scope_type")
    expected = {"status", "role", "scope_type", "effective"} | (
        {"scope_id"} if scope == "project" else set()
    )
    return (
        set(facts) == expected
        and facts["status"] == status
        and facts["effective"] is effective
        and scope in {"system", "project"}
        and not (facts["role"] in {"access_administrator", "operator"} and scope != "system")
        and not (facts["role"] in _PROJECT_ROLES and scope != "project")
    )


def _event_facts_valid(
    event: AuthorityEventType, before: dict[str, object] | None, after: dict[str, object] | None
) -> bool:
    if event in {
        AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED,
        AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
    }:
        expected_allowed = event is AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED
        return (
            before is None
            and after is not None
            and after.get("allowed") is expected_allowed
            and set(after)
            in (
                {"allowed"},
                {"allowed", "resource_context_digest"},
            )
        )
    exact = {
        AuthorityEventType.ACTOR_PROFILE_PROVISIONED: (
            None,
            {
                "status": "active",
                "subject_kind": "human",
                "provisioning_method": "automatic_first_access",
            },
        ),
        AuthorityEventType.SERVICE_ACTOR_PROVISIONED: (
            None,
            {
                "status": "active",
                "subject_kind": "service",
                "provisioning_method": "manual_service_provisioning",
            },
        ),
        AuthorityEventType.ACTOR_IDENTITY_LINK_REVOKED: (
            {"status": "active"},
            {"status": "revoked"},
        ),
        AuthorityEventType.ACTOR_IDENTITY_LINK_REACTIVATED: (
            {"status": "revoked"},
            {"status": "active"},
        ),
        AuthorityEventType.ACTOR_PROFILE_SUSPENDED: ({"status": "active"}, {"status": "suspended"}),
        AuthorityEventType.ACTOR_PROFILE_REACTIVATED: (
            {"status": "suspended"},
            {"status": "active"},
        ),
        AuthorityEventType.PROJECT_ROLE_QUALIFICATION_CAPTURED: (None, {"status": "captured"}),
        AuthorityEventType.ADMIN_ROLE_GRANT_ISSUE_DENIED: (None, None),
        AuthorityEventType.LAST_ACCESS_ADMIN_OPERATION_DENIED: (None, None),
    }
    if event in exact:
        return (before, after) == exact[event]
    if event == AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED:
        if (before, after) in (
            ({"effective": True}, {"effective": False}),
            ({"effective": False}, {"effective": True}),
        ):
            return True
        if before is None or after is None:
            return False
        expected_obligation = {
            "submitter": "auth13_assignment",
            "reviewer": "rev_reviewer_obligation",
        }.get(before.get("role"))
        keys = {"effective", "role", "scope_type", "scope_id", "future_obligation"}
        return (
            set(before) == keys
            and set(after) == keys
            and before["effective"] is True
            and after["effective"] is False
            and before["scope_type"] == after["scope_type"] == "project"
            and before["role"] == after["role"]
            and before["scope_id"] == after["scope_id"]
            and before["future_obligation"] == after["future_obligation"] == expected_obligation
        )
    if event == AuthorityEventType.ACTOR_IDENTITY_LINKED:
        return before is None and after in (
            {"status": "active", "subject_kind": "human"},
            {"status": "active", "subject_kind": "service"},
        )
    if event == AuthorityEventType.ACTOR_PROFILE_DEACTIVATED:
        return before in ({"status": "active"}, {"status": "suspended"}) and after == {
            "status": "deactivated"
        }
    if event == AuthorityEventType.INITIAL_ACCESS_ADMIN_BOOTSTRAPPED:
        return (
            before is None
            and _grant_facts(after, _ADMIN_ROLES, "active", True)
            and after["role"] == "access_administrator"
        )
    roles, action = {
        AuthorityEventType.ADMIN_ROLE_GRANT_ISSUED: (_ADMIN_ROLES, "issued"),
        AuthorityEventType.ADMIN_ROLE_GRANT_REVOKED: (_ADMIN_ROLES, "revoked"),
        AuthorityEventType.PROJECT_ROLE_GRANT_ISSUED: (_PROJECT_ROLES, "issued"),
        AuthorityEventType.PROJECT_ROLE_GRANT_REVOKED: (_PROJECT_ROLES, "revoked"),
    }[event]
    if action == "issued":
        return before is None and _grant_facts(after, roles, "active", True)
    if action == "revoked":
        return (
            _grant_facts(before, roles, "active", True)
            and _grant_facts(after, roles, "revoked", False)
            and (before["role"], before["scope_type"], before.get("scope_id"))
            == (after["role"], after["scope_type"], after.get("scope_id"))
        )
    return _grant_facts(before, roles, "active", True) and _grant_facts(
        after, roles, "active", True
    )


class AuthorityAuditEventInput(BaseModel):
    """Validate one authority event without provider claims or request bodies."""

    model_config = ConfigDict(extra="forbid", strict=True)

    event_id: UUID
    event_type: AuthorityEventType
    entity_type: str
    entity_id: str
    actor_ref_kind: ActorReferenceKind
    actor_ref: Annotated[str, Field(max_length=120)]
    request_id: UUID
    correlation_id: UUID
    target_actor_ref_kind: ActorReferenceKind | None = None
    target_actor_ref: Annotated[str, Field(max_length=120)] | None = None
    matched_grant_id: str | None = None
    permission_id: PermissionId | None = None
    action_id: ActionId | None = None
    project_id: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    target_ref_kind: str | None = None
    target_ref_id: Annotated[str, Field(max_length=120)] | None = None
    reason: str
    denial_code: str | None = None
    idempotency_reference: UUID | None = None
    invalidation_cause_event_id: UUID | None = None
    invalidation_target_kind: str | None = None
    invalidation_target_ref: Annotated[str, Field(max_length=120)] | None = None
    before_facts: dict[str, str | bool] | None = None
    after_facts: dict[str, str | bool] | None = None

    @model_validator(mode="before")
    @classmethod
    def admit_privacy_safe_input(cls, value: object) -> object:
        """Reject unsafe input before Pydantic can retain rejected values."""
        try:
            admitted = cls._inspect_privacy_safe_input(value)
        except Exception:  # noqa: BLE001 - hostile Mapping methods are untrusted input
            admitted = None
        if admitted is None:
            raise TypeError("invalid authority audit input")
        return admitted

    @classmethod
    def _inspect_privacy_safe_input(cls, value: object) -> dict | None:
        if not isinstance(value, Mapping):
            return None
        data = dict(value)
        if set(data) - cls.model_fields.keys():
            return None
        event_raw = _enum_value(data.get("event_type"), AuthorityEventType)
        kind = _enum_value(data.get("actor_ref_kind"), ActorReferenceKind)
        event = AuthorityEventType(event_raw) if event_raw else None
        actor_ref = data.get("actor_ref")
        before_facts = _facts(data.get("before_facts"))
        after_facts = _facts(data.get("after_facts"))
        uuid_fields = (
            "event_id",
            "entity_id",
            "request_id",
            "correlation_id",
            "matched_grant_id",
            "project_id",
            "resource_id",
            "idempotency_reference",
            "invalidation_cause_event_id",
        )
        invalid = (
            event is None
            or not _registered(data.get("entity_type"), _ENTITY_TYPES)
            or any(data.get(key) is not None and _uuid(data[key]) is None for key in uuid_fields)
            or kind is None
            or (kind == "system_principal" and actor_ref != "workstream:system:bootstrap")
            or (kind != "system_principal" and _uuid(actor_ref) is None)
            or data.get("permission_id") is not None
            and not _registered(data["permission_id"], PERMISSION_IDS)
            or data.get("action_id") is not None
            and not _registered(data["action_id"], ACTION_IDS)
            or data.get("denial_code") is not None
            and not _registered(data["denial_code"], _DENIAL_CODES)
            or data.get("resource_type") is not None
            and not _registered(data["resource_type"], _RESOURCE_TYPES)
            or data.get("target_ref_kind") is not None
            and not _registered(
                data["target_ref_kind"], _TARGET_REF_KINDS | {"permission_registry"}
            )
            or data.get("invalidation_target_kind") is not None
            and not _registered(
                data["invalidation_target_kind"], _UUID_TARGET_KINDS | {"permission_registry"}
            )
            or event is not None
            and not _registered(data.get("reason"), _REASONS[event])
            or before_facts is None
            and data.get("before_facts") is not None
            or after_facts is None
            and data.get("after_facts") is not None
        )
        for prefix in ("target_ref", "invalidation_target"):
            ref_kind = data.get(f"{prefix}_kind")
            ref = data.get(f"{prefix}_ref" if prefix == "invalidation_target" else f"{prefix}_id")
            invalid |= (ref_kind is None) != (ref is None)
            valid_uuid_kinds = (
                _UUID_TARGET_KINDS if prefix == "invalidation_target" else _TARGET_REF_KINDS
            )
            invalid |= (
                _registered(ref_kind, valid_uuid_kinds) and ref is not None and _uuid(ref) is None
            )
            invalid |= ref_kind == "permission_registry" and not _registered(ref, PERMISSION_IDS)
        target_kind, target_ref = data.get("target_actor_ref_kind"), data.get("target_actor_ref")
        invalid |= (target_kind is None) != (target_ref is None)
        invalid |= target_kind is not None and (
            _enum_value(target_kind, ActorReferenceKind) != "actor_profile"
            or _uuid(target_ref) is None
        )
        if invalid:
            return None
        if data.get("permission_id") is not None:
            data["permission_id"] = PermissionId(data["permission_id"])
        if data.get("action_id") is not None:
            data["action_id"] = ActionId(data["action_id"])
        data["before_facts"] = before_facts
        data["after_facts"] = after_facts
        return data

    @classmethod
    def model_validate_json(cls, json_data: str | bytes | bytearray, **kwargs: Any) -> Self:
        """Parse JSON without retaining malformed or non-object input."""
        try:
            snapshot = (
                str.encode(json_data)
                if isinstance(json_data, str)
                else memoryview(json_data).tobytes()
            )
            value = json.loads(snapshot, object_pairs_hook=_unique_object)
        except Exception:  # noqa: BLE001 - hostile buffer methods are untrusted input
            value = None
        if not isinstance(value, Mapping):
            raise TypeError("invalid authority audit input")
        return super().model_validate_json(json.dumps(value, separators=(",", ":")), **kwargs)

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        """Enforce event, reference, fact, and project-scope integrity."""
        if self.resource_id is not None and self.resource_type is None:
            raise ValueError("resource ID requires resource type")
        if self.entity_type in {
            "authorization_decision",
            "authority_invalidation",
        } and self.entity_id != str(self.event_id):
            raise ValueError("decision entity ID must equal event ID")
        if (
            self.resource_type == "project"
            and self.resource_id is not None
            and self.resource_id != self.project_id
        ):
            raise ValueError("project resource must match project scope")
        before, after = _facts(self.before_facts), _facts(self.after_facts)
        if not _event_facts_valid(self.event_type, before, after):
            raise ValueError("invalid authority event facts")
        for facts in (before, after):
            if facts and "scope_type" in facts:
                if facts["scope_type"] == "system" and self.project_id is not None:
                    raise ValueError("system grant cannot carry project scope")
                if facts["scope_type"] == "project" and facts.get("scope_id") != self.project_id:
                    raise ValueError("grant facts must match project scope")
        if (
            before
            and after
            and "scope_id" in before
            and before.get("scope_id") != after.get("scope_id")
        ):
            raise ValueError("replacement cannot change project scope")
        invalidation = self.invalidation_cause_event_id is not None or self.invalidation_target_kind
        action = ACTION_BY_ID.get(self.action_id) if self.action_id is not None else None
        if action is not None and action.permission_id is not self.permission_id:
            raise ValueError("action permission does not match catalogue")
        if self.permission_id in NEW_PERMISSION_IDS and action is None:
            raise ValueError("new permission requires registered action")
        if self.action_id is not None and self.event_type not in {
            AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED,
            AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
        }:
            raise ValueError("action requires authorization decision event")
        if self.event_type == AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED:
            if self.permission_id is None or self.denial_code is not None or invalidation:
                raise ValueError("invalid allowed authorization evidence")
            if action is not None and action.availability is ActionAvailability.PLANNED:
                raise ValueError("planned action cannot produce allowed evidence")
        elif self.event_type == AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED:
            if (
                self.permission_id is None
                or self.denial_code is None
                or invalidation
                or self.idempotency_reference
            ):
                raise ValueError("invalid denied authorization evidence")
        elif self.event_type in {
            AuthorityEventType.ADMIN_ROLE_GRANT_ISSUE_DENIED,
            AuthorityEventType.LAST_ACCESS_ADMIN_OPERATION_DENIED,
        }:
            if self.denial_code is None:
                raise ValueError("denied authority operation requires denial code")
        elif self.event_type == AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED:
            if (
                self.invalidation_cause_event_id is None
                or self.invalidation_target_kind is None
                or self.denial_code
            ):
                raise ValueError("invalid authority invalidation evidence")
            restoration = self.permission_id in {
                PermissionId.ADMIN_ROLE_GRANT,
                PermissionId.ACTOR_PROFILE_REACTIVATE,
                PermissionId.ACTOR_IDENTITY_LINK_REACTIVATE,
            }
            expected_direction = (
                ({"effective": False}, {"effective": True})
                if restoration
                else ({"effective": True}, {"effective": False})
            )
            projected_project_role = (
                self.permission_id is PermissionId.PROJECT_ROLE_GRANT_MANAGE
                and before is not None
                and after is not None
                and before.get("effective") is True
                and after.get("effective") is False
                and before.get("role") in _PROJECT_ROLES
                and before.get("role") == after.get("role")
                and before.get("future_obligation") == after.get("future_obligation")
            )
            if (before, after) != expected_direction and not projected_project_role:
                raise ValueError("invalid authority invalidation direction")
            if self.permission_id in {
                PermissionId.ADMIN_ROLE_GRANT,
                PermissionId.ADMIN_ROLE_REVOKE,
            } and (
                self.resource_type != "actor_profile"
                or self.invalidation_target_kind != "actor_profile"
                or self.resource_id != self.invalidation_target_ref
            ):
                raise ValueError("admin grant invalidation must target actor projection")
        if self.invalidation_cause_event_id == self.event_id:
            raise ValueError("invalidation cannot reference its own event")
        return self
