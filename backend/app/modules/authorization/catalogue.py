"""Closed authorization identifiers and staged action metadata."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from types import MappingProxyType

from app.modules.actors.service_identities import SERVICE_IDENTITIES, ServiceIdentity


@unique
class PermissionId(StrEnum):
    """Closed product permission identifiers."""

    ACTOR_PROFILE_READ_SELF = "actor.profile.read_self"
    ACTOR_PROFILE_UPDATE_SELF = "actor.profile.update_self"
    ACTOR_PROFILE_READ_ANY = "actor.profile.read_any"
    ACTOR_PROFILE_SUSPEND = "actor.profile.suspend"
    ACTOR_PROFILE_REACTIVATE = "actor.profile.reactivate"
    ACTOR_PROFILE_DEACTIVATE = "actor.profile.deactivate"
    ACTOR_IDENTITY_LINK_READ = "actor.identity_link.read"
    ACTOR_IDENTITY_LINK_REVOKE = "actor.identity_link.revoke"
    ACTOR_IDENTITY_LINK_REACTIVATE = "actor.identity_link.reactivate"
    ACTOR_SERVICE_PROVISION = "actor.service.provision"
    ADMIN_ROLE_READ = "admin_role.read"
    ADMIN_ROLE_GRANT = "admin_role.grant"
    ADMIN_ROLE_REVOKE = "admin_role.revoke"
    PROJECT_CREATE = "project.create"
    PROJECT_READ = "project.read"
    PROJECT_UPDATE = "project.update"
    PROJECT_ARCHIVE = "project.archive"
    PROJECT_GUIDE_MANAGE = "project.guide.manage"
    PROJECT_EFFECTIVE_POLICY_MANAGE = "project.effective_policy.manage"
    PROJECT_TASK_MANAGE = "project.task.manage"
    PROJECT_REVIEW_POLICY_MANAGE = "project.review_policy.manage"
    PROJECT_ROLE_GRANT_READ = "project.role_grant.read"
    PROJECT_ROLE_GRANT_MANAGE = "project.role_grant.manage"
    TASK_QUEUE_READ = "task.queue.read"
    TASK_CLAIM = "task.claim"
    SUBMISSION_CREATE = "submission.create"
    SUBMISSION_READ_OWN = "submission.read_own"
    SUBMISSION_READ_FOR_REVIEW = "submission.read_for_review"
    REVIEW_QUEUE_READ = "review.queue.read"
    REVIEW_QUEUE_INSPECT = "review.queue.inspect"
    REVIEW_CLAIM = "review.claim"
    REVIEW_RELEASE = "review.release"
    REVIEW_DECLINE_PREFERENCE = "review.decline_preference"
    REVIEW_DECISION = "review.decision"
    REVIEW_LEASE_FORCE_RELEASE = "review.lease.force_release"
    REVIEW_CHAIN_READ = "review.chain.read"
    REVIEW_QUEUE_OVERRIDE = "review.queue.override"
    CONTRIBUTION_READ_SELF = "contribution.read_self"
    CONTRIBUTION_READ_PROJECT = "contribution.read_project"
    COMPENSATION_POLICY_MANAGE = "compensation.policy.manage"
    COMPENSATION_ADAPTER_BINDING_MANAGE = "compensation.adapter_binding.manage"
    COMPENSATION_AWARD_READ = "compensation.award.read"
    COMPENSATION_DELIVERY_RECONCILE = "compensation.delivery.reconcile"
    OPERATIONS_STATUS_READ = "operations.status.read"
    OPERATIONS_TIMER_RUN = "operations.timer.run"
    OPERATIONS_RECONCILE_RUN = "operations.reconcile.run"
    OPERATIONS_OUTBOX_RETRY = "operations.outbox.retry"
    OPERATIONS_PROJECTION_REBUILD = "operations.projection.rebuild"
    OPERATIONS_TASK_START_OVERRIDE = "operations.task.start_override"
    OPERATIONS_SUBMISSION_GATE_REPAIR = "operations.submission_gate.repair"
    OPERATIONS_CHECKER_RETRY = "operations.checker.retry"
    ARTIFACT_BINDING_READ = "artifact.binding.read"
    ARTIFACT_REPLICA_READ = "artifact.replica.read"
    ARTIFACT_RECEIPT_READ = "artifact.receipt.read"
    ARTIFACT_VERIFICATION_JOB_READ = "artifact.verification_job.read"
    ARTIFACT_VERIFICATION_JOB_RETRY = "artifact.verification_job.retry"
    ARTIFACT_RECOVERY_ATTEMPT_READ = "artifact.recovery_attempt.read"
    ARTIFACT_AUDIT_READ = "artifact.audit.read"
    ARTIFACT_GUIDE_SOURCE_INGEST = "artifact.guide_source.ingest"
    ARTIFACT_UPLOAD_SESSION_CREATE = "artifact.upload_session.create"
    ARTIFACT_UPLOAD_SESSION_READ = "artifact.upload_session.read"
    ARTIFACT_UPLOAD_ITEM_WRITE = "artifact.upload_item.write"
    ARTIFACT_UPLOAD_SESSION_SEAL = "artifact.upload_session.seal"
    ARTIFACT_UPLOAD_SESSION_CANCEL = "artifact.upload_session.cancel"
    ARTIFACT_UPLOAD_SESSION_EXPIRE = "artifact.upload_session.expire"
    ARTIFACT_BINDING_CREATE = "artifact.binding.create"
    ARTIFACT_VERIFICATION_EXECUTE = "artifact.verification.execute"
    ARTIFACT_PENDING_WORK_SCAN = "artifact.pending_work.scan"
    ARTIFACT_PUT_ATTEMPT_RESOLVE = "artifact.put_attempt.resolve"
    ARTIFACT_GUIDE_SOURCE_READ = "artifact.guide_source.read"
    ARTIFACT_CHECKER_INPUT_MATERIALIZE = "artifact.checker_input.materialize"
    ARTIFACT_CHECKER_OUTPUT_WRITE = "artifact.checker_output.write"
    AUDIT_READ = "audit.read"
    AUDIT_EXPORT = "audit.export"


@unique
class ActionId(StrEnum):
    """Closed action identifiers reserved by approved owner chunks."""

    ACTOR_PROFILE_READ_SELF = "actor.profile.read_self"
    ACTOR_PROFILE_UPDATE_SELF = "actor.profile.update_self"
    AUTHORIZATION_PERMISSION_CATALOGUE_READ = "authorization.permission_catalogue.read"
    AUTHORIZATION_ADMIN_ROLE_DEFINITIONS_READ = "authorization.admin_role_definitions.read"
    ADMIN_ROLE_GRANT_LIST = "admin_role_grant.list"
    ACTOR_ADMIN_ROLE_GRANT_HISTORY_READ = "actor.admin_role_grant_history.read"
    ADMIN_ROLE_GRANT_ISSUE = "admin_role_grant.issue"
    ADMIN_ROLE_GRANT_REVOKE = "admin_role_grant.revoke"
    ADMIN_ROLE_GRANT_BOOTSTRAP = "admin_role_grant.bootstrap"
    ACTOR_PROFILE_READ = "actor.profile.read"
    ACTOR_PROFILE_SUSPEND = "actor.profile.suspend"
    ACTOR_PROFILE_REACTIVATE = "actor.profile.reactivate"
    ACTOR_PROFILE_DEACTIVATE = "actor.profile.deactivate"
    ACTOR_IDENTITY_LINK_READ = "actor.identity_link.read"
    ACTOR_IDENTITY_LINK_REVOKE = "actor.identity_link.revoke"
    ACTOR_IDENTITY_LINK_REACTIVATE = "actor.identity_link.reactivate"
    ACTOR_SERVICE_PROVISION = "actor.service.provision"
    OPERATIONS_TASK_START_OVERRIDE = "operations.task.start_override"
    OPERATIONS_SUBMISSION_GATE_REPAIR = "operations.submission_gate.repair"
    OPERATIONS_CHECKER_RETRY = "operations.checker.retry"
    SUBMISSION_CREATE = "submission.create"
    REVIEW_QUEUE_READ = "review.queue.read"
    REVIEW_QUEUE_INSPECT = "review.queue.inspect"
    REVIEW_CLAIM = "review.claim"
    REVIEW_RELEASE = "review.release"
    REVIEW_DECLINE_PREFERENCE = "review.decline_preference"
    REVIEW_PREFERENCE_EXPIRY_RUN = "review.preference_expiry.run"
    REVIEW_LEASE_EXPIRY_RUN = "review.lease_expiry.run"
    REVIEW_CONTEXT_READ = "review.context.read"
    REVIEW_CHAIN_READ = "review.chain.read"
    REVIEW_FINDING_EVIDENCE_INGEST = "review.finding_evidence.ingest"
    REVIEW_DECISION = "review.decision"
    REVIEW_FINDING_RESPONSE_EVIDENCE_INGEST = "review.finding_response_evidence.ingest"
    REVIEW_LEASE_FORCE_RELEASE = "review.lease.force_release"
    REVIEW_QUEUE_ROUTING_OVERRIDE = "review.queue.routing.override"
    REVIEW_QUEUE_ROUTING_CORRECT = "review.queue.routing.correct"
    REVIEW_QUEUE_CLOSE = "review.queue.close"
    REVIEW_RECONCILE_RUN = "review.reconcile.run"
    REVIEW_ARTIFACT_REFERENCE_RECONCILE = "review.artifact_reference.reconcile"
    REVIEW_PROJECTION_REBUILD = "review.projection.rebuild"
    ARTIFACT_BINDING_READ = "artifact.binding.read"
    ARTIFACT_REPLICA_READ = "artifact.replica.read"
    ARTIFACT_RECEIPT_READ = "artifact.receipt.read"
    ARTIFACT_VERIFICATION_JOB_READ = "artifact.verification_job.read"
    ARTIFACT_VERIFICATION_JOB_RETRY = "artifact.verification_job.retry"
    ARTIFACT_RECOVERY_ATTEMPT_READ = "artifact.recovery_attempt.read"
    ARTIFACT_AUDIT_READ = "artifact.audit.read"
    OPERATIONS_ARTIFACT_STORAGE_ADMISSION_READ = "operations.artifact_storage_admission.read"
    ARTIFACT_GUIDE_SOURCE_INGEST = "artifact.guide_source.ingest"
    ARTIFACT_GUIDE_SOURCE_READ = "artifact.guide_source.read"
    ARTIFACT_UPLOAD_SESSION_CREATE = "artifact.upload_session.create"
    ARTIFACT_UPLOAD_SESSION_READ = "artifact.upload_session.read"
    ARTIFACT_UPLOAD_ITEM_WRITE = "artifact.upload_item.write"
    ARTIFACT_UPLOAD_SESSION_SEAL = "artifact.upload_session.seal"
    ARTIFACT_UPLOAD_SESSION_CANCEL = "artifact.upload_session.cancel"
    ARTIFACT_UPLOAD_SESSION_EXPIRE = "artifact.upload_session.expire"
    ARTIFACT_GUIDE_SOURCE_BINDING_CREATE = "artifact.guide_source.binding.create"
    ARTIFACT_SUBMISSION_BINDING_CREATE = "artifact.submission.binding.create"
    ARTIFACT_CHECKER_OUTPUT_BINDING_CREATE = "artifact.checker_output.binding.create"
    ARTIFACT_VERIFICATION_EXECUTE = "artifact.verification.execute"
    ARTIFACT_PENDING_WORK_SCAN = "artifact.pending_work.scan"
    ARTIFACT_PUT_ATTEMPT_RESOLVE = "artifact.put_attempt.resolve"
    ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE = "artifact.pre_submit.checker_input.materialize"
    ARTIFACT_POST_SUBMIT_CHECKER_INPUT_MATERIALIZE = (
        "artifact.post_submit.checker_input.materialize"
    )
    ARTIFACT_CHECKER_OUTPUT_WRITE = "artifact.checker_output.write"


@unique
class ActionOwner(StrEnum):
    """Closed implementation chunks allowed to activate reserved actions."""

    AUTH_07B = "WS-AUTH-001-07B"
    AUTH_08 = "WS-AUTH-001-08"
    AUTH_09B = "WS-AUTH-001-09B"
    AUTH_09C = "WS-AUTH-001-09C"
    AUTH_09D_A = "WS-AUTH-001-09D-A"
    AUTH_09D_B = "WS-AUTH-001-09D-B"
    AUTH_13 = "WS-AUTH-001-13"
    AUTH_14 = "WS-AUTH-001-14"
    AUTH_REV_05 = "WS-AUTH-001-REV-05"
    AUTH_REV_06 = "WS-AUTH-001-REV-06"
    AUTH_REV_07 = "WS-AUTH-001-REV-07"
    AUTH_REV_08 = "WS-AUTH-001-REV-08"
    AUTH_REV_09A = "WS-AUTH-001-REV-09A"
    AUTH_REV_11 = "WS-AUTH-001-REV-11"
    AUTH_REV_12 = "WS-AUTH-001-REV-12"
    AUTH_ART_02D_INTERNAL = "WS-AUTH-001-ART-02D-INTERNAL"
    AUTH_ART_02D_OPERATOR = "WS-AUTH-001-ART-02D-OPERATOR"
    AUTH_ART_03 = "WS-AUTH-001-ART-03"
    AUTH_ART_04A = "WS-AUTH-001-ART-04A"
    AUTH_ART_04B = "WS-AUTH-001-ART-04B"
    AUTH_ART_05 = "WS-AUTH-001-ART-05"
    AUTH_ART_06A = "WS-AUTH-001-ART-06A"
    AUTH_ART_06B = "WS-AUTH-001-ART-06B"


@unique
class ActionAvailability(StrEnum):
    """Whether AUTH has activated an action after merged feature proof."""

    PLANNED = "planned"
    ACTIVE = "active"


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    """Bounded action metadata; feature guards remain owner-defined."""

    action_id: ActionId
    permission_id: PermissionId
    owner: ActionOwner
    availability: ActionAvailability


def _planned(
    action_id: ActionId,
    permission_id: PermissionId,
    owner: ActionOwner,
) -> ActionDefinition:
    return ActionDefinition(action_id, permission_id, owner, ActionAvailability.PLANNED)


def _active(
    action_id: ActionId,
    permission_id: PermissionId,
    owner: ActionOwner,
) -> ActionDefinition:
    return ActionDefinition(action_id, permission_id, owner, ActionAvailability.ACTIVE)


ACTION_DEFINITIONS = (
    _active(
        ActionId.ACTOR_PROFILE_READ_SELF, PermissionId.ACTOR_PROFILE_READ_SELF, ActionOwner.AUTH_07B
    ),
    _active(
        ActionId.ACTOR_PROFILE_UPDATE_SELF,
        PermissionId.ACTOR_PROFILE_UPDATE_SELF,
        ActionOwner.AUTH_07B,
    ),
    _active(
        ActionId.AUTHORIZATION_PERMISSION_CATALOGUE_READ,
        PermissionId.ADMIN_ROLE_READ,
        ActionOwner.AUTH_08,
    ),
    _active(
        ActionId.AUTHORIZATION_ADMIN_ROLE_DEFINITIONS_READ,
        PermissionId.ADMIN_ROLE_READ,
        ActionOwner.AUTH_08,
    ),
    _active(
        ActionId.ADMIN_ROLE_GRANT_LIST,
        PermissionId.ADMIN_ROLE_READ,
        ActionOwner.AUTH_08,
    ),
    _active(
        ActionId.ACTOR_ADMIN_ROLE_GRANT_HISTORY_READ,
        PermissionId.ADMIN_ROLE_READ,
        ActionOwner.AUTH_08,
    ),
    _active(
        ActionId.ADMIN_ROLE_GRANT_ISSUE,
        PermissionId.ADMIN_ROLE_GRANT,
        ActionOwner.AUTH_08,
    ),
    _active(
        ActionId.ADMIN_ROLE_GRANT_REVOKE,
        PermissionId.ADMIN_ROLE_REVOKE,
        ActionOwner.AUTH_08,
    ),
    _active(
        ActionId.ADMIN_ROLE_GRANT_BOOTSTRAP,
        PermissionId.ADMIN_ROLE_GRANT,
        ActionOwner.AUTH_08,
    ),
    _active(
        ActionId.ACTOR_PROFILE_READ,
        PermissionId.ACTOR_PROFILE_READ_ANY,
        ActionOwner.AUTH_09C,
    ),
    _active(
        ActionId.ACTOR_PROFILE_SUSPEND,
        PermissionId.ACTOR_PROFILE_SUSPEND,
        ActionOwner.AUTH_09D_A,
    ),
    _active(
        ActionId.ACTOR_PROFILE_REACTIVATE,
        PermissionId.ACTOR_PROFILE_REACTIVATE,
        ActionOwner.AUTH_09D_A,
    ),
    _active(
        ActionId.ACTOR_PROFILE_DEACTIVATE,
        PermissionId.ACTOR_PROFILE_DEACTIVATE,
        ActionOwner.AUTH_09D_A,
    ),
    _active(
        ActionId.ACTOR_IDENTITY_LINK_READ,
        PermissionId.ACTOR_IDENTITY_LINK_READ,
        ActionOwner.AUTH_09C,
    ),
    _active(
        ActionId.ACTOR_IDENTITY_LINK_REVOKE,
        PermissionId.ACTOR_IDENTITY_LINK_REVOKE,
        ActionOwner.AUTH_09D_B,
    ),
    _active(
        ActionId.ACTOR_IDENTITY_LINK_REACTIVATE,
        PermissionId.ACTOR_IDENTITY_LINK_REACTIVATE,
        ActionOwner.AUTH_09D_B,
    ),
    _active(
        ActionId.ACTOR_SERVICE_PROVISION,
        PermissionId.ACTOR_SERVICE_PROVISION,
        ActionOwner.AUTH_09B,
    ),
    _planned(
        ActionId.OPERATIONS_TASK_START_OVERRIDE,
        PermissionId.OPERATIONS_TASK_START_OVERRIDE,
        ActionOwner.AUTH_13,
    ),
    _planned(
        ActionId.OPERATIONS_SUBMISSION_GATE_REPAIR,
        PermissionId.OPERATIONS_SUBMISSION_GATE_REPAIR,
        ActionOwner.AUTH_14,
    ),
    _planned(
        ActionId.OPERATIONS_CHECKER_RETRY,
        PermissionId.OPERATIONS_CHECKER_RETRY,
        ActionOwner.AUTH_14,
    ),
    _planned(ActionId.SUBMISSION_CREATE, PermissionId.SUBMISSION_CREATE, ActionOwner.AUTH_14),
    _planned(ActionId.REVIEW_QUEUE_READ, PermissionId.REVIEW_QUEUE_READ, ActionOwner.AUTH_REV_05),
    _planned(
        ActionId.REVIEW_QUEUE_INSPECT,
        PermissionId.REVIEW_QUEUE_INSPECT,
        ActionOwner.AUTH_REV_05,
    ),
    _planned(ActionId.REVIEW_CLAIM, PermissionId.REVIEW_CLAIM, ActionOwner.AUTH_REV_06),
    _planned(ActionId.REVIEW_RELEASE, PermissionId.REVIEW_RELEASE, ActionOwner.AUTH_REV_06),
    _planned(
        ActionId.REVIEW_DECLINE_PREFERENCE,
        PermissionId.REVIEW_DECLINE_PREFERENCE,
        ActionOwner.AUTH_REV_06,
    ),
    _planned(
        ActionId.REVIEW_PREFERENCE_EXPIRY_RUN,
        PermissionId.OPERATIONS_TIMER_RUN,
        ActionOwner.AUTH_REV_06,
    ),
    _planned(
        ActionId.REVIEW_LEASE_EXPIRY_RUN,
        PermissionId.OPERATIONS_TIMER_RUN,
        ActionOwner.AUTH_REV_06,
    ),
    _planned(
        ActionId.REVIEW_CONTEXT_READ,
        PermissionId.SUBMISSION_READ_FOR_REVIEW,
        ActionOwner.AUTH_REV_07,
    ),
    _planned(ActionId.REVIEW_CHAIN_READ, PermissionId.REVIEW_CHAIN_READ, ActionOwner.AUTH_REV_07),
    _planned(
        ActionId.REVIEW_FINDING_EVIDENCE_INGEST,
        PermissionId.REVIEW_DECISION,
        ActionOwner.AUTH_REV_07,
    ),
    _planned(ActionId.REVIEW_DECISION, PermissionId.REVIEW_DECISION, ActionOwner.AUTH_REV_08),
    _planned(
        ActionId.REVIEW_FINDING_RESPONSE_EVIDENCE_INGEST,
        PermissionId.SUBMISSION_CREATE,
        ActionOwner.AUTH_REV_09A,
    ),
    _planned(
        ActionId.REVIEW_LEASE_FORCE_RELEASE,
        PermissionId.REVIEW_LEASE_FORCE_RELEASE,
        ActionOwner.AUTH_REV_11,
    ),
    _planned(
        ActionId.REVIEW_QUEUE_ROUTING_OVERRIDE,
        PermissionId.REVIEW_QUEUE_OVERRIDE,
        ActionOwner.AUTH_REV_11,
    ),
    _planned(
        ActionId.REVIEW_QUEUE_ROUTING_CORRECT,
        PermissionId.REVIEW_QUEUE_OVERRIDE,
        ActionOwner.AUTH_REV_11,
    ),
    _planned(
        ActionId.REVIEW_QUEUE_CLOSE,
        PermissionId.REVIEW_QUEUE_OVERRIDE,
        ActionOwner.AUTH_REV_11,
    ),
    _planned(
        ActionId.REVIEW_RECONCILE_RUN,
        PermissionId.OPERATIONS_RECONCILE_RUN,
        ActionOwner.AUTH_REV_11,
    ),
    _planned(
        ActionId.REVIEW_ARTIFACT_REFERENCE_RECONCILE,
        PermissionId.OPERATIONS_RECONCILE_RUN,
        ActionOwner.AUTH_REV_12,
    ),
    _planned(
        ActionId.REVIEW_PROJECTION_REBUILD,
        PermissionId.OPERATIONS_PROJECTION_REBUILD,
        ActionOwner.AUTH_REV_12,
    ),
    _planned(
        ActionId.ARTIFACT_BINDING_READ,
        PermissionId.ARTIFACT_BINDING_READ,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _planned(
        ActionId.ARTIFACT_REPLICA_READ,
        PermissionId.ARTIFACT_REPLICA_READ,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _planned(
        ActionId.ARTIFACT_RECEIPT_READ,
        PermissionId.ARTIFACT_RECEIPT_READ,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _planned(
        ActionId.ARTIFACT_VERIFICATION_JOB_READ,
        PermissionId.ARTIFACT_VERIFICATION_JOB_READ,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _planned(
        ActionId.ARTIFACT_VERIFICATION_JOB_RETRY,
        PermissionId.ARTIFACT_VERIFICATION_JOB_RETRY,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _planned(
        ActionId.ARTIFACT_RECOVERY_ATTEMPT_READ,
        PermissionId.ARTIFACT_RECOVERY_ATTEMPT_READ,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _planned(
        ActionId.ARTIFACT_AUDIT_READ,
        PermissionId.ARTIFACT_AUDIT_READ,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _planned(
        ActionId.OPERATIONS_ARTIFACT_STORAGE_ADMISSION_READ,
        PermissionId.OPERATIONS_STATUS_READ,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _planned(
        ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
        PermissionId.ARTIFACT_GUIDE_SOURCE_INGEST,
        ActionOwner.AUTH_ART_03,
    ),
    _planned(
        ActionId.ARTIFACT_GUIDE_SOURCE_READ,
        PermissionId.ARTIFACT_GUIDE_SOURCE_READ,
        ActionOwner.AUTH_ART_03,
    ),
    _planned(
        ActionId.ARTIFACT_UPLOAD_SESSION_CREATE,
        PermissionId.ARTIFACT_UPLOAD_SESSION_CREATE,
        ActionOwner.AUTH_ART_04A,
    ),
    _planned(
        ActionId.ARTIFACT_UPLOAD_SESSION_READ,
        PermissionId.ARTIFACT_UPLOAD_SESSION_READ,
        ActionOwner.AUTH_ART_04A,
    ),
    _planned(
        ActionId.ARTIFACT_UPLOAD_ITEM_WRITE,
        PermissionId.ARTIFACT_UPLOAD_ITEM_WRITE,
        ActionOwner.AUTH_ART_04A,
    ),
    _planned(
        ActionId.ARTIFACT_UPLOAD_SESSION_SEAL,
        PermissionId.ARTIFACT_UPLOAD_SESSION_SEAL,
        ActionOwner.AUTH_ART_04A,
    ),
    _planned(
        ActionId.ARTIFACT_UPLOAD_SESSION_CANCEL,
        PermissionId.ARTIFACT_UPLOAD_SESSION_CANCEL,
        ActionOwner.AUTH_ART_04A,
    ),
    _planned(
        ActionId.ARTIFACT_UPLOAD_SESSION_EXPIRE,
        PermissionId.ARTIFACT_UPLOAD_SESSION_EXPIRE,
        ActionOwner.AUTH_ART_04A,
    ),
    _planned(
        ActionId.ARTIFACT_GUIDE_SOURCE_BINDING_CREATE,
        PermissionId.ARTIFACT_BINDING_CREATE,
        ActionOwner.AUTH_ART_03,
    ),
    _planned(
        ActionId.ARTIFACT_SUBMISSION_BINDING_CREATE,
        PermissionId.ARTIFACT_BINDING_CREATE,
        ActionOwner.AUTH_ART_05,
    ),
    _planned(
        ActionId.ARTIFACT_CHECKER_OUTPUT_BINDING_CREATE,
        PermissionId.ARTIFACT_BINDING_CREATE,
        ActionOwner.AUTH_ART_06B,
    ),
    _planned(
        ActionId.ARTIFACT_VERIFICATION_EXECUTE,
        PermissionId.ARTIFACT_VERIFICATION_EXECUTE,
        ActionOwner.AUTH_ART_02D_INTERNAL,
    ),
    _planned(
        ActionId.ARTIFACT_PENDING_WORK_SCAN,
        PermissionId.ARTIFACT_PENDING_WORK_SCAN,
        ActionOwner.AUTH_ART_02D_INTERNAL,
    ),
    _planned(
        ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
        PermissionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
        ActionOwner.AUTH_ART_02D_INTERNAL,
    ),
    _planned(
        ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE,
        PermissionId.ARTIFACT_CHECKER_INPUT_MATERIALIZE,
        ActionOwner.AUTH_ART_04B,
    ),
    _planned(
        ActionId.ARTIFACT_POST_SUBMIT_CHECKER_INPUT_MATERIALIZE,
        PermissionId.ARTIFACT_CHECKER_INPUT_MATERIALIZE,
        ActionOwner.AUTH_ART_06A,
    ),
    _planned(
        ActionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
        PermissionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
        ActionOwner.AUTH_ART_06B,
    ),
)

PERMISSION_IDS = frozenset(PermissionId)
ACTION_IDS = frozenset(ActionId)
NEW_PERMISSION_IDS = frozenset(
    {
        PermissionId.OPERATIONS_TASK_START_OVERRIDE,
        PermissionId.OPERATIONS_SUBMISSION_GATE_REPAIR,
        PermissionId.OPERATIONS_CHECKER_RETRY,
        PermissionId.REVIEW_QUEUE_OVERRIDE,
        PermissionId.ARTIFACT_BINDING_READ,
        PermissionId.ARTIFACT_REPLICA_READ,
        PermissionId.ARTIFACT_RECEIPT_READ,
        PermissionId.ARTIFACT_VERIFICATION_JOB_READ,
        PermissionId.ARTIFACT_VERIFICATION_JOB_RETRY,
        PermissionId.ARTIFACT_RECOVERY_ATTEMPT_READ,
        PermissionId.ARTIFACT_AUDIT_READ,
        PermissionId.ARTIFACT_GUIDE_SOURCE_INGEST,
        PermissionId.ARTIFACT_UPLOAD_SESSION_CREATE,
        PermissionId.ARTIFACT_UPLOAD_SESSION_READ,
        PermissionId.ARTIFACT_UPLOAD_ITEM_WRITE,
        PermissionId.ARTIFACT_UPLOAD_SESSION_SEAL,
        PermissionId.ARTIFACT_UPLOAD_SESSION_CANCEL,
        PermissionId.ARTIFACT_UPLOAD_SESSION_EXPIRE,
        PermissionId.ARTIFACT_BINDING_CREATE,
        PermissionId.ARTIFACT_VERIFICATION_EXECUTE,
        PermissionId.ARTIFACT_PENDING_WORK_SCAN,
        PermissionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
        PermissionId.ARTIFACT_GUIDE_SOURCE_READ,
        PermissionId.ARTIFACT_CHECKER_INPUT_MATERIALIZE,
        PermissionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
    }
)
HISTORICAL_PERMISSION_IDS = PERMISSION_IDS - NEW_PERMISSION_IDS


def _index_actions(
    definitions: tuple[ActionDefinition, ...],
) -> MappingProxyType[ActionId, ActionDefinition]:
    if any(
        not isinstance(definition, ActionDefinition)
        or not isinstance(definition.action_id, ActionId)
        or not isinstance(definition.permission_id, PermissionId)
        or not isinstance(definition.owner, ActionOwner)
        or not isinstance(definition.availability, ActionAvailability)
        for definition in definitions
    ):
        raise RuntimeError("authorization action catalogue contains an invalid row")
    indexed = {definition.action_id: definition for definition in definitions}
    if len(PERMISSION_IDS) != 74 or len(ACTION_IDS) != 65:
        raise RuntimeError("authorization catalogue count mismatch")
    if len(indexed) != len(definitions) or set(indexed) != ACTION_IDS:
        raise RuntimeError("authorization action catalogue is incomplete")
    if len(HISTORICAL_PERMISSION_IDS) != 49 or len(NEW_PERMISSION_IDS) != 25:
        raise RuntimeError("authorization permission boundary mismatch")
    active_actions = {
        ActionId.ACTOR_PROFILE_READ_SELF,
        ActionId.ACTOR_PROFILE_UPDATE_SELF,
        ActionId.AUTHORIZATION_PERMISSION_CATALOGUE_READ,
        ActionId.AUTHORIZATION_ADMIN_ROLE_DEFINITIONS_READ,
        ActionId.ADMIN_ROLE_GRANT_LIST,
        ActionId.ACTOR_ADMIN_ROLE_GRANT_HISTORY_READ,
        ActionId.ADMIN_ROLE_GRANT_ISSUE,
        ActionId.ADMIN_ROLE_GRANT_REVOKE,
        ActionId.ADMIN_ROLE_GRANT_BOOTSTRAP,
        ActionId.ACTOR_PROFILE_READ,
        ActionId.ACTOR_IDENTITY_LINK_READ,
        ActionId.ACTOR_SERVICE_PROVISION,
        ActionId.ACTOR_PROFILE_SUSPEND,
        ActionId.ACTOR_PROFILE_REACTIVATE,
        ActionId.ACTOR_PROFILE_DEACTIVATE,
        ActionId.ACTOR_IDENTITY_LINK_REVOKE,
        ActionId.ACTOR_IDENTITY_LINK_REACTIVATE,
    }
    if {
        definition.action_id
        for definition in definitions
        if definition.availability is ActionAvailability.ACTIVE
    } != active_actions:
        raise RuntimeError("authorization active action boundary mismatch")
    if set(definitions) != set(ACTION_DEFINITIONS):
        raise RuntimeError("authorization action metadata mismatch")
    if {definition.owner for definition in definitions} != set(ActionOwner):
        raise RuntimeError("authorization action owner catalogue is incomplete")
    return MappingProxyType(indexed)


ACTION_BY_ID = _index_actions(ACTION_DEFINITIONS)


_SERVICE_ACTIONS = {
    ServiceIdentity.ARTIFACT_VERIFIER: frozenset({ActionId.ARTIFACT_VERIFICATION_EXECUTE}),
    ServiceIdentity.ARTIFACT_PUT_RESOLVER: frozenset({ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE}),
    ServiceIdentity.ARTIFACT_SCHEDULER: frozenset(
        {ActionId.ARTIFACT_PENDING_WORK_SCAN, ActionId.ARTIFACT_UPLOAD_SESSION_EXPIRE}
    ),
    ServiceIdentity.ARTIFACT_BINDING: frozenset(
        {
            ActionId.ARTIFACT_GUIDE_SOURCE_BINDING_CREATE,
            ActionId.ARTIFACT_SUBMISSION_BINDING_CREATE,
            ActionId.ARTIFACT_CHECKER_OUTPUT_BINDING_CREATE,
        }
    ),
    ServiceIdentity.ARTIFACT_GUIDE_READER: frozenset(
        {ActionId.ARTIFACT_GUIDE_SOURCE_READ}
    ),
    ServiceIdentity.ARTIFACT_MATERIALIZER: frozenset(
        {
            ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE,
            ActionId.ARTIFACT_POST_SUBMIT_CHECKER_INPUT_MATERIALIZE,
        }
    ),
    ServiceIdentity.ARTIFACT_CHECKER_OUTPUT: frozenset(
        {ActionId.ARTIFACT_CHECKER_OUTPUT_WRITE}
    ),
}


def _index_service_actions(
    rows: dict[ServiceIdentity, frozenset[ActionId]],
) -> MappingProxyType[ServiceIdentity, frozenset[ActionId]]:
    """Validate the exact fixed service matrix and return an immutable view."""
    expected_rows = {
        ServiceIdentity.ARTIFACT_VERIFIER: frozenset(
            {ActionId.ARTIFACT_VERIFICATION_EXECUTE}
        ),
        ServiceIdentity.ARTIFACT_PUT_RESOLVER: frozenset(
            {ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE}
        ),
        ServiceIdentity.ARTIFACT_SCHEDULER: frozenset(
            {ActionId.ARTIFACT_PENDING_WORK_SCAN, ActionId.ARTIFACT_UPLOAD_SESSION_EXPIRE}
        ),
        ServiceIdentity.ARTIFACT_BINDING: frozenset(
            {
                ActionId.ARTIFACT_GUIDE_SOURCE_BINDING_CREATE,
                ActionId.ARTIFACT_SUBMISSION_BINDING_CREATE,
                ActionId.ARTIFACT_CHECKER_OUTPUT_BINDING_CREATE,
            }
        ),
        ServiceIdentity.ARTIFACT_GUIDE_READER: frozenset(
            {ActionId.ARTIFACT_GUIDE_SOURCE_READ}
        ),
        ServiceIdentity.ARTIFACT_MATERIALIZER: frozenset(
            {
                ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE,
                ActionId.ARTIFACT_POST_SUBMIT_CHECKER_INPUT_MATERIALIZE,
            }
        ),
        ServiceIdentity.ARTIFACT_CHECKER_OUTPUT: frozenset(
            {ActionId.ARTIFACT_CHECKER_OUTPUT_WRITE}
        ),
    }
    expected_metadata = {
        ActionId.ARTIFACT_VERIFICATION_EXECUTE: (
            PermissionId.ARTIFACT_VERIFICATION_EXECUTE,
            ActionOwner.AUTH_ART_02D_INTERNAL,
        ),
        ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE: (
            PermissionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
            ActionOwner.AUTH_ART_02D_INTERNAL,
        ),
        ActionId.ARTIFACT_PENDING_WORK_SCAN: (
            PermissionId.ARTIFACT_PENDING_WORK_SCAN,
            ActionOwner.AUTH_ART_02D_INTERNAL,
        ),
        ActionId.ARTIFACT_UPLOAD_SESSION_EXPIRE: (
            PermissionId.ARTIFACT_UPLOAD_SESSION_EXPIRE,
            ActionOwner.AUTH_ART_04A,
        ),
        ActionId.ARTIFACT_GUIDE_SOURCE_BINDING_CREATE: (
            PermissionId.ARTIFACT_BINDING_CREATE,
            ActionOwner.AUTH_ART_03,
        ),
        ActionId.ARTIFACT_SUBMISSION_BINDING_CREATE: (
            PermissionId.ARTIFACT_BINDING_CREATE,
            ActionOwner.AUTH_ART_05,
        ),
        ActionId.ARTIFACT_CHECKER_OUTPUT_BINDING_CREATE: (
            PermissionId.ARTIFACT_BINDING_CREATE,
            ActionOwner.AUTH_ART_06B,
        ),
        ActionId.ARTIFACT_GUIDE_SOURCE_READ: (
            PermissionId.ARTIFACT_GUIDE_SOURCE_READ,
            ActionOwner.AUTH_ART_03,
        ),
        ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE: (
            PermissionId.ARTIFACT_CHECKER_INPUT_MATERIALIZE,
            ActionOwner.AUTH_ART_04B,
        ),
        ActionId.ARTIFACT_POST_SUBMIT_CHECKER_INPUT_MATERIALIZE: (
            PermissionId.ARTIFACT_CHECKER_INPUT_MATERIALIZE,
            ActionOwner.AUTH_ART_06A,
        ),
        ActionId.ARTIFACT_CHECKER_OUTPUT_WRITE: (
            PermissionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
            ActionOwner.AUTH_ART_06B,
        ),
    }
    if set(rows) != SERVICE_IDENTITIES:
        raise RuntimeError("service action matrix identity mismatch")
    if rows != expected_rows:
        raise RuntimeError("service action matrix row mismatch")
    for action, (permission, owner) in expected_metadata.items():
        definition = ACTION_BY_ID[action]
        if (
            definition.permission_id is not permission
            or definition.owner is not owner
            or definition.availability is not ActionAvailability.PLANNED
        ):
            raise RuntimeError("service action matrix metadata mismatch")
    return MappingProxyType(dict(rows))


SERVICE_ACTIONS_BY_IDENTITY = _index_service_actions(_SERVICE_ACTIONS)


def resolve_executable_action(action_id: ActionId) -> ActionDefinition:
    """Return active metadata and fail closed for planned actions."""
    definition = ACTION_BY_ID[action_id]
    if definition.availability is not ActionAvailability.ACTIVE:
        raise ValueError("authorization action is not active")
    return definition
