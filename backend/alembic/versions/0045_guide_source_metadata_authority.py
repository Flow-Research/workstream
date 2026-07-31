"""activate transaction-bound guide source-metadata authority

Revision ID: 0045_guide_metadata_authority
Revises: 0044_project_create_authority
Create Date: 2026-07-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0045_guide_metadata_authority"
down_revision = "0044_project_create_authority"
branch_labels = depends_on = None

_ACTIONS = "'project.guide.create','project.guide.update','project.guide_source_snapshot.create'"


def _authority_columns(table: str, *, prefix: str) -> None:
    metadata_prefix = {
        "last_mutated": "last_mutation",
        "created": "creation",
        "authorized": "authorization",
    }[prefix]
    op.add_column(table, sa.Column(f"{prefix}_by_actor_profile_id", sa.String(36)))
    op.add_column(table, sa.Column(f"{prefix}_via_identity_link_id", sa.String(36)))
    op.add_column(table, sa.Column(f"{prefix}_by_admin_role_grant_id", sa.Uuid()))
    op.add_column(table, sa.Column(f"{metadata_prefix}_scope_type", sa.String(16)))
    op.add_column(table, sa.Column(f"{metadata_prefix}_scope_project_id", sa.String(36)))
    op.add_column(table, sa.Column(f"{metadata_prefix}_action_id", sa.String(160)))
    decision_column = (
        "last_authorization_decision_event_id"
        if prefix == "last_mutated"
        else "authorization_decision_event_id"
    )
    op.add_column(table, sa.Column(decision_column, sa.String(36)))
    for suffix, target, target_column in (
        ("actor", "actor_profiles", "id"),
        ("identity_link", "actor_identity_links", "id"),
        ("admin_grant", "admin_role_grants", "id"),
        ("decision", "audit_events", "id"),
    ):
        column = {
            "actor": f"{prefix}_by_actor_profile_id",
            "identity_link": f"{prefix}_via_identity_link_id",
            "admin_grant": f"{prefix}_by_admin_role_grant_id",
            "decision": decision_column,
        }[suffix]
        op.create_foreign_key(
            f"fk_{table}_{prefix}_{suffix}", table, target, [column], [target_column]
        )


def _drop_authority_columns(table: str, *, prefix: str) -> None:
    metadata_prefix = {
        "last_mutated": "last_mutation",
        "created": "creation",
        "authorized": "authorization",
    }[prefix]
    for suffix in ("decision", "admin_grant", "identity_link", "actor"):
        op.drop_constraint(f"fk_{table}_{prefix}_{suffix}", table, type_="foreignkey")
    decision_column = (
        "last_authorization_decision_event_id"
        if prefix == "last_mutated"
        else "authorization_decision_event_id"
    )
    for column in (
        decision_column,
        f"{metadata_prefix}_action_id",
        f"{metadata_prefix}_scope_project_id",
        f"{metadata_prefix}_scope_type",
        f"{prefix}_by_admin_role_grant_id",
        f"{prefix}_via_identity_link_id",
        f"{prefix}_by_actor_profile_id",
    ):
        op.drop_column(table, column)


def upgrade() -> None:
    """Install nullable history and mandatory custody for every new mutation."""
    _authority_columns("project_guides", prefix="last_mutated")
    op.add_column("project_guides", sa.Column("mutation_generation", sa.Integer()))
    op.create_check_constraint(
        "guide_mutation_authority_shape",
        "project_guides",
        "(mutation_generation is null and last_mutated_by_actor_profile_id is null "
        "and last_mutated_via_identity_link_id is null "
        "and last_mutated_by_admin_role_grant_id is null "
        "and last_mutation_scope_type is null and last_mutation_scope_project_id is null "
        "and last_mutation_action_id is null and last_authorization_decision_event_id is null) or "
        "(mutation_generation > 0 and last_mutated_by_actor_profile_id is not null "
        "and last_mutated_via_identity_link_id is not null "
        "and last_mutated_by_admin_role_grant_id is not null "
        "and last_mutation_scope_type in ('system','project') "
        "and ((last_mutation_scope_type='system' and last_mutation_scope_project_id is null) "
        "or (last_mutation_scope_type='project' and last_mutation_scope_project_id=project_id)) "
        f"and last_mutation_action_id in ({_ACTIONS}) "
        "and last_authorization_decision_event_id is not null)",
    )

    _authority_columns("guide_source_snapshots", prefix="created")
    op.add_column("guide_source_snapshots", sa.Column("creation_generation", sa.Integer()))
    op.create_check_constraint(
        "source_snapshot_creation_authority_shape",
        "guide_source_snapshots",
        "(creation_generation is null and created_by_actor_profile_id is null "
        "and created_via_identity_link_id is null and created_by_admin_role_grant_id is null "
        "and creation_scope_type is null and creation_scope_project_id is null "
        "and creation_action_id is null and authorization_decision_event_id is null) or "
        "(creation_generation > 0 and created_by_actor_profile_id is not null "
        "and created_via_identity_link_id is not null "
        "and created_by_admin_role_grant_id is not null "
        "and creation_scope_type in ('system','project') "
        "and ((creation_scope_type='system' and creation_scope_project_id is null) "
        "or (creation_scope_type='project' and creation_scope_project_id=project_id)) "
        "and creation_action_id='project.guide_source_snapshot.create' "
        "and authorization_decision_event_id is not null)",
    )

    _authority_columns("project_setup_runs", prefix="authorized")
    op.create_check_constraint(
        "setup_run_authority_shape",
        "project_setup_runs",
        "(authorized_by_actor_profile_id is null and authorized_via_identity_link_id is null "
        "and authorized_by_admin_role_grant_id is null and authorization_scope_type is null "
        "and authorization_scope_project_id is null and authorization_action_id is null "
        "and authorization_decision_event_id is null) or "
        "(authorized_by_actor_profile_id is not null "
        "and authorized_via_identity_link_id is not null "
        "and authorized_by_admin_role_grant_id is not null "
        "and authorization_scope_type in ('system','project') "
        "and ((authorization_scope_type='system' and authorization_scope_project_id is null) "
        "or (authorization_scope_type='project' and authorization_scope_project_id=project_id)) "
        "and authorization_action_id='project.guide_source_snapshot.create' "
        "and authorization_decision_event_id is not null)",
    )

    op.create_table(
        "guide_mutation_idempotency_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "actor_profile_id", sa.String(36), sa.ForeignKey("actor_profiles.id"), nullable=False
        ),
        sa.Column(
            "identity_link_id",
            sa.String(36),
            sa.ForeignKey("actor_identity_links.id"),
            nullable=False,
        ),
        sa.Column("action_id", sa.String(160), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("resource_context_digest", sa.String(71), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column("operation_generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("response_json", sa.JSON()),
        sa.Column("setup_run_id", sa.String(36), sa.ForeignKey("project_setup_runs.id")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "actor_profile_id",
            "action_id",
            "idempotency_key",
            name="uq_guide_mutation_replay_namespace",
        ),
        sa.UniqueConstraint("operation_id", name="uq_guide_mutation_operation_identity"),
        sa.CheckConstraint(f"action_id in ({_ACTIONS})", name="ck_guide_mutation_action"),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'", name="ck_guide_mutation_request_digest"
        ),
        sa.CheckConstraint(
            "resource_context_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_guide_mutation_resource_context_digest",
        ),
        sa.CheckConstraint("operation_generation > 0", name="ck_guide_mutation_generation"),
        sa.CheckConstraint("status in ('pending','committed')", name="ck_guide_mutation_status"),
        sa.CheckConstraint(
            "(status='pending' and response_json is null and committed_at is null and setup_run_id is null) or "
            "(status='committed' and response_json is not null and committed_at is not null)",
            name="ck_guide_mutation_state_shape",
        ),
    )
    op.execute(
        """
        create function guard_guide_mutation_idempotency() returns trigger
        language plpgsql as $$ begin
          if tg_op='INSERT' then
            if new.status<>'pending' then raise exception 'guide mutation must begin pending' using errcode='23514'; end if;
            return new;
          elsif tg_op='DELETE' then
            raise exception 'guide mutation custody is immutable' using errcode='55000';
          end if;
          if new is not distinct from old then return new; end if;
          if old.status<>'pending' or new.status<>'committed'
             or (new.id,new.actor_profile_id,new.identity_link_id,new.action_id,new.idempotency_key,
                 new.request_digest,new.resource_context_digest,new.operation_id,new.project_id,new.resource_id,
                 new.operation_generation,new.created_at)
                is distinct from
                (old.id,old.actor_profile_id,old.identity_link_id,old.action_id,old.idempotency_key,
                 old.request_digest,old.resource_context_digest,old.operation_id,old.project_id,old.resource_id,
                 old.operation_generation,old.created_at) then
            raise exception 'invalid guide mutation custody transition' using errcode='23514';
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        "create trigger guide_mutation_idempotency_guard before insert or update or delete "
        "on guide_mutation_idempotency_records for each row execute function guard_guide_mutation_idempotency()"
    )
    op.execute(
        """
        create function reject_guide_mutation_idempotency_truncate() returns trigger
        language plpgsql as $$ begin
          raise exception 'guide mutation custody is immutable' using errcode='55000';
        end $$
        """
    )
    op.execute(
        "create trigger guide_mutation_idempotency_reject_truncate before truncate "
        "on guide_mutation_idempotency_records execute function reject_guide_mutation_idempotency_truncate()"
    )
    op.execute(
        """
        create function guard_guide_lineage_and_lifecycle() returns trigger
        language plpgsql as $$ begin
          if (new.id,new.project_id,new.version)
             is distinct from (old.id,old.project_id,old.version) then
            raise exception 'guide identity and lineage are immutable' using errcode='23514';
          end if;
          if (new.status,new.approved_by,new.effective_at,new.superseded_at)
             is distinct from (old.status,old.approved_by,old.effective_at,old.superseded_at) then
            raise exception 'guide lifecycle mutation requires activation authority'
              using errcode='23514';
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        "create trigger guide_lineage_lifecycle_guard before update on project_guides "
        "for each row execute function guard_guide_lineage_and_lifecycle()"
    )
    op.execute(
        """
        create function validate_guide_mutation_custody() returns trigger
        language plpgsql as $$
        declare reservation guide_mutation_idempotency_records%rowtype;
                evidence audit_events%rowtype;
                actor_id text; link_id text; grant_id uuid; action_value text;
                scope_type text; scope_project text; decision_id text;
                product_project text; product_resource text; product_generation integer;
        begin
          if tg_table_name='guide_mutation_idempotency_records' then
            select * into reservation from guide_mutation_idempotency_records where id=new.id;
            if reservation.status<>'committed' then
              raise exception 'pending guide mutation custody cannot commit' using errcode='23514';
            end if;
            if reservation.action_id in ('project.guide.create','project.guide.update') then
              select last_mutated_by_actor_profile_id,last_mutated_via_identity_link_id,
                     last_mutated_by_admin_role_grant_id,last_mutation_action_id,
                     last_mutation_scope_type,last_mutation_scope_project_id,
                     last_authorization_decision_event_id,project_id,id,mutation_generation
                into actor_id,link_id,grant_id,action_value,scope_type,scope_project,
                     decision_id,product_project,product_resource,product_generation
                from project_guides where id=reservation.resource_id;
            else
              select created_by_actor_profile_id,created_via_identity_link_id,
                     created_by_admin_role_grant_id,creation_action_id,
                     creation_scope_type,creation_scope_project_id,
                     authorization_decision_event_id,project_id,id,creation_generation
                into actor_id,link_id,grant_id,action_value,scope_type,scope_project,
                     decision_id,product_project,product_resource,product_generation
                from guide_source_snapshots where id=reservation.resource_id;
            end if;
          elsif tg_table_name='project_guides' then
            if tg_op='UPDATE'
               and (new.content_markdown is distinct from old.content_markdown
                    or new.change_summary is distinct from old.change_summary)
               and (new.mutation_generation is not distinct from old.mutation_generation
                    or new.last_authorization_decision_event_id
                       is not distinct from old.last_authorization_decision_event_id) then
              raise exception 'guide content mutation requires fresh custody' using errcode='23514';
            end if;
            if new.mutation_generation is null then
              if tg_op='INSERT' then
                raise exception 'new guides require mutation authority' using errcode='23514';
              end if;
              return null;
            end if;
            actor_id:=new.last_mutated_by_actor_profile_id;
            link_id:=new.last_mutated_via_identity_link_id;
            grant_id:=new.last_mutated_by_admin_role_grant_id;
            action_value:=new.last_mutation_action_id;
            scope_type:=new.last_mutation_scope_type;
            scope_project:=new.last_mutation_scope_project_id;
            decision_id:=new.last_authorization_decision_event_id;
            product_project:=new.project_id; product_resource:=new.id;
            product_generation:=new.mutation_generation;
            select * into reservation from guide_mutation_idempotency_records
              where resource_id=new.id and action_id=new.last_mutation_action_id
                and operation_generation=new.mutation_generation and status='committed';
          elsif tg_table_name='guide_source_snapshots' then
            if tg_op='UPDATE'
               and (new.project_id,new.guide_id,new.guide_version,
                    new.manifest_schema_version,new.manifest_json::jsonb,new.bundle_hash,new.captured_by)
                   is distinct from
                   (old.project_id,old.guide_id,old.guide_version,
                    old.manifest_schema_version,old.manifest_json::jsonb,old.bundle_hash,old.captured_by) then
              raise exception 'guide source snapshot content is immutable' using errcode='23514';
            end if;
            if new.creation_generation is null then
              raise exception 'new source snapshots require creation authority' using errcode='23514';
            end if;
            actor_id:=new.created_by_actor_profile_id;
            link_id:=new.created_via_identity_link_id;
            grant_id:=new.created_by_admin_role_grant_id;
            action_value:=new.creation_action_id;
            scope_type:=new.creation_scope_type;
            scope_project:=new.creation_scope_project_id;
            decision_id:=new.authorization_decision_event_id;
            product_project:=new.project_id; product_resource:=new.id;
            product_generation:=new.creation_generation;
            select * into reservation from guide_mutation_idempotency_records
              where resource_id=new.id and action_id='project.guide_source_snapshot.create'
                and operation_generation=new.creation_generation and status='committed';
          else
            if new.authorization_action_id is null then return null; end if;
            actor_id:=new.authorized_by_actor_profile_id;
            link_id:=new.authorized_via_identity_link_id;
            grant_id:=new.authorized_by_admin_role_grant_id;
            action_value:=new.authorization_action_id;
            scope_type:=new.authorization_scope_type;
            scope_project:=new.authorization_scope_project_id;
            decision_id:=new.authorization_decision_event_id;
            product_project:=new.project_id; product_resource:=new.source_snapshot_id;
            select * into reservation from guide_mutation_idempotency_records
              where setup_run_id=new.id and action_id='project.guide_source_snapshot.create'
                and status='committed';
            product_generation:=reservation.operation_generation;
          end if;
          if reservation.id is null or product_resource is null
             or reservation.actor_profile_id is distinct from actor_id
             or reservation.identity_link_id is distinct from link_id
             or reservation.action_id is distinct from action_value
             or reservation.project_id is distinct from product_project
             or reservation.resource_id is distinct from product_resource
             or reservation.operation_generation is distinct from product_generation
             or scope_type not in ('system','project')
             or (scope_type='project' and scope_project is distinct from product_project)
             or (scope_type='system' and scope_project is not null) then
            raise exception 'guide mutation custody mismatch' using errcode='23514';
          end if;
          select * into evidence from audit_events where id=decision_id;
          if evidence.id is null
             or evidence.event_domain is distinct from 'authority'
             or evidence.event_type is distinct from 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind is distinct from 'actor_profile'
             or evidence.actor_id is distinct from actor_id
             or evidence.matched_grant_id is distinct from grant_id::text
             or evidence.permission_id is distinct from 'project.guide.manage'
             or evidence.action_id is distinct from action_value
             or evidence.resource_type is distinct from 'project'
             or evidence.resource_id is distinct from product_project
             or evidence.target_ref_kind is distinct from 'project'
             or evidence.target_ref_id is distinct from product_project
             or evidence.after_facts->>'allowed' is distinct from 'true'
             or evidence.after_facts->>'resource_context_digest'
                is distinct from reservation.resource_context_digest then
            raise exception 'guide mutation evidence mismatch' using errcode='23514';
          end if;
          return null;
        end $$
        """
    )
    for name, table in (
        (
            "guide_mutation_product_custody",
            "project_guides",
        ),
        (
            "source_snapshot_product_custody",
            "guide_source_snapshots",
        ),
        (
            "source_setup_run_custody",
            "project_setup_runs",
        ),
    ):
        op.execute(
            f"create constraint trigger {name} after insert or update on {table} "
            "deferrable initially deferred for each row execute function validate_guide_mutation_custody()"
        )
    op.execute(
        "create constraint trigger guide_mutation_reservation_custody after insert or update "
        "on guide_mutation_idempotency_records deferrable initially deferred for each row "
        "execute function validate_guide_mutation_custody()"
    )
    op.execute(
        """
        create function reject_guide_source_snapshot_item_mutation() returns trigger
        language plpgsql as $$ begin
          raise exception 'guide source snapshot items are immutable' using errcode='23514';
        end $$
        """
    )
    op.execute(
        "create trigger guide_source_snapshot_items_immutable before update or delete or truncate "
        "on guide_source_snapshot_items for each statement "
        "execute function reject_guide_source_snapshot_item_mutation()"
    )
    op.execute(
        """
        create function validate_guide_source_snapshot_items() returns trigger
        language plpgsql as $$
        declare expected jsonb; actual jsonb; reservation guide_mutation_idempotency_records%rowtype;
        begin
          select jsonb_agg(item.value - 'content_excerpt' order by item.ordinality)
            into expected
            from guide_source_snapshots snapshot,
                 jsonb_array_elements(snapshot.manifest_json::jsonb->'items')
                   with ordinality as item(value, ordinality)
            where snapshot.id=new.source_snapshot_id;
          if expected is null then
            raise exception 'guide source snapshot item parent is unavailable' using errcode='23514';
          end if;
          select coalesce(jsonb_agg(jsonb_build_object(
                   'source_kind',source_kind,'durable_ref',durable_ref,
                   'ingestion_adapter',ingestion_adapter,'content_hash',content_hash,
                   'content_cid',content_cid,'media_type',media_type) order by item_order),'[]'::jsonb)
            into actual from guide_source_snapshot_items
            where source_snapshot_id=new.source_snapshot_id;
          if actual is distinct from expected then
            raise exception 'guide source snapshot items do not match manifest' using errcode='23514';
          end if;
          select r.* into reservation from guide_mutation_idempotency_records r
            join guide_source_snapshots s on s.id=r.resource_id
            where s.id=new.source_snapshot_id
              and r.action_id='project.guide_source_snapshot.create'
              and r.operation_generation=s.creation_generation and r.status='committed';
          if reservation.id is null then
            raise exception 'guide source snapshot item custody mismatch' using errcode='23514';
          end if;
          return null;
        end $$
        """
    )
    op.execute(
        "create constraint trigger guide_source_snapshot_items_custody after insert "
        "on guide_source_snapshot_items deferrable initially deferred for each row "
        "execute function validate_guide_source_snapshot_items()"
    )


def downgrade() -> None:
    """Refuse removal once the authority seam has custody of any mutation."""
    bind = op.get_bind()
    for table in (
        "guide_mutation_idempotency_records",
        "project_guides",
        "guide_source_snapshots",
        "project_setup_runs",
    ):
        bind.execute(sa.text(f"lock table {table} in share row exclusive mode"))
    used = bind.execute(
        sa.text(
            "select exists(select 1 from guide_mutation_idempotency_records) "
            "or exists(select 1 from project_guides where mutation_generation is not null) "
            "or exists(select 1 from guide_source_snapshots where creation_generation is not null) "
            "or exists(select 1 from project_setup_runs where authorization_action_id is not null)"
        )
    ).scalar_one()
    if used:
        raise RuntimeError("cannot downgrade used guide source-metadata authority")
    op.execute("drop trigger guide_source_snapshot_items_custody on guide_source_snapshot_items")
    op.execute("drop function validate_guide_source_snapshot_items()")
    op.execute("drop trigger guide_source_snapshot_items_immutable on guide_source_snapshot_items")
    op.execute("drop function reject_guide_source_snapshot_item_mutation()")
    op.execute(
        "drop trigger guide_mutation_reservation_custody on guide_mutation_idempotency_records"
    )
    op.execute("drop trigger source_setup_run_custody on project_setup_runs")
    op.execute("drop trigger source_snapshot_product_custody on guide_source_snapshots")
    op.execute("drop trigger guide_mutation_product_custody on project_guides")
    op.execute("drop trigger guide_lineage_lifecycle_guard on project_guides")
    op.execute(
        "drop trigger guide_mutation_idempotency_reject_truncate on guide_mutation_idempotency_records"
    )
    op.execute(
        "drop trigger guide_mutation_idempotency_guard on guide_mutation_idempotency_records"
    )
    op.execute("drop function reject_guide_mutation_idempotency_truncate()")
    op.execute("drop function guard_guide_mutation_idempotency()")
    op.execute("drop function validate_guide_mutation_custody()")
    op.execute("drop function guard_guide_lineage_and_lifecycle()")
    op.drop_table("guide_mutation_idempotency_records")
    op.drop_constraint("setup_run_authority_shape", "project_setup_runs", type_="check")
    _drop_authority_columns("project_setup_runs", prefix="authorized")
    op.drop_constraint(
        "source_snapshot_creation_authority_shape", "guide_source_snapshots", type_="check"
    )
    op.drop_column("guide_source_snapshots", "creation_generation")
    _drop_authority_columns("guide_source_snapshots", prefix="created")
    op.drop_constraint("guide_mutation_authority_shape", "project_guides", type_="check")
    op.drop_column("project_guides", "mutation_generation")
    _drop_authority_columns("project_guides", prefix="last_mutated")
