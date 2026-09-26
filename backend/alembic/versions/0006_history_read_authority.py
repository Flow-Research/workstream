"""Admit only the exact submission/checker history authorization evidence pairs."""

from alembic import op
import sqlalchemy as sa

revision = "0006_history_read_authority"
down_revision = "0005_task_evidence_authority"
branch_labels = None
depends_on = None


def upgrade():
    """Extend the closed decision constraint without rewriting retained evidence."""
    name = "ck_audit_events_authorization_action_evidence"
    op.execute("lock table audit_events, checker_runs, checker_results in access exclusive mode")
    _checker_custody()
    definition = op.get_bind().execute(sa.text(
        "select pg_get_constraintdef(oid) from pg_constraint "
        "where conrelid='audit_events'::regclass and conname=:name"
    ), {"name": name}).scalar_one()
    anchor = "(((action_id)::text = 'project.task.create'::text) AND ((permission_id)::text = 'project.task.manage'::text))"
    addition = " OR ".join(
        f"(((action_id)::text = '{action}'::text) AND ((permission_id)::text = '{permission}'::text))"
        for action, permission in (
            ("task.submission.list", "submission.read_own"),
            ("submission.read", "submission.read_own"),
            ("submission.checker_run.list", "submission.read_own"),
            ("checker_run.read", "submission.read_own"),
            ("project.task.submission.list", "project.task.manage"),
            ("project.submission.read", "project.task.manage"),
            ("project.submission.checker_run.list", "project.task.manage"),
            ("project.checker_run.read", "project.task.manage"),
        )
    )
    if definition.count(anchor) != 2:
        raise RuntimeError("history authority constraint shape changed")
    op.execute(f"alter table audit_events drop constraint {name}")
    op.execute(f"alter table audit_events add constraint {name} " + definition.replace(anchor, anchor + " OR " + addition))


def downgrade():
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


def _checker_custody():
    """Preserve retained bytes; reject invalid parentage before installing custody."""
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM checker_results r JOIN checker_runs c ON c.id=r.checker_run_id
            WHERE (r.task_id,r.submission_id) IS DISTINCT FROM (c.task_id,c.submission_id)
          ) OR EXISTS (
            SELECT 1 FROM checker_runs c JOIN checker_runs p ON p.id=c.supersedes_checker_run_id
            WHERE (c.task_id,c.submission_id) IS DISTINCT FROM (p.task_id,p.submission_id)
          ) THEN
            RAISE EXCEPTION 'retained checker ownership is inconsistent' USING ERRCODE='23514';
          END IF;
        END $$
    """)
    op.create_unique_constraint("uq_checker_runs_ownership", "checker_runs", ["id", "task_id", "submission_id"])
    for table, name in (
        ("checker_runs", "fk_checker_runs_supersedes_checker_run_id_checker_runs"),
        ("checker_results", "fk_checker_results_checker_run_id_checker_runs"),
        ("checker_results", "fk_checker_results_task_id_workstream_tasks"),
        ("checker_results", "fk_checker_results_submission_id_submissions"),
    ):
        op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key("fk_checker_runs_predecessor_ownership", "checker_runs", "checker_runs",
                          ["supersedes_checker_run_id", "task_id", "submission_id"], ["id", "task_id", "submission_id"])
    op.create_foreign_key("fk_checker_results_run_ownership", "checker_results", "checker_runs",
                          ["checker_run_id", "task_id", "submission_id"], ["id", "task_id", "submission_id"])
    op.execute("""
        CREATE FUNCTION protect_checker_run_custody() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP IN ('DELETE','TRUNCATE') THEN
            RAISE EXCEPTION 'checker run custody is immutable' USING ERRCODE='23514';
          END IF;
          IF (to_jsonb(NEW) - ARRAY['status','routing_recommendation','outcome_source',
                'audit_event_id','is_current_for_submission','passed_count',
                'warning_count','failed_count','blocking_count','started_at','completed_at',
                'failure_code','failure_message']) IS DISTINCT FROM
             (to_jsonb(OLD) - ARRAY['status','routing_recommendation','outcome_source',
                'audit_event_id','is_current_for_submission','passed_count',
                'warning_count','failed_count','blocking_count','started_at','completed_at',
                'failure_code','failure_message'])
             OR NEW.locked_post_submit_checker_policy_body::text IS DISTINCT FROM OLD.locked_post_submit_checker_policy_body::text
             OR NEW.artifact_hash_manifest::text IS DISTINCT FROM OLD.artifact_hash_manifest::text
             OR (OLD.audit_event_id IS NOT NULL AND NEW.audit_event_id IS DISTINCT FROM OLD.audit_event_id)
             OR (NOT OLD.is_current_for_submission AND NEW.is_current_for_submission) THEN
            RAISE EXCEPTION 'checker run custody is immutable' USING ERRCODE='23514';
          END IF;
          IF (OLD.status IN ('completed','failed') OR OLD.completed_at IS NOT NULL)
             AND (to_jsonb(NEW) - ARRAY['audit_event_id','is_current_for_submission'])
                 IS DISTINCT FROM
                 (to_jsonb(OLD) - ARRAY['audit_event_id','is_current_for_submission']) THEN
            RAISE EXCEPTION 'checker run outcome is immutable' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE FUNCTION protect_checker_result_custody() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent_status text; parent_completed_at timestamptz;
        BEGIN
          IF TG_OP = 'INSERT' THEN
            SELECT status, completed_at INTO parent_status, parent_completed_at
            FROM checker_runs
            WHERE id=NEW.checker_run_id AND task_id=NEW.task_id AND submission_id=NEW.submission_id
            FOR UPDATE;
            -- A later FK snapshot must not admit a parent invisible to this check.
            IF NOT FOUND THEN
              RAISE EXCEPTION 'checker result violates fk_checker_results_run_ownership'
                USING ERRCODE='23503', CONSTRAINT='fk_checker_results_run_ownership', TABLE='checker_results';
            END IF;
            IF parent_status NOT IN ('queued','running') OR parent_completed_at IS NOT NULL THEN
              RAISE EXCEPTION 'finished checker run cannot receive results' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'checker result custody is immutable' USING ERRCODE='23514';
        END $$
    """)
    for table, owner in (("checker_runs", "run"), ("checker_results", "result")):
        events = "INSERT OR UPDATE OR DELETE" if owner == "result" else "UPDATE OR DELETE"
        op.execute(f"CREATE TRIGGER checker_{owner}_custody BEFORE {events} ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION protect_checker_{owner}_custody()")
        op.execute(f"CREATE TRIGGER checker_{owner}_no_truncate BEFORE TRUNCATE ON {table} "
                   f"FOR EACH STATEMENT EXECUTE FUNCTION protect_checker_{owner}_custody()")
