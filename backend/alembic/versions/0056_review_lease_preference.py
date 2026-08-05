"""add hidden review lease and preference persistence

Revision ID: 0056_review_lease_preference
Revises: 0055_contribution_policy
Create Date: 2026-08-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0056_review_lease_preference"
down_revision = "0055_contribution_policy"
branch_labels = depends_on = None


def _replace_queue_checks(*, with_leases: bool) -> None:
    op.drop_constraint("ck_review_queue_entries_queue_state", "review_queue_entries", type_="check")
    op.drop_constraint(
        "ck_review_queue_entries_lifecycle_shape", "review_queue_entries", type_="check"
    )
    states = "'pending','leased','closed'" if with_leases else "'pending','closed'"
    op.create_check_constraint(
        "ck_review_queue_entries_queue_state",
        "review_queue_entries",
        f"queue_state in ({states})",
    )
    if with_leases:
        shape = (
            "(queue_state='pending' and active_lease_id is null "
            "and closed_at is null and closed_reason is null) or "
            "(queue_state='leased' and active_lease_id is not null "
            "and closed_at is null and closed_reason is null) or "
            "(queue_state='closed' and active_lease_id is null and closed_at is not null "
            "and closed_reason in ('review_recorded','task_closed','admin_cancelled') "
            "and closed_at >= first_queued_at)"
        )
    else:
        shape = (
            "(queue_state='pending' and closed_at is null and closed_reason is null) or "
            "(queue_state='closed' and closed_at is not null and "
            "closed_reason in ('review_recorded','task_closed','admin_cancelled') "
            "and closed_at >= first_queued_at)"
        )
    op.create_check_constraint(
        "ck_review_queue_entries_lifecycle_shape", "review_queue_entries", shape
    )


def _create_lease_table() -> None:
    op.create_unique_constraint(
        "uq_review_queue_lease_lineage",
        "review_queue_entries",
        ["id", "project_id", "task_id", "submission_id", "submission_version"],
    )
    op.create_table(
        "review_leases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_queue_entry_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("submission_id", sa.String(36), nullable=False),
        sa.Column("submission_version", sa.Integer(), nullable=False),
        sa.Column("reviewer_id", sa.String(36), nullable=False),
        sa.Column("reviewer_contribution_policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column(
            "claimed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("close_reason", sa.String(32)),
        sa.CheckConstraint("attempt_generation > 0", name="attempt_generation_positive"),
        sa.CheckConstraint(
            "status in ('active','consumed','released','expired','revoked')", name="status"
        ),
        sa.CheckConstraint("expires_at > claimed_at", name="expiry_after_claim"),
        sa.CheckConstraint(
            "(status='active' and closed_at is null and close_reason is null) or "
            "(status='consumed' and closed_at is not null and close_reason='review_recorded') or "
            "(status='released' and closed_at is not null and close_reason='manual_release') or "
            "(status='expired' and closed_at is not null and close_reason='lease_expired') or "
            "(status='revoked' and closed_at is not null "
            "and close_reason in ('grant_revoked','admin_override'))",
            name="lifecycle_shape",
        ),
        sa.CheckConstraint(
            "closed_at is null or closed_at >= claimed_at", name="closure_after_claim"
        ),
        sa.ForeignKeyConstraint(
            ["review_queue_entry_id", "project_id", "task_id", "submission_id", "submission_version"],
            ["review_queue_entries.id", "review_queue_entries.project_id", "review_queue_entries.task_id", "review_queue_entries.submission_id", "review_queue_entries.submission_version"],
            name="fk_review_lease_queue_lineage",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_review_lease_project"),
        sa.ForeignKeyConstraint(["task_id"], ["workstream_tasks.id"], name="fk_review_lease_task"),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], name="fk_review_lease_submission"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["actor_profiles.id"], name="fk_review_lease_reviewer"),
        sa.ForeignKeyConstraint(
            ["reviewer_contribution_policy_version_id", "project_id"],
            ["contribution_policy_versions.id", "contribution_policy_versions.project_id"],
            name="fk_review_lease_policy_version",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_leases"),
        sa.UniqueConstraint("review_queue_entry_id", "id", name="uq_review_lease_queue_identity"),
        sa.UniqueConstraint(
            "review_queue_entry_id", "attempt_generation", name="uq_review_lease_attempt"
        ),
    )
    op.create_index(
        "uq_review_lease_active_queue",
        "review_leases",
        ["review_queue_entry_id"],
        unique=True,
        postgresql_where=sa.text("status='active'"),
    )
    op.create_index(
        "uq_review_lease_active_reviewer",
        "review_leases",
        ["reviewer_id"],
        unique=True,
        postgresql_where=sa.text("status='active'"),
    )
    op.create_index("ix_review_lease_expiry", "review_leases", ["status", "expires_at", "id"])


def _create_guards() -> None:
    op.execute(
        """
        create function guard_review_lease() returns trigger language plpgsql as $$
        declare
          actor_type text;
          policy_status text;
        begin
          if tg_op='DELETE' then
            raise exception 'review leases cannot be deleted' using errcode='55000';
          end if;
          if tg_op='INSERT' then
            if new.status <> 'active' then
              raise exception 'review lease must begin active' using errcode='23514';
            end if;
            new.claimed_at := statement_timestamp();
            new.closed_at := null;
            new.close_reason := null;
          else
            if old.status <> 'active' then
              raise exception 'terminal review leases are immutable' using errcode='55000';
            end if;
            if (new.id,new.review_queue_entry_id,new.project_id,new.task_id,new.submission_id,
                new.submission_version,new.reviewer_id,
                new.reviewer_contribution_policy_version_id,new.attempt_generation,
                new.claimed_at,new.expires_at)
               is distinct from
               (old.id,old.review_queue_entry_id,old.project_id,old.task_id,old.submission_id,
                old.submission_version,old.reviewer_id,
                old.reviewer_contribution_policy_version_id,old.attempt_generation,
                old.claimed_at,old.expires_at) then
              raise exception 'review lease identity is immutable' using errcode='55000';
            end if;
            if new.status='active' then
              raise exception 'review lease update must close attempt' using errcode='23514';
            end if;
          end if;
          select actor_kind into actor_type from actor_profiles where id=new.reviewer_id;
          if actor_type is distinct from 'human' then
            raise exception 'review lease reviewer must be human' using errcode='23514';
          end if;
          if tg_op='INSERT' then
            select status into policy_status from contribution_policy_versions
             where id=new.reviewer_contribution_policy_version_id and project_id=new.project_id;
            if policy_status is distinct from 'published' then
              raise exception 'review lease policy version must be published' using errcode='23514';
            end if;
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        "create trigger review_leases_guard before insert or update or delete on review_leases "
        "for each row execute function guard_review_lease()"
    )
    op.execute(
        """
        create function validate_review_active_lease() returns trigger language plpgsql as $$
        declare
          queue_row review_queue_entries%rowtype;
          active_count integer;
        begin
          if tg_table_name='review_queue_entries' then
            queue_row := new;
          else
            select * into queue_row from review_queue_entries
             where id=coalesce(new.review_queue_entry_id,old.review_queue_entry_id);
          end if;
          if not found and tg_table_name='review_leases' then
            raise exception 'review lease queue is missing' using errcode='23514';
          end if;
          select count(*) into active_count from review_leases
           where review_queue_entry_id=queue_row.id and status='active';
          if queue_row.queue_state='leased' then
            if queue_row.active_lease_id is null or active_count <> 1 or not exists(
              select 1 from review_leases where id=queue_row.active_lease_id
               and review_queue_entry_id=queue_row.id and status='active'
            ) then
              raise exception 'leased queue must identify its active lease' using errcode='23514';
            end if;
          elsif queue_row.active_lease_id is not null or active_count <> 0 then
            raise exception 'non-leased queue cannot retain an active lease' using errcode='23514';
          end if;
          return null;
        end $$
        """
    )
    for table in ("review_queue_entries", "review_leases"):
        op.execute(
            f"create constraint trigger {table}_active_lease_guard "
            f"after insert or update on {table} deferrable initially deferred "
            "for each row execute function validate_review_active_lease()"
        )
    op.execute(
        """
        create function reject_review_lease_truncate() returns trigger language plpgsql as $$
        begin
          raise exception 'review leases cannot be truncated' using errcode='55000';
        end $$
        """
    )
    op.execute(
        "create trigger review_leases_reject_truncate before truncate on review_leases "
        "execute function reject_review_lease_truncate()"
    )


