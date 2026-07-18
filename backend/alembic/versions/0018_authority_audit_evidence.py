"""add append-only authority audit evidence

Revision ID: 0018_authority_audit_evidence
Revises: 0017_api_controls
Create Date: 2026-07-14
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_authority_audit_evidence"
down_revision = "0017_api_controls"
branch_labels = depends_on = None

AUTHORITY_EVENT_TYPES = (
    "ActorProfileProvisioned",
    "ServiceActorProvisioned",
    "ActorIdentityLinked",
    "ActorIdentityLinkRevoked",
    "ActorIdentityLinkReactivated",
    "ActorProfileSuspended",
    "ActorProfileReactivated",
    "ActorProfileDeactivated",
    "InitialAccessAdministratorBootstrapped",
    "AdminRoleGrantIssued",
    "AdminRoleGrantRevoked",
    "AdminRoleGrantIssueDenied",
    "LastAccessAdministratorOperationDenied",
    "ProjectRoleQualificationSnapshotCaptured",
    "ProjectRoleGrantIssued",
    "ProjectRoleGrantReplaced",
    "ProjectRoleGrantRevoked",
    "SensitiveAuthorizationAllowed",
    "SensitiveAuthorizationDenied",
    "AuthorityInvalidationRequested",
)
PERMISSIONS = """actor.profile.read_self actor.profile.update_self actor.profile.read_any
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


