"""Replace the retained unstarted claim state with work started by claim."""

from alembic import op


revision = "0065_claim_starts_work"
down_revision = "0064_checker_trial_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Convert only unambiguous current claims; retain immutable command evidence."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    # Freeze both mutable lineage and immutable evidence before validating it.
    # The order follows TASK command reservation -> task -> assignment -> audit.
    op.execute(
        "LOCK TABLE public.task_command_receipts, public.workstream_tasks, "
        "public.task_assignments, public.submissions, public.audit_events "
        "IN ACCESS EXCLUSIVE MODE"
    )
    op.execute(
        """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM public.workstream_tasks task
    LEFT JOIN public.task_assignments assignment
      ON assignment.task_id=task.id AND assignment.status='active'
    WHERE task.status='claimed' AND (
      (SELECT pg_catalog.count(*) FROM public.task_assignments current_assignment
       WHERE current_assignment.task_id=task.id AND current_assignment.status='active')<>1
      OR assignment.project_id IS DISTINCT FROM task.project_id
      OR assignment.contributor_id IS DISTINCT FROM task.assigned_to
      OR task.assigned_to IS NULL
      OR assignment.submitter_contribution_policy_version_id IS DISTINCT FROM
         task.locked_contribution_policy_version_id
      OR assignment.accepted_at IS NULL OR assignment.released_at IS NOT NULL
      OR assignment.started_at IS NOT NULL
      OR EXISTS (SELECT 1 FROM public.submissions submission
                 WHERE submission.task_assignment_id=assignment.id)
      OR EXISTS (SELECT 1 FROM public.task_command_receipts receipt
                 WHERE receipt.assignment_id=assignment.id
                   AND receipt.action_id IN ('task.start','operations.task.start_override'))
      OR EXISTS (
        SELECT 1 FROM public.audit_events event
        WHERE event.event_type IN ('TaskStarted','TaskStartOverridden')
          AND (event.event_payload::jsonb#>>'{references,assignment_id}'=assignment.id::text
               OR (event.event_payload::jsonb#>>'{references,assignment_id}' IS NULL
                   AND event.entity_type='task' AND event.entity_id=task.id
                   AND event.created_at>=assignment.assigned_at))
      )
    )
  ) THEN
    RAISE EXCEPTION 'claimed task has ambiguous current assignment lineage'
      USING ERRCODE='23514';
  END IF;
END $$
        """
    )
    # The existing assignment guard requires the task to be in_progress first.
    # No historical start event or command receipt is manufactured or rewritten.
    op.execute(
        """
DO $$
DECLARE claimed_ids uuid[];
BEGIN
  SELECT pg_catalog.array_agg(id) INTO claimed_ids
    FROM public.workstream_tasks WHERE status='claimed';
  UPDATE public.workstream_tasks SET status='in_progress' WHERE id=ANY(claimed_ids);
  UPDATE public.task_assignments SET started_at=assigned_at
    WHERE task_id=ANY(claimed_ids) AND status='active' AND started_at IS NULL;
END $$
        """
    )
    # Task/assignment updates queue deferred lineage checks. Run those checks
    # before ALTER TABLE, which PostgreSQL refuses with pending trigger events.
    op.execute("SET CONSTRAINTS ALL IMMEDIATE")
    op.execute(
        "ALTER TABLE public.workstream_tasks DROP CONSTRAINT ck_workstream_tasks_status"
    )
    op.execute(
        "ALTER TABLE public.workstream_tasks ADD CONSTRAINT ck_workstream_tasks_status "
        "CHECK (status IN ('draft','screening','ready','in_progress','submitted',"
        "'evaluation_pending','review_pending','needs_revision','accepted'))"
    )


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
