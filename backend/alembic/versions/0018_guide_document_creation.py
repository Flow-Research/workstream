"""Require one atomic guide, document declaration and initial setup creation."""

from alembic import op

revision = "0018_guide_document_creation"
down_revision = "0017_task_project_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Constrain new mutations without rewriting or deleting retained evidence."""
    op.execute("""
    CREATE FUNCTION require_guide_document_creation_pair() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE
      guide_key text;
      root_row guide_mutation_idempotency_records%rowtype;
      source_row guide_mutation_idempotency_records%rowtype;
      guide_row project_guides%rowtype;
      snapshot_row guide_source_snapshots%rowtype;
      setup_row project_setup_runs%rowtype;
      expected_documents jsonb;
    BEGIN
      IF TG_TABLE_NAME = 'project_guides' THEN
        guide_key := NEW.id;
      ELSIF TG_TABLE_NAME = 'guide_source_snapshots' THEN
        guide_key := NEW.guide_id;
      ELSE
        IF NEW.action_id = 'project.guide.create' THEN
          guide_key := NEW.resource_id;
        ELSIF NEW.action_id = 'project.guide_source_snapshot.create' THEN
          SELECT guide_id INTO guide_key FROM guide_source_snapshots WHERE id=NEW.resource_id;
        ELSE RETURN NULL;
        END IF;
      END IF;
      SELECT * INTO guide_row FROM project_guides WHERE id=guide_key;
      SELECT * INTO root_row FROM guide_mutation_idempotency_records
        WHERE resource_id=guide_key AND action_id='project.guide.create';
      SELECT * INTO snapshot_row FROM guide_source_snapshots WHERE guide_id=guide_key;
      SELECT * INTO source_row FROM guide_mutation_idempotency_records
        WHERE resource_id=snapshot_row.id AND action_id='project.guide_source_snapshot.create';
      SELECT * INTO setup_row FROM project_setup_runs WHERE id=source_row.setup_run_id;
      IF guide_row.id IS NULL OR root_row.id IS NULL OR source_row.id IS NULL
         OR snapshot_row.id IS NULL OR setup_row.id IS NULL
         OR (SELECT count(*) FROM guide_source_snapshots WHERE guide_id=guide_key) <> 1
         OR (SELECT count(*) FROM guide_mutation_idempotency_records
             WHERE resource_id=guide_key AND action_id='project.guide.create') <> 1
         OR (SELECT count(*) FROM guide_mutation_idempotency_records
             WHERE resource_id=snapshot_row.id AND action_id='project.guide_source_snapshot.create') <> 1
         OR root_row.status <> 'committed' OR source_row.status <> 'committed'
         OR root_row.operation_generation <> 1 OR source_row.operation_generation <> 1
         OR snapshot_row.creation_generation <> 1
         OR (root_row.actor_profile_id,root_row.identity_link_id,root_row.project_id,root_row.idempotency_key)
            IS DISTINCT FROM
            (source_row.actor_profile_id,source_row.identity_link_id,source_row.project_id,source_row.idempotency_key)
         OR root_row.project_id IS DISTINCT FROM guide_row.project_id
         OR (snapshot_row.project_id,snapshot_row.guide_version)
            IS DISTINCT FROM (guide_row.project_id,guide_row.version)
         OR (setup_row.project_id,setup_row.guide_id,setup_row.guide_version,
             setup_row.source_snapshot_id,setup_row.source_snapshot_hash)
            IS DISTINCT FROM (guide_row.project_id,guide_row.id,guide_row.version,
                              snapshot_row.id,snapshot_row.bundle_hash)
         OR root_row.response_json::jsonb->'setup'->>'id' IS DISTINCT FROM setup_row.id
         OR root_row.response_json::jsonb->'setup'->>'status' IS DISTINCT FROM 'awaiting_documents'
         OR setup_row.status IS DISTINCT FROM 'awaiting_documents'
         OR setup_row.current_step IS DISTINCT FROM 'awaiting_documents'
         OR setup_row.documents_ready_at IS NOT NULL
         OR setup_row.celery_task_id IS NOT NULL
      THEN
        RAISE EXCEPTION 'guide document creation pair is invalid' USING ERRCODE='23514';
      END IF;
      SELECT jsonb_agg(jsonb_build_object(
        'document_id',id,'label',source_label,'media_type',media_type,'order',item_order
      ) ORDER BY item_order) INTO expected_documents
      FROM guide_source_snapshot_items WHERE source_snapshot_id=snapshot_row.id;
      IF expected_documents IS NULL
         OR root_row.response_json::jsonb->'documents' IS DISTINCT FROM expected_documents THEN
        RAISE EXCEPTION 'guide document creation response is invalid' USING ERRCODE='23514';
      END IF;
      RETURN NULL;
    END $$;
    """)
    for table in ("project_guides", "guide_source_snapshots", "guide_mutation_idempotency_records"):
        op.execute(f"""
          CREATE CONSTRAINT TRIGGER require_document_creation_pair
          AFTER INSERT ON {table}
          DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
          EXECUTE FUNCTION require_guide_document_creation_pair();
        """)


def downgrade() -> None:
    """Do not restore independent document-set creation."""
    raise RuntimeError("guide document creation custody cannot be downgraded")