def _sql_tokens(values) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    """Extend the shared audit table and install normal-DML custody guards."""
    columns = (
        sa.Column(
            "event_domain",
            sa.String(24),
            nullable=False,
            server_default="legacy_lifecycle",
        ),
        sa.Column("event_version", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor_ref_kind", sa.String(32), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=True),
        sa.Column("target_actor_ref_kind", sa.String(32), nullable=True),
        sa.Column("target_actor_ref", sa.String(100), nullable=True),
        sa.Column("matched_grant_id", sa.String(100), nullable=True),
        sa.Column("permission_id", sa.String(120), nullable=True),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("resource_type", sa.String(80), nullable=True),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("target_ref_kind", sa.String(32), nullable=True),
        sa.Column("target_ref_id", sa.String(100), nullable=True),
        sa.Column("denial_code", sa.String(80), nullable=True),
        sa.Column("idempotency_reference", sa.Uuid(), nullable=True),
        sa.Column("invalidation_cause_event_id", sa.String(36), nullable=True),
        sa.Column("invalidation_target_kind", sa.String(32), nullable=True),
        sa.Column("invalidation_target_ref", sa.String(100), nullable=True),
        sa.Column("before_facts", sa.JSON(), nullable=True),
        sa.Column("after_facts", sa.JSON(), nullable=True),
    )
    for column in columns:
        op.add_column("audit_events", column)
    op.alter_column("audit_events", "external_subject", existing_type=sa.String(200), nullable=True)
    op.alter_column("audit_events", "external_issuer", existing_type=sa.String(200), nullable=True)
    op.execute(
        """
        create function authority_facts_are_safe(facts json)
        returns boolean language sql immutable strict as $$
          select json_typeof(facts) = 'object'
            and (select count(*) = count(distinct key) and count(*) <= 8 from json_each(facts))
            and not exists (
              select 1 from json_each(facts) item
              where item.key not in (
                'status', 'subject_kind', 'provisioning_method', 'role',
                'scope_type', 'scope_id', 'effective', 'allowed'
              )
              or case item.key
                when 'status' then item.value #>> '{}' not in (
                  'active', 'suspended', 'deactivated', 'revoked', 'captured'
                )
                when 'subject_kind' then item.value #>> '{}' not in ('human', 'service')
                when 'provisioning_method' then item.value #>> '{}' not in (
                  'automatic_first_access', 'manual_service_provisioning'
                )
                when 'role' then item.value #>> '{}' not in (
                  'access_administrator', 'operator', 'project_manager',
                  'finance_authority', 'audit_authority', 'submitter', 'reviewer', 'both'
                )
                when 'scope_type' then item.value #>> '{}' not in ('system', 'project')
                when 'scope_id' then (item.value #>> '{}') !~
                  '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                when 'effective' then json_typeof(item.value) <> 'boolean'
                when 'allowed' then json_typeof(item.value) <> 'boolean'
                else true
              end
            )
        $$
        """
    )
    op.execute(
        """
        create function authority_grant_facts_are_safe(
          facts json, roles text[], expected_status text,
          expected_effective boolean, envelope_project_id text
        ) returns boolean language sql immutable as $$
          select authority_facts_are_safe(facts)
            and facts->>'role' = any(roles)
            and facts->>'status' = expected_status
            and (facts->>'effective')::boolean = expected_effective
            and (
              (
                facts->>'scope_type' = 'system'
                and envelope_project_id is null
                and not facts::jsonb ? 'scope_id'
                and facts->>'role' not in ('submitter', 'reviewer', 'both')
                and (select count(*) from json_each(facts)) = 4
              ) or (
                facts->>'scope_type' = 'project'
                and envelope_project_id is not null
                and facts->>'scope_id' = envelope_project_id
                and facts->>'role' not in ('access_administrator', 'operator')
                and (select count(*) from json_each(facts)) = 5
              )
            )
        $$
        """
    )
    op.execute(
        """
        create function authority_event_facts_are_safe(
          event_name text, before_state json, after_state json, envelope_project_id text
        ) returns boolean language plpgsql immutable as $$
        begin
          if (before_state is not null and not authority_facts_are_safe(before_state))
             or (after_state is not null and not authority_facts_are_safe(after_state)) then
            return false;
          end if;
          case event_name
            when 'ActorProfileProvisioned' then
              return before_state is null and after_state::jsonb =
                '{"status":"active","subject_kind":"human",'
                '"provisioning_method":"automatic_first_access"}'::jsonb;
            when 'ServiceActorProvisioned' then
              return before_state is null and after_state::jsonb =
                '{"status":"active","subject_kind":"service",'
                '"provisioning_method":"manual_service_provisioning"}'::jsonb;
            when 'ActorIdentityLinked' then
              return before_state is null and after_state::jsonb in (
                '{"status":"active","subject_kind":"human"}'::jsonb,
                '{"status":"active","subject_kind":"service"}'::jsonb
              );
            when 'ActorIdentityLinkRevoked' then
              return before_state::jsonb = '{"status":"active"}'::jsonb
                and after_state::jsonb = '{"status":"revoked"}'::jsonb;
            when 'ActorIdentityLinkReactivated' then
              return before_state::jsonb = '{"status":"revoked"}'::jsonb
                and after_state::jsonb = '{"status":"active"}'::jsonb;
            when 'ActorProfileSuspended' then
              return before_state::jsonb = '{"status":"active"}'::jsonb
                and after_state::jsonb = '{"status":"suspended"}'::jsonb;
            when 'ActorProfileReactivated' then
              return before_state::jsonb = '{"status":"suspended"}'::jsonb
                and after_state::jsonb = '{"status":"active"}'::jsonb;
            when 'ActorProfileDeactivated' then
              return before_state::jsonb in (
                '{"status":"active"}'::jsonb, '{"status":"suspended"}'::jsonb
              ) and after_state::jsonb = '{"status":"deactivated"}'::jsonb;
            when 'InitialAccessAdministratorBootstrapped' then
              return before_state is null and authority_grant_facts_are_safe(
                after_state, array['access_administrator'], 'active', true, null
              );
            when 'AdminRoleGrantIssued' then
              return before_state is null and authority_grant_facts_are_safe(
                after_state,
                array[
                  'access_administrator', 'operator', 'project_manager',
                  'finance_authority', 'audit_authority'
                ], 'active', true, envelope_project_id
              );
            when 'ProjectRoleGrantIssued' then
              return before_state is null and authority_grant_facts_are_safe(
                after_state, array['submitter', 'reviewer', 'both'],
                'active', true, envelope_project_id
              );
            when 'AdminRoleGrantRevoked', 'ProjectRoleGrantRevoked' then
              return authority_grant_facts_are_safe(
                before_state,
                case when event_name = 'AdminRoleGrantRevoked' then
                  array[
                    'access_administrator', 'operator', 'project_manager',
                    'finance_authority', 'audit_authority'
                  ]
                else array['submitter', 'reviewer', 'both'] end,
                'active', true, envelope_project_id
              ) and authority_grant_facts_are_safe(
                after_state,
                case when event_name = 'AdminRoleGrantRevoked' then
                  array[
                    'access_administrator', 'operator', 'project_manager',
                    'finance_authority', 'audit_authority'
                  ]
                else array['submitter', 'reviewer', 'both'] end,
                'revoked', false, envelope_project_id
              ) and before_state->>'role' = after_state->>'role'
                and before_state->>'scope_type' = after_state->>'scope_type'
                and coalesce(before_state->>'scope_id', '') =
                  coalesce(after_state->>'scope_id', '');
            when 'ProjectRoleGrantReplaced' then
              return authority_grant_facts_are_safe(
                before_state, array['submitter', 'reviewer', 'both'],
                'active', true, envelope_project_id
              ) and authority_grant_facts_are_safe(
                after_state, array['submitter', 'reviewer', 'both'],
                'active', true, envelope_project_id
              ) and before_state->>'scope_id' = after_state->>'scope_id';
            when 'ProjectRoleQualificationSnapshotCaptured' then
              return before_state is null
                and after_state::jsonb = '{"status":"captured"}'::jsonb;
            when 'AdminRoleGrantIssueDenied', 'LastAccessAdministratorOperationDenied' then
              return before_state is null and after_state is null;
            when 'SensitiveAuthorizationAllowed' then
              return before_state is null and after_state::jsonb = '{"allowed": true}'::jsonb;
            when 'SensitiveAuthorizationDenied' then
              return before_state is null and after_state::jsonb = '{"allowed": false}'::jsonb;
            when 'AuthorityInvalidationRequested' then
              return before_state::jsonb = '{"effective": true}'::jsonb
                and after_state::jsonb = '{"effective": false}'::jsonb;
            else return false;
          end case;
        end
        $$
        """
    )

    event_tokens = _sql_tokens(AUTHORITY_EVENT_TYPES)
    permission_tokens = _sql_tokens(PERMISSIONS)
    denial_tokens = _sql_tokens(DENIAL_CODES)
    reason_rules = " or ".join(
        f"(event_type = '{event}' and reason in ({_sql_tokens(reasons)}))"
        for event, reasons in REASONS.items()
    )
    entity_tokens = _sql_tokens(
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
    resource_tokens = _sql_tokens(
        """actor_profile actor_identity_link admin_role_grant project project_role_grant task
        submission review contribution compensation_award compensation_delivery operations
        audit_event""".split()
    )
    uuid_target_tokens = _sql_tokens(
        (
            "actor_profile",
            "actor_identity_link",
            "admin_role_grant",
            "qualification_snapshot",
            "project_role_grant",
        )
    )
    uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    op.create_check_constraint(
        "domain_shape",
        "audit_events",
        """
        (
          event_domain = 'legacy_lifecycle'
          and event_version is null and occurred_at is null and actor_ref_kind is null
          and request_id is null and correlation_id is null and target_actor_ref_kind is null
          and target_actor_ref is null and matched_grant_id is null and permission_id is null
          and project_id is null and resource_type is null and resource_id is null
          and target_ref_kind is null and target_ref_id is null and denial_code is null
          and idempotency_reference is null and invalidation_cause_event_id is null
          and invalidation_target_kind is null and invalidation_target_ref is null
          and before_facts is null and after_facts is null
          and external_subject is not null and external_issuer is not null
        ) or (
          event_domain = 'authority' and event_version = 1 and occurred_at is not null
          and actor_ref_kind in ('legacy_actor', 'actor_profile', 'system_principal')
          and request_id is not null and correlation_id is not null
          and from_status is null and to_status is null and reason is not null
          and external_subject is null and external_issuer is null
          and actor_roles::jsonb = '[]'::jsonb and claim_snapshot::jsonb = '{}'::jsonb
          and auth_source = 'local_authority' and is_dev_auth = false
          and event_payload::jsonb = '{}'::jsonb
        )
        """,
    )
    op.create_check_constraint(
        "authority_tokens",
        "audit_events",
        f"event_domain <> 'authority' or event_type in ({event_tokens})",
    )
    op.create_check_constraint(
        "authority_registries",
        "audit_events",
        f"""
        event_domain <> 'authority' or (
          reason is not null and ({reason_rules})
          and (permission_id is null or permission_id in ({permission_tokens}))
          and (denial_code is null or denial_code in ({denial_tokens}))
        )
        """,
    )
    op.create_check_constraint(
        "reference_pairs",
        "audit_events",
        """
        (target_actor_ref_kind is null) = (target_actor_ref is null)
        and (resource_type is not null or resource_id is null)
        and (target_ref_kind is null) = (target_ref_id is null)
        and (invalidation_target_kind is null) = (invalidation_target_ref is null)
        and (invalidation_cause_event_id is null or invalidation_cause_event_id <> id)
        """,
    )
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
    op.create_check_constraint(
        "fact_bounds",
        "audit_events",
        """
        event_domain <> 'authority' or (
          (before_facts is null or octet_length(before_facts::text) <= 4096)
          and (after_facts is null or octet_length(after_facts::text) <= 4096)
          and coalesce(
            authority_event_facts_are_safe(event_type, before_facts, after_facts, project_id),
            false
          )
        )
        """,
    )
    op.create_foreign_key(
        "fk_audit_events_invalidation_cause",
        "audit_events",
        "audit_events",
        ["invalidation_cause_event_id"],
        ["id"],
    )
    op.create_check_constraint(
        "foundation_shapes",
        "audit_events",
        """
        event_domain <> 'authority'
        or event_type not in (
          'SensitiveAuthorizationAllowed', 'SensitiveAuthorizationDenied',
          'AuthorityInvalidationRequested', 'AdminRoleGrantIssueDenied',
          'LastAccessAdministratorOperationDenied'
        )
        or (
          event_type in ('AdminRoleGrantIssueDenied', 'LastAccessAdministratorOperationDenied')
          and denial_code is not null
        )
        or (
          event_type = 'SensitiveAuthorizationAllowed' and permission_id is not null
          and denial_code is null and invalidation_cause_event_id is null
          and invalidation_target_kind is null
        )
        or (
          event_type = 'SensitiveAuthorizationDenied' and permission_id is not null
          and denial_code is not null and invalidation_cause_event_id is null
          and invalidation_target_kind is null and idempotency_reference is null
        )
        or (
          event_type = 'AuthorityInvalidationRequested'
          and invalidation_cause_event_id is not null
          and invalidation_target_kind is not null and denial_code is null
        )
        """,
    )
    for name, fields in (
        ("ix_audit_events_request_id", ["request_id"]),
        ("ix_audit_events_correlation_id", ["correlation_id"]),
        ("ix_audit_events_occurred_at", ["occurred_at"]),
        ("ix_audit_events_project_id", ["project_id"]),
        ("ix_audit_events_actor_ref", ["actor_ref_kind", "actor_id"]),
    ):
        op.create_index(name, "audit_events", fields)

    op.execute(
        """
        create function set_authority_audit_database_time()
        returns trigger language plpgsql as $$
        begin
          if new.event_domain = 'authority' then
            if new.invalidation_cause_event_id is not null and not exists (
              select 1 from audit_events
              where id = new.invalidation_cause_event_id and event_domain = 'authority'
            ) then
              raise exception 'invalid authority invalidation cause' using errcode = '23503';
            end if;
            new.occurred_at = statement_timestamp();
          else
            new.occurred_at = null;
          end if;
          return new;
        end
        $$
        """
    )
    op.execute(
        """
        create trigger audit_events_set_authority_time
        before insert on audit_events for each row
        execute function set_authority_audit_database_time()
        """
    )
    op.execute(
        """
        create function reject_audit_event_mutation()
        returns trigger language plpgsql as $$
        begin
          raise exception 'audit events are append-only' using errcode = '55000';
        end
        $$
        """
    )
    op.execute(
        """
        create trigger audit_events_reject_update_delete
        before update or delete on audit_events for each row
        execute function reject_audit_event_mutation()
        """
    )
    op.execute(
        """
        create trigger audit_events_reject_truncate
        before truncate on audit_events for each statement
        execute function reject_audit_event_mutation()
        """
    )


def downgrade() -> None:
    """Remove only unused authority-envelope schema while preserving legacy rows."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table audit_events in access exclusive mode"))
    has_authority = bind.execute(
        sa.text("select exists(select 1 from audit_events where event_domain = 'authority')")
    ).scalar_one()
    if has_authority:
        raise RuntimeError("cannot downgrade non-empty authority audit evidence")

    for trigger in (
        "audit_events_reject_truncate",
        "audit_events_reject_update_delete",
        "audit_events_set_authority_time",
    ):
        op.execute(f"drop trigger {trigger} on audit_events")
    op.execute("drop function reject_audit_event_mutation()")
    op.execute("drop function set_authority_audit_database_time()")
    for name in (
        "ix_audit_events_actor_ref",
        "ix_audit_events_project_id",
        "ix_audit_events_occurred_at",
        "ix_audit_events_correlation_id",
        "ix_audit_events_request_id",
    ):
        op.drop_index(name, table_name="audit_events")
    op.drop_constraint("fk_audit_events_invalidation_cause", "audit_events", type_="foreignkey")
    for name in (
        "foundation_shapes",
        "fact_bounds",
        "authority_privacy_bounds",
        "reference_pairs",
        "authority_registries",
        "authority_tokens",
        "domain_shape",
    ):
        op.drop_constraint(name, "audit_events", type_="check")
    op.execute("drop function authority_event_facts_are_safe(text, json, json, text)")
    op.execute("drop function authority_grant_facts_are_safe(json, text[], text, boolean, text)")
    op.execute("drop function authority_facts_are_safe(json)")
    for column in reversed(
        (
            "event_version",
            "occurred_at",
            "actor_ref_kind",
            "request_id",
            "correlation_id",
            "target_actor_ref_kind",
            "target_actor_ref",
            "matched_grant_id",
            "permission_id",
            "project_id",
            "resource_type",
            "resource_id",
            "target_ref_kind",
            "target_ref_id",
            "denial_code",
            "idempotency_reference",
            "invalidation_cause_event_id",
            "invalidation_target_kind",
            "invalidation_target_ref",
            "before_facts",
            "after_facts",
            "event_domain",
        )
    ):
        op.drop_column("audit_events", column)
    op.alter_column("audit_events", "external_issuer", existing_type=sa.String(200), nullable=False)
    op.alter_column("audit_events", "external_subject", existing_type=sa.String(200), nullable=False)
