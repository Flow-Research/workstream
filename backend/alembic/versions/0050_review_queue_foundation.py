"""add hidden review queue and admission idempotency persistence

Revision ID: 0050_review_queue_foundation
Revises: 0049_rev_auth_readiness
Create Date: 2026-08-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0050_review_queue_foundation"
down_revision = "0049_rev_auth_readiness"
branch_labels = depends_on = None


def _create_queue_table() -> None:
    op.create_table(
        "review_queue_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("submission_id", sa.String(36), nullable=False),
        sa.Column("submission_version", sa.Integer(), nullable=False),
        sa.Column("admitting_checker_run_id", sa.String(36), nullable=False),
        sa.Column("queue_state", sa.String(16), server_default="pending", nullable=False),
        sa.Column("routing_mode", sa.String(16), nullable=False),
        sa.Column("routing_reason", sa.String(32), nullable=False),
        sa.Column(
            "first_queued_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "available_since",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.Column("preferred_reviewer_id", sa.String(36)),
        sa.Column("preference_expires_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_reason", sa.String(32)),
        sa.Column("routing_generation", sa.Integer(), server_default="1", nullable=False),
        sa.Column("lifecycle_generation", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "submission_version > 0",
            name="ck_review_queue_entries_submission_version_positive",
        ),
        sa.CheckConstraint(
            "queue_state in ('pending','closed')",
            name="ck_review_queue_entries_queue_state",
        ),
        sa.CheckConstraint(
            "routing_mode in ('open','preferred')",
            name="ck_review_queue_entries_routing_mode",
        ),
        sa.CheckConstraint(
            "routing_reason in ('first_submission','revision_return','admin_assignment')",
            name="ck_review_queue_entries_routing_reason",
        ),
        sa.CheckConstraint(
            "(routing_mode='open' and preferred_reviewer_id is null "
            "and preference_expires_at is null) or "
            "(routing_mode='preferred' and preferred_reviewer_id is not null "
            "and preference_expires_at is not null "
            "and preference_expires_at > first_queued_at)",
            name="ck_review_queue_entries_routing_shape",
        ),
        sa.CheckConstraint(
            "(queue_state='pending' and closed_at is null and closed_reason is null) or "
            "(queue_state='closed' and closed_at is not null and "
            "closed_reason in ('review_recorded','task_closed','admin_cancelled') "
            "and closed_at >= first_queued_at)",
            name="ck_review_queue_entries_lifecycle_shape",
        ),
        sa.CheckConstraint(
            "available_since >= first_queued_at",
            name="ck_review_queue_entries_availability_time",
        ),
        sa.CheckConstraint(
            "routing_generation > 0 and lifecycle_generation > 0",
            name="ck_review_queue_entries_generations_positive",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_review_queue_project"
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["workstream_tasks.id"],
            name="fk_review_queue_task",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name="fk_review_queue_submission",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id", "task_id", "submission_version"],
            ["submissions.id", "submissions.task_id", "submissions.version"],
            name="fk_review_queue_submission_lineage",
        ),
        sa.ForeignKeyConstraint(
            ["admitting_checker_run_id"],
            ["checker_runs.id"],
            name="fk_review_queue_checker",
        ),
        sa.ForeignKeyConstraint(
            ["preferred_reviewer_id"],
            ["actor_profiles.id"],
            name="fk_review_queue_preferred_reviewer",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_queue_entries"),
        sa.UniqueConstraint("submission_id", name="uq_review_queue_submission"),
        sa.UniqueConstraint(
            "id",
            "project_id",
            "task_id",
            "submission_id",
            "submission_version",
            "admitting_checker_run_id",
            name="uq_review_queue_admission_identity",
        ),
    )
    op.create_index(
        "ix_review_queue_selection",
        "review_queue_entries",
        ["project_id", "queue_state", "routing_mode", "first_queued_at", "id"],
    )
    op.create_index(
        "ix_review_queue_preference",
        "review_queue_entries",
        ["preferred_reviewer_id", "queue_state", "preference_expires_at", "id"],
    )


def _create_admission_table() -> None:
    op.create_table(
        "review_admission_idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("submission_id", sa.String(36), nullable=False),
        sa.Column("submission_version", sa.Integer(), nullable=False),
        sa.Column("admitting_checker_run_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("review_queue_entry_id", sa.Uuid()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "submission_version > 0",
            name="ck_review_admission_idempotency_records_submission_version_positive",
        ),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_review_admission_idempotency_records_request_digest",
        ),
        sa.CheckConstraint(
            "status in ('pending','committed')",
            name="ck_review_admission_idempotency_records_status",
        ),
        sa.CheckConstraint(
            "(status='pending' and review_queue_entry_id is null and committed_at is null) or "
            "(status='committed' and review_queue_entry_id is not null "
            "and committed_at is not null)",
            name="ck_review_admission_idempotency_records_state_shape",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_review_admission_project",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["workstream_tasks.id"],
            name="fk_review_admission_task",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name="fk_review_admission_submission",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id", "task_id", "submission_version"],
            ["submissions.id", "submissions.task_id", "submissions.version"],
            name="fk_review_admission_submission_lineage",
        ),
        sa.ForeignKeyConstraint(
            ["admitting_checker_run_id"],
            ["checker_runs.id"],
            name="fk_review_admission_checker",
        ),
        sa.ForeignKeyConstraint(
            ["review_queue_entry_id"],
            ["review_queue_entries.id"],
            name="fk_review_admission_queue",
        ),
        sa.ForeignKeyConstraint(
            [
                "review_queue_entry_id",
                "project_id",
                "task_id",
                "submission_id",
                "submission_version",
                "admitting_checker_run_id",
            ],
            [
                "review_queue_entries.id",
                "review_queue_entries.project_id",
                "review_queue_entries.task_id",
                "review_queue_entries.submission_id",
                "review_queue_entries.submission_version",
                "review_queue_entries.admitting_checker_run_id",
            ],
            name="fk_review_admission_committed_queue",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_admission_idempotency_records"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_review_admission_replay_key"
        ),
        sa.UniqueConstraint("operation_id", name="uq_review_admission_operation"),
        sa.UniqueConstraint(
            "admitting_checker_run_id", name="uq_review_admission_checker_run"
        ),
    )
    op.create_index(
        "ix_review_admission_submission",
        "review_admission_idempotency_records",
        ["submission_id", "status", "created_at", "id"],
    )


def _create_guards() -> None:
    op.execute(
        """
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
            return new;
          end if;
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
          if checker_row.status <> 'completed'
             or checker_row.routing_recommendation <> 'allow_review'
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
    op.execute(
        """
        create function guard_review_admission_record() returns trigger language plpgsql as $$
        declare
          task_project text;
          checker_row checker_runs%rowtype;
        begin
          if tg_op='DELETE' then
            raise exception 'review admission records cannot be deleted' using errcode='55000';
          end if;
          if tg_op='INSERT' and new.status <> 'pending' then
            raise exception 'review admission must begin pending' using errcode='23514';
          end if;
          if tg_op='INSERT' then
            new.created_at := statement_timestamp();
          end if;
          if tg_op='UPDATE' then
            if (new.id,new.idempotency_key,new.operation_id,new.request_digest,new.project_id,
                new.task_id,new.submission_id,new.submission_version,
                new.admitting_checker_run_id,new.created_at)
               is distinct from
               (old.id,old.idempotency_key,old.operation_id,old.request_digest,old.project_id,
                old.task_id,old.submission_id,old.submission_version,
                old.admitting_checker_run_id,old.created_at) then
              raise exception 'review admission identity is immutable' using errcode='55000';
            end if;
            if old.status <> 'pending' or new.status <> 'committed' then
              raise exception 'invalid review admission transition' using errcode='23514';
            end if;
          end if;
          select project_id into task_project from workstream_tasks where id=new.task_id;
          if task_project is null or task_project <> new.project_id then
            raise exception 'review admission task project mismatch' using errcode='23514';
          end if;
          select * into checker_row from checker_runs where id=new.admitting_checker_run_id;
          if not found or checker_row.task_id <> new.task_id
             or checker_row.submission_id <> new.submission_id
             or checker_row.submission_version <> new.submission_version then
            raise exception 'review admission checker lineage mismatch' using errcode='23514';
          end if;
          if new.status='committed' and (
             checker_row.status <> 'completed'
             or checker_row.routing_recommendation <> 'allow_review'
             or checker_row.is_current_for_submission is not true) then
            raise exception 'review admission checker is not admissible' using errcode='23514';
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        "create trigger review_admission_records_guard before insert or update or delete "
        "on review_admission_idempotency_records for each row "
        "execute function guard_review_admission_record()"
    )
    op.execute(
        """
        create function reject_review_queue_foundation_truncate() returns trigger
        language plpgsql as $$
        begin
          raise exception 'review queue foundation cannot be truncated' using errcode='55000';
        end $$
        """
    )
    for table in ("review_queue_entries", "review_admission_idempotency_records"):
        op.execute(
            f"create trigger {table}_reject_truncate before truncate on {table} "
            "execute function reject_review_queue_foundation_truncate()"
        )


def upgrade() -> None:
    """Install empty hidden REV persistence without admitting historical work."""
    _create_queue_table()
    _create_admission_table()
    _create_guards()


def downgrade() -> None:
    """Remove only an unused queue foundation; never discard review history."""
    bind = op.get_bind()
    bind.execute(sa.text("lock table review_admission_idempotency_records in access exclusive mode"))
    bind.execute(sa.text("lock table review_queue_entries in access exclusive mode"))
    populated = bind.execute(
        sa.text(
            "select exists(select 1 from review_queue_entries) or "
            "exists(select 1 from review_admission_idempotency_records)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("cannot downgrade populated review queue foundation")
    for table in ("review_admission_idempotency_records", "review_queue_entries"):
        op.execute(f"drop trigger {table}_reject_truncate on {table}")
    op.execute("drop trigger review_admission_records_guard on review_admission_idempotency_records")
    op.execute("drop function guard_review_admission_record()")
    op.execute("drop trigger review_queue_entries_guard on review_queue_entries")
    op.execute("drop function guard_review_queue_entry()")
    op.execute("drop function reject_review_queue_foundation_truncate()")
    op.drop_table("review_admission_idempotency_records")
    op.drop_table("review_queue_entries")
