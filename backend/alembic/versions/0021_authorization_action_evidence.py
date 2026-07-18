"""add closed permission and action audit parity

Revision ID: 0021_auth_action_evidence
Revises: 0020_canonical_actor_profile
Create Date: 2026-07-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0021_auth_action_evidence"
down_revision = "0020_canonical_actor_profile"
branch_labels = None
depends_on = None

HISTORICAL_PERMISSIONS = """actor.profile.read_self actor.profile.update_self actor.profile.read_any
actor.profile.suspend actor.profile.reactivate actor.profile.deactivate actor.identity_link.read
actor.identity_link.revoke actor.identity_link.reactivate actor.service.provision admin_role.read
admin_role.grant admin_role.revoke project.create project.read project.update project.archive
project.guide.manage project.effective_policy.manage project.task.manage project.review_policy.manage
project.role_grant.read project.role_grant.manage task.queue.read task.claim submission.create
submission.read_own submission.read_for_review review.queue.read review.queue.inspect review.claim
review.release review.decline_preference review.decision review.lease.force_release review.chain.read
contribution.read_self contribution.read_project compensation.policy.manage
compensation.adapter_binding.manage compensation.award.read compensation.delivery.reconcile
operations.status.read operations.timer.run operations.reconcile.run operations.outbox.retry
operations.projection.rebuild audit.read audit.export""".split()

NEW_PERMISSIONS = """operations.task.start_override operations.submission_gate.repair
operations.checker.retry artifact.binding.read artifact.replica.read artifact.receipt.read
artifact.verification_job.read artifact.verification_job.retry artifact.recovery_attempt.read
artifact.audit.read artifact.guide_source.ingest artifact.upload_session.create
artifact.upload_session.read artifact.upload_item.write artifact.upload_session.seal
artifact.upload_session.cancel artifact.upload_session.expire artifact.binding.create
artifact.verification.execute artifact.pending_work.scan artifact.put_attempt.resolve
artifact.guide_source.read artifact.checker_input.materialize artifact.checker_output.write
review.queue.override""".split()

PERMISSIONS = HISTORICAL_PERMISSIONS + NEW_PERMISSIONS

ACTION_PERMISSION_PAIRS = (
    ("actor.profile.read_self", "actor.profile.read_self"),
    ("actor.profile.update_self", "actor.profile.update_self"),
    ("operations.task.start_override", "operations.task.start_override"),
    ("operations.submission_gate.repair", "operations.submission_gate.repair"),
    ("operations.checker.retry", "operations.checker.retry"),
    ("submission.create", "submission.create"),
    ("review.queue.read", "review.queue.read"),
    ("review.queue.inspect", "review.queue.inspect"),
    ("review.claim", "review.claim"),
    ("review.release", "review.release"),
    ("review.decline_preference", "review.decline_preference"),
    ("review.preference_expiry.run", "operations.timer.run"),
    ("review.lease_expiry.run", "operations.timer.run"),
    ("review.context.read", "submission.read_for_review"),
    ("review.chain.read", "review.chain.read"),
    ("review.finding_evidence.ingest", "review.decision"),
    ("review.decision", "review.decision"),
    ("review.finding_response_evidence.ingest", "submission.create"),
    ("review.lease.force_release", "review.lease.force_release"),
    ("review.queue.routing.override", "review.queue.override"),
    ("review.queue.routing.correct", "review.queue.override"),
    ("review.queue.close", "review.queue.override"),
    ("review.reconcile.run", "operations.reconcile.run"),
    ("review.artifact_reference.reconcile", "operations.reconcile.run"),
    ("review.projection.rebuild", "operations.projection.rebuild"),
    ("artifact.binding.read", "artifact.binding.read"),
    ("artifact.replica.read", "artifact.replica.read"),
    ("artifact.receipt.read", "artifact.receipt.read"),
    ("artifact.verification_job.read", "artifact.verification_job.read"),
    ("artifact.verification_job.retry", "artifact.verification_job.retry"),
    ("artifact.recovery_attempt.read", "artifact.recovery_attempt.read"),
    ("artifact.audit.read", "artifact.audit.read"),
    ("operations.artifact_storage_admission.read", "operations.status.read"),
    ("artifact.guide_source.ingest", "artifact.guide_source.ingest"),
    ("artifact.guide_source.read", "artifact.guide_source.read"),
    ("artifact.upload_session.create", "artifact.upload_session.create"),
    ("artifact.upload_session.read", "artifact.upload_session.read"),
    ("artifact.upload_item.write", "artifact.upload_item.write"),
    ("artifact.upload_session.seal", "artifact.upload_session.seal"),
    ("artifact.upload_session.cancel", "artifact.upload_session.cancel"),
    ("artifact.upload_session.expire", "artifact.upload_session.expire"),
    ("artifact.guide_source.binding.create", "artifact.binding.create"),
    ("artifact.submission.binding.create", "artifact.binding.create"),
    ("artifact.checker_output.binding.create", "artifact.binding.create"),
    ("artifact.verification.execute", "artifact.verification.execute"),
    ("artifact.pending_work.scan", "artifact.pending_work.scan"),
    ("artifact.put_attempt.resolve", "artifact.put_attempt.resolve"),
    (
        "artifact.pre_submit.checker_input.materialize",
        "artifact.checker_input.materialize",
    ),
    (
        "artifact.post_submit.checker_input.materialize",
        "artifact.checker_input.materialize",
    ),
    ("artifact.checker_output.write", "artifact.checker_output.write"),
)

DENIAL_CODES = """required_scope_missing unsupported_subject_kind service_actor_not_provisioned
identity_link_revoked actor_suspended actor_deactivated permission_not_granted scope_not_authorized
self_grant_forbidden self_role_revoke_forbidden resource_guard_denied actor_not_found grant_not_found
resource_not_found actor_already_suspended actor_not_suspended actor_deactivated_terminal
last_access_administrator admin_role_grant_exists project_role_grant_exists identity_link_conflict
resource_project_mismatch idempotency_mismatch invalid_role_scope invalid_project_role
qualification_snapshot_invalid""".split()

REASONS = {
    "ActorProfileProvisioned": ("automatic_first_access",),
    "ServiceActorProvisioned": ("manual_service_provisioning",),
    "ActorIdentityLinked": ("identity_lifecycle_change",),
    "ActorIdentityLinkRevoked": ("identity_lifecycle_change",),
    "ActorIdentityLinkReactivated": ("identity_lifecycle_change",),
    "ActorProfileSuspended": ("security_response", "administrative_correction"),
    "ActorProfileReactivated": ("administrative_correction",),
    "ActorProfileDeactivated": ("security_response", "administrative_correction"),
    "InitialAccessAdministratorBootstrapped": ("initial_access_bootstrap",),
    "AdminRoleGrantIssued": ("authority_assignment",),
    "AdminRoleGrantRevoked": ("authority_revocation",),
    "AdminRoleGrantIssueDenied": ("authorization_policy_denial",),
    "LastAccessAdministratorOperationDenied": ("authorization_policy_denial",),
    "ProjectRoleQualificationSnapshotCaptured": ("qualification_evidence_captured",),
    "ProjectRoleGrantIssued": ("authority_assignment",),
    "ProjectRoleGrantReplaced": ("authority_replacement",),
    "ProjectRoleGrantRevoked": ("authority_revocation",),
    "SensitiveAuthorizationAllowed": ("authorization_evaluation",),
    "SensitiveAuthorizationDenied": ("authorization_evaluation",),
    "AuthorityInvalidationRequested": ("authority_state_changed",),
}


def _tokens(values: list[str] | tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _pair_tokens() -> str:
    return ", ".join(
        f"('{action}', '{permission}')" for action, permission in ACTION_PERMISSION_PAIRS
    )


def _create_registry_constraint(permissions: list[str]) -> None:
    reason_rules = " or ".join(
        f"(event_type = '{event}' and reason in ({_tokens(reasons)}))"
        for event, reasons in REASONS.items()
    )
    op.create_check_constraint(
        "authority_registries",
        "audit_events",
        f"""
        event_domain <> 'authority' or (
          reason is not null and ({reason_rules})
          and (permission_id is null or permission_id in ({_tokens(permissions)}))
          and (denial_code is null or denial_code in ({_tokens(DENIAL_CODES)}))
        )
        """,
    )


def _create_privacy_constraint(permissions: list[str]) -> None:
    entity_tokens = _tokens(
        (
            "actor_profile",
            "actor_identity_link",
            "admin_role_grant",
            "qualification_snapshot",
            "project_role_grant",
            "authorization_decision",
            "authority_invalidation",
        )
    )
    resource_tokens = _tokens(
        """actor_profile actor_identity_link admin_role_grant project project_role_grant task
        submission review contribution compensation_award compensation_delivery operations
        audit_event""".split()
    )
    uuid_target_tokens = _tokens(
        (
            "actor_profile",
            "actor_identity_link",
            "admin_role_grant",
            "qualification_snapshot",
            "project_role_grant",
        )
    )
    uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    permission_tokens = _tokens(permissions)
    op.create_check_constraint(
        "authority_privacy_bounds",
        "audit_events",
        f"""
        event_domain <> 'authority' or (
          id ~ '{uuid_pattern}' and entity_type in ({entity_tokens}) and entity_id ~ '{uuid_pattern}'
          and (
            (actor_ref_kind in ('legacy_actor', 'actor_profile') and actor_id ~ '{uuid_pattern}')
            or (actor_ref_kind = 'system_principal' and actor_id = 'workstream:system:bootstrap')
          )
          and (
            target_actor_ref is null
            or (target_actor_ref_kind = 'actor_profile' and target_actor_ref ~ '{uuid_pattern}')
          )
          and (matched_grant_id is null or matched_grant_id ~ '{uuid_pattern}')
          and (project_id is null or project_id ~ '{uuid_pattern}')
          and (resource_type is null or resource_type in ({resource_tokens}))
          and (resource_id is null or resource_id ~ '{uuid_pattern}')
          and (
            target_ref_kind is null
            or (target_ref_kind in ({uuid_target_tokens}) and target_ref_id ~ '{uuid_pattern}')
            or (target_ref_kind = 'permission_registry' and target_ref_id in ({permission_tokens}))
          )
          and (
            invalidation_target_kind is null
            or (
              invalidation_target_kind in ({uuid_target_tokens})
              and invalidation_target_ref ~ '{uuid_pattern}'
            )
            or (
              invalidation_target_kind = 'permission_registry'
              and invalidation_target_ref in ({permission_tokens})
            )
          )
          and (
            entity_type not in ('authorization_decision', 'authority_invalidation')
            or entity_id = id
          )
          and (
            resource_type <> 'project' or resource_id is null
            or (project_id is not null and resource_id = project_id)
          )
        )
        """,
    )


def upgrade() -> None:
    """Install action-aware audit constraints without activating any action."""
    op.add_column("audit_events", sa.Column("action_id", sa.String(160), nullable=True))
    op.drop_constraint("authority_registries", "audit_events", type_="check")
    op.drop_constraint("authority_privacy_bounds", "audit_events", type_="check")
    _create_registry_constraint(PERMISSIONS)
    _create_privacy_constraint(PERMISSIONS)

    # Availability is typed lifecycle state; SQL remains stable across owner activation.
    pair_tokens = _pair_tokens()
    op.create_check_constraint(
        "authorization_action_evidence",
        "audit_events",
        f"""
        (
          event_domain = 'legacy_lifecycle' and action_id is null
        ) or (
          event_domain = 'authority'
          and (
            action_id is null or (
              event_type in ('SensitiveAuthorizationAllowed', 'SensitiveAuthorizationDenied')
              and permission_id is not null
              and (action_id, permission_id) in ({pair_tokens})
            )
          )
          and (
            permission_id is null
            or permission_id not in ({_tokens(NEW_PERMISSIONS)})
            or (
              action_id is not null
              and (action_id, permission_id) in ({pair_tokens})
            )
          )
        )
        """,
    )


def downgrade() -> None:
    """Remove action parity only when no forward evidence would be discarded."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table audit_events in access exclusive mode"))
    has_forward_evidence = bind.execute(
        sa.text(
            "select exists(select 1 from audit_events where action_id is not null "
            f"or permission_id in ({_tokens(NEW_PERMISSIONS)}) "
            "or (target_ref_kind = 'permission_registry' "
            f"and target_ref_id in ({_tokens(NEW_PERMISSIONS)})) "
            "or (invalidation_target_kind = 'permission_registry' "
            f"and invalidation_target_ref in ({_tokens(NEW_PERMISSIONS)})))"
        )
    ).scalar_one()
    if has_forward_evidence:
        raise RuntimeError("cannot downgrade non-empty authorization action evidence")

    op.drop_constraint("authorization_action_evidence", "audit_events", type_="check")
    op.drop_constraint("authority_registries", "audit_events", type_="check")
    op.drop_constraint("authority_privacy_bounds", "audit_events", type_="check")
    _create_registry_constraint(HISTORICAL_PERMISSIONS)
    _create_privacy_constraint(HISTORICAL_PERMISSIONS)
    op.drop_column("audit_events", "action_id")
