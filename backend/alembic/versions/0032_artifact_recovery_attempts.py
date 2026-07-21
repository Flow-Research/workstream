"""add artifact recovery attempts and verification retry lineage

Revision ID: 0032_artifact_recovery
Revises: 0031_project_role_grants
Create Date: 2026-07-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0032_artifact_recovery"
down_revision = "0031_project_role_grants"
branch_labels = depends_on = None


def upgrade() -> None:
    """Install immutable recovery envelopes and retry-job lineage."""
    op.drop_constraint(
        "uq_artifact_verification_origin", "artifact_verification_jobs", type_="unique"
    )
    op.add_column(
        "artifact_verification_jobs",
        sa.Column("parent_verification_job_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_artifact_verification_parent",
        "artifact_verification_jobs",
        "artifact_verification_jobs",
        ["parent_verification_job_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_artifact_verification_parent",
        "artifact_verification_jobs",
        ["parent_verification_job_id"],
    )
    op.create_index(
        "ix_artifact_verification_jobs_parent_verification_job_id",
        "artifact_verification_jobs",
        ["parent_verification_job_id"],
    )
    op.create_index(
        "uq_artifact_verification_initial_origin",
        "artifact_verification_jobs",
        ["originating_put_attempt_id"],
        unique=True,
        postgresql_where=sa.text("parent_verification_job_id is null"),
    )

    op.create_table(
        "artifact_recovery_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("requester_actor_profile_id", sa.String(36), nullable=False),
        sa.Column("requester_identity_link_id", sa.String(36), nullable=False),
        sa.Column("authorization_request_id", sa.String(36), nullable=False),
        sa.Column("authorization_correlation_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("submission_id", sa.String(36), nullable=True),
        sa.Column("source_verification_job_id", sa.String(36), nullable=False),
        sa.Column("retry_verification_job_id", sa.String(36), nullable=False),
        sa.Column("parent_recovery_attempt_id", sa.String(36), nullable=True),
        sa.Column("recovery_class", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("client_idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="requested"),
        sa.Column("terminal_result_code", sa.String(40), nullable=True),
        sa.Column("initiation_audit_event_id", sa.String(36), nullable=False),
        sa.Column("terminal_audit_event_id", sa.String(36), nullable=True),
        sa.Column("cas_version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["requester_actor_profile_id"], ["actor_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["requester_identity_link_id"], ["actor_identity_links.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["workstream_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_verification_job_id"],
            ["artifact_verification_jobs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["retry_verification_job_id"],
            ["artifact_verification_jobs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_recovery_attempt_id"],
            ["artifact_recovery_attempts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["initiation_audit_event_id"], ["audit_events.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["terminal_audit_event_id"], ["audit_events.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "requester_actor_profile_id",
            "source_verification_job_id",
            "recovery_class",
            "client_idempotency_key",
            name="uq_artifact_recovery_idempotency",
        ),
        sa.UniqueConstraint(
            "source_verification_job_id", name="uq_artifact_recovery_source_job"
        ),
        sa.UniqueConstraint(
            "retry_verification_job_id", name="uq_artifact_recovery_retry_job"
        ),
        sa.CheckConstraint(
            "source_verification_job_id <> retry_verification_job_id", name="distinct_jobs"
        ),
        sa.CheckConstraint("recovery_class = 'provider_observation'", name="recovery_class"),
        sa.CheckConstraint("status in ('requested','succeeded','failed')", name="status"),
        sa.CheckConstraint("request_digest ~ '^sha256:[0-9a-f]{64}$'", name="request_digest"),
        sa.CheckConstraint("cas_version >= 0", name="cas_nonnegative"),
        sa.CheckConstraint(
            "(status='requested' and terminal_result_code is null and terminal_at is null "
            "and terminal_audit_event_id is null) or "
            "(status in ('succeeded','failed') and terminal_result_code is not null "
            "and terminal_at is not null and terminal_audit_event_id is not null)",
            name="terminal_shape",
        ),
        sa.CheckConstraint(
            "(status='succeeded' and terminal_result_code='verified') or "
            "(status='failed' and terminal_result_code in "
            "('provider_unavailable','missing','integrity_mismatch','conflict')) or "
            "status='requested'",
            name="terminal_result",
        ),
    )
    for column in (
        "requester_actor_profile_id",
        "project_id",
        "task_id",
        "submission_id",
        "parent_recovery_attempt_id",
    ):
        op.create_index(
            f"ix_artifact_recovery_attempts_{column}",
            "artifact_recovery_attempts",
            [column],
        )
    op.execute(
        """
        create function validate_artifact_recovery_attempt() returns trigger
        language plpgsql as $$
        declare
          source_row artifact_verification_jobs%rowtype;
          retry_row artifact_verification_jobs%rowtype;
          expected_parent text;
        begin
          if tg_op = 'DELETE' then
            raise exception 'artifact recovery attempts are append-only' using errcode='55000';
          end if;
          if tg_op = 'UPDATE' and (
            to_jsonb(new) - array['status','terminal_result_code','terminal_audit_event_id',
              'terminal_at','cas_version','updated_at']
            is distinct from
            to_jsonb(old) - array['status','terminal_result_code','terminal_audit_event_id',
              'terminal_at','cas_version','updated_at']
          ) then
            raise exception 'artifact recovery identity is immutable' using errcode='55000';
          end if;
          select * into source_row from artifact_verification_jobs
            where id=new.source_verification_job_id;
          select * into retry_row from artifact_verification_jobs
            where id=new.retry_verification_job_id;
          if source_row.id is null or retry_row.id is null
             or source_row.status <> 'provider_unavailable'
             or source_row.terminal_result_code <> 'provider_unavailable'
             or source_row.terminal_at is null or source_row.next_run_at is not null
             or source_row.executor_id is not null
             or source_row.attempt_count < source_row.maximum_attempts
             or retry_row.parent_verification_job_id <> source_row.id
             or retry_row.originating_put_attempt_id <> source_row.originating_put_attempt_id
             or retry_row.replica_id <> source_row.replica_id then
            raise exception 'invalid artifact recovery verification lineage' using errcode='23514';
          end if;
          if (tg_op = 'INSERT' and (retry_row.status <> 'pending' or retry_row.attempt_count <> 0))
             or (tg_op = 'UPDATE' and (
               retry_row.status <> new.terminal_result_code or retry_row.terminal_at is null
             )) then
            raise exception 'invalid artifact recovery retry state' using errcode='23514';
          end if;
          select id into expected_parent from artifact_recovery_attempts
            where retry_verification_job_id=source_row.id;
          if new.parent_recovery_attempt_id is distinct from expected_parent then
            raise exception 'invalid artifact recovery parent chain' using errcode='23514';
          end if;
          if not exists (
            select 1 from audit_events where id=new.initiation_audit_event_id
              and entity_type='artifact_recovery_attempt' and entity_id=new.id
              and event_type='ArtifactRecoveryInitiated'
          ) then
            raise exception 'invalid artifact recovery initiation audit' using errcode='23514';
          end if;
          if new.terminal_audit_event_id is not null and not exists (
            select 1 from audit_events where id=new.terminal_audit_event_id
              and entity_type='artifact_recovery_attempt' and entity_id=new.id
              and event_type='ArtifactRecoveryCompleted'
          ) then
            raise exception 'invalid artifact recovery terminal audit' using errcode='23514';
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        """
        create trigger artifact_recovery_attempt_custody
        before insert or update or delete on artifact_recovery_attempts
        for each row execute function validate_artifact_recovery_attempt()
        """
    )
    op.execute(
        """
        create function validate_artifact_verification_lineage() returns trigger
        language plpgsql as $$
        begin
          if old.originating_put_attempt_id is distinct from new.originating_put_attempt_id
             or old.replica_id is distinct from new.replica_id
             or old.parent_verification_job_id is distinct from new.parent_verification_job_id then
            raise exception 'artifact verification lineage is immutable' using errcode='55000';
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        """
        create trigger artifact_verification_lineage_custody
        before update on artifact_verification_jobs
        for each row execute function validate_artifact_verification_lineage()
        """
    )


def downgrade() -> None:
    """Remove recovery only when no durable recovery lineage exists."""
    bind = op.get_bind()
    if bind.execute(sa.text("select exists(select 1 from artifact_recovery_attempts)")).scalar():
        raise RuntimeError("cannot downgrade populated artifact recovery attempts")
    op.execute(
        "drop trigger artifact_verification_lineage_custody on artifact_verification_jobs"
    )
    op.execute("drop function validate_artifact_verification_lineage()")
    op.execute("drop trigger artifact_recovery_attempt_custody on artifact_recovery_attempts")
    op.execute("drop function validate_artifact_recovery_attempt()")
    op.drop_table("artifact_recovery_attempts")
    op.drop_index(
        "uq_artifact_verification_initial_origin", table_name="artifact_verification_jobs"
    )
    op.drop_index(
        "ix_artifact_verification_jobs_parent_verification_job_id",
        table_name="artifact_verification_jobs",
    )
    op.drop_constraint(
        "uq_artifact_verification_parent", "artifact_verification_jobs", type_="unique"
    )
    op.drop_constraint(
        "fk_artifact_verification_parent", "artifact_verification_jobs", type_="foreignkey"
    )
    op.drop_column("artifact_verification_jobs", "parent_verification_job_id")
    op.create_unique_constraint(
        "uq_artifact_verification_origin",
        "artifact_verification_jobs",
        ["originating_put_attempt_id"],
    )
