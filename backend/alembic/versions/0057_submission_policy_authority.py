"""install submission-policy authorization foundation

Revision ID: 0057_submission_policy_authority
Revises: 0056_review_lease_preference
Create Date: 2026-08-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0057_submission_policy_authority"
down_revision = "0056_review_lease_preference"
branch_labels = depends_on = None

_SUBMISSION_CREATION_COLUMNS = (
    ("created_by_actor_profile_id", sa.String(36)),
    ("created_via_identity_link_id", sa.String(36)),
    ("created_by_admin_role_grant_id", sa.Uuid()),
    ("created_by_service_identity", sa.String(160)),
    ("creation_scope_type", sa.String(16)),
    ("creation_scope_project_id", sa.String(36)),
    ("creation_action_id", sa.String(160)),
    ("creation_decision_event_id", sa.String(36)),
)
_SUBMISSION_APPROVAL_COLUMNS = (
    ("approved_by_actor_profile_id", sa.String(36)),
    ("approved_via_identity_link_id", sa.String(36)),
    ("approved_by_admin_role_grant_id", sa.Uuid()),
    ("approval_scope_type", sa.String(16)),
    ("approval_scope_project_id", sa.String(36)),
    ("approval_action_id", sa.String(160)),
    ("approval_decision_event_id", sa.String(36)),
)
_APPROVAL_OUTPUT_COLUMNS = (
    ("created_by_actor_profile_id", sa.String(36)),
    ("created_via_identity_link_id", sa.String(36)),
    ("created_by_admin_role_grant_id", sa.Uuid()),
    ("creation_scope_type", sa.String(16)),
    ("creation_scope_project_id", sa.String(36)),
    ("creation_action_id", sa.String(160)),
    ("creation_decision_event_id", sa.String(36)),
)
_AUDIT_RESOURCE_MARKER = "('project_create_operation'::character varying)::text"
_AUDIT_RESOURCE_ADDITION = (
    ", ('project_submission_artifact_policy_mutation'::character varying)::text"
)


def _rewrite_audit_resource(*, add: bool) -> None:
    bind = op.get_bind()
    definition = bind.execute(
        sa.text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='audit_events'::regclass "
            "and conname='ck_audit_events_authority_privacy_bounds'"
        )
    ).scalar_one()
    expanded = _AUDIT_RESOURCE_MARKER + _AUDIT_RESOURCE_ADDITION
    source, target = (
        (_AUDIT_RESOURCE_MARKER, expanded)
        if add
        else (expanded, _AUDIT_RESOURCE_MARKER)
    )
    if definition.count(source) != 1 or (add and expanded in definition):
        raise RuntimeError("unexpected authority privacy constraint")
    op.drop_constraint("authority_privacy_bounds", "audit_events", type_="check")
    op.execute(
        "alter table audit_events add constraint "
        f"ck_audit_events_authority_privacy_bounds {definition.replace(source, target, 1)}"
    )


def _add_columns(table: str, columns: tuple[tuple[str, sa.types.TypeEngine], ...]) -> None:
    for name, column_type in columns:
        op.add_column(table, sa.Column(name, column_type))


def _add_common_foreign_keys(table: str, prefix: str, *, approval: bool = False) -> None:
    stem = "approval" if approval else "creation"
    actor = "approved_by_actor_profile_id" if approval else "created_by_actor_profile_id"
    link = "approved_via_identity_link_id" if approval else "created_via_identity_link_id"
    grant = (
        "approved_by_admin_role_grant_id" if approval else "created_by_admin_role_grant_id"
    )
    project = "approval_scope_project_id" if approval else "creation_scope_project_id"
    decision = "approval_decision_event_id" if approval else "creation_decision_event_id"
    for suffix, column, remote_table in (
        ("actor", actor, "actor_profiles"),
        ("link", link, "actor_identity_links"),
        ("grant", grant, "admin_role_grants"),
        ("project", project, "projects"),
        ("decision", decision, "audit_events"),
    ):
        op.create_foreign_key(
            f"fk_{prefix}_{stem}_{suffix}", table, remote_table, [column], ["id"]
        )


def upgrade() -> None:
    """Install nullable provenance and replay custody without activation."""
    op.execute("lock table audit_events in access exclusive mode")
    _rewrite_audit_resource(add=True)
    _add_columns(
        "submission_artifact_policies",
        (*_SUBMISSION_CREATION_COLUMNS, *_SUBMISSION_APPROVAL_COLUMNS),
    )
    _add_common_foreign_keys("submission_artifact_policies", "submission_policy")
    _add_common_foreign_keys(
        "submission_artifact_policies", "submission_policy", approval=True
    )
    _add_columns("effective_project_submission_artifact_policies", _APPROVAL_OUTPUT_COLUMNS)
    _add_common_foreign_keys("effective_project_submission_artifact_policies", "effective_policy")
    _add_columns("pre_submit_checker_policies", _APPROVAL_OUTPUT_COLUMNS)
    _add_common_foreign_keys("pre_submit_checker_policies", "pre_submit_policy")

    op.create_check_constraint(
        "ck_submission_policy_creation_authority_shape",
        "submission_artifact_policies",
        "(created_by_actor_profile_id is null and created_via_identity_link_id is null "
        "and created_by_admin_role_grant_id is null and created_by_service_identity is null "
        "and creation_scope_type is null and creation_scope_project_id is null "
        "and creation_action_id is null and creation_decision_event_id is null) or "
        "(created_by_actor_profile_id is not null and created_via_identity_link_id is not null "
        "and creation_scope_type is not null and creation_action_id is not null "
        "and creation_scope_project_id is not null "
        "and creation_scope_project_id=project_id and creation_decision_event_id is not null "
        "and creation_action_id in ('project.submission_artifact_policy.create',"
        "'project.submission_artifact_policy.derive',"
        "'project.submission_artifact_policy.update') and "
        "((created_by_admin_role_grant_id is not null and created_by_service_identity is null "
        "and creation_scope_type in ('system','project')) or "
        "(created_by_admin_role_grant_id is null "
        "and created_by_service_identity is not null "
        "and created_by_service_identity='workstream.project.setup' "
        "and creation_scope_type='service' "
        "and creation_action_id='project.submission_artifact_policy.derive')))",
    )
    op.create_check_constraint(
        "ck_submission_policy_approval_authority_shape",
        "submission_artifact_policies",
        "(approved_by_actor_profile_id is null and approved_via_identity_link_id is null "
        "and approved_by_admin_role_grant_id is null and approval_scope_type is null "
        "and approval_scope_project_id is null and approval_action_id is null "
        "and approval_decision_event_id is null) or "
        "(approved_by_actor_profile_id is not null and approved_via_identity_link_id is not null "
        "and approved_by_admin_role_grant_id is not null "
        "and approval_scope_type is not null and approval_action_id is not null "
        "and approval_scope_type in ('system','project') "
        "and approval_scope_project_id is not null "
        "and approval_scope_project_id=project_id "
        "and approval_action_id='project.submission_artifact_policy.approve' "
        "and approval_decision_event_id is not null)",
    )
    output_shape = (
        "(created_by_actor_profile_id is null and created_via_identity_link_id is null "
        "and created_by_admin_role_grant_id is null and creation_scope_type is null "
        "and creation_scope_project_id is null and creation_action_id is null "
        "and creation_decision_event_id is null) or "
        "(created_by_actor_profile_id is not null and created_via_identity_link_id is not null "
        "and created_by_admin_role_grant_id is not null "
        "and creation_scope_type is not null and creation_action_id is not null "
        "and creation_scope_type in ('system','project') "
        "and creation_scope_project_id is not null "
        "and creation_scope_project_id=project_id "
        "and creation_action_id='project.submission_artifact_policy.approve' "
        "and creation_decision_event_id is not null)"
    )
    op.create_check_constraint(
        "ck_effective_submission_policy_authority_shape",
        "effective_project_submission_artifact_policies",
        output_shape,
    )
    op.create_check_constraint(
        "ck_pre_submit_policy_authority_shape",
        "pre_submit_checker_policies",
        output_shape,
    )

    op.create_table(
        "submission_policy_mutation_idempotency_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_profile_id", sa.String(36), sa.ForeignKey("actor_profiles.id"), nullable=False),
        sa.Column("identity_link_id", sa.String(36), sa.ForeignKey("actor_identity_links.id"), nullable=False),
        sa.Column("service_identity", sa.String(160)),
        sa.Column("action_id", sa.String(160), nullable=False),
        sa.Column("idempotency_key", sa.Uuid()),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("resource_context_digest", sa.String(71), nullable=False),
        sa.Column("resource_context_json", sa.JSON(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("guide_id", sa.String(36), sa.ForeignKey("project_guides.id"), nullable=False),
        sa.Column("source_snapshot_id", sa.String(36), sa.ForeignKey("guide_source_snapshots.id"), nullable=False),
        sa.Column("policy_id", sa.String(36), nullable=False),
        sa.Column("setup_run_id", sa.String(36), sa.ForeignKey("project_setup_runs.id")),
        sa.Column("setup_generation", sa.BigInteger(), nullable=False),
        sa.Column("setup_task_id", sa.Uuid()),
        sa.Column("correlation_id", sa.Uuid()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("response_json", sa.JSON()),
        sa.Column(
            "committed_policy_id",
            sa.String(36),
            sa.ForeignKey("submission_artifact_policies.id"),
        ),
        sa.Column(
            "committed_effective_policy_id",
            sa.String(36),
            sa.ForeignKey("effective_project_submission_artifact_policies.id"),
        ),
        sa.Column(
            "committed_pre_submit_policy_id",
            sa.String(36),
            sa.ForeignKey("pre_submit_checker_policies.id"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("operation_id", name="uq_submission_policy_operation_identity"),
        sa.CheckConstraint(
            "action_id in ('project.submission_artifact_policy.create',"
            "'project.submission_artifact_policy.derive',"
            "'project.submission_artifact_policy.update',"
            "'project.submission_artifact_policy.approve')",
            name="ck_submission_policy_mutation_action",
        ),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "resource_context_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_submission_policy_mutation_digests",
        ),
        sa.CheckConstraint("setup_generation > 0", name="ck_submission_policy_generation"),
        sa.CheckConstraint(
            "(service_identity is null and idempotency_key is not null "
            "and setup_run_id is null and setup_task_id is null and correlation_id is null) or "
            "(service_identity is not null "
            "and service_identity='workstream.project.setup' and idempotency_key is null "
            "and action_id='project.submission_artifact_policy.derive' "
            "and setup_run_id is not null and setup_task_id is not null "
            "and correlation_id is not null)",
            name="ck_submission_policy_replay_principal_shape",
        ),
        sa.CheckConstraint(
            "status in ('pending','committed')", name="ck_submission_policy_replay_status"
        ),
        sa.CheckConstraint(
            "(status='pending' and response_json is null and committed_at is null "
            "and committed_policy_id is null and committed_effective_policy_id is null "
            "and committed_pre_submit_policy_id is null) or "
            "(status='committed' and response_json is not null and committed_at is not null "
            "and committed_policy_id is not null and "
            "((action_id='project.submission_artifact_policy.approve' "
            "and committed_effective_policy_id is not null "
            "and committed_pre_submit_policy_id is not null) or "
            "(action_id<>'project.submission_artifact_policy.approve' "
            "and committed_effective_policy_id is null "
            "and committed_pre_submit_policy_id is null)))",
            name="ck_submission_policy_replay_state_shape",
        ),
    )
    op.create_index(
        "uq_submission_policy_human_replay_namespace",
        "submission_policy_mutation_idempotency_records",
        ["actor_profile_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("service_identity is null"),
    )
    op.create_index(
        "uq_submission_policy_service_replay_namespace",
        "submission_policy_mutation_idempotency_records",
        [
            "actor_profile_id",
            "setup_run_id",
            "setup_generation",
            "setup_task_id",
            "correlation_id",
            "action_id",
        ],
        unique=True,
        postgresql_where=sa.text("service_identity is not null"),
    )
    op.create_index(
        "uq_submission_policy_committed_policy_action",
        "submission_policy_mutation_idempotency_records",
        ["committed_policy_id", "action_id"],
        unique=True,
        postgresql_where=sa.text("status='committed'"),
    )
    op.execute(
        """
        create function reject_submission_policy_replay_mutation() returns trigger
        language plpgsql as $$
        begin
          if tg_op = 'DELETE' then
            raise exception 'submission-policy replay rows cannot be deleted';
          end if;
          if old.status <> 'pending' or new.status <> 'committed'
             or (new.id,new.actor_profile_id,new.identity_link_id,new.service_identity,
                 new.action_id,new.idempotency_key,new.request_digest,
                 new.resource_context_digest,new.resource_context_json::text,new.operation_id,
                 new.project_id,new.guide_id,new.source_snapshot_id,new.policy_id,
                 new.setup_run_id,new.setup_generation,new.setup_task_id,
                 new.correlation_id,new.created_at)
                is distinct from
                (old.id,old.actor_profile_id,old.identity_link_id,old.service_identity,
                 old.action_id,old.idempotency_key,old.request_digest,
                 old.resource_context_digest,old.resource_context_json::text,old.operation_id,
                 old.project_id,old.guide_id,old.source_snapshot_id,old.policy_id,
                 old.setup_run_id,old.setup_generation,old.setup_task_id,
                 old.correlation_id,old.created_at)
          then
            raise exception 'invalid submission-policy replay mutation';
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        "create trigger trg_submission_policy_replay_immutable before update or delete "
        "on submission_policy_mutation_idempotency_records for each row "
        "execute function reject_submission_policy_replay_mutation()"
    )
    op.execute(
        """
        create function reject_submission_policy_replay_truncate() returns trigger
        language plpgsql as $$ begin
          raise exception 'submission-policy replay rows cannot be truncated';
        end $$
        """
    )
    op.execute(
        "create trigger trg_submission_policy_replay_no_truncate before truncate "
        "on submission_policy_mutation_idempotency_records for each statement "
        "execute function reject_submission_policy_replay_truncate()"
    )
    op.execute(
        """
        create function protect_submission_policy_creation_provenance() returns trigger
        language plpgsql as $$
        begin
          if old.creation_action_id is not null and
             (new.created_by_actor_profile_id,new.created_via_identity_link_id,
              new.created_by_admin_role_grant_id,new.created_by_service_identity,
              new.creation_scope_type,new.creation_scope_project_id,
              new.creation_action_id,new.creation_decision_event_id)
             is distinct from
             (old.created_by_actor_profile_id,old.created_via_identity_link_id,
              old.created_by_admin_role_grant_id,old.created_by_service_identity,
              old.creation_scope_type,old.creation_scope_project_id,
              old.creation_action_id,old.creation_decision_event_id) then
            raise exception 'submission-policy creation provenance is immutable'
              using errcode='23514';
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        "create trigger submission_policy_creation_provenance_immutable before update on "
        "submission_artifact_policies for each row "
        "execute function protect_submission_policy_creation_provenance()"
    )
    op.execute(
        """
        create function protect_submission_policy_approval_provenance() returns trigger
        language plpgsql as $$
        begin
          if old.approval_action_id is not null and
             (new.approved_by_actor_profile_id,new.approved_via_identity_link_id,
              new.approved_by_admin_role_grant_id,new.approval_scope_type,
              new.approval_scope_project_id,new.approval_action_id,
              new.approval_decision_event_id)
             is distinct from
             (old.approved_by_actor_profile_id,old.approved_via_identity_link_id,
              old.approved_by_admin_role_grant_id,old.approval_scope_type,
              old.approval_scope_project_id,old.approval_action_id,
              old.approval_decision_event_id) then
            raise exception 'submission-policy approval provenance is immutable'
              using errcode='23514';
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        "create trigger submission_policy_approval_provenance_immutable before update on "
        "submission_artifact_policies for each row "
        "execute function protect_submission_policy_approval_provenance()"
    )
    op.execute(
        """
        create function protect_submission_policy_output_provenance() returns trigger
        language plpgsql as $$
        begin
          if old.creation_action_id is not null and
             (new.created_by_actor_profile_id,new.created_via_identity_link_id,
              new.created_by_admin_role_grant_id,new.creation_scope_type,
              new.creation_scope_project_id,new.creation_action_id,
              new.creation_decision_event_id)
             is distinct from
             (old.created_by_actor_profile_id,old.created_via_identity_link_id,
              old.created_by_admin_role_grant_id,old.creation_scope_type,
              old.creation_scope_project_id,old.creation_action_id,
              old.creation_decision_event_id) then
            raise exception 'submission-policy output provenance is immutable'
              using errcode='23514';
          end if;
          return new;
        end $$
        """
    )
    for trigger, table in (
        (
            "effective_submission_policy_provenance_immutable",
            "effective_project_submission_artifact_policies",
        ),
        ("pre_submit_policy_provenance_immutable", "pre_submit_checker_policies"),
    ):
        op.execute(
            f"create trigger {trigger} before update on {table} for each row "
            "execute function protect_submission_policy_output_provenance()"
        )
    op.execute(
        """
        create function validate_submission_policy_creation_custody() returns trigger
        language plpgsql as $$
        declare reservation submission_policy_mutation_idempotency_records%rowtype;
                evidence audit_events%rowtype;
        begin
          if new.creation_action_id is null then
            if new.created_by_actor_profile_id is not null
               or new.created_via_identity_link_id is not null
               or new.created_by_admin_role_grant_id is not null
               or new.created_by_service_identity is not null
               or new.creation_scope_type is not null
               or new.creation_scope_project_id is not null
               or new.creation_decision_event_id is not null then
              raise exception 'partial submission-policy creation provenance'
                using errcode='23514';
            end if;
            return null;
          end if;
          select * into reservation from submission_policy_mutation_idempotency_records
            where committed_policy_id=new.id and action_id=new.creation_action_id
              and status='committed';
          if reservation.id is null
             or reservation.actor_profile_id
                is distinct from new.created_by_actor_profile_id
             or reservation.identity_link_id
                is distinct from new.created_via_identity_link_id
             or reservation.service_identity
                is distinct from new.created_by_service_identity
             or reservation.project_id is distinct from new.project_id
             or reservation.policy_id is distinct from new.id
             or reservation.guide_id is distinct from new.guide_id
             or reservation.source_snapshot_id is distinct from new.source_snapshot_id
             or reservation.resource_context_json->>'guide_version'
                is distinct from new.guide_version then
            raise exception 'submission-policy creation custody mismatch' using errcode='23514';
          end if;
          select * into evidence from audit_events where id=new.creation_decision_event_id;
          if evidence.id is null or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind is distinct from 'actor_profile'
             or evidence.actor_id is distinct from new.created_by_actor_profile_id
             or evidence.matched_grant_id
                is distinct from new.created_by_admin_role_grant_id::text
             or evidence.permission_id is distinct from 'project.effective_policy.manage'
             or evidence.action_id is distinct from new.creation_action_id
             or evidence.resource_type
                is distinct from 'project_submission_artifact_policy_mutation'
             or evidence.resource_id is distinct from new.id
             or evidence.project_id is distinct from reservation.project_id
             or evidence.target_ref_kind is distinct from 'project'
             or evidence.target_ref_id is distinct from reservation.project_id
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or evidence.after_facts->>'resource_context_digest'
                is distinct from reservation.resource_context_digest then
            raise exception 'submission-policy creation evidence mismatch'
              using errcode='23514';
          end if;
          return null;
        end $$
        """
    )
    op.execute(
        "create constraint trigger submission_policy_creation_custody "
        "after insert or update on submission_artifact_policies "
        "deferrable initially deferred for each row "
        "execute function validate_submission_policy_creation_custody()"
    )
    op.execute(
        """
        create function validate_submission_policy_authority_custody() returns trigger
        language plpgsql as $$
        declare reservation submission_policy_mutation_idempotency_records%rowtype;
                evidence audit_events%rowtype;
                actor_id varchar; link_id varchar; grant_id uuid; service_id varchar;
                action_value varchar; decision_id varchar; product_project varchar;
                product_id varchar; approval_outputs_valid boolean;
        begin
          if tg_table_name='submission_policy_mutation_idempotency_records' then
            if new.status='pending' then return null; end if;
            reservation:=new;
            select project_id,id,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then approved_by_actor_profile_id else created_by_actor_profile_id end,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then approved_via_identity_link_id else created_via_identity_link_id end,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then approved_by_admin_role_grant_id
                        else created_by_admin_role_grant_id end,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then null else created_by_service_identity end,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then approval_action_id else creation_action_id end,
                   case when reservation.action_id='project.submission_artifact_policy.approve'
                        then approval_decision_event_id else creation_decision_event_id end
              into product_project,product_id,actor_id,link_id,grant_id,service_id,
                   action_value,decision_id
              from submission_artifact_policies where id=reservation.committed_policy_id;
            if reservation.action_id='project.submission_artifact_policy.approve' then
              select exists(
                select 1
                  from submission_artifact_policies s
                  join effective_project_submission_artifact_policies e
                    on e.id=reservation.committed_effective_policy_id
                   and e.submission_artifact_policy_id=s.id
                   and e.submission_artifact_policy_hash=s.policy_hash
                  join pre_submit_checker_policies p
                    on p.id=reservation.committed_pre_submit_policy_id
                   and p.project_id=e.project_id
                  where s.id=reservation.committed_policy_id
                    and s.id=reservation.policy_id
                    and s.guide_id=reservation.guide_id
                    and s.source_snapshot_id=reservation.source_snapshot_id
                    and s.guide_version=reservation.resource_context_json->>'guide_version'
                    and s.policy_hash=reservation.resource_context_json->>'policy_digest'
                    and e.effective_policy_hash=
                        reservation.resource_context_json->>'effective_output_digest'
                    and p.compiled_bundle_hash=
                        reservation.resource_context_json->>'compiled_pre_submit_output_digest'
                    and e.project_id=reservation.project_id
                    and e.guide_id=s.guide_id and p.guide_id=s.guide_id
                    and e.guide_version=s.guide_version
                    and p.guide_version=s.guide_version
                    and e.source_snapshot_id=s.source_snapshot_id
                    and p.source_snapshot_id=s.source_snapshot_id
                    and e.source_snapshot_hash=s.source_snapshot_hash
                    and p.source_snapshot_hash=s.source_snapshot_hash
                    and e.submission_artifact_policy_id=reservation.committed_policy_id
                    and p.effective_policy_id=e.id
                    and p.effective_policy_hash=e.effective_policy_hash
                    and e.created_by_actor_profile_id=reservation.actor_profile_id
                    and p.created_by_actor_profile_id=reservation.actor_profile_id
                    and e.created_via_identity_link_id=reservation.identity_link_id
                    and p.created_via_identity_link_id=reservation.identity_link_id
                    and e.created_by_admin_role_grant_id=grant_id
                    and p.created_by_admin_role_grant_id=grant_id
                    and e.creation_scope_project_id=reservation.project_id
                    and p.creation_scope_project_id=reservation.project_id
                    and e.creation_action_id=reservation.action_id
                    and p.creation_action_id=reservation.action_id
                    and e.creation_decision_event_id=decision_id
                    and p.creation_decision_event_id=decision_id
              ) into approval_outputs_valid;
              if approval_outputs_valid is not true then
                raise exception 'submission-policy approval output custody mismatch'
                  using errcode='23514';
              end if;
            end if;
          elsif tg_table_name='submission_artifact_policies' then
            if new.creation_action_id is null and new.approval_action_id is null then
              if new.created_by_actor_profile_id is not null
                 or new.created_via_identity_link_id is not null
                 or new.created_by_admin_role_grant_id is not null
                 or new.created_by_service_identity is not null
                 or new.creation_scope_type is not null
                 or new.creation_scope_project_id is not null
                 or new.creation_decision_event_id is not null
                 or new.approved_by_actor_profile_id is not null
                 or new.approved_via_identity_link_id is not null
                 or new.approved_by_admin_role_grant_id is not null
                 or new.approval_scope_type is not null
                 or new.approval_scope_project_id is not null
                 or new.approval_decision_event_id is not null then
                raise exception 'partial submission-policy provenance'
                  using errcode='23514';
              end if;
              return null;
            end if;
            if new.approval_action_id is not null then
              select * into reservation from submission_policy_mutation_idempotency_records
                where committed_policy_id=new.id and action_id=new.approval_action_id
                  and status='committed';
              actor_id:=new.approved_by_actor_profile_id;
              link_id:=new.approved_via_identity_link_id;
              grant_id:=new.approved_by_admin_role_grant_id;
              service_id:=null; action_value:=new.approval_action_id;
              decision_id:=new.approval_decision_event_id;
            else
              select * into reservation from submission_policy_mutation_idempotency_records
                where committed_policy_id=new.id and action_id=new.creation_action_id
                  and status='committed';
              actor_id:=new.created_by_actor_profile_id;
              link_id:=new.created_via_identity_link_id;
              grant_id:=new.created_by_admin_role_grant_id;
              service_id:=new.created_by_service_identity;
              action_value:=new.creation_action_id;
              decision_id:=new.creation_decision_event_id;
            end if;
            product_project:=new.project_id; product_id:=new.id;
          elsif tg_table_name='effective_project_submission_artifact_policies' then
            if new.creation_action_id is null then
              if new.created_by_actor_profile_id is not null
                 or new.created_via_identity_link_id is not null
                 or new.created_by_admin_role_grant_id is not null
                 or new.creation_scope_type is not null
                 or new.creation_scope_project_id is not null
                 or new.creation_decision_event_id is not null then
                raise exception 'partial effective-policy provenance'
                  using errcode='23514';
              end if;
              return null;
            end if;
            select * into reservation from submission_policy_mutation_idempotency_records
              where committed_effective_policy_id=new.id and status='committed';
            actor_id:=new.created_by_actor_profile_id;
            link_id:=new.created_via_identity_link_id;
            grant_id:=new.created_by_admin_role_grant_id;
            service_id:=null; action_value:=new.creation_action_id;
            decision_id:=new.creation_decision_event_id;
            product_project:=new.project_id; product_id:=reservation.committed_policy_id;
          else
            if new.creation_action_id is null then
              if new.created_by_actor_profile_id is not null
                 or new.created_via_identity_link_id is not null
                 or new.created_by_admin_role_grant_id is not null
                 or new.creation_scope_type is not null
                 or new.creation_scope_project_id is not null
                 or new.creation_decision_event_id is not null then
                raise exception 'partial pre-submit-policy provenance'
                  using errcode='23514';
              end if;
              return null;
            end if;
            select * into reservation from submission_policy_mutation_idempotency_records
              where committed_pre_submit_policy_id=new.id and status='committed';
            actor_id:=new.created_by_actor_profile_id;
            link_id:=new.created_via_identity_link_id;
            grant_id:=new.created_by_admin_role_grant_id;
            service_id:=null; action_value:=new.creation_action_id;
            decision_id:=new.creation_decision_event_id;
            product_project:=new.project_id; product_id:=reservation.committed_policy_id;
          end if;
          if reservation.id is null or product_id is null
             or reservation.actor_profile_id is distinct from actor_id
             or reservation.identity_link_id is distinct from link_id
             or reservation.action_id is distinct from action_value
             or reservation.project_id is distinct from product_project
             or reservation.committed_policy_id is distinct from product_id
             or reservation.service_identity is distinct from service_id then
            raise exception 'submission-policy mutation custody mismatch' using errcode='23514';
          end if;
          select * into evidence from audit_events where id=decision_id;
          if evidence.id is null or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind is distinct from 'actor_profile'
             or evidence.actor_id is distinct from actor_id
             or evidence.matched_grant_id is distinct from grant_id::text
             or evidence.permission_id is distinct from 'project.effective_policy.manage'
             or evidence.action_id is distinct from action_value
             or evidence.resource_type
                is distinct from 'project_submission_artifact_policy_mutation'
             or evidence.resource_id is distinct from product_id
             or evidence.project_id is distinct from reservation.project_id
             or evidence.target_ref_kind is distinct from 'project'
             or evidence.target_ref_id is distinct from reservation.project_id
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or evidence.after_facts->>'resource_context_digest'
                is distinct from reservation.resource_context_digest then
            raise exception 'submission-policy authorization evidence mismatch'
              using errcode='23514';
          end if;
          return null;
        end $$
        """
    )
    for trigger, table in (
        ("submission_policy_product_custody", "submission_artifact_policies"),
        ("effective_submission_policy_custody", "effective_project_submission_artifact_policies"),
        ("pre_submit_policy_custody", "pre_submit_checker_policies"),
        ("submission_policy_replay_custody", "submission_policy_mutation_idempotency_records"),
    ):
        op.execute(
            f"create constraint trigger {trigger} after insert or update on {table} "
            "deferrable initially deferred for each row "
            "execute function validate_submission_policy_authority_custody()"
        )


