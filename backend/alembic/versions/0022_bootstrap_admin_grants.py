"""add one-time bootstrap and immutable administrative grants

Revision ID: 0022_bootstrap_admin_grants
Revises: 0021_auth_action_evidence
Create Date: 2026-07-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0022_bootstrap_admin_grants"
down_revision = "0021_auth_action_evidence"
branch_labels = depends_on = None

AUTH_08_ACTIONS = (
    "authorization.permission_catalogue.read",
    "authorization.admin_role_definitions.read",
    "admin_role_grant.list",
    "actor.admin_role_grant_history.read",
    "admin_role_grant.issue",
    "admin_role_grant.revoke",
    "admin_role_grant.bootstrap",
)

AUTH_08_EVIDENCE_EVENTS = (
    "InitialAccessAdministratorBootstrapped",
    "AdminRoleGrantIssued",
    "AdminRoleGrantRevoked",
    "AdminRoleGrantIssueDenied",
    "LastAccessAdministratorOperationDenied",
)

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
    ("artifact.pre_submit.checker_input.materialize", "artifact.checker_input.materialize"),
    ("artifact.post_submit.checker_input.materialize", "artifact.checker_input.materialize"),
    ("artifact.checker_output.write", "artifact.checker_output.write"),
    ("authorization.permission_catalogue.read", "admin_role.read"),
    ("authorization.admin_role_definitions.read", "admin_role.read"),
    ("admin_role_grant.list", "admin_role.read"),
    ("actor.admin_role_grant_history.read", "admin_role.read"),
    ("admin_role_grant.issue", "admin_role.grant"),
    ("admin_role_grant.revoke", "admin_role.revoke"),
    ("admin_role_grant.bootstrap", "admin_role.grant"),
)


def _tokens(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _pair_tokens(pairs: tuple[tuple[str, str], ...]) -> str:
    return ", ".join(f"('{action}', '{permission}')" for action, permission in pairs)


def _create_action_constraint(pairs: tuple[tuple[str, str], ...]) -> None:
    new_permissions = tuple(
        "operations.task.start_override operations.submission_gate.repair operations.checker.retry "
        "artifact.binding.read artifact.replica.read artifact.receipt.read "
        "artifact.verification_job.read artifact.verification_job.retry "
        "artifact.recovery_attempt.read artifact.audit.read artifact.guide_source.ingest "
        "artifact.upload_session.create artifact.upload_session.read artifact.upload_item.write "
        "artifact.upload_session.seal artifact.upload_session.cancel artifact.upload_session.expire "
        "artifact.binding.create artifact.verification.execute artifact.pending_work.scan "
        "artifact.put_attempt.resolve artifact.guide_source.read "
        "artifact.checker_input.materialize artifact.checker_output.write review.queue.override".split()
    )
    pair_tokens = _pair_tokens(pairs)
    op.create_check_constraint(
        "authorization_action_evidence",
        "audit_events",
        f"""
        (event_domain = 'legacy_lifecycle' and action_id is null) or (
          event_domain = 'authority'
          and (
            action_id is null or (
              event_type in ('SensitiveAuthorizationAllowed', 'SensitiveAuthorizationDenied')
              and permission_id is not null
              and (action_id, permission_id) in ({pair_tokens})
            )
          )
          and (
            permission_id is null or permission_id not in ({_tokens(new_permissions)})
            or (action_id is not null and (action_id, permission_id) in ({pair_tokens}))
          )
        )
        """,
    )


def _replace_fact_function(*, admin_issue_direction: bool) -> None:
    invalidation = (
        "(before_state::jsonb = '{\"effective\": true}'::jsonb and "
        "after_state::jsonb = '{\"effective\": false}'::jsonb) or "
        "(before_state::jsonb = '{\"effective\": false}'::jsonb and "
        "after_state::jsonb = '{\"effective\": true}'::jsonb)"
        if admin_issue_direction
        else "before_state::jsonb = '{\"effective\": true}'::jsonb and "
        "after_state::jsonb = '{\"effective\": false}'::jsonb"
    )
    op.execute(
        f"""
        create or replace function authority_event_facts_are_safe(
          event_name text, before_state json, after_state json, envelope_project_id text
        ) returns boolean language plpgsql immutable as $$
        begin
          if (before_state is not null and not authority_facts_are_safe(before_state))
             or (after_state is not null and not authority_facts_are_safe(after_state)) then
            return false;
          end if;
          case event_name
            when 'ActorProfileProvisioned' then return before_state is null and after_state::jsonb =
              '{{"status":"active","subject_kind":"human","provisioning_method":"automatic_first_access"}}'::jsonb;
            when 'ServiceActorProvisioned' then return before_state is null and after_state::jsonb =
              '{{"status":"active","subject_kind":"service","provisioning_method":"manual_service_provisioning"}}'::jsonb;
            when 'ActorIdentityLinked' then return before_state is null and after_state::jsonb in (
              '{{"status":"active","subject_kind":"human"}}'::jsonb,
              '{{"status":"active","subject_kind":"service"}}'::jsonb);
            when 'ActorIdentityLinkRevoked' then return before_state::jsonb='{{"status":"active"}}'::jsonb and after_state::jsonb='{{"status":"revoked"}}'::jsonb;
            when 'ActorIdentityLinkReactivated' then return before_state::jsonb='{{"status":"revoked"}}'::jsonb and after_state::jsonb='{{"status":"active"}}'::jsonb;
            when 'ActorProfileSuspended' then return before_state::jsonb='{{"status":"active"}}'::jsonb and after_state::jsonb='{{"status":"suspended"}}'::jsonb;
            when 'ActorProfileReactivated' then return before_state::jsonb='{{"status":"suspended"}}'::jsonb and after_state::jsonb='{{"status":"active"}}'::jsonb;
            when 'ActorProfileDeactivated' then return before_state::jsonb in ('{{"status":"active"}}'::jsonb,'{{"status":"suspended"}}'::jsonb) and after_state::jsonb='{{"status":"deactivated"}}'::jsonb;
            when 'InitialAccessAdministratorBootstrapped' then return before_state is null and authority_grant_facts_are_safe(after_state,array['access_administrator'],'active',true,null);
            when 'AdminRoleGrantIssued' then return before_state is null and authority_grant_facts_are_safe(after_state,array['access_administrator','operator','project_manager','finance_authority','audit_authority'],'active',true,envelope_project_id);
            when 'ProjectRoleGrantIssued' then return before_state is null and authority_grant_facts_are_safe(after_state,array['submitter','reviewer','both'],'active',true,envelope_project_id);
            when 'AdminRoleGrantRevoked','ProjectRoleGrantRevoked' then
              return authority_grant_facts_are_safe(before_state,
                case when event_name='AdminRoleGrantRevoked' then array['access_administrator','operator','project_manager','finance_authority','audit_authority'] else array['submitter','reviewer','both'] end,
                'active',true,envelope_project_id)
                and authority_grant_facts_are_safe(after_state,
                case when event_name='AdminRoleGrantRevoked' then array['access_administrator','operator','project_manager','finance_authority','audit_authority'] else array['submitter','reviewer','both'] end,
                'revoked',false,envelope_project_id)
                and before_state->>'role'=after_state->>'role'
                and before_state->>'scope_type'=after_state->>'scope_type'
                and coalesce(before_state->>'scope_id','')=coalesce(after_state->>'scope_id','');
            when 'ProjectRoleGrantReplaced' then return
              authority_grant_facts_are_safe(before_state,array['submitter','reviewer','both'],'active',true,envelope_project_id)
              and authority_grant_facts_are_safe(after_state,array['submitter','reviewer','both'],'active',true,envelope_project_id)
              and before_state->>'scope_id'=after_state->>'scope_id';
            when 'ProjectRoleQualificationSnapshotCaptured' then return before_state is null and after_state::jsonb='{{"status":"captured"}}'::jsonb;
            when 'AdminRoleGrantIssueDenied','LastAccessAdministratorOperationDenied' then return before_state is null and after_state is null;
            when 'SensitiveAuthorizationAllowed' then return before_state is null and after_state::jsonb='{{"allowed": true}}'::jsonb;
            when 'SensitiveAuthorizationDenied' then return before_state is null and after_state::jsonb='{{"allowed": false}}'::jsonb;
            when 'AuthorityInvalidationRequested' then return {invalidation};
            else return false;
          end case;
        end $$
        """
    )


def _replace_linked_function(*, admin_projection: bool) -> None:
    admin_branch = "record_row.operation in ('admin_role_grant.issue','admin_role_grant.revoke')"
    direction_checks = """
               or (record_row.operation='admin_role_grant.issue' and
                   (new.before_facts::jsonb <> '{"effective": false}'::jsonb or new.after_facts::jsonb <> '{"effective": true}'::jsonb))
               or (record_row.operation='admin_role_grant.revoke' and
                   (new.before_facts::jsonb <> '{"effective": true}'::jsonb or new.after_facts::jsonb <> '{"effective": false}'::jsonb))
               or (not (record_row.operation in ('admin_role_grant.issue','admin_role_grant.revoke')) and
                   (new.before_facts::jsonb <> '{"effective": true}'::jsonb or new.after_facts::jsonb <> '{"effective": false}'::jsonb))
    """
    if not admin_projection:
        admin_branch = "false"
        direction_checks = """
               or (new.before_facts::jsonb <> '{"effective": true}'::jsonb
                   or new.after_facts::jsonb <> '{"effective": false}'::jsonb)
        """
    op.execute(
        f"""
        create or replace function validate_linked_authority_event() returns trigger
        language plpgsql as $$
        declare record_row authority_idempotency_records%rowtype;
                cause_row audit_events%rowtype; expected_permission text;
                expected_resource text; expected_invalidation_resource text;
                expected_invalidation_id text; valid_success boolean;
        begin
          if new.event_domain <> 'authority' then return new; end if;
          valid_success := new.event_type in (
            'ServiceActorProvisioned','AdminRoleGrantIssued','AdminRoleGrantRevoked',
            'ProjectRoleGrantIssued','ProjectRoleGrantReplaced','ProjectRoleGrantRevoked',
            'ActorProfileSuspended','ActorProfileReactivated','ActorProfileDeactivated',
            'ActorIdentityLinkRevoked','ActorIdentityLinkReactivated');
          if not valid_success and new.event_type <> 'AuthorityInvalidationRequested' then
            if new.idempotency_reference is not null then
              raise exception 'invalid authority idempotency event' using errcode='23514';
            end if; return new;
          end if;
          if new.idempotency_reference is null then
            raise exception 'authority event requires idempotency reference' using errcode='23514';
          end if;
          select * into record_row from authority_idempotency_records
          where id=new.idempotency_reference and actor_ref_kind=new.actor_ref_kind and actor_ref=new.actor_id;
          if not found then raise exception 'invalid authority idempotency reference' using errcode='23503'; end if;
          if record_row.status <> 'pending' then raise exception 'committed authority idempotency is closed' using errcode='23514'; end if;
          expected_permission := case record_row.operation
            when 'service_actor.create' then 'actor.service.provision'
            when 'admin_role_grant.issue' then 'admin_role.grant'
            when 'admin_role_grant.revoke' then 'admin_role.revoke'
            when 'project_role_grant.issue' then 'project.role_grant.manage'
            when 'project_role_grant.revoke' then 'project.role_grant.manage'
            when 'actor_profile.suspend' then 'actor.profile.suspend'
            when 'actor_profile.reactivate' then 'actor.profile.reactivate'
            when 'actor_profile.deactivate' then 'actor.profile.deactivate'
            when 'actor_identity_link.revoke' then 'actor.identity_link.revoke'
            when 'actor_identity_link.reactivate' then 'actor.identity_link.reactivate' end;
          expected_resource := case
            when record_row.operation='service_actor.create' or record_row.operation like 'actor_profile.%' then 'actor_profile'
            when record_row.operation like 'admin_role_grant.%' then 'admin_role_grant'
            when record_row.operation like 'project_role_grant.%' then 'project_role_grant'
            else 'actor_identity_link' end;
          if new.permission_id <> expected_permission or new.resource_id is null then
            raise exception 'authority event does not match operation' using errcode='23514';
          end if;
          if new.event_type='AuthorityInvalidationRequested' then
            select * into cause_row from audit_events where id=new.invalidation_cause_event_id;
            expected_invalidation_resource := case when {admin_branch} then 'actor_profile' else expected_resource end;
            expected_invalidation_id := case when {admin_branch} then cause_row.target_actor_ref else cause_row.resource_id end;
            if not found or cause_row.idempotency_reference is distinct from record_row.id
               or cause_row.actor_ref_kind is distinct from new.actor_ref_kind
               or cause_row.actor_id is distinct from new.actor_id
               or cause_row.permission_id is distinct from new.permission_id
               or cause_row.resource_type is distinct from expected_resource
               or new.resource_type is distinct from expected_invalidation_resource
               or new.resource_id is distinct from expected_invalidation_id
               or new.invalidation_target_kind is distinct from expected_invalidation_resource
               or new.invalidation_target_ref is distinct from expected_invalidation_id
               or cause_row.target_ref_kind is distinct from cause_row.resource_type
               or cause_row.target_ref_id is distinct from cause_row.resource_id
               or cause_row.request_id is distinct from new.request_id
               or cause_row.correlation_id is distinct from new.correlation_id
               or cause_row.project_id is distinct from new.project_id
               or new.entity_type <> 'authority_invalidation' or new.entity_id <> new.id
               or ({admin_branch} and (cause_row.target_actor_ref_kind <> 'actor_profile' or cause_row.target_actor_ref is null))
               {direction_checks}
               or not (
                 (record_row.operation='service_actor.create' and cause_row.event_type='ServiceActorProvisioned') or
                 (record_row.operation='admin_role_grant.issue' and cause_row.event_type='AdminRoleGrantIssued') or
                 (record_row.operation='admin_role_grant.revoke' and cause_row.event_type='AdminRoleGrantRevoked') or
                 (record_row.operation='project_role_grant.issue' and cause_row.event_type in ('ProjectRoleGrantIssued','ProjectRoleGrantReplaced')) or
                 (record_row.operation='project_role_grant.revoke' and cause_row.event_type='ProjectRoleGrantRevoked') or
                 (record_row.operation='actor_profile.suspend' and cause_row.event_type='ActorProfileSuspended') or
                 (record_row.operation='actor_profile.reactivate' and cause_row.event_type='ActorProfileReactivated') or
                 (record_row.operation='actor_profile.deactivate' and cause_row.event_type='ActorProfileDeactivated') or
                 (record_row.operation='actor_identity_link.revoke' and cause_row.event_type='ActorIdentityLinkRevoked') or
                 (record_row.operation='actor_identity_link.reactivate' and cause_row.event_type='ActorIdentityLinkReactivated')) then
              raise exception 'invalid linked authority cause' using errcode='23514';
            end if;
          else
            if new.resource_type <> expected_resource or new.entity_type <> expected_resource
               or new.entity_id <> new.resource_id or new.target_ref_kind is distinct from expected_resource
               or new.target_ref_id is distinct from new.resource_id
               or new.invalidation_cause_event_id is not null
               or new.invalidation_target_kind is not null or new.invalidation_target_ref is not null
               or not (
                 (record_row.operation='service_actor.create' and new.event_type='ServiceActorProvisioned') or
                 (record_row.operation='admin_role_grant.issue' and new.event_type='AdminRoleGrantIssued') or
                 (record_row.operation='admin_role_grant.revoke' and new.event_type='AdminRoleGrantRevoked') or
                 (record_row.operation='project_role_grant.issue' and new.event_type in ('ProjectRoleGrantIssued','ProjectRoleGrantReplaced')) or
                 (record_row.operation='project_role_grant.revoke' and new.event_type='ProjectRoleGrantRevoked') or
                 (record_row.operation='actor_profile.suspend' and new.event_type='ActorProfileSuspended') or
                 (record_row.operation='actor_profile.reactivate' and new.event_type='ActorProfileReactivated') or
                 (record_row.operation='actor_profile.deactivate' and new.event_type='ActorProfileDeactivated') or
                 (record_row.operation='actor_identity_link.revoke' and new.event_type='ActorIdentityLinkRevoked') or
                 (record_row.operation='actor_identity_link.reactivate' and new.event_type='ActorIdentityLinkReactivated')) then
              raise exception 'authority success event does not match operation' using errcode='23514';
            end if;
          end if; return new;
        end $$
        """
    )


def _create_tables() -> None:
    op.create_table(
        "admin_role_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target_actor_profile_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_project_id", sa.String(36)),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("granted_by_actor_profile_id", sa.String(36)),
        sa.Column("granted_by_system_principal", sa.String(100)),
        sa.Column("granted_by_admin_role_grant_id", sa.Uuid()),
        sa.Column("grant_reason", sa.Text(), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("revoked_by_actor_profile_id", sa.String(36)),
        sa.Column("revoked_by_admin_role_grant_id", sa.Uuid()),
        sa.Column("revoked_reason", sa.Text()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_role_grants")),
        sa.ForeignKeyConstraint(
            ["target_actor_profile_id"],
            ["actor_profiles.id"],
            name=op.f("fk_admin_role_grants_target_actor_profile_id_actor_profiles"),
        ),
        sa.ForeignKeyConstraint(
            ["scope_project_id"],
            ["projects.id"],
            name=op.f("fk_admin_role_grants_scope_project_id_projects"),
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_actor_profile_id"],
            ["actor_profiles.id"],
            name=op.f("fk_admin_role_grants_granted_by_actor_profile_id_actor_profiles"),
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_admin_role_grant_id"],
            ["admin_role_grants.id"],
            name=op.f("fk_admin_role_grants_granted_by_admin_role_grant_id_admin_role_grants"),
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_actor_profile_id"],
            ["actor_profiles.id"],
            name=op.f("fk_admin_role_grants_revoked_by_actor_profile_id_actor_profiles"),
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_admin_role_grant_id"],
            ["admin_role_grants.id"],
            name=op.f("fk_admin_role_grants_revoked_by_admin_role_grant_id_admin_role_grants"),
        ),
        sa.CheckConstraint(
            "role in ('access_administrator','operator','project_manager','finance_authority','audit_authority')",
            name=op.f("ck_admin_role_grants_role"),
        ),
        sa.CheckConstraint(
            "scope_type in ('system','project')", name=op.f("ck_admin_role_grants_scope_type")
        ),
        sa.CheckConstraint(
            "(scope_type='system' and scope_project_id is null) or (scope_type='project' and scope_project_id is not null and role not in ('access_administrator','operator'))",
            name=op.f("ck_admin_role_grants_role_scope"),
        ),
        sa.CheckConstraint(
            "(granted_by_system_principal='workstream:system:bootstrap' and granted_by_actor_profile_id is null and granted_by_admin_role_grant_id is null) or (granted_by_system_principal is null and granted_by_actor_profile_id is not null and granted_by_admin_role_grant_id is not null)",
            name=op.f("ck_admin_role_grants_grant_attribution"),
        ),
        sa.CheckConstraint(
            "octet_length(grant_reason) between 1 and 500",
            name=op.f("ck_admin_role_grants_grant_reason"),
        ),
        sa.CheckConstraint(
            "(status='active' and version=1 and revoked_by_actor_profile_id is null and revoked_by_admin_role_grant_id is null and revoked_reason is null and revoked_at is null) or (status='revoked' and version=2 and revoked_by_actor_profile_id is not null and revoked_by_admin_role_grant_id is not null and revoked_reason is not null and octet_length(revoked_reason) between 1 and 500 and revoked_at is not null)",
            name=op.f("ck_admin_role_grants_lifecycle"),
        ),
    )
    op.create_index(
        "uq_admin_role_grants_active_system",
        "admin_role_grants",
        ["target_actor_profile_id", "role"],
        unique=True,
        postgresql_where=sa.text("status='active' and scope_type='system'"),
    )
    op.create_index(
        "uq_admin_role_grants_active_project",
        "admin_role_grants",
        ["target_actor_profile_id", "role", "scope_project_id"],
        unique=True,
        postgresql_where=sa.text("status='active' and scope_type='project'"),
    )
    op.create_index(
        "ix_admin_role_grants_effective_candidate",
        "admin_role_grants",
        ["target_actor_profile_id", "status", "scope_type", "scope_project_id"],
    )
    op.create_index(
        "ix_admin_role_grants_history",
        "admin_role_grants",
        ["target_actor_profile_id", "granted_at", "id"],
    )
    op.create_index(
        "ix_admin_role_grants_final_access_admin",
        "admin_role_grants",
        ["role", "status"],
        postgresql_where=sa.text(
            "role='access_administrator' and status='active' and scope_type='system'"
        ),
    )

    op.create_table(
        "authority_control",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("bootstrap_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("bootstrap_grant_id", sa.Uuid()),
        sa.Column("version", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_authority_control")),
        sa.ForeignKeyConstraint(
            ["bootstrap_grant_id"],
            ["admin_role_grants.id"],
            name=op.f("fk_authority_control_bootstrap_grant_id_admin_role_grants"),
        ),
        sa.CheckConstraint("id=1", name=op.f("ck_authority_control_singleton")),
        sa.CheckConstraint(
            "(bootstrap_completed=false and bootstrap_grant_id is null and version=0) or (bootstrap_completed=true and bootstrap_grant_id is not null and version=1)",
            name=op.f("ck_authority_control_bootstrap_state"),
        ),
    )
    op.execute(
        "insert into authority_control(id,bootstrap_completed,bootstrap_grant_id,version) values (1,false,null,0)"
    )


def _create_table_guards() -> None:
    statements = (
        """
        create function guard_admin_role_grant() returns trigger language plpgsql as $$
        declare target_kind text; authorizer admin_role_grants%rowtype;
                bootstrap_done boolean;
        begin
          if tg_op='DELETE' then raise exception 'admin role grants are immutable' using errcode='55000'; end if;
          if tg_op='INSERT' then
            select actor_kind into target_kind from actor_profiles where id=new.target_actor_profile_id;
            if target_kind is distinct from 'human' then raise exception 'admin role target must be human' using errcode='23514'; end if;
            new.granted_at := clock_timestamp();
            if new.granted_by_system_principal is not null then
              if new.role <> 'access_administrator' or new.scope_type <> 'system' then raise exception 'invalid bootstrap grant' using errcode='23514'; end if;
              select bootstrap_completed into bootstrap_done from authority_control where id=1 for update;
              if bootstrap_done is distinct from false
                 or exists(select 1 from admin_role_grants where granted_by_system_principal='workstream:system:bootstrap') then
                raise exception 'bootstrap already completed' using errcode='23514';
              end if;
            else
              select * into authorizer from admin_role_grants where id=new.granted_by_admin_role_grant_id;
              if not found or authorizer.target_actor_profile_id <> new.granted_by_actor_profile_id
                 or authorizer.role <> 'access_administrator' or authorizer.scope_type <> 'system'
                 or authorizer.status <> 'active' then raise exception 'invalid admin grant attribution' using errcode='23514'; end if;
            end if;
            return new;
          end if;
          if old.status <> 'active' or old.version <> 1 or new.status <> 'revoked' or new.version <> 2
             or (new.id,new.target_actor_profile_id,new.role,new.scope_type,new.scope_project_id,
                 new.granted_by_actor_profile_id,new.granted_by_system_principal,
                 new.granted_by_admin_role_grant_id,new.grant_reason,new.granted_at)
                is distinct from
                (old.id,old.target_actor_profile_id,old.role,old.scope_type,old.scope_project_id,
                 old.granted_by_actor_profile_id,old.granted_by_system_principal,
                 old.granted_by_admin_role_grant_id,old.grant_reason,old.granted_at) then
            raise exception 'invalid admin role grant transition' using errcode='23514';
          end if;
          select * into authorizer from admin_role_grants where id=new.revoked_by_admin_role_grant_id;
          if not found or authorizer.target_actor_profile_id <> new.revoked_by_actor_profile_id
             or authorizer.role <> 'access_administrator' or authorizer.scope_type <> 'system'
             or authorizer.status <> 'active' then raise exception 'invalid admin revoke attribution' using errcode='23514'; end if;
          new.revoked_at := clock_timestamp(); return new;
        end $$
        """,
        "create trigger admin_role_grants_guard before insert or update or delete on admin_role_grants for each row execute function guard_admin_role_grant()",
        """create function reject_admin_role_grant_truncate() returns trigger language plpgsql as $$
             begin raise exception 'admin role grants are immutable' using errcode='55000'; end $$""",
        "create trigger admin_role_grants_reject_truncate before truncate on admin_role_grants execute function reject_admin_role_grant_truncate()",
        """
        create function guard_authority_control() returns trigger language plpgsql as $$
        begin
          if tg_op in ('INSERT','DELETE') then raise exception 'authority control is immutable' using errcode='55000'; end if;
          if old.id <> 1 or old.bootstrap_completed or old.version <> 0
             or new.id <> 1 or not new.bootstrap_completed or new.version <> 1
             or new.bootstrap_grant_id is null or new.created_at is distinct from old.created_at then
            raise exception 'invalid authority control transition' using errcode='23514';
          end if;
          new.updated_at := clock_timestamp(); return new;
        end $$
        """,
        "create trigger authority_control_guard before insert or update or delete on authority_control for each row execute function guard_authority_control()",
        """create function reject_authority_control_truncate() returns trigger language plpgsql as $$
             begin raise exception 'authority control is immutable' using errcode='55000'; end $$""",
        "create trigger authority_control_reject_truncate before truncate on authority_control execute function reject_authority_control_truncate()",
        """
        create function validate_bootstrap_authority_state() returns trigger language plpgsql as $$
        declare control authority_control%rowtype;
                bootstrap_count bigint;
                referenced_bootstrap boolean;
        begin
          select * into control from authority_control where id=1;
          if not found then
            raise exception 'bootstrap grant/control invariant violated' using errcode='23514';
          end if;
          select count(*) into bootstrap_count from admin_role_grants
          where granted_by_system_principal='workstream:system:bootstrap';
          referenced_bootstrap := exists(
            select 1 from admin_role_grants
            where id=control.bootstrap_grant_id
              and granted_by_system_principal='workstream:system:bootstrap'
          );
          if (not control.bootstrap_completed and
              (control.bootstrap_grant_id is not null or control.version <> 0 or bootstrap_count <> 0))
             or (control.bootstrap_completed and
              (control.bootstrap_grant_id is null or control.version <> 1
               or bootstrap_count <> 1 or not referenced_bootstrap)) then
            raise exception 'bootstrap grant/control invariant violated' using errcode='23514';
          end if;
          return null;
        end $$
        """,
        "create constraint trigger admin_role_grants_bootstrap_invariant after insert or update or delete on admin_role_grants deferrable initially deferred for each row execute function validate_bootstrap_authority_state()",
        "create constraint trigger authority_control_bootstrap_invariant after insert or update or delete on authority_control deferrable initially deferred for each row execute function validate_bootstrap_authority_state()",
    )
    for statement in statements:
        op.execute(statement)


def upgrade() -> None:
    """Install irreversible bootstrap state and immutable admin grants."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "lock table authority_idempotency_records, audit_events in access exclusive mode"
        )
    )
    if bind.execute(
        sa.text(
            f"select exists(select 1 from audit_events where event_domain='authority' and event_type in ({_tokens(AUTH_08_EVIDENCE_EVENTS)}))"
        )
    ).scalar_one():
        raise RuntimeError("cannot adopt orphan administrative grant evidence")
    if bind.execute(
        sa.text(
            "select exists(select 1 from authority_idempotency_records where operation like 'admin_role_grant.%')"
        )
    ).scalar_one():
        raise RuntimeError("cannot adopt orphan administrative idempotency")
    _create_tables()
    _create_table_guards()
    op.drop_constraint("authorization_action_evidence", "audit_events", type_="check")
    _create_action_constraint(ACTION_PERMISSION_PAIRS)
    _replace_fact_function(admin_issue_direction=True)
    _replace_linked_function(admin_projection=True)


