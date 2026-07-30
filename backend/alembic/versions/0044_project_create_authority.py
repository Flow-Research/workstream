"""activate transaction-bound project creation authority

Revision ID: 0044_project_create_authority
Revises: 0043_project_setup_service
Create Date: 2026-07-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0044_project_create_authority"
down_revision = "0043_project_setup_service"
branch_labels = depends_on = None

_RESOURCE_MARKER = "('audit_event'::character varying)::text"
_RESOURCE_ADDITION = ", ('project_create_operation'::character varying)::text"
_TARGET_MARKER = "('project_role_grant'::character varying)::text"
_TARGET_ADDITION = ", ('project'::character varying)::text"


def _rewrite_audit_privacy(*, add: bool) -> None:
    bind = op.get_bind()
    definition = bind.execute(
        sa.text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='audit_events'::regclass "
            "and conname='ck_audit_events_authority_privacy_bounds'"
        )
    ).scalar_one()
    resource_new = _RESOURCE_MARKER + _RESOURCE_ADDITION
    resource_source, resource_target = (
        (_RESOURCE_MARKER, resource_new) if add else (resource_new, _RESOURCE_MARKER)
    )
    if definition.count(resource_source) != 1 or (add and resource_new in definition):
        raise RuntimeError("unexpected authority privacy constraint")
    definition = definition.replace(resource_source, resource_target, 1)

    target_new = _TARGET_MARKER + _TARGET_ADDITION
    target_source, target_target = (
        (_TARGET_MARKER, target_new) if add else (target_new, _TARGET_MARKER)
    )
    anchor = "((target_ref_kind)::text = ANY (ARRAY["
    anchor_index = definition.find(anchor)
    source_index = definition.find(target_source, anchor_index)
    invalidation_index = definition.find("invalidation_target_kind", anchor_index)
    if (
        anchor_index < 0
        or source_index < 0
        or invalidation_index < 0
        or source_index > invalidation_index
        or (add and target_new in definition[anchor_index:invalidation_index])
    ):
        raise RuntimeError("unexpected authority privacy constraint")
    definition = (
        definition[:source_index]
        + target_target
        + definition[source_index + len(target_source) :]
    )
    op.drop_constraint("authority_privacy_bounds", "audit_events", type_="check")
    op.execute(
        "alter table audit_events add constraint "
        f"ck_audit_events_authority_privacy_bounds {definition}"
    )


def upgrade() -> None:
    """Add nullable historical provenance and project-owned replay state."""
    op.execute("lock table audit_events in access exclusive mode")
    _rewrite_audit_privacy(add=True)
    op.add_column("projects", sa.Column("created_by_actor_profile_id", sa.String(36)))
    op.add_column("projects", sa.Column("created_via_identity_link_id", sa.String(36)))
    op.add_column(
        "projects", sa.Column("created_by_admin_role_grant_id", sa.Uuid())
    )
    op.add_column("projects", sa.Column("creation_scope_type", sa.String(16)))
    op.add_column("projects", sa.Column("creation_action_id", sa.String(160)))
    op.add_column(
        "projects", sa.Column("authorization_decision_event_id", sa.String(36))
    )
    op.create_foreign_key(
        "fk_projects_creation_actor",
        "projects",
        "actor_profiles",
        ["created_by_actor_profile_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_projects_creation_identity_link",
        "projects",
        "actor_identity_links",
        ["created_via_identity_link_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_projects_creation_admin_grant",
        "projects",
        "admin_role_grants",
        ["created_by_admin_role_grant_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_projects_creation_decision",
        "projects",
        "audit_events",
        ["authorization_decision_event_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_projects_creation_authority_shape",
        "projects",
        "(created_by_actor_profile_id is null and created_via_identity_link_id is null "
        "and created_by_admin_role_grant_id is null and creation_scope_type is null "
        "and creation_action_id is null and authorization_decision_event_id is null) or "
        "(created_by_actor_profile_id is not null and created_via_identity_link_id is not null "
        "and created_by_admin_role_grant_id is not null and creation_scope_type = 'system' "
        "and creation_action_id = 'project.create' and authorization_decision_event_id is not null)",
    )

    op.create_table(
        "project_create_idempotency_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "actor_profile_id",
            sa.String(36),
            sa.ForeignKey("actor_profiles.id"),
            nullable=False,
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
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("operation_generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "actor_profile_id", "action_id", "idempotency_key", name="uq_project_create_replay_namespace"
        ),
        sa.UniqueConstraint("operation_id", name="uq_project_create_operation_identity"),
        sa.UniqueConstraint("project_id", name="uq_project_create_project_identity"),
        sa.CheckConstraint("action_id = 'project.create'", name="ck_project_create_action"),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_project_create_request_digest",
        ),
        sa.CheckConstraint("operation_generation = 1", name="ck_project_create_generation"),
        sa.CheckConstraint(
            "status in ('pending','committed')", name="ck_project_create_status"
        ),
        sa.CheckConstraint(
            "(status = 'pending' and committed_at is null) or "
            "(status = 'committed' and committed_at is not null)",
            name="ck_project_create_state_shape",
        ),
    )
    op.execute(
        """
        create function guard_project_create_idempotency() returns trigger
        language plpgsql as $$
        begin
          if tg_op = 'INSERT' then
            if new.status <> 'pending' or new.committed_at is not null then
              raise exception 'project create reservation must begin pending' using errcode='23514';
            end if;
            return new;
          elsif tg_op = 'DELETE' then
            raise exception 'project create reservations are immutable' using errcode='55000';
          end if;
          if old.status <> 'pending' or new.status <> 'committed'
             or (new.id, new.actor_profile_id, new.identity_link_id, new.action_id,
                 new.idempotency_key, new.request_digest, new.operation_id,
                 new.project_id, new.operation_generation, new.created_at)
                is distinct from
                (old.id, old.actor_profile_id, old.identity_link_id, old.action_id,
                 old.idempotency_key, old.request_digest, old.operation_id,
                 old.project_id, old.operation_generation, old.created_at) then
            raise exception 'invalid project create reservation transition' using errcode='23514';
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        "create trigger project_create_idempotency_guard before insert or update or delete "
        "on project_create_idempotency_records for each row "
        "execute function guard_project_create_idempotency()"
    )
    op.execute(
        """
        create function reject_project_create_idempotency_truncate() returns trigger
        language plpgsql as $$ begin
          raise exception 'project create reservations are immutable' using errcode='55000';
        end $$
        """
    )
    op.execute(
        "create trigger project_create_idempotency_reject_truncate before truncate "
        "on project_create_idempotency_records execute function "
        "reject_project_create_idempotency_truncate()"
    )
    op.execute(
        """
        create function validate_project_create_custody() returns trigger
        language plpgsql as $$
        declare project_row projects%rowtype; reservation project_create_idempotency_records%rowtype;
                evidence audit_events%rowtype;
        begin
          if tg_table_name = 'projects' then
            if tg_op = 'INSERT' and new.creation_action_id is null then
              raise exception 'new projects require creation authority' using errcode='23514';
            end if;
            if new.creation_action_id is null then return null; end if;
            project_row := new;
            select * into reservation from project_create_idempotency_records
              where project_id=project_row.id and status='committed';
          else
            select * into reservation from project_create_idempotency_records
              where id=new.id;
            if reservation.status <> 'committed' then
              raise exception 'pending project create reservation cannot commit' using errcode='23514';
            end if;
            select * into project_row from projects where id=reservation.project_id;
          end if;
          if project_row.id is null or reservation.id is null
             or project_row.created_by_actor_profile_id <> reservation.actor_profile_id
             or project_row.created_via_identity_link_id <> reservation.identity_link_id
             or project_row.creation_action_id <> reservation.action_id then
            raise exception 'project create custody mismatch' using errcode='23514';
          end if;
          select * into evidence from audit_events
            where id=project_row.authorization_decision_event_id;
          if evidence.id is null or evidence.event_domain <> 'authority'
             or evidence.event_type <> 'SensitiveAuthorizationAllowed'
             or evidence.denial_code is not null
             or evidence.actor_ref_kind <> 'actor_profile'
             or evidence.actor_id <> project_row.created_by_actor_profile_id
             or evidence.matched_grant_id <> project_row.created_by_admin_role_grant_id::text
             or evidence.permission_id <> 'project.create'
             or evidence.action_id <> 'project.create'
             or evidence.resource_type <> 'project_create_operation'
             or evidence.resource_id <> reservation.operation_id::text
             or evidence.target_ref_kind <> 'project'
             or evidence.target_ref_id <> project_row.id
             or evidence.after_facts->>'allowed' <> 'true' then
            raise exception 'project create evidence mismatch' using errcode='23514';
          end if;
          return null;
        end $$
        """
    )
    op.execute(
        "create constraint trigger project_creation_custody after insert or update "
        "of created_by_actor_profile_id, created_via_identity_link_id, "
        "created_by_admin_role_grant_id, creation_scope_type, creation_action_id, "
        "authorization_decision_event_id on projects deferrable initially deferred "
        "for each row execute function validate_project_create_custody()"
    )
    op.execute(
        "create constraint trigger project_create_reservation_custody after insert or update "
        "on project_create_idempotency_records deferrable initially deferred for each row "
        "execute function validate_project_create_custody()"
    )