def downgrade() -> None:
    """Remove the inactive foundation only when no replay/provenance exists."""
    connection = op.get_bind()
    connection.execute(sa.text("lock table audit_events in access exclusive mode"))
    for table in (
        "submission_policy_mutation_idempotency_records",
        "submission_artifact_policies",
        "effective_project_submission_artifact_policies",
        "pre_submit_checker_policies",
    ):
        connection.execute(sa.text(f"lock table {table} in share row exclusive mode"))
    replay_count = connection.execute(
        sa.text("select count(*) from submission_policy_mutation_idempotency_records")
    ).scalar_one()
    provenance_count = connection.execute(
        sa.text(
            "select "
            "(select count(*) from submission_artifact_policies where "
            "created_by_actor_profile_id is not null or approved_by_actor_profile_id is not null) + "
            "(select count(*) from effective_project_submission_artifact_policies where "
            "created_by_actor_profile_id is not null) + "
            "(select count(*) from pre_submit_checker_policies where "
            "created_by_actor_profile_id is not null)"
        )
    ).scalar_one()
    audit_count = connection.execute(
        sa.text(
            "select count(*) from audit_events where "
            "resource_type='project_submission_artifact_policy_mutation'"
        )
    ).scalar_one()
    if replay_count or provenance_count or audit_count:
        raise RuntimeError("cannot downgrade submission-policy authority with evidence")

    for trigger, table in (
        ("submission_policy_replay_custody", "submission_policy_mutation_idempotency_records"),
        ("pre_submit_policy_custody", "pre_submit_checker_policies"),
        ("effective_submission_policy_custody", "effective_project_submission_artifact_policies"),
        ("submission_policy_product_custody", "submission_artifact_policies"),
    ):
        op.execute(f"drop trigger {trigger} on {table}")
    op.execute("drop function validate_submission_policy_authority_custody()")
    op.execute(
        "drop trigger submission_policy_creation_custody on submission_artifact_policies"
    )
    op.execute("drop function validate_submission_policy_creation_custody()")
    for trigger, table in (
        ("pre_submit_policy_provenance_immutable", "pre_submit_checker_policies"),
        (
            "effective_submission_policy_provenance_immutable",
            "effective_project_submission_artifact_policies",
        ),
    ):
        op.execute(f"drop trigger {trigger} on {table}")
    op.execute("drop function protect_submission_policy_output_provenance()")
    op.execute(
        "drop trigger submission_policy_approval_provenance_immutable "
        "on submission_artifact_policies"
    )
    op.execute("drop function protect_submission_policy_approval_provenance()")
    op.execute(
        "drop trigger submission_policy_creation_provenance_immutable "
        "on submission_artifact_policies"
    )
    op.execute("drop function protect_submission_policy_creation_provenance()")

    op.execute(
        "drop trigger trg_submission_policy_replay_no_truncate "
        "on submission_policy_mutation_idempotency_records"
    )
    op.execute("drop function reject_submission_policy_replay_truncate()")
    op.execute(
        "drop trigger trg_submission_policy_replay_immutable "
        "on submission_policy_mutation_idempotency_records"
    )
    op.execute("drop function reject_submission_policy_replay_mutation()")
    op.drop_table("submission_policy_mutation_idempotency_records")

    for table, constraint in (
        ("pre_submit_checker_policies", "ck_pre_submit_policy_authority_shape"),
        (
            "effective_project_submission_artifact_policies",
            "ck_effective_submission_policy_authority_shape",
        ),
        ("submission_artifact_policies", "ck_submission_policy_approval_authority_shape"),
        ("submission_artifact_policies", "ck_submission_policy_creation_authority_shape"),
    ):
        op.drop_constraint(op.f(f"ck_{table}_{constraint}"), table, type_="check")

    for table, prefix, columns, approval in (
        ("pre_submit_checker_policies", "pre_submit_policy", _APPROVAL_OUTPUT_COLUMNS, False),
        (
            "effective_project_submission_artifact_policies",
            "effective_policy",
            _APPROVAL_OUTPUT_COLUMNS,
            False,
        ),
        (
            "submission_artifact_policies",
            "submission_policy",
            _SUBMISSION_APPROVAL_COLUMNS,
            True,
        ),
        (
            "submission_artifact_policies",
            "submission_policy",
            _SUBMISSION_CREATION_COLUMNS,
            False,
        ),
    ):
        stem = "approval" if approval else "creation"
        for suffix in ("actor", "link", "grant", "project", "decision"):
            op.drop_constraint(f"fk_{prefix}_{stem}_{suffix}", table, type_="foreignkey")
        for name, _column_type in reversed(columns):
            op.drop_column(table, name)
    _rewrite_audit_resource(add=False)
