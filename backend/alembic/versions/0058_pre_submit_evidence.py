"""install immutable pre-submit execution evidence

Revision ID: 0058_pre_submit_evidence
Revises: 0057_submission_policy_authority
Create Date: 2026-08-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0058_pre_submit_evidence"
down_revision = "0057_submission_policy_authority"
branch_labels = depends_on = None

_SHA256 = r"^sha256:[0-9a-f]{64}$"


def _immutable_guard(table: str) -> None:
    op.execute(
        f"""
        create function guard_{table}_immutable() returns trigger language plpgsql as $$
        begin
          raise exception '{table} rows are immutable' using errcode='55000';
        end;
        $$
        """
    )
    op.execute(
        f"create trigger {table}_immutable before update or delete on {table} "
        f"for each row execute function guard_{table}_immutable()"
    )
    op.execute(
        f"create trigger {table}_no_truncate before truncate on {table} "
        f"for each statement execute function guard_{table}_immutable()"
    )


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_actor_identity_links_id_profile",
        "actor_identity_links",
        ["id", "actor_profile_id"],
    )
    op.create_unique_constraint(
        "uq_workstream_tasks_id_project", "workstream_tasks", ["id", "project_id"]
    )
    op.create_unique_constraint(
        "uq_task_assignments_id_task_contributor",
        "task_assignments",
        ["id", "task_id", "contributor_id"],
    )
    op.create_table(
        "pre_submit_evidence_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("operation_identity", sa.String(71), nullable=False),
        sa.Column("actor_profile_id", sa.String(36), nullable=False),
        sa.Column("identity_link_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("assignment_id", sa.String(36), nullable=False),
        sa.Column("predecessor_submission_id", sa.String(36)),
        sa.Column("predecessor_submission_version", sa.Integer()),
        sa.Column("prepared_generation_id", sa.String(36), nullable=False),
        sa.Column("archive_sha256", sa.String(71), nullable=False),
        sa.Column("archive_byte_count", sa.BigInteger(), nullable=False),
        sa.Column("semantic_manifest_id", sa.String(36), nullable=False),
        sa.Column("semantic_manifest_sha256", sa.String(71), nullable=False),
        sa.Column("guide_id", sa.String(36), nullable=False),
        sa.Column("guide_version", sa.String(50), nullable=False),
        sa.Column("source_snapshot_id", sa.String(36), nullable=False),
        sa.Column("source_snapshot_sha256", sa.String(71), nullable=False),
        sa.Column("locked_guide_sha256", sa.String(71), nullable=False),
        sa.Column("effective_policy_id", sa.String(36), nullable=False),
        sa.Column("locked_artifact_policy_sha256", sa.String(71), nullable=False),
        sa.Column("pre_submit_policy_id", sa.String(36), nullable=False),
        sa.Column("locked_checker_policy_sha256", sa.String(71), nullable=False),
        sa.Column("effective_plan_sha256", sa.String(71), nullable=False),
        sa.Column("catalogue_id", sa.String(160), nullable=False),
        sa.Column("catalogue_version", sa.String(40), nullable=False),
        sa.Column("catalogue_manifest_sha256", sa.String(71), nullable=False),
        sa.Column("storage_scheme", sa.String(16), nullable=False),
        sa.Column("terminal_status", sa.String(16), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("result_manifest_sha256", sa.String(71), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("operation_identity", name="uq_pre_submit_evidence_operation"),
        sa.CheckConstraint(
            f"operation_identity ~ '{_SHA256}'", name="ck_pre_submit_evidence_operation_sha256"
        ),
        sa.CheckConstraint(
            f"archive_sha256 ~ '{_SHA256}'", name="ck_pre_submit_evidence_archive_sha256"
        ),
        sa.CheckConstraint(
            f"semantic_manifest_sha256 ~ '{_SHA256}'",
            name="ck_pre_submit_evidence_manifest_sha256",
        ),
        sa.CheckConstraint(
            f"effective_plan_sha256 ~ '{_SHA256}'", name="ck_pre_submit_evidence_plan_sha256"
        ),
        sa.CheckConstraint(
            f"catalogue_manifest_sha256 ~ '{_SHA256}'",
            name="ck_pre_submit_evidence_catalogue_sha256",
        ),
        sa.CheckConstraint(
            f"locked_guide_sha256 ~ '{_SHA256}'", name="ck_pre_submit_evidence_guide_sha256"
        ),
        sa.CheckConstraint(
            f"source_snapshot_sha256 ~ '{_SHA256}'",
            name="ck_pre_submit_evidence_source_snapshot_sha256",
        ),
        sa.CheckConstraint(
            f"locked_artifact_policy_sha256 ~ '{_SHA256}'",
            name="ck_pre_submit_evidence_artifact_policy_sha256",
        ),
        sa.CheckConstraint(
            f"locked_checker_policy_sha256 ~ '{_SHA256}'",
            name="ck_pre_submit_evidence_checker_policy_sha256",
        ),
        sa.CheckConstraint(
            f"result_manifest_sha256 ~ '{_SHA256}'",
            name="ck_pre_submit_evidence_result_manifest_sha256",
        ),
        sa.CheckConstraint(
            "archive_byte_count >= 0", name="ck_pre_submit_evidence_archive_size"
        ),
        sa.CheckConstraint("result_count > 0", name="ck_pre_submit_evidence_result_count"),
        sa.CheckConstraint(
            "(predecessor_submission_id is null and predecessor_submission_version is null) "
            "or (predecessor_submission_id is not null and "
            "predecessor_submission_version is not null)",
            name="ck_pre_submit_evidence_predecessor_shape",
        ),
        sa.CheckConstraint(
            "storage_scheme in ('local','s3')", name="ck_pre_submit_evidence_storage_scheme"
        ),
        sa.CheckConstraint(
            "terminal_status in ('passed','blocked')",
            name="ck_pre_submit_evidence_terminal_status",
        ),
        sa.CheckConstraint(
            "(terminal_status='passed' and eligible) or "
            "(terminal_status='blocked' and not eligible)",
            name="ck_pre_submit_evidence_status_eligibility",
        ),
        sa.ForeignKeyConstraint(
            ["actor_profile_id"], ["actor_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["identity_link_id"], ["actor_identity_links.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["workstream_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["task_assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["predecessor_submission_id"], ["submissions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["guide_id"], ["project_guides.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"], ["guide_source_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["effective_policy_id"],
            ["effective_project_submission_artifact_policies.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pre_submit_policy_id"], ["pre_submit_checker_policies.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["identity_link_id", "actor_profile_id"],
            ["actor_identity_links.id", "actor_identity_links.actor_profile_id"],
            name="fk_pre_submit_evidence_identity_actor",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id", "task_id", "actor_profile_id"],
            ["task_assignments.id", "task_assignments.task_id", "task_assignments.contributor_id"],
            name="fk_pre_submit_evidence_assignment",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "project_id"],
            ["workstream_tasks.id", "workstream_tasks.project_id"],
            name="fk_pre_submit_evidence_task_project",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "guide_version"],
            ["workstream_tasks.id", "workstream_tasks.locked_guide_version"],
            name="fk_pre_submit_evidence_task_guide",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "source_snapshot_id", "source_snapshot_sha256"],
            [
                "workstream_tasks.id",
                "workstream_tasks.locked_guide_source_snapshot_id",
                "workstream_tasks.locked_guide_source_snapshot_hash",
            ],
            name="fk_pre_submit_evidence_task_source_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["predecessor_submission_id", "task_id", "predecessor_submission_version"],
            ["submissions.id", "submissions.task_id", "submissions.version"],
            name="fk_pre_submit_evidence_predecessor",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "effective_policy_id", "locked_artifact_policy_sha256"],
            [
                "workstream_tasks.id",
                "workstream_tasks.locked_effective_project_submission_artifact_policy_id",
                "workstream_tasks.locked_effective_project_submission_artifact_policy_hash",
            ],
            name="fk_pre_submit_evidence_task_artifact_policy",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "pre_submit_policy_id", "locked_checker_policy_sha256"],
            [
                "workstream_tasks.id",
                "workstream_tasks.locked_pre_submit_checker_policy_id",
                "workstream_tasks.locked_pre_submit_checker_bundle_hash",
            ],
            name="fk_pre_submit_evidence_task_checker_policy",
        ),
    )
    op.create_index(
        "ix_pre_submit_evidence_sets_actor_profile_id",
        "pre_submit_evidence_sets",
        ["actor_profile_id"],
    )
    op.create_index(
        "ix_pre_submit_evidence_sets_project_id", "pre_submit_evidence_sets", ["project_id"]
    )
    op.create_index(
        "ix_pre_submit_evidence_sets_task_id", "pre_submit_evidence_sets", ["task_id"]
    )
    op.create_table(
        "pre_submit_evidence_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("evidence_set_id", sa.String(36), nullable=False),
        sa.Column("result_order", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(80), nullable=False),
        sa.Column("dispatch_authority", sa.String(160), nullable=False),
        sa.Column("definition_id", sa.String(160), nullable=False),
        sa.Column("definition_version", sa.String(40), nullable=False),
        sa.Column("public_name", sa.String(160), nullable=False),
        sa.Column("source", sa.String(160), nullable=False),
        sa.Column("phase", sa.String(40), nullable=False),
        sa.Column("classification", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("failure_code", sa.String(160)),
        sa.Column("message_code", sa.String(160), nullable=False),
        sa.Column("effective_plan_sha256", sa.String(71), nullable=False),
        sa.Column("rule_instance_id", sa.String(71)),
        sa.Column("locked_policy_sha256", sa.String(71), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "evidence_set_id", "result_order", name="uq_pre_submit_result_order"
        ),
        sa.UniqueConstraint(
            "evidence_set_id", "definition_id", name="uq_pre_submit_result_definition"
        ),
        sa.CheckConstraint("result_order >= 0", name="ck_pre_submit_result_order"),
        sa.CheckConstraint(
            "status in ('passed','warning','advisory_disabled','dependency_not_run','failed')",
            name="ck_pre_submit_result_status",
        ),
        sa.CheckConstraint(
            "phase in ('custody','identity','materialization','default_policy','project_policy')",
            name="ck_pre_submit_result_phase",
        ),
        sa.CheckConstraint(
            "classification in ('mandatory_security','mandatory_integrity',"
            "'mandatory_accountability','advisory')",
            name="ck_pre_submit_result_classification",
        ),
        sa.CheckConstraint(
            "severity in ('blocking','warning')", name="ck_pre_submit_result_severity"
        ),
        sa.CheckConstraint(
            "(classification='advisory' and severity='warning') or "
            "(classification<>'advisory' and severity='blocking')",
            name="ck_pre_submit_result_classification_severity",
        ),
        sa.CheckConstraint(
            f"effective_plan_sha256 ~ '{_SHA256}'", name="ck_pre_submit_result_plan_sha256"
        ),
        sa.CheckConstraint(
            f"locked_policy_sha256 ~ '{_SHA256}'", name="ck_pre_submit_result_policy_sha256"
        ),
        sa.CheckConstraint(
            "(phase='project_policy' and rule_instance_id is not null and "
            f"rule_instance_id ~ '{_SHA256}') or "
            "(phase<>'project_policy' and rule_instance_id is null)",
            name="ck_pre_submit_result_rule_instance_shape",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_set_id"], ["pre_submit_evidence_sets.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "ix_pre_submit_evidence_results_evidence_set_id",
        "pre_submit_evidence_results",
        ["evidence_set_id"],
    )
    _immutable_guard("pre_submit_evidence_results")
    _immutable_guard("pre_submit_evidence_sets")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("select count(*) from pre_submit_evidence_sets")).scalar_one():
        raise RuntimeError("cannot downgrade populated immutable pre-submit evidence")
    for table in ("pre_submit_evidence_sets", "pre_submit_evidence_results"):
        op.execute(f"drop trigger {table}_no_truncate on {table}")
        op.execute(f"drop trigger {table}_immutable on {table}")
        op.execute(f"drop function guard_{table}_immutable()")
    op.drop_index(
        "ix_pre_submit_evidence_results_evidence_set_id",
        table_name="pre_submit_evidence_results",
    )
    op.drop_table("pre_submit_evidence_results")
    for name in (
        "ix_pre_submit_evidence_sets_task_id",
        "ix_pre_submit_evidence_sets_project_id",
        "ix_pre_submit_evidence_sets_actor_profile_id",
    ):
        op.drop_index(name, table_name="pre_submit_evidence_sets")
    op.drop_table("pre_submit_evidence_sets")
    op.drop_constraint(
        "uq_task_assignments_id_task_contributor", "task_assignments", type_="unique"
    )
    op.drop_constraint("uq_workstream_tasks_id_project", "workstream_tasks", type_="unique")
    op.drop_constraint(
        "uq_actor_identity_links_id_profile", "actor_identity_links", type_="unique"
    )
