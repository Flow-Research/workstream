"""cut guide source declarations to verified ART identity

Revision ID: 0048_guide_source_v2
Revises: 0047_policy_identity_lineage
Create Date: 2026-08-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0048_guide_source_v2"
down_revision = "0047_policy_identity_lineage"
branch_labels = depends_on = None


def _refuse_populated(message: str) -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "select exists(select 1 from guide_source_snapshots) "
            "or exists(select 1 from guide_source_snapshot_items)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError(message)


def upgrade() -> None:
    """Install the v2 declaration only on an empty clean-cut namespace."""
    _refuse_populated(
        "guide source v2 requires an empty guide-source namespace; "
        "reingest authoritative bytes through verified ART custody"
    )
    op.drop_constraint(
        "uq_guide_source_snapshot_items_snapshot_kind_ref",
        "guide_source_snapshot_items",
        type_="unique",
    )
    op.alter_column(
        "guide_source_snapshot_items",
        "durable_ref",
        new_column_name="source_label",
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.drop_column("guide_source_snapshot_items", "content_cid")
    op.drop_column("guide_source_snapshot_items", "content_hash")
    op.create_unique_constraint(
        "uq_guide_source_snapshot_items_snapshot_order",
        "guide_source_snapshot_items",
        ["source_snapshot_id", "item_order"],
    )
    op.drop_constraint(
        "uq_guide_sufficiency_reports_source_snapshot",
        "guide_sufficiency_reports",
        type_="unique",
    )
    op.create_index(
        "uq_guide_sufficiency_reports_verified_snapshot",
        "guide_sufficiency_reports",
        ["source_snapshot_id"],
        unique=True,
        postgresql_where=sa.text("project_setup_run_id is not null"),
    )
    op.create_index(
        "uq_guide_sufficiency_reports_diagnostic_snapshot",
        "guide_sufficiency_reports",
        ["source_snapshot_id"],
        unique=True,
        postgresql_where=sa.text("project_setup_run_id is null"),
    )
    op.add_column(
        "project_setup_runs",
        sa.Column("continuation_verification_job_id", sa.String(36)),
    )
    op.add_column(
        "project_setup_runs",
        sa.Column("continuation_started_at", sa.DateTime(timezone=True)),
    )
    op.create_foreign_key(
        "fk_project_setup_runs_continuation_verification_job",
        "project_setup_runs",
        "artifact_verification_jobs",
        ["continuation_verification_job_id"],
        ["id"],
    )
    op.create_index(
        "ix_project_setup_runs_continuation_verification_job_id",
        "project_setup_runs",
        ["continuation_verification_job_id"],
    )
    op.drop_constraint(
        op.f("ck_project_setup_runs_ck_project_setup_runs_status"),
        "project_setup_runs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_project_setup_runs_ck_project_setup_runs_status"),
        "project_setup_runs",
        "status in ('queued','dispatch_pending','enqueue_failed',"
        "'running_sufficiency_agent','sufficiency_blocked',"
        "'running_policy_derivation_agent','policy_draft_ready',"
        "'running_post_submit_derivation_agent','post_submit_setup_blocked',"
        "'post_submit_policy_compiled','setup_blocked','failed')",
    )
    op.execute(
        """
        create or replace function validate_guide_source_snapshot_items() returns trigger
        language plpgsql as $$
        declare expected jsonb; actual jsonb; reservation guide_mutation_idempotency_records%rowtype;
        begin
          select snapshot.manifest_json::jsonb->'items' into expected
            from guide_source_snapshots snapshot where snapshot.id=new.source_snapshot_id;
          if expected is null then
            raise exception 'guide source snapshot item parent is unavailable' using errcode='23514';
          end if;
          select coalesce(jsonb_agg(jsonb_build_object(
                   'item_id',id,'item_order',item_order,'source_kind',source_kind,
                   'source_label',source_label,'ingestion_adapter',ingestion_adapter,
                   'media_type',media_type) order by item_order),'[]'::jsonb)
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


def downgrade() -> None:
    """Refuse to fabricate legacy byte identity from v2 declarations."""
    _refuse_populated(
        "guide source v2 downgrade requires empty guide-source tables; "
        "legacy caller byte identity cannot be reconstructed"
    )
    op.drop_constraint(
        op.f("ck_project_setup_runs_ck_project_setup_runs_status"),
        "project_setup_runs",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_project_setup_runs_ck_project_setup_runs_status"),
        "project_setup_runs",
        "status in ('queued','enqueue_failed','running_sufficiency_agent',"
        "'sufficiency_blocked','running_policy_derivation_agent','policy_draft_ready',"
        "'running_post_submit_derivation_agent','post_submit_setup_blocked',"
        "'post_submit_policy_compiled','setup_blocked','failed')",
    )
    op.drop_index(
        "ix_project_setup_runs_continuation_verification_job_id",
        table_name="project_setup_runs",
    )
    op.drop_constraint(
        "fk_project_setup_runs_continuation_verification_job",
        "project_setup_runs",
        type_="foreignkey",
    )
    op.drop_column("project_setup_runs", "continuation_started_at")
    op.drop_column("project_setup_runs", "continuation_verification_job_id")
    op.drop_index(
        "uq_guide_sufficiency_reports_diagnostic_snapshot",
        table_name="guide_sufficiency_reports",
    )
    op.drop_index(
        "uq_guide_sufficiency_reports_verified_snapshot",
        table_name="guide_sufficiency_reports",
    )
    op.create_unique_constraint(
        "uq_guide_sufficiency_reports_source_snapshot",
        "guide_sufficiency_reports",
        ["source_snapshot_id"],
    )
    op.drop_constraint(
        "uq_guide_source_snapshot_items_snapshot_order",
        "guide_source_snapshot_items",
        type_="unique",
    )
    op.add_column(
        "guide_source_snapshot_items",
        sa.Column("content_hash", sa.String(71), nullable=False),
    )
    op.add_column(
        "guide_source_snapshot_items",
        sa.Column("content_cid", sa.String(200)),
    )
    op.alter_column(
        "guide_source_snapshot_items",
        "source_label",
        new_column_name="durable_ref",
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.create_unique_constraint(
        "uq_guide_source_snapshot_items_snapshot_kind_ref",
        "guide_source_snapshot_items",
        ["source_snapshot_id", "source_kind", "durable_ref"],
    )
    op.execute(
        """
        create or replace function validate_guide_source_snapshot_items() returns trigger
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
