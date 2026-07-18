"""Immutable administrative role and permission definitions."""

from __future__ import annotations

from types import MappingProxyType

from app.modules.authorization.catalogue import PermissionId
from app.modules.authorization.schemas import AdminRole, AdminScope


ADMIN_ROLE_PERMISSIONS = MappingProxyType(
    {
        AdminRole.ACCESS_ADMINISTRATOR: (
            PermissionId.ACTOR_PROFILE_READ_ANY,
            PermissionId.ACTOR_PROFILE_SUSPEND,
            PermissionId.ACTOR_PROFILE_REACTIVATE,
            PermissionId.ACTOR_PROFILE_DEACTIVATE,
            PermissionId.ACTOR_IDENTITY_LINK_READ,
            PermissionId.ACTOR_IDENTITY_LINK_REVOKE,
            PermissionId.ACTOR_IDENTITY_LINK_REACTIVATE,
            PermissionId.ACTOR_SERVICE_PROVISION,
            PermissionId.ADMIN_ROLE_READ,
            PermissionId.ADMIN_ROLE_GRANT,
            PermissionId.ADMIN_ROLE_REVOKE,
            PermissionId.AUDIT_READ,
            PermissionId.AUDIT_EXPORT,
        ),
        AdminRole.OPERATOR: (
            PermissionId.PROJECT_READ,
            PermissionId.REVIEW_QUEUE_INSPECT,
            PermissionId.REVIEW_LEASE_FORCE_RELEASE,
            PermissionId.CONTRIBUTION_READ_PROJECT,
            PermissionId.COMPENSATION_AWARD_READ,
            PermissionId.OPERATIONS_STATUS_READ,
            PermissionId.OPERATIONS_TIMER_RUN,
            PermissionId.OPERATIONS_RECONCILE_RUN,
            PermissionId.OPERATIONS_OUTBOX_RETRY,
            PermissionId.OPERATIONS_PROJECTION_REBUILD,
            PermissionId.OPERATIONS_TASK_START_OVERRIDE,
            PermissionId.OPERATIONS_SUBMISSION_GATE_REPAIR,
            PermissionId.OPERATIONS_CHECKER_RETRY,
            PermissionId.ARTIFACT_BINDING_READ,
            PermissionId.ARTIFACT_REPLICA_READ,
            PermissionId.ARTIFACT_RECEIPT_READ,
            PermissionId.ARTIFACT_VERIFICATION_JOB_READ,
            PermissionId.ARTIFACT_VERIFICATION_JOB_RETRY,
            PermissionId.ARTIFACT_RECOVERY_ATTEMPT_READ,
            PermissionId.ARTIFACT_AUDIT_READ,
            PermissionId.AUDIT_READ,
        ),
        AdminRole.PROJECT_MANAGER: (
            PermissionId.PROJECT_CREATE,
            PermissionId.PROJECT_READ,
            PermissionId.PROJECT_UPDATE,
            PermissionId.PROJECT_ARCHIVE,
            PermissionId.PROJECT_GUIDE_MANAGE,
            PermissionId.PROJECT_EFFECTIVE_POLICY_MANAGE,
            PermissionId.PROJECT_TASK_MANAGE,
            PermissionId.PROJECT_REVIEW_POLICY_MANAGE,
            PermissionId.PROJECT_ROLE_GRANT_READ,
            PermissionId.PROJECT_ROLE_GRANT_MANAGE,
            PermissionId.REVIEW_QUEUE_INSPECT,
            PermissionId.CONTRIBUTION_READ_PROJECT,
            PermissionId.COMPENSATION_AWARD_READ,
            PermissionId.AUDIT_READ,
        ),
        AdminRole.FINANCE_AUTHORITY: (
            PermissionId.PROJECT_READ,
            PermissionId.CONTRIBUTION_READ_PROJECT,
            PermissionId.COMPENSATION_POLICY_MANAGE,
            PermissionId.COMPENSATION_ADAPTER_BINDING_MANAGE,
            PermissionId.COMPENSATION_AWARD_READ,
            PermissionId.COMPENSATION_DELIVERY_RECONCILE,
            PermissionId.AUDIT_READ,
        ),
        AdminRole.AUDIT_AUTHORITY: (
            PermissionId.ACTOR_PROFILE_READ_ANY,
            PermissionId.ACTOR_IDENTITY_LINK_READ,
            PermissionId.ADMIN_ROLE_READ,
            PermissionId.PROJECT_READ,
            PermissionId.PROJECT_ROLE_GRANT_READ,
            PermissionId.REVIEW_QUEUE_INSPECT,
            PermissionId.REVIEW_CHAIN_READ,
            PermissionId.CONTRIBUTION_READ_PROJECT,
            PermissionId.COMPENSATION_AWARD_READ,
            PermissionId.AUDIT_READ,
            PermissionId.AUDIT_EXPORT,
        ),
    }
)

ADMIN_ROLE_SCOPES = MappingProxyType(
    {
        AdminRole.ACCESS_ADMINISTRATOR: (AdminScope.SYSTEM,),
        AdminRole.OPERATOR: (AdminScope.SYSTEM,),
        AdminRole.PROJECT_MANAGER: (AdminScope.SYSTEM, AdminScope.PROJECT),
        AdminRole.FINANCE_AUTHORITY: (AdminScope.SYSTEM, AdminScope.PROJECT),
        AdminRole.AUDIT_AUTHORITY: (AdminScope.SYSTEM, AdminScope.PROJECT),
    }
)


def permissions_for(role: AdminRole) -> tuple[PermissionId, ...]:
    """Return the exact immutable permission candidates for one role."""
    return ADMIN_ROLE_PERMISSIONS[role]


def scopes_for(role: AdminRole) -> tuple[AdminScope, ...]:
    """Return the exact compatible scope tokens for one role."""
    return ADMIN_ROLE_SCOPES[role]
