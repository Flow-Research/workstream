"""submission artifact policy foundation

Revision ID: 0006_submission_policy
Revises: 0005_checker_runs
Create Date: 2026-06-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_submission_policy"
down_revision = "0005_checker_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create guide-source snapshot and submission artifact policy tables."""
    op.create_table(
        "guide_source_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("guide_id", sa.String(length=36), nullable=False),
        sa.Column("guide_version", sa.String(length=50), nullable=False),
        sa.Column("manifest_schema_version", sa.String(length=50), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("bundle_hash", sa.String(length=71), nullable=False),
        sa.Column("captured_by", sa.String(length=100), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["guide_id"],
            ["project_guides.id"],
            name=op.f("fk_guide_source_snapshots_guide_id_project_guides"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_guide_source_snapshots_project_id_projects"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_guide_source_snapshots_project_guide",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guide_source_snapshots")),
        sa.UniqueConstraint("id", "bundle_hash", name="uq_guide_source_snapshots_id_hash"),
        sa.UniqueConstraint(
            "project_id",
            "guide_version",
            "bundle_hash",
            name="uq_guide_source_snapshots_project_version_hash",
        ),
    )
    op.create_index(
        op.f("ix_guide_source_snapshots_bundle_hash"),
        "guide_source_snapshots",
        ["bundle_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_guide_source_snapshots_guide_id"),
        "guide_source_snapshots",
        ["guide_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_guide_source_snapshots_project_id"),
        "guide_source_snapshots",
        ["project_id"],
        unique=False,
    )

    op.create_table(
        "guide_source_snapshot_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("item_order", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(length=50), nullable=False),
        sa.Column("durable_ref", sa.Text(), nullable=False),
        sa.Column("ingestion_adapter", sa.String(length=100), nullable=False),
        sa.Column("content_hash", sa.String(length=71), nullable=False),
        sa.Column("content_cid", sa.String(length=200), nullable=True),
        sa.Column("media_type", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["guide_source_snapshots.id"],
            name="fk_gssi_source_snapshot",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guide_source_snapshot_items")),
        sa.UniqueConstraint(
            "source_snapshot_id",
            "source_kind",
            "durable_ref",
            name="uq_guide_source_snapshot_items_snapshot_kind_ref",
        ),
    )
    op.create_index(
        op.f("ix_guide_source_snapshot_items_source_snapshot_id"),
        "guide_source_snapshot_items",
        ["source_snapshot_id"],
        unique=False,
    )

    op.create_table(
        "guide_sufficiency_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("guide_id", sa.String(length=36), nullable=False),
        sa.Column("guide_version", sa.String(length=50), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(length=71), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("agent_name", sa.String(length=100), nullable=True),
        sa.Column("agent_version", sa.String(length=50), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("warnings_acknowledged_by_role", sa.String(length=50), nullable=True),
        sa.Column("warnings_acknowledged_by_actor", sa.String(length=100), nullable=True),
        sa.Column("warnings_acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledgement_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('passed', 'blocked', 'passed_with_warnings')",
            name="ck_guide_sufficiency_reports_status",
        ),
        sa.ForeignKeyConstraint(
            ["guide_id"],
            ["project_guides.id"],
            name=op.f("fk_guide_sufficiency_reports_guide_id_project_guides"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_guide_sufficiency_reports_project_id_projects"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_guide_sufficiency_reports_project_guide",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id", "source_snapshot_hash"],
            ["guide_source_snapshots.id", "guide_source_snapshots.bundle_hash"],
            name="fk_guide_sufficiency_reports_source_snapshot_hash",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guide_sufficiency_reports")),
        sa.UniqueConstraint(
            "source_snapshot_id",
            name="uq_guide_sufficiency_reports_source_snapshot",
        ),
    )
    op.create_index(
        op.f("ix_guide_sufficiency_reports_guide_id"),
        "guide_sufficiency_reports",
        ["guide_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_guide_sufficiency_reports_project_id"),
        "guide_sufficiency_reports",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_guide_sufficiency_reports_source_snapshot_id"),
        "guide_sufficiency_reports",
        ["source_snapshot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_guide_sufficiency_reports_status"),
        "guide_sufficiency_reports",
        ["status"],
        unique=False,
    )

    op.create_table(
        "submission_artifact_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("guide_id", sa.String(length=36), nullable=False),
        sa.Column("guide_version", sa.String(length=50), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(length=71), nullable=False),
        sa.Column("policy_version", sa.String(length=50), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=30), nullable=False),
        sa.Column("policy_body", sa.JSON(), nullable=False),
        sa.Column("policy_hash", sa.String(length=71), nullable=False),
        sa.Column("derivation_source", sa.String(length=100), nullable=False),
        sa.Column("source_material_refs", sa.JSON(), nullable=False),
        sa.Column("derivation_agent_name", sa.String(length=100), nullable=True),
        sa.Column("derivation_agent_version", sa.String(length=50), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("approved_by_role", sa.String(length=50), nullable=True),
        sa.Column("approved_by_actor", sa.String(length=100), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_policy_id", sa.String(length=36), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "lifecycle_status in ('draft', 'approved', 'superseded')",
            name="ck_submission_artifact_policies_lifecycle_status",
        ),
        sa.CheckConstraint(
            "lifecycle_status != 'approved' or "
            "(approved_by_role in ('admin', 'project_manager') and "
            "approved_by_actor is not null and approved_at is not null)",
            name="ck_submission_artifact_policies_approval_provenance",
        ),
        sa.ForeignKeyConstraint(
            ["guide_id"],
            ["project_guides.id"],
            name=op.f("fk_submission_artifact_policies_guide_id_project_guides"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_submission_artifact_policies_project_id_projects"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_submission_artifact_policies_project_guide",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id", "source_snapshot_hash"],
            ["guide_source_snapshots.id", "guide_source_snapshots.bundle_hash"],
            name="fk_submission_artifact_policies_source_snapshot_hash",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_policy_id"],
            ["submission_artifact_policies.id"],
            name="fk_sap_supersedes_policy",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submission_artifact_policies")),
        sa.UniqueConstraint(
            "id",
            "policy_hash",
            name="uq_submission_artifact_policies_id_hash",
        ),
        sa.UniqueConstraint(
            "project_id",
            "guide_version",
            "policy_version",
            name="uq_submission_artifact_policies_project_version_policy",
        ),
    )
    op.create_index(
        op.f("ix_submission_artifact_policies_guide_id"),
        "submission_artifact_policies",
        ["guide_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_submission_artifact_policies_lifecycle_status"),
        "submission_artifact_policies",
        ["lifecycle_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_submission_artifact_policies_policy_hash"),
        "submission_artifact_policies",
        ["policy_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_submission_artifact_policies_project_id"),
        "submission_artifact_policies",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_submission_artifact_policies_source_snapshot_id"),
        "submission_artifact_policies",
        ["source_snapshot_id"],
        unique=False,
    )
    op.create_table(
        "effective_project_submission_artifact_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("guide_id", sa.String(length=36), nullable=False),
        sa.Column("guide_version", sa.String(length=50), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(length=71), nullable=False),
        sa.Column("submission_artifact_policy_id", sa.String(length=36), nullable=False),
        sa.Column("submission_artifact_policy_hash", sa.String(length=71), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=30), nullable=False),
        sa.Column("merge_algorithm_version", sa.String(length=50), nullable=False),
        sa.Column("effective_policy", sa.JSON(), nullable=False),
        sa.Column("effective_policy_hash", sa.String(length=71), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("supersedes_effective_policy_id", sa.String(length=36), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "lifecycle_status in ('approved', 'superseded')",
            name="ck_effective_psap_lifecycle_status",
        ),
        sa.ForeignKeyConstraint(
            ["guide_id"],
            ["project_guides.id"],
            name="fk_effective_psap_guide",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_effective_psap_project",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_effective_project_submission_artifact_policies_project_guide",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id", "source_snapshot_hash"],
            ["guide_source_snapshots.id", "guide_source_snapshots.bundle_hash"],
            name="fk_effective_psap_source_snapshot_hash",
        ),
        sa.ForeignKeyConstraint(
            ["submission_artifact_policy_id", "submission_artifact_policy_hash"],
            ["submission_artifact_policies.id", "submission_artifact_policies.policy_hash"],
            name="fk_effective_psap_submission_policy_hash",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_effective_policy_id"],
            ["effective_project_submission_artifact_policies.id"],
            name="fk_effective_psap_supersedes",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_effective_project_submission_artifact_policies"),
        ),
        sa.UniqueConstraint(
            "id",
            "effective_policy_hash",
            name="uq_effective_project_submission_artifact_policies_id_hash",
        ),
    )
    op.create_index(
        "ix_effective_psap_effective_hash",
        "effective_project_submission_artifact_policies",
        ["effective_policy_hash"],
        unique=False,
    )
    op.create_index(
        "ix_effective_psap_guide",
        "effective_project_submission_artifact_policies",
        ["guide_id"],
        unique=False,
    )
    op.create_index(
        "ix_effective_psap_lifecycle",
        "effective_project_submission_artifact_policies",
        ["lifecycle_status"],
        unique=False,
    )
    op.create_index(
        "ix_effective_psap_project",
        "effective_project_submission_artifact_policies",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_effective_psap_source_snapshot",
        "effective_project_submission_artifact_policies",
        ["source_snapshot_id"],
        unique=False,
    )
    op.create_index(
        "ix_effective_psap_submission_policy",
        "effective_project_submission_artifact_policies",
        ["submission_artifact_policy_id"],
        unique=False,
    )
    op.create_table(
        "pre_submit_checker_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("guide_id", sa.String(length=36), nullable=False),
        sa.Column("guide_version", sa.String(length=50), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(length=71), nullable=False),
        sa.Column("effective_policy_id", sa.String(length=36), nullable=False),
        sa.Column("effective_policy_hash", sa.String(length=71), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=30), nullable=False),
        sa.Column("compiler_version", sa.String(length=50), nullable=True),
        sa.Column("compiled_bundle", sa.JSON(), nullable=True),
        sa.Column("compiled_bundle_hash", sa.String(length=71), nullable=True),
        sa.Column("checker_names", sa.JSON(), nullable=False),
        sa.Column("checker_configs", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("supersedes_pre_submit_checker_policy_id", sa.String(length=36), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "lifecycle_status in ('pending_compilation', 'compiled', 'superseded')",
            name="ck_pre_submit_checker_policies_lifecycle_status",
        ),
        sa.CheckConstraint(
            "lifecycle_status != 'compiled' or "
            "(compiler_version is not null and compiled_bundle is not null and "
            "compiled_bundle_hash is not null and "
            "compiled_bundle_hash ~ '^sha256:[0-9a-f]{64}$')",
            name="ck_pre_submit_checker_policies_compiled_fields",
        ),
        sa.ForeignKeyConstraint(
            ["effective_policy_id", "effective_policy_hash"],
            [
                "effective_project_submission_artifact_policies.id",
                "effective_project_submission_artifact_policies.effective_policy_hash",
            ],
            name="fk_pre_submit_checker_policies_effective_hash",
        ),
        sa.ForeignKeyConstraint(
            ["guide_id"],
            ["project_guides.id"],
            name="fk_pre_submit_checker_policies_guide",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_pre_submit_checker_policies_project",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "guide_version"],
            ["project_guides.project_id", "project_guides.version"],
            name="fk_pre_submit_checker_policies_project_guide",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id", "source_snapshot_hash"],
            ["guide_source_snapshots.id", "guide_source_snapshots.bundle_hash"],
            name="fk_pre_submit_checker_policies_source_snapshot_hash",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_pre_submit_checker_policy_id"],
            ["pre_submit_checker_policies.id"],
            name="fk_pre_submit_checker_policies_supersedes",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pre_submit_checker_policies")),
    )
    op.create_index(
        "ix_pre_submit_checker_compiled_hash",
        "pre_submit_checker_policies",
        ["compiled_bundle_hash"],
        unique=False,
    )
    op.create_index(
        "ix_pre_submit_checker_effective",
        "pre_submit_checker_policies",
        ["effective_policy_id"],
        unique=False,
    )
    op.create_index(
        "ix_pre_submit_checker_effective_hash",
        "pre_submit_checker_policies",
        ["effective_policy_hash"],
        unique=False,
    )
    op.create_index(
        "ix_pre_submit_checker_guide",
        "pre_submit_checker_policies",
        ["guide_id"],
        unique=False,
    )
    op.create_index(
        "ix_pre_submit_checker_lifecycle",
        "pre_submit_checker_policies",
        ["lifecycle_status"],
        unique=False,
    )
    op.create_index(
        "ix_pre_submit_checker_project",
        "pre_submit_checker_policies",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_pre_submit_checker_source_snapshot",
        "pre_submit_checker_policies",
        ["source_snapshot_id"],
        unique=False,
    )

def downgrade() -> None:
    """Drop submission artifact policy tables in dependency order."""
    op.drop_index(
        "ix_pre_submit_checker_source_snapshot",
        table_name="pre_submit_checker_policies",
    )
    op.drop_index(
        "ix_pre_submit_checker_project",
        table_name="pre_submit_checker_policies",
    )
    op.drop_index(
        "ix_pre_submit_checker_lifecycle",
        table_name="pre_submit_checker_policies",
    )
    op.drop_index(
        "ix_pre_submit_checker_guide",
        table_name="pre_submit_checker_policies",
    )
    op.drop_index(
        "ix_pre_submit_checker_effective_hash",
        table_name="pre_submit_checker_policies",
    )
    op.drop_index(
        "ix_pre_submit_checker_effective",
        table_name="pre_submit_checker_policies",
    )
    op.drop_index(
        "ix_pre_submit_checker_compiled_hash",
        table_name="pre_submit_checker_policies",
    )
    op.drop_table("pre_submit_checker_policies")

    op.drop_index(
        "ix_effective_psap_submission_policy",
        table_name="effective_project_submission_artifact_policies",
    )
    op.drop_index(
        "ix_effective_psap_source_snapshot",
        table_name="effective_project_submission_artifact_policies",
    )
    op.drop_index(
        "ix_effective_psap_project",
        table_name="effective_project_submission_artifact_policies",
    )
    op.drop_index(
        "ix_effective_psap_lifecycle",
        table_name="effective_project_submission_artifact_policies",
    )
    op.drop_index(
        "ix_effective_psap_guide",
        table_name="effective_project_submission_artifact_policies",
    )
    op.drop_index(
        "ix_effective_psap_effective_hash",
        table_name="effective_project_submission_artifact_policies",
    )
    op.drop_table("effective_project_submission_artifact_policies")

    op.drop_index(
        op.f("ix_submission_artifact_policies_source_snapshot_id"),
        table_name="submission_artifact_policies",
    )
    op.drop_index(
        op.f("ix_submission_artifact_policies_project_id"),
        table_name="submission_artifact_policies",
    )
    op.drop_index(
        op.f("ix_submission_artifact_policies_policy_hash"),
        table_name="submission_artifact_policies",
    )
    op.drop_index(
        op.f("ix_submission_artifact_policies_lifecycle_status"),
        table_name="submission_artifact_policies",
    )
    op.drop_index(
        op.f("ix_submission_artifact_policies_guide_id"),
        table_name="submission_artifact_policies",
    )
    op.drop_table("submission_artifact_policies")

    op.drop_index(
        op.f("ix_guide_sufficiency_reports_status"),
        table_name="guide_sufficiency_reports",
    )
    op.drop_index(
        op.f("ix_guide_sufficiency_reports_source_snapshot_id"),
        table_name="guide_sufficiency_reports",
    )
    op.drop_index(
        op.f("ix_guide_sufficiency_reports_project_id"),
        table_name="guide_sufficiency_reports",
    )
    op.drop_index(
        op.f("ix_guide_sufficiency_reports_guide_id"),
        table_name="guide_sufficiency_reports",
    )
    op.drop_table("guide_sufficiency_reports")

    op.drop_index(
        op.f("ix_guide_source_snapshot_items_source_snapshot_id"),
        table_name="guide_source_snapshot_items",
    )
    op.drop_table("guide_source_snapshot_items")

    op.drop_index(
        op.f("ix_guide_source_snapshots_project_id"),
        table_name="guide_source_snapshots",
    )
    op.drop_index(
        op.f("ix_guide_source_snapshots_guide_id"),
        table_name="guide_source_snapshots",
    )
    op.drop_index(
        op.f("ix_guide_source_snapshots_bundle_hash"),
        table_name="guide_source_snapshots",
    )
    op.drop_table("guide_source_snapshots")