def _replace_queue_guard(*, with_preference_guard: bool) -> None:
    op.execute("drop trigger review_queue_entries_guard on review_queue_entries")
    op.execute("drop function guard_review_queue_entry()")
    preference = """
          if new.preferred_reviewer_id is not null and not exists(
            select 1 from actor_profiles where id=new.preferred_reviewer_id and actor_kind='human'
          ) then
            raise exception 'preferred reviewer must be human' using errcode='23514';
          end if;
    """ if with_preference_guard else ""
    op.execute(
        f"""
        create function guard_review_queue_entry() returns trigger language plpgsql as $$
        declare
          task_project text;
          checker_row checker_runs%rowtype;
        begin
          if tg_op='DELETE' then
            raise exception 'review queue entries cannot be deleted' using errcode='55000';
          end if;
          if tg_op='INSERT' then
            if new.queue_state <> 'pending' then
              raise exception 'review queue must begin pending' using errcode='23514';
            end if;
            new.first_queued_at := statement_timestamp();
            new.available_since := new.first_queued_at;
            new.routing_generation := 1;
            new.lifecycle_generation := 1;
            new.created_at := new.first_queued_at;
          end if;
          if tg_op='UPDATE' then
            if (new.id,new.project_id,new.task_id,new.submission_id,new.submission_version,
                new.admitting_checker_run_id,new.first_queued_at,new.created_at)
               is distinct from
               (old.id,old.project_id,old.task_id,old.submission_id,old.submission_version,
                old.admitting_checker_run_id,old.first_queued_at,old.created_at) then
              raise exception 'review queue identity is immutable' using errcode='55000';
            end if;
            if old.queue_state='closed' and new.queue_state <> 'closed' then
              raise exception 'closed review queue entries cannot reopen' using errcode='23514';
            end if;
            if new.routing_generation < old.routing_generation
               or new.lifecycle_generation < old.lifecycle_generation then
              raise exception 'review queue generations cannot decrease' using errcode='23514';
            end if;
          end if;
          {preference}
          if tg_op='UPDATE' then return new; end if;
          select project_id into task_project from workstream_tasks where id=new.task_id;
          if task_project is null or task_project <> new.project_id then
            raise exception 'review queue task project mismatch' using errcode='23514';
          end if;
          select * into checker_row from checker_runs where id=new.admitting_checker_run_id;
          if not found or checker_row.task_id <> new.task_id
             or checker_row.submission_id <> new.submission_id
             or checker_row.submission_version <> new.submission_version then
            raise exception 'review queue checker lineage mismatch' using errcode='23514';
          end if;
          if checker_row.status <> 'completed' or checker_row.routing_recommendation <> 'allow_review'
             or checker_row.is_current_for_submission is not true then
            raise exception 'review queue checker is not admissible' using errcode='23514';
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        "create trigger review_queue_entries_guard before insert or update or delete "
        "on review_queue_entries for each row execute function guard_review_queue_entry()"
    )


def upgrade() -> None:
    """Install empty lease persistence after the canonical CON policy target."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table review_queue_entries in share row exclusive mode"))
    invalid_preference = bind.execute(
        sa.text(
            "select exists(select 1 from review_queue_entries queue "
            "left join actor_profiles actor on actor.id=queue.preferred_reviewer_id "
            "where queue.preferred_reviewer_id is not null "
            "and actor.actor_kind is distinct from 'human')"
        )
    ).scalar_one()
    if invalid_preference:
        raise RuntimeError("cannot add lease persistence with nonhuman reviewer preference")
    op.add_column("review_queue_entries", sa.Column("active_lease_id", sa.Uuid()))
    _replace_queue_checks(with_leases=True)
    _create_lease_table()
    op.create_foreign_key(
        "fk_review_queue_active_lease",
        "review_queue_entries",
        "review_leases",
        ["active_lease_id", "id"],
        ["id", "review_queue_entry_id"],
        deferrable=True,
        initially="DEFERRED",
    )
    _replace_queue_guard(with_preference_guard=True)
    _create_guards()


def downgrade() -> None:
    """Remove only unused lease persistence; never discard attempt history."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table review_leases in access exclusive mode"))
    if bind.execute(sa.text("select exists(select 1 from review_leases)" )).scalar_one():
        raise RuntimeError("cannot downgrade populated review lease persistence")
    op.execute("drop trigger review_leases_reject_truncate on review_leases")
    op.execute("drop function reject_review_lease_truncate()")
    for table in ("review_queue_entries", "review_leases"):
        op.execute(f"drop trigger {table}_active_lease_guard on {table}")
    op.execute("drop function validate_review_active_lease()")
    op.execute("drop trigger review_leases_guard on review_leases")
    op.execute("drop function guard_review_lease()")
    _replace_queue_guard(with_preference_guard=False)
    op.drop_constraint("fk_review_queue_active_lease", "review_queue_entries", type_="foreignkey")
    op.drop_table("review_leases")
    op.drop_constraint("uq_review_queue_lease_lineage", "review_queue_entries", type_="unique")
    _replace_queue_checks(with_leases=False)
    op.drop_column("review_queue_entries", "active_lease_id")
