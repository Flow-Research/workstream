"""add bounded guide extraction provenance

Revision ID: 0042_guide_extraction
Revises: 0041_project_mutation_evidence
Create Date: 2026-07-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0042_guide_extraction"
down_revision = "0041_project_mutation_evidence"
branch_labels = depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_guide_bindings_extraction_attempt_lineage",
        "guide_source_artifact_bindings",
        ["id", "content_id", "setup_generation"],
    )
    op.create_unique_constraint(
        "uq_guide_bindings_extraction_lineage",
        "guide_source_artifact_bindings",
        ["id", "content_id", "source_item_id", "project_setup_run_id", "setup_generation"],
    )
    op.create_unique_constraint(
        "uq_guide_classifications_extraction_lineage",
        "guide_source_format_classifications",
        ["id", "binding_id", "content_id", "setup_generation"],
    )
    op.create_table(
        "guide_source_extraction_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("binding_id", sa.String(36), nullable=False),
        sa.Column("content_id", sa.String(36), nullable=False),
        sa.Column("classification_id", sa.String(36), nullable=False),
        sa.Column("setup_generation", sa.BigInteger(), nullable=False),
        sa.Column("detected_format", sa.String(40), nullable=False),
        sa.Column("extractor_name", sa.String(100), nullable=False),
        sa.Column("extractor_version", sa.String(40), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("attempt_number", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("bounded_facts", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["binding_id", "content_id", "setup_generation"],
            [
                "guide_source_artifact_bindings.id",
                "guide_source_artifact_bindings.content_id",
                "guide_source_artifact_bindings.setup_generation",
            ],
            name="fk_guide_extraction_attempts_exact_binding",
        ),
        sa.ForeignKeyConstraint(
            ["classification_id", "binding_id", "content_id", "setup_generation"],
            [
                "guide_source_format_classifications.id",
                "guide_source_format_classifications.binding_id",
                "guide_source_format_classifications.content_id",
                "guide_source_format_classifications.setup_generation",
            ],
            name="fk_guide_extraction_attempts_exact_classification",
        ),
        sa.UniqueConstraint(
            "binding_id", "policy_version", "attempt_number", name="uq_guide_extraction_attempts"
        ),
        sa.UniqueConstraint(
            "id",
            "binding_id",
            "content_id",
            "setup_generation",
            "status",
            name="uq_guide_extraction_attempts_exact_usage",
        ),
        sa.CheckConstraint("attempt_number > 0", name="ck_guide_extraction_attempts_number"),
        sa.CheckConstraint(
            "(status = 'extracted') = (error_code is null)",
            name="ck_guide_extraction_attempts_error",
        ),
        sa.CheckConstraint(
            "status in ('extracted','unsupported','ambiguous','malformed','limit_exceeded','parser_failure','cancelled','artifact_incident')",
            name="ck_guide_extraction_attempts_status",
        ),
    )
    op.create_table(
        "guide_source_extracted_contents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "content_id",
            sa.String(36),
            sa.ForeignKey("artifact_contents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("detected_format", sa.String(40), nullable=False),
        sa.Column("extractor_name", sa.String(100), nullable=False),
        sa.Column("extractor_version", sa.String(40), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("source_sha256", sa.String(71), nullable=False),
        sa.Column("source_byte_count", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("output_sha256", sa.String(71), nullable=False),
        sa.Column("canonical_output", sa.Text(), nullable=False),
        sa.Column("omission_facts", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "content_id",
            "detected_format",
            "extractor_name",
            "extractor_version",
            "policy_version",
            name="uq_guide_extracted_contents_identity",
        ),
        sa.UniqueConstraint("id", "content_id", name="uq_guide_extracted_contents_exact_usage"),
        sa.CheckConstraint("status = 'extracted'", name="ck_guide_extracted_contents_status"),
        sa.CheckConstraint(
            "source_sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_guide_extracted_contents_source_sha256",
        ),
        sa.CheckConstraint(
            "output_sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_guide_extracted_contents_output_sha256",
        ),
        sa.CheckConstraint(
            "source_byte_count >= 0", name="ck_guide_extracted_contents_source_size"
        ),
        sa.CheckConstraint(
            "octet_length(canonical_output) <= 4194304",
            name="ck_guide_extracted_contents_output_size",
        ),
    )
    op.create_table(
        "guide_source_extraction_retry_budgets",
        sa.Column("binding_id", sa.String(36), primary_key=True),
        sa.Column("content_id", sa.String(36), nullable=False),
        sa.Column("classification_id", sa.String(36), nullable=False),
        sa.Column("setup_generation", sa.BigInteger(), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("claimed_slots", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["binding_id", "content_id", "setup_generation"],
            ["guide_source_artifact_bindings.id", "guide_source_artifact_bindings.content_id", "guide_source_artifact_bindings.setup_generation"],
            name="fk_guide_extraction_retry_budgets_exact_binding",
        ),
        sa.ForeignKeyConstraint(
            ["classification_id", "binding_id", "content_id", "setup_generation"],
            ["guide_source_format_classifications.id", "guide_source_format_classifications.binding_id", "guide_source_format_classifications.content_id", "guide_source_format_classifications.setup_generation"],
            name="fk_guide_extraction_retry_budgets_exact_classification",
        ),
        sa.CheckConstraint("claimed_slots between 1 and 2", name="ck_guide_extraction_retry_budgets_slots"),
    )
    op.create_table(
        "guide_source_extraction_usages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("extracted_content_id", sa.String(36), nullable=False),
        sa.Column("extraction_attempt_id", sa.String(36), nullable=False),
        sa.Column("attempt_status", sa.String(40), nullable=False),
        sa.Column("binding_id", sa.String(36), nullable=False),
        sa.Column("content_id", sa.String(36), nullable=False),
        sa.Column("source_item_id", sa.String(36), nullable=False),
        sa.Column("project_setup_run_id", sa.String(36), nullable=False),
        sa.Column("setup_generation", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            [
                "binding_id",
                "content_id",
                "source_item_id",
                "project_setup_run_id",
                "setup_generation",
            ],
            [
                "guide_source_artifact_bindings.id",
                "guide_source_artifact_bindings.content_id",
                "guide_source_artifact_bindings.source_item_id",
                "guide_source_artifact_bindings.project_setup_run_id",
                "guide_source_artifact_bindings.setup_generation",
            ],
            name="fk_guide_extraction_usages_exact_binding",
        ),
        sa.ForeignKeyConstraint(
            [
                "extraction_attempt_id",
                "binding_id",
                "content_id",
                "setup_generation",
                "attempt_status",
            ],
            [
                "guide_source_extraction_attempts.id",
                "guide_source_extraction_attempts.binding_id",
                "guide_source_extraction_attempts.content_id",
                "guide_source_extraction_attempts.setup_generation",
                "guide_source_extraction_attempts.status",
            ],
            name="fk_guide_extraction_usages_exact_attempt",
        ),
        sa.ForeignKeyConstraint(
            ["extracted_content_id", "content_id"],
            ["guide_source_extracted_contents.id", "guide_source_extracted_contents.content_id"],
            name="fk_guide_extraction_usages_exact_content",
        ),
        sa.UniqueConstraint(
            "binding_id", "extracted_content_id", name="uq_guide_extraction_usages"
        ),
        sa.CheckConstraint(
            "attempt_status = 'extracted'",
            name="ck_guide_extraction_usages_successful_attempt",
        ),
    )
    for table, columns in {
        "guide_source_extraction_attempts": ("binding_id", "content_id"),
        "guide_source_extracted_contents": ("content_id",),
        "guide_source_extraction_usages": (
            "extracted_content_id",
            "binding_id",
            "content_id",
            "source_item_id",
            "project_setup_run_id",
        ),
    }.items():
        for column in columns:
            op.create_index(op.f(f"ix_{table}_{column}"), table, [column])


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "lock table guide_source_extraction_usages, guide_source_extracted_contents, guide_source_extraction_retry_budgets, guide_source_extraction_attempts in access exclusive mode"
        )
    )
    if bind.execute(
        sa.text(
            "select exists(select 1 from guide_source_extraction_usages) or exists(select 1 from guide_source_extracted_contents) or exists(select 1 from guide_source_extraction_attempts) or exists(select 1 from guide_source_extraction_retry_budgets)"
        )
    ).scalar_one():
        raise RuntimeError("cannot downgrade populated guide extraction evidence")
    op.drop_table("guide_source_extraction_usages")
    op.drop_table("guide_source_extraction_retry_budgets")
    op.drop_table("guide_source_extracted_contents")
    op.drop_table("guide_source_extraction_attempts")
    op.drop_constraint(
        "uq_guide_classifications_extraction_lineage",
        "guide_source_format_classifications",
        type_="unique",
    )
    op.drop_constraint(
        "uq_guide_bindings_extraction_lineage", "guide_source_artifact_bindings", type_="unique"
    )
    op.drop_constraint(
        "uq_guide_bindings_extraction_attempt_lineage",
        "guide_source_artifact_bindings",
        type_="unique",
    )
