"""Closed immutable authorization action definition rows."""

from app.modules.authorization import catalogue as _catalogue

ActionId = _catalogue.ActionId
PermissionId = _catalogue.PermissionId
ActionOwner = _catalogue.ActionOwner
CONTRIBUTOR_WORK_READ_ACTIONS = _catalogue.CONTRIBUTOR_WORK_READ_ACTIONS
PROJECT_GUIDE_READ_ACTIONS = _catalogue.PROJECT_GUIDE_READ_ACTIONS
PROJECT_WORK_READ_ACTIONS = _catalogue.PROJECT_WORK_READ_ACTIONS
_CONTRIBUTION_POLICY_ACTION_IDS = _catalogue._CONTRIBUTION_POLICY_ACTION_IDS
_active = _catalogue._active
_planned = _catalogue._planned


ACTION_DEFINITIONS = (
    _active(ActionId.SUBMISSION_INTAKE_RESERVE, PermissionId.SUBMISSION_CREATE, ActionOwner.SUBMISSION_INTAKE),
    _active(ActionId.TASK_SUBMISSION_OPERATION_READ, PermissionId.SUBMISSION_READ_OWN, ActionOwner.SUBMISSION_INTAKE),
    _active(
        ActionId.ACTOR_PROJECT_LIST, PermissionId.ACTOR_PROFILE_READ_SELF, ActionOwner.PILOT_READ_2
    ),
    *(
        _active(action, PermissionId.SUBMISSION_READ_OWN, ActionOwner.PILOT_READ_2)
        for action in sorted(CONTRIBUTOR_WORK_READ_ACTIONS - {ActionId.TASK_SUBMISSION_OPERATION_READ})
    ),
    *(
        _active(a, PermissionId.PROJECT_GUIDE_MANAGE, ActionOwner.PILOT_READ_3)
        for a in sorted(PROJECT_GUIDE_READ_ACTIONS)
    ),
    *(
        _active(a, PermissionId.PROJECT_TASK_MANAGE, ActionOwner.PILOT_READ_3)
        for a in sorted(PROJECT_WORK_READ_ACTIONS)
    ),
    _active(
        ActionId.CONTRIBUTION_POLICY_LIST,
        PermissionId.COMPENSATION_POLICY_MANAGE,
        ActionOwner.PILOT_READ_3,
    ),
    _active(
        ActionId.CONTRIBUTION_READ_SELF, PermissionId.CONTRIBUTION_READ_SELF, ActionOwner.PILOT_10
    ),
    _active(
        ActionId.CONTRIBUTION_READ_PROJECT,
        PermissionId.CONTRIBUTION_READ_PROJECT,
        ActionOwner.PILOT_10,
    ),
    _active(
        ActionId.TASK_POST_SUBMIT_ROUTE, PermissionId.TASK_POST_SUBMIT_ROUTE, ActionOwner.ARCH_04E2
    ),
    _active(
        ActionId.TASK_ASSIGNMENT_AUTHORITY_RECONCILE,
        PermissionId.TASK_ASSIGNMENT_AUTHORITY_RECONCILE,
        ActionOwner.ARCH_03C1,
    ),
    _active(ActionId.TASK_REVISION_EXPIRE, PermissionId.TASK_REVISION_EXPIRE, ActionOwner.PILOT_08),
    _active(
        ActionId.TASK_REVISION_RECOVER, PermissionId.TASK_REVISION_RECOVER, ActionOwner.PILOT_08
    ),
    _active(ActionId.OUTBOX_DISPATCH, PermissionId.OUTBOX_DISPATCH, ActionOwner.AUTH_OUTBOX_01),
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
    _active(ActionId.ADMIN_ROLE_GRANT_LIST, PermissionId.ADMIN_ROLE_READ, ActionOwner.AUTH_08),
    _active(
        ActionId.ACTOR_ADMIN_ROLE_GRANT_HISTORY_READ,
        PermissionId.ADMIN_ROLE_READ,
        ActionOwner.AUTH_08,
    ),
    _active(ActionId.ADMIN_ROLE_GRANT_ISSUE, PermissionId.ADMIN_ROLE_GRANT, ActionOwner.AUTH_08),
    _active(ActionId.ADMIN_ROLE_GRANT_REVOKE, PermissionId.ADMIN_ROLE_REVOKE, ActionOwner.AUTH_08),
    _active(
        ActionId.ADMIN_ROLE_GRANT_BOOTSTRAP, PermissionId.ADMIN_ROLE_GRANT, ActionOwner.AUTH_08
    ),
    _active(ActionId.ACTOR_PROFILE_READ, PermissionId.ACTOR_PROFILE_READ_ANY, ActionOwner.AUTH_09C),
    _active(
        ActionId.ACTOR_PROFILE_SUSPEND, PermissionId.ACTOR_PROFILE_SUSPEND, ActionOwner.AUTH_09D_A
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
        ActionId.ACTOR_SERVICE_PROVISION, PermissionId.ACTOR_SERVICE_PROVISION, ActionOwner.AUTH_09B
    ),
    _active(
        ActionId.PROJECT_CONTRIBUTOR_CANDIDATE_LIST,
        PermissionId.PROJECT_ROLE_GRANT_MANAGE,
        ActionOwner.AUTH_10B,
    ),
    _active(
        ActionId.PROJECT_ROLE_GRANT_LIST, PermissionId.PROJECT_ROLE_GRANT_READ, ActionOwner.AUTH_10B
    ),
    _active(
        ActionId.PROJECT_ROLE_GRANT_READ, PermissionId.PROJECT_ROLE_GRANT_READ, ActionOwner.AUTH_10B
    ),
    _active(
        ActionId.PROJECT_ROLE_GRANT_ISSUE,
        PermissionId.PROJECT_ROLE_GRANT_MANAGE,
        ActionOwner.AUTH_10C,
    ),
    _active(
        ActionId.PROJECT_ROLE_GRANT_REVOKE,
        PermissionId.PROJECT_ROLE_GRANT_MANAGE,
        ActionOwner.AUTH_10C,
    ),
    _active(ActionId.PROJECT_READ, PermissionId.PROJECT_READ, ActionOwner.AUTH_11B),
    _active(ActionId.PROJECT_CATALOGUE_LIST, PermissionId.PROJECT_READ, ActionOwner.CLI_46),
    _active(
        ActionId.ACTOR_AUTHORIZATION_CONTEXT_READ,
        PermissionId.ACTOR_PROFILE_READ_SELF,
        ActionOwner.AUTH_11B,
    ),
    _active(
        ActionId.PROJECT_SETUP_RUN_READ,
        PermissionId.PROJECT_SETUP_DIAGNOSTIC_READ,
        ActionOwner.AUTH_11C1,
    ),
    _active(
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_LIST,
        PermissionId.PROJECT_SETUP_DIAGNOSTIC_READ,
        ActionOwner.AUTH_11C1,
    ),
    _active(
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_READ,
        PermissionId.PROJECT_SETUP_DIAGNOSTIC_READ,
        ActionOwner.AUTH_11C1,
    ),
    _active(
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_LIST,
        PermissionId.PROJECT_EFFECTIVE_POLICY_READ,
        ActionOwner.AUTH_11C1,
    ),
    _active(
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_READ,
        PermissionId.PROJECT_EFFECTIVE_POLICY_READ,
        ActionOwner.AUTH_11C1,
    ),
    _active(
        ActionId.PROJECT_EFFECTIVE_SUBMISSION_ARTIFACT_POLICY_READ,
        PermissionId.PROJECT_EFFECTIVE_POLICY_READ,
        ActionOwner.AUTH_11C2,
    ),
    _active(
        ActionId.PROJECT_PRE_SUBMIT_CHECKER_POLICY_READ,
        PermissionId.PROJECT_EFFECTIVE_POLICY_READ,
        ActionOwner.AUTH_11C2,
    ),
    _active(ActionId.PROJECT_ACTIVE_GUIDE_READ, PermissionId.PROJECT_READ, ActionOwner.AUTH_11C2),
    _active(ActionId.PROJECT_CREATE, PermissionId.PROJECT_CREATE, ActionOwner.AUTH_12C),
    _active(ActionId.PROJECT_GUIDE_CREATE, PermissionId.PROJECT_GUIDE_MANAGE, ActionOwner.AUTH_12D),
    _active(ActionId.PROJECT_GUIDE_UPDATE, PermissionId.PROJECT_GUIDE_MANAGE, ActionOwner.AUTH_12D),
    _active(
        ActionId.PROJECT_GUIDE_SOURCE_SNAPSHOT_CREATE,
        PermissionId.PROJECT_GUIDE_MANAGE,
        ActionOwner.AUTH_12D,
    ),
    _active(
        ActionId.PROJECT_GUIDE_COMPILATION_REQUEST,
        PermissionId.PROJECT_GUIDE_COMPILATION_REQUEST,
        ActionOwner.AUTH_12I,
    ),
    _planned(
        ActionId.PROJECT_GUIDE_COMPILATION_REQUEST_AUTOMATIC,
        PermissionId.PROJECT_GUIDE_COMPILATION_EXECUTE,
        ActionOwner.AUTH_12I,
    ),
    _active(
        ActionId.PROJECT_GUIDE_COMPILATION_EXECUTE,
        PermissionId.PROJECT_GUIDE_COMPILATION_EXECUTE,
        ActionOwner.AUTH_12I,
    ),
    _active(
        ActionId.PROJECT_REVIEW_POLICY_UPDATE,
        PermissionId.PROJECT_REVIEW_POLICY_MANAGE,
        ActionOwner.XINT_003_02B,
    ),
    _active(
        ActionId.PROJECT_REVISION_POLICY_UPDATE,
        PermissionId.PROJECT_REVIEW_POLICY_MANAGE,
        ActionOwner.XINT_003_02B,
    ),
    _active(
        ActionId.PROJECT_GUIDE_SUFFICIENCY_REPORT_CREATE,
        PermissionId.PROJECT_GUIDE_MANAGE,
        ActionOwner.AUTH_12E,
    ),
    _active(
        ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN,
        PermissionId.PROJECT_GUIDE_MANAGE,
        ActionOwner.AUTH_12E,
    ),
    _active(
        ActionId.PROJECT_GUIDE_SUFFICIENCY_WARNINGS_ACKNOWLEDGE,
        PermissionId.PROJECT_GUIDE_MANAGE,
        ActionOwner.AUTH_12E,
    ),
    _active(
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE,
        PermissionId.PROJECT_EFFECTIVE_POLICY_MANAGE,
        ActionOwner.AUTH_12F2,
    ),
    _active(
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE,
        PermissionId.PROJECT_EFFECTIVE_POLICY_MANAGE,
        ActionOwner.AUTH_12F3,
    ),
    _active(
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE,
        PermissionId.PROJECT_EFFECTIVE_POLICY_MANAGE,
        ActionOwner.AUTH_12F2,
    ),
    _active(
        ActionId.PROJECT_GUIDE_COMPILATION_REVIEW_PACKAGE_READ,
        PermissionId.PROJECT_GUIDE_MANAGE,
        ActionOwner.AUTH_12F4,
    ),
    _active(
        ActionId.PROJECT_GUIDE_COMPILATION_CORRECTION_REQUEST,
        PermissionId.PROJECT_GUIDE_COMPILATION_REQUEST,
        ActionOwner.AUTH_12F4,
    ),
    _active(
        ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_APPROVE,
        PermissionId.PROJECT_EFFECTIVE_POLICY_MANAGE,
        ActionOwner.AUTH_12F4,
    ),
    _active(
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_APPROVE,
        PermissionId.PROJECT_EFFECTIVE_POLICY_MANAGE,
        ActionOwner.AUTH_12G,
    ),
    _active(
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_CORRECTION_REQUEST,
        PermissionId.PROJECT_EFFECTIVE_POLICY_MANAGE,
        ActionOwner.AUTH_12G,
    ),
    _active(
        ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_DERIVE,
        PermissionId.PROJECT_EFFECTIVE_POLICY_MANAGE,
        ActionOwner.AUTH_12G,
    ),
    _active(
        ActionId.PROJECT_SETUP_RUN_UPDATE, PermissionId.PROJECT_GUIDE_MANAGE, ActionOwner.AUTH_12B2
    ),
    _active(
        ActionId.PROJECT_GUIDE_ACTIVATE, PermissionId.PROJECT_GUIDE_MANAGE, ActionOwner.AUTH_12H
    ),
    _active(
        ActionId.TASK_SUBMISSION_LIST,
        PermissionId.SUBMISSION_READ_OWN,
        ActionOwner.TASK_CHECKER_CLEANUP,
    ),
    _active(
        ActionId.SUBMISSION_READ, PermissionId.SUBMISSION_READ_OWN, ActionOwner.TASK_CHECKER_CLEANUP
    ),
    _active(
        ActionId.SUBMISSION_CHECKER_RUN_LIST,
        PermissionId.SUBMISSION_READ_OWN,
        ActionOwner.TASK_CHECKER_CLEANUP,
    ),
    _active(
        ActionId.CHECKER_RUN_READ,
        PermissionId.SUBMISSION_READ_OWN,
        ActionOwner.TASK_CHECKER_CLEANUP,
    ),
    _active(
        ActionId.PROJECT_TASK_SUBMISSION_LIST,
        PermissionId.PROJECT_TASK_MANAGE,
        ActionOwner.TASK_CHECKER_CLEANUP,
    ),
    _active(
        ActionId.PROJECT_SUBMISSION_READ,
        PermissionId.PROJECT_TASK_MANAGE,
        ActionOwner.TASK_CHECKER_CLEANUP,
    ),
    _active(
        ActionId.PROJECT_SUBMISSION_CHECKER_RUN_LIST,
        PermissionId.PROJECT_TASK_MANAGE,
        ActionOwner.TASK_CHECKER_CLEANUP,
    ),
    _active(
        ActionId.PROJECT_CHECKER_RUN_READ,
        PermissionId.PROJECT_TASK_MANAGE,
        ActionOwner.TASK_CHECKER_CLEANUP,
    ),
    _active(ActionId.TASK_CLAIM, PermissionId.TASK_CLAIM, ActionOwner.TASK_PROJECT_GRANT),
    _active(
        ActionId.TASK_WORK_CONTEXT_READ,
        PermissionId.TASK_QUEUE_READ,
        ActionOwner.TASK_PROJECT_GRANT,
    ),
    _active(ActionId.TASK_GUIDE_READ, PermissionId.TASK_QUEUE_READ, ActionOwner.PILOT_13),
    _active(ActionId.TASK_READ, PermissionId.TASK_QUEUE_READ, ActionOwner.ARCH_03C5),
    _active(
        ActionId.TASK_SUBMISSION_REQUIREMENTS_READ,
        PermissionId.TASK_QUEUE_READ,
        ActionOwner.ARCH_03C5,
    ),
    _active(ActionId.PROJECT_TASK_READ, PermissionId.PROJECT_TASK_MANAGE, ActionOwner.ARCH_03C5),
    _active(
        ActionId.PROJECT_TASK_LOCKED_CONTEXT_READ,
        PermissionId.PROJECT_TASK_MANAGE,
        ActionOwner.ARCH_03C6,
    ),
    _active(
        ActionId.OPERATIONS_TASK_LOCKED_CONTEXT_READ,
        PermissionId.OPERATIONS_STATUS_READ,
        ActionOwner.ARCH_03C6,
    ),
    _active(
        ActionId.AUDIT_TASK_LOCKED_CONTEXT_READ, PermissionId.AUDIT_READ, ActionOwner.ARCH_03C6
    ),
    _active(ActionId.AUDIT_TASK_EVIDENCE_READ, PermissionId.AUDIT_READ, ActionOwner.ARCH_03C7),
    _active(
        ActionId.PROJECT_TASK_SUBMISSION_REQUIREMENTS_READ,
        PermissionId.PROJECT_TASK_MANAGE,
        ActionOwner.ARCH_03C5,
    ),
    _active(ActionId.TASK_QUEUE_READ, PermissionId.TASK_QUEUE_READ, ActionOwner.ARCH_03C4),
    _active(
        ActionId.PROJECT_TASK_QUEUE_READ, PermissionId.PROJECT_TASK_MANAGE, ActionOwner.ARCH_03C4
    ),
    _active(
        ActionId.OPERATIONS_TASK_QUEUE_READ,
        PermissionId.OPERATIONS_STATUS_READ,
        ActionOwner.ARCH_03C4,
    ),
    _active(ActionId.PROJECT_TASK_CREATE, PermissionId.PROJECT_TASK_MANAGE, ActionOwner.ARCH_03C3),
    _active(ActionId.PROJECT_TASK_IMPORT, PermissionId.PROJECT_TASK_MANAGE, ActionOwner.PILOT_02B),
    _active(
        ActionId.PROJECT_TASK_IMPORT_BATCH_READ,
        PermissionId.PROJECT_TASK_MANAGE,
        ActionOwner.PILOT_02B,
    ),
    _active(
        ActionId.ARTIFACT_TASK_IMPORT_SOURCE_DECLARE,
        PermissionId.PROJECT_TASK_MANAGE,
        ActionOwner.PILOT_02A,
    ),
    _active(
        ActionId.ARTIFACT_TASK_IMPORT_SOURCE_UPLOAD,
        PermissionId.PROJECT_TASK_MANAGE,
        ActionOwner.PILOT_02A,
    ),
    _active(
        ActionId.ARTIFACT_TASK_IMPORT_SOURCE_READ,
        PermissionId.PROJECT_TASK_MANAGE,
        ActionOwner.PILOT_02A,
    ),
    _active(ActionId.PROJECT_TASK_SCREEN, PermissionId.PROJECT_TASK_MANAGE, ActionOwner.ARCH_03C3),
    _active(ActionId.PROJECT_TASK_RELEASE, PermissionId.PROJECT_TASK_MANAGE, ActionOwner.ARCH_03C3),
    _active(
        ActionId.PROJECT_TASK_REVISION_REPAIR,
        PermissionId.PROJECT_TASK_MANAGE,
        ActionOwner.PILOT_08,
    ),
    _active(
        ActionId.PROJECT_TASK_WORK_CONTEXT_READ,
        PermissionId.PROJECT_TASK_MANAGE,
        ActionOwner.TASK_PROJECT_GRANT,
    ),
    _active(
        ActionId.OPERATIONS_SUBMISSION_GATE_REPAIR,
        PermissionId.OPERATIONS_SUBMISSION_GATE_REPAIR,
        ActionOwner.AUTH_14,
    ),
    _active(
        ActionId.OPERATIONS_CHECKER_RETRY,
        PermissionId.OPERATIONS_CHECKER_RETRY,
        ActionOwner.AUTH_14,
    ),
    _active(
        ActionId.OPERATIONS_CHECKER_RETRY_SOURCE_LIST,
        PermissionId.OPERATIONS_STATUS_READ,
        ActionOwner.AUTH_14,
    ),
    _active(
        ActionId.OPERATIONS_POST_SUBMIT_DELIVERY_LIST,
        PermissionId.OPERATIONS_STATUS_READ,
        ActionOwner.AUTH_14,
    ),
    _active(
        ActionId.OPERATIONS_POST_SUBMIT_DELIVERY_RECONCILE,
        PermissionId.OPERATIONS_RECONCILE_RUN,
        ActionOwner.AUTH_14,
    ),
    _active(
        ActionId.CHECKER_REGISTRY_READ, PermissionId.OPERATIONS_STATUS_READ, ActionOwner.PILOT_04
    ),
    _active(
        ActionId.CHECKER_REGISTRY_REGISTER,
        PermissionId.OPERATIONS_RECONCILE_RUN,
        ActionOwner.PILOT_04,
    ),
    _active(ActionId.SUBMISSION_CREATE, PermissionId.SUBMISSION_CREATE, ActionOwner.AUTH_14),
    _planned(ActionId.REVIEW_QUEUE_READ, PermissionId.REVIEW_QUEUE_READ, ActionOwner.AUTH_REV_05),
    _planned(
        ActionId.REVIEW_QUEUE_INSPECT, PermissionId.REVIEW_QUEUE_INSPECT, ActionOwner.AUTH_REV_05
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
        ActionId.REVIEW_LEASE_EXPIRY_RUN, PermissionId.OPERATIONS_TIMER_RUN, ActionOwner.AUTH_REV_06
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
        ActionId.REVIEW_QUEUE_CLOSE, PermissionId.REVIEW_QUEUE_OVERRIDE, ActionOwner.AUTH_REV_11
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
        ActionId.REVIEW_REVISION_CONTEXT_REPAIR,
        PermissionId.PROJECT_TASK_MANAGE,
        ActionOwner.XINT_003_08A,
    ),
    _planned(
        ActionId.REVIEW_REVISION_CONTEXT_LEGACY_CLOSE,
        PermissionId.OPERATIONS_RECONCILE_RUN,
        ActionOwner.XINT_003_08A,
    ),
    _active(
        ActionId.REVIEW_LIFECYCLE_ACTIVATION_MANAGE,
        PermissionId.OPERATIONS_RECONCILE_RUN,
        ActionOwner.XINT_003_08B,
    ),
    _active(
        ActionId.ARTIFACT_BINDING_READ,
        PermissionId.ARTIFACT_BINDING_READ,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _active(
        ActionId.ARTIFACT_REPLICA_READ,
        PermissionId.ARTIFACT_REPLICA_READ,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _active(
        ActionId.ARTIFACT_RECEIPT_READ,
        PermissionId.ARTIFACT_RECEIPT_READ,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _active(
        ActionId.ARTIFACT_VERIFICATION_JOB_READ,
        PermissionId.ARTIFACT_VERIFICATION_JOB_READ,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _active(
        ActionId.ARTIFACT_VERIFICATION_JOB_RETRY,
        PermissionId.ARTIFACT_VERIFICATION_JOB_RETRY,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _active(
        ActionId.ARTIFACT_RECOVERY_ATTEMPT_READ,
        PermissionId.ARTIFACT_RECOVERY_ATTEMPT_READ,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _active(
        ActionId.ARTIFACT_AUDIT_READ,
        PermissionId.ARTIFACT_AUDIT_READ,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _active(
        ActionId.OPERATIONS_ARTIFACT_STORAGE_ADMISSION_READ,
        PermissionId.OPERATIONS_STATUS_READ,
        ActionOwner.AUTH_ART_02D_OPERATOR,
    ),
    _active(
        ActionId.ARTIFACT_GUIDE_SOURCE_INGEST,
        PermissionId.ARTIFACT_GUIDE_SOURCE_INGEST,
        ActionOwner.XINT_002_04A,
    ),
    _active(
        ActionId.ARTIFACT_GUIDE_SOURCE_READ,
        PermissionId.ARTIFACT_GUIDE_SOURCE_READ,
        ActionOwner.XINT_002_04B,
    ),
    _active(
        ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE,
        PermissionId.SUBMISSION_CREATE,
        ActionOwner.XINT_002_05A,
    ),
    _active(
        ActionId.ARTIFACT_SOURCE_CLEANUP,
        PermissionId.ARTIFACT_SOURCE_CLEANUP,
        ActionOwner.AUTH_ART_02D_INTERNAL,
    ),
    _active(
        ActionId.ARTIFACT_SUBMISSION_FINALIZE,
        PermissionId.ARTIFACT_BINDING_CREATE,
        ActionOwner.AUTH_ART_05,
    ),
    _active(
        ActionId.ARTIFACT_SUBMISSION_BINDING_CREATE,
        PermissionId.ARTIFACT_BINDING_CREATE,
        ActionOwner.AUTH_ART_05,
    ),
    _active(
        ActionId.ARTIFACT_CHECKER_OUTPUT_BINDING_CREATE,
        PermissionId.ARTIFACT_BINDING_CREATE,
        ActionOwner.AUTH_ART_06B,
    ),
    _active(
        ActionId.ARTIFACT_VERIFICATION_EXECUTE,
        PermissionId.ARTIFACT_VERIFICATION_EXECUTE,
        ActionOwner.AUTH_ART_02D_INTERNAL,
    ),
    _active(
        ActionId.ARTIFACT_PENDING_WORK_SCAN,
        PermissionId.ARTIFACT_PENDING_WORK_SCAN,
        ActionOwner.AUTH_ART_02D_INTERNAL,
    ),
    _active(
        ActionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
        PermissionId.ARTIFACT_PUT_ATTEMPT_RESOLVE,
        ActionOwner.AUTH_ART_02D_INTERNAL,
    ),
    _active(
        ActionId.CHECKER_PRE_SUBMIT_EXECUTE,
        PermissionId.CHECKER_PRE_SUBMIT_EXECUTE,
        ActionOwner.PILOT_04,
    ),
    _active(
        ActionId.CHECKER_PRE_SUBMIT_FINALIZE,
        PermissionId.CHECKER_PRE_SUBMIT_FINALIZE,
        ActionOwner.PILOT_04,
    ),
    _active(
        ActionId.CHECKER_POST_SUBMIT_EXECUTE,
        PermissionId.CHECKER_POST_SUBMIT_EXECUTE,
        ActionOwner.ARCH_04D2,
    ),
    _active(
        ActionId.CHECKER_POST_SUBMIT_FINALIZE,
        PermissionId.CHECKER_POST_SUBMIT_FINALIZE,
        ActionOwner.ARCH_04D2,
    ),
    _active(
        ActionId.CHECKER_MODEL_CALL_PREPARE,
        PermissionId.CHECKER_MODEL_CALL_PREPARE,
        ActionOwner.PILOT_05,
    ),
    _active(
        ActionId.CHECKER_MODEL_CALL_DISPATCH,
        PermissionId.CHECKER_MODEL_CALL_DISPATCH,
        ActionOwner.PILOT_05,
    ),
    _active(
        ActionId.CHECKER_MODEL_CALL_RECOVER,
        PermissionId.CHECKER_MODEL_CALL_RECOVER,
        ActionOwner.PILOT_05,
    ),
    _active(
        ActionId.CHECKER_MODEL_CALL_OBSERVE,
        PermissionId.CHECKER_MODEL_CALL_OBSERVE,
        ActionOwner.PILOT_05,
    ),
    _active(
        ActionId.CHECKER_MODEL_CALL_COMPLETE,
        PermissionId.CHECKER_MODEL_CALL_COMPLETE,
        ActionOwner.PILOT_05,
    ),
    _active(
        ActionId.CHECKER_MODEL_CALL_GRANT,
        PermissionId.CHECKER_MODEL_CALL_GRANT,
        ActionOwner.PILOT_05,
    ),
    _active(
        ActionId.PROJECT_GUIDE_COMPILATION_MODEL_PREPARE,
        PermissionId.PROJECT_GUIDE_COMPILATION_MODEL_PREPARE,
        ActionOwner.PILOT_05,
    ),
    _active(
        ActionId.PROJECT_GUIDE_COMPILATION_MODEL_DISPATCH,
        PermissionId.PROJECT_GUIDE_COMPILATION_MODEL_DISPATCH,
        ActionOwner.PILOT_05,
    ),
    _active(
        ActionId.PROJECT_GUIDE_COMPILATION_MODEL_OBSERVE,
        PermissionId.PROJECT_GUIDE_COMPILATION_MODEL_OBSERVE,
        ActionOwner.PILOT_05,
    ),
    _active(
        ActionId.PROJECT_GUIDE_COMPILATION_MODEL_COMPLETE,
        PermissionId.PROJECT_GUIDE_COMPILATION_MODEL_COMPLETE,
        ActionOwner.PILOT_05,
    ),
    _active(
        ActionId.PROJECT_MODEL_PROFILE_PROVISION,
        PermissionId.PROJECT_MODEL_PROFILE_MANAGE,
        ActionOwner.PILOT_05,
    ),
    _active(
        ActionId.PROJECT_MODEL_BUDGET_CONFIGURE,
        PermissionId.PROJECT_MODEL_BUDGET_MANAGE,
        ActionOwner.PILOT_05,
    ),
    _active(
        ActionId.PROJECT_MODEL_USAGE_READ,
        PermissionId.PROJECT_MODEL_BUDGET_MANAGE,
        ActionOwner.PILOT_05,
    ),
    _active(
        ActionId.PROJECT_MODEL_CALL_RECOVERY_CHILD_AUTHORIZE,
        PermissionId.PROJECT_MODEL_CALL_RECOVERY_CHILD_AUTHORIZE,
        ActionOwner.PILOT_05,
    ),
    _active(
        ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE,
        PermissionId.ARTIFACT_CHECKER_INPUT_MATERIALIZE,
        ActionOwner.XINT_002_06A,
    ),
    _active(
        ActionId.ARTIFACT_POST_SUBMIT_CHECKER_INPUT_MATERIALIZE,
        PermissionId.ARTIFACT_CHECKER_INPUT_MATERIALIZE,
        ActionOwner.AUTH_ART_06A,
    ),
    _active(
        ActionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
        PermissionId.ARTIFACT_CHECKER_OUTPUT_WRITE,
        ActionOwner.AUTH_ART_06B,
    ),
    _planned(
        ActionId.ARTIFACT_REVIEW_PACKET_MATERIALIZE,
        PermissionId.ARTIFACT_REVIEW_PACKET_MATERIALIZE,
        ActionOwner.XINT_002_07,
    ),
    _planned(
        ActionId.ARTIFACT_REVIEW_EVIDENCE_BINDING_CREATE,
        PermissionId.ARTIFACT_BINDING_CREATE,
        ActionOwner.XINT_002_07,
    ),
    *(
        _active(action, PermissionId.COMPENSATION_ADAPTER_BINDING_MANAGE, ActionOwner.ARCH_CP01A)
        for action in (
            ActionId.COMPENSATION_ADAPTER_BINDING_READ,
            ActionId.COMPENSATION_ADAPTER_BINDING_CREATE,
            ActionId.COMPENSATION_ADAPTER_BINDING_SUSPEND,
            ActionId.COMPENSATION_ADAPTER_BINDING_RESUME,
        )
    ),
    *(
        _active(action, PermissionId.COMPENSATION_POLICY_MANAGE, ActionOwner.ARCH_CP01B)
        for action in _CONTRIBUTION_POLICY_ACTION_IDS
    ),
    _active(
        ActionId.CONTRIBUTION_COMPENSATION_UNIT_CREATE,
        PermissionId.COMPENSATION_POLICY_MANAGE,
        ActionOwner.PROJECT_POINTS_UNIT_CREATION,
    ),
)
