"""bind guide sufficiency reports to exact extraction usages

Revision ID: 0046_guide_sufficiency
Revises: 0045_guide_metadata_authority
Create Date: 2026-08-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0046_guide_sufficiency"
down_revision = "0045_guide_metadata_authority"
branch_labels = depends_on = None


def upgrade() -> None:
    """Install normalized exact extraction provenance for agent reports."""
    op.create_unique_constraint(
        "uq_guide_extraction_usages_exact_provenance",
        "guide_source_extraction_usages",
        [
            "id",
            "source_item_id",
            "binding_id",
            "content_id",
            "extraction_attempt_id",
            "extracted_content_id",
            "project_setup_run_id",
            "setup_generation",
        ],
    )
    op.add_column(
        "project_setup_runs", sa.Column("error_artifact_incident_id", sa.String(36))
    )
    op.create_foreign_key(
        "fk_project_setup_runs_artifact_incident",
        "project_setup_runs",
        "guide_source_artifact_incidents",
        ["error_artifact_incident_id"],
        ["id"],
        use_alter=True,
    )
    op.create_index(
        "ix_project_setup_runs_error_artifact_incident_id",
        "project_setup_runs",
        ["error_artifact_incident_id"],
    )
    for name, column in (
        ("project_setup_run_id", sa.String(36)),
        ("setup_generation", sa.BigInteger),
        ("agent_material_sha256", sa.String(71)),
        ("agent_material_byte_count", sa.BigInteger),
    ):
        op.add_column("guide_sufficiency_reports", sa.Column(name, column))
    op.create_foreign_key(
        "fk_sufficiency_reports_setup_run",
        "guide_sufficiency_reports",
        "project_setup_runs",
        ["project_setup_run_id"],
        ["id"],
        use_alter=True,
    )
    op.create_index(
        "ix_guide_sufficiency_reports_project_setup_run_id",
        "guide_sufficiency_reports",
        ["project_setup_run_id"],
    )
    for name, condition in (
        (
            "ck_guide_sufficiency_reports_generation_positive",
            "setup_generation is null or setup_generation > 0",
        ),
        (
            "ck_guide_sufficiency_reports_material_sha256",
            "agent_material_sha256 is null or "
            "agent_material_sha256 ~ '^sha256:[0-9a-f]{64}$'",
        ),
        (
            "ck_guide_sufficiency_reports_material_size",
            "agent_material_byte_count is null or agent_material_byte_count >= 0",
        ),
        (
            "ck_guide_sufficiency_reports_material_provenance_shape",
            "(project_setup_run_id is null and setup_generation is null "
            "and agent_material_sha256 is null and agent_material_byte_count is null) or "
            "(project_setup_run_id is not null and setup_generation is not null "
            "and agent_material_sha256 is not null and agent_material_byte_count is not null)",
        ),
    ):
        op.create_check_constraint(name, "guide_sufficiency_reports", condition)
    op.create_table(
        "guide_sufficiency_report_source_usages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "report_id",
            sa.String(36),
            sa.ForeignKey("guide_sufficiency_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_order", sa.Integer, nullable=False),
        sa.Column("source_item_id", sa.String(36), nullable=False),
        sa.Column("binding_id", sa.String(36), nullable=False),
        sa.Column("content_id", sa.String(36), nullable=False),
        sa.Column("extraction_usage_id", sa.String(36), nullable=False),
        sa.Column("extraction_attempt_id", sa.String(36), nullable=False),
        sa.Column("extracted_content_id", sa.String(36), nullable=False),
        sa.Column("project_setup_run_id", sa.String(36), nullable=False),
        sa.Column("setup_generation", sa.BigInteger, nullable=False),
        sa.Column("canonical_output_sha256", sa.String(71), nullable=False),
        sa.ForeignKeyConstraint(
            [
                "extraction_usage_id",
                "source_item_id",
                "binding_id",
                "content_id",
                "extraction_attempt_id",
                "extracted_content_id",
                "project_setup_run_id",
                "setup_generation",
            ],
            [
                "guide_source_extraction_usages.id",
                "guide_source_extraction_usages.source_item_id",
                "guide_source_extraction_usages.binding_id",
                "guide_source_extraction_usages.content_id",
                "guide_source_extraction_usages.extraction_attempt_id",
                "guide_source_extraction_usages.extracted_content_id",
                "guide_source_extraction_usages.project_setup_run_id",
                "guide_source_extraction_usages.setup_generation",
            ],
            name="fk_sufficiency_report_source_usage_exact_extraction",
        ),
        sa.UniqueConstraint("report_id", "item_order", name="uq_sufficiency_report_item_order"),
        sa.UniqueConstraint(
            "report_id", "extraction_usage_id", name="uq_sufficiency_report_extraction_usage"
        ),
        sa.CheckConstraint("item_order >= 0", name="ck_sufficiency_report_item_order"),
        sa.CheckConstraint(
            "setup_generation > 0", name="ck_sufficiency_report_usage_generation"
        ),
        sa.CheckConstraint(
            "canonical_output_sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_sufficiency_report_output_sha256",
        ),
    )
    op.create_index(
        "ix_sufficiency_report_source_usage_report_id",
        "guide_sufficiency_report_source_usages",
        ["report_id"],
    )


def downgrade() -> None:
    """Remove guide sufficiency extraction provenance."""
    op.drop_index(
        "ix_sufficiency_report_source_usage_report_id",
        table_name="guide_sufficiency_report_source_usages",
    )
    op.drop_table("guide_sufficiency_report_source_usages")
    op.drop_index(
        "ix_project_setup_runs_error_artifact_incident_id",
        table_name="project_setup_runs",
    )
    op.drop_constraint(
        "fk_project_setup_runs_artifact_incident", "project_setup_runs", type_="foreignkey"
    )
    op.drop_column("project_setup_runs", "error_artifact_incident_id")
    op.drop_index(
        "ix_guide_sufficiency_reports_project_setup_run_id",
        table_name="guide_sufficiency_reports",
    )
    op.drop_constraint(
        "fk_sufficiency_reports_setup_run", "guide_sufficiency_reports", type_="foreignkey"
    )
    for name in (
        "ck_guide_sufficiency_reports_material_provenance_shape",
        "ck_guide_sufficiency_reports_material_size",
        "ck_guide_sufficiency_reports_material_sha256",
        "ck_guide_sufficiency_reports_generation_positive",
    ):
        op.drop_constraint(name, "guide_sufficiency_reports", type_="check")
    for name in (
        "agent_material_byte_count",
        "agent_material_sha256",
        "setup_generation",
        "project_setup_run_id",
    ):
        op.drop_column("guide_sufficiency_reports", name)
    op.drop_constraint(
        "uq_guide_extraction_usages_exact_provenance",
        "guide_source_extraction_usages",
        type_="unique",
    )