def downgrade() -> None:
    """Remove the seam only before any project-create authority is used."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table audit_events in access exclusive mode"))
    bind.execute(sa.text("lock table projects in share row exclusive mode"))
    bind.execute(
        sa.text("lock table project_create_idempotency_records in share row exclusive mode")
    )
    used = bind.execute(
        sa.text(
            "select exists(select 1 from projects where creation_action_id is not null) "
            "or exists(select 1 from project_create_idempotency_records)"
        )
    ).scalar_one()
    if used:
        raise RuntimeError("cannot downgrade non-empty project creation authority")
    op.execute("drop trigger project_creation_custody on projects")
    op.execute(
        "drop trigger project_create_reservation_custody on "
        "project_create_idempotency_records"
    )
    op.execute(
        "drop trigger project_create_idempotency_reject_truncate on "
        "project_create_idempotency_records"
    )
    op.execute(
        "drop trigger project_create_idempotency_guard on "
        "project_create_idempotency_records"
    )
    op.execute("drop function validate_project_create_custody()")
    op.execute("drop function reject_project_create_idempotency_truncate()")
    op.execute("drop function guard_project_create_idempotency()")
    op.drop_table("project_create_idempotency_records")
    op.drop_constraint("ck_projects_creation_authority_shape", "projects", type_="check")
    op.drop_constraint("fk_projects_creation_decision", "projects", type_="foreignkey")
    op.drop_constraint("fk_projects_creation_admin_grant", "projects", type_="foreignkey")
    op.drop_constraint("fk_projects_creation_identity_link", "projects", type_="foreignkey")
    op.drop_constraint("fk_projects_creation_actor", "projects", type_="foreignkey")
    op.drop_column("projects", "authorization_decision_event_id")
    op.drop_column("projects", "creation_action_id")
    op.drop_column("projects", "creation_scope_type")
    op.drop_column("projects", "created_by_admin_role_grant_id")
    op.drop_column("projects", "created_via_identity_link_id")
    op.drop_column("projects", "created_by_actor_profile_id")
    _rewrite_audit_privacy(add=False)
