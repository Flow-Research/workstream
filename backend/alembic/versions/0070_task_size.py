"""Persist explicit new task sizes while retaining original immutable responses."""

from alembic import op
from sqlalchemy import text

revision = "0070_task_size"
down_revision = "0069_reward_policy_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("SELECT id FROM public.authority_control WHERE id=1 FOR UPDATE")
    phase = (
        op.get_bind()
        .execute(
            text(
                "SELECT phase FROM public.joint_lifecycle_release_control WHERE singleton FOR UPDATE"
            )
        )
        .scalar_one()
    )
    if phase != "disabled":
        raise RuntimeError("task size cutover requires the shared lifecycle disabled after drain")
    op.execute("""LOCK TABLE public.workstream_tasks, public.task_assignments,
        public.submissions, public.task_command_receipts IN ACCESS EXCLUSIVE MODE""")
    if (
        op.get_bind()
        .execute(
            text("""SELECT
        EXISTS(SELECT 1 FROM public.workstream_tasks
          WHERE status<>'accepted' AND locked_contribution_policy_version_id IS NOT NULL)
        OR EXISTS(SELECT 1 FROM public.task_assignments WHERE status='active')
        OR EXISTS(SELECT 1 FROM public.submissions
          WHERE attempt_status IN ('evaluation_pending','review_pending','needs_revision'))
    """)
        )
        .scalar_one()
    ):
        raise RuntimeError("task size cutover blocked by work without a recorded size")
    op.execute("ALTER TABLE public.workstream_tasks ADD COLUMN task_size varchar(8)")
    op.execute("""ALTER TABLE public.workstream_tasks ADD CONSTRAINT
        ck_workstream_tasks_task_size CHECK (task_size IS NULL OR task_size IN ('small','medium','large'))""")
    # Only unscreened drafts acquire the creation default. Terminal evidence and
    # all saved command/import JSON remain unchanged.
    op.execute("""UPDATE public.workstream_tasks SET task_size='small'
        WHERE status='draft' AND locked_contribution_policy_version_id IS NULL""")
    op.execute("""
CREATE FUNCTION public.guard_task_size() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
  IF TG_OP='INSERT' AND NEW.task_size IS NULL THEN
    RAISE EXCEPTION 'new tasks require an explicit size' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' AND NEW.task_size IS DISTINCT FROM OLD.task_size THEN
    RAISE EXCEPTION 'task size is immutable' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
    """)
    op.execute("""
CREATE TRIGGER task_size_guard BEFORE INSERT OR UPDATE ON public.workstream_tasks
FOR EACH ROW EXECUTE FUNCTION public.guard_task_size();
    """)
    op.execute("""
CREATE FUNCTION public.guard_task_command_size() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE original jsonb; actual_size text;
BEGIN
  IF NEW.status<>'committed' THEN RETURN NEW; END IF;
  IF TG_OP='UPDATE' AND OLD.status='committed' THEN RETURN NEW; END IF;
  SELECT task_size INTO actual_size FROM public.workstream_tasks WHERE id=NEW.task_id;
  original := CASE WHEN NEW.action_id='task.claim' THEN NEW.response->'task' ELSE NEW.response END;
  IF actual_size IS NULL OR jsonb_typeof(original->'task_size') IS DISTINCT FROM 'string'
     OR original->>'task_size' IS DISTINCT FROM actual_size THEN
    RAISE EXCEPTION 'new task commands must record the exact size' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
    """)
    op.execute("""
CREATE TRIGGER task_command_size_guard BEFORE INSERT OR UPDATE ON public.task_command_receipts
FOR EACH ROW EXECUTE FUNCTION public.guard_task_command_size();
    """)


    # The existing deferred validator owns both retained and new manifest custody.
    # Select the recorded field set before hashing; never rewrite archived bytes.
    body = op.get_bind().execute(text(
        "SELECT pg_get_functiondef('public.validate_task_import_batch_custody(uuid)'::regprocedure)"
    )).scalar_one()
    anchor = "'rejection_criteria',m.response::jsonb->'rejection_criteria')"
    if body.count(anchor) != 2:
        raise RuntimeError("task import manifest custody function shape changed")
    op.execute(body.replace(anchor, anchor + " || CASE WHEN m.response::jsonb ? 'task_size' "
        "THEN pg_catalog.jsonb_build_object('task_size',m.response::jsonb->'task_size') "
        "ELSE '{}'::jsonb END"))


def downgrade() -> None:
    raise RuntimeError("Recorded task sizes cannot be downgraded; restore a matched backup")
