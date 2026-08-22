"""Install immutable unified-compilation projection custody."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_guide_compilation_projections"
down_revision = "0008_guide_compilation_authorized_persistence"
branch_labels = None
depends_on = None

_NEW_RESOURCES = (
    "project_guide_sufficiency_projection",
    "project_submission_artifact_policy_projection",
)


def upgrade() -> None:
    """Create exact component custody and protect its canonical outputs."""
    op.drop_index(
        "uq_guide_sufficiency_reports_verified_snapshot",
        table_name="guide_sufficiency_reports",
    )
    op.create_index(
        "uq_guide_sufficiency_reports_verified_snapshot",
        "guide_sufficiency_reports",
        ["source_snapshot_id", "setup_generation"],
        unique=True,
        postgresql_where=sa.text("project_setup_run_id is not null"),
    )
    op.create_table(
        "project_guide_component_projection_operations",
        sa.Column("operation_id", sa.Uuid(), primary_key=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("component", sa.String(40), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("guide_id", sa.String(36), nullable=False),
        sa.Column("guide_version", sa.String(50), nullable=False),
        sa.Column("source_snapshot_id", sa.String(36), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(71), nullable=False),
        sa.Column("setup_run_id", sa.String(36), nullable=False),
        sa.Column("setup_generation", sa.BigInteger(), nullable=False),
        sa.Column("celery_task_id", sa.String(155), nullable=False),
        sa.Column("source_state_digest", sa.String(71), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("request_operation_id", sa.Uuid(), nullable=False),
        sa.Column("provider_idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("compilation_id", sa.Uuid(), nullable=False),
        sa.Column("result_hash", sa.String(71), nullable=False),
        sa.Column("component_hash", sa.String(71), nullable=False),
        sa.Column("result_schema_version", sa.String(100), nullable=False),
        sa.Column("compilation_agent_name", sa.String(100), nullable=False),
        sa.Column("compilation_agent_version", sa.String(100), nullable=False),
        sa.Column("material_sha256", sa.String(71)),
        sa.Column("material_byte_count", sa.BigInteger(), nullable=False),
        sa.Column("prior_operation_id", sa.Uuid()),
        sa.Column("prior_output_id", sa.Uuid()),
        sa.Column("prior_output_digest", sa.String(71)),
        sa.Column("output_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.String(36)),
        sa.Column("policy_id", sa.String(36)),
        sa.Column("output_digest", sa.String(71), nullable=False),
        sa.Column("facts_digest", sa.String(71), nullable=False),
        sa.Column("authority_resource_digest", sa.String(71), nullable=False),
        sa.Column("actor_profile_id", sa.String(36), nullable=False),
        sa.Column("identity_link_id", sa.String(36), nullable=False),
        sa.Column("service_identity", sa.String(160), nullable=False),
        sa.Column("action_id", sa.String(160), nullable=False),
        sa.Column("permission_id", sa.String(120), nullable=False),
        sa.Column("authorization_decision_event_id", sa.String(36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["guide_id"], ["project_guides.id"]),
        sa.ForeignKeyConstraint(
            ["request_operation_id"],
            ["project_guide_compilation_request_operations.operation_id"],
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id", "project_id", "guide_id", "source_snapshot_id", "setup_run_id", "setup_generation"],
            [
                "project_guide_compilation_attempts.id",
                "project_guide_compilation_attempts.project_id",
                "project_guide_compilation_attempts.guide_id",
                "project_guide_compilation_attempts.source_snapshot_id",
                "project_guide_compilation_attempts.setup_run_id",
                "project_guide_compilation_attempts.setup_generation",
            ],
            name="fk_projection_operation_exact_attempt",
        ),
        sa.ForeignKeyConstraint(
            ["compilation_id", "attempt_id"],
            ["project_guide_compilations.id", "project_guide_compilations.attempt_id"],
            name="fk_projection_operation_exact_compilation",
        ),
        sa.ForeignKeyConstraint(
            ["setup_run_id", "project_id", "guide_id", "source_snapshot_id", "setup_generation"],
            [
                "project_setup_runs.id",
                "project_setup_runs.project_id",
                "project_setup_runs.guide_id",
                "project_setup_runs.source_snapshot_id",
                "project_setup_runs.setup_generation",
            ],
            name="fk_projection_operation_exact_setup",
        ),
        sa.ForeignKeyConstraint(
            ["identity_link_id", "actor_profile_id"],
            ["actor_identity_links.id", "actor_identity_links.actor_profile_id"],
            name="fk_projection_operation_actor_link",
        ),
        sa.ForeignKeyConstraint(["report_id"], ["guide_sufficiency_reports.id"]),
        sa.ForeignKeyConstraint(["policy_id"], ["submission_artifact_policies.id"]),
        sa.ForeignKeyConstraint(
            ["prior_operation_id"],
            ["project_guide_component_projection_operations.operation_id"],
        ),
        sa.ForeignKeyConstraint(
            ["authorization_decision_event_id"], ["audit_events.id"]
        ),
        sa.UniqueConstraint(
            "setup_run_id", "setup_generation", "component",
            name="uq_projection_operation_setup_component",
        ),
        sa.UniqueConstraint(
            "compilation_id", "component",
            name="uq_projection_operation_compilation_component",
        ),
        sa.UniqueConstraint("output_id", name="uq_projection_operation_output"),
        sa.UniqueConstraint(
            "authorization_decision_event_id",
            name="uq_projection_operation_decision_event",
        ),
        sa.CheckConstraint(
            "component in ('guide_sufficiency','submission_artifact_policy')",
            name="ck_projection_operation_component",
        ),
        sa.CheckConstraint(
            "setup_generation > 0 and material_byte_count >= 0",
            name="ck_projection_operation_positive_values",
        ),
        sa.CheckConstraint(
            "source_snapshot_hash ~ '^sha256:[0-9a-f]{64}$' and "
            "source_state_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "result_hash ~ '^sha256:[0-9a-f]{64}$' and "
            "component_hash ~ '^sha256:[0-9a-f]{64}$' and "
            "output_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "facts_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "authority_resource_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "(material_sha256 is null or material_sha256 ~ '^sha256:[0-9a-f]{64}$')",
            name="ck_projection_operation_hashes",
        ),
        sa.CheckConstraint(
            "(component='guide_sufficiency' and prior_operation_id is null and "
            "prior_output_id is null and prior_output_digest is null and "
            "report_id is not null and policy_id is null and material_sha256 is not null) or "
            "(component='submission_artifact_policy' and prior_operation_id is not null and "
            "prior_output_id is not null and prior_output_digest is not null and "
            "report_id is null and policy_id is not null and material_sha256 is null)",
            name="ck_projection_operation_component_shape",
        ),
    )
    _extend_audit_resource_constraint(_NEW_RESOURCES)
    _install_digest_functions()
    _install_guards()
    _install_submission_policy_creation_guard(allow_projection=True)
    _install_submission_policy_product_trigger(allow_projection=True)


def _extend_audit_resource_constraint(resources: tuple[str, ...]) -> None:
    connection = op.get_bind()
    definition = connection.execute(
        sa.text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='audit_events'::regclass "
            "and conname='ck_audit_events_authority_privacy_bounds'"
        )
    ).scalar_one()
    anchor = "('project_guide_compilation_request'::character varying)::text]))"
    additions = "".join(
        f", ('{resource}'::character varying)::text" for resource in resources
    )
    replacement = (
        "('project_guide_compilation_request'::character varying)::text"
        + additions
        + "]))"
    )
    if anchor not in definition:
        raise RuntimeError("audit resource constraint shape changed")
    amended = definition.replace(anchor, replacement, 1)
    op.execute(
        "alter table audit_events drop constraint "
        "ck_audit_events_authority_privacy_bounds"
    )
    op.execute(
        "alter table audit_events add constraint "
        "ck_audit_events_authority_privacy_bounds " + amended
    )


def _install_digest_functions() -> None:
    op.execute(
        r"""
        create function project_guide_projection_facts_digest(
          item project_guide_component_projection_operations
        ) returns text immutable strict language sql as $$
          select 'sha256:' || encode(sha256(convert_to(
            case when item.component='guide_sufficiency' then
              '{"domain":"workstream.project_guide_sufficiency_projection.facts.v1","facts":{' ||
              '"attempt_id":' || to_json(item.attempt_id::text)::text || ',' ||
              '"celery_task_id":' || to_json(item.celery_task_id)::text || ',' ||
              '"compilation_agent_name":' || to_json(item.compilation_agent_name)::text || ',' ||
              '"compilation_agent_version":' || to_json(item.compilation_agent_version)::text || ',' ||
              '"compilation_id":' || to_json(item.compilation_id::text)::text || ',' ||
              '"component_hash":' || to_json(item.component_hash)::text || ',' ||
              '"guide_id":' || to_json(item.guide_id)::text || ',' ||
              '"guide_version":' || to_json(item.guide_version)::text || ',' ||
              '"material_byte_count":' || item.material_byte_count::text || ',' ||
              '"material_sha256":' || to_json(item.material_sha256)::text || ',' ||
              '"project_id":' || to_json(item.project_id)::text || ',' ||
              '"provider_idempotency_key":' ||
                to_json(item.provider_idempotency_key::text)::text || ',' ||
              '"report_content_digest":' || to_json(item.output_digest)::text || ',' ||
              '"report_id":' || to_json(item.output_id::text)::text || ',' ||
              '"request_operation_id":' ||
                to_json(item.request_operation_id::text)::text || ',' ||
              '"result_hash":' || to_json(item.result_hash)::text || ',' ||
              '"result_schema_version":' || to_json(item.result_schema_version)::text || ',' ||
              '"setup_generation":' || item.setup_generation::text || ',' ||
              '"setup_run_id":' || to_json(item.setup_run_id)::text || ',' ||
              '"source_snapshot_hash":' || to_json(item.source_snapshot_hash)::text || ',' ||
              '"source_snapshot_id":' || to_json(item.source_snapshot_id)::text || ',' ||
              '"source_state_digest":' || to_json(item.source_state_digest)::text || '}}'
            else
              '{"domain":"workstream.project_submission_artifact_policy_projection.facts.v1","facts":{' ||
              '"attempt_id":' || to_json(item.attempt_id::text)::text || ',' ||
              '"celery_task_id":' || to_json(item.celery_task_id)::text || ',' ||
              '"compilation_agent_name":' || to_json(item.compilation_agent_name)::text || ',' ||
              '"compilation_agent_version":' || to_json(item.compilation_agent_version)::text || ',' ||
              '"compilation_id":' || to_json(item.compilation_id::text)::text || ',' ||
              '"component_hash":' || to_json(item.component_hash)::text || ',' ||
              '"guide_id":' || to_json(item.guide_id)::text || ',' ||
              '"guide_version":' || to_json(item.guide_version)::text || ',' ||
              '"policy_content_digest":' || to_json(item.output_digest)::text || ',' ||
              '"policy_id":' || to_json(item.output_id::text)::text || ',' ||
              '"prior_operation_id":' || to_json(item.prior_operation_id::text)::text || ',' ||
              '"project_id":' || to_json(item.project_id)::text || ',' ||
              '"provider_idempotency_key":' ||
                to_json(item.provider_idempotency_key::text)::text || ',' ||
              '"request_operation_id":' ||
                to_json(item.request_operation_id::text)::text || ',' ||
              '"result_hash":' || to_json(item.result_hash)::text || ',' ||
              '"result_schema_version":' || to_json(item.result_schema_version)::text || ',' ||
              '"setup_generation":' || item.setup_generation::text || ',' ||
              '"setup_run_id":' || to_json(item.setup_run_id)::text || ',' ||
              '"source_snapshot_hash":' || to_json(item.source_snapshot_hash)::text || ',' ||
              '"source_snapshot_id":' || to_json(item.source_snapshot_id)::text || ',' ||
              '"source_state_digest":' || to_json(item.source_state_digest)::text || ',' ||
              '"sufficiency_report_digest":' || to_json(item.prior_output_digest)::text || ',' ||
              '"sufficiency_report_id":' || to_json(item.prior_output_id::text)::text || '}}'
            end,
            'UTF8')), 'hex')
        $$
        """
    )
    op.execute(
        r"""
        create function project_guide_projection_authority_digest(
          item project_guide_component_projection_operations
        ) returns text immutable strict language sql as $$
          select 'sha256:' || encode(sha256(convert_to(
            '{"domain":' || to_json(case
              when item.component='guide_sufficiency' then
                'workstream.project_guide_sufficiency_projection.authority.v1'
              else
                'workstream.project_submission_artifact_policy_projection.authority.v1'
              end)::text || ',"facts":{' ||
            '"action_id":' || to_json(item.action_id)::text || ',' ||
            '"actor_profile_id":' || to_json(item.actor_profile_id)::text || ',' ||
            '"facts_digest":' || to_json(item.facts_digest)::text || ',' ||
            '"identity_link_id":' || to_json(item.identity_link_id)::text || ',' ||
            '"permission_id":' || to_json(item.permission_id)::text || ',' ||
            '"resource_id":' || to_json(item.operation_id::text)::text || ',' ||
            '"resource_type":' || to_json(case
              when item.component='guide_sufficiency' then
                'project_guide_sufficiency_projection'
              else 'project_submission_artifact_policy_projection' end)::text || ',' ||
            '"scope_project_id":' || to_json(item.project_id)::text || ',' ||
            '"service_identity":' || to_json(item.service_identity)::text || '}}',
            'UTF8')), 'hex')
        $$
        """
    )


def _install_guards() -> None:
    op.execute(
        """
        create function guard_project_guide_component_projection_operation()
        returns trigger language plpgsql as $$
        declare evidence audit_events%rowtype;
        begin
          select * into evidence from audit_events
            where id=new.authorization_decision_event_id;
          if new.facts_digest is distinct from
                project_guide_projection_facts_digest(new)
             or new.authority_resource_digest is distinct from
                project_guide_projection_authority_digest(new) then
            raise exception 'projection digest custody is invalid'
              using errcode='23514';
          end if;
          if evidence.id is null
             or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.action_id is distinct from new.action_id
             or evidence.permission_id is distinct from new.permission_id
             or evidence.resource_id is distinct from new.operation_id::text
             or evidence.project_id is distinct from new.project_id
             or evidence.actor_id is distinct from new.actor_profile_id
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or evidence.after_facts->>'resource_context_digest'
                  is distinct from new.authority_resource_digest
             or new.service_identity is distinct from 'workstream.project.setup'
             or (new.component='guide_sufficiency' and
                 (new.action_id is distinct from 'project.guide_sufficiency.run'
                  or new.permission_id is distinct from 'project.guide.manage'
                  or evidence.resource_type is distinct from
                     'project_guide_sufficiency_projection'))
             or (new.component='submission_artifact_policy' and
                 (new.action_id is distinct from
                     'project.submission_artifact_policy.derive'
                  or new.permission_id is distinct from
                     'project.effective_policy.manage'
                  or evidence.resource_type is distinct from
                     'project_submission_artifact_policy_projection')) then
            raise exception 'projection authority custody is invalid'
              using errcode='23514';
          end if;
          return new;
        end; $$
        """
    )
    op.execute(
        """
        create function reject_project_guide_projection_change()
        returns trigger language plpgsql as $$ begin
          raise exception 'project guide projection custody is immutable'
            using errcode='55000';
        end; $$
        """
    )
    op.execute(
        """
        create function guard_compilation_projection_business_change()
        returns trigger language plpgsql as $$ begin
          if tg_table_name='guide_sufficiency_reports' and exists(
            select 1 from project_guide_component_projection_operations
              where report_id=old.id
          ) and ((to_jsonb(new)-'warnings_acknowledged_by_role'-'warnings_acknowledged_by_actor'
                   -'warnings_acknowledged_at'-'acknowledgement_note'
                   -'warnings_acknowledged_by_actor_profile_id'
                   -'warnings_acknowledged_via_identity_link_id'
                   -'warnings_acknowledged_by_admin_role_grant_id'
                   -'warning_acknowledgement_scope_type'
                   -'warning_acknowledgement_scope_project_id'
                   -'warning_acknowledgement_action_id'
                   -'warning_acknowledgement_decision_event_id') is distinct from
                  (to_jsonb(old)-'warnings_acknowledged_by_role'-'warnings_acknowledged_by_actor'
                   -'warnings_acknowledged_at'-'acknowledgement_note'
                   -'warnings_acknowledged_by_actor_profile_id'
                   -'warnings_acknowledged_via_identity_link_id'
                   -'warnings_acknowledged_by_admin_role_grant_id'
                   -'warning_acknowledgement_scope_type'
                   -'warning_acknowledgement_scope_project_id'
                   -'warning_acknowledgement_action_id'
                   -'warning_acknowledgement_decision_event_id')) then
            raise exception 'projected sufficiency content is immutable' using errcode='55000';
          end if;
          if tg_table_name='submission_artifact_policies' and exists(
            select 1 from project_guide_component_projection_operations
              where policy_id=old.id
          ) and ((to_jsonb(new)-'lifecycle_status'-'approved_by_role'-'approved_by_actor'
                   -'approved_by_actor_profile_id'-'approved_via_identity_link_id'
                   -'approved_by_admin_role_grant_id'-'approval_scope_type'
                   -'approval_scope_project_id'-'approval_action_id'
                   -'approval_decision_event_id'-'approved_at'-'supersedes_policy_id'
                   -'superseded_at'-'updated_at') is distinct from
                  (to_jsonb(old)-'lifecycle_status'-'approved_by_role'-'approved_by_actor'
                   -'approved_by_actor_profile_id'-'approved_via_identity_link_id'
                   -'approved_by_admin_role_grant_id'-'approval_scope_type'
                   -'approval_scope_project_id'-'approval_action_id'
                   -'approval_decision_event_id'-'approved_at'-'supersedes_policy_id'
                   -'superseded_at'-'updated_at')) then
            raise exception 'projected policy content is immutable' using errcode='55000';
          end if;
          return new;
        end; $$
        """
    )
    op.execute(
        """
        create function reject_compilation_projection_business_truncate()
        returns trigger language plpgsql as $$ begin
          if tg_table_name='guide_sufficiency_reports' and exists(
            select 1 from project_guide_component_projection_operations
              where report_id is not null
          ) then raise exception 'projected sufficiency content is immutable'
            using errcode='55000';
          end if;
          if tg_table_name='submission_artifact_policies' and exists(
            select 1 from project_guide_component_projection_operations
              where policy_id is not null
          ) then raise exception 'projected policy content is immutable'
            using errcode='55000';
          end if;
          if tg_table_name='guide_sufficiency_report_source_usages' and exists(
            select 1 from project_guide_component_projection_operations
              where report_id is not null
          ) then raise exception 'projected source usage is immutable'
            using errcode='55000';
          end if;
          return null;
        end; $$
        """
    )
    op.execute(
        """
        create function reject_compilation_projection_business_delete()
        returns trigger language plpgsql as $$ begin
          if tg_table_name='guide_sufficiency_reports' and exists(
            select 1 from project_guide_component_projection_operations where report_id=old.id
          ) then raise exception 'projected sufficiency content is immutable' using errcode='55000';
          end if;
          if tg_table_name='submission_artifact_policies' and exists(
            select 1 from project_guide_component_projection_operations where policy_id=old.id
          ) then raise exception 'projected policy content is immutable' using errcode='55000';
          end if;
          if tg_table_name='guide_sufficiency_report_source_usages' and exists(
            select 1 from project_guide_component_projection_operations where report_id=old.report_id
          ) then raise exception 'projected source usage is immutable' using errcode='55000';
          end if;
          return old;
        end; $$
        """
    )
    for statement in (
        "create trigger projection_operation_insert_guard before insert on project_guide_component_projection_operations for each row execute function guard_project_guide_component_projection_operation()",
        "create trigger projection_operation_change_guard before update or delete on project_guide_component_projection_operations for each row execute function reject_project_guide_projection_change()",
        "create trigger projection_operation_truncate_guard before truncate on project_guide_component_projection_operations execute function reject_project_guide_projection_change()",
        "create trigger projected_report_update_guard before update on guide_sufficiency_reports for each row execute function guard_compilation_projection_business_change()",
        "create trigger projected_policy_update_guard before update on submission_artifact_policies for each row execute function guard_compilation_projection_business_change()",
        "create trigger projected_report_delete_guard before delete on guide_sufficiency_reports for each row execute function reject_compilation_projection_business_delete()",
        "create trigger projected_policy_delete_guard before delete on submission_artifact_policies for each row execute function reject_compilation_projection_business_delete()",
        "create trigger projected_usage_delete_guard before update or delete on guide_sufficiency_report_source_usages for each row execute function reject_compilation_projection_business_delete()",
        "create trigger projected_report_truncate_guard before truncate on guide_sufficiency_reports execute function reject_compilation_projection_business_truncate()",
        "create trigger projected_policy_truncate_guard before truncate on submission_artifact_policies execute function reject_compilation_projection_business_truncate()",
        "create trigger projected_usage_truncate_guard before truncate on guide_sufficiency_report_source_usages execute function reject_compilation_projection_business_truncate()",
    ):
        op.execute(statement)


def _install_submission_policy_creation_guard(*, allow_projection: bool) -> None:
    projection_branch = ""
    if allow_projection:
        projection_branch = """
          if new.derivation_source='unified_compilation' then
            select * into projection
              from project_guide_component_projection_operations
              where policy_id=new.id
                and component='submission_artifact_policy';
            if projection.operation_id is null
               or projection.output_id::text is distinct from new.id
               or projection.project_id is distinct from new.project_id
               or projection.guide_id is distinct from new.guide_id
               or projection.guide_version is distinct from new.guide_version
               or projection.source_snapshot_id is distinct from new.source_snapshot_id
               or projection.source_snapshot_hash is distinct from new.source_snapshot_hash
               or projection.actor_profile_id
                    is distinct from new.created_by_actor_profile_id
               or projection.identity_link_id
                    is distinct from new.created_via_identity_link_id
               or projection.service_identity
                    is distinct from new.created_by_service_identity
               or projection.action_id is distinct from new.creation_action_id
               or projection.permission_id is distinct from
                    'project.effective_policy.manage'
               or projection.authorization_decision_event_id
                    is distinct from new.creation_decision_event_id then
              raise exception 'submission-policy projection custody mismatch'
                using errcode='23514';
            end if;
            return null;
          end if;
        """
    projection_declaration = (
        "projection project_guide_component_projection_operations%rowtype;"
        if allow_projection
        else ""
    )
    op.execute(
        f"""
        create or replace function validate_submission_policy_creation_custody()
        returns trigger language plpgsql as $$
        declare
          reservation submission_policy_mutation_idempotency_records%rowtype;
          evidence audit_events%rowtype;
          {projection_declaration}
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
          {projection_branch}
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
            raise exception 'submission-policy creation custody mismatch'
              using errcode='23514';
          end if;
          select * into evidence from audit_events
            where id=new.creation_decision_event_id;
          if evidence.id is null
             or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind is distinct from 'actor_profile'
             or evidence.actor_id is distinct from new.created_by_actor_profile_id
             or evidence.matched_grant_id
                is distinct from new.created_by_admin_role_grant_id::text
             or evidence.permission_id is distinct from
                'project.effective_policy.manage'
             or evidence.action_id is distinct from new.creation_action_id
             or evidence.resource_type is distinct from
                'project_submission_artifact_policy_mutation'
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
        end; $$
        """
    )


def _install_submission_policy_product_trigger(*, allow_projection: bool) -> None:
    op.execute(
        "drop trigger submission_policy_product_custody "
        "on submission_artifact_policies"
    )
    condition = (
        " when (new.derivation_source <> 'unified_compilation' or "
        "new.approval_action_id is not null)"
        if allow_projection
        else ""
    )
    op.execute(
        "create constraint trigger submission_policy_product_custody "
        "after insert or update on submission_artifact_policies "
        "deferrable initially deferred for each row"
        + condition
        + " execute function validate_submission_policy_authority_custody()"
    )


def downgrade() -> None:
    """Remove empty projection custody only."""
    connection = op.get_bind()
    protected = connection.execute(
        sa.text(
            "select exists(select 1 from project_guide_component_projection_operations) "
            "or exists(select 1 from submission_artifact_policies "
            "where derivation_source='unified_compilation') "
            "or exists(select 1 from guide_sufficiency_reports r where "
            "project_setup_run_id is not null and exists(select 1 from "
            "guide_sufficiency_reports other_report where "
            "other_report.source_snapshot_id=r.source_snapshot_id "
            "and other_report.project_setup_run_id is not null "
            "and other_report.id<>r.id))"
        )
    ).scalar_one()
    if protected:
        raise RuntimeError("guide projection custody is non-empty; downgrade refused")
    for trigger, table in (
        ("projected_usage_truncate_guard", "guide_sufficiency_report_source_usages"),
        ("projected_policy_truncate_guard", "submission_artifact_policies"),
        ("projected_report_truncate_guard", "guide_sufficiency_reports"),
        ("projected_usage_delete_guard", "guide_sufficiency_report_source_usages"),
        ("projected_policy_delete_guard", "submission_artifact_policies"),
        ("projected_report_delete_guard", "guide_sufficiency_reports"),
        ("projected_policy_update_guard", "submission_artifact_policies"),
        ("projected_report_update_guard", "guide_sufficiency_reports"),
        ("projection_operation_truncate_guard", "project_guide_component_projection_operations"),
        ("projection_operation_change_guard", "project_guide_component_projection_operations"),
        ("projection_operation_insert_guard", "project_guide_component_projection_operations"),
    ):
        op.execute(f"drop trigger {trigger} on {table}")
    op.execute("drop function reject_compilation_projection_business_delete")
    op.execute("drop function reject_compilation_projection_business_truncate")
    op.execute("drop function guard_compilation_projection_business_change")
    op.execute("drop function reject_project_guide_projection_change")
    op.execute("drop function guard_project_guide_component_projection_operation")
    op.execute("drop function project_guide_projection_authority_digest")
    op.execute("drop function project_guide_projection_facts_digest")
    _install_submission_policy_product_trigger(allow_projection=False)
    _install_submission_policy_creation_guard(allow_projection=False)
    _remove_audit_resources(_NEW_RESOURCES)
    op.drop_table("project_guide_component_projection_operations")
    op.drop_index(
        "uq_guide_sufficiency_reports_verified_snapshot",
        table_name="guide_sufficiency_reports",
    )
    op.create_index(
        "uq_guide_sufficiency_reports_verified_snapshot",
        "guide_sufficiency_reports",
        ["source_snapshot_id"],
        unique=True,
        postgresql_where=sa.text("project_setup_run_id is not null"),
    )


def _remove_audit_resources(resources: tuple[str, ...]) -> None:
    connection = op.get_bind()
    definition = connection.execute(
        sa.text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='audit_events'::regclass "
            "and conname='ck_audit_events_authority_privacy_bounds'"
        )
    ).scalar_one()
    suffix = "".join(f", ('{resource}'::character varying)::text" for resource in resources)
    amended = definition.replace(suffix, "", 1)
    if amended == definition:
        raise RuntimeError("audit projection resources are absent")
    op.execute(
        "alter table audit_events drop constraint "
        "ck_audit_events_authority_privacy_bounds"
    )
    op.execute(
        "alter table audit_events add constraint "
        "ck_audit_events_authority_privacy_bounds " + amended
    )
