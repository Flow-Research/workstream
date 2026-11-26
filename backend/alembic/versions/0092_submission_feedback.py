"""Store optional feedback and server-selected intake lineage without rewriting history."""

from alembic import op
from sqlalchemy import text

revision = "0092_submission_feedback"
down_revision = "0091_qualified_aws_source"
branch_labels = None
depends_on = None


def _definition(signature):
    return op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": signature}).scalar_one()


def _replace(definition, before, after, *, expected=1):
    if definition.count(before) != expected:
        raise RuntimeError("submission feedback predecessor guard changed")
    return definition.replace(before, after)


def _intake_guard():
    definition = _definition("public.guard_submission_intake_mutation()")
    start = definition.index("    IF NOT (m ?& ARRAY")
    end = definition.index(" THEN", definition.index("!~ '^sha256:[0-9a-f]{64}$'", start))
    definition = definition[:start] + """    IF NOT (m ?& ARRAY['task_id','assignment_id','feedback','predecessor_submission_id',
        'revision_preparation_id','revision_preparation_sha256'])
       OR m - ARRAY['task_id','assignment_id','feedback','predecessor_submission_id',
        'revision_preparation_id','revision_preparation_sha256'] <> '{}'::jsonb
       OR m->>'task_id' IS DISTINCT FROM NEW.task_id::text
       OR m->>'assignment_id' IS DISTINCT FROM NEW.assignment_id::text
       OR jsonb_typeof(m->'feedback') NOT IN ('string','null')
       OR octet_length(m->>'feedback')>4096
       OR (m->>'feedback') COLLATE "C" ~ '[^ -~]'
       OR btrim(m->>'feedback') IS DISTINCT FROM m->>'feedback'
       OR (NEW.eligible_task_status='needs_revision')<>(m->>'predecessor_submission_id' IS NOT NULL)
       OR (NEW.eligible_task_status='needs_revision')<>(m->>'revision_preparation_id' IS NOT NULL)
       OR ((m->>'revision_preparation_id' IS NULL)<>(m->>'revision_preparation_sha256' IS NULL))
       OR (m->>'revision_preparation_sha256' IS NOT NULL AND
           m->>'revision_preparation_sha256' !~ '^sha256:[0-9a-f]{64}$')""" + definition[end:]
    definition = _replace(
        definition,
        "m || jsonb_build_object('schema_version','workstream.submission_intake_metadata.v1')",
        "(m - ARRAY['predecessor_submission_id','revision_preparation_id','revision_preparation_sha256'])"
        " || jsonb_build_object('schema_version','workstream.submission_intake_metadata.v2')",
    )
    op.execute(definition)


def _pre_guard():
    definition = _definition("public.require_selected_pre_source(public.selected_pre_submit_runs)")
    definition = _replace(
        definition,
        "jsonb_build_object(\n      'summary',o.command_metadata->>'summary',\n"
        "      'contributor_attestation',o.command_metadata->>'contributor_attestation')",
        "public.submission_operation_checker_packet(o.command_metadata)",
    )
    definition = _replace(
        definition,
        "jsonb_build_object('summary',o.command_metadata->>'summary',\n"
        "      'contributor_attestation',o.command_metadata->>'contributor_attestation')",
        "public.submission_operation_checker_packet(o.command_metadata)",
    )
    definition = _replace(
        definition,
        "    OR request->'admission_lineage'->>'rules_sha256' IS DISTINCT FROM",
        "    OR request->'admission_lineage'->>'predecessor_submission_id' IS DISTINCT FROM\n"
        "       o.command_metadata->>'predecessor_submission_id'\n"
        "    OR (o.command_metadata ? 'feedback' AND (\n"
        "       request->'admission_lineage'->>'revision_preparation_id' IS DISTINCT FROM\n"
        "         o.command_metadata->>'revision_preparation_id' OR\n"
        "       request->'admission_lineage'->>'revision_preparation_sha256' IS DISTINCT FROM\n"
        "         o.command_metadata->>'revision_preparation_sha256'))\n"
        "    OR request->'admission_lineage'->>'rules_sha256' IS DISTINCT FROM",
    )
    op.execute(definition)


