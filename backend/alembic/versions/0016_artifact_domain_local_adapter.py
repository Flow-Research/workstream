"""add immutable artifact domain foundation

Revision ID: 0016_artifact_domain
Revises: 0015_post_submit_correction
Create Date: 2026-07-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0016_artifact_domain"
down_revision = "0015_post_submit_correction"
branch_labels = None
depends_on = None

_ARTIFACT_TABLES = (
    "artifact_operation_receipts",
    "artifact_replicas",
    "artifact_bindings",
    "artifact_upload_items",
    "artifact_contents",
    "artifact_upload_sessions",
)


def upgrade() -> None:
    """Create additive artifact records without promoting legacy declarations."""
    op.create_table(
        "artifact_upload_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("guide_id", sa.String(36), nullable=True),
        sa.Column("permitted_roles", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("maximum_bytes", sa.Integer(), nullable=False),
        sa.Column("current_bytes", sa.Integer(), nullable=False),
        sa.Column("reserved_bytes", sa.Integer(), nullable=False),
        sa.Column("maximum_items", sa.Integer(), nullable=False),
        sa.Column("current_items", sa.Integer(), nullable=False),
        sa.Column("reserved_items", sa.Integer(), nullable=False),
        sa.Column("artifact_set_hash", sa.String(71), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cas_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "state in ('open', 'sealed', 'consumed', 'expired', 'cancelled')",
            name="state",
        ),
        sa.CheckConstraint(
            "maximum_bytes >= 0 and current_bytes >= 0 and reserved_bytes >= 0",
            name="byte_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "maximum_items >= 0 and current_items >= 0 and reserved_items >= 0",
            name="item_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "current_bytes + reserved_bytes <= maximum_bytes", name="byte_limit"
        ),
        sa.CheckConstraint(
            "current_items + reserved_items <= maximum_items", name="item_limit"
        ),
        sa.CheckConstraint("cas_version >= 0", name="cas_nonnegative"),
        sa.CheckConstraint(
            "artifact_set_hash is null or artifact_set_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="artifact_set_hash_shape",
        ),
        sa.CheckConstraint(
            "(state = 'consumed') = (consumed_at is not null)", name="consumed_timestamp"
        ),
        sa.CheckConstraint(
            "state not in ('sealed', 'consumed') or artifact_set_hash is not null",
            name="sealed_hash_required",
        ),
    )
    op.create_index("ix_artifact_upload_sessions_actor_id", "artifact_upload_sessions", ["actor_id"])
    op.create_index("ix_artifact_upload_sessions_project_id", "artifact_upload_sessions", ["project_id"])
    op.create_index("ix_artifact_upload_sessions_task_id", "artifact_upload_sessions", ["task_id"])
    op.create_index("ix_artifact_upload_sessions_guide_id", "artifact_upload_sessions", ["guide_id"])
    op.create_index("ix_artifact_upload_sessions_state", "artifact_upload_sessions", ["state"])

    op.create_table(
        "artifact_contents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sha256", sa.String(71), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(200), nullable=True),
        sa.Column("normalized_display_name", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("sha256", "byte_count", name="uq_artifact_content_digest_size"),
        sa.CheckConstraint("sha256 ~ '^sha256:[0-9a-f]{64}$'", name="sha256_shape"),
        sa.CheckConstraint("byte_count >= 0", name="byte_count_nonnegative"),
    )
    op.create_index("ix_artifact_contents_sha256", "artifact_contents", ["sha256"])

    op.create_table(
        "artifact_upload_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("logical_role", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(500), nullable=False),
        sa.Column("media_type", sa.String(200), nullable=True),
        sa.Column("reserved_bytes", sa.Integer(), nullable=False),
        sa.Column("expected_sha256", sa.String(71), nullable=True),
        sa.Column("expected_size", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("cas_version", sa.Integer(), nullable=False),
        sa.Column("provider_operation_reference", sa.String(200), nullable=True),
        sa.Column("content_id", sa.String(36), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["session_id"], ["artifact_upload_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["content_id"], ["artifact_contents.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("session_id", "idempotency_key", name="uq_artifact_item_operation"),
        sa.CheckConstraint(
            "state in ('reserved', 'uploading', 'provider_committed', "
            "'replay_required', 'ready', 'failed', 'cancelled')",
            name="state",
        ),
        sa.CheckConstraint(
            "reserved_bytes >= 0 and cas_version >= 0 and "
            "(expected_size is null or expected_size >= 0)",
            name="counts_nonnegative",
        ),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'", name="request_digest_shape"
        ),
        sa.CheckConstraint(
            "expected_sha256 is null or expected_sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="expected_sha256_shape",
        ),
        sa.CheckConstraint(
            "(state = 'ready') = "
            "(content_id is not null and provider_operation_reference is not null)",
            name="ready_result_required",
        ),
        sa.CheckConstraint("state != 'failed' or error_code is not null", name="failed_error_required"),
    )
    op.create_index("ix_artifact_upload_items_session_id", "artifact_upload_items", ["session_id"])
    op.create_index("ix_artifact_upload_items_content_id", "artifact_upload_items", ["content_id"])
    op.create_index("ix_artifact_upload_items_state", "artifact_upload_items", ["state"])

    op.create_table(
        "artifact_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("content_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=False),
        sa.Column("logical_role", sa.String(100), nullable=False),
        sa.Column("scope_version", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("attribution_type", sa.String(30), nullable=False),
        sa.Column("supersedes_binding_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["content_id"], ["artifact_contents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["supersedes_binding_id"], ["artifact_bindings.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "project_id", "resource_type", "resource_id", "logical_role", "scope_version",
            name="uq_artifact_binding_scope_version",
        ),
        sa.UniqueConstraint("supersedes_binding_id", name="uq_artifact_binding_supersedes"),
        sa.CheckConstraint("scope_version > 0", name="scope_version_positive"),
        sa.CheckConstraint(
            "(scope_version = 1 and supersedes_binding_id is null) or "
            "(scope_version > 1 and supersedes_binding_id is not null)",
            name="scope_version_predecessor",
        ),
    )
    op.create_index("ix_artifact_bindings_content_id", "artifact_bindings", ["content_id"])
    op.create_index("ix_artifact_bindings_project_id", "artifact_bindings", ["project_id"])
    op.create_index("ix_artifact_bindings_supersedes_binding_id", "artifact_bindings", ["supersedes_binding_id"])
    op.create_index(
        "ix_artifact_bindings_scope",
        "artifact_bindings",
        ["project_id", "resource_type", "resource_id", "logical_role", sa.text("scope_version DESC")],
    )

    op.create_table(
        "artifact_replicas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("content_id", sa.String(36), nullable=False),
        sa.Column("adapter", sa.String(50), nullable=False),
        sa.Column("provider_artifact_id", sa.String(200), nullable=False),
        sa.Column("provider_manifest_id", sa.String(200), nullable=True),
        sa.Column("verification_state", sa.String(30), nullable=False),
        sa.Column("retention_state", sa.String(30), nullable=False),
        sa.Column("availability_state", sa.String(30), nullable=False),
        sa.Column("integrity_state", sa.String(30), nullable=False),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["content_id"], ["artifact_contents.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("adapter", "provider_artifact_id", name="uq_artifact_replica_provider"),
        sa.CheckConstraint(
            "verification_state in ('pending', 'verified', 'failed')", name="verification_state"
        ),
        sa.CheckConstraint(
            "retention_state in ('unretained', 'retained', 'released')", name="retention_state"
        ),
        sa.CheckConstraint(
            "availability_state in ('available', 'unavailable', 'missing')",
            name="availability_state",
        ),
        sa.CheckConstraint(
            "integrity_state in ('unknown', 'valid', 'quarantined')",
            name="integrity_state",
        ),
    )
    op.create_index("ix_artifact_replicas_content_id", "artifact_replicas", ["content_id"])

    op.create_table(
        "artifact_operation_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("upload_item_id", sa.String(36), nullable=True),
        sa.Column("replica_id", sa.String(36), nullable=True),
        sa.Column("adapter", sa.String(50), nullable=False),
        sa.Column("service_principal", sa.String(200), nullable=False),
        sa.Column("operation", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("response_digest", sa.String(71), nullable=False),
        sa.Column("provider_receipt_id", sa.String(200), nullable=False),
        sa.Column("provider_operation_reference", sa.String(200), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column("retention_reference", sa.String(200), nullable=True),
        sa.Column("retention_class", sa.String(100), nullable=True),
        sa.Column("retention_owner", sa.String(200), nullable=True),
        sa.Column("provider_recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["upload_item_id"], ["artifact_upload_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["replica_id"], ["artifact_replicas.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "adapter", "service_principal", "operation", "idempotency_key",
            name="uq_artifact_receipt_operation",
        ),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$'", name="request_digest_shape"
        ),
        sa.CheckConstraint(
            "response_digest ~ '^sha256:[0-9a-f]{64}$'", name="response_digest_shape"
        ),
        sa.CheckConstraint("operation in ('store', 'verify', 'retain', 'release')", name="operation"),
        sa.CheckConstraint(
            "outcome in ('stored', 'verified', 'retained', 'released')", name="outcome"
        ),
        sa.CheckConstraint(
            "(operation = 'store' and outcome = 'stored') or "
            "(operation = 'verify' and outcome = 'verified') or "
            "(operation = 'retain' and outcome = 'retained') or "
            "(operation = 'release' and outcome = 'released')",
            name="operation_outcome",
        ),
        sa.CheckConstraint("attempt_number > 0", name="attempt_positive"),
        sa.CheckConstraint(
            "operation != 'retain' or "
            "(retention_reference is not null and retention_class is not null "
            "and retention_owner is not null)",
            name="retain_fields",
        ),
        sa.CheckConstraint(
            "operation != 'release' or "
            "(retention_reference is not null and retention_class is not null "
            "and retention_owner is not null)",
            name="release_reference",
        ),
        sa.CheckConstraint(
            "operation in ('retain', 'release') or "
            "(retention_reference is null and retention_class is null "
            "and retention_owner is null)",
            name="non_retention_fields_empty",
        ),
    )
    op.create_index("ix_artifact_operation_receipts_upload_item_id", "artifact_operation_receipts", ["upload_item_id"])
    op.create_index("ix_artifact_operation_receipts_replica_id", "artifact_operation_receipts", ["replica_id"])

    _create_artifact_guards()


def _create_artifact_guards() -> None:
    """Install immutable-row and binding-history database guards."""
    op.execute(
        """
        create function reject_artifact_fact_mutation() returns trigger
        language plpgsql as $$
        begin
            raise exception '% rows are immutable', tg_table_name;
        end;
        $$
        """
    )
    for table_name in ("artifact_contents", "artifact_bindings", "artifact_operation_receipts"):
        op.execute(
            sa.text(
                f"""
                create trigger trg_{table_name}_immutable
                before update or delete on {table_name}
                for each row execute function reject_artifact_fact_mutation()
                """
            )
        )
    op.execute(
        """
        create function validate_artifact_binding_history() returns trigger
        language plpgsql as $$
        declare predecessor artifact_bindings%rowtype;
        begin
            if new.scope_version = 1 then
                return new;
            end if;
            select * into predecessor
              from artifact_bindings where id = new.supersedes_binding_id;
            if not found
               or predecessor.project_id != new.project_id
               or predecessor.resource_type != new.resource_type
               or predecessor.resource_id != new.resource_id
               or predecessor.logical_role != new.logical_role
               or predecessor.scope_version + 1 != new.scope_version then
                raise exception 'artifact binding predecessor is invalid';
            end if;
            return new;
        end;
        $$
        """
    )
    op.execute(
        """
        create constraint trigger trg_artifact_binding_history
        after insert on artifact_bindings
        deferrable initially immediate
        for each row execute function validate_artifact_binding_history()
        """
    )


def downgrade() -> None:
    """Drop the additive foundation only when it contains no artifact facts."""
    connection = op.get_bind()
    for table_name in _ARTIFACT_TABLES:
        if connection.execute(sa.text(f"select exists(select 1 from {table_name})")).scalar():
            raise RuntimeError("cannot downgrade non-empty artifact foundation")
    op.execute("drop trigger trg_artifact_binding_history on artifact_bindings")
    op.execute("drop function validate_artifact_binding_history()")
    for table_name in ("artifact_operation_receipts", "artifact_bindings", "artifact_contents"):
        op.execute(f"drop trigger trg_{table_name}_immutable on {table_name}")
    op.execute("drop function reject_artifact_fact_mutation()")
    for table_name in _ARTIFACT_TABLES:
        op.drop_table(table_name)