def downgrade() -> None:
    """Restore 0021 only when no AUTH-08 durable state exists."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "lock table authority_control, admin_role_grants, authority_idempotency_records, audit_events in access exclusive mode"
        )
    )
    blocked = bind.execute(
        sa.text(f"""
      select exists(select 1 from admin_role_grants)
      or exists(select 1 from authority_control where bootstrap_completed)
      or exists(select 1 from authority_idempotency_records where operation like 'admin_role_grant.%')
      or exists(select 1 from audit_events where action_id in ({_tokens(AUTH_08_ACTIONS)})
        or event_type in ({_tokens(AUTH_08_EVIDENCE_EVENTS)}))
    """)
    ).scalar_one()
    if blocked:
        raise RuntimeError("cannot downgrade non-empty administrative authority")
    op.drop_constraint("authorization_action_evidence", "audit_events", type_="check")
    _create_action_constraint(ACTION_PERMISSION_PAIRS[:-7])
    _replace_fact_function(admin_issue_direction=False)
    _replace_linked_function(admin_projection=False)
    op.execute("drop trigger authority_control_bootstrap_invariant on authority_control")
    op.execute("drop trigger admin_role_grants_bootstrap_invariant on admin_role_grants")
    op.execute("drop function validate_bootstrap_authority_state()")
    op.execute("drop trigger authority_control_reject_truncate on authority_control")
    op.execute("drop trigger authority_control_guard on authority_control")
    op.execute("drop function reject_authority_control_truncate()")
    op.execute("drop function guard_authority_control()")
    op.execute("drop trigger admin_role_grants_reject_truncate on admin_role_grants")
    op.execute("drop trigger admin_role_grants_guard on admin_role_grants")
    op.execute("drop function reject_admin_role_grant_truncate()")
    op.execute("drop function guard_admin_role_grant()")
    op.drop_table("authority_control")
    op.drop_table("admin_role_grants")