def _submission_guards():
    packet = _definition("public.validate_submission_packet_custody()")
    packet = _replace(packet, "    expected_packet text;", "    expected_packet text;\n    metadata jsonb;")
    packet = _replace(
        packet,
        "    SELECT coalesce(evidence.packet_sha256,admission.packet_sha256)\n      INTO expected_packet",
        "    SELECT coalesce(evidence.packet_sha256,admission.packet_sha256),operation.command_metadata\n"
        "      INTO expected_packet,metadata",
    )
    packet = _replace(
        packet,
        "     WHERE admission.id = stored.submission_bundle_admission_id;",
        "      LEFT JOIN public.submission_intake_operations operation ON operation.id=admission.source_operation_id\n"
        "     WHERE admission.id = stored.submission_bundle_admission_id;\n"
        "    IF stored.feedback IS DISTINCT FROM metadata->>'feedback' OR (metadata ? 'feedback' "
        "AND (stored.summary IS NOT NULL OR stored.worker_attestation IS NOT NULL)) THEN\n"
        "        RAISE EXCEPTION 'submission feedback differs from the accepted command' USING ERRCODE='23514';\n"
        "    END IF;",
    )
    packet = _replace(
        packet,
        "pg_catalog.jsonb_build_object(\n"
        "            'summary', stored.summary, 'contributor_attestation', stored.worker_attestation\n"
        "        )",
        "CASE WHEN stored.summary IS NULL THEN '{}'::jsonb ELSE pg_catalog.jsonb_build_object(\n"
        "            'summary', stored.summary, 'contributor_attestation', stored.worker_attestation\n"
        "        ) END",
    )
    op.execute(packet)
    dispatch = _definition("public.submission_dispatch_valid(public.submission_dispatches)")
    dispatch = _replace(
        dispatch,
        "'predecessor_submission_id',s.supersedes_submission_id,'summary',s.summary,"
        "'contributor_attestation',s.worker_attestation)))",
        "'predecessor_submission_id',s.supersedes_submission_id) || CASE WHEN s.summary IS NULL\n"
        "       THEN pg_catalog.jsonb_build_object('feedback',s.feedback)\n"
        "       ELSE pg_catalog.jsonb_build_object('summary',s.summary,"
        "'contributor_attestation',s.worker_attestation) END))",
    )
    op.execute(dispatch)


def upgrade() -> None:
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.submission_intake_operations, public.selected_pre_submit_runs,"
               " public.submissions, public.submission_dispatches IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        ALTER TABLE public.submissions
          ADD COLUMN feedback text,
          ALTER COLUMN summary DROP NOT NULL,
          ALTER COLUMN worker_attestation DROP NOT NULL,
          ADD CONSTRAINT ck_submissions_feedback_shape CHECK (
            (summary IS NULL)=(worker_attestation IS NULL)
            AND (feedback IS NULL OR (summary IS NULL AND octet_length(feedback)<=4096
              AND feedback COLLATE "C" !~ '[^ -~]' AND btrim(feedback)=feedback))
          );

        CREATE FUNCTION public.guard_submission_feedback()
        RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
        BEGIN
          IF NEW.feedback IS DISTINCT FROM OLD.feedback
             OR NEW.summary IS DISTINCT FROM OLD.summary
             OR NEW.worker_attestation IS DISTINCT FROM OLD.worker_attestation THEN
            RAISE EXCEPTION 'submission input is immutable' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$;

        CREATE TRIGGER submission_feedback_immutable
        BEFORE UPDATE OF feedback,summary,worker_attestation ON public.submissions
        FOR EACH ROW EXECUTE FUNCTION public.guard_submission_feedback();

        CREATE FUNCTION public.submission_operation_checker_packet(metadata jsonb)
        RETURNS jsonb LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog,public,pg_temp AS $$
          SELECT CASE WHEN metadata ? 'feedback' THEN '{}'::jsonb
            ELSE jsonb_build_object('summary',metadata->>'summary',
                    'contributor_attestation',metadata->>'contributor_attestation') END
        $$;
    """)
    _intake_guard()
    _pre_guard()
    acceptance = _definition("public.require_submission_acceptance_current(public.submission_intake_operations)")
    op.execute(_replace(
        acceptance,
        " IF o.eligible_task_status='in_progress' THEN",
        " IF o.command_metadata ? 'feedback' AND NOT EXISTS (\n"
        "   SELECT 1 FROM public.workstream_tasks t WHERE t.id=o.task_id\n"
        "     AND public.submission_intake_task_snapshot(t)=o.locked_task_context\n"
        " ) THEN RAISE EXCEPTION 'accepted task context changed' USING ERRCODE='23514'; END IF;\n"
        " IF o.eligible_task_status='in_progress' THEN",
    ))
    _submission_guards()


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
